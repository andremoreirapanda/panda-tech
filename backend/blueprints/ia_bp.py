"""
IA fase 1: ditado por voz. O áudio chega, é transcrito e esquecido: nada do
conteúdo (áudio ou texto) é gravado; só o consumo em `ia_uso`.
Spec: docs/superpowers/specs/2026-11-25-ia-ditado-design.md
"""
import math

from flask import Blueprint, current_app, request, jsonify, g
from werkzeug.exceptions import RequestEntityTooLarge

import ia_service
from auth import login_required, papel_required
from db import get_db, log_evento, query_one
from modulos_service import modulo_ativo_para_clinica
from rate_limit import limitar

bp = Blueprint("ia", __name__, url_prefix="/api/ia")

TOLERANCIA_DURACAO = 310  # o navegador corta em 300 s; sobra margem para arredondamento
FOLGA_FORMULARIO = 64 * 1024  # cabeçalhos do multipart e o campo da duração
ERRO_MODULO = "O assistente de IA não está liberado para esta clínica."


def _erro(msg, codigo, status):
    return jsonify({"erro": msg, "codigo": codigo}), status


def _tipo_do_audio(b):
    """(nome, mime) pelo conteúdo (o iPhone grava MP4; o Chrome, WebM); None se não é áudio.
    O nome e o tipo informados pelo navegador não valem: o fornecedor decide pelo nome."""
    if b[4:8] == b"ftyp":
        return "ditado.mp4", "audio/mp4"
    if b[:4] == b"OggS":
        return "ditado.ogg", "audio/ogg"
    if b[:4] == b"\x1a\x45\xdf\xa3":
        return "ditado.webm", "audio/webm"
    if b[:3] == b"ID3" or (len(b) >= 2 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0):
        return "ditado.mp3", "audio/mpeg"
    if b[:4] == b"RIFF" and b[8:12] == b"WAVE":
        return "ditado.wav", "audio/wav"
    return None


def _sem_derrubar(acao, oque, *args, **kwargs):
    """Registro depois da transcrição (já paga): falha no banco não pode tirar o texto
    de quem ditou nem trocar o 502 por um 500. No log, só a classe do erro."""
    try:
        acao(*args, **kwargs)
    except Exception as e:
        try:
            get_db().rollback()
        except Exception:
            pass
        current_app.logger.warning("IA ditado: falha ao registrar %s (%s)", oque, type(e).__name__)


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
    mes = ia_service.mes_atual()
    base = {"limite_segundos": ia_service.LIMITE_SEGUNDOS, "mes": mes}
    if not ia_service.tabelas_existem():
        return jsonify({**base, "disponivel": False, "motivo": "sem_migracao", "minutos_cota": 0,
                        "minutos_usados": 0, "minutos_restantes": 0, "segundos_restantes": 0})
    cota = ia_service.cota_do_mes(g.usuario["organizacao_id"], plano, mes)
    chave = ia_service.chave_configurada()
    return jsonify({**base, "disponivel": chave, "motivo": None if chave else "sem_chave",
                    "minutos_cota": cota["minutos_cota"], "minutos_usados": cota["minutos_usados"],
                    "minutos_restantes": cota["minutos_restantes"],
                    "segundos_restantes": cota["segundos_restantes"]})


@bp.route("/ditado", methods=["POST"])
@login_required
@papel_required("gestor", "profissional")
@limitar("ia_ditado", max_tentativas=30, janela_segundos=600, por_usuario=True)
def ditar():
    # Tamanho barrado antes de ler o corpo; sem Content-Length, o Werkzeug para no limite.
    request.max_content_length = ia_service.LIMITE_BYTES + FOLGA_FORMULARIO
    if request.content_length is not None and request.content_length > request.max_content_length:
        return _erro("Áudio inválido ou grande demais.", "audio_invalido", 400)
    plano = _plano_se_modulo_ativo()
    if plano is None:
        return _erro(ERRO_MODULO, "sem_modulo", 403)
    if not ia_service.tabelas_existem() or not ia_service.chave_configurada():
        return _erro("O ditado não está disponível no momento.", "indisponivel", 503)

    try:
        arquivo = request.files.get("audio")
    except RequestEntityTooLarge:
        return _erro("Áudio inválido ou grande demais.", "audio_invalido", 400)
    if arquivo is None:
        return _erro("Nenhum áudio enviado.", "audio_invalido", 400)
    try:
        duracao = float(request.form.get("duracao_segundos", ""))
    except (TypeError, ValueError):
        return _erro("Duração inválida.", "audio_invalido", 400)
    if not math.isfinite(duracao) or duracao < 0 or duracao > TOLERANCIA_DURACAO:
        return _erro("O ditado pode ter no máximo 5 minutos.", "audio_invalido", 400)
    audio = arquivo.read(ia_service.LIMITE_BYTES + 1)
    tipo = _tipo_do_audio(audio[:16]) if audio else None
    if not audio or len(audio) > ia_service.LIMITE_BYTES or tipo is None:
        return _erro("Áudio inválido ou grande demais.", "audio_invalido", 400)
    nome_arquivo, mime = tipo

    org_id = g.usuario["organizacao_id"]
    cota = ia_service.cota_do_mes(org_id, plano, ia_service.mes_atual())
    previsto = ia_service.segundos_cobrados(None, duracao, len(audio))
    if cota["segundos_restantes"] <= 0:
        return _erro("Os minutos de ditado deste mês acabaram.", "cota_esgotada", 409)
    if cota["segundos_restantes"] < previsto:
        resta = cota["segundos_restantes"]
        quanto = f"{resta // 60} min" if resta >= 60 else f"{resta} s"
        return _erro(f"Este áudio passa dos minutos que restam ({quanto}).", "cota_esgotada", 409)

    try:
        resultado = ia_service.transcrever(audio, mime, nome_arquivo)
    except ia_service.FalhaFornecedorIA as e:
        _sem_derrubar(ia_service.registrar_uso, "o uso", org_id, g.usuario["id"], "ditado", 0,
                      ia_service.MODELO_PADRAO, 0)
        # Como o `email_falhou`: só a causa curta (HTTP nnn ou a classe do erro).
        _sem_derrubar(log_evento, "a falha", org_id, "ia_falhou", "ia_ditado", None,
                      payload={"causa": e.causa})
        return _erro("Não foi possível transcrever agora. Tente de novo em instantes.", "falha_transcricao", 502)

    segundos = ia_service.segundos_cobrados(resultado["segundos"], duracao, len(audio))
    _sem_derrubar(ia_service.registrar_uso, "o uso", org_id, g.usuario["id"], "ditado", segundos,
                  ia_service.MODELO_PADRAO, 1)
    restantes = max(0, cota["segundos_restantes"] - segundos)
    return jsonify({"texto": resultado["texto"], "minutos_restantes": restantes // 60,
                    "segundos_restantes": restantes})
