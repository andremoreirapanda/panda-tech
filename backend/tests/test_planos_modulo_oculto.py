"""Achado do usuário (25/09/2026): salvar o plano Pro dava "Módulo desconhecido: ia"
— o plano tem o módulo escondido (ia) gravado e a tela o reenviava."""
import db
import planos_padrao
from factories import novo_usuario
from conftest import autenticado


def _pro():
    return db.query_one("SELECT id FROM planos WHERE codigo = 'pro'")["id"]


def _modulos(pid):
    return {l["modulo_codigo"] for l in db.query("SELECT modulo_codigo FROM planos_modulos WHERE plano_id = ?", (pid,))}


def _admin():
    return novo_usuario(None, "Admin", "admin@saas.com", "admin_master")


def test_ia_nao_vem_gravado_no_plano_pro_padrao(client, db_ctx):
    # IA fase 1: o módulo deixou de ser escondido e ninguém o ganha sozinho
    planos_padrao.criar_planos_padrao_para_teste()
    assert "ia" not in _modulos(_pro())
    planos = autenticado(client, _admin()).get("/api/admin/planos").get_json()
    pro = next(p for p in planos if p["codigo"] == "pro")
    assert "ia" not in pro["modulos_efetivos"]


def test_salvar_plano_com_ia_liga_e_desliga(client, db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    admin = _admin()
    pro = next(p for p in autenticado(client, admin).get("/api/admin/planos").get_json() if p["codigo"] == "pro")
    r = autenticado(client, admin).put("/api/admin/planos/pro", json={"modulos": pro["modulos_proprios"] + ["ia"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert "ia" in _modulos(_pro())
    r = autenticado(client, admin).put("/api/admin/planos/pro", json={"modulos": ["financeiro"]})
    assert r.status_code == 200
    assert _modulos(_pro()) == {"financeiro"}


def test_codigo_realmente_desconhecido_continua_recusado(client, db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    r = autenticado(client, _admin()).put("/api/admin/planos/pro", json={"modulos": ["xyz"]})
    assert r.status_code == 400
