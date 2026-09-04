"""
Regressão para a troca de senha autoatendida (`PUT /api/pessoas/perfil/senha`,
insight do usuário, 04/09/2026): antes disso não existia NENHUM jeito de um
usuário já logado (qualquer papel, incluindo admin_master) trocar a própria
senha sem passar pelo fluxo de "esqueci a senha" — usado sempre pra quando a
pessoa NÃO está logada. Cobre: sucesso, senha atual errada, nova senha curta
demais, e a revogação do token atual (mesmo mecanismo de auth.py usado pelo
resto do sistema).
"""
from factories import DuasClinicas, novo_usuario

from conftest import autenticado, token_de


def test_troca_de_senha_com_sucesso_e_revoga_token_antigo(client, db_ctx):
    cen = DuasClinicas()
    token_antigo = token_de(cen.gestor_a)

    r = autenticado(client, cen.gestor_a).put("/api/pessoas/perfil/senha", json={
        "senha_atual": "senhateste123", "nova_senha": "novaSenhaForte1",
    })
    assert r.status_code == 200, r.get_data(as_text=True)

    # O token emitido ANTES da troca (pwd_ts velho) deixa de funcionar —
    # mesmo mecanismo de revogação usado em qualquer troca de senha do sistema.
    client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token_antigo}"
    r = client.get("/api/auth/me")
    assert r.status_code == 401, r.get_data(as_text=True)


def test_troca_de_senha_recusa_senha_atual_errada(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).put("/api/pessoas/perfil/senha", json={
        "senha_atual": "senhaErrada", "nova_senha": "novaSenhaForte1",
    })
    assert r.status_code == 401, r.get_data(as_text=True)


def test_troca_de_senha_recusa_nova_senha_curta_demais(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).put("/api/pessoas/perfil/senha", json={
        "senha_atual": "senhateste123", "nova_senha": "curta",
    })
    assert r.status_code == 400, r.get_data(as_text=True)


def test_troca_de_senha_exige_senha_atual_e_nova(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).put("/api/pessoas/perfil/senha", json={"senha_atual": "senhateste123"})
    assert r.status_code == 400, r.get_data(as_text=True)


def test_troca_de_senha_funciona_para_admin_master(client, db_ctx):
    admin = novo_usuario(None, "Admin Teste", "admin.teste@plataforma.com", "admin_master")
    r = autenticado(client, admin).put("/api/pessoas/perfil/senha", json={
        "senha_atual": "senhateste123", "nova_senha": "novaSenhaForte1",
    })
    assert r.status_code == 200, r.get_data(as_text=True)
