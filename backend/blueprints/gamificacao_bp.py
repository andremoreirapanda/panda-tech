"""
Domínio 6 — Gamificação (leitura — a escrita acontece via gamificacao_service,
disparada pelo evento 'missao_concluida' na Jornada Terapêutica).
"""
from flask import Blueprint, jsonify

from db import query, query_one
from auth import login_required, paciente_acessivel
from gamificacao_service import sequencia_efetiva

bp = Blueprint("gamificacao", __name__, url_prefix="/api/gamificacao")


@bp.get("/paciente/<int:paciente_id>")
@login_required
def obter_gamificacao(paciente_id):
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Sem acesso."}), 403
    gam = query_one("SELECT * FROM gamificacao_paciente WHERE paciente_id = ?", (paciente_id,))
    if gam:
        gam["sequencia_dias"] = sequencia_efetiva(gam)  # quebrada aparece como 0
    medalhas = query(
        """SELECT m.*, mp.conquistado_em FROM medalhas_paciente mp
           JOIN medalhas m ON m.id = mp.medalha_id
           WHERE mp.paciente_id = ? ORDER BY mp.conquistado_em DESC""",
        (paciente_id,),
    )
    todas_medalhas = query("SELECT * FROM medalhas ORDER BY id")
    bau = query("SELECT * FROM recompensas_bau WHERE paciente_id = ? ORDER BY criado_em DESC", (paciente_id,))
    conquistadas_ids = {m["id"] for m in medalhas}
    for m in todas_medalhas:
        m["conquistada"] = m["id"] in conquistadas_ids
    return jsonify({
        "gamificacao": gam,
        "medalhas_conquistadas": medalhas,
        "todas_medalhas": todas_medalhas,
        "bau": bau,
    })
