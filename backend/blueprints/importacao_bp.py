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

from flask import Blueprint, request, jsonify, g

from db import query, query_one
from auth import login_required, papel_required
from modulos_service import modulo_ativo_para_clinica
from blueprints.pessoas_bp import (
    MASCOTES_VALIDOS, criar_paciente_core, vincular_responsavel_core, _limite_do_plano_excedido,
)

bp = Blueprint("importacao", __name__, url_prefix="/api/importacao")

_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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


def _validar_linha(linha, indice, contas_conhecidas):
    """
    Valida uma linha do lote. `contas_conhecidas` é um dict {email_lower: nome_da_conta}
    acumulado ao longo do lote inteiro (já semeado com as contas que já existem
    no banco desta clínica) — permite avisar quando duas linhas do MESMO lote
    usam o mesmo e-mail com nomes diferentes (provável erro de digitação na
    planilha de origem), sem bloquear a importação por causa disso.

    Retorna um dict com o resultado da linha (nunca lança exceção — uma linha
    ruim não pode derrubar o lote inteiro).
    """
    erros = []
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
    if not resp_nome:
        erros.append("Nome do responsável é obrigatório.")
    if not resp_email:
        erros.append("E-mail do responsável é obrigatório.")
    elif not _RE_EMAIL.match(resp_email):
        erros.append("E-mail do responsável parece inválido.")
    if avatar_mascote and avatar_mascote not in MASCOTES_VALIDOS:
        erros.append(f"Mascote '{avatar_mascote}' não é válido — deixe em branco para usar o padrão.")

    aviso = None
    responsavel_status = None
    if resp_email and _RE_EMAIL.match(resp_email):
        conhecida = contas_conhecidas.get(resp_email)
        if conhecida is None:
            responsavel_status = "novo"
        else:
            responsavel_status = "existente"
            if resp_nome and conhecida.lower() != resp_nome.lower():
                aviso = (f"Este e-mail já é de uma conta chamada '{conhecida}' nesta clínica — "
                         f"o paciente será vinculado a ela (o nome '{resp_nome}' informado aqui não será usado).")
        # Registra pra próximas linhas do lote enxergarem essa conta como já conhecida.
        contas_conhecidas.setdefault(resp_email, conhecida or resp_nome)

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
        "valido": not erros,
        "erros": erros,
        "aviso": aviso,
        "responsavel_status": responsavel_status,
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

    contas_conhecidas = _contas_existentes_do_lote(g.usuario["organizacao_id"], linhas)
    resultados = [_validar_linha(l, i, contas_conhecidas) for i, l in enumerate(linhas)]
    validas = [r for r in resultados if r["valido"]]

    erro_limite = None
    if validas:
        erro_limite = _limite_do_plano_excedido_para_lote(g.usuario["organizacao_id"], len(validas))

    return jsonify({
        "linhas": resultados,
        "total": len(resultados),
        "validas": len(validas),
        "invalidas": len(resultados) - len(validas),
        "erro_limite_plano": erro_limite,
    })


def _limite_do_plano_excedido_para_lote(organizacao_id, quantidade_novos):
    """`_limite_do_plano_excedido` (pessoas_bp.py) checa 1 paciente por vez
    (>=), então não serve pra checar "cabem N novos de uma vez" — esta
    função simula isso olhando o mesmo limite do plano, mas comparando
    contra (pacientes ativos atuais + quantidade do lote)."""
    org = query_one("SELECT plano FROM organizacoes WHERE id = ?", (organizacao_id,))
    if not org:
        return None
    plano = query_one(
        "SELECT nome, limite_pacientes FROM planos WHERE codigo = ?", (org["plano"],)
    )
    if not plano or plano["limite_pacientes"] is None:
        return None
    atual = query_one(
        "SELECT COUNT(*) as c FROM pacientes WHERE organizacao_id = ? AND ativo = 1", (organizacao_id,)
    )["c"]
    if atual + quantidade_novos > plano["limite_pacientes"]:
        vagas = max(plano["limite_pacientes"] - atual, 0)
        return (f"O plano {plano['nome']} permite até {plano['limite_pacientes']} paciente(s) ativo(s). "
                f"Sua clínica já tem {atual} e este lote tem {quantidade_novos} linha(s) válida(s) — só há espaço "
                f"para mais {vagas}. Reduza o lote ou fale com o time comercial para aumentar o limite.")
    return None


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
    contas_conhecidas = _contas_existentes_do_lote(g.usuario["organizacao_id"], linhas)
    resultados = [_validar_linha(l, i, contas_conhecidas) for i, l in enumerate(linhas)]
    validas = [r for r in resultados if r["valido"]]

    if validas:
        erro_limite = _limite_do_plano_excedido_para_lote(g.usuario["organizacao_id"], len(validas))
        if erro_limite:
            return jsonify({"erro": erro_limite}), 403

    organizacao_id = g.usuario["organizacao_id"]
    criados = []
    ignorados = [{"linha": r["linha"], "nome": r["nome"], "erros": r["erros"]} for r in resultados if not r["valido"]]

    for r in validas:
        paciente_id = criar_paciente_core(
            organizacao_id, r["nome"], r["data_nascimento"], r["avatar_mascote"], r["genero"],
        )
        resp = vincular_responsavel_core(
            organizacao_id, paciente_id, r["responsavel_nome"], r["responsavel_email"],
            r["responsavel_telefone"], r["parentesco"],
            enviar_whatsapp=False,  # lote pode ter dezenas de linhas — não dispara N mensagens de convite de uma vez
        )
        criados.append({
            "linha": r["linha"], "paciente_id": paciente_id, "nome": r["nome"],
            "responsavel_novo": bool(resp.get("link_convite")),
        })

    return jsonify({"criados": criados, "ignorados": ignorados, "total_criados": len(criados)}), 201
