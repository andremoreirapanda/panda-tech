"""White Label completo (25/09/2026): rotas públicas da tela de login da clínica."""
import base64

import db
from factories import DuasClinicas
from modulos_service import definir_liberacao_admin

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PNG = base64.b64encode(PNG_BYTES).decode()


def _prep(com_modulo=True, **campos):
    cen = DuasClinicas()
    campos.setdefault("endereco_login", "clinica-a")
    sets = ", ".join(f"{k} = ?" for k in campos)
    db.execute(f"UPDATE organizacoes SET {sets} WHERE id = ?", (*campos.values(), cen.org_a))
    if com_modulo:
        definir_liberacao_admin(cen.org_a, "white_label", True)
    return cen


def test_dados_publicos_sem_campos_comerciais(client, db_ctx):
    _prep(app_nome="Encantar", login_mensagem="Oi!", contato_email="segredo@x.com", cnpj="12345678000199")
    r = client.get("/api/publico/clinica/clinica-a")
    assert r.status_code == 200
    d = r.get_json()
    assert d["app_nome"] == "Encantar" and d["login_mensagem"] == "Oi!" and d["nome"] == "Clínica A"
    texto = r.get_data(as_text=True)
    assert "segredo@x.com" not in texto and "12345678000199" not in texto
    for proibido in ("cnpj", "plano", "status_comercial", "contato_email", "id", "app_icone_base64"):
        assert proibido not in d, proibido


def test_endereco_nao_diferencia_maiusculas(client, db_ctx):
    _prep()
    assert client.get("/api/publico/clinica/Clinica-A").status_code == 200


def test_404_sem_modulo_ou_inexistente(client, db_ctx):
    _prep(com_modulo=False)
    assert client.get("/api/publico/clinica/clinica-a").status_code == 404
    assert client.get("/api/publico/clinica/nao-existe").status_code == 404


def test_404_cancelada_e_inativa(client, db_ctx):
    cen = _prep(status_comercial="cancelada", app_icone_base64=PNG)
    assert client.get("/api/publico/clinica/clinica-a").status_code == 404
    assert client.get("/api/publico/clinica/clinica-a/icone").status_code == 404
    db.execute("UPDATE organizacoes SET status_comercial = 'ativa', ativo = 0 WHERE id = ?", (cen.org_a,))
    assert client.get("/api/publico/clinica/clinica-a").status_code == 404
    assert client.get("/api/publico/clinica/clinica-a/icone").status_code == 404


def test_imagens_com_content_type(client, db_ctx):
    _prep(app_icone_base64=PNG, mundo_mascote_imagem=PNG, pandoo_cenario_imagem=PNG)
    for rota in ("icone", "mascote", "cenario"):
        r = client.get(f"/api/publico/clinica/clinica-a/{rota}")
        assert r.status_code == 200 and r.mimetype == "image/png" and r.data == PNG_BYTES, rota
        assert "max-age" in r.headers.get("Cache-Control", "")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_imagem_ausente_404(client, db_ctx):
    _prep()
    for rota in ("icone", "mascote", "cenario"):
        assert client.get(f"/api/publico/clinica/clinica-a/{rota}").status_code == 404


def test_manifest(client, db_ctx):
    _prep(app_nome="Encantar", app_icone_base64=PNG, cor_primaria="#112233")
    r = client.get("/api/publico/clinica/clinica-a/manifest.webmanifest")
    assert r.status_code == 200 and r.mimetype == "application/manifest+json"
    m = r.get_json(force=True)
    assert m["name"] == "Encantar" and m["short_name"] == "Encantar" and m["theme_color"] == "#112233"
    assert m["start_url"] == "/#/entrar/clinica-a" and m["display"] == "standalone"
    assert m["icons"][0]["src"].startswith("/api/publico/clinica/clinica-a/icone")
    assert m["icons"][0]["type"] == "image/png"


def test_manifest_nome_longo_encurta(client, db_ctx):
    _prep(app_nome="Clínica Encantar Terapias")
    m = client.get("/api/publico/clinica/clinica-a/manifest.webmanifest").get_json(force=True)
    assert m["name"] == "Clínica Encantar Terapias" and len(m["short_name"]) <= 12 and m["icons"] == []
