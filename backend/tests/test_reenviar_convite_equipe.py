"""
Reenviar link de acesso (ativação/redefinição de senha) de profissional e
secretária pela tela de Equipe — espelho do que já existe para responsável
(ver test_uat_26_08_2026.py). Sempre restrito à própria clínica e ao gestor.
"""
from factories import DuasClinicas, novo_usuario

from conftest import autenticado


def test_gestor_reenvia_link_de_profissional_da_propria_clinica(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post(f"/api/pessoas/profissionais/{cen.prof_a1['id']}/reenviar-convite")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert "link_convite" in r.get_json()


def test_reenviar_link_de_profissional_de_outra_clinica_e_404(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_b).post(f"/api/pessoas/profissionais/{cen.prof_a1['id']}/reenviar-convite")
    assert r.status_code == 404, r.get_data(as_text=True)


def test_profissional_nao_reenvia_link_de_colega(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.prof_a1).post(f"/api/pessoas/profissionais/{cen.prof_a2['id']}/reenviar-convite")
    assert r.status_code == 403, r.get_data(as_text=True)


def test_gestor_reenvia_link_de_secretaria_e_bloqueia_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    sec = novo_usuario(cen.org_a, "Secretária A", "secretaria@a.com", "secretaria")
    ok = autenticado(client, cen.gestor_a).post(f"/api/pessoas/secretarias/{sec['id']}/reenviar-convite")
    assert ok.status_code == 200, ok.get_data(as_text=True)
    assert "link_convite" in ok.get_json()
    negado = autenticado(client, cen.gestor_b).post(f"/api/pessoas/secretarias/{sec['id']}/reenviar-convite")
    assert negado.status_code == 404, negado.get_data(as_text=True)
