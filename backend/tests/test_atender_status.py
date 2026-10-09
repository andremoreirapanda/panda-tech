"""Status novos da consulta (spec 08/10/2026, Atender)."""
from datetime import date, timedelta

import pytest

from factories import DuasClinicas, novo_usuario

from conftest import autenticado

AMANHA = (date.today() + timedelta(days=2)).isoformat()


def _agendar(client, cen, hora="14:00", paciente=None):
    return autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": paciente or cen.paciente_a1, "profissional_id": cen.prof_a1["id"],
        "data_hora": f"{AMANHA} {hora}:00", "duracao_min": 50}).get_json()["id"]


@pytest.mark.parametrize("status", ["falta_justificada", "desmarcada_profissional"])
def test_status_novos_sao_aceitos(client, db_ctx, status):
    cen = DuasClinicas()
    cid = _agendar(client, cen)
    assert autenticado(client, cen.prof_a1).put(f"/api/agenda/{cid}/status", json={"status": status}).status_code == 200
    assert db_ctx.query_one("SELECT status FROM consultas WHERE id = ?", (cid,))["status"] == status


def test_secretaria_nao_finaliza(client, db_ctx):
    cen = DuasClinicas()
    sec = novo_usuario(cen.org_a, "Secretária A", "sec@a.com", "secretaria")
    cid = _agendar(client, cen)
    r = autenticado(client, sec).put(f"/api/agenda/{cid}/status", json={"status": "realizada"})
    assert r.status_code == 403
    assert autenticado(client, sec).put(f"/api/agenda/{cid}/status", json={"status": "falta_justificada"}).status_code == 200


@pytest.mark.parametrize("status", ["falta_justificada", "desmarcada_profissional"])
def test_status_que_liberam_horario_nao_pedem_encaixe(client, db_ctx, status):
    cen = DuasClinicas()
    cid = _agendar(client, cen)
    autenticado(client, cen.gestor_a).put(f"/api/agenda/{cid}/status", json={"status": status})
    r = autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": cen.paciente_a2, "profissional_id": cen.prof_a1["id"], "data_hora": f"{AMANHA} 14:00:00", "duracao_min": 50})
    assert r.status_code == 201, r.get_data(as_text=True)


def test_reativar_desmarcada_pelo_profissional_sobre_horario_ocupado_pede_encaixe(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    cid = _agendar(client, cen)
    c.put(f"/api/agenda/{cid}/status", json={"status": "desmarcada_profissional"})
    _agendar(client, cen, paciente=cen.paciente_a2)
    r = c.put(f"/api/agenda/{cid}/status", json={"status": "agendada"})
    assert r.status_code == 409 and r.get_json()["pode_encaixar"] is True


def test_editar_consulta_desmarcada_nao_checa_conflito(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    cid = _agendar(client, cen, hora="10:00")
    c.put(f"/api/agenda/{cid}/status", json={"status": "falta_justificada"})
    _agendar(client, cen, hora="16:00", paciente=cen.paciente_a2)
    assert c.put(f"/api/agenda/{cid}", json={"data_hora": f"{AMANHA} 16:00:00"}).status_code == 200


def test_consultas_no_periodo_ignora_status_que_liberam(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    cid = _agendar(client, cen, hora="12:30")
    c.put(f"/api/agenda/{cid}/status", json={"status": "desmarcada_profissional"})
    r = c.post("/api/agenda/ausencias", json={"profissional_id": cen.prof_a1["id"], "data_inicio": AMANHA, "data_fim": AMANHA,
                                              "dia_inteiro": True, "dias_semana": "0123456", "motivo": "Curso"})
    assert r.get_json()["consultas_no_periodo"] == []


def test_exclusao_da_equipe_nao_trava_por_consulta_desmarcada(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    cid = c.post("/api/agenda", json={"paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a2["id"],
                                      "data_hora": f"{AMANHA} 09:00:00"}).get_json()["id"]
    c.put(f"/api/agenda/{cid}/status", json={"status": "desmarcada_profissional"})
    assert c.delete(f"/api/pessoas/profissionais/{cen.prof_a2['id']}").status_code == 200
