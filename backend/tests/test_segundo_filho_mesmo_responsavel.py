"""
Regressão para "segundo filho, mesmo responsável, mesma clínica" (insight do
usuário, 02/09/2026): quando uma família já tem um filho cadastrado e a
clínica cadastra o segundo, vincular o responsável usando o MESMO e-mail
precisa reaproveitar a conta já existente — nunca criar uma conta duplicada
(o que faria o segundo filho "sumir" pro responsável, já que ele só
apareceria sob um login novo que ninguém tem a senha).

Cobre também a permissão nova de GET /pessoas/responsaveis para a Secretária
(usada pelo front-end para sugerir/autocompletar o responsável já
cadastrado, ver util.js::ativarAutocompleteResponsavel).
"""
from factories import DuasClinicas, novo_usuario

from conftest import autenticado


def test_segundo_paciente_mesma_clinica_mesmo_email_reaproveita_conta(client, db_ctx):
    cen = DuasClinicas()

    # Primeiro filho: vincula um responsável novo (conta ainda não existe).
    r1 = autenticado(client, cen.gestor_a).post(
        f"/api/pessoas/pacientes/{cen.paciente_a1}/vincular-responsavel",
        json={"nome": "Familia Dois Filhos", "email": "duasfilhas@a.com"},
    )
    assert r1.status_code == 201, r1.get_data(as_text=True)
    usuario_id_1 = r1.get_json()["usuario_id"]
    assert r1.get_json().get("link_convite")  # conta nova -> tem convite pra ativar

    # Segundo filho, cadastrado à parte, com o MESMO e-mail do responsável.
    r_paciente = autenticado(client, cen.gestor_a).post("/api/pessoas/pacientes", json={
        "nome": "Segundo Filho", "data_nascimento": "2021-03-01",
    })
    assert r_paciente.status_code == 201, r_paciente.get_data(as_text=True)
    segundo_filho_id = r_paciente.get_json()["id"]

    r2 = autenticado(client, cen.gestor_a).post(
        f"/api/pessoas/pacientes/{segundo_filho_id}/vincular-responsavel",
        json={"nome": "Familia Dois Filhos", "email": "DuasFilhas@a.com"},  # mesmo e-mail, caixa diferente
    )
    assert r2.status_code == 201, r2.get_data(as_text=True)
    usuario_id_2 = r2.get_json()["usuario_id"]

    # Mesma conta reaproveitada — nunca uma segunda.
    assert usuario_id_2 == usuario_id_1
    assert "link_convite" not in r2.get_json()  # não é conta nova, não há convite

    # Só existe UMA conta com esse e-mail nesta clínica.
    contas = db_ctx.query(
        "SELECT id FROM usuarios WHERE organizacao_id = ? AND lower(email) = ?",
        (cen.org_a, "duasfilhas@a.com"),
    )
    assert len(contas) == 1

    # E o responsável agora está vinculado aos DOIS filhos.
    vinculos = db_ctx.query(
        "SELECT paciente_id FROM responsaveis_pacientes WHERE usuario_id = ?", (usuario_id_1,)
    )
    ids_vinculados = {v["paciente_id"] for v in vinculos}
    assert ids_vinculados == {cen.paciente_a1, segundo_filho_id}


def test_secretaria_pode_listar_responsaveis_da_clinica(client, db_ctx):
    cen = DuasClinicas()
    sec = novo_usuario(cen.org_a, "Secretária A", "secretaria@a.com", "secretaria")
    from factories import vincular_responsavel
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)

    r = autenticado(client, sec).get("/api/pessoas/responsaveis")
    assert r.status_code == 200, r.get_data(as_text=True)
    emails = {resp["email"] for resp in r.get_json()}
    assert cen.resp_a1["email"] in emails


def test_listar_responsaveis_nao_vaza_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).get("/api/pessoas/responsaveis")
    assert r.status_code == 200
    emails = {resp["email"] for resp in r.get_json()}
    assert cen.resp_b1["email"] not in emails


def test_responsavel_nao_pode_listar_responsaveis(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.resp_a1).get("/api/pessoas/responsaveis")
    assert r.status_code == 403
