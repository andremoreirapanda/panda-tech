"""
Feature Flags — endpoints de gestão (Documento 22A).
Só o Gestor mexe aqui; o Admin do SaaS mexe no plano (que define o teto).
"""
from flask import Blueprint, request, jsonify, g

from db import query_one, execute, log_auditoria
from auth import login_required, papel_required
from modulos_service import (
    MODULOS_OPCIONAIS, modulos_do_plano, modulos_habilitados_clinica, _garantir_linhas_clinica,
)

bp = Blueprint("modulos", __name__, url_prefix="/api/modulos")


@bp.get("")
@login_required
@papel_required("gestor", "admin_master")
def listar():
    u = g.usuario
    org = query_one("SELECT plano FROM organizacoes WHERE id = ?", (u["organizacao_id"],))
    liberados_plano = set(modulos_do_plano(org["plano"]))
    habilitados = modulos_habilitados_clinica(u["organizacao_id"], org["plano"])

    resultado = []
    for m in MODULOS_OPCIONAIS:
        resultado.append({
            **m,
            "liberado_pelo_plano": m["codigo"] in liberados_plano,
            "habilitado": m["codigo"] in habilitados,
        })
    return jsonify(resultado)


@bp.post("/<codigo>/toggle")
@login_required
@papel_required("gestor")
def alternar(codigo):
    u = g.usuario
    org = query_one("SELECT plano FROM organizacoes WHERE id = ?", (u["organizacao_id"],))
    if codigo not in modulos_do_plano(org["plano"]):
        return jsonify({"erro": "Este módulo não está incluído no seu plano atual. Fale com o time comercial para fazer upgrade."}), 403

    _garantir_linhas_clinica(u["organizacao_id"], org["plano"])
    linha = query_one(
        "SELECT * FROM modulos_clinica WHERE organizacao_id = ? AND modulo_codigo = ?",
        (u["organizacao_id"], codigo),
    )
    novo_estado = 0 if linha["habilitado"] else 1
    execute(
        "UPDATE modulos_clinica SET habilitado = ? WHERE id = ?", (novo_estado, linha["id"])
    )
    log_auditoria(u["organizacao_id"], u["id"], "alternar_modulo", "modulo_clinica", linha["id"], f"{codigo} -> {'on' if novo_estado else 'off'}")
    return jsonify({"habilitado": bool(novo_estado)})
