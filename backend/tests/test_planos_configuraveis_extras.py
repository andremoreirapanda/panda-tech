"""Planos configuráveis (25/09/2026): módulos extras por clínica."""
import db
import planos_padrao
from factories import DuasClinicas, novo_usuario
from conftest import autenticado


def _prep(client):
    planos_padrao.criar_planos_padrao_para_teste()
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    admin = autenticado(client, novo_usuario(None, "Admin", "admin@saas.com", "admin_master"))
    return cen, admin


def test_admin_libera_extra_e_lista_mostra(client, db_ctx):
    cen, admin = _prep(client)
    assert admin.put(f"/api/admin/clinicas/{cen.org_a}/modulos/white_label", json={"liberado": True}).status_code == 200
    a = next(c for c in admin.get("/api/admin/clinicas").get_json() if c["id"] == cen.org_a)
    assert "white_label" in a["modulos"]["extras"] and "financeiro" in a["modulos"]["do_plano"]
    assert "limite_pacientes" not in a and "uso_pacientes_pct" not in a and "modulos_so_admin" not in a


def test_modulo_do_plano_nao_vira_extra(client, db_ctx):
    cen, admin = _prep(client)
    r = admin.put(f"/api/admin/clinicas/{cen.org_a}/modulos/financeiro", json={"liberado": True})
    assert r.status_code == 400 and "plano" in r.get_json()["erro"]


def test_gestor_ve_origem_e_nao_desliga_extra(client, db_ctx):
    cen, admin = _prep(client)
    admin.put(f"/api/admin/clinicas/{cen.org_a}/modulos/white_label", json={"liberado": True})
    g = autenticado(client, cen.gestor_a)
    mods = {m["codigo"]: m for m in g.get("/api/modulos").get_json()}
    assert mods["white_label"]["origem"] == "extra" and mods["financeiro"]["origem"] == "plano"
    assert mods["pandoo"]["origem"] is None
    assert g.post("/api/modulos/white_label/toggle").status_code == 403
    assert g.post("/api/modulos/ia/toggle").status_code == 200  # módulo do plano: pode desligar


def test_desligar_extra_tira_acesso_na_hora(client, db_ctx):
    # autenticado() troca o login do MESMO test_client: reautentica antes de cada chamada.
    cen, _ = _prep(client)
    admin_user = db.query_one("SELECT * FROM usuarios WHERE papel = 'admin_master'")
    autenticado(client, admin_user).put(f"/api/admin/clinicas/{cen.org_a}/modulos/pandoo", json={"liberado": True})
    me = autenticado(client, cen.gestor_a).get("/api/auth/me").get_json()
    assert "pandoo" in me["organizacao"]["modulos_habilitados"]
    autenticado(client, admin_user).put(f"/api/admin/clinicas/{cen.org_a}/modulos/pandoo", json={"liberado": False})
    me = autenticado(client, cen.gestor_a).get("/api/auth/me").get_json()
    assert "pandoo" not in me["organizacao"]["modulos_habilitados"]
