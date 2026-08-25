"""
Domínio 1 — Pessoas (Documento 09 / Módulo 01)

Fonte oficial de identidade de: Clínicas, Profissionais, Pacientes, Responsáveis.
Não é responsável por: Agenda, Financeiro, Exercícios, Gamificação (Doc 10).
"""
import json

from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute, log_auditoria, log_evento, agora_sql
from auth import login_required, papel_required, hash_senha, paciente_acessivel, paciente_editavel
from tokens_service import gerar_token as gerar_token_convite, link_para as link_para_token, gerar_senha_bloqueada
from validacao_arquivo import validar_arquivo_base64

bp = Blueprint("pessoas", __name__, url_prefix="/api/pessoas")


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
        "SELECT nome, limite_pacientes, limite_profissionais FROM planos WHERE codigo = ?",
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
    else:
        rows = []
    return jsonify(rows)


@bp.get("/pacientes/<int:paciente_id>")
@login_required
def obter_paciente(paciente_id):
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Você não tem acesso a este paciente."}), 403
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
@papel_required("gestor", "admin_master")
def vincular_profissional(paciente_id):
    """Adiciona mais um profissional à equipe que atende o paciente (Gestor decide quem entra na equipe)."""
    if not paciente_editavel(paciente_id):
        return jsonify({"erro": "Você não tem acesso a este paciente."}), 403
    body = request.get_json(force=True, silent=True) or {}
    profissional_id = body.get("profissional_id")
    prof = query_one(
        "SELECT * FROM usuarios WHERE id = ? AND organizacao_id = ? AND papel = 'profissional'",
        (profissional_id, g.usuario["organizacao_id"]),
    )
    if not prof:
        return jsonify({"erro": "Profissional não encontrado nesta clínica."}), 404
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


@bp.post("/pacientes")
@login_required
@papel_required("gestor", "admin_master", "profissional")
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

    paciente_id = execute(
        """INSERT INTO pacientes (organizacao_id, nome, data_nascimento, avatar_mascote, genero)
           VALUES (?, ?, ?, ?, ?)""",
        (u["organizacao_id"], nome, nascimento, body.get("avatar_mascote", "🐻"), body.get("genero")),
    )
    execute("INSERT INTO gamificacao_paciente (paciente_id) VALUES (?)", (paciente_id,))

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
            if not query_one(
                "SELECT 1 FROM usuarios WHERE id = ? AND organizacao_id = ? AND papel = 'profissional'",
                (prof_id, u["organizacao_id"]),
            ):
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
@papel_required("gestor", "admin_master", "profissional")
def vincular_responsavel(paciente_id):
    if not paciente_editavel(paciente_id):
        return jsonify({"erro": "Você não tem permissão para editar este paciente."}), 403
    body = request.get_json(force=True, silent=True) or {}
    nome = body.get("nome")
    email = (body.get("email") or "").strip().lower()
    telefone = (body.get("telefone") or "").strip()
    parentesco = body.get("parentesco", "Responsável")
    if not nome or not email:
        return jsonify({"erro": "Nome e e-mail do responsável são obrigatórios."}), 400

    # Correção de auditoria: a busca precisa ser restrita à própria clínica.
    # O e-mail só é único POR clínica (UNIQUE(organizacao_id, email) no
    # schema) — sem o filtro de organizacao_id aqui, uma busca sem escopo
    # podia encontrar a conta de um usuário de OUTRA clínica com o mesmo
    # e-mail e vinculá-la como responsável a este paciente, vazando os dados
    # dele pra uma família que não tem nada a ver com essa clínica.
    existente = query_one(
        "SELECT * FROM usuarios WHERE organizacao_id = ? AND lower(email) = ?",
        (g.usuario["organizacao_id"], email),
    )
    link_convite = None
    if existente:
        usuario_id = existente["id"]
        if telefone:
            execute("UPDATE usuarios SET telefone = ? WHERE id = ?", (telefone, usuario_id))
    else:
        # Convite de ativação (Doc 31A/35/36): a conta nasce com senha bloqueada
        # (aleatória, impossível de adivinhar) até a pessoa abrir o link e criar a própria senha.
        senha_hash, salt = hash_senha(gerar_senha_bloqueada())
        usuario_id = execute(
            """INSERT INTO usuarios (organizacao_id, nome, email, telefone, senha_hash, senha_salt, papel)
               VALUES (?, ?, ?, ?, ?, ?, 'responsavel')""",
            (g.usuario["organizacao_id"], nome, email, telefone, senha_hash, salt),
        )
        token = gerar_token_convite(usuario_id, tipo="convite")
        link_convite = link_para_token(token)
    execute(
        """INSERT INTO responsaveis_pacientes (usuario_id, paciente_id, parentesco) VALUES (?, ?, ?)
           ON CONFLICT (usuario_id, paciente_id) DO NOTHING""",
        (usuario_id, paciente_id, parentesco),
    )
    log_evento(g.usuario["organizacao_id"], "responsavel_vinculado", "paciente", paciente_id, paciente_id)
    resposta = {"usuario_id": usuario_id}
    if link_convite:
        resposta["link_convite"] = link_convite
    return jsonify(resposta), 201


# ---------------------------------------------------------------- Profissionais

PALETA_CORES_AGENDA = ["#5B4FE9", "#E8385A", "#10B981", "#F59E0B", "#8B5CF6", "#0EA5E9", "#EC4899", "#84CC16", "#F97316", "#14B8A6"]


@bp.get("/profissionais")
@login_required
def listar_profissionais():
    incluir_inativos = request.args.get("incluir_inativos") == "1"
    sql = """SELECT id, nome, email, telefone, especialidade, avatar_emoji, avatar_base64, ativo,
                    cor_agenda, agenda_permissao_total, tipo_registro, numero_registro,
                    (SELECT COUNT(*) FROM profissionais_pacientes pp WHERE pp.usuario_id = usuarios.id) AS total_pacientes
             FROM usuarios WHERE organizacao_id = ? AND papel = 'profissional'"""
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
    cor_agenda = body.get("cor_agenda") or PALETA_CORES_AGENDA[total_atual % len(PALETA_CORES_AGENDA)]
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
         body.get("cor_agenda", prof["cor_agenda"]), 1 if body.get("agenda_permissao_total") else 0,
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


# ---------------------------------------------------------------- Responsáveis (listagem para vincular)

@bp.get("/responsaveis")
@login_required
@papel_required("gestor", "admin_master", "profissional")
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
        (body.get("nome", org_atual["nome"]), body.get("cor_primaria", org_atual["cor_primaria"]),
         body.get("cor_secundaria", org_atual["cor_secundaria"]), body.get("logo_emoji", org_atual["logo_emoji"]),
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
        alvo = query_one("SELECT 1 FROM usuarios WHERE id = ? AND organizacao_id = ? AND papel = 'profissional'",
                          (usuario_id_alvo, u["organizacao_id"]))
        return bool(alvo)
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
    prof = query_one("SELECT organizacao_id FROM usuarios WHERE id = ? AND papel = 'profissional'", (usuario_id,))
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
