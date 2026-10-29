"""
App instalável (29/10/2026): o PandaUp pode ir para a tela inicial do celular
(Android e iPhone) com nome, ícone do panda e tela cheia — manifest e ícones
servidos pelo próprio app, sem depender de arquivo estático no servidor.
"""
import json


def test_manifest_do_pandaup(client):
    r = client.get("/api/publico/app/manifest.webmanifest")
    assert r.status_code == 200
    assert r.mimetype == "application/manifest+json"
    m = json.loads(r.get_data(as_text=True))
    assert m["name"] == "PandaUp" and m["short_name"] == "PandaUp"
    assert m["display"] == "standalone"
    assert m["start_url"] == "/" and m["scope"] == "/"
    assert m["theme_color"] == "#5B4FE9"
    tamanhos = {(i["sizes"], i.get("purpose", "any")) for i in m["icons"]}
    assert ("192x192", "any") in tamanhos and ("512x512", "any") in tamanhos
    assert ("512x512", "maskable") in tamanhos


def test_icones_do_manifest_existem(client):
    m = client.get("/api/publico/app/manifest.webmanifest").get_json(force=True)
    for icone in m["icons"]:
        r = client.get(icone["src"])
        assert r.status_code == 200, icone["src"]
        assert r.mimetype == "image/png"
        assert r.data[:8] == b"\x89PNG\r\n\x1a\n"
        assert "max-age" in r.headers.get("Cache-Control", "")


def test_icone_desconhecido_404(client):
    assert client.get("/api/publico/app/../app.py").status_code == 404
    assert client.get("/api/publico/app/nao-existe.png").status_code == 404


def test_index_aponta_para_manifest_e_icone_do_iphone(client):
    html = client.get("/").get_data(as_text=True)
    assert '<link rel="manifest" href="/api/publico/app/manifest.webmanifest"' in html
    assert '<link rel="apple-touch-icon" href="/api/publico/app/icone-apple-180.png"' in html
    assert '<meta name="theme-color" content="#5B4FE9"' in html
    assert '<meta name="apple-mobile-web-app-capable" content="yes"' in html
    assert client.get("/api/publico/app/icone-apple-180.png").status_code == 200
