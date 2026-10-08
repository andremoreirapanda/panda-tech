"""Ausência bloqueia agendar por cima; duração validada (spec 07/10/2026)."""
from factories import DuasClinicas

from conftest import autenticado

ALMOCO = {"data_inicio": "2026-10-05", "data_fim": "", "dia_inteiro": False,
          "hora_inicio": "12:00", "hora_fim": "13:00", "dias_semana": "12345", "motivo": "Almoço"}


def _ausencia(client, cen, prof, **extra):
    r = autenticado(client, cen.gestor_a).post("/api/agenda/ausencias", json={**ALMOCO, "profissional_id": prof["id"], **extra})
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["id"]


def _agendar(client, usuario, prof, data_hora, _pac, **extra):
    return autenticado(client, usuario).post("/api/agenda", json={
        "paciente_id": _pac, "profissional_id": prof["id"], "data_hora": data_hora, **extra})


def test_criar_por_cima_da_ausencia_da_409(client, db_ctx):
    cen = DuasClinicas()
    _ausencia(client, cen, cen.prof_a1)
    r = _agendar(client, cen.gestor_a, cen.prof_a1, "2026-10-06 12:30:00", _pac=cen.paciente_a1, duracao_min=30)
    assert r.status_code == 409
    assert "Prof A1 está ausente" in r.get_json()["erro"] and "Almoço" in r.get_json()["erro"]


def test_consulta_que_encosta_passa(client, db_ctx):
    cen = DuasClinicas()
    _ausencia(client, cen, cen.prof_a1)
    r = _agendar(client, cen.gestor_a, cen.prof_a1, "2026-10-06 11:00:00", _pac=cen.paciente_a1, duracao_min=60)
    assert r.status_code == 201, r.get_data(as_text=True)


def test_duracao_invalida_da_400_e_padrao_vem_da_clinica(client, db_ctx):
    cen = DuasClinicas()
    r = _agendar(client, cen.gestor_a, cen.prof_a1, "2026-10-06 09:00:00", _pac=cen.paciente_a1, duracao_min=2)
    assert r.status_code == 400
    db_ctx.execute("UPDATE organizacoes SET agenda_duracao_padrao = 45 WHERE id = ?", (cen.org_a,))
    r = _agendar(client, cen.gestor_a, cen.prof_a1, "2026-10-06 09:00:00", _pac=cen.paciente_a1)
    assert r.status_code == 201
    assert db_ctx.query_one("SELECT duracao_min FROM consultas WHERE id = ?", (r.get_json()["id"],))["duracao_min"] == 45


def test_remarcar_e_reatribuir_para_ausencia_dao_409(client, db_ctx):
    cen = DuasClinicas()
    r = _agendar(client, cen.gestor_a, cen.prof_a1, "2026-10-06 09:00:00", _pac=cen.paciente_a1, duracao_min=50)
    cid = r.get_json()["id"]
    _ausencia(client, cen, cen.prof_a1)
    _ausencia(client, cen, cen.prof_a2, hora_inicio="08:00", hora_fim="10:00", motivo="Curso")
    c = autenticado(client, cen.gestor_a)
    assert c.put(f"/api/agenda/{cid}", json={"data_hora": "2026-10-06 12:15:00"}).status_code == 409
    r2 = c.put(f"/api/agenda/{cid}", json={"profissional_id": cen.prof_a2["id"]})
    assert r2.status_code == 409 and "Curso" in r2.get_json()["erro"]
    assert c.put(f"/api/agenda/{cid}", json={"duracao_min": 300}).status_code == 409  # 09:00 + 300 min cruza o almoço


def test_editar_so_observacao_nao_checa_ausencia(client, db_ctx):
    cen = DuasClinicas()
    cid = _agendar(client, cen.gestor_a, cen.prof_a1, "2026-10-06 12:00:00", _pac=cen.paciente_a1, duracao_min=50).get_json()["id"]
    _ausencia(client, cen, cen.prof_a1)  # criada depois, por cima da consulta
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{cid}", json={"observacoes": "Trazer exames"})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_recorrente_pula_datas_da_ausencia(client, db_ctx):
    cen = DuasClinicas()
    _ausencia(client, cen, cen.prof_a1, data_inicio="2026-10-13", data_fim="2026-10-17",
              dia_inteiro=True, hora_inicio="", hora_fim="", motivo="Férias")
    r = autenticado(client, cen.gestor_a).post("/api/agenda/recorrente", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a1["id"], "data_hora": "2026-10-06 09:00:00",
        "frequencia": "semanal", "repeticoes": 3, "duracao_min": 45})
    assert r.status_code == 201, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["total_criadas"] == 2 and corpo["datas_puladas"] == ["2026-10-13"]
    datas = [c["data_hora"] for c in db_ctx.query("SELECT data_hora FROM consultas ORDER BY data_hora")]
    assert datas == ["2026-10-06 09:00:00", "2026-10-20 09:00:00"]


def test_recorrente_toda_bloqueada_nao_cria_nada(client, db_ctx):
    cen = DuasClinicas()
    _ausencia(client, cen, cen.prof_a1, data_inicio="2026-10-01", data_fim="2026-10-31",
              dia_inteiro=True, hora_inicio="", hora_fim="", dias_semana="0123456", motivo="Férias")
    r = autenticado(client, cen.gestor_a).post("/api/agenda/recorrente", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a1["id"], "data_hora": "2026-10-06 09:00:00",
        "frequencia": "semanal", "repeticoes": 3})
    assert r.status_code == 409
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM consultas")["n"] == 0


def test_reativar_consulta_cancelada_dentro_de_ausencia_da_409(client, db_ctx):
    # Revisão final: "desfazer o cancelamento" não pode furar o bloqueio.
    cen = DuasClinicas()
    cid = _agendar(client, cen.gestor_a, cen.prof_a1, "2026-10-06 12:00:00", _pac=cen.paciente_a1, duracao_min=50).get_json()["id"]
    c = autenticado(client, cen.gestor_a)
    assert c.put(f"/api/agenda/{cid}/status", json={"status": "cancelada"}).status_code == 200
    _ausencia(client, cen, cen.prof_a1)
    r = c.put(f"/api/agenda/{cid}/status", json={"status": "agendada"})
    assert r.status_code == 409 and "ausente" in r.get_json()["erro"]
    assert db_ctx.query_one("SELECT status FROM consultas WHERE id = ?", (cid,))["status"] == "cancelada"
    assert c.put(f"/api/agenda/{cid}/status", json={"status": "faltou"}).status_code == 200  # registrar desfecho continua livre
