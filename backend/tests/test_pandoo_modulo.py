"""Pandoo (25/09/2026): módulo pago que não entra em nenhum plano — só o
Admin do SaaS libera, clínica por clínica."""
import db
from factories import DuasClinicas, novo_usuario
from conftest import autenticado
from modulos_service import modulo_ativo_para_clinica


def _admin(db_ctx):
    return novo_usuario(None, "Admin", "admin@saas.com", "admin_master")


def _ativo(org_id):
    plano = db.query_one("SELECT plano FROM organizacoes WHERE id = ?", (org_id,))["plano"]
    return modulo_ativo_para_clinica(org_id, plano, "pandoo")


def test_pandoo_comeca_desligado_em_qualquer_plano(db_ctx):
    cen = DuasClinicas()
    for plano in ("starter", "pro", "enterprise", "premium"):
        db.execute("UPDATE organizacoes SET plano = ? WHERE id = ?", (plano, cen.org_a))
        assert not _ativo(cen.org_a), plano


def test_admin_libera_e_desliga(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, _admin(db_ctx))
    r = c.put(f"/api/admin/clinicas/{cen.org_a}/modulos/pandoo", json={"liberado": True})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert _ativo(cen.org_a) and not _ativo(cen.org_b)
    c.put(f"/api/admin/clinicas/{cen.org_a}/modulos/pandoo", json={"liberado": False})
    assert not _ativo(cen.org_a)


def test_liberacao_vale_mesmo_trocando_de_plano(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, _admin(db_ctx)).put(f"/api/admin/clinicas/{cen.org_a}/modulos/pandoo", json={"liberado": True})
    db.execute("UPDATE organizacoes SET plano = 'starter' WHERE id = ?", (cen.org_a,))
    assert _ativo(cen.org_a)


def test_gestor_nao_liga_sozinho(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/modulos/pandoo/toggle")
    assert r.status_code == 403
    assert not _ativo(cen.org_a)
    r = autenticado(client, cen.gestor_a).put(f"/api/admin/clinicas/{cen.org_a}/modulos/pandoo", json={"liberado": True})
    assert r.status_code == 403


def test_admin_libera_qualquer_modulo_opcional_como_extra(client, db_ctx):
    # Planos configuráveis (25/09/2026): extras valem para qualquer módulo opcional.
    cen = DuasClinicas()
    c = autenticado(client, _admin(db_ctx))
    assert c.put(f"/api/admin/clinicas/{cen.org_a}/modulos/financeiro", json={"liberado": True}).status_code == 200
    assert c.put(f"/api/admin/clinicas/{cen.org_a}/modulos/inexistente", json={"liberado": True}).status_code == 400


def test_listagens_mostram_o_estado(client, db_ctx):
    cen = DuasClinicas()
    admin = _admin(db_ctx)
    autenticado(client, admin).put(f"/api/admin/clinicas/{cen.org_a}/modulos/pandoo", json={"liberado": True})
    clinicas = autenticado(client, admin).get("/api/admin/clinicas").get_json()
    a = next(c for c in clinicas if c["id"] == cen.org_a)
    assert a["modulos"]["extras"] == ["pandoo"]
    mods = autenticado(client, cen.gestor_a).get("/api/modulos").get_json()
    pandoo = next(m for m in mods if m["codigo"] == "pandoo")
    assert pandoo["habilitado"] is True and pandoo["origem"] == "extra"
