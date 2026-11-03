"""
robots.txt (03/11/2026, pedido do usuário): pede aos robôs de IA que não leiam
o PandaUp. Só os robôs bem-comportados respeitam — é um pedido, não um bloqueio.
"""


def _linhas(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert r.mimetype == "text/plain"
    return r, r.get_data(as_text=True)


def _bloqueia(texto, robo):
    # O grupo do robô tem "Disallow: /" (o site inteiro).
    grupo = texto.split(f"User-agent: {robo}\n", 1)
    assert len(grupo) == 2, robo
    resto = grupo[1].split("\n\n", 1)[0]
    return "Disallow: /\n" in resto + "\n"


def test_producao_bloqueia_robos_de_ia(client, monkeypatch):
    monkeypatch.delenv("AMBIENTE", raising=False)
    _, texto = _linhas(client)
    for robo in ("GPTBot", "ClaudeBot", "anthropic-ai", "Google-Extended", "CCBot", "PerplexityBot", "Bytespider"):
        assert _bloqueia(texto, robo), robo


def test_producao_buscadores_comuns_veem_so_a_pagina_inicial(client, monkeypatch):
    monkeypatch.delenv("AMBIENTE", raising=False)
    _, texto = _linhas(client)
    geral = texto.split("User-agent: *\n", 1)[1].split("\n\n", 1)[0]
    assert "Disallow: /api/" in geral
    assert "Disallow: /\n" not in geral + "\n"


def test_homologacao_bloqueia_todo_mundo(client, monkeypatch):
    monkeypatch.setenv("AMBIENTE", "homologacao")
    r, texto = _linhas(client)
    assert "User-agent: *\nDisallow: /" in texto
    assert r.headers["X-Robots-Tag"] == "noindex, nofollow"


def test_robots_tem_cache_curto(client):
    r, _ = _linhas(client)
    assert "max-age=86400" in r.headers.get("Cache-Control", "")
