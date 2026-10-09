"""Planos anteriores (encerrados) na ficha do paciente (09/10/2026)."""
from factories import DuasClinicas, vincular_responsavel

from conftest import autenticado

INICIO = {"objetivo_principal": "Autonomia", "especialidade": "Fonoaudiologia", "titulo": "Fono 1", "objetivos": ["Fala"]}


def _iniciar(client, cen):
    return autenticado(client, cen.prof_a1).post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=INICIO).get_json()


def _novo_plano(client, cen, jornada_id, titulo, especialidade="Fonoaudiologia"):
    return autenticado(client, cen.prof_a1).post(f"/api/jornada/jornada/{jornada_id}/criar-plano",
                                                json={"titulo": titulo, "objetivos": ["Y"], "especialidade": especialidade})


def _ficha(client, quem, cen):
    return autenticado(client, quem).get(f"/api/jornada/paciente/{cen.paciente_a1}").get_json()


def test_plano_encerrado_aparece_com_data_de_fim(client, db_ctx):
    cen = DuasClinicas()
    jor = _iniciar(client, cen)["jornada_id"]
    assert _novo_plano(client, cen, jor, "Fono 2").status_code == 201
    assert _novo_plano(client, cen, jor, "Fono 3").status_code == 201
    ficha = _ficha(client, cen.prof_a1, cen)
    assert [p["titulo"] for p in ficha["planos_ativos"]] == ["Fono 3"]
    anteriores = ficha["planos_encerrados"]
    assert [p["titulo"] for p in anteriores] == ["Fono 2", "Fono 1"]          # mais recente primeiro
    assert all(p["data_fim"] for p in anteriores)
    assert anteriores[1]["objetivos"][0]["descricao"] == "Fala"
    assert {"missoes", "progresso_pct", "missoes_total"} <= set(anteriores[0])


def test_outra_especialidade_nao_encerra(client, db_ctx):
    cen = DuasClinicas()
    jor = _iniciar(client, cen)["jornada_id"]
    _novo_plano(client, cen, jor, "TO 1", "Terapia Ocupacional")
    assert _ficha(client, cen.gestor_a, cen)["planos_encerrados"] == []


def test_familia_nao_recebe_planos_anteriores(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    jor = _iniciar(client, cen)["jornada_id"]
    _novo_plano(client, cen, jor, "Fono 2")
    assert _ficha(client, cen.resp_a1, cen).get("planos_encerrados", []) == []


def test_sem_jornada_ativa_ainda_mostra_os_anteriores(client, db_ctx):
    cen = DuasClinicas()
    jor = _iniciar(client, cen)["jornada_id"]
    _novo_plano(client, cen, jor, "Fono 2")
    db_ctx.execute("UPDATE jornadas SET status = 'encerrada' WHERE id = ?", (jor,))
    ficha = _ficha(client, cen.gestor_a, cen)
    assert ficha["jornada"] is None
    assert [p["titulo"] for p in ficha["planos_encerrados"]] == ["Fono 1"]
