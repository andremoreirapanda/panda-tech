"""
Pandoo (25/09/2026) — jogos educativos da clínica. O jogo é um exercício
(`exercicios.tipo = 'jogo'`, aparece na Biblioteca e nas missões) com o
conteúdo e as regras em `pandoo_jogos`. Criar/editar/listar exige o módulo
liberado pelo Admin; ler um jogo e salvar resultado não — jogos já colocados
em missões continuam jogáveis se o módulo for desligado.
"""
import json
from datetime import date

from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute, log_auditoria, agora_sql
from auth import login_required, papel_required, paciente_acessivel
from modulos_service import modulo_ativo_para_clinica
from pandoo_service import validar_jogo, calcular_resultado, ErroPandoo
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


def _jogo_em_missao_de_filho(exercicio_id, responsavel_id):
    return bool(query_one(
        """SELECT 1 FROM atividades a
           JOIN missoes m ON m.id = a.missao_id
           JOIN planos_terapeuticos p ON p.id = m.plano_id
           JOIN jornadas j ON j.id = p.jornada_id
           JOIN responsaveis_pacientes rp ON rp.paciente_id = j.paciente_id
           WHERE a.exercicio_id = ? AND rp.usuario_id = ? AND m.status != 'rascunho'
           LIMIT 1""",
        (exercicio_id, responsavel_id),
    ))


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
    if u["papel"] == "responsavel" and not _jogo_em_missao_de_filho(exercicio_id, u["id"]):
        # jogo pode ter foto/voz de uma criança específica: a família só vê o
        # que está nas missões publicadas dos próprios filhos
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
    try:
        execute(
            """INSERT INTO pandoo_jogos (exercicio_id, modelo, conteudo_json, regras_json, cenario, total_itens, atualizado_em)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ex_id, d["modelo"], json.dumps(d["conteudo"]), json.dumps(d["regras"]), d["cenario"], len(d["conteudo"]["itens"]), agora_sql()),
        )
    except Exception:
        # sem transação entre os dois INSERTs: desfaz o exercício pra não
        # deixar um "jogo" vazio na Biblioteca
        execute("DELETE FROM exercicios WHERE id = ?", (ex_id,))
        raise
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


def _paciente_da_missao(missao_id):
    linha = query_one(
        """SELECT j.paciente_id FROM missoes m JOIN planos_terapeuticos p ON p.id = m.plano_id
           JOIN jornadas j ON j.id = p.jornada_id WHERE m.id = ?""",
        (missao_id,),
    )
    return linha["paciente_id"] if linha else None


@bp.post("/resultados")
@login_required
def salvar_resultado():
    """Uma partida terminada (ou encerrada em "Finalizar jogo"). Os números
    são recalculados aqui a partir dos detalhes — o navegador não decide."""
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    try:
        paciente_id = int(body.get("paciente_id"))
        exercicio_id = int(body.get("exercicio_id"))
    except (TypeError, ValueError):
        return jsonify({"erro": "Paciente e jogo são obrigatórios."}), 400
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Você não tem acesso a este paciente."}), 403
    paciente = query_one("SELECT organizacao_id FROM pacientes WHERE id = ?", (paciente_id,))
    ex, jogo, erro = _jogo_ou_erro(exercicio_id)
    if erro:
        return erro
    if not paciente or ex["organizacao_id"] != paciente["organizacao_id"]:
        return jsonify({"erro": "Sem acesso a este jogo."}), 403

    missao_id, atividade_id = body.get("missao_id"), body.get("atividade_id")
    if missao_id or atividade_id:
        atividade = query_one("SELECT * FROM atividades WHERE id = ?", (atividade_id,)) if atividade_id else None
        if (not atividade or str(atividade["missao_id"]) != str(missao_id)
                or atividade["exercicio_id"] != exercicio_id or _paciente_da_missao(missao_id) != paciente_id):
            return jsonify({"erro": "Missão e atividade não conferem com este jogo e paciente."}), 400

    try:
        r = calcular_resultado(body.get("detalhes"))
    except ErroPandoo as e:
        return jsonify({"erro": str(e)}), 400
    novo_id = execute(
        """INSERT INTO pandoo_resultados (organizacao_id, paciente_id, exercicio_id, missao_id, atividade_id, modelo,
               iniciado_em, finalizado_em, encerrado_antes, total_rodadas, acertos, a_treinar, detalhes_json, usuario_id, data_local)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (paciente["organizacao_id"], paciente_id, exercicio_id, missao_id or None, atividade_id or None, jogo["modelo"],
         str(body.get("iniciado_em") or "")[:25] or None, agora_sql(), 1 if body.get("encerrado_antes") else 0,
         r["total_rodadas"], r["acertos"], r["a_treinar"], json.dumps(r["detalhes"], ensure_ascii=False), u["id"],
         date.today().isoformat()),
    )
    return jsonify({"id": novo_id, "total_rodadas": r["total_rodadas"], "acertos": r["acertos"], "a_treinar": r["a_treinar"]}), 201


@bp.get("/resultados")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def listar_resultados():
    try:
        paciente_id = int(request.args.get("paciente_id"))
    except (TypeError, ValueError):
        return jsonify({"erro": "Informe o paciente."}), 400
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Você não tem acesso a este paciente."}), 403
    partidas = query(
        """SELECT r.id, r.exercicio_id, e.titulo, r.modelo, r.finalizado_em, r.data_local, r.encerrado_antes,
                  r.total_rodadas, r.acertos, r.a_treinar, r.detalhes_json, r.missao_id
           FROM pandoo_resultados r JOIN exercicios e ON e.id = r.exercicio_id
           WHERE r.paciente_id = ? ORDER BY r.id DESC LIMIT 50""",
        (paciente_id,),
    )
    por_jogo = {}
    for p in partidas:
        p["detalhes"] = json.loads(p.pop("detalhes_json") or "[]")
        jogo = por_jogo.setdefault(p["exercicio_id"], {"exercicio_id": p["exercicio_id"], "titulo": p["titulo"], "itens": {}})
        for d in p["detalhes"]:
            chave = d.get("texto") or d.get("item_id")
            item = jogo["itens"].setdefault(chave, {"texto": chave, "conseguiu": 0, "total": 0})
            item["total"] += 1
            item["conseguiu"] += 1 if d["resultado"] == "conseguiu" else 0
    resumo = [{**j, "itens": sorted(j["itens"].values(), key=lambda i: i["texto"])} for j in por_jogo.values()]
    return jsonify({"partidas": partidas, "por_jogo": resumo})
