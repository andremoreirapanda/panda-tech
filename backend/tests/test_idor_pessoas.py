"""
Regressão para os achados de IDOR em Pessoas (auditoria de segurança de
25/08/2026): cadastro de paciente, vínculo de responsável por e-mail, e
visualização de disponibilidade de profissional — nenhum deve atravessar
clínicas.
"""
from factories import DuasClinicas

from conftest import autenticado


def test_criar_paciente_ignora_responsavel_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/pessoas/pacientes", json={
        "nome": "Novo Paciente", "data_nascimento": "2020-01-01",
        "responsaveis_ids": [cen.resp_b1["id"]],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    novo_id = r.get_json()["id"]
    vinculo = db_ctx.query_one(
        "SELECT 1 FROM responsaveis_pacientes WHERE usuario_id = ? AND paciente_id = ?",
        (cen.resp_b1["id"], novo_id),
    )
    assert vinculo is None


def test_criar_paciente_ignora_profissional_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/pessoas/pacientes", json={
        "nome": "Novo Paciente 2", "data_nascimento": "2020-01-01",
        "profissionais_ids": [cen.prof_b1["id"]],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    novo_id = r.get_json()["id"]
    vinculo = db_ctx.query_one(
        "SELECT 1 FROM profissionais_pacientes WHERE usuario_id = ? AND paciente_id = ?",
        (cen.prof_b1["id"], novo_id),
    )
    assert vinculo is None


def test_criar_paciente_vincula_profissional_da_mesma_clinica_como_principal(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/pessoas/pacientes", json={
        "nome": "Novo Paciente 3", "data_nascimento": "2020-01-01",
        "profissionais_ids": [cen.prof_a2["id"]],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    novo_id = r.get_json()["id"]
    vinculo = db_ctx.query_one(
        "SELECT * FROM profissionais_pacientes WHERE usuario_id = ? AND paciente_id = ?",
        (cen.prof_a2["id"], novo_id),
    )
    assert vinculo is not None
    assert vinculo["principal"] == 1


def test_vincular_responsavel_por_email_nao_reaproveita_conta_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post(f"/api/pessoas/pacientes/{cen.paciente_a1}/vincular-responsavel", json={
        "nome": "Familia Compartilhada", "email": "familia.compartilhada@x.com",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    usuario_id_vinculado = r.get_json()["usuario_id"]
    assert usuario_id_vinculado != cen.resp_b1["id"]
    vinculado = db_ctx.query_one("SELECT organizacao_id FROM usuarios WHERE id = ?", (usuario_id_vinculado,))
    assert vinculado["organizacao_id"] == cen.org_a


def test_disponibilidade_de_profissional_de_outra_clinica_e_404(client, db_ctx):
    cen = DuasClinicas()
    db_ctx.execute(
        "INSERT INTO disponibilidade_profissional (usuario_id, dia_semana, hora_inicio, hora_fim) VALUES (?, 1, '08:00', '18:00')",
        (cen.prof_b1["id"],),
    )
    r = autenticado(client, cen.gestor_a).get(f"/api/pessoas/profissionais/{cen.prof_b1['id']}/disponibilidade")
    assert r.status_code == 404, r.get_data(as_text=True)


def test_disponibilidade_de_profissional_da_mesma_clinica_e_200(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).get(f"/api/pessoas/profissionais/{cen.prof_a1['id']}/disponibilidade")
    assert r.status_code == 200, r.get_data(as_text=True)
