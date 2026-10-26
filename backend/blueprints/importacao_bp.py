"""
Importação em lote de pacientes (Doc 22A — módulo opcional "importacao_pacientes",
Pro/Enterprise): pedido do usuário (02/09/2026) para clínicas que já têm uma
base de pacientes cadastrada em outro sistema/software de gestão e não
querem recadastrar um por um.

Desenho escolhido (explicado ao usuário antes de implementar): a gente não
integra com o sistema de origem (desconhecido, varia por clínica) — o
gestor exporta de lá pra uma planilha e importa aqui. O front-end lê o CSV
no navegador (sem enviar o arquivo bruto pro servidor) e manda cada linha
já como JSON; este blueprint faz a validação de verdade (nunca confia só
na validação do front) e, na confirmação, cria os pacientes.

Cada linha passa pelas MESMAS regras do cadastro manual — reaproveitando
`criar_paciente_core`/`vincular_responsavel_core` de pessoas_bp.py — porque
a base legada quase sempre repete o e-mail do responsável entre irmãos, e
essa é exatamente a situação que a auditoria de 02/09/2026 tratou (ver
test_segundo_filho_mesmo_responsavel.py): tem que reaproveitar a conta já
existente NESTA clínica, nunca duplicar.
"""
import re

from flask import Blueprint, request, jsonify, g, current_app

from ausencias_service import hoje_brasilia
from db import agora_sql, em_lote, execute, log_auditoria, query, query_one
from auth import login_required, papel_required
from importacao_service import (
    chave_importacao, colunas_diario_importacao_existem, converter_data, normalizar_nome,
)
from modulos_service import modulo_ativo_para_clinica
from blueprints.pessoas_bp import (
    MASCOTES_VALIDOS, criar_paciente_core, vincular_responsavel_core,
)

bp = Blueprint("importacao", __name__, url_prefix="/api/importacao")

_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _email_formato_valido(email):
    """Validação de formato de e-mail sem regex.

    Correção de segurança (04/09/2026 — CodeQL apontou "polynomial regular
    expression used on uncontrolled data" nos dois usos da regex antiga,
    `^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$": o grupo do meio ([^@\\s]+, entre o "@"
    e o ".") podia incluir pontos, então um e-mail malicioso com muitos
    pontos no domínio (linha de uma planilha de importação — dado que
    literalmente não confiamos, é o cliente que sobe o CSV) fazia o motor de
    regex tentar cada ponto como candidato pro "." literal antes de falhar,
    custo O(n²) numa linha só. Checagem por string simples abaixo é O(n)
    garantido, sem esse risco, e aceita os mesmos formatos de antes."""
    if not email or any(c.isspace() for c in email):
        return False
    if email.count("@") != 1:
        return False
    local, _, dominio = email.partition("@")
    if not local or not dominio:
        return False
    if "." not in dominio or dominio.startswith(".") or dominio.endswith("."):
        return False
    return True

MAX_LINHAS_POR_LOTE = 500  # limite técnico de segurança, não relacionado ao limite do plano


def _organizacao_do_usuario():
    return query_one("SELECT * FROM organizacoes WHERE id = ?", (g.usuario["organizacao_id"],))


def _modulo_liberado_ou_403():
    org = _organizacao_do_usuario()
    if not org or not modulo_ativo_para_clinica(g.usuario["organizacao_id"], org["plano"], "importacao_pacientes"):
        return jsonify({
            "erro": "A importação em lote não está incluída no seu plano atual. "
                    "Fale com o time comercial para fazer upgrade para o plano Pro ou Enterprise.",
        }), 403
    return None


# Ficha Clínica na planilha de pacientes (26/10/2026): coluna da planilha →
# (coluna de fichas_clinicas, limite de caracteres).
CAMPOS_FICHA = {
    "diagnostico": ("diagnostico", 2000),
    "alergias": ("alergias", 2000),
    "medicamentos_em_uso": ("medicamentos_em_uso", 2000),
    "profissionais_externos": ("profissionais_externos", 2000),
    "observacoes_clinicas": ("observacoes", 5000),
}


def _chave_paciente(nome, nascimento):
    return f"{normalizar_nome(nome)}|{str(nascimento or '').strip()}"


def _vazio(valor):
    return valor is None or not str(valor).strip()


class _ContextoLote:
    """O que a validação precisa saber do banco e das linhas anteriores do
    mesmo lote, carregado uma vez por lote (nunca uma consulta por linha).

    - `pacientes`: {chave nome|nascimento: [pacientes da clínica, ativos e arquivados]}
    - `vinculados`: {paciente_id: e-mails (minúsculos) dos responsáveis do paciente}
    - `fichas`: {paciente_id: ficha atual}
    - `do_lote`: {chave: dados de um paciente novo de uma linha anterior do lote}
    """

    def __init__(self, organizacao_id):
        self.pacientes = {}
        for p in query("SELECT id, nome, data_nascimento, ativo FROM pacientes WHERE organizacao_id = ?",
                       (organizacao_id,)):
            self.pacientes.setdefault(_chave_paciente(p["nome"], p["data_nascimento"]), []).append(p)
        self.vinculados = {}
        for v in query(
            """SELECT rp.paciente_id, u.email FROM responsaveis_pacientes rp
               JOIN usuarios u ON u.id = rp.usuario_id
               JOIN pacientes p ON p.id = rp.paciente_id WHERE p.organizacao_id = ?""",
            (organizacao_id,),
        ):
            self.vinculados.setdefault(v["paciente_id"], set()).add((v["email"] or "").lower())
        self.fichas = {
            f["paciente_id"]: f for f in query(
                """SELECT f.* FROM fichas_clinicas f JOIN pacientes p ON p.id = f.paciente_id
                   WHERE p.organizacao_id = ?""",
                (organizacao_id,),
            )
        }
        self.do_lote = {}


def _validar_linha(linha, indice, contas_conhecidas, contexto):
    """
    Valida uma linha do lote. `contas_conhecidas` é um dict {email_lower: nome_da_conta}
    acumulado ao longo do lote inteiro (já semeado com as contas que já existem
    no banco desta clínica) — permite avisar quando duas linhas do MESMO lote
    usam o mesmo e-mail com nomes diferentes (provável erro de digitação na
    planilha de origem), sem bloquear a importação por causa disso.

    `contexto` (_ContextoLote) reconhece o paciente que já existe (26/10/2026):
    mesmo nome + nascimento, sem acento/maiúsculas/espaços extras, entre os
    pacientes da clínica ativos ou arquivados — e as linhas anteriores do lote.

    Retorna um dict com o resultado da linha (nunca lança exceção — uma linha
    ruim não pode derrubar o lote inteiro).
    """
    erros = []
    avisos = []
    nome = (linha.get("nome") or "").strip()
    nascimento = (linha.get("data_nascimento") or "").strip()
    resp_nome = (linha.get("responsavel_nome") or "").strip()
    resp_email = (linha.get("responsavel_email") or "").strip().lower()
    resp_telefone = (linha.get("responsavel_telefone") or "").strip()
    genero = (linha.get("genero") or "").strip() or None
    avatar_mascote = (linha.get("avatar_mascote") or "").strip() or None
    parentesco = (linha.get("parentesco") or "").strip() or "Responsável"

    if not nome:
        erros.append("Nome do paciente é obrigatório.")
    if not nascimento:
        erros.append("Data de nascimento é obrigatória.")
    elif not _RE_DATA.match(nascimento):
        erros.append("Data de nascimento precisa estar no formato AAAA-MM-DD (ex: 2019-05-20).")
    if avatar_mascote and avatar_mascote not in MASCOTES_VALIDOS:
        erros.append(f"Mascote '{avatar_mascote}' não é válido — deixe em branco para usar o padrão.")

    ficha = {}
    for coluna, (destino, limite) in CAMPOS_FICHA.items():
        valor = str(linha.get(coluna) or "").strip()
        if not valor:
            continue
        if len(valor) > limite:
            erros.append(f"A coluna '{coluna}' passa de {limite:,} caracteres.".replace(",", "."))
        ficha[destino] = valor

    # --- Paciente novo ou que já existe
    paciente_status, paciente_id, arquivado, ficha_atual, vinculados = "novo", None, False, {}, set()
    chave = _chave_paciente(nome, nascimento)
    if nome and nascimento and _RE_DATA.match(nascimento):
        do_banco = contexto.pacientes.get(chave, [])
        if len(do_banco) > 1:
            erros.append("Há mais de um paciente com esse nome e nascimento nesta clínica — "
                         "complete a ficha dele pela tela do paciente.")
        elif do_banco:
            paciente_status, paciente_id = "existente", do_banco[0]["id"]
            arquivado = not do_banco[0]["ativo"]
            ficha_atual = contexto.fichas.get(paciente_id) or {}
            vinculados = contexto.vinculados.get(paciente_id, set())
            avisos.append("Paciente já cadastrado: não será criado de novo; a ficha só é completada.")
            if arquivado:
                avisos.append("Paciente arquivado: continua arquivado.")
        elif chave in contexto.do_lote:
            paciente_status = "existente"
            anterior = contexto.do_lote[chave]
            ficha_atual, vinculados = anterior["ficha"], anterior["vinculados"]
            avisos.append(f"Mesmo paciente da linha {anterior['linha'] + 1}: os dados desta linha completam a ficha.")

    ficha_mantidos = sum(1 for destino in ficha if not _vazio(ficha_atual.get(destino)))
    if ficha_mantidos:
        avisos.append(f"{ficha_mantidos} campo(s) da ficha já estavam preenchidos e foram mantidos.")

    # --- Responsável
    responsavel_status = None
    if paciente_status == "novo":
        responsavel_acao = "vincular"
        if not resp_nome:
            erros.append("Nome do responsável é obrigatório.")
        if not resp_email:
            erros.append("E-mail do responsável é obrigatório.")
        elif not _email_formato_valido(resp_email):
            erros.append("E-mail do responsável parece inválido.")
        if resp_email and _email_formato_valido(resp_email):
            conhecida = contas_conhecidas.get(resp_email)
            if conhecida is None:
                responsavel_status = "novo"
            else:
                responsavel_status = "existente"
                if resp_nome and conhecida.lower() != resp_nome.lower():
                    avisos.append(f"Este e-mail já é de uma conta chamada '{conhecida}' nesta clínica — "
                                  f"o paciente será vinculado a ela (o nome '{resp_nome}' informado aqui não será usado).")
            # Registra pra próximas linhas do lote enxergarem essa conta como já conhecida.
            contas_conhecidas.setdefault(resp_email, conhecida or resp_nome)
    elif not resp_email:
        responsavel_acao = "sem_responsavel"
    elif resp_email in vinculados:
        responsavel_acao = "ja_vinculado"
    else:
        # Segurança: um e-mail digitado errado daria acesso à criança a uma
        # conta errada — paciente que já existe nunca ganha responsável novo aqui.
        responsavel_acao = "nao_vinculado"
        avisos.append("Responsável diferente do cadastrado — não vinculado; "
                      "se for o caso, vincule pela ficha do paciente.")

    valido = not erros
    if valido:
        if paciente_status == "novo":
            contexto.do_lote[chave] = {"linha": indice, "ficha": dict(ficha), "vinculados": {resp_email}}
        elif chave in contexto.do_lote and paciente_id is None:
            for destino, valor in ficha.items():
                contexto.do_lote[chave]["ficha"].setdefault(destino, valor)

    return {
        "linha": indice,
        "nome": nome,
        "data_nascimento": nascimento,
        "genero": genero,
        "avatar_mascote": avatar_mascote,
        "responsavel_nome": resp_nome,
        "responsavel_email": resp_email,
        "responsavel_telefone": resp_telefone,
        "parentesco": parentesco,
        "valido": valido,
        "erros": erros,
        "avisos": avisos,
        "aviso": " ".join(avisos) or None,
        "responsavel_status": responsavel_status,
        "responsavel_acao": responsavel_acao,
        "paciente_status": paciente_status,
        "paciente_id": paciente_id,
        "paciente_arquivado": arquivado,
        "ficha": ficha,
        "ficha_campos": len(ficha),
        "ficha_mantidos": ficha_mantidos,
        "_chave": chave,
    }


def _contas_existentes_do_lote(organizacao_id, linhas):
    """Pré-carrega, num dict {email: nome}, as contas de responsável que já
    existem NESTA clínica para os e-mails presentes no lote — evita uma
    consulta por linha e alimenta `_validar_linha` com o estado real do banco."""
    emails = {(l.get("responsavel_email") or "").strip().lower() for l in linhas}
    emails.discard("")
    if not emails:
        return {}
    marcadores = ",".join("?" for _ in emails)
    linhas_banco = query(
        f"SELECT nome, email FROM usuarios WHERE organizacao_id = ? AND lower(email) IN ({marcadores})",
        (organizacao_id, *emails),
    )
    return {r["email"].lower(): r["nome"] for r in linhas_banco}


def _validar_lote(linhas):
    organizacao_id = g.usuario["organizacao_id"]
    contas_conhecidas = _contas_existentes_do_lote(organizacao_id, linhas)
    contexto = _ContextoLote(organizacao_id)
    return [_validar_linha(l if isinstance(l, dict) else {}, i, contas_conhecidas, contexto)
            for i, l in enumerate(linhas)]


def _sem_internos(r):
    return {k: v for k, v in r.items() if not k.startswith("_") and k != "ficha"}


def _completar_ficha(paciente_id, ficha, usuario_id):
    """Grava os campos da ficha que estão VAZIOS no PandaUp (nunca sobrescreve
    o que a clínica já escreveu). Devolve quantos campos entraram."""
    if not ficha:
        return 0
    atual = query_one("SELECT * FROM fichas_clinicas WHERE paciente_id = ?", (paciente_id,))
    if not atual:
        colunas = list(ficha)
        execute(
            f"INSERT INTO fichas_clinicas (paciente_id, {', '.join(colunas)}, atualizado_por) "
            f"VALUES (?, {', '.join('?' for _ in colunas)}, ?)",
            (paciente_id, *[ficha[c] for c in colunas], usuario_id),
        )
        return len(colunas)
    novos = {c: v for c, v in ficha.items() if _vazio(atual.get(c))}
    if not novos:
        return 0
    execute(
        f"UPDATE fichas_clinicas SET {', '.join(f'{c} = ?' for c in novos)}, atualizado_por = ?, atualizado_em = ? "
        "WHERE paciente_id = ?",
        (*novos.values(), usuario_id, agora_sql(), paciente_id),
    )
    return len(novos)


@bp.post("/pacientes/preview")
@login_required
@papel_required("gestor", "admin_master")
def preview():
    bloqueio = _modulo_liberado_ou_403()
    if bloqueio:
        return bloqueio
    body = request.get_json(force=True, silent=True) or {}
    linhas = body.get("linhas")
    if not isinstance(linhas, list) or not linhas:
        return jsonify({"erro": "Envie ao menos uma linha para pré-visualizar."}), 400
    if len(linhas) > MAX_LINHAS_POR_LOTE:
        return jsonify({"erro": f"O lote pode ter no máximo {MAX_LINHAS_POR_LOTE} linhas por vez."}), 400

    resultados = _validar_lote(linhas)
    validas = [r for r in resultados if r["valido"]]

    erro_limite = None  # pacientes ilimitados desde 25/09/2026 (planos configuráveis); campo mantido pela tela

    return jsonify({
        "linhas": [_sem_internos(r) for r in resultados],
        "total": len(resultados),
        "validas": len(validas),
        "invalidas": len(resultados) - len(validas),
        "novos": len([r for r in validas if r["paciente_status"] == "novo"]),
        "existentes": len([r for r in validas if r["paciente_status"] == "existente"]),
        "erro_limite_plano": erro_limite,
    })


@bp.post("/pacientes/confirmar")
@login_required
@papel_required("gestor", "admin_master")
def confirmar():
    bloqueio = _modulo_liberado_ou_403()
    if bloqueio:
        return bloqueio
    body = request.get_json(force=True, silent=True) or {}
    linhas = body.get("linhas")
    if not isinstance(linhas, list) or not linhas:
        return jsonify({"erro": "Envie ao menos uma linha para importar."}), 400
    if len(linhas) > MAX_LINHAS_POR_LOTE:
        return jsonify({"erro": f"O lote pode ter no máximo {MAX_LINHAS_POR_LOTE} linhas por vez."}), 400

    # Revalida do zero no servidor — nunca confia que o que o front mandou
    # pro "confirmar" é o mesmo que passou pelo "preview" (o front podia ter
    # sido adulterado, ou o gestor pode ter editado o CSV entre as duas
    # chamadas). Só as linhas que continuam válidas AGORA são importadas.
    resultados = _validar_lote(linhas)
    validas = [r for r in resultados if r["valido"]]

    organizacao_id = g.usuario["organizacao_id"]
    criados = []
    atualizados = []
    ignorados = [{"linha": r["linha"], "nome": r["nome"], "erros": r["erros"]} for r in resultados if not r["valido"]]
    criados_no_lote = {}  # chave nome|nascimento → paciente_id criado por uma linha anterior

    for r in validas:
        if r["paciente_status"] == "novo":
            paciente_id = criar_paciente_core(
                organizacao_id, r["nome"], r["data_nascimento"], r["avatar_mascote"], r["genero"],
            )
            criados_no_lote[r["_chave"]] = paciente_id
            resp = vincular_responsavel_core(
                organizacao_id, paciente_id, r["responsavel_nome"], r["responsavel_email"],
                r["responsavel_telefone"], r["parentesco"],
                enviar_whatsapp=False,  # lote pode ter dezenas de linhas — não dispara N mensagens de convite de uma vez
            )
            campos = _completar_ficha(paciente_id, r["ficha"], g.usuario["id"])
            criados.append({
                "linha": r["linha"], "paciente_id": paciente_id, "nome": r["nome"],
                "responsavel_novo": bool(resp.get("link_convite")), "paciente_status": "novo",
                "ficha_campos": campos,
            })
        else:
            paciente_id = r["paciente_id"] or criados_no_lote.get(r["_chave"])
            if not paciente_id:
                continue
            campos = _completar_ficha(paciente_id, r["ficha"], g.usuario["id"])
            atualizados.append({
                "linha": r["linha"], "paciente_id": paciente_id, "nome": r["nome"],
                "paciente_status": "existente", "ficha_campos": campos,
            })

    if criados or atualizados:
        log_auditoria(organizacao_id, g.usuario["id"], "importar", "pacientes", None,
                      f"{len(criados) + len(atualizados)} registros")

    return jsonify({
        "criados": criados, "atualizados": atualizados, "ignorados": ignorados,
        "total_criados": len(criados), "total_atualizados": len(atualizados),
    }), 201


# ============================================================================
# Histórico de evoluções → Diário (26/10/2026). Cada linha da 2ª planilha vira
# um registro do Diário marcado como importado (origem = 'importacao'), só
# para a equipe: nunca compartilhado com a família e sem notificação.
# ============================================================================
MAX_EVOLUCOES_POR_LOTE = 1000
LINHAS_POR_INSERT = 100  # linhas por INSERT no confirmar (menos idas ao banco)
LIMITE_EVOLUCAO = 10000
LIMITE_OBSERVACAO = 5000
ERRO_SEM_MIGRACAO = ("A importação de evoluções precisa de uma atualização do banco. "
                     "Fale com o suporte do PandaUp.")


class _ContextoEvolucoes:
    """Pacientes, profissionais e evoluções já importadas da clínica,
    carregados uma vez por lote."""

    def __init__(self, organizacao_id):
        self.pacientes = {}
        for p in query("SELECT id, nome, data_nascimento FROM pacientes WHERE organizacao_id = ?", (organizacao_id,)):
            self.pacientes.setdefault(_chave_paciente(p["nome"], p["data_nascimento"]), []).append(p)
        # Equipe que atende: profissional ou gestor, arquivados também; excluídos não.
        self.profissionais = {
            (u["email"] or "").lower(): u for u in query(
                """SELECT id, nome, email FROM usuarios WHERE organizacao_id = ?
                   AND papel IN ('profissional', 'gestor') AND excluido_em IS NULL""",
                (organizacao_id,),
            )
        }
        self.chaves = {
            d["importacao_chave"] for d in query(
                """SELECT d.importacao_chave FROM diarios_terapeuticos d JOIN pacientes p ON p.id = d.paciente_id
                   WHERE p.organizacao_id = ? AND d.importacao_chave IS NOT NULL""",
                (organizacao_id,),
            )
        }


def _validar_evolucao(linha, indice, contexto, hoje):
    erros, avisos = [], []
    nome = str(linha.get("paciente_nome") or "").strip()
    nascimento_txt = str(linha.get("paciente_nascimento") or "").strip()
    data_txt = str(linha.get("data_atendimento") or "").strip()
    prof_email = str(linha.get("profissional_email") or "").strip().lower()
    prof_nome = str(linha.get("profissional_nome") or "").strip()
    evolucao = str(linha.get("evolucao") or "").strip()
    observacao = str(linha.get("observacao") or "").strip()

    nascimento = converter_data(nascimento_txt)
    data_atendimento = converter_data(data_txt)
    if not nome:
        erros.append("Nome do paciente é obrigatório.")
    if not nascimento_txt:
        erros.append("Data de nascimento do paciente é obrigatória.")
    elif not nascimento:
        erros.append("Data de nascimento inválida (use AAAA-MM-DD ou DD/MM/AAAA).")
    if not data_txt:
        erros.append("Data do atendimento é obrigatória.")
    elif not data_atendimento:
        erros.append("Data do atendimento inválida (use AAAA-MM-DD ou DD/MM/AAAA).")
    elif data_atendimento > hoje:
        erros.append("Data do atendimento no futuro.")
    if not evolucao:
        erros.append("O texto da evolução é obrigatório.")
    elif len(evolucao) > LIMITE_EVOLUCAO:
        erros.append("A evolução passa de 10.000 caracteres.")
    if len(observacao) > LIMITE_OBSERVACAO:
        erros.append("A observação passa de 5.000 caracteres.")

    paciente_id = None
    if nome and nascimento:
        achados = contexto.pacientes.get(_chave_paciente(nome, nascimento), [])
        if not achados:
            erros.append("Paciente não encontrado nesta clínica (importe os pacientes antes das evoluções).")
        elif len(achados) > 1:
            erros.append("Há mais de um paciente com esse nome e nascimento nesta clínica.")
        else:
            paciente_id = achados[0]["id"]

    profissional = contexto.profissionais.get(prof_email) if prof_email else None
    texto = evolucao
    if profissional:
        rotulo = profissional["nome"]
    else:
        rotulo = "você (quem importa)"
        anterior = prof_nome or prof_email
        if anterior:
            texto = f"Profissional no sistema anterior: {anterior}.\n\n{evolucao}"
            avisos.append(f"Profissional '{anterior}' não está na Equipe: o registro fica no seu nome, "
                          "com o nome dele no texto.")
        else:
            avisos.append("Sem profissional na planilha: o registro fica no seu nome.")

    chave = None
    status = "erro" if erros else ("aviso" if avisos else "pronta")
    if not erros:
        chave = chave_importacao(paciente_id, data_atendimento, evolucao)
        if chave in contexto.chaves:
            status = "ja_importada"
        else:
            contexto.chaves.add(chave)  # linha idêntica mais abaixo no lote também é duplicata

    return {
        "linha": indice, "paciente_nome": nome, "data_atendimento": data_atendimento or data_txt,
        "status": status, "erros": erros, "avisos": avisos, "profissional": rotulo,
        "_paciente_id": paciente_id, "_profissional_id": profissional["id"] if profissional else None,
        "_texto": texto, "_observacao": observacao or None, "_chave": chave,
    }


def _lote_de_evolucoes():
    """Validações comuns do preview e do confirmar: (linhas, None) ou (None, resposta de erro)."""
    bloqueio = _modulo_liberado_ou_403()
    if bloqueio:
        return None, bloqueio
    if not colunas_diario_importacao_existem():
        return None, (jsonify({"erro": ERRO_SEM_MIGRACAO}), 503)
    body = request.get_json(force=True, silent=True) or {}
    linhas = body.get("linhas")
    if not isinstance(linhas, list) or not linhas:
        return None, (jsonify({"erro": "Envie ao menos uma linha."}), 400)
    if len(linhas) > MAX_EVOLUCOES_POR_LOTE:
        return None, (jsonify({"erro": f"Envie no máximo {MAX_EVOLUCOES_POR_LOTE} evoluções por vez."}), 400)
    contexto = _ContextoEvolucoes(g.usuario["organizacao_id"])
    hoje = hoje_brasilia().isoformat()
    return [_validar_evolucao(l if isinstance(l, dict) else {}, i, contexto, hoje)
            for i, l in enumerate(linhas)], None


@bp.post("/evolucoes/preview")
@login_required
@papel_required("gestor", "admin_master")
def preview_evolucoes():
    resultados, erro = _lote_de_evolucoes()
    if erro:
        return erro
    contar = lambda st: len([r for r in resultados if r["status"] == st])  # noqa: E731
    return jsonify({
        "linhas": [{k: v for k, v in r.items() if not k.startswith("_")} for r in resultados],
        "total": len(resultados), "prontas": contar("pronta"), "avisos": contar("aviso"),
        "erros": contar("erro"), "ja_importadas": contar("ja_importada"),
    })


@bp.post("/evolucoes/confirmar")
@login_required
@papel_required("gestor", "admin_master")
def confirmar_evolucoes():
    # Revalida do zero (nunca confia no preview), como na importação de pacientes.
    resultados, erro = _lote_de_evolucoes()
    if erro:
        return erro
    a_gravar = [r for r in resultados if r["status"] in ("pronta", "aviso")]
    # O Supabase fica longe do servidor: jornadas numa consulta só e os
    # registros em INSERTs de várias linhas (uma ida ao banco por linha
    # estourava o tempo do Passenger num lote de 1.000).
    jornadas = {}
    pacientes = sorted({r["_paciente_id"] for r in a_gravar})
    if pacientes:
        for j in query(
            f"SELECT id, paciente_id FROM jornadas WHERE status = 'ativa' "
            f"AND paciente_id IN ({','.join('?' for _ in pacientes)}) ORDER BY id",
            tuple(pacientes),
        ):
            jornadas[j["paciente_id"]] = j["id"]  # em ordem de id: fica a mais nova
    try:
        with em_lote():  # tudo ou nada: um erro no meio não deixa meio arquivo gravado
            for inicio in range(0, len(a_gravar), LINHAS_POR_INSERT):
                bloco = a_gravar[inicio:inicio + LINHAS_POR_INSERT]
                valores = []
                for r in bloco:
                    valores += [jornadas.get(r["_paciente_id"]), r["_paciente_id"],
                                r["_profissional_id"] or g.usuario["id"], r["data_atendimento"],
                                r["_texto"], r["_observacao"], r["_chave"]]
                execute(
                    """INSERT INTO diarios_terapeuticos
                       (jornada_id, paciente_id, profissional_id, data_atendimento, evolucao_clinica, observacao,
                        mensagem_familia, compartilhado_familia, origem, importacao_chave)
                       VALUES """ + ", ".join("(?, ?, ?, ?, ?, ?, NULL, 0, 'importacao', ?)" for _ in bloco),
                    tuple(valores),
                )
            if a_gravar:
                log_auditoria(g.usuario["organizacao_id"], g.usuario["id"], "importar", "evolucoes", None,
                              f"{len(a_gravar)} registros")
    except Exception:
        current_app.logger.exception("Falha ao importar evoluções (nada foi gravado)")
        return jsonify({"erro": "Não foi possível importar as evoluções. Nada foi gravado; tente de novo."}), 500
    return jsonify({
        "importadas": len(a_gravar),
        "puladas": len([r for r in resultados if r["status"] == "ja_importada"]),
        "erros": [{"linha": r["linha"], "paciente_nome": r["paciente_nome"], "erros": r["erros"]}
                  for r in resultados if r["status"] == "erro"],
    }), 201
