"""
Domínio 1 — Pessoas (Documento 09 / Módulo 01)

Fonte oficial de identidade de: Clínicas, Profissionais, Pacientes, Responsáveis.
Não é responsável por: Agenda, Financeiro, Exercícios, Gamificação (Doc 10).
"""
import json
import re

from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute, log_auditoria, log_evento, agora_sql
from auth import login_required, papel_required, hash_senha, verificar_senha, paciente_acessivel, paciente_editavel
from tokens_service import gerar_token as gerar_token_convite, link_para as link_para_token, gerar_senha_bloqueada
from validacao_arquivo import validar_arquivo_base64
from rate_limit import limitar
import whatsapp_service

bp = Blueprint("pessoas", __name__, url_prefix="/api/pessoas")

_RE_COR_HEX = re.compile(r"^#[0-9a-fA-F]{3,8}$")

# Achado de UAT (26/08/2026): o e-mail só era garantido único POR CLÍNICA
# (UNIQUE(organizacao_id, email) no schema), mas o login busca só por e-mail,
# sem filtrar organização (ver auth_bp.py::login) — então se duas contas de
# CLÍNICAS DIFERENTES (ou uma clínica e o admin_master) nascessem com o mesmo
# e-mail, a consulta do login sempre encontra a MESMA linha, e a segunda
# conta criada nunca mais consegue entrar, mesmo com a senha certa (falha
# silenciosa, sem nenhum aviso na hora do cadastro). Esta função bloqueia
# isso na origem: verifica o e-mail em QUALQUER organização da plataforma
# (não só a de quem está cadastrando), com a mesma mensagem em todo lugar
# que cria ou edita o e-mail de uma conta.
MENSAGEM_EMAIL_EM_USO = "Este e-mail já está em uso em outra conta da plataforma."


def _email_disponivel_globalmente(email, excluir_usuario_id=None):
    sql = "SELECT 1 FROM usuarios WHERE lower(email) = ?"
    params = [email]
    if excluir_usuario_id:
        sql += " AND id != ?"
        params.append(excluir_usuario_id)
    return query_one(sql, params) is None


def _cor_segura(valor, padrao):
    """Correção de auditoria (25/08/2026, achado do CodeQL): cor_primaria,
    cor_secundaria e cor_agenda eram gravadas sem nenhuma validação de
    formato — o front-end usa esses valores dentro de atributos HTML
    (value="" de <input type="color">, style="background:...") em várias
    telas, então um valor malicioso salvo aqui (por um gestor/admin da
    própria clínica) rodava como XSS armazenado para qualquer outro usuário
    da mesma clínica que visse essa tela. O front-end também passou a
    escapar esses valores na renderização (ver util.js::corSegura) — esta
    validação aqui é a segunda camada, que impede o dado ruim de sequer
    chegar a existir no banco."""
    return valor if isinstance(valor, str) and _RE_COR_HEX.match(valor) else padrao


def _e_profissional_ativo(usuario_id, organizacao_id):
    """
    True se `usuario_id` pode atuar como profissional desta clínica: ou é
    uma conta com papel='profissional' de verdade, ou é o GESTOR da própria
    clínica que ligou 'atuar como profissional' (insight do usuário — mesma
    conta/login, sem cadastro novo; ver /perfil/atuar-como-profissional).

    Usada em todo lugar que hoje só aceitava `papel = 'profissional'` como
    alvo de atribuição (consulta, vínculo com paciente, disponibilidade)
    para também aceitar esse gestor — mas propositalmente NÃO é usada em
    `listar_profissionais` sem o parâmetro `incluir_gestor`, nem nas rotas de
    CRUD da Equipe (`/profissionais/<id>`, `/arquivar`), que continuam
    exclusivas de contas profissional de verdade.
    """
    row = query_one(
        """SELECT 1 FROM usuarios WHERE id = ? AND organizacao_id = ? AND ativo = 1
           AND (papel = 'profissional' OR (papel = 'gestor' AND atua_como_profissional = 1))""",
        (usuario_id, organizacao_id),
    )
    return bool(row)


def _secretaria_pode_gerenciar_paciente(usuario, paciente_id):
    """
    True se `usuario` é uma secretária administrativa e o paciente é da
    mesma clínica dela. Helper deliberadamente estreito (insight do
    usuário, 31/08/2026): usado só nos dois call sites que são, de fato,
    as únicas ações NÃO clínicas que a secretária tem permissão de fazer
    sobre um paciente (vincular profissional, vincular responsável) — não
    substitui `paciente_editavel` em nenhuma outra rota, então ela continua
    sem acesso a jornada, diário, ficha clínica etc.
    """
    if usuario["papel"] != "secretaria":
        return False
    return bool(query_one(
        "SELECT 1 FROM pacientes WHERE id = ? AND organizacao_id = ?",
        (paciente_id, usuario["organizacao_id"]),
    ))


def _limite_do_plano_excedido(organizacao_id, tipo):
    """
    Correção de auditoria (item 4.10 / seção 12): `limite_pacientes` e
    `limite_profissionais` do plano existiam no schema e alimentavam só o
    painel comercial (upsell manual do time de vendas) — nenhuma rota de
    criação verificava isso antes de inserir, então uma clínica no plano mais
    barato podia cadastrar pacientes/profissionais sem limite nenhum.

    Retorna uma mensagem de erro (para devolver como 403) se o limite do
    plano foi atingido, ou None se ainda há espaço — inclusive quando o
    limite é NULL (ilimitado, comportamento já existente e intencional).
    `tipo` é "pacientes" ou "profissionais".
    """
    if not organizacao_id:
        return None  # admin_master não pertence a nenhuma clínica; não se aplica.
    org = query_one("SELECT plano FROM organizacoes WHERE id = ?", (organizacao_id,))
    if not org:
        return None
    plano = query_one(
        "SELECT nome, limite_pacientes, limite_profissionais, limite_secretarias FROM planos WHERE codigo = ?",
        (org["plano"],),
    )
    if not plano:
        return None  # plano com código desconhecido — validar isso é responsabilidade de outra rota, não bloqueia aqui.

    if tipo == "pacientes":
        limite = plano["limite_pacientes"]
        if limite is None:
            return None
        atual = query_one(
            "SELECT COUNT(*) as c FROM pacientes WHERE organizacao_id = ? AND ativo = 1", (organizacao_id,)
        )["c"]
        if atual >= limite:
            return (f"O plano {plano['nome']} permite até {limite} paciente(s) ativo(s), e sua clínica já está "
                    f"nesse limite. Fale com o time comercial para aumentar o limite ou mudar de plano.")
    elif tipo == "profissionais":
        limite = plano["limite_profissionais"]
        if limite is None:
            return None
        atual = query_one(
            "SELECT COUNT(*) as c FROM usuarios WHERE organizacao_id = ? AND papel = 'profissional' AND ativo = 1",
            (organizacao_id,),
        )["c"]
        if atual >= limite:
            return (f"O plano {plano['nome']} permite até {limite} profissional(is), e sua clínica já está "
                    f"nesse limite. Fale com o time comercial para aumentar o limite ou mudar de plano.")
    elif tipo == "secretarias":
        # Perfil opcional (insight do usuário, 31/08/2026) — diferente de
        # pacientes/profissionais, aqui 0 é um valor normal (plano que não
        # inclui o recurso), não "sem restrição configurada".
        limite = plano["limite_secretarias"]
        if limite is None:
            return None
        atual = query_one(
            "SELECT COUNT(*) as c FROM usuarios WHERE organizacao_id = ? AND papel = 'secretaria' AND ativo = 1",
            (organizacao_id,),
        )["c"]
        if atual >= limite:
            if limite == 0:
                return (f"O plano {plano['nome']} não inclui o perfil de secretária. "
                        f"Fale com o time comercial para adicionar esse recurso.")
            return (f"O plano {plano['nome']} permite até {limite} secretária(s), e sua clínica já está "
                    f"nesse limite. Fale com o time comercial para aumentar o limite ou mudar de plano.")
    return None


# ---------------------------------------------------------------- Pacientes

@bp.get("/pacientes")
@login_required
def listar_pacientes():
    u = g.usuario
    if u["papel"] in ("gestor", "admin_master"):
        rows = query(
            """SELECT p.*,
                      (SELECT COUNT(*) FROM jornadas j WHERE j.paciente_id = p.id AND j.status='ativa') AS jornadas_ativas
               FROM pacientes p WHERE p.organizacao_id = ? AND p.ativo = 1 ORDER BY p.nome""",
            (u["organizacao_id"],),
        )
    elif u["papel"] == "profissional":
        # Visualização ampliada (insight do usuário): o profissional vê todos os
        # pacientes da clínica, mas só pode EDITAR os que ele de fato atende
        # (ver `pode_editar` abaixo — o mesmo critério de `paciente_editavel`).
        rows = query(
            """SELECT p.*,
                      (SELECT COUNT(*) FROM jornadas j WHERE j.paciente_id = p.id AND j.status='ativa') AS jornadas_ativas,
                      EXISTS(SELECT 1 FROM profissionais_pacientes pp WHERE pp.usuario_id = ? AND pp.paciente_id = p.id) AS pode_editar
               FROM pacientes p WHERE p.organizacao_id = ? AND p.ativo = 1 ORDER BY pode_editar DESC, p.nome""",
            (u["id"], u["organizacao_id"]),
        )
    elif u["papel"] == "responsavel":
        rows = query(
            """SELECT p.* FROM pacientes p
               JOIN responsaveis_pacientes rp ON rp.paciente_id = p.id
               WHERE rp.usuario_id = ? AND p.ativo = 1 ORDER BY p.nome""",
            (u["id"],),
        )
    elif u["papel"] == "secretaria":
        # Insight do usuário (31/08/2026): a secretária só pode ver nome e
        # responsável — NENHUM campo clínico (jornada, diagnóstico, ficha
        # etc). Monta o nome do(s) responsável(is) em Python (em vez de
        # GROUP_CONCAT/string_agg no SQL) porque essas funções de agregação
        # de texto têm nomes diferentes em SQLite x Postgres, e o mesmo SQL
        # aqui precisa rodar nos dois (ver db.py).
        rows = query(
            "SELECT id, nome, avatar_mascote FROM pacientes WHERE organizacao_id = ? AND ativo = 1 ORDER BY nome",
            (u["organizacao_id"],),
        )
        vinculos = query(
            """SELECT rp.paciente_id, resp.nome FROM responsaveis_pacientes rp
               JOIN usuarios resp ON resp.id = rp.usuario_id
               JOIN pacientes p ON p.id = rp.paciente_id
               WHERE p.organizacao_id = ?""",
            (u["organizacao_id"],),
        )
        nomes_por_paciente = {}
        for v in vinculos:
            nomes_por_paciente.setdefault(v["paciente_id"], []).append(v["nome"])
        for p in rows:
            p["responsaveis_nomes"] = ", ".join(nomes_por_paciente.get(p["id"], []))
    else:
        rows = []
    return jsonify(rows)


@bp.get("/pacientes/<int:paciente_id>")
@login_required
def obter_paciente(paciente_id):
    u = g.usuario
    if u["papel"] == "secretaria":
        # Mesma restrição de listar_pacientes: só nome + responsável(is) +
        # quais profissionais atendem (pra poder vincular/desvincular) —
        # NUNCA os campos clínicos (genero, data_nascimento fica de fora de
        # propósito) que a linha `SELECT *` abaixo devolveria pros outros papéis.
        paciente = query_one(
            "SELECT id, nome, avatar_mascote FROM pacientes WHERE id = ? AND organizacao_id = ?",
            (paciente_id, u["organizacao_id"]),
        )
        if not paciente:
            return jsonify({"erro": "Paciente não encontrado."}), 404
    elif not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Você não tem acesso a este paciente."}), 403
    else:
        paciente = query_one("SELECT * FROM pacientes WHERE id = ?", (paciente_id,))
        if not paciente:
            return jsonify({"erro": "Paciente não encontrado."}), 404
    responsaveis = query(
        """SELECT u.id, u.nome, u.email, u.telefone, rp.parentesco
           FROM usuarios u JOIN responsaveis_pacientes rp ON rp.usuario_id = u.id
           WHERE rp.paciente_id = ?""",
        (paciente_id,),
    )
    profissionais = query(
        """SELECT u.id, u.nome, u.especialidade, pp.principal
           FROM usuarios u JOIN profissionais_pacientes pp ON pp.usuario_id = u.id
           WHERE pp.paciente_id = ?""",
        (paciente_id,),
    )
    paciente["responsaveis"] = responsaveis
    paciente["profissionais"] = profissionais
    return jsonify(paciente)


@bp.put("/pacientes/<int:paciente_id>")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def editar_paciente(paciente_id):
    """Edição dos dados básicos de identidade — Gestor e Profissional (vinculado) podem editar."""
    if not paciente_editavel(paciente_id):
        return jsonify({"erro": "Você não tem acesso a este paciente."}), 403
    paciente = query_one("SELECT * FROM pacientes WHERE id = ?", (paciente_id,))
    if not paciente:
        return jsonify({"erro": "Paciente não encontrado."}), 404
    body = request.get_json(force=True, silent=True) or {}
    nome = (body.get("nome") or paciente["nome"]).strip()
    if not nome:
        return jsonify({"erro": "Nome é obrigatório."}), 400
    execute(
        "UPDATE pacientes SET nome = ?, data_nascimento = ?, genero = ? WHERE id = ?",
        (nome, body.get("data_nascimento", paciente["data_nascimento"]), body.get("genero", paciente["genero"]), paciente_id),
    )
    log_auditoria(g.usuario["organizacao_id"], g.usuario["id"], "editar", "paciente", paciente_id, nome)
    return jsonify({"ok": True})


@bp.post("/pacientes/<int:paciente_id>/vincular-profissional")
@login_required
@papel_required("gestor", "admin_master", "secretaria")
def vincular_profissional(paciente_id):
    """Adiciona mais um profissional à equipe que atende o paciente (Gestor
    decide quem entra na equipe — ou a secretária, insight do usuário 31/08/2026)."""
    if not (paciente_editavel(paciente_id) or _secretaria_pode_gerenciar_paciente(g.usuario, paciente_id)):
        return jsonify({"erro": "Você não tem acesso a este paciente."}), 403
    body = request.get_json(force=True, silent=True) or {}
    profissional_id = body.get("profissional_id")
    if not _e_profissional_ativo(profissional_id, g.usuario["organizacao_id"]):
        return jsonify({"erro": "Profissional não encontrado nesta clínica."}), 404
    prof = query_one("SELECT * FROM usuarios WHERE id = ?", (profissional_id,))
    ja_vinculado = query_one(
        "SELECT 1 FROM profissionais_pacientes WHERE usuario_id = ? AND paciente_id = ?",
        (profissional_id, paciente_id),
    )
    if ja_vinculado:
        return jsonify({"erro": "Este profissional já atende este paciente."}), 409
    ja_tem_principal = query_one("SELECT 1 FROM profissionais_pacientes WHERE paciente_id = ? AND principal = 1", (paciente_id,))
    execute(
        "INSERT INTO profissionais_pacientes (usuario_id, paciente_id, principal) VALUES (?, ?, ?)",
        (profissional_id, paciente_id, 0 if ja_tem_principal else 1),
    )
    log_auditoria(g.usuario["organizacao_id"], g.usuario["id"], "vincular", "profissional_paciente", paciente_id, prof["nome"])
    return jsonify({"ok": True})


# ---------------------------------------------------------------- Ficha Clínica (Doc 34 — opcional, sub-registro separado)

@bp.get("/pacientes/<int:paciente_id>/ficha-clinica")
@login_required
def obter_ficha_clinica(paciente_id):
    """
    Sub-registro totalmente opcional (Doc 34 — ClinicalProfile): diagnóstico,
    alergias, medicações e profissionais externos, separados da identidade
    básica do paciente. Se nunca foi preenchida, devolve um objeto vazio —
    não é erro, é o estado normal e esperado pra maioria dos pacientes.
    """
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Você não tem acesso a este paciente."}), 403
    ficha = query_one(
        """SELECT f.*, u.nome as atualizado_por_nome FROM fichas_clinicas f
           LEFT JOIN usuarios u ON u.id = f.atualizado_por WHERE f.paciente_id = ?""",
        (paciente_id,),
    )
    if not ficha:
        return jsonify({"preenchida": False, "paciente_id": paciente_id})
    ficha["preenchida"] = True
    return jsonify(ficha)


@bp.put("/pacientes/<int:paciente_id>/ficha-clinica")
@login_required
@papel_required("gestor", "profissional")
def atualizar_ficha_clinica(paciente_id):
    """Criar/editar a ficha — só a clínica (gestor/profissional vinculado) pode
    escrever; o responsável só visualiza (é informação clínica, não autodeclarada)."""
    if not paciente_editavel(paciente_id):
        return jsonify({"erro": "Você não tem acesso a este paciente."}), 403
    body = request.get_json(force=True, silent=True) or {}
    existente = query_one("SELECT id FROM fichas_clinicas WHERE paciente_id = ?", (paciente_id,))
    campos = (body.get("diagnostico", ""), body.get("alergias", ""), body.get("medicamentos_em_uso", ""),
              body.get("profissionais_externos", ""), body.get("observacoes", ""), g.usuario["id"])
    if existente:
        execute(
            """UPDATE fichas_clinicas SET diagnostico = ?, alergias = ?, medicamentos_em_uso = ?,
               profissionais_externos = ?, observacoes = ?, atualizado_por = ?, atualizado_em = ?
               WHERE paciente_id = ?""",
            campos + (agora_sql(), paciente_id),
        )
    else:
        execute(
            """INSERT INTO fichas_clinicas (paciente_id, diagnostico, alergias, medicamentos_em_uso,
               profissionais_externos, observacoes, atualizado_por)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (paciente_id,) + campos,
        )
    log_auditoria(g.usuario["organizacao_id"], g.usuario["id"], "atualizar", "ficha_clinica", paciente_id, "Ficha clínica")
    return jsonify({"ok": True})


def criar_paciente_core(organizacao_id, nome, nascimento, avatar_mascote=None, genero=None):
    """
    Núcleo do cadastro de um paciente: só o INSERT em `pacientes` +
    `gamificacao_paciente`. Extraído (02/09/2026) para ser reaproveitado
    pela importação em lote (importacao_bp.py) sem duplicar essa lógica —
    quem chama continua responsável por checar `_limite_do_plano_excedido`
    antes e por tratar vínculos de responsáveis/profissionais depois.
    """
    paciente_id = execute(
        """INSERT INTO pacientes (organizacao_id, nome, data_nascimento, avatar_mascote, genero)
           VALUES (?, ?, ?, ?, ?)""",
        (organizacao_id, nome, nascimento, avatar_mascote or "🐻", genero),
    )
    execute("INSERT INTO gamificacao_paciente (paciente_id) VALUES (?)", (paciente_id,))
    return paciente_id


def vincular_responsavel_core(organizacao_id, paciente_id, nome, email, telefone=None, parentesco="Responsável",
                               enviar_whatsapp=True):
    """
    Núcleo de "vincular responsável a um paciente": reaproveita a conta já
    existente NESTA clínica com o mesmo e-mail (ver comentário grande logo
    abaixo, na rota `vincular_responsavel`, para o porquê disso ser
    restrito à própria organização) ou cria uma conta nova com convite de
    ativação. Extraído (02/09/2026) para a importação em lote
    (importacao_bp.py) reaproveitar exatamente a mesma regra de segurança
    que já protege o cadastro manual contra duplicar a conta de uma família
    que já tem outro filho na clínica (ver test_segundo_filho_mesmo_responsavel.py).

    Retorna um dict {usuario_id, link_convite?, enviado_whatsapp?} — mesmo
    formato da resposta HTTP da rota, sem o `jsonify`/status code.
    """
    email = (email or "").strip().lower()
    telefone = (telefone or "").strip()
    existente = query_one(
        "SELECT * FROM usuarios WHERE organizacao_id = ? AND lower(email) = ?",
        (organizacao_id, email),
    )
    link_convite = None
    if existente:
        usuario_id = existente["id"]
        if telefone:
            execute("UPDATE usuarios SET telefone = ? WHERE id = ?", (telefone, usuario_id))
    else:
        senha_hash, salt = hash_senha(gerar_senha_bloqueada())
        usuario_id = execute(
            """INSERT INTO usuarios (organizacao_id, nome, email, telefone, senha_hash, senha_salt, papel)
               VALUES (?, ?, ?, ?, ?, ?, 'responsavel')""",
            (organizacao_id, nome, email, telefone, senha_hash, salt),
        )
        token = gerar_token_convite(usuario_id, tipo="convite")
        link_convite = link_para_token(token)
    execute(
        """INSERT INTO responsaveis_pacientes (usuario_id, paciente_id, parentesco) VALUES (?, ?, ?)
           ON CONFLICT (usuario_id, paciente_id) DO NOTHING""",
        (usuario_id, paciente_id, parentesco),
    )
    log_evento(organizacao_id, "responsavel_vinculado", "paciente", paciente_id, paciente_id)
    resposta = {"usuario_id": usuario_id}
    if link_convite:
        resposta["link_convite"] = link_convite
        if enviar_whatsapp:
            resposta["enviado_whatsapp"] = whatsapp_service.enviar_convite_responsavel(usuario_id, link_convite)
    return resposta


@bp.post("/pacientes")
@login_required
@papel_required("gestor", "admin_master", "profissional", "secretaria")
def criar_paciente():
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    nome = (body.get("nome") or "").strip()
    nascimento = body.get("data_nascimento")
    if not nome or not nascimento:
        return jsonify({"erro": "Nome e data de nascimento são obrigatórios."}), 400

    erro_limite = _limite_do_plano_excedido(u["organizacao_id"], "pacientes")
    if erro_limite:
        return jsonify({"erro": erro_limite}), 403

    paciente_id = criar_paciente_core(
        u["organizacao_id"], nome, nascimento, body.get("avatar_mascote"), body.get("genero"),
    )

    # Vínculos opcionais enviados na criação.
    # Correção de auditoria: os ids recebidos no corpo da requisição precisam
    # ser validados contra a própria clínica antes de virar vínculo — sem
    # isso, um gestor podia passar o id de um usuário de OUTRA clínica (ex:
    # um profissional ou responsável de outra organização) e dar a essa
    # pessoa acesso permanente a este paciente.
    for resp_id in body.get("responsaveis_ids", []):
        if not query_one(
            "SELECT 1 FROM usuarios WHERE id = ? AND organizacao_id = ? AND papel = 'responsavel'",
            (resp_id, u["organizacao_id"]),
        ):
            continue
        execute(
            """INSERT INTO responsaveis_pacientes (usuario_id, paciente_id, parentesco) VALUES (?, ?, ?)
               ON CONFLICT (usuario_id, paciente_id) DO NOTHING""",
            (resp_id, paciente_id, "Responsável"),
        )
    if u["papel"] == "profissional":
        execute(
            """INSERT INTO profissionais_pacientes (usuario_id, paciente_id, principal) VALUES (?, ?, 1)
               ON CONFLICT (usuario_id, paciente_id) DO NOTHING""",
            (u["id"], paciente_id),
        )
    else:
        # Gestor escolhe 1+ profissionais pra já atender o paciente (o primeiro válido vira o principal).
        principal_definido = False
        for prof_id in body.get("profissionais_ids", []):
            if not _e_profissional_ativo(prof_id, u["organizacao_id"]):
                continue
            execute(
                """INSERT INTO profissionais_pacientes (usuario_id, paciente_id, principal) VALUES (?, ?, ?)
                   ON CONFLICT (usuario_id, paciente_id) DO NOTHING""",
                (prof_id, paciente_id, 0 if principal_definido else 1),
            )
            principal_definido = True

    log_auditoria(u["organizacao_id"], u["id"], "criar", "paciente", paciente_id, nome)
    log_evento(u["organizacao_id"], "paciente_criado", "paciente", paciente_id, paciente_id)
    return jsonify({"id": paciente_id}), 201


@bp.post("/pacientes/<int:paciente_id>/vincular-responsavel")
@login_required
@papel_required("gestor", "admin_master", "profissional", "secretaria")
def vincular_responsavel(paciente_id):
    if not (paciente_editavel(paciente_id) or _secretaria_pode_gerenciar_paciente(g.usuario, paciente_id)):
        return jsonify({"erro": "Você não tem permissão para editar este paciente."}), 403
    body = request.get_json(force=True, silent=True) or {}
    nome = body.get("nome")
    email = (body.get("email") or "").strip().lower()
    telefone = (body.get("telefone") or "").strip()
    parentesco = body.get("parentesco", "Responsável")
    if not nome or not email:
        return jsonify({"erro": "Nome e e-mail do responsável são obrigatórios."}), 400

    # Correção de auditoria: a busca (dentro do helper abaixo) precisa ser
    # restrita à própria clínica. O e-mail só é único POR clínica
    # (UNIQUE(organizacao_id, email) no schema) — sem o filtro de
    # organizacao_id, uma busca sem escopo podia encontrar a conta de um
    # usuário de OUTRA clínica com o mesmo e-mail e vinculá-la como
    # responsável a este paciente, vazando os dados dele pra uma família que
    # não tem nada a ver com essa clínica.
    #
    # NÃO aplicar _email_disponivel_globalmente aqui de propósito: um
    # responsável pode legitimamente ter filhos em clínicas diferentes com o
    # mesmo e-mail — o design já escolhido (e coberto por
    # test_vincular_responsavel_por_email_nao_reaproveita_conta_de_outra_clinica
    # em tests/test_idor_pessoas.py) é criar uma conta NOVA e isolada por
    # clínica nesse caso, nunca reaproveitar a conta de outra clínica (isso
    # vazaria os pacientes dela). O efeito colateral conhecido (login por
    # e-mail só alcança uma das duas contas — ver MENSAGEM_EMAIL_EM_USO acima
    # e auth_bp.py::login) fica registrado como limitação aceita para
    # responsável nesta rodada; a checagem global É aplicada para
    # gestor/profissional/admin (papéis sem esse cenário legítimo de "mesma
    # pessoa em clínicas diferentes"). Convite de ativação (Doc 31A/35/36): a
    # conta nasce com senha bloqueada (aleatória, impossível de adivinhar)
    # até a pessoa abrir o link e criar a própria senha.
    resposta = vincular_responsavel_core(
        g.usuario["organizacao_id"], paciente_id, nome, email, telefone, parentesco,
    )
    return jsonify(resposta), 201


def _responsavel_vinculado_ou_404(paciente_id, usuario_id):
    """Confirma que usuario_id é de fato um responsável VINCULADO a este
    paciente, dentro da própria clínica de quem está pedindo — mesma lógica
    de isolamento das rotas de IDOR já cobertas pelos testes de auditoria."""
    if not paciente_editavel(paciente_id):
        return None
    return query_one(
        """SELECT u.id, u.nome, u.email, u.telefone FROM usuarios u
           JOIN responsaveis_pacientes rp ON rp.usuario_id = u.id
           WHERE rp.paciente_id = ? AND u.id = ? AND u.organizacao_id = ? AND u.papel = 'responsavel'""",
        (paciente_id, usuario_id, g.usuario["organizacao_id"]),
    )


@bp.put("/pacientes/<int:paciente_id>/responsaveis/<int:usuario_id>")
@login_required
@papel_required("gestor", "admin_master", "profissional")
def editar_responsavel_vinculado(paciente_id, usuario_id):
    """Achado de UAT (26/08/2026): não dava pra corrigir nome/e-mail/telefone
    nem o grau de parentesco de um responsável já vinculado — só cadastrar
    um novo. Edita os dados da CONTA do responsável e o parentesco deste
    vínculo específico com este paciente."""
    resp = _responsavel_vinculado_ou_404(paciente_id, usuario_id)
    if not resp:
        return jsonify({"erro": "Responsável não encontrado neste paciente."}), 404
    body = request.get_json(force=True, silent=True) or {}
    nome = (body.get("nome") or resp["nome"]).strip()
    email = (body.get("email") or resp["email"]).strip().lower()
    telefone = (body.get("telefone") or resp["telefone"] or "").strip()
    parentesco = body.get("parentesco")
    if not nome or not email:
        return jsonify({"erro": "Nome e e-mail são obrigatórios."}), 400
    if email != resp["email"].lower() and query_one(
        "SELECT 1 FROM usuarios WHERE organizacao_id = ? AND lower(email) = ? AND id != ?",
        (g.usuario["organizacao_id"], email, usuario_id),
    ):
        return jsonify({"erro": "Já existe um usuário com este e-mail nesta clínica."}), 409
    # _email_disponivel_globalmente NÃO se aplica a responsável de propósito
    # — ver o comentário equivalente em vincular_responsavel, acima.

    execute("UPDATE usuarios SET nome = ?, email = ?, telefone = ? WHERE id = ?", (nome, email, telefone, usuario_id))
    if parentesco:
        execute(
            "UPDATE responsaveis_pacientes SET parentesco = ? WHERE usuario_id = ? AND paciente_id = ?",
            (parentesco, usuario_id, paciente_id),
        )
    log_auditoria(g.usuario["organizacao_id"], g.usuario["id"], "editar", "responsavel", usuario_id, nome)
    return jsonify({"ok": True})


@bp.delete("/pacientes/<int:paciente_id>/responsaveis/<int:usuario_id>")
@login_required
@papel_required("gestor", "admin_master")
def remover_vinculo_responsavel(paciente_id, usuario_id):
    """Achado de UAT (26/08/2026): não dava pra desvincular um responsável
    cadastrado por engano (ou que perdeu a guarda etc). Remove só o VÍNCULO
    com este paciente — a conta do responsável continua existindo (ela pode
    estar vinculada a outros pacientes), consistente com o padrão de
    'arquivar em vez de apagar' usado no resto da plataforma."""
    resp = _responsavel_vinculado_ou_404(paciente_id, usuario_id)
    if not resp:
        return jsonify({"erro": "Responsável não encontrado neste paciente."}), 404
    execute("DELETE FROM responsaveis_pacientes WHERE usuario_id = ? AND paciente_id = ?", (usuario_id, paciente_id))
    log_auditoria(g.usuario["organizacao_id"], g.usuario["id"], "desvincular", "responsavel", usuario_id, resp["nome"])
    log_evento(g.usuario["organizacao_id"], "responsavel_desvinculado", "paciente", paciente_id, paciente_id)
    return jsonify({"ok": True})


@bp.post("/pacientes/<int:paciente_id>/responsaveis/<int:usuario_id>/reenviar-convite")
@login_required
@papel_required("gestor", "admin_master", "profissional")
def reenviar_convite_responsavel(paciente_id, usuario_id):
    """Achado de UAT (26/08/2026): se quem cadastrou o responsável fechasse o
    modal sem copiar o link de ativação (Doc 31A/35/36), não havia como
    recuperá-lo depois — só cadastrando tudo de novo. Gera um novo token de
    convite/redefinição válido (mesmo mecanismo de 'esqueci minha senha',
    ver tokens_service.py) e devolve o link pra reenviar."""
    resp = _responsavel_vinculado_ou_404(paciente_id, usuario_id)
    if not resp:
        return jsonify({"erro": "Responsável não encontrado neste paciente."}), 404
    token = gerar_token_convite(usuario_id, tipo="convite")
    link_convite = link_para_token(token)
    log_auditoria(g.usuario["organizacao_id"], g.usuario["id"], "reenviar_convite", "responsavel", usuario_id, resp["nome"])
    enviado_whatsapp = whatsapp_service.enviar_convite_responsavel(usuario_id, link_convite)
    return jsonify({"link_convite": link_convite, "enviado_whatsapp": enviado_whatsapp})


# ---------------------------------------------------------------- Profissionais

PALETA_CORES_AGENDA = ["#5B4FE9", "#E8385A", "#10B981", "#F59E0B", "#8B5CF6", "#0EA5E9", "#EC4899", "#84CC16", "#F97316", "#14B8A6"]

# Mascotes válidos para pacientes.avatar_mascote (insight do usuário,
# 31/08/2026: provisório até existir a Gamificação de verdade com mascotes
# próprios). Mesma lista usada no front-end (frontend/js/util.js ::
# MASCOTES_DISPONIVEIS) — mantida aqui em espelho para nunca aceitar um
# emoji arbitrário (evita lixo/abuso no campo).
MASCOTES_VALIDOS = ["🐻", "🐰", "🦁", "🐼", "🐨", "🦊", "🐯", "🐸", "🐧", "🦄"]


@bp.get("/profissionais")
@login_required
def listar_profissionais():
    incluir_inativos = request.args.get("incluir_inativos") == "1"
    # `incluir_gestor`: usado pelas telas que selecionam um profissional pra
    # atribuir algo (agenda, vínculo com paciente) — inclui o gestor que
    # ligou "atuar como profissional" (ver _e_profissional_ativo) junto dos
    # profissionais de verdade. Propositalmente NÃO é o padrão: a tela de
    # Equipe (gestão/edição/arquivamento de profissionais) chama esta rota
    # sem esse parâmetro, porque o gestor não é um cadastro de equipe — as
    # rotas de editar/arquivar profissional continuam exclusivas de
    # papel='profissional' e quebrariam para a linha dele.
    incluir_gestor = request.args.get("incluir_gestor") == "1"
    # `incluir_secretarias` (insight do usuário, 31/08/2026): usado só pela
    # tela de Equipe, que passou a listar secretárias junto dos
    # profissionais (com selo distinto no front). Propositalmente separado
    # de `incluir_gestor` — as telas que selecionam alvo de agenda/vínculo
    # de paciente não devem ganhar secretárias como opção, já que elas não
    # atendem paciente nenhum.
    incluir_secretarias = request.args.get("incluir_secretarias") == "1"
    partes_papel = ["papel = 'profissional'"]
    if incluir_gestor:
        partes_papel.append("(papel = 'gestor' AND atua_como_profissional = 1)")
    if incluir_secretarias:
        partes_papel.append("papel = 'secretaria'")
    condicao_papel = "(" + " OR ".join(partes_papel) + ")"
    sql = f"""SELECT id, nome, email, telefone, especialidade, avatar_emoji, avatar_base64, ativo, papel,
                    cor_agenda, agenda_permissao_total, tipo_registro, numero_registro,
                    (SELECT COUNT(*) FROM profissionais_pacientes pp WHERE pp.usuario_id = usuarios.id) AS total_pacientes
             FROM usuarios WHERE organizacao_id = ? AND {condicao_papel}"""
    if not incluir_inativos:
        sql += " AND ativo = 1"
    sql += " ORDER BY nome"
    rows = query(sql, (g.usuario["organizacao_id"],))
    return jsonify(rows)


@bp.post("/profissionais")
@login_required
@papel_required("gestor", "admin_master")
def criar_profissional():
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    nome = (body.get("nome") or "").strip()
    email = (body.get("email") or "").strip().lower()
    especialidade = body.get("especialidade", "")
    telefone = (body.get("telefone") or "").strip()
    if not nome or not email:
        return jsonify({"erro": "Nome e e-mail são obrigatórios."}), 400
    if query_one("SELECT 1 FROM usuarios WHERE organizacao_id = ? AND lower(email) = ?", (u["organizacao_id"], email)):
        return jsonify({"erro": "Já existe um usuário com este e-mail nesta clínica."}), 409
    # Achado de UAT (26/08/2026) — ver MENSAGEM_EMAIL_EM_USO.
    if not _email_disponivel_globalmente(email):
        return jsonify({"erro": MENSAGEM_EMAIL_EM_USO}), 409

    erro_limite = _limite_do_plano_excedido(u["organizacao_id"], "profissionais")
    if erro_limite:
        return jsonify({"erro": erro_limite}), 403

    avatar_base64 = body.get("avatar_base64")
    if avatar_base64:
        if int(len(avatar_base64) * 3 / 4) > LIMITE_FOTO_BYTES:
            return jsonify({"erro": f"Foto muito grande (limite de {LIMITE_FOTO_BYTES // (1024*1024)}MB)."}), 400
        ok, erro_assinatura = validar_arquivo_base64(avatar_base64, "imagem")
        if not ok:
            return jsonify({"erro": erro_assinatura}), 400

    # Cor da agenda: usa a escolhida, ou atribui automaticamente da paleta
    # (ciclando pelo total de profissionais já cadastrados) pra já nascer
    # visualmente distinta das demais, sem o gestor precisar escolher.
    total_atual = query_one("SELECT COUNT(*) as c FROM usuarios WHERE organizacao_id = ? AND papel = 'profissional'", (u["organizacao_id"],))["c"]
    cor_padrao_ciclo = PALETA_CORES_AGENDA[total_atual % len(PALETA_CORES_AGENDA)]
    cor_agenda = _cor_segura(body.get("cor_agenda"), cor_padrao_ciclo)
    # Se o gestor já ligou o padrão "todo profissional gerencia qualquer
    # agenda" (ver /equipe/agenda-permissao-total-padrao), o profissional
    # novo já nasce com a permissão — sem isso, cai no valor explícito do
    # formulário (ou desligado, por padrão).
    if "agenda_permissao_total" in body:
        agenda_permissao_total = 1 if body.get("agenda_permissao_total") else 0
    else:
        org_padrao = query_one("SELECT agenda_permissao_total_padrao FROM organizacoes WHERE id = ?", (u["organizacao_id"],))
        agenda_permissao_total = 1 if (org_padrao and org_padrao["agenda_permissao_total_padrao"]) else 0

    senha_hash, salt = hash_senha(gerar_senha_bloqueada())
    novo_id = execute(
        """INSERT INTO usuarios (organizacao_id, nome, email, telefone, senha_hash, senha_salt, papel, especialidade,
                                  avatar_base64, avatar_nome, cor_agenda, agenda_permissao_total, tipo_registro, numero_registro)
           VALUES (?, ?, ?, ?, ?, ?, 'profissional', ?, ?, ?, ?, ?, ?, ?)""",
        (u["organizacao_id"], nome, email, telefone, senha_hash, salt, especialidade, avatar_base64, body.get("avatar_nome"),
         cor_agenda, agenda_permissao_total, body.get("tipo_registro", ""), body.get("numero_registro", "")),
    )
    token = gerar_token_convite(novo_id, tipo="convite")
    link_convite = link_para_token(token)
    log_auditoria(u["organizacao_id"], u["id"], "criar", "profissional", novo_id, nome)
    log_evento(u["organizacao_id"], "profissional_vinculado", "usuario", novo_id)
    return jsonify({"id": novo_id, "link_convite": link_convite}), 201


@bp.put("/profissionais/<int:profissional_id>")
@login_required
@papel_required("gestor", "admin_master")
def editar_profissional(profissional_id):
    u = g.usuario
    prof = query_one(
        "SELECT * FROM usuarios WHERE id = ? AND organizacao_id = ? AND papel = 'profissional'",
        (profissional_id, u["organizacao_id"]),
    )
    if not prof:
        return jsonify({"erro": "Profissional não encontrado nesta clínica."}), 404
    body = request.get_json(force=True, silent=True) or {}
    nome = (body.get("nome") or prof["nome"]).strip()
    email = (body.get("email") or prof["email"]).strip().lower()
    if email != prof["email"].lower() and query_one(
        "SELECT 1 FROM usuarios WHERE organizacao_id = ? AND lower(email) = ? AND id != ?",
        (u["organizacao_id"], email, profissional_id),
    ):
        return jsonify({"erro": "Já existe um usuário com este e-mail nesta clínica."}), 409
    # Achado de UAT (26/08/2026) — ver MENSAGEM_EMAIL_EM_USO.
    if email != prof["email"].lower() and not _email_disponivel_globalmente(email, excluir_usuario_id=profissional_id):
        return jsonify({"erro": MENSAGEM_EMAIL_EM_USO}), 409

    avatar_base64 = body.get("avatar_base64")
    if avatar_base64:
        if int(len(avatar_base64) * 3 / 4) > LIMITE_FOTO_BYTES:
            return jsonify({"erro": f"Foto muito grande (limite de {LIMITE_FOTO_BYTES // (1024*1024)}MB)."}), 400
        ok, erro_assinatura = validar_arquivo_base64(avatar_base64, "imagem")
        if not ok:
            return jsonify({"erro": erro_assinatura}), 400
    else:
        avatar_base64 = prof["avatar_base64"]

    execute(
        """UPDATE usuarios SET nome = ?, email = ?, telefone = ?, especialidade = ?, avatar_base64 = ?, avatar_nome = ?,
           cor_agenda = ?, agenda_permissao_total = ?, tipo_registro = ?, numero_registro = ? WHERE id = ?""",
        (nome, email, body.get("telefone", prof["telefone"]), body.get("especialidade", prof["especialidade"]),
         avatar_base64, body.get("avatar_nome", prof["avatar_nome"]),
         _cor_segura(body.get("cor_agenda", prof["cor_agenda"]), prof["cor_agenda"]), 1 if body.get("agenda_permissao_total") else 0,
         body.get("tipo_registro", prof["tipo_registro"]), body.get("numero_registro", prof["numero_registro"]),
         profissional_id),
    )
    log_auditoria(u["organizacao_id"], u["id"], "editar", "profissional", profissional_id, nome)
    return jsonify({"ok": True})


@bp.put("/equipe/agenda-permissao-total-padrao")
@login_required
@papel_required("gestor", "admin_master")
def definir_agenda_permissao_total_padrao():
    """
    Liga/desliga de uma vez só, para TODA a equipe, a permissão que hoje só
    dava pra marcar profissional por profissional no cadastro (insight do
    usuário: 'quero que todos os profissionais possam editar qualquer
    agenda depois que eu liberar, sem precisar abrir um por um').

    - Ativando: todo profissional já cadastrado ganha
      `agenda_permissao_total = 1` na hora, e qualquer profissional novo já
      nasce com a permissão (ver `criar_profissional`).
    - Desativando: reverte todo mundo para `0`. Quem precisar de uma
      exceção pontual continua podendo marcar a caixinha individual no
      cadastro de cada profissional (isso não muda).
    """
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    ativo = 1 if body.get("ativo") else 0

    execute("UPDATE organizacoes SET agenda_permissao_total_padrao = ? WHERE id = ?", (ativo, u["organizacao_id"]))
    execute(
        "UPDATE usuarios SET agenda_permissao_total = ? WHERE organizacao_id = ? AND papel = 'profissional'",
        (ativo, u["organizacao_id"]),
    )
    total = query_one(
        "SELECT COUNT(*) as c FROM usuarios WHERE organizacao_id = ? AND papel = 'profissional'",
        (u["organizacao_id"],),
    )["c"]
    log_auditoria(
        u["organizacao_id"], u["id"], "definir_agenda_permissao_total_padrao", "organizacao", u["organizacao_id"],
        f"padrão -> {'ativo' if ativo else 'inativo'} ({total} profissionais afetados)",
    )
    return jsonify({"ativo": bool(ativo), "profissionais_atualizados": total})


@bp.put("/profissionais/<int:profissional_id>/arquivar")
@login_required
@papel_required("gestor", "admin_master")
def arquivar_profissional(profissional_id):
    """
    'Excluir' um profissional na prática arquiva (inativa) o cadastro — nunca
    apagamos fisicamente dados clínicos vinculados (histórico de missões,
    diários, evoluções continuam intactos e consultáveis).
    """
    u = g.usuario
    prof = query_one(
        "SELECT * FROM usuarios WHERE id = ? AND organizacao_id = ? AND papel = 'profissional'",
        (profissional_id, u["organizacao_id"]),
    )
    if not prof:
        return jsonify({"erro": "Profissional não encontrado nesta clínica."}), 404
    novo_estado = 0 if prof["ativo"] else 1
    execute("UPDATE usuarios SET ativo = ? WHERE id = ?", (novo_estado, profissional_id))
    total_pacientes = query_one(
        "SELECT COUNT(*) as c FROM profissionais_pacientes WHERE usuario_id = ?", (profissional_id,)
    )["c"]
    log_auditoria(u["organizacao_id"], u["id"], "arquivar" if not novo_estado else "reativar",
                  "profissional", profissional_id, prof["nome"])
    return jsonify({"ativo": bool(novo_estado), "total_pacientes_vinculados": total_pacientes})


# ---------------------------------------------------------------- Equipe (Secretárias) — apenas Gestor
#
# Perfil opcional cadastrado pelo gestor (insight do usuário, 31/08/2026):
# cadastro deliberadamente mais simples que o de profissional (sem
# especialidade/registro/cor de agenda/permissão de agenda — ela já tem
# acesso total à agenda por ser uma função administrativa, não clínica; ver
# agenda_bp.py). Cadastro/edição/arquivamento continuam exclusivos de
# gestor/admin_master, igual ao padrão de profissional acima.

@bp.post("/secretarias")
@login_required
@papel_required("gestor", "admin_master")
def criar_secretaria():
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    nome = (body.get("nome") or "").strip()
    email = (body.get("email") or "").strip().lower()
    telefone = (body.get("telefone") or "").strip()
    if not nome or not email:
        return jsonify({"erro": "Nome e e-mail são obrigatórios."}), 400
    if query_one("SELECT 1 FROM usuarios WHERE organizacao_id = ? AND lower(email) = ?", (u["organizacao_id"], email)):
        return jsonify({"erro": "Já existe um usuário com este e-mail nesta clínica."}), 409
    if not _email_disponivel_globalmente(email):
        return jsonify({"erro": MENSAGEM_EMAIL_EM_USO}), 409

    erro_limite = _limite_do_plano_excedido(u["organizacao_id"], "secretarias")
    if erro_limite:
        return jsonify({"erro": erro_limite}), 403

    senha_hash, salt = hash_senha(gerar_senha_bloqueada())
    novo_id = execute(
        """INSERT INTO usuarios (organizacao_id, nome, email, telefone, senha_hash, senha_salt, papel)
           VALUES (?, ?, ?, ?, ?, ?, 'secretaria')""",
        (u["organizacao_id"], nome, email, telefone, senha_hash, salt),
    )
    token = gerar_token_convite(novo_id, tipo="convite")
    link_convite = link_para_token(token)
    log_auditoria(u["organizacao_id"], u["id"], "criar", "secretaria", novo_id, nome)
    return jsonify({"id": novo_id, "link_convite": link_convite}), 201


@bp.put("/secretarias/<int:secretaria_id>")
@login_required
@papel_required("gestor", "admin_master")
def editar_secretaria(secretaria_id):
    u = g.usuario
    sec = query_one(
        "SELECT * FROM usuarios WHERE id = ? AND organizacao_id = ? AND papel = 'secretaria'",
        (secretaria_id, u["organizacao_id"]),
    )
    if not sec:
        return jsonify({"erro": "Secretária não encontrada nesta clínica."}), 404
    body = request.get_json(force=True, silent=True) or {}
    nome = (body.get("nome") or sec["nome"]).strip()
    email = (body.get("email") or sec["email"]).strip().lower()
    if email != sec["email"].lower() and query_one(
        "SELECT 1 FROM usuarios WHERE organizacao_id = ? AND lower(email) = ? AND id != ?",
        (u["organizacao_id"], email, secretaria_id),
    ):
        return jsonify({"erro": "Já existe um usuário com este e-mail nesta clínica."}), 409
    if email != sec["email"].lower() and not _email_disponivel_globalmente(email, excluir_usuario_id=secretaria_id):
        return jsonify({"erro": MENSAGEM_EMAIL_EM_USO}), 409
    telefone = body.get("telefone", sec["telefone"] or "")
    execute("UPDATE usuarios SET nome = ?, email = ?, telefone = ? WHERE id = ?", (nome, email, telefone, secretaria_id))
    log_auditoria(u["organizacao_id"], u["id"], "editar", "secretaria", secretaria_id, nome)
    return jsonify({"ok": True})


@bp.put("/secretarias/<int:secretaria_id>/arquivar")
@login_required
@papel_required("gestor", "admin_master")
def arquivar_secretaria(secretaria_id):
    u = g.usuario
    sec = query_one(
        "SELECT * FROM usuarios WHERE id = ? AND organizacao_id = ? AND papel = 'secretaria'",
        (secretaria_id, u["organizacao_id"]),
    )
    if not sec:
        return jsonify({"erro": "Secretária não encontrada nesta clínica."}), 404
    novo_estado = 0 if sec["ativo"] else 1
    execute("UPDATE usuarios SET ativo = ? WHERE id = ?", (novo_estado, secretaria_id))
    log_auditoria(u["organizacao_id"], u["id"], "arquivar" if not novo_estado else "reativar",
                  "secretaria", secretaria_id, sec["nome"])
    return jsonify({"ativo": bool(novo_estado)})


# ---------------------------------------------------------------- Responsáveis (listagem para vincular)
#
# Usada pelo front-end pra sugerir/autocompletar responsáveis já cadastrados
# na clínica (insight do usuário, 02/09/2026: quando um responsável tem mais
# de um filho na mesma clínica, cadastrar o segundo filho digitando o e-mail
# de novo, à mão, arrisca um erro de digitação — o que criaria uma CONTA
# NOVA e duplicada em vez de vincular à conta já existente, e o segundo filho
# "sumiria" pro responsável, porque apareceria só sob esse login novo que
# ninguém tem a senha). Secretária também cadastra paciente e vincula
# responsável (ver criar_paciente/vincular_responsavel), por isso está aqui.

@bp.get("/responsaveis")
@login_required
@papel_required("gestor", "admin_master", "profissional", "secretaria")
def listar_responsaveis():
    rows = query(
        "SELECT id, nome, email, telefone FROM usuarios WHERE organizacao_id = ? AND papel = 'responsavel' ORDER BY nome",
        (g.usuario["organizacao_id"],),
    )
    return jsonify(rows)


# ---------------------------------------------------------------- Perfil (autoedição — qualquer papel)

LIMITE_FOTO_BYTES = 2 * 1024 * 1024  # 2MB — mesma política do logo da clínica


@bp.put("/perfil")
@login_required
def atualizar_perfil():
    """
    Autoedição do próprio cadastro — disponível pra qualquer papel (Doc 33,
    tela de Perfil). Propositalmente NÃO permite trocar o e-mail por aqui
    (é o identificador de login; trocar exigiria um fluxo de confirmação à
    parte, fora do escopo desta versão).
    """
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    atual = query_one("SELECT * FROM usuarios WHERE id = ?", (u["id"],))

    avatar_base64 = body.get("avatar_base64")
    if avatar_base64:
        tamanho = int(len(avatar_base64) * 3 / 4)
        if tamanho > LIMITE_FOTO_BYTES:
            return jsonify({"erro": f"Foto muito grande (limite de {LIMITE_FOTO_BYTES // (1024*1024)}MB)."}), 400
        ok, erro_assinatura = validar_arquivo_base64(avatar_base64, "imagem")
        if not ok:
            return jsonify({"erro": erro_assinatura}), 400
    else:
        avatar_base64 = atual["avatar_base64"]

    execute(
        "UPDATE usuarios SET nome = ?, telefone = ?, avatar_base64 = ?, avatar_nome = ? WHERE id = ?",
        (
            (body.get("nome") or atual["nome"]).strip(),
            body.get("telefone", atual["telefone"]),
            avatar_base64,
            body.get("avatar_nome", atual["avatar_nome"]),
            u["id"],
        ),
    )
    return jsonify({"ok": True})


@bp.put("/perfil/senha")
@login_required
@limitar("trocar-senha", max_tentativas=10, janela_segundos=300)
def trocar_propria_senha():
    """
    Autoedição de senha — disponível pra qualquer papel, incluindo
    admin_master (insight do usuário, 04/09/2026: faltava uma tela de
    "Perfil da Plataforma" onde o próprio administrador trocasse os dados de
    acesso). Diferente da recuperação via link (auth_bp.py/redefinir_senha,
    pensada pra quando a pessoa ESQUECEU a senha e não está logada): aqui
    ela já está logada e confirma a senha ATUAL antes de definir uma nova.

    Ao trocar, carimba `senha_alterada_em` — o mesmo mecanismo que já
    revoga qualquer token JWT emitido antes disso (ver login_required em
    auth.py), incluindo o desta própria sessão: o front encerra a sessão e
    manda pro login logo em seguida, de propósito.
    """
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    senha_atual = body.get("senha_atual", "")
    nova_senha = body.get("nova_senha", "")
    if not senha_atual or not nova_senha:
        return jsonify({"erro": "Informe a senha atual e a nova senha."}), 400
    if len(nova_senha) < 8:
        return jsonify({"erro": "A nova senha precisa ter pelo menos 8 caracteres."}), 400

    atual = query_one("SELECT * FROM usuarios WHERE id = ?", (u["id"],))
    if not verificar_senha(senha_atual, atual["senha_hash"], atual["senha_salt"]):
        return jsonify({"erro": "Senha atual incorreta."}), 401

    senha_hash, salt = hash_senha(nova_senha)
    execute(
        "UPDATE usuarios SET senha_hash = ?, senha_salt = ?, senha_alterada_em = ? WHERE id = ?",
        (senha_hash, salt, agora_sql(), u["id"]),
    )
    log_auditoria(u["organizacao_id"], u["id"], "trocar_senha", "usuario", u["id"], "própria senha")
    return jsonify({"ok": True})


@bp.put("/perfil/atuar-como-profissional")
@login_required
@papel_required("gestor")
def atualizar_atuar_como_profissional():
    """
    Insight do usuário: o gestor pode, opcionalmente, também atuar como
    profissional da própria clínica, com a MESMA conta (mesmo login/senha) —
    sem precisar de um segundo cadastro. Fica em Configurações > Minha Conta.

    Ativar exige preencher os mesmos dados pedidos no cadastro de um
    profissional comum (especialidade, registro profissional, cor da
    agenda) — as colunas já existem em `usuarios` (reaproveitadas do
    cadastro de profissional), não é criada nenhuma coluna nova pra isso.

    Desativar NÃO apaga esses dados (ficam guardados, caso ele reative
    depois) nem desfaz vínculos/consultas já criados com ele como
    profissional — só ele deixa de poder ser selecionado como profissional
    em novas atribuições (ver _e_profissional_ativo).
    """
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    ativar = bool(body.get("atua_como_profissional"))

    if ativar:
        especialidade = (body.get("especialidade") or "").strip()
        if not especialidade:
            return jsonify({"erro": "Informe a especialidade para atuar como profissional."}), 400
        atual = query_one("SELECT cor_agenda FROM usuarios WHERE id = ?", (u["id"],))
        cor_agenda = _cor_segura(body.get("cor_agenda"), atual["cor_agenda"] or PALETA_CORES_AGENDA[0])
        execute(
            """UPDATE usuarios SET atua_como_profissional = 1, especialidade = ?, tipo_registro = ?,
               numero_registro = ?, cor_agenda = ? WHERE id = ?""",
            (especialidade, (body.get("tipo_registro") or "").strip(),
             (body.get("numero_registro") or "").strip(), cor_agenda, u["id"]),
        )
        log_auditoria(u["organizacao_id"], u["id"], "ativar", "atua_como_profissional", u["id"], u["nome"])
    else:
        execute("UPDATE usuarios SET atua_como_profissional = 0 WHERE id = ?", (u["id"],))
        log_auditoria(u["organizacao_id"], u["id"], "desativar", "atua_como_profissional", u["id"], u["nome"])
    return jsonify({"ok": True})


@bp.put("/pacientes/<int:paciente_id>/foto")
@login_required
def atualizar_foto_paciente(paciente_id):
    """Upload da foto real da criança — acessível a quem já tem acesso a essa jornada."""
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Sem acesso a este paciente."}), 403
    body = request.get_json(force=True, silent=True) or {}
    foto_base64 = body.get("foto_base64")
    if not foto_base64:
        return jsonify({"erro": "Envie uma foto."}), 400
    tamanho = int(len(foto_base64) * 3 / 4)
    if tamanho > LIMITE_FOTO_BYTES:
        return jsonify({"erro": f"Foto muito grande (limite de {LIMITE_FOTO_BYTES // (1024*1024)}MB)."}), 400
    ok, erro_assinatura = validar_arquivo_base64(foto_base64, "imagem")
    if not ok:
        return jsonify({"erro": erro_assinatura}), 400
    execute(
        "UPDATE pacientes SET foto_base64 = ?, foto_nome = ? WHERE id = ?",
        (foto_base64, body.get("foto_nome", ""), paciente_id),
    )
    return jsonify({"ok": True})


@bp.put("/pacientes/<int:paciente_id>/mascote")
@login_required
def atualizar_mascote_paciente(paciente_id):
    """Troca o mascote (emoji) da criança — provisório (insight do usuário,
    31/08/2026): até a Gamificação ganhar mascotes de verdade, deixamos o
    responsável (ou qualquer um que já enxergue a jornada, mesma regra da
    foto acima) escolher entre um conjunto fixo de emojis."""
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Sem acesso a este paciente."}), 403
    body = request.get_json(force=True, silent=True) or {}
    mascote = body.get("avatar_mascote")
    if mascote not in MASCOTES_VALIDOS:
        return jsonify({"erro": "Escolha um dos mascotes disponíveis."}), 400
    execute("UPDATE pacientes SET avatar_mascote = ? WHERE id = ?", (mascote, paciente_id))
    return jsonify({"ok": True, "avatar_mascote": mascote})


# ---------------------------------------------------------------- Organização (clínica)

@bp.get("/organizacao")
@login_required
def obter_organizacao():
    org = query_one("SELECT * FROM organizacoes WHERE id = ?", (g.usuario["organizacao_id"],))
    if not org:
        return jsonify({"erro": "Organização não encontrada."}), 404
    org["especialidades"] = json.loads(org.get("especialidades_json") or "[]")
    return jsonify(org)


@bp.put("/organizacao")
@login_required
@papel_required("gestor", "admin_master")
def atualizar_organizacao():
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    org_atual = query_one("SELECT * FROM organizacoes WHERE id = ?", (u["organizacao_id"],))
    especialidades = body.get("especialidades")

    logo_base64 = body.get("logo_base64")
    if logo_base64:
        tamanho_estimado = int(len(logo_base64) * 3 / 4)
        if tamanho_estimado > 2 * 1024 * 1024:
            return jsonify({"erro": "Imagem do logo muito grande (limite de 2MB)."}), 400
        ok, erro_assinatura = validar_arquivo_base64(logo_base64, "imagem")
        if not ok:
            return jsonify({"erro": erro_assinatura}), 400
    else:
        logo_base64 = org_atual["logo_base64"]

    execute(
        """UPDATE organizacoes SET nome = ?, cor_primaria = ?, cor_secundaria = ?, logo_emoji = ?,
           logo_base64 = ?, logo_nome = ?, nome_ia = ?, nome_moeda_gamificacao = ?,
           nome_medalha_generico = ?, especialidades_json = ?,
           cnpj = ?, telefone = ?, endereco_cep = ?, endereco_logradouro = ?, endereco_numero = ?,
           endereco_bairro = ?, endereco_cidade = ?, endereco_uf = ? WHERE id = ?""",
        (body.get("nome", org_atual["nome"]),
         _cor_segura(body.get("cor_primaria", org_atual["cor_primaria"]), org_atual["cor_primaria"]),
         _cor_segura(body.get("cor_secundaria", org_atual["cor_secundaria"]), org_atual["cor_secundaria"]),
         body.get("logo_emoji", org_atual["logo_emoji"]),
         logo_base64, body.get("logo_nome", org_atual["logo_nome"]),
         body.get("nome_ia", org_atual["nome_ia"]) or "Lumi",
         body.get("nome_moeda_gamificacao", org_atual["nome_moeda_gamificacao"]) or "XP",
         body.get("nome_medalha_generico", org_atual["nome_medalha_generico"]) or "Medalha",
         json.dumps(especialidades, ensure_ascii=False) if especialidades is not None else org_atual["especialidades_json"],
         body.get("cnpj", org_atual["cnpj"]), body.get("telefone", org_atual["telefone"]),
         body.get("endereco_cep", org_atual["endereco_cep"]), body.get("endereco_logradouro", org_atual["endereco_logradouro"]),
         body.get("endereco_numero", org_atual["endereco_numero"]), body.get("endereco_bairro", org_atual["endereco_bairro"]),
         body.get("endereco_cidade", org_atual["endereco_cidade"]), body.get("endereco_uf", org_atual["endereco_uf"]),
         u["organizacao_id"]),
    )
    log_auditoria(u["organizacao_id"], u["id"], "atualizar", "organizacao", u["organizacao_id"], "Identidade visual e personalização")
    return jsonify({"ok": True})


# ---------------------------------------------------------------- Feature Flags, camada Usuário

@bp.put("/responsaveis/<int:usuario_id>/financeiro-override")
@login_required
@papel_required("gestor")
def atualizar_override_financeiro(usuario_id):
    """
    Permite ao gestor esconder o Financeiro para um responsável específico,
    mesmo que a clínica o tenha habilitado (Doc 22A, camada 'Usuário').
    Envie {"habilitado": true|false} para forçar, ou {"habilitado": null} para
    voltar a herdar o comportamento padrão da clínica.
    """
    u = g.usuario
    resp = query_one("SELECT * FROM usuarios WHERE id = ? AND organizacao_id = ? AND papel = 'responsavel'",
                      (usuario_id, u["organizacao_id"]))
    if not resp:
        return jsonify({"erro": "Responsável não encontrado nesta clínica."}), 404
    body = request.get_json(force=True, silent=True) or {}
    valor = body.get("habilitado", None)
    valor_sql = None if valor is None else (1 if valor else 0)
    execute("UPDATE usuarios SET financeiro_habilitado_override = ? WHERE id = ?", (valor_sql, usuario_id))
    log_auditoria(u["organizacao_id"], u["id"], "override_financeiro", "usuario", usuario_id, str(valor))
    return jsonify({"ok": True})


# ---------------------------------------------------------------- Disponibilidade de agenda

DIAS_SEMANA_NOMES = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]


def _pode_gerenciar_disponibilidade(usuario_id_alvo):
    """Gestor pode editar a disponibilidade de qualquer profissional da clínica;
    o próprio profissional pode editar a própria."""
    u = g.usuario
    if u["papel"] == "gestor":
        # Cobre tanto um profissional de verdade quanto o próprio gestor,
        # quando ele mesmo é o alvo e está com "atuar como profissional" ligado.
        return _e_profissional_ativo(usuario_id_alvo, u["organizacao_id"])
    if u["papel"] == "profissional":
        return u["id"] == usuario_id_alvo
    return False


@bp.get("/profissionais/<int:usuario_id>/disponibilidade")
@login_required
def obter_disponibilidade(usuario_id):
    """Visualização é aberta pra qualquer papel logado da clínica (gestor,
    profissionais, e a família também pode ver os dias livres) — só a
    edição é restrita."""
    u = g.usuario
    prof = query_one(
        """SELECT organizacao_id FROM usuarios WHERE id = ?
           AND (papel = 'profissional' OR (papel = 'gestor' AND atua_como_profissional = 1))""",
        (usuario_id,),
    )
    if not prof:
        return jsonify({"erro": "Profissional não encontrado."}), 404
    # Correção de auditoria: "aberta pra qualquer papel logado da clínica"
    # significa a MESMA clínica do profissional, não qualquer usuário da
    # plataforma — faltava essa comparação, o que deixava a agenda semanal
    # de qualquer profissional visível a qualquer usuário logado de qualquer
    # clínica.
    if u["papel"] != "admin_master" and prof["organizacao_id"] != u["organizacao_id"]:
        return jsonify({"erro": "Profissional não encontrado."}), 404
    linhas = query("SELECT * FROM disponibilidade_profissional WHERE usuario_id = ?", (usuario_id,))
    por_dia = {l["dia_semana"]: l for l in linhas}
    resultado = []
    for dia in range(7):
        l = por_dia.get(dia)
        resultado.append({
            "dia_semana": dia,
            "dia_nome": DIAS_SEMANA_NOMES[dia],
            "ausente": bool(l["ausente"]) if l else (dia in (0, 6)),  # sem registro ainda: assume fim de semana ausente por padrão
            "hora_inicio": l["hora_inicio"] if l else "08:00",
            "hora_fim": l["hora_fim"] if l else "18:00",
        })
    return jsonify(resultado)


@bp.put("/profissionais/<int:usuario_id>/disponibilidade")
@login_required
@papel_required("gestor", "profissional")
def atualizar_disponibilidade(usuario_id):
    if not _pode_gerenciar_disponibilidade(usuario_id):
        return jsonify({"erro": "Você não tem permissão para editar esta disponibilidade."}), 403
    body = request.get_json(force=True, silent=True) or {}
    dias = body.get("dias", [])
    for d in dias:
        dia_semana = d.get("dia_semana")
        if dia_semana is None or not (0 <= int(dia_semana) <= 6):
            continue
        execute(
            """INSERT INTO disponibilidade_profissional (usuario_id, dia_semana, ausente, hora_inicio, hora_fim)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(usuario_id, dia_semana) DO UPDATE SET ausente = excluded.ausente,
                   hora_inicio = excluded.hora_inicio, hora_fim = excluded.hora_fim""",
            (usuario_id, dia_semana, 1 if d.get("ausente") else 0, d.get("hora_inicio", "08:00"), d.get("hora_fim", "18:00")),
        )
    log_auditoria(g.usuario["organizacao_id"], g.usuario["id"], "editar", "disponibilidade", usuario_id, "")
    return jsonify({"ok": True})
