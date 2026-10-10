"""Versão nos endereços do front-end (cache do celular, 09/10/2026)."""
import re

import versao_front


def test_calcula_impressao_por_arquivo(tmp_path):
    (tmp_path / "js").mkdir()
    (tmp_path / "css").mkdir()
    (tmp_path / "js" / "a.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "css" / "b.css").write_text("body{}", encoding="utf-8")
    v1 = versao_front.calcular_versoes(str(tmp_path))
    assert set(v1["arquivos"]) == {"/js/a.js", "/css/b.css"}
    (tmp_path / "js" / "a.js").write_text("console.log(2)", encoding="utf-8")
    v2 = versao_front.calcular_versoes(str(tmp_path))
    assert v2["arquivos"]["/js/a.js"] != v1["arquivos"]["/js/a.js"]
    assert v2["arquivos"]["/css/b.css"] == v1["arquivos"]["/css/b.css"]
    assert v2["geral"] != v1["geral"]


def test_index_ganha_versao_em_scripts_e_css():
    versoes = {"arquivos": {"/js/a.js": "aaaa1111", "/css/b.css": "bbbb2222"}, "geral": "cafe1234"}
    html = """<head><link rel="stylesheet" href="/css/b.css" />
<link href="https://fonts.googleapis.com/css2?family=Inter" rel="stylesheet">
</head><body><script src="/js/a.js"></script><script src="/js/sem-hash.js"></script></body>"""
    saida = versao_front.index_versionado(html, versoes)
    assert 'href="/css/b.css?v=bbbb2222"' in saida
    assert 'src="/js/a.js?v=aaaa1111"' in saida
    assert 'src="/js/sem-hash.js"' in saida                       # arquivo desconhecido: fica igual
    assert "fonts.googleapis.com/css2?family=Inter" in saida      # externo: intocado
    assert '<meta name="versao-app" content="cafe1234">' in saida


def test_rotas_servem_index_versionado_sem_cache(client):
    for caminho in ("/", "/qualquer/rota-da-spa"):
        r = client.get(caminho)
        html = r.get_data(as_text=True)
        assert r.status_code == 200
        assert "no-cache" in r.headers.get("Cache-Control", "")
        assert re.search(r'src="/js/api\.js\?v=[0-9a-f]{10}"', html)
        assert re.search(r'href="/css/components\.css\?v=[0-9a-f]{10}"', html)
        assert re.search(r'<meta name="versao-app" content="[0-9a-f]{10}">', html)


def test_api_versao(client):
    r = client.get("/api/versao")
    assert r.status_code == 200 and re.fullmatch(r"[0-9a-f]{10}", r.get_json()["versao"])
    assert "no-store" in r.headers.get("Cache-Control", "")
    html = client.get("/").get_data(as_text=True)
    assert f'content="{r.get_json()["versao"]}"' in html
