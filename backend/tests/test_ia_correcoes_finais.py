"""IA fase 1: correções da revisão final (áudio só na memória, nome/tipo pelo conteúdo,
segundos restantes, falha no registro de uso, limite por usuário, evento de falha)."""
import io
import json
import os
import tempfile

import pytest
import werkzeug.formparser

import db
import ia_service
from conftest import autenticado
from factories import novo_usuario
from test_ia_ditado import AUDIO, _post, cenario  # noqa: F401  (fixture)

_CHAMAR_ORIGINAL = ia_service._chamar_openai  # a fixture troca por um falso; aqui o requests.post é o falso


def _proibir_disco(monkeypatch):
    def nao(*a, **k):
        raise AssertionError("o áudio do ditado não pode ir para o disco")
    monkeypatch.setattr(werkzeug.formparser, "SpooledTemporaryFile", nao)
    monkeypatch.setattr(tempfile, "SpooledTemporaryFile", nao)
    monkeypatch.setattr(tempfile, "TemporaryFile", nao)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", nao)


# ---------- 1. áudio só na memória e tamanho barrado antes de ler ----------

def test_audio_acima_de_500kb_fica_na_memoria(client, cenario, monkeypatch):
    _proibir_disco(monkeypatch)
    r = _post(client, cenario.prof_a1, audio=b"\x1a\x45\xdf\xa3" + b"0" * (700 * 1024), duracao="60")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["texto"] == "Paciente evoluiu bem."


def test_corpo_grande_demais_barrado_sem_ler_o_formulario(client, cenario, monkeypatch):
    def nao_ler(*a, **k):
        raise AssertionError("não deveria ler o formulário")
    monkeypatch.setattr(werkzeug.formparser.FormDataParser, "parse", nao_ler)
    r = _post(client, cenario.prof_a1, audio=b"\x1a\x45\xdf\xa3" + b"0" * (16 * 1024 * 1024))
    assert r.status_code == 400 and r.get_json()["codigo"] == "audio_invalido"
    assert cenario.chamadas == []


def test_outras_rotas_continuam_com_o_padrao(client, cenario):
    """A troca do fluxo de arquivo só vale para o ditado."""
    from app import PedidoPandaUp
    from flask import request
    with client.application.test_request_context("/api/diario/1/anexo", method="POST"):
        assert not isinstance(request._get_file_stream(10 * 1024 * 1024, "audio/webm"), io.BytesIO)
    with client.application.test_request_context("/api/ia/ditado", method="POST"):
        assert isinstance(request._get_current_object(), PedidoPandaUp)
        assert isinstance(request._get_file_stream(10 * 1024 * 1024, "audio/webm"), io.BytesIO)


# ---------- 2. nome e tipo pelo conteúdo ----------

@pytest.mark.parametrize("audio,nome,mime", [
    (b"\x00\x00\x00\x20ftypM4A " + b"0" * 500, "ditado.mp4", "audio/mp4"),
    (b"OggS" + b"0" * 500, "ditado.ogg", "audio/ogg"),
    (b"\x1a\x45\xdf\xa3" + b"0" * 500, "ditado.webm", "audio/webm"),
    (b"ID3" + b"0" * 500, "ditado.mp3", "audio/mpeg"),
    (b"\xff\xfb" + b"0" * 500, "ditado.mp3", "audio/mpeg"),
    (b"RIFF\x00\x00\x00\x00WAVE" + b"0" * 500, "ditado.wav", "audio/wav"),
], ids=["mp4", "ogg", "webm", "mp3_id3", "mp3_sync", "wav"])
def test_nome_e_tipo_pelo_conteudo(client, cenario, monkeypatch, audio, nome, mime):
    recebido = {}

    def falso(audio_, mime_, nome_, modelo):
        recebido.update(mime=mime_, nome=nome_)
        return {"text": "ok"}
    monkeypatch.setattr(ia_service, "_chamar_openai", falso)
    r = _post(client, cenario.prof_a1, audio=audio)  # o cliente diz "audio/webm"
    assert r.status_code == 200
    assert recebido == {"mime": mime, "nome": nome}


# ---------- 3 e 8. config com segundos restantes e o mês ----------

def test_config_traz_segundos_restantes_e_mes(client, cenario):
    db.execute("INSERT INTO ia_uso (organizacao_id, recurso, mes, segundos, sucesso) VALUES (?, 'ditado', ?, 75, 1)",
               (cenario.org_a, ia_service.mes_atual()))
    c = autenticado(client, cenario.prof_a1).get("/api/ia/ditado/config").get_json()
    assert c["segundos_restantes"] == 525
    assert c["mes"] == ia_service.mes_atual()


def test_config_sem_migracao_traz_segundos_e_mes(client, cenario):
    db.execute("DROP TABLE ia_uso")
    c = autenticado(client, cenario.prof_a1).get("/api/ia/ditado/config").get_json()
    assert c["segundos_restantes"] == 0 and c["mes"] == ia_service.mes_atual()


# ---------- 4. criado_em em texto na migração ----------

def test_migracao_usa_texto_no_criado_em():
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "migracoes", "migracao_ia_ditado.sql")
    sql = open(caminho, encoding="utf-8").read()
    assert "TIMESTAMP" not in sql.upper()
    assert sql.count("criado_em                 TEXT DEFAULT (to_char(") == 1
    assert sql.count("criado_em         TEXT DEFAULT (to_char(") == 1


# ---------- 5. falha ao registrar o uso não perde o texto ----------

def test_falha_ao_registrar_uso_ainda_devolve_o_texto(client, cenario, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("banco caiu")
    monkeypatch.setattr(ia_service, "registrar_uso", quebra)
    r = _post(client, cenario.prof_a1)
    assert r.status_code == 200 and r.get_json()["texto"] == "Paciente evoluiu bem."


def test_falha_ao_registrar_uso_na_falha_do_fornecedor_continua_502(client, cenario, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("banco caiu")

    def fornecedor(*a, **k):
        raise ia_service.FalhaFornecedorIA("x")
    monkeypatch.setattr(ia_service, "registrar_uso", quebra)
    monkeypatch.setattr(ia_service, "_chamar_openai", fornecedor)
    r = _post(client, cenario.prof_a1)
    assert r.status_code == 502 and r.get_json()["codigo"] == "falha_transcricao"


# ---------- 6. limite por usuário, não por IP ----------

def test_limite_e_por_usuario(client, cenario):
    for _ in range(30):
        assert _post(client, cenario.prof_a1, audio=None).status_code == 400
    assert _post(client, cenario.prof_a1, audio=None).status_code == 429
    # outro profissional da mesma clínica (mesmo IP) continua ditando
    assert _post(client, cenario.gestor_a).status_code == 200


# ---------- 7. causa da falha do fornecedor nos eventos ----------

def test_falha_do_fornecedor_vira_evento_sem_conteudo(client, cenario, monkeypatch):
    class R:
        status_code = 503
        text = "segredo Paciente evoluiu"

        def json(self):
            return {}
    monkeypatch.setattr(ia_service, "_chamar_openai", _CHAMAR_ORIGINAL)
    monkeypatch.setattr(ia_service.requests, "post", lambda *a, **k: R())
    r = _post(client, cenario.prof_a1)
    assert r.status_code == 502
    ev = db.query("SELECT * FROM eventos WHERE tipo = 'ia_falhou'")
    assert len(ev) == 1
    payload = json.loads(ev[0]["payload_json"])
    assert payload == {"causa": "HTTP 503"}
    assert ev[0]["organizacao_id"] == cenario.org_a
    assert "sk-teste" not in ev[0]["payload_json"] and "evoluiu" not in ev[0]["payload_json"]


def test_falha_de_rede_vira_evento_com_a_classe(client, cenario, monkeypatch):
    import requests

    def post(*a, **k):
        raise requests.ConnectionError("sk-teste e texto")
    monkeypatch.setattr(ia_service, "_chamar_openai", _CHAMAR_ORIGINAL)
    monkeypatch.setattr(ia_service.requests, "post", post)
    assert _post(client, cenario.prof_a1).status_code == 502
    ev = db.query_one("SELECT payload_json FROM eventos WHERE tipo = 'ia_falhou'")
    assert json.loads(ev["payload_json"]) == {"causa": "ConnectionError"}



def test_ditado_devolve_segundos_restantes(client, cenario):
    d = _post(client, cenario.prof_a1).get_json()
    assert d["segundos_restantes"] == 593 and d["minutos_restantes"] == 9


def test_audio_que_passa_do_resto_diz_os_segundos(client, cenario):
    db.execute("INSERT INTO ia_uso (organizacao_id, recurso, mes, segundos, sucesso) VALUES (?, 'ditado', ?, 560, 1)",
               (cenario.org_a, ia_service.mes_atual()))
    r = _post(client, cenario.prof_a1, duracao="60")
    assert r.status_code == 409 and "(40 s)" in r.get_json()["erro"]
    assert cenario.chamadas == []
