"""
Regressão para os achados de autenticação/sessão (auditoria de segurança de
25/08/2026): revogação de token ao trocar senha, limite de tentativas nas
rotas de redefinição, e política de senha mínima.
"""
import auth

from factories import DuasClinicas, novo_usuario

from conftest import token_de


def test_token_antigo_e_revogado_apos_troca_de_senha(client, db_ctx):
    cen = DuasClinicas()

    tok_antigo = token_de(cen.resp_a1)
    c = client
    c.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {tok_antigo}"
    r = c.get("/api/auth/me")
    assert r.status_code == 200, r.get_data(as_text=True)

    novo_hash, novo_salt = auth.hash_senha("outrasenha456")
    db_ctx.execute(
        "UPDATE usuarios SET senha_hash = ?, senha_salt = ?, senha_alterada_em = ? WHERE id = ?",
        (novo_hash, novo_salt, db_ctx.agora_sql(), cen.resp_a1["id"]),
    )

    r = c.get("/api/auth/me")
    assert r.status_code == 401, r.get_data(as_text=True)


def test_token_novo_apos_troca_de_senha_funciona(client, db_ctx):
    cen = DuasClinicas()

    novo_hash, novo_salt = auth.hash_senha("outrasenha456")
    db_ctx.execute(
        "UPDATE usuarios SET senha_hash = ?, senha_salt = ?, senha_alterada_em = ? WHERE id = ?",
        (novo_hash, novo_salt, db_ctx.agora_sql(), cen.resp_a1["id"]),
    )
    usuario_atualizado = db_ctx.query_one("SELECT * FROM usuarios WHERE id = ?", (cen.resp_a1["id"],))

    c = client
    c.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token_de(usuario_atualizado)}"
    r = c.get("/api/auth/me")
    assert r.status_code == 200, r.get_data(as_text=True)


def test_redefinir_senha_exige_minimo_8_caracteres(client, db_ctx):
    r = client.post("/api/auth/redefinir-senha", json={"token": "qualquer-coisa", "nova_senha": "1234567"})
    assert r.status_code == 400, r.get_data(as_text=True)


def test_validar_token_redefinicao_tem_limite_de_tentativas(client, db_ctx):
    codigos = [client.get("/api/auth/validar-token-redefinicao/naoexiste").status_code for _ in range(25)]
    assert 429 in codigos, f"esperava um 429 entre as respostas, recebi: {codigos}"


def test_redefinir_senha_tem_limite_de_tentativas(client, db_ctx):
    codigos = [
        client.post("/api/auth/redefinir-senha", json={"token": "x", "nova_senha": "senhalonga123"}).status_code
        for _ in range(25)
    ]
    assert 429 in codigos, f"esperava um 429 entre as respostas, recebi: {codigos}"


def test_login_com_senha_errada_e_negado(client, db_ctx):
    org = db_ctx.execute("INSERT INTO organizacoes (nome, plano) VALUES (?, ?)", ("Clínica Teste", "premium"))
    novo_usuario(org, "Usuário", "usuario@teste.com", "gestor")
    r = client.post("/api/auth/login", json={"email": "usuario@teste.com", "senha": "senhaerrada"})
    assert r.status_code == 401, r.get_data(as_text=True)


def test_login_com_senha_correta_funciona(client, db_ctx):
    org = db_ctx.execute("INSERT INTO organizacoes (nome, plano) VALUES (?, ?)", ("Clínica Teste", "premium"))
    novo_usuario(org, "Usuário", "usuario2@teste.com", "gestor")
    r = client.post("/api/auth/login", json={"email": "usuario2@teste.com", "senha": "senhateste123"})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert "token" in r.get_json()
