"""Planos configuráveis (25/09/2026): API do Admin."""
from datetime import date, timedelta

import db
import planos_padrao
from factories import DuasClinicas, novo_usuario
from conftest import autenticado


def _admin():
    return novo_usuario(None, "Admin", "admin@saas.com", "admin_master")


def _c(client):
    return autenticado(client, _admin())


def test_criar_plano_a_partir_de_outro(client, db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    c = _c(client)
    pro = db.query_one("SELECT id FROM planos WHERE codigo = 'pro'")["id"]
    r = c.post("/api/admin/planos", json={"nome": "Promoção Primavera", "preco_mensal_centavos": 9900,
                                          "plano_base_id": pro, "modulos": ["pandoo"], "disponivel_ate": "2099-12-31"})
    assert r.status_code == 201, r.get_data(as_text=True)
    codigo = r.get_json()["codigo"]
    assert codigo == "promocao-primavera"
    p = next(x for x in c.get("/api/admin/planos").get_json() if x["codigo"] == codigo)
    assert p["modulos_proprios"] == ["pandoo"]
    assert "financeiro" in p["modulos_herdados"] and "pandoo" in p["modulos_efetivos"]
    assert p["plano_base_nome"] == "Pro" and p["promocao_encerrada"] is False


def test_codigo_unico_e_nome_obrigatorio(client, db_ctx):
    c = _c(client)
    assert c.post("/api/admin/planos", json={"nome": "Básico", "preco_mensal_centavos": 0}).get_json()["codigo"] == "basico"
    assert c.post("/api/admin/planos", json={"nome": "Basico", "preco_mensal_centavos": 0}).get_json()["codigo"] == "basico-2"
    assert c.post("/api/admin/planos", json={"nome": "  ", "preco_mensal_centavos": 0}).status_code == 400


def test_modulo_desconhecido_recusado(client, db_ctx):
    assert _c(client).post("/api/admin/planos", json={"nome": "X", "preco_mensal_centavos": 0, "modulos": ["voar"]}).status_code == 400


def test_ciclo_recusado(client, db_ctx):
    c = _c(client)
    a = c.post("/api/admin/planos", json={"nome": "A", "preco_mensal_centavos": 0}).get_json()["codigo"]
    a_id = db.query_one("SELECT id FROM planos WHERE codigo = ?", (a,))["id"]
    b = c.post("/api/admin/planos", json={"nome": "B", "preco_mensal_centavos": 0, "plano_base_id": a_id}).get_json()["codigo"]
    b_id = db.query_one("SELECT id FROM planos WHERE codigo = ?", (b,))["id"]
    assert c.put(f"/api/admin/planos/{a}", json={"plano_base_id": b_id}).status_code == 400
    assert c.put(f"/api/admin/planos/{a}", json={"plano_base_id": a_id}).status_code == 400
    assert db.query_one("SELECT plano_base_id FROM planos WHERE id = ?", (a_id,))["plano_base_id"] is None


def test_editar_modulos_da_base_muda_o_filho(client, db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    c = _c(client)
    c.put("/api/admin/planos/pro", json={"modulos": ["financeiro", "analytics_avancado", "integracoes", "importacao_pacientes", "pandoo"]})
    ent = next(x for x in c.get("/api/admin/planos").get_json() if x["codigo"] == "enterprise")
    assert "pandoo" in ent["modulos_efetivos"] and "pandoo" in ent["modulos_herdados"]


def test_nao_desativa_base_de_plano_ativo(client, db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    c = _c(client)
    r = c.put("/api/admin/planos/pro", json={"ativo": False})
    assert r.status_code == 409 and "Enterprise" in r.get_json()["erro"]
    assert c.put("/api/admin/planos/starter", json={"ativo": False}).status_code == 200


def test_promocao_vencida_nao_e_atribuivel_mas_clinica_nela_continua(client, db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    c = _c(client)
    ontem = (date.today() - timedelta(days=1)).isoformat()
    codigo = c.post("/api/admin/planos", json={"nome": "Promo", "preco_mensal_centavos": 100, "modulos": ["integracoes"],
                                               "disponivel_ate": "2099-01-01"}).get_json()["codigo"]
    cen = DuasClinicas()
    assert c.put(f"/api/admin/clinicas/{cen.org_a}/plano", json={"plano": codigo}).status_code == 200
    c.put(f"/api/admin/planos/{codigo}", json={"disponivel_ate": ontem})
    assert c.put(f"/api/admin/clinicas/{cen.org_b}/plano", json={"plano": codigo}).status_code == 400
    from modulos_service import modulo_ativo_para_clinica
    assert modulo_ativo_para_clinica(cen.org_a, codigo, "integracoes")
    p = next(x for x in c.get("/api/admin/planos").get_json() if x["codigo"] == codigo)
    assert p["promocao_encerrada"] is True and p["total_clinicas"] == 1


def test_limite_de_pacientes_ignorado(client, db_ctx):
    c = _c(client)
    codigo = c.post("/api/admin/planos", json={"nome": "L", "preco_mensal_centavos": 0, "limite_pacientes": 5}).get_json()["codigo"]
    assert db.query_one("SELECT limite_pacientes FROM planos WHERE codigo = ?", (codigo,))["limite_pacientes"] is None


def test_gestor_nao_cria_nem_edita_plano(client, db_ctx):
    cen = DuasClinicas()
    g = autenticado(client, cen.gestor_a)
    assert g.post("/api/admin/planos", json={"nome": "X", "preco_mensal_centavos": 0}).status_code == 403
