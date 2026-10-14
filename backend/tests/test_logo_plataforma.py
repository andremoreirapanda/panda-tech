"""Logo da plataforma (14/10/2026): o Admin envia em Perfil da Plataforma e ele
aparece no menu do Admin, na tela de login e nas de recuperar acesso."""
import base64

import db
import plataforma_service
from factories import novo_usuario

from conftest import autenticado

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
WEBP = base64.b64encode(b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64).decode()
GIF = base64.b64encode(b"GIF89a" + b"\x00" * 64).decode()
SVG = base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>').decode()


def _admin(client):
    return autenticado(client, novo_usuario(None, "Admin", "admin@plataforma.com", "admin_master"))


def _meta(client):
    html = client.get("/").get_data(as_text=True)
    marca = '<meta name="logo-plataforma" content="'
    if marca not in html:
        return None
    return html.split(marca, 1)[1].split('"', 1)[0]


def test_sem_logo_nada_muda(client, db_ctx):
    assert _meta(client) is None
    assert client.get("/api/publico/plataforma/logo").status_code == 404


def test_admin_envia_e_logo_aparece(client, db_ctx):
    r = _admin(client).put("/api/admin/plataforma/logo", json={"logo_base64": PNG})
    assert r.status_code == 200, r.get_data(as_text=True)
    versao = r.get_json()["versao"]
    assert versao and _meta(client) == versao
    img = client.get(f"/api/publico/plataforma/logo?v={versao}")
    assert img.status_code == 200 and img.mimetype == "image/png"
    assert img.data == base64.b64decode(PNG)
    assert "max-age" in img.headers["Cache-Control"]


def test_trocar_muda_a_versao(client, db_ctx):
    c = _admin(client)
    v1 = c.put("/api/admin/plataforma/logo", json={"logo_base64": PNG}).get_json()["versao"]
    v2 = c.put("/api/admin/plataforma/logo", json={"logo_base64": WEBP}).get_json()["versao"]
    assert v1 != v2 and _meta(client) == v2
    assert client.get("/api/publico/plataforma/logo").mimetype == "image/webp"


def test_remover(client, db_ctx):
    c = _admin(client)
    c.put("/api/admin/plataforma/logo", json={"logo_base64": PNG})
    assert c.delete("/api/admin/plataforma/logo").status_code == 200
    assert _meta(client) is None and client.get("/api/publico/plataforma/logo").status_code == 404


def test_formatos_recusados(client, db_ctx):
    c = _admin(client)
    for conteudo in (GIF, SVG, "isso-nao-e-base64", "", None):
        r = c.put("/api/admin/plataforma/logo", json={"logo_base64": conteudo})
        assert r.status_code == 400, conteudo
    assert _meta(client) is None


def test_tamanho_maximo(client, db_ctx, monkeypatch):
    monkeypatch.setattr(plataforma_service, "MAX_LOGO_BYTES", 50)
    r = _admin(client).put("/api/admin/plataforma/logo", json={"logo_base64": PNG})
    assert r.status_code == 400 and "grande" in r.get_json()["erro"]


def test_so_admin_da_plataforma(client, db_ctx):
    gestor = novo_usuario(None, "Gi", "gi@x.com", "gestor")
    c = autenticado(client, gestor)
    assert c.put("/api/admin/plataforma/logo", json={"logo_base64": PNG}).status_code == 403
    assert c.delete("/api/admin/plataforma/logo").status_code == 403


def test_sem_a_tabela_a_pagina_abre(client, db_ctx):
    # Deploy antes da migração: o index.html continua saindo, só sem logo.
    db_ctx.execute("DROP TABLE plataforma_identidade")
    r = client.get("/")
    assert r.status_code == 200 and 'name="logo-plataforma"' not in r.get_data(as_text=True)
    assert client.get("/api/publico/plataforma/logo").status_code == 404


def test_migracao_cria_a_tabela_e_pode_rodar_de_novo(client, db_ctx):
    import migrar_logo_plataforma
    db_ctx.execute("DROP TABLE plataforma_identidade")
    migrar_logo_plataforma.migrar()
    migrar_logo_plataforma.migrar()
    assert _admin(client).put("/api/admin/plataforma/logo", json={"logo_base64": PNG}).status_code == 200
