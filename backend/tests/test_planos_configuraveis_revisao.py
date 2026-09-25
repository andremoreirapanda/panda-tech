"""Planos configuráveis (25/09/2026) — achados da revisão final."""
import db
import planos_padrao
from factories import DuasClinicas, novo_usuario
from conftest import autenticado
from modulos_service import modulo_ativo_para_clinica


def _prep(client):
    planos_padrao.criar_planos_padrao_para_teste()
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET plano = 'starter' WHERE id = ?", (cen.org_a,))
    admin = novo_usuario(None, "Admin", "admin@saas.com", "admin_master")
    return cen, admin


def _put_admin(client, admin, rota, corpo):
    return autenticado(client, admin).put(rota, json=corpo)


# ---- I-1: extra e plano não podem se contaminar

def test_extra_nao_volta_sozinho_depois_de_ir_e_voltar_de_plano(client, db_ctx):
    cen, admin = _prep(client)
    _put_admin(client, admin, f"/api/admin/clinicas/{cen.org_a}/modulos/integracoes", {"liberado": True})
    assert _put_admin(client, admin, f"/api/admin/clinicas/{cen.org_a}/plano", {"plano": "pro"}).status_code == 200
    assert _put_admin(client, admin, f"/api/admin/clinicas/{cen.org_a}/plano", {"plano": "starter"}).status_code == 200
    assert not modulo_ativo_para_clinica(cen.org_a, "starter", "integracoes")


def test_extra_removido_nao_desliga_modulo_que_vem_do_plano(client, db_ctx):
    cen, admin = _prep(client)
    _put_admin(client, admin, f"/api/admin/clinicas/{cen.org_a}/modulos/financeiro", {"liberado": True})
    _put_admin(client, admin, f"/api/admin/clinicas/{cen.org_a}/modulos/financeiro", {"liberado": False})
    _put_admin(client, admin, f"/api/admin/clinicas/{cen.org_a}/plano", {"plano": "pro"})
    assert modulo_ativo_para_clinica(cen.org_a, "pro", "financeiro")


def test_remover_extra_de_modulo_que_ja_vem_do_plano_so_limpa_o_extra(client, db_ctx):
    cen, admin = _prep(client)
    _put_admin(client, admin, f"/api/admin/clinicas/{cen.org_a}/modulos/integracoes", {"liberado": True})
    db.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))  # mudança direta, sem a rota
    r = _put_admin(client, admin, f"/api/admin/clinicas/{cen.org_a}/modulos/integracoes", {"liberado": False})
    assert r.status_code == 200
    assert db.query_one("SELECT liberado_admin FROM modulos_clinica WHERE organizacao_id = ? AND modulo_codigo = 'integracoes'",
                        (cen.org_a,))["liberado_admin"] == 0
    assert modulo_ativo_para_clinica(cen.org_a, "pro", "integracoes")


# ---- I-2: gestor não vê dados da plataforma na lista de planos

def test_gestor_nao_ve_dados_da_plataforma_nos_planos(client, db_ctx):
    cen, _ = _prep(client)
    planos = autenticado(client, cen.gestor_a).get("/api/admin/planos").get_json()
    assert planos and all("total_clinicas" not in p and "modulos_herdados" not in p for p in planos)


# ---- Validações da definição do plano

def test_validacoes_da_definicao_do_plano(client, db_ctx):
    _, admin = _prep(client)
    c = autenticado(client, admin)
    pro_id = db.query_one("SELECT id FROM planos WHERE codigo = 'pro'")["id"]
    assert c.put("/api/admin/planos/pro", json={"plano_base_id": str(pro_id)}).status_code == 400  # base = ele mesmo, como texto
    assert c.put("/api/admin/planos/pro", json={"plano_base_id": "abc"}).status_code == 400
    assert c.put("/api/admin/planos/pro", json={"recursos": "abc"}).status_code == 400
    assert c.put("/api/admin/planos/pro", json={"disponivel_ate": "20260101"}).status_code == 400
    assert c.put("/api/admin/planos/pro", json={"cor": "red;background:url(x)"}).status_code == 400
    assert c.post("/api/admin/planos", json={"nome": "x" * 81, "preco_mensal_centavos": 0}).status_code == 400
    assert db.query_one("SELECT plano_base_id FROM planos WHERE id = ?", (pro_id,))["plano_base_id"] is None
