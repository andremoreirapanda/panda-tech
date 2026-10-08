"""Iniciar jornada num passo só e editar objetivo principal (spec 08/10/2026)."""
from factories import DuasClinicas

from conftest import autenticado

CORPO = {"objetivo_principal": "Falar com autonomia", "especialidade": "Fonoaudiologia", "titulo": "Plano Out/2026",
         "objetivos": ["Vocabulário", "Fonema /r/"]}


def test_iniciar_cria_jornada_plano_e_objetivos(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.prof_a1).post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=CORPO)
    assert r.status_code == 201, r.get_data(as_text=True)
    ids = r.get_json()
    assert db_ctx.query_one("SELECT objetivo_principal FROM jornadas WHERE id = ?", (ids["jornada_id"],))["objetivo_principal"] == "Falar com autonomia"
    assert db_ctx.query_one("SELECT titulo, jornada_id FROM planos_terapeuticos WHERE id = ?", (ids["plano_id"],)) == {"titulo": "Plano Out/2026", "jornada_id": ids["jornada_id"]}
    assert [o["descricao"] for o in db_ctx.query("SELECT descricao FROM objetivos_terapeuticos WHERE plano_id = ? ORDER BY id", (ids["plano_id"],))] == ["Vocabulário", "Fonema /r/"]


def test_iniciar_valida_tudo_antes_de_gravar(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)
    for ruim in ({**CORPO, "objetivo_principal": " "}, {**CORPO, "titulo": ""}, {**CORPO, "objetivos": ["  "]},
                 {**CORPO, "objetivos": []}, {**CORPO, "objetivo_principal": "x" * 301}, {**CORPO, "titulo": "x" * 121}):
        assert c.post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=ruim).status_code == 400, ruim
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM jornadas")["n"] == 0


def test_iniciar_com_jornada_ativa_da_409_e_outra_clinica_403(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)
    assert c.post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=CORPO).status_code == 201
    assert c.post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=CORPO).status_code == 409
    assert autenticado(client, cen.prof_b1).post(f"/api/jornada/paciente/{cen.paciente_a2}/iniciar", json=CORPO).status_code == 403


def test_editar_objetivo_principal(client, db_ctx):
    cen = DuasClinicas()
    jor = autenticado(client, cen.prof_a1).post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=CORPO).get_json()["jornada_id"]
    c = autenticado(client, cen.prof_a2)
    assert c.put(f"/api/jornada/jornada/{jor}", json={"objetivo_principal": "Novo objetivo"}).status_code == 200
    assert db_ctx.query_one("SELECT objetivo_principal FROM jornadas WHERE id = ?", (jor,))["objetivo_principal"] == "Novo objetivo"
    assert c.put(f"/api/jornada/jornada/{jor}", json={"objetivo_principal": "  "}).status_code == 400
    assert c.put("/api/jornada/jornada/99999", json={"objetivo_principal": "X"}).status_code == 404
    assert autenticado(client, cen.gestor_b).put(f"/api/jornada/jornada/{jor}", json={"objetivo_principal": "X"}).status_code == 403
