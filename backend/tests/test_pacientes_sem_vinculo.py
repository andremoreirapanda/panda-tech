"""
Pacientes sem vínculo (pedido do usuário, 01/10/2026): não é mais preciso
vincular o profissional ao paciente — todo profissional ativo da clínica edita
plano, missões, diário e ficha de qualquer paciente da clínica (como o gestor).
Outra clínica continua sem acesso nenhum, e secretária/responsável não ganham
edição.
"""
from factories import DuasClinicas, novo_usuario

from conftest import autenticado


def test_profissional_sem_vinculo_edita_paciente_da_clinica(client, db_ctx):
    cen = DuasClinicas()   # prof_a2 não tem vínculo com ninguém
    r = autenticado(client, cen.prof_a2).put(f"/api/pessoas/pacientes/{cen.paciente_a1}", json={"nome": "Paciente A1"})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_lista_de_pacientes_marca_todos_como_editaveis(client, db_ctx):
    cen = DuasClinicas()
    pacientes = autenticado(client, cen.prof_a2).get("/api/pessoas/pacientes").get_json()
    assert pacientes and all(p["pode_editar"] for p in pacientes)


def test_profissional_sem_vinculo_escreve_no_diario(client, db_ctx):
    cen = DuasClinicas()
    j = autenticado(client, cen.prof_a2).post(f"/api/jornada/paciente/{cen.paciente_a1}/criar-jornada", json={})
    assert j.status_code == 201, j.get_data(as_text=True)
    r = autenticado(client, cen.prof_a2).post(f"/api/diario/jornada/{j.get_json()['id']}", json={
        "evolucao_clinica": "Sessão boa.",
    })
    assert r.status_code == 201, r.get_data(as_text=True)


def test_outra_clinica_continua_sem_acesso(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.prof_b1).put(f"/api/pessoas/pacientes/{cen.paciente_a1}", json={"nome": "X"})
    assert r.status_code in (403, 404)


def test_secretaria_e_profissional_inativo_nao_editam(client, db_ctx):
    cen = DuasClinicas()
    sec = novo_usuario(cen.org_a, "Secretária A", "sec@a.com", "secretaria")
    r = autenticado(client, sec).put(f"/api/pessoas/pacientes/{cen.paciente_a1}", json={"nome": "X"})
    assert r.status_code == 403
