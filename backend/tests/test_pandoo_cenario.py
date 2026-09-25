"""Pandoo (25/09/2026): cenário padrão da clínica (Configurações do gestor)."""
import base64

import db
from factories import DuasClinicas
from conftest import autenticado
from modulos_service import definir_liberacao_admin

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def _org(org_id):
    return db.query_one("SELECT pandoo_cenario_padrao, pandoo_cenario_imagem, pandoo_cenario_tom FROM organizacoes WHERE id = ?", (org_id,))


def test_gestor_escolhe_cenario_pronto(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={"pandoo_cenario_padrao": "mar"})
    assert r.status_code == 200
    assert _org(cen.org_a)["pandoo_cenario_padrao"] == "mar"
    me = autenticado(client, cen.gestor_a).get("/api/auth/me").get_json()
    assert me["organizacao"]["pandoo_cenario_padrao"] == "mar"


def test_imagem_da_clinica_com_tom(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    r = c.put("/api/pessoas/organizacao", json={"pandoo_cenario_padrao": "clinica", "pandoo_cenario_imagem": PNG, "pandoo_cenario_tom": "claro"})
    assert r.status_code == 200, r.get_data(as_text=True)
    o = _org(cen.org_a)
    assert (o["pandoo_cenario_padrao"], o["pandoo_cenario_tom"]) == ("clinica", "claro") and o["pandoo_cenario_imagem"] == PNG


def test_recusas(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    assert c.put("/api/pessoas/organizacao", json={"pandoo_cenario_padrao": "praia"}).status_code == 400
    assert c.put("/api/pessoas/organizacao", json={"pandoo_cenario_tom": "cinza"}).status_code == 400
    falso = base64.b64encode(b"<svg onload=alert(1)>").decode()
    assert c.put("/api/pessoas/organizacao", json={"pandoo_cenario_imagem": falso}).status_code == 400
    assert c.put("/api/pessoas/organizacao", json={"pandoo_cenario_padrao": "clinica"}).status_code == 400  # sem imagem enviada


def test_put_sem_campos_nao_mexe_no_cenario(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    c.put("/api/pessoas/organizacao", json={"pandoo_cenario_padrao": "espaco"})
    c.put("/api/pessoas/organizacao", json={"nome": "Outra"})
    assert _org(cen.org_a)["pandoo_cenario_padrao"] == "espaco"


def test_jogo_usa_padrao_da_clinica(client, db_ctx):
    cen = DuasClinicas()
    definir_liberacao_admin(cen.org_a, "pandoo", True)
    autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={
        "pandoo_cenario_padrao": "clinica", "pandoo_cenario_imagem": PNG, "pandoo_cenario_tom": "claro"})
    corpo = {"titulo": "R", "modelo": "roleta",
             "conteudo": {"versao": 1, "itens": [{"id": f"i{i}", "pergunta": {"texto": "x", "imagem": PNG}} for i in range(2)]}}
    jogo = autenticado(client, cen.prof_a1).post("/api/pandoo/jogos", json=corpo).get_json()["id"]
    efetivo = autenticado(client, cen.prof_a1).get(f"/api/pandoo/jogos/{jogo}").get_json()["cenario_efetivo"]
    assert efetivo == {"tipo": "clinica", "imagem": PNG, "tom": "claro"}
