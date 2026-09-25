"""White Label completo (25/09/2026): trava real do módulo e campos novos em Configurações."""
import base64

import db
import planos_padrao
from factories import DuasClinicas, novo_usuario
from conftest import autenticado
from modulos_service import definir_liberacao_admin

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def _me_org(client, u):
    return autenticado(client, u).get("/api/auth/me").get_json()["organizacao"]


def test_sem_modulo_me_devolve_padroes_e_guarda_valores(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    r = c.put("/api/pessoas/organizacao", json={"cor_primaria": "#112233", "nome_moeda_gamificacao": "Estrelinhas",
                                                "mundo_fundo": "mar"})
    assert r.status_code == 200, r.get_data(as_text=True)
    org = _me_org(client, cen.gestor_a)
    assert org["cor_primaria"] == "#5B4FE9" and org["nome_moeda_gamificacao"] == "XP" and org["mundo_fundo"] == "estrelas"
    assert org["white_label_ativo"] is False
    guardado = autenticado(client, cen.gestor_a).get("/api/pessoas/organizacao").get_json()
    assert guardado["cor_primaria"] == "#112233" and guardado["white_label_ativo"] is False
    definir_liberacao_admin(cen.org_a, "white_label", True)
    org = _me_org(client, cen.gestor_a)
    assert org["cor_primaria"] == "#112233" and org["mundo_fundo"] == "mar" and org["white_label_ativo"] is True
    assert "white_label" in org["modulos_habilitados"]


def test_login_tambem_devolve_identidade_efetiva(client, db_ctx):
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET cor_primaria = '#112233' WHERE id = ?", (cen.org_a,))
    r = client.post("/api/auth/login", json={"email": "gestora@a.com", "senha": "senhateste123"})
    assert r.status_code == 200
    assert r.get_json()["usuario"]["organizacao"]["cor_primaria"] == "#5B4FE9"


def test_me_nao_carrega_imagens_grandes(client, db_ctx):
    cen = DuasClinicas()
    definir_liberacao_admin(cen.org_a, "white_label", True)
    autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={"app_icone_base64": PNG})
    org = _me_org(client, cen.gestor_a)
    assert "app_icone_base64" not in org and "pandoo_cenario_imagem" not in org
    assert org["tem_icone"] is True and org["versao_imagens"]


def test_campos_novos_salvam_e_put_parcial_nao_apaga(client, db_ctx):
    cen = DuasClinicas()
    corpo = {"app_nome": "Encantar App", "login_mensagem": "Bem-vindo!", "mundo_fonte": "nunito",
             "mundo_fundo": "espaco", "mundo_mascote": "🦊", "mundo_comemoracao": "Arrasou!",
             "app_icone_base64": PNG, "mundo_mascote_imagem": PNG, "endereco_login": "encantar"}
    r = autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json=corpo)
    assert r.status_code == 200, r.get_data(as_text=True)
    autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={"nome": "Outro nome"})
    o = db.query_one("SELECT * FROM organizacoes WHERE id = ?", (cen.org_a,))
    for k, v in corpo.items():
        assert o[k] == v, k


def test_limpar_campo_texto_volta_ao_padrao(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={"app_nome": "X"})
    autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={"app_nome": ""})
    assert db.query_one("SELECT app_nome FROM organizacoes WHERE id = ?", (cen.org_a,))["app_nome"] is None


def test_recusas(client, db_ctx):
    cen = DuasClinicas()
    ruins = [{"app_nome": "x" * 31}, {"login_mensagem": "x" * 121}, {"mundo_comemoracao": "x" * 41},
             {"mundo_comemoracao": "<b>oi</b>"}, {"mundo_fonte": "comic"}, {"mundo_fundo": "praia"},
             {"mundo_mascote": "🐙"}, {"mundo_mascote": "clinica"}, {"mundo_fundo": "clinica"},
             {"app_icone_base64": base64.b64encode(b"GIF89a" + b"\x00" * 10).decode()},
             {"mundo_mascote_imagem": "not base64 \" onerror="}, {"endereco_login": "a b"},
             {"app_nome": 42}]
    for corpo in ruins:
        r = autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json=corpo)
        assert r.status_code == 400, corpo


def test_mascote_e_fundo_clinica_com_imagem(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={
        "mundo_mascote_imagem": PNG, "mundo_mascote": "clinica", "pandoo_cenario_imagem": PNG, "mundo_fundo": "clinica"})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_remover_imagem_em_uso_e_recusado(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={
        "mundo_mascote_imagem": PNG, "mundo_mascote": "clinica"})
    r = autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={"mundo_mascote_imagem": None})
    assert r.status_code == 400


def test_endereco_repetido_409_e_gerado_na_leitura(client, db_ctx):
    cen = DuasClinicas()
    end_b = autenticado(client, cen.gestor_b).get("/api/pessoas/organizacao").get_json()["endereco_login"]
    assert end_b == "clinica-b"
    r = autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={"endereco_login": "clinica-b"})
    assert r.status_code == 409


def test_criar_clinica_gera_endereco(client, db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    admin = novo_usuario(None, "Admin", "admin@saas.com", "admin_master")
    r = autenticado(client, admin).post("/api/admin/clinicas", json={
        "nome": "Clínica Nova Vida", "plano": "starter", "gestor_email": "g@nova.com"})
    assert r.status_code == 201, r.get_data(as_text=True)
    o = db.query_one("SELECT endereco_login FROM organizacoes WHERE id = ?", (r.get_json()["id"],))
    assert o["endereco_login"] == "clinica-nova-vida"


def test_descricao_do_modulo_cita_login_e_mundo():
    from modulos_service import MODULOS_OPCIONAIS
    d = next(m for m in MODULOS_OPCIONAIS if m["codigo"] == "white_label")["descricao"]
    assert "login" in d and "Mundo da Criança" in d
