"""
Regressão para os achados de IDOR na Agenda (auditoria de segurança de
25/08/2026) — nenhuma clínica pode gerenciar ou reatribuir uma consulta
que envolva outra clínica, mesmo tendo o papel de gestor/profissional.
"""
from factories import DuasClinicas

from conftest import autenticado


def test_gestor_cria_consulta_na_propria_clinica(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a1["id"], "data_hora": "2026-09-01 10:00:00",
    })
    assert r.status_code == 201, r.get_data(as_text=True)


def test_gestor_nao_cria_consulta_com_profissional_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.prof_b1["id"], "data_hora": "2026-09-02 10:00:00",
    })
    assert r.status_code == 400, r.get_data(as_text=True)


def test_gestor_de_outra_clinica_nao_edita_consulta(client, db_ctx):
    cen = DuasClinicas()
    consulta_id = db_ctx.execute(
        "INSERT INTO consultas (paciente_id, profissional_id, data_hora) VALUES (?, ?, ?)",
        (cen.paciente_a1, cen.prof_a1["id"], "2026-09-01 10:00:00"),
    )
    r = autenticado(client, cen.gestor_b).put(f"/api/agenda/{consulta_id}", json={"observacoes": "hackeado"})
    assert r.status_code == 403, r.get_data(as_text=True)


def test_gestor_de_outra_clinica_nao_exclui_consulta(client, db_ctx):
    cen = DuasClinicas()
    consulta_id = db_ctx.execute(
        "INSERT INTO consultas (paciente_id, profissional_id, data_hora) VALUES (?, ?, ?)",
        (cen.paciente_a1, cen.prof_a1["id"], "2026-09-01 10:00:00"),
    )
    r = autenticado(client, cen.gestor_b).delete(f"/api/agenda/{consulta_id}")
    assert r.status_code == 403, r.get_data(as_text=True)


def test_gestor_da_mesma_clinica_edita_consulta_normalmente(client, db_ctx):
    cen = DuasClinicas()
    consulta_id = db_ctx.execute(
        "INSERT INTO consultas (paciente_id, profissional_id, data_hora) VALUES (?, ?, ?)",
        (cen.paciente_a1, cen.prof_a1["id"], "2026-09-01 10:00:00"),
    )
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{consulta_id}", json={"observacoes": "ajuste legítimo"})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_nao_reatribui_consulta_a_profissional_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    consulta_id = db_ctx.execute(
        "INSERT INTO consultas (paciente_id, profissional_id, data_hora) VALUES (?, ?, ?)",
        (cen.paciente_a1, cen.prof_a1["id"], "2026-09-01 10:00:00"),
    )
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{consulta_id}", json={"profissional_id": cen.prof_b1["id"]})
    assert r.status_code == 400, r.get_data(as_text=True)


def test_reatribui_consulta_a_profissional_da_mesma_clinica(client, db_ctx):
    cen = DuasClinicas()
    consulta_id = db_ctx.execute(
        "INSERT INTO consultas (paciente_id, profissional_id, data_hora) VALUES (?, ?, ?)",
        (cen.paciente_a1, cen.prof_a1["id"], "2026-09-01 10:00:00"),
    )
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{consulta_id}", json={"profissional_id": cen.prof_a2["id"]})
    assert r.status_code == 200, r.get_data(as_text=True)
