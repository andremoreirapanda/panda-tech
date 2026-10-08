"""Planos terapêuticos por especialidade (spec 08/10/2026)."""
from factories import DuasClinicas, novo_usuario, vincular_responsavel

from conftest import autenticado

INICIO = {"objetivo_principal": "Autonomia", "especialidade": "Fonoaudiologia", "titulo": "Fono Out", "objetivos": ["A"]}


def _iniciar(client, cen):
    return autenticado(client, cen.prof_a1).post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=INICIO).get_json()


def _plano(client, usuario, jornada_id, especialidade, titulo="P"):
    return autenticado(client, usuario).post(f"/api/jornada/jornada/{jornada_id}/criar-plano",
                                             json={"titulo": titulo, "objetivos": ["X"], "especialidade": especialidade})


def _status(db_ctx):
    return {r["titulo"]: (r["especialidade"], r["status"]) for r in db_ctx.query("SELECT titulo, especialidade, status FROM planos_terapeuticos")}


def test_especialidade_obrigatoria_e_limitada(client, db_ctx):
    cen = DuasClinicas()
    jor = _iniciar(client, cen)["jornada_id"]
    assert _plano(client, cen.prof_a1, jor, "").status_code == 400
    assert _plano(client, cen.prof_a1, jor, "x" * 61).status_code == 400
    r = autenticado(client, cen.prof_a1).post(f"/api/jornada/paciente/{cen.paciente_a2}/iniciar", json={**INICIO, "especialidade": " "})
    assert r.status_code == 400
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM jornadas WHERE paciente_id = ?", (cen.paciente_a2,))["n"] == 0


def test_iniciar_grava_especialidade_do_primeiro_plano(client, db_ctx):
    cen = DuasClinicas()
    _iniciar(client, cen)
    assert _status(db_ctx) == {"Fono Out": ("Fonoaudiologia", "ativo")}


def test_planos_de_especialidades_diferentes_convivem(client, db_ctx):
    cen = DuasClinicas()
    jor = _iniciar(client, cen)["jornada_id"]
    assert _plano(client, cen.prof_a2, jor, "Terapia Ocupacional", "TO Out").status_code == 201
    assert _status(db_ctx) == {"Fono Out": ("Fonoaudiologia", "ativo"), "TO Out": ("Terapia Ocupacional", "ativo")}


def test_novo_plano_encerra_so_a_mesma_especialidade(client, db_ctx):
    cen = DuasClinicas()
    jor = _iniciar(client, cen)["jornada_id"]
    _plano(client, cen.prof_a2, jor, "Terapia Ocupacional", "TO Out")
    assert _plano(client, cen.prof_a1, jor, "Fonoaudiologia", "Fono Nov").status_code == 201
    assert _status(db_ctx) == {"Fono Out": ("Fonoaudiologia", "encerrado"), "TO Out": ("Terapia Ocupacional", "ativo"),
                               "Fono Nov": ("Fonoaudiologia", "ativo")}


def test_grafias_diferentes_sao_especialidades_distintas(client, db_ctx):
    cen = DuasClinicas()
    jor = _iniciar(client, cen)["jornada_id"]
    assert _plano(client, cen.prof_a1, jor, "fonoaudiologia", "fono minúsculo").status_code == 201
    assert _status(db_ctx)["Fono Out"] == ("Fonoaudiologia", "ativo")


def test_especialidades_disponiveis(client, db_ctx):
    from blueprints.jornada_bp import especialidades_disponiveis
    cen = DuasClinicas()
    db_ctx.execute("UPDATE organizacoes SET especialidades_json = '[\"Psicologia\", \"Fonoaudiologia\"]' WHERE id = ?", (cen.org_a,))
    db_ctx.execute("UPDATE usuarios SET especialidade = 'Fonoaudiologia' WHERE id = ?", (cen.prof_a1["id"],))
    db_ctx.execute("UPDATE usuarios SET especialidade = 'Terapia Ocupacional' WHERE id = ?", (cen.prof_a2["id"],))
    db_ctx.execute("UPDATE usuarios SET especialidade = 'Musicoterapia' WHERE id = ?", (cen.prof_b1["id"],))
    novo_usuario(cen.org_a, "Arquivada", "arq@a.com", "profissional", especialidade="Fisioterapia", ativo=0)
    assert especialidades_disponiveis(cen.org_a) == ["Fonoaudiologia", "Psicologia", "Terapia Ocupacional"]
    org_vazia = db_ctx.execute("INSERT INTO organizacoes (nome) VALUES ('Vazia')")
    assert especialidades_disponiveis(org_vazia) == ["Geral"]
