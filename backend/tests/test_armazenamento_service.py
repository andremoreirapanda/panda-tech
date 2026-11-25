"""armazenamento_service com a API do Supabase Storage simulada (sem rede)."""
import pytest
import requests

import armazenamento_service as arm


class Resp:
    def __init__(self, status=200, json=None, headers=None, corpo=b"", text=""):
        self.status_code, self._json, self.headers, self._corpo, self.text = status, json, headers or {}, corpo, text
        self.ok = 200 <= status < 300

    def json(self):
        return self._json

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._corpo), chunk_size):
            yield self._corpo[i:i + chunk_size]

    def close(self):
        pass


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co/")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "segredo")
    monkeypatch.delenv("DIARIO_ANEXO_BUCKET", raising=False)
    chamadas, respostas = [], []

    def falso(metodo, url, headers=None, timeout=None, **kw):
        chamadas.append({"metodo": metodo, "url": url, "headers": headers, **kw})
        return respostas.pop(0)
    monkeypatch.setattr(requests, "request", falso)
    return chamadas, respostas


def test_link_de_envio_absoluto_com_chave_nos_cabecalhos(http):
    chamadas, respostas = http
    respostas.append(Resp(json={"url": "/object/upload/sign/diario-anexos/clinica-1/diario-2/a b.mp4?token=x"}))
    url = arm.criar_link_envio("clinica-1/diario-2/a b.mp4")
    assert url == "https://proj.supabase.co/storage/v1/object/upload/sign/diario-anexos/clinica-1/diario-2/a b.mp4?token=x"
    assert chamadas[0]["url"] == "https://proj.supabase.co/storage/v1/object/upload/sign/diario-anexos/clinica-1/diario-2/a%20b.mp4"
    assert chamadas[0]["headers"]["apikey"] == "segredo"


def test_cria_o_bucket_privado_quando_nao_existe(http):
    chamadas, respostas = http
    respostas += [Resp(400, text='{"statusCode":"404","error":"Bucket not found"}'), Resp(200, json={"name": "diario-anexos"}),
                  Resp(json={"url": "/object/upload/sign/diario-anexos/x.mp4?token=y"})]
    assert arm.criar_link_envio("x.mp4").endswith("?token=y")
    assert chamadas[1]["url"].endswith("/storage/v1/bucket")
    assert chamadas[1]["json"] == {"id": "diario-anexos", "name": "diario-anexos", "public": False}


def test_ler_inicio_pelo_content_range(http):
    chamadas, respostas = http
    respostas.append(Resp(206, headers={"Content-Range": "bytes 0-63/31457280"}, corpo=b"A" * 64))
    inicio, total = arm.ler_inicio("x.mp4")
    assert total == 31457280 and inicio == b"A" * 64
    assert chamadas[0]["headers"]["Range"] == "bytes=0-63"
    assert chamadas[0]["url"].endswith("/object/authenticated/diario-anexos/x.mp4")


def test_ler_inicio_sem_range_e_arquivo_inexistente(http):
    _, respostas = http
    respostas += [Resp(200, headers={"Content-Length": "10"}, corpo=b"0123456789"), Resp(400, text="Object not found")]
    assert arm.ler_inicio("x.mp4") == (b"0123456789", 10)
    assert arm.ler_inicio("y.mp4") is None


def test_link_de_leitura(http):
    chamadas, respostas = http
    respostas.append(Resp(json={"signedURL": "/object/sign/diario-anexos/x.mp4?token=z"}))
    assert arm.criar_link_leitura("x.mp4") == "https://proj.supabase.co/storage/v1/object/sign/diario-anexos/x.mp4?token=z"
    assert chamadas[0]["json"] == {"expiresIn": 3600}


def test_apagar_nunca_levanta_excecao(http, monkeypatch):
    chamadas, respostas = http
    respostas.append(Resp(200, json=[]))
    assert arm.apagar("x.mp4") is True
    assert chamadas[0]["metodo"] == "DELETE" and chamadas[0]["json"] == {"prefixes": ["x.mp4"]}

    def cai(*a, **k):
        raise requests.ConnectionError("fora")
    monkeypatch.setattr(requests, "request", cai)
    assert arm.apagar("x.mp4") is False


def test_fora_do_ar_vira_erro_amigavel_sem_a_chave(http, monkeypatch):
    def cai(*a, **k):
        raise requests.ConnectionError("https://proj.supabase.co segredo")
    monkeypatch.setattr(requests, "request", cai)
    with pytest.raises(arm.ErroArmazenamento) as e:
        arm.criar_link_envio("x.mp4")
    assert "segredo" not in str(e.value) and "não respondeu" in str(e.value)


def test_origem_para_a_csp(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co/")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    assert arm.origem() == "https://proj.supabase.co"
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co; script-src *")
    assert arm.origem() is None
    monkeypatch.delenv("SUPABASE_SERVICE_KEY")
    assert arm.origem() is None
