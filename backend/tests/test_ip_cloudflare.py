"""IP real atrás da Cloudflare (spec PandaUp 12/10/2026, item C) — desligado por padrão."""
import pytest

import rate_limit


def _ip(flask_app, remoto, cf=None):
    headers = {"CF-Connecting-IP": cf} if cf is not None else {}
    with flask_app.test_request_context(environ_base={"REMOTE_ADDR": remoto}, headers=headers):
        return rate_limit._ip_cliente()


def test_sem_a_variavel_ignora_o_cabecalho(flask_app, monkeypatch):
    monkeypatch.delenv("ENCANTO_CLOUDFLARE", raising=False)
    assert _ip(flask_app, "173.245.48.10", "200.1.2.3") == "173.245.48.10"


@pytest.mark.parametrize("remoto", ["173.245.48.10", "104.16.0.1", "2400:cb00::1"])
def test_ligada_e_vindo_da_cloudflare_usa_o_cabecalho(flask_app, monkeypatch, remoto):
    monkeypatch.setenv("ENCANTO_CLOUDFLARE", "1")
    assert _ip(flask_app, remoto, "200.1.2.3") == "200.1.2.3"


def test_ligada_mas_fora_da_cloudflare_ignora_o_cabecalho(flask_app, monkeypatch):
    monkeypatch.setenv("ENCANTO_CLOUDFLARE", "1")
    assert _ip(flask_app, "186.209.113.98", "200.1.2.3") == "186.209.113.98"


@pytest.mark.parametrize("cf", ["texto", "", "1.2.3.4, 5.6.7.8"])
def test_cabecalho_invalido_usa_remote_addr(flask_app, monkeypatch, cf):
    monkeypatch.setenv("ENCANTO_CLOUDFLARE", "1")
    assert _ip(flask_app, "173.245.48.10", cf) == "173.245.48.10"
