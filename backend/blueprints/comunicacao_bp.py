"""
Domínio 4 — Comunicação (Documento 09 / Módulo 04)

UX Pattern 05 — Chat: Mensagem → Imagem → Vídeo → Áudio → Resposta rápida → Reação → IA
"""
from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute, log_evento, criar_notificacao
from auth import login_required, paciente_acessivel, papel_required
from validacao_arquivo import validar_arquivo_base64

bp = Blueprint("comunicacao", __name__, url_prefix="/api/comunicacao")


def _obter_ou_criar_conversa(paciente_id):
    conversa = query_one("SELECT * FROM conversas WHERE paciente_id = ?", (paciente_id,))
    if conversa:
        return conversa["id"]
    return execute("INSERT INTO conversas (paciente_id) VALUES (?)", (paciente_id,))


LIMITE_ANEXO_MENSAGEM_BYTES = 4 * 1024 * 1024  # 4 MB — mesma política do Diário/Biblioteca


@bp.get("/paciente/<int:paciente_id>/conversa")
@login_required
def obter_conversa(paciente_id):
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Sem acesso à conversa deste paciente."}), 403
    conversa_id = _obter_ou_criar_conversa(paciente_id)
    mensagens = query(
        """SELECT m.id, m.conversa_id, m.autor_id, m.tipo, m.conteudo, m.anexo_nome, m.reacao, m.criado_em,
                  u.nome as autor_nome, u.papel as autor_papel, u.avatar_emoji as autor_avatar,
                  (m.anexo_base64 IS NOT NULL AND m.anexo_base64 != '') as tem_anexo
           FROM mensagens m JOIN usuarios u ON u.id = m.autor_id
           WHERE m.conversa_id = ? ORDER BY m.criado_em""",
        (conversa_id,),
    )
    return jsonify({"conversa_id": conversa_id, "mensagens": mensagens})


@bp.get("/mensagem/<int:mensagem_id>/anexo")
@login_required
def obter_anexo_mensagem(mensagem_id):
    """Carrega o conteúdo do anexo sob demanda (evita pesar a listagem principal do chat)."""
    msg = query_one(
        "SELECT m.*, c.paciente_id FROM mensagens m JOIN conversas c ON c.id = m.conversa_id WHERE m.id = ?",
        (mensagem_id,),
    )
    if not msg:
        return jsonify({"erro": "Mensagem não encontrada."}), 404
    if not paciente_acessivel(msg["paciente_id"]):
        return jsonify({"erro": "Sem acesso a esta conversa."}), 403
    return jsonify({"tipo": msg["tipo"], "anexo_nome": msg["anexo_nome"], "anexo_base64": msg["anexo_base64"]})


@bp.post("/paciente/<int:paciente_id>/mensagem")
@login_required
def enviar_mensagem(paciente_id):
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Sem acesso à conversa deste paciente."}), 403
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    tipo = body.get("tipo", "texto")
    conteudo = (body.get("conteudo") or "").strip()
    anexo_base64 = body.get("anexo_base64")
    anexo_nome = body.get("anexo_nome", "")

    if tipo in ("imagem", "audio", "video"):
        if not anexo_base64:
            return jsonify({"erro": "Anexo vazio."}), 400
        tamanho_estimado = int(len(anexo_base64) * 3 / 4)
        if tamanho_estimado > LIMITE_ANEXO_MENSAGEM_BYTES:
            return jsonify({"erro": f"Arquivo muito grande (limite de {LIMITE_ANEXO_MENSAGEM_BYTES // (1024*1024)}MB)."}), 400
        # Correção de auditoria (recomendação 1, 25/08/2026): confere a assinatura
        # real do arquivo, não só o tamanho declarado.
        ok, erro_assinatura = validar_arquivo_base64(anexo_base64, tipo)
        if not ok:
            return jsonify({"erro": erro_assinatura}), 400
        if not conteudo:
            conteudo = {"imagem": "📷 Foto", "audio": "🎙️ Áudio", "video": "🎬 Vídeo"}[tipo]
    else:
        anexo_base64, anexo_nome, tamanho_estimado = None, None, None
        if not conteudo:
            return jsonify({"erro": "Mensagem vazia."}), 400

    conversa_id = _obter_ou_criar_conversa(paciente_id)
    msg_id = execute(
        "INSERT INTO mensagens (conversa_id, autor_id, tipo, conteudo, anexo_nome, anexo_base64, anexo_tamanho_bytes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (conversa_id, u["id"], tipo, conteudo, anexo_nome, anexo_base64, tamanho_estimado),
    )
    org_id = u["organizacao_id"] or query_one("SELECT organizacao_id FROM pacientes WHERE id=?", (paciente_id,))["organizacao_id"]
    log_evento(org_id, "mensagem_enviada", "mensagem", msg_id, paciente_id)

    destinatarios = set()
    for r in query("SELECT usuario_id FROM responsaveis_pacientes WHERE paciente_id = ?", (paciente_id,)):
        destinatarios.add(r["usuario_id"])
    for p in query("SELECT usuario_id FROM profissionais_pacientes WHERE paciente_id = ?", (paciente_id,)):
        destinatarios.add(p["usuario_id"])
    destinatarios.discard(u["id"])
    for dest_id in destinatarios:
        criar_notificacao(
            dest_id, f"Nova mensagem de {u['nome']}", conteudo[:80],
            tipo="mensagem", entidade="paciente", entidade_id=paciente_id,
        )
    return jsonify({"id": msg_id}), 201





REACOES_PERMITIDAS = ("👍", "❤️", "⭐", "👏", "😊")


@bp.post("/mensagem/<int:mensagem_id>/reagir")
@login_required
def reagir_mensagem(mensagem_id):
    """Reações rápidas (Doc 29) — reduz a necessidade de escrever mensagem toda hora."""
    msg = query_one(
        "SELECT m.*, c.paciente_id FROM mensagens m JOIN conversas c ON c.id = m.conversa_id WHERE m.id = ?",
        (mensagem_id,),
    )
    if not msg:
        return jsonify({"erro": "Mensagem não encontrada."}), 404
    if not paciente_acessivel(msg["paciente_id"]):
        return jsonify({"erro": "Sem acesso a esta conversa."}), 403

    body = request.get_json(force=True, silent=True) or {}
    reacao = body.get("reacao", "❤️")
    if reacao not in REACOES_PERMITIDAS:
        return jsonify({"erro": "Reação inválida."}), 400

    # Clicar de novo na mesma reação remove (toggle)
    nova_reacao = None if msg["reacao"] == reacao else reacao
    execute("UPDATE mensagens SET reacao = ? WHERE id = ?", (nova_reacao, mensagem_id))
    return jsonify({"ok": True, "reacao": nova_reacao})


# --------------------------------------------------------------- Mural / Avisos

@bp.get("/avisos")
@login_required
def listar_avisos():
    u = g.usuario
    sql = """SELECT a.*, u.nome as autor_nome FROM avisos a JOIN usuarios u ON u.id = a.autor_id
             WHERE a.organizacao_id = ?"""
    params = [u["organizacao_id"]]
    if u["papel"] == "responsavel":
        sql += " AND a.publico IN ('todos', 'familias')"
    elif u["papel"] in ("gestor", "profissional", "secretaria"):
        sql += " AND a.publico IN ('todos', 'equipe')"
    # admin_master (raro acessar isso) vê tudo, sem filtro
    sql += " ORDER BY a.criado_em DESC LIMIT 20"
    rows = query(sql, tuple(params))
    return jsonify(rows)


@bp.post("/avisos")
@login_required
@papel_required("gestor", "profissional", "admin_master", "secretaria")
def criar_aviso():
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    publico = body.get("publico") if body.get("publico") in ("todos", "equipe", "familias") else "todos"
    aviso_id = execute(
        "INSERT INTO avisos (organizacao_id, autor_id, titulo, conteudo, publico) VALUES (?, ?, ?, ?, ?)",
        (u["organizacao_id"], u["id"], body.get("titulo", "Aviso"), body.get("conteudo", ""), publico),
    )
    return jsonify({"id": aviso_id}), 201
