"""IA fase 1: cota, uso e transcrição (ia_service)."""
import pytest
import requests

import db
import ia_service


def _org():
    return db.execute("INSERT INTO organizacoes (nome) VALUES ('Clínica IA')")


def _plano(codigo, minutos=None, base=None):
    return db.execute(
        "INSERT INTO planos (codigo, nome, preco_mensal_centavos, ia_minutos_mes, plano_base_id) VALUES (?, ?, 0, ?, ?)",
        (codigo, codigo, minutos, base))


def _uso(org, segundos, sucesso=1, mes="2026-11"):
    db.execute("INSERT INTO ia_uso (organizacao_id, recurso, mes, segundos, sucesso) VALUES (?, 'ditado', ?, ?, ?)",
               (org, mes, segundos, sucesso))


def test_minutos_do_plano_herda_da_base(db_ctx):
    base = _plano("base_ia", 300)
    _plano("filho_ia", None, base)
    _plano("zero_ia", 0, base)
    _plano("vazio_ia", None)
    assert ia_service.minutos_do_plano("filho_ia") == 300
    assert ia_service.minutos_do_plano("zero_ia") == 0
    assert ia_service.minutos_do_plano("vazio_ia") == 0
    assert ia_service.minutos_do_plano("nao_existe") == 0


def test_cota_soma_creditos_do_mes_e_ignora_outros_meses(db_ctx):
    org = _org()
    _plano("p100", 100)
    for mes, minutos in (("2026-11", 50), ("2026-10", 999)):
        db.execute("INSERT INTO ia_creditos (organizacao_id, mes, minutos) VALUES (?, ?, ?)", (org, mes, minutos))
    assert ia_service.cota_do_mes(org, "p100", "2026-11")["minutos_cota"] == 150


def test_cota_usados_so_sucesso(db_ctx):
    org = _org()
    _plano("p10", 10)
    _uso(org, 90)
    _uso(org, 600, sucesso=0)
    _uso(org, 500, mes="2026-10")
    c = ia_service.cota_do_mes(org, "p10", "2026-11")
    assert c["segundos_usados"] == 90 and c["minutos_usados"] == 2
    assert c["segundos_restantes"] == 600 - 90 and c["minutos_restantes"] == 8


def test_restante_nunca_negativo(db_ctx):
    org = _org()
    _plano("p1", 1)
    _uso(org, 120)
    c = ia_service.cota_do_mes(org, "p1", "2026-11")
    assert c["segundos_restantes"] == 0 and c["minutos_restantes"] == 0


def test_segundos_cobrados():
    f = ia_service.segundos_cobrados
    assert f(12.3, 5, 10_000) == 13
    assert f(None, 40, 100_000) == 40
    assert f(None, 5, 3_000_000) == 188
    assert f(None, 900, 1000) == 300
    assert f(None, 0, 10) == 1
    assert f(900.0, 5, 10) == 300


def test_transcrever_usa_fornecedor_e_devolve_texto(monkeypatch):
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    monkeypatch.setattr(ia_service, "_chamar_openai", lambda *a: {"text": " olá ", "duration": 4.2})
    assert ia_service.transcrever(b"x", "audio/webm", "a.webm") == {"texto": "olá", "segundos": 4.2}


def test_transcrever_le_usage_por_duracao_ou_tokens(monkeypatch):
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    resp = {"text": "oi", "usage": {"type": "duration", "seconds": 7}}
    monkeypatch.setattr(ia_service, "_chamar_openai", lambda *a: resp)
    assert ia_service.transcrever(b"x", "audio/webm", "a.webm")["segundos"] == 7.0
    # formato real do gpt-transcribe: usage por tokens, sem duração -> None (cobra pelo navegador)
    resp2 = {"text": "oi", "usage": {"type": "tokens", "input_tokens": 14, "output_tokens": 45, "total_tokens": 59},
             "languages": [{"code": "pt"}]}
    monkeypatch.setattr(ia_service, "_chamar_openai", lambda *a: resp2)
    assert ia_service.transcrever(b"x", "audio/webm", "a.webm") == {"texto": "oi", "segundos": None}


def test_transcrever_erro_vira_falha(monkeypatch):
    monkeypatch.delenv("FLASK_DEBUG", raising=False)

    def boom(*a):
        raise requests.Timeout("segredo sk-123 texto clinico")
    monkeypatch.setattr(ia_service, "_chamar_openai", boom)
    with pytest.raises(ia_service.FalhaFornecedorIA) as e:
        ia_service.transcrever(b"x", "audio/webm", "a.webm")
    assert "sk-123" not in str(e.value) and "clinico" not in str(e.value)


def test_transcrever_resposta_invalida_vira_falha(monkeypatch):
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    monkeypatch.setattr(ia_service, "_chamar_openai", lambda *a: {"sem": "texto"})
    with pytest.raises(ia_service.FalhaFornecedorIA):
        ia_service.transcrever(b"x", "audio/webm", "a.webm")


def test_chamar_openai_http_erro_sem_vazar_chave(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-segredo")

    class R:
        status_code = 401
        text = "Incorrect API key sk-segredo"

        def json(self):
            return {}
    monkeypatch.setattr(ia_service.requests, "post", lambda *a, **k: R())
    with pytest.raises(ia_service.FalhaFornecedorIA) as e:
        ia_service._chamar_openai(b"x", "audio/webm", "a.webm", "gpt-transcribe")
    assert "sk-segredo" not in str(e.value)


def test_chamar_openai_monta_pedido(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-segredo")
    visto = {}

    class R:
        status_code = 200

        def json(self):
            return {"text": "ok"}

    def post(url, headers=None, data=None, files=None, timeout=None):
        visto.update(url=url, headers=headers, data=data, files=files, timeout=timeout)
        return R()
    monkeypatch.setattr(ia_service.requests, "post", post)
    assert ia_service._chamar_openai(b"abc", "audio/webm", "a.webm", "whisper-1") == {"text": "ok"}
    assert visto["url"].endswith("/v1/audio/transcriptions")
    assert visto["headers"]["Authorization"] == "Bearer sk-segredo"
    assert visto["data"]["language"] == "pt" and visto["data"]["prompt"] == ia_service.VOCABULARIO_CLINICO
    assert visto["data"]["model"] == "whisper-1" and visto["data"]["response_format"] == "verbose_json"
    assert visto["timeout"] == 90
    visto.clear()
    ia_service._chamar_openai(b"abc", "audio/webm", "a.webm", "gpt-transcribe")
    assert "response_format" not in visto["data"]


def test_provedor_falso_so_com_debug(monkeypatch):
    def nao_chamar(*a):
        raise AssertionError("rede")
    monkeypatch.setattr(ia_service, "_chamar_openai", nao_chamar)
    monkeypatch.setenv("IA_FAKE", "1")
    monkeypatch.setenv("FLASK_DEBUG", "1")
    assert ia_service.transcrever(b"x", "audio/webm", "a.webm") == {"texto": "Texto de teste do ditado.", "segundos": None}
    monkeypatch.delenv("FLASK_DEBUG")
    with pytest.raises(ia_service.FalhaFornecedorIA):  # tentou a rede (o AssertionError vira falha)
        ia_service.transcrever(b"x", "audio/webm", "a.webm")


def test_registrar_uso_grava_mes_e_custo_sem_conteudo(db_ctx):
    org = _org()
    ia_service.registrar_uso(org, None, "ditado", 60, "gpt-transcribe", True)
    ia_service.registrar_uso(org, None, "ditado", 0, "gpt-transcribe", False)
    ok, falha = db.query("SELECT * FROM ia_uso ORDER BY id")
    assert ok["mes"] == ia_service.mes_atual() and ok["sucesso"] == 1 and ok["custo_estimado_micro_usd"] > 0
    assert falha["sucesso"] == 0 and falha["segundos"] == 0
    assert not {c for c in ok.keys() if c in ("texto", "audio")}


def test_tabelas_existem_e_chave(db_ctx, monkeypatch):
    ia_service._tabelas_ok[0] = False
    assert ia_service.tabelas_existem() is True
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert ia_service.chave_configurada() is False
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert ia_service.chave_configurada() is True
