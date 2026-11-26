"""
IA fase 1 (ditado por voz): único ponto que fala com fornecedores de IA.

Cota mensal por clínica (minutos do plano + créditos do mês), registro de uso
(nunca guarda áudio nem texto) e transcrição via API da OpenAI.

Spec: docs/superpowers/specs/2026-11-25-ia-ditado-design.md (seções 5.2 a 5.6)
"""
import math
import os

import requests

import ausencias_service
from db import execute, get_db, query, query_one
from modulos_service import cadeia_de_bases

LIMITE_SEGUNDOS = 300
LIMITE_BYTES = 15 * 1024 * 1024
BYTES_POR_SEGUNDO_MAX = 16000  # maior bitrate comum: o tamanho nunca subestima a duração

# gpt-transcribe: modelo recomendado pela OpenAI (docs consultadas em 26/11/2026),
# US$ 0,0045/min; whisper-1 e os gpt-4o-*-transcribe saem do ar em 26/02/2027.
MODELO_PADRAO = os.environ.get("OPENAI_MODELO_TRANSCRICAO") or "gpt-transcribe"
PRECO_MICRO_USD_POR_MINUTO = {
    "gpt-transcribe": 4500,
    "whisper-1": 6000,
    "gpt-4o-transcribe": 6000,
    "gpt-4o-mini-transcribe": 3000,
}
_PRECO_DESCONHECIDO = 6000

URL_TRANSCRICAO = "https://api.openai.com/v1/audio/transcriptions"

VOCABULARIO_CLINICO = (
    "Sessão de terapia infantil: fonoaudiologia, terapia ocupacional, psicopedagogia e psicologia. "
    "Termos: fonema, articulação, praxia, apraxia de fala, ceceio, disfluência, gagueira, linguagem "
    "expressiva, consciência fonológica, motricidade orofacial, deglutição, integração sensorial, "
    "processamento auditivo, coordenação motora fina, TEA, TDAH, função executiva, alfabetização, "
    "dislexia, atenção compartilhada, comunicação alternativa, plano terapêutico, evolução."
)


class FalhaFornecedorIA(Exception):
    """Erro do fornecedor de IA. A mensagem nunca leva chave, áudio nem texto."""


_tabelas_ok = [False]


def mes_atual():
    return ausencias_service.hoje_brasilia().strftime("%Y-%m")


def tabelas_existem():
    """True se `ia_uso`/`ia_creditos`/`planos.ia_minutos_mes` já existem (deploy antes da migração)."""
    if _tabelas_ok[0]:
        return True
    try:
        query_one("SELECT ia_minutos_mes FROM planos LIMIT 1")
        query_one("SELECT id FROM ia_uso LIMIT 1")
        query_one("SELECT id FROM ia_creditos LIMIT 1")
    except Exception:
        try:
            get_db().rollback()
        except Exception:
            pass
        return False
    _tabelas_ok[0] = True
    return True


def chave_configurada():
    return bool((os.environ.get("OPENAI_API_KEY") or "").strip())


def minutos_do_plano(codigo_plano):
    """Primeiro `ia_minutos_mes` não NULL no plano e nas bases (herança); nada → 0."""
    plano = query_one("SELECT id, ia_minutos_mes FROM planos WHERE codigo = ?", (codigo_plano,))
    if not plano:
        return 0
    if plano["ia_minutos_mes"] is not None:
        return int(plano["ia_minutos_mes"])
    for base_id in cadeia_de_bases(plano["id"]):
        linha = query_one("SELECT ia_minutos_mes FROM planos WHERE id = ?", (base_id,))
        if linha and linha["ia_minutos_mes"] is not None:
            return int(linha["ia_minutos_mes"])
    return 0


def cota_do_mes(organizacao_id, codigo_plano, mes):
    creditos = query_one(
        "SELECT COALESCE(SUM(minutos), 0) AS m FROM ia_creditos WHERE organizacao_id = ? AND mes = ?",
        (organizacao_id, mes))["m"]
    usados = query_one(
        "SELECT COALESCE(SUM(segundos), 0) AS s FROM ia_uso WHERE organizacao_id = ? AND mes = ? AND sucesso = 1",
        (organizacao_id, mes))["s"]
    minutos_cota = minutos_do_plano(codigo_plano) + int(creditos)
    segundos_usados = int(usados)
    segundos_restantes = max(0, minutos_cota * 60 - segundos_usados)
    return {
        "minutos_cota": minutos_cota,
        "minutos_usados": math.ceil(segundos_usados / 60),
        "segundos_usados": segundos_usados,
        "segundos_restantes": segundos_restantes,
        "minutos_restantes": segundos_restantes // 60,
    }


def segundos_cobrados(segundos_fornecedor, segundos_navegador, tamanho_bytes):
    if segundos_fornecedor is not None:
        base = float(segundos_fornecedor)
    else:
        base = max(float(segundos_navegador or 0), tamanho_bytes / BYTES_POR_SEGUNDO_MAX)
    return min(LIMITE_SEGUNDOS, max(1, math.ceil(base)))


def registrar_uso(organizacao_id, usuario_id, recurso, segundos, modelo, sucesso):
    custo = None
    if sucesso:
        preco = PRECO_MICRO_USD_POR_MINUTO.get(modelo, _PRECO_DESCONHECIDO)
        custo = round(segundos * preco / 60)
    execute(
        "INSERT INTO ia_uso (organizacao_id, usuario_id, recurso, mes, segundos, modelo, "
        "custo_estimado_micro_usd, sucesso, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (organizacao_id, usuario_id, recurso, mes_atual(), int(segundos) if sucesso else 0, modelo, custo,
         1 if sucesso else 0, ausencias_service.agora_brasilia_iso()))


def _chamar_openai(audio, mime, nome_arquivo, modelo):
    """Única função que faz chamada de rede. Devolve o JSON da resposta."""
    chave = (os.environ.get("OPENAI_API_KEY") or "").strip()
    dados = {"model": modelo, "language": "pt", "prompt": VOCABULARIO_CLINICO}
    if modelo == "whisper-1":
        dados["response_format"] = "verbose_json"  # devolve `duration`; os demais usam o json padrão
    try:
        resp = requests.post(
            URL_TRANSCRICAO,
            headers={"Authorization": f"Bearer {chave}"},
            data=dados,
            files={"file": (nome_arquivo, audio, mime)},
            timeout=90,
        )
    except requests.RequestException as e:
        raise FalhaFornecedorIA(f"Falha de rede com o fornecedor de IA ({type(e).__name__}).") from None
    if resp.status_code != 200:
        raise FalhaFornecedorIA(f"O fornecedor de IA respondeu HTTP {resp.status_code}.")
    try:
        return resp.json()
    except ValueError:
        raise FalhaFornecedorIA("Resposta inválida do fornecedor de IA.") from None


def _duracao(resposta):
    """Segundos informados pelo fornecedor (`duration` ou `usage` por duração); senão None."""
    d = resposta.get("duration")
    if isinstance(d, (int, float)) and not isinstance(d, bool) and d > 0:
        return float(d)
    uso = resposta.get("usage")
    if isinstance(uso, dict) and uso.get("type") == "duration":
        s = uso.get("seconds")
        if isinstance(s, (int, float)) and not isinstance(s, bool) and s > 0:
            return float(s)
    return None


def transcrever(audio, mime, nome_arquivo):
    """→ {"texto": str, "segundos": float | None}. Erro → FalhaFornecedorIA."""
    if os.environ.get("FLASK_DEBUG") == "1" and os.environ.get("IA_FAKE") == "1":
        return {"texto": "Texto de teste do ditado.", "segundos": None}
    try:
        resposta = _chamar_openai(audio, mime, nome_arquivo, MODELO_PADRAO)
    except FalhaFornecedorIA:
        raise
    except requests.RequestException as e:
        raise FalhaFornecedorIA(f"Falha de rede com o fornecedor de IA ({type(e).__name__}).") from None
    except Exception as e:
        raise FalhaFornecedorIA(f"Erro inesperado no fornecedor de IA ({type(e).__name__}).") from None
    texto = resposta.get("text") if isinstance(resposta, dict) else None
    if not isinstance(texto, str):
        raise FalhaFornecedorIA("Resposta do fornecedor de IA sem texto.")
    return {"texto": texto.strip(), "segundos": _duracao(resposta)}
