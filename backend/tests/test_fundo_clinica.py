"""Fundo da clínica no app da equipe e das famílias (26/09/2026) — só com o
módulo Identidade Visual Própria."""
import base64

import db
from factories import DuasClinicas
from conftest import autenticado
from modulos_service import definir_liberacao_admin

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def _me_org(client, u):
    return autenticado(client, u).get("/api/auth/me").get_json()["organizacao"]


def _salvar(client, u, corpo):
    return autenticado(client, u).put("/api/pessoas/organizacao", json=corpo)


def test_fundo_so_vale_com_o_modulo(client, db_ctx):
    cen = DuasClinicas()
    assert _salvar(client, cen.gestor_a, {"app_fundo": "mar"}).status_code == 200
    assert _me_org(client, cen.gestor_a)["app_fundo"] == "padrao"
    definir_liberacao_admin(cen.org_a, "white_label", True)
    assert _me_org(client, cen.gestor_a)["app_fundo"] == "mar"


def test_fundo_colorido_paleta_ou_cor_livre(client, db_ctx):
    cen = DuasClinicas()
    definir_liberacao_admin(cen.org_a, "white_label", True)
    assert _salvar(client, cen.gestor_a, {"app_fundo": "cor", "app_fundo_cor": "degrade-aurora"}).status_code == 200
    org = _me_org(client, cen.gestor_a)
    assert (org["app_fundo"], org["app_fundo_cor"]) == ("cor", "degrade-aurora")
    assert _salvar(client, cen.gestor_a, {"app_fundo": "cor", "app_fundo_cor": "#A1B2C3"}).status_code == 200
    assert _me_org(client, cen.gestor_a)["app_fundo_cor"] == "#A1B2C3"


def test_recusas(client, db_ctx):
    cen = DuasClinicas()
    for corpo in ({"app_fundo": "praia"}, {"app_fundo": "cor"}, {"app_fundo": "cor", "app_fundo_cor": "red; background:url(x)"},
                  {"app_fundo_cor": "#12345"}, {"app_fundo": "clinica"}):
        assert _salvar(client, cen.gestor_a, corpo).status_code == 400, corpo


def test_fundo_imagem_da_clinica_usa_a_foto_do_cenario(client, db_ctx):
    cen = DuasClinicas()
    r = _salvar(client, cen.gestor_a, {"pandoo_cenario_imagem": PNG, "app_fundo": "clinica"})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_put_parcial_nao_apaga_o_fundo(client, db_ctx):
    cen = DuasClinicas()
    _salvar(client, cen.gestor_a, {"app_fundo": "cor", "app_fundo_cor": "menta"})
    _salvar(client, cen.gestor_a, {"nome": "Outro"})
    o = db.query_one("SELECT app_fundo, app_fundo_cor FROM organizacoes WHERE id = ?", (cen.org_a,))
    assert (o["app_fundo"], o["app_fundo_cor"]) == ("cor", "menta")
