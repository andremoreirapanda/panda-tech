"""
Pandoo (25/09/2026) — jogos educativos da clínica. O jogo é um exercício
(`exercicios.tipo = 'jogo'`, aparece na Biblioteca e nas missões) com o
conteúdo e as regras em `pandoo_jogos`. Criar/editar/listar exige o módulo
liberado pelo Admin; ler um jogo e salvar resultado não — jogos já colocados
em missões continuam jogáveis se o módulo for desligado.
"""
import json

from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute, log_auditoria, agora_sql
from auth import login_required, papel_required
from modulos_service import modulo_ativo_para_clinica
from pandoo_service import validar_jogo, ErroPandoo
from blueprints.biblioteca_bp import _pode_editar, _resolver_categoria_id

bp = Blueprint("pandoo", __name__, url_prefix="/api/pandoo")

ERRO_MODULO = {"erro": "O Pandoo não está liberado para esta clínica. Fale com a Panda Tech para ativar."}


def _pandoo_ativo(org_id):
    org = query_one("SELECT plano FROM organizacoes WHERE id = ?", (org_id,))
    return bool(org) and modulo_ativo_para_clinica(org_id, org["plano"], "pandoo")


def _cenario_efetivo(org_id, cenario_jogo):
    org = query_one("SELECT pandoo_cenario_padrao, pandoo_cenario_imagem, pandoo_cenario_tom FROM organizacoes WHERE id = ?", (org_id,)) or {}
    tipo = cenario_jogo or org.get("pandoo_cenario_padrao") or "bambu"
    if tipo == "clinica" and org.get("pandoo_cenario_imagem"):
        return {"tipo": "clinica", "imagem": org["pandoo_cenario_imagem"], "tom": org.get("pandoo_cenario_tom") or "claro"}
    if tipo == "clinica":
        tipo = "bambu"  # imagem ainda não enviada: cai no cenário pronto
    return {"tipo": tipo, "imagem": None, "tom": "escuro"}


def _jogo_ou_erro(exercicio_id):
    ex = query_one("SELECT * FROM exercicios WHERE id = ?", (exercicio_id,))
    if not ex or ex.get("tipo") != "jogo":
        return None, None, (jsonify({"erro": "Jogo não encontrado."}), 404)
    jogo = query_one("SELECT * FROM pandoo_jogos WHERE exercicio_id = ?", (exercicio_id,))
    if not jogo:
        return None, None, (jsonify({"erro": "Jogo não encontrado."}), 404)
    return ex, jogo, None


def _dados_do_corpo(body, org_id):
    titulo = str(body.get("titulo") or "").strip()[:120]
    if not titulo:
        raise ErroPandoo("Dê um nome ao jogo.")
    conteudo, regras = validar_jogo(body.get("modelo"), body.get("conteudo"), body.get("regras"), body.get("cenario") or None)
    try:
        categoria_id = _resolver_categoria_id(body.get("categoria_id"), org_id)
    except ValueError as e:
        raise ErroPandoo(str(e))
    return {
        "titulo": titulo, "descricao": str(body.get("descricao") or "").strip()[:500],
        "categoria_id": categoria_id, "modelo": body["modelo"], "cenario": body.get("cenario") or None,
        "conteudo": conteudo, "regras": regras,
    }


@bp.get("/jogos")
@login_required
@papel_required("gestor", "profissional")
def listar_jogos():
    u = g.usuario
    if not _pandoo_ativo(u["organizacao_id"]):
        return jsonify(ERRO_MODULO), 403
    linhas = query(
        """SELECT e.id, e.titulo, e.categoria_id, p.modelo, p.total_itens, p.atualizado_em
           FROM exercicios e JOIN pandoo_jogos p ON p.exercicio_id = e.id
           WHERE e.organizacao_id = ? AND e.tipo = 'jogo' AND e.ativo = 1
           ORDER BY p.atualizado_em DESC, e.id DESC""",
        (u["organizacao_id"],),
    )
    return jsonify(linhas)


@bp.get("/jogos/<int:exercicio_id>")
@login_required
def obter_jogo(exercicio_id):
    u = g.usuario
    ex, jogo, erro = _jogo_ou_erro(exercicio_id)
    if erro:
        return erro
    if ex["organizacao_id"] != u["organizacao_id"]:
        return jsonify({"erro": "Sem acesso a este jogo."}), 403
    return jsonify({
        "id": ex["id"], "titulo": ex["titulo"], "descricao": ex["descricao"], "categoria_id": ex["categoria_id"],
        "modelo": jogo["modelo"], "conteudo": json.loads(jogo["conteudo_json"]), "regras": json.loads(jogo["regras_json"]),
        "cenario": jogo["cenario"], "cenario_efetivo": _cenario_efetivo(ex["organizacao_id"], jogo["cenario"]),
        "pode_editar": u["papel"] in ("gestor", "profissional") and _pode_editar(ex, u),
    })


@bp.post("/jogos")
@login_required
@papel_required("gestor", "profissional")
def criar_jogo():
    u = g.usuario
    if not _pandoo_ativo(u["organizacao_id"]):
        return jsonify(ERRO_MODULO), 403
    try:
        d = _dados_do_corpo(request.get_json(force=True, silent=True) or {}, u["organizacao_id"])
    except ErroPandoo as e:
        return jsonify({"erro": str(e)}), 400
    ex_id = execute(
        """INSERT INTO exercicios (organizacao_id, categoria_id, titulo, descricao, tipo)
           VALUES (?, ?, ?, ?, 'jogo')""",
        (u["organizacao_id"], d["categoria_id"], d["titulo"], d["descricao"]),
    )
    execute(
        """INSERT INTO pandoo_jogos (exercicio_id, modelo, conteudo_json, regras_json, cenario, total_itens, atualizado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (ex_id, d["modelo"], json.dumps(d["conteudo"]), json.dumps(d["regras"]), d["cenario"], len(d["conteudo"]["itens"]), agora_sql()),
    )
    log_auditoria(u["organizacao_id"], u["id"], "criar", "pandoo_jogo", ex_id, d["titulo"])
    return jsonify({"id": ex_id}), 201


@bp.put("/jogos/<int:exercicio_id>")
@login_required
@papel_required("gestor", "profissional")
def editar_jogo(exercicio_id):
    u = g.usuario
    ex, _, erro = _jogo_ou_erro(exercicio_id)
    if erro:
        return erro
    if not _pode_editar(ex, u):
        return jsonify({"erro": "Sem permissão para editar este jogo."}), 403
    if not _pandoo_ativo(u["organizacao_id"]):
        return jsonify(ERRO_MODULO), 403
    try:
        d = _dados_do_corpo(request.get_json(force=True, silent=True) or {}, ex["organizacao_id"])
    except ErroPandoo as e:
        return jsonify({"erro": str(e)}), 400
    execute("UPDATE exercicios SET titulo = ?, descricao = ?, categoria_id = ? WHERE id = ?",
            (d["titulo"], d["descricao"], d["categoria_id"], exercicio_id))
    execute(
        """UPDATE pandoo_jogos SET modelo = ?, conteudo_json = ?, regras_json = ?, cenario = ?, total_itens = ?, atualizado_em = ?
           WHERE exercicio_id = ?""",
        (d["modelo"], json.dumps(d["conteudo"]), json.dumps(d["regras"]), d["cenario"], len(d["conteudo"]["itens"]), agora_sql(), exercicio_id),
    )
    log_auditoria(u["organizacao_id"], u["id"], "editar", "pandoo_jogo", exercicio_id, d["titulo"])
    return jsonify({"ok": True})
