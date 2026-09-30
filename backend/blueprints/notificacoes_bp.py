"""
Core > Notificações (Documento 07) — central única.
"""
from flask import Blueprint, jsonify, g

from db import query, execute, manter_ultimas_notificacoes, MAX_NOTIFICACOES

bp = Blueprint("notificacoes", __name__, url_prefix="/api/notificacoes")

from auth import login_required


@bp.get("")
@login_required
def listar():
    manter_ultimas_notificacoes(g.usuario["id"])
    rows = query(
        "SELECT * FROM notificacoes WHERE usuario_id = ? ORDER BY criado_em DESC, id DESC LIMIT ?",
        (g.usuario["id"], MAX_NOTIFICACOES),
    )
    return jsonify(rows)


@bp.post("/<int:notificacao_id>/marcar-lida")
@login_required
def marcar_lida(notificacao_id):
    execute("UPDATE notificacoes SET lida = 1 WHERE id = ? AND usuario_id = ?", (notificacao_id, g.usuario["id"]))
    return jsonify({"ok": True})


@bp.post("/marcar-todas-lidas")
@login_required
def marcar_todas_lidas():
    execute("UPDATE notificacoes SET lida = 1 WHERE usuario_id = ?", (g.usuario["id"],))
    return jsonify({"ok": True})
