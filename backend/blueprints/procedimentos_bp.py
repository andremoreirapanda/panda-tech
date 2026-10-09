"""
Procedimentos da clínica (spec 09/10/2026, parte A). O gestor salva a lista
inteira de uma vez, como na tela; profissional e secretária só leem os nomes
dos ativos (nunca o valor).
"""
from flask import Blueprint, request, jsonify, g

from db import query, execute, log_auditoria, agora_sql, get_db
from auth import login_required, papel_required
import procedimentos_service as ps

bp = Blueprint("procedimentos", __name__, url_prefix="/api/procedimentos")


@bp.get("")
@login_required
@papel_required("gestor", "profissional", "secretaria")
def listar_procedimentos():
    u = g.usuario
    if u["papel"] != "gestor":
        return jsonify(ps.ativos_da_clinica(u["organizacao_id"]))
    return jsonify(query(
        """SELECT p.id, p.codigo, p.nome, p.valor_centavos, p.ativo, p.ordem,
                  (SELECT COUNT(*) FROM consultas c WHERE c.procedimento_id = p.id) AS em_uso
           FROM procedimentos p WHERE p.organizacao_id = ? ORDER BY p.ordem, p.id""",
        (u["organizacao_id"],)))


def _texto(valor):
    return valor.strip() if isinstance(valor, str) else ""


PREFIXO_PROVISORIO = "__provisorio__"


def _ativo(valor):
    """JSON pode trazer false/0/"0"/"false" (a própria listagem devolve 0/1)."""
    return 0 if valor in (False, 0, "0", "false", "False") else 1


def _eh_conflito(erro):
    # No Postgres chega como UniqueViolation/ForeignKeyViolation (subclasses de IntegrityError).
    return any(c.__name__ == "IntegrityError" for c in type(erro).__mro__)


@bp.put("")
@login_required
@papel_required("gestor")
def salvar_procedimentos():
    u = g.usuario
    org_id = u["organizacao_id"]
    body = request.get_json(force=True, silent=True) or {}
    itens = body.get("procedimentos")
    if not isinstance(itens, list):
        return jsonify({"erro": "Envie a lista de procedimentos."}), 400
    atuais = {p["id"]: p for p in query(
        """SELECT p.id, p.nome, (SELECT COUNT(*) FROM consultas c WHERE c.procedimento_id = p.id) AS em_uso
           FROM procedimentos p WHERE p.organizacao_id = ?""", (org_id,))}

    # 1) Valida tudo antes de gravar qualquer coisa (db.execute grava na hora).
    linhas, nomes_vistos, ids_vistos = [], set(), set()
    for n, item in enumerate(itens, start=1):
        if not isinstance(item, dict):
            return jsonify({"erro": f"Linha {n}: formato inválido."}), 400
        nome = _texto(item.get("nome"))
        rotulo = f"'{nome}'" if nome else f"Linha {n}"
        if not nome:
            return jsonify({"erro": f"Linha {n}: informe o nome do procedimento."}), 400
        if nome.startswith(PREFIXO_PROVISORIO):
            return jsonify({"erro": f"Linha {n}: escolha outro nome."}), 400
        if len(nome) > ps.NOME_MAX:
            return jsonify({"erro": f"{rotulo}: o nome passa de {ps.NOME_MAX} caracteres."}), 400
        codigo = _texto(item.get("codigo"))
        if len(codigo) > ps.CODIGO_MAX:
            return jsonify({"erro": f"{rotulo}: o código passa de {ps.CODIGO_MAX} caracteres."}), 400
        valor = ps.reais_para_centavos(item.get("valor"))
        if valor is None:
            return jsonify({"erro": f"{rotulo}: valor inválido (use, por exemplo, 230,00)."}), 400
        chave = ps.chave_nome(nome)
        if chave in nomes_vistos:
            return jsonify({"erro": f"{rotulo} aparece duas vezes na lista."}), 400
        nomes_vistos.add(chave)
        pid = item.get("id")
        if pid is not None:
            if isinstance(pid, bool) or not isinstance(pid, int) or pid not in atuais or pid in ids_vistos:
                return jsonify({"erro": f"{rotulo}: procedimento não encontrado nesta clínica."}), 400
            ids_vistos.add(pid)
        linhas.append({"id": pid, "nome": nome, "codigo": codigo or None, "valor": valor,
                       "ativo": _ativo(item.get("ativo")), "ordem": n - 1})
    removidos = [p for pid, p in atuais.items() if pid not in ids_vistos]
    usados = [p["nome"] for p in removidos if p["em_uso"]]
    if usados:
        return jsonify({"erro": f"'{usados[0]}' já foi usado em consultas: desative em vez de remover."}), 409

    # 2) Grava. Nomes trocados entre linhas passam por um nome provisório, para
    # não esbarrar no índice único no meio do caminho. Outra gravação ao mesmo
    # tempo (ou consulta nova num removido) vira 409 em vez de erro 500.
    try:
        _gravar(org_id, linhas, removidos, atuais)
    except Exception as erro:
        if not _eh_conflito(erro):
            raise
        get_db().rollback()  # no Postgres a transação fica abortada depois do erro
        return jsonify({"erro": "A lista mudou enquanto você editava. Recarregue a página e salve de novo."}), 409
    log_auditoria(org_id, u["id"], "editar", "procedimentos", None,
                  f"{len(linhas)} procedimento(s), {len(removidos)} removido(s)")
    return jsonify({"ok": True})


def _gravar(org_id, linhas, removidos, atuais):
    for p in removidos:
        execute("DELETE FROM procedimentos WHERE id = ?", (p["id"],))
    mudou_nome = [l for l in linhas if l["id"] and ps.chave_nome(atuais[l["id"]]["nome"]) != ps.chave_nome(l["nome"])]
    for l in mudou_nome:
        execute("UPDATE procedimentos SET nome = ? WHERE id = ?", (f"{PREFIXO_PROVISORIO}{l['id']}", l["id"]))
    for l in linhas:
        if l["id"]:
            execute("""UPDATE procedimentos SET nome = ?, codigo = ?, valor_centavos = ?, ativo = ?, ordem = ?,
                       atualizado_em = ? WHERE id = ?""",
                    (l["nome"], l["codigo"], l["valor"], l["ativo"], l["ordem"], agora_sql(), l["id"]))
        else:
            execute("""INSERT INTO procedimentos (organizacao_id, codigo, nome, valor_centavos, ativo, ordem)
                       VALUES (?, ?, ?, ?, ?, ?)""", (org_id, l["codigo"], l["nome"], l["valor"], l["ativo"], l["ordem"]))
