"""
IA fase 1: ditado por voz. O áudio chega, é transcrito e esquecido: nada do
conteúdo (áudio ou texto) é gravado; só o consumo em `ia_uso`.
Spec: docs/superpowers/specs/2026-11-25-ia-ditado-design.md
"""
import math

from flask import Blueprint, request, jsonify, g

import ia_service
import validacao_arquivo
from auth import login_required, papel_required
from db import query_one
from modulos_service import modulo_ativo_para_clinica
from rate_limit import limitar

bp = Blueprint("ia", __name__, url_prefix="/api/ia")

TOLERANCIA_DURACAO = 310  # o navegador corta em 300 s; sobra margem para arredondamento
ERRO_MODULO = "O assistente de IA não está liberado para esta clínica."


def _erro(msg, codigo, status):
    return jsonify({"erro": msg, "codigo": codigo}), status


def _e_audio_do_ditado(b):
    # WebM é o que o navegador grava; `_e_audio` não o conhece (só `_e_video`).
    return validacao_arquivo._e_audio(b) or b[:4] == b"\x1a\x45\xdf\xa3"


def _plano_se_modulo_ativo():
    org = query_one("SELECT plano FROM organizacoes WHERE id = ?", (g.usuario["organizacao_id"],))
    if org and modulo_ativo_para_clinica(g.usuario["organizacao_id"], org["plano"], "ia"):
        return org["plano"]
    return None


@bp.route("/ditado/config", methods=["GET"])
@login_required
@papel_required("gestor", "profissional")
def config_ditado():
    plano = _plano_se_modulo_ativo()
    if plano is None:
        return _erro(ERRO_MODULO, "sem_modulo", 403)
    base = {"limite_segundos": ia_service.LIMITE_SEGUNDOS}
    if not ia_service.tabelas_existem():
        return jsonify({**base, "disponivel": False, "motivo": "sem_migracao", "minutos_cota": 0,
                        "minutos_usados": 0, "minutos_restantes": 0})
    cota = ia_service.cota_do_mes(g.usuario["organizacao_id"], plano, ia_service.mes_atual())
    chave = ia_service.chave_configurada()
    return jsonify({**base, "disponivel": chave, "motivo": None if chave else "sem_chave",
                    "minutos_cota": cota["minutos_cota"], "minutos_usados": cota["minutos_usados"],
                    "minutos_restantes": cota["minutos_restantes"]})


@bp.route("/ditado", methods=["POST"])
@login_required
@papel_required("gestor", "profissional")
@limitar("ia_ditado", max_tentativas=30, janela_segundos=600)
def ditar():
    plano = _plano_se_modulo_ativo()
    if plano is None:
        return _erro(ERRO_MODULO, "sem_modulo", 403)
    if not ia_service.tabelas_existem() or not ia_service.chave_configurada():
        return _erro("O ditado não está disponível no momento.", "indisponivel", 503)

    arquivo = request.files.get("audio")
    if arquivo is None:
        return _erro("Nenhum áudio enviado.", "audio_invalido", 400)
    try:
        duracao = float(request.form.get("duracao_segundos", ""))
    except (TypeError, ValueError):
        return _erro("Duração inválida.", "audio_invalido", 400)
    if not math.isfinite(duracao) or duracao < 0 or duracao > TOLERANCIA_DURACAO:
        return _erro("O ditado pode ter no máximo 5 minutos.", "audio_invalido", 400)
    audio = arquivo.read(ia_service.LIMITE_BYTES + 1)
    if not audio or len(audio) > ia_service.LIMITE_BYTES or not _e_audio_do_ditado(audio[:16]):
        return _erro("Áudio inválido ou grande demais.", "audio_invalido", 400)

    org_id = g.usuario["organizacao_id"]
    cota = ia_service.cota_do_mes(org_id, plano, ia_service.mes_atual())
    previsto = ia_service.segundos_cobrados(None, duracao, len(audio))
    if cota["segundos_restantes"] <= 0:
        return _erro("Os minutos de ditado deste mês acabaram.", "cota_esgotada", 409)
    if cota["segundos_restantes"] < previsto:
        return _erro(f"Este áudio passa dos minutos que restam ({cota['minutos_restantes']} min).",
                     "cota_esgotada", 409)

    try:
        resultado = ia_service.transcrever(audio, arquivo.mimetype or "audio/webm", "ditado.webm")
    except ia_service.FalhaFornecedorIA:
        ia_service.registrar_uso(org_id, g.usuario["id"], "ditado", 0, ia_service.MODELO_PADRAO, 0)
        return _erro("Não foi possível transcrever agora. Tente de novo em instantes.", "falha_transcricao", 502)

    segundos = ia_service.segundos_cobrados(resultado["segundos"], duracao, len(audio))
    ia_service.registrar_uso(org_id, g.usuario["id"], "ditado", segundos, ia_service.MODELO_PADRAO, 1)
    restantes = max(0, cota["segundos_restantes"] - segundos) // 60
    return jsonify({"texto": resultado["texto"], "minutos_restantes": restantes})
