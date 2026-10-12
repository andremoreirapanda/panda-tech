"""Marca do ambiente de homologação (spec PandaUp 12/10/2026, item D)."""
META = '<meta name="ambiente" content="homologacao">'


def test_homologacao_marca_pagina_cabecalho_e_health(client, monkeypatch):
    monkeypatch.setenv("AMBIENTE", "homologacao")
    pagina = client.get("/")
    assert META in pagina.get_data(as_text=True)
    assert pagina.headers["X-Robots-Tag"] == "noindex, nofollow"
    health = client.get("/api/health")
    assert health.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert health.get_json()["ambiente"] == "homologacao"


def test_producao_nao_muda_nada(client, monkeypatch):
    monkeypatch.delenv("AMBIENTE", raising=False)
    pagina = client.get("/")
    assert 'name="ambiente"' not in pagina.get_data(as_text=True)
    assert "X-Robots-Tag" not in pagina.headers
    health = client.get("/api/health")
    assert "X-Robots-Tag" not in health.headers and health.get_json()["ambiente"] == "producao"


def test_index_html_carrega_o_script_da_faixa(client):
    assert "js/ambiente.js" in client.get("/").get_data(as_text=True)
