"""Diário por paciente (spec 08/10/2026)."""
from factories import DuasClinicas, vincular_responsavel

from conftest import autenticado


def _jornada(db_ctx, paciente_id):
    return db_ctx.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, 'O')", (paciente_id,))


def test_cria_e_lista_diario_sem_jornada(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)
    r = c.post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "Sessão 1"})
    assert r.status_code == 201, r.get_data(as_text=True)
    linha = db_ctx.query_one("SELECT paciente_id, jornada_id FROM diarios_terapeuticos WHERE id = ?", (r.get_json()["id"],))
    assert linha == {"paciente_id": cen.paciente_a1, "jornada_id": None}
    lista = c.get(f"/api/diario/paciente/{cen.paciente_a1}").get_json()
    assert [d["evolucao_clinica"] for d in lista] == ["Sessão 1"]


def test_com_jornada_grava_as_duas_colunas(client, db_ctx):
    cen = DuasClinicas()
    jor = _jornada(db_ctx, cen.paciente_a1)
    r = autenticado(client, cen.prof_a1).post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "E"})
    assert db_ctx.query_one("SELECT jornada_id FROM diarios_terapeuticos WHERE id = ?", (r.get_json()["id"],))["jornada_id"] == jor


def test_familia_ve_so_compartilhado_e_sem_evolucao(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    c = autenticado(client, cen.prof_a1)
    c.post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "Técnico", "mensagem_familia": "Oi"})
    c.post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "Privado", "compartilhado_familia": False})
    lista = autenticado(client, cen.resp_a1).get(f"/api/diario/paciente/{cen.paciente_a1}").get_json()
    assert len(lista) == 1 and lista[0]["evolucao_clinica"] is None and lista[0]["mensagem_familia"] == "Oi"


def test_outra_clinica_nao_le_nem_cria(client, db_ctx):
    cen = DuasClinicas()
    assert autenticado(client, cen.prof_b1).post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "x"}).status_code == 403
    assert autenticado(client, cen.resp_b1).get(f"/api/diario/paciente/{cen.paciente_a1}").status_code == 403


def test_consulta_de_outro_paciente_da_400(client, db_ctx):
    cen = DuasClinicas()
    cid = db_ctx.execute("INSERT INTO consultas (paciente_id, profissional_id, data_hora) VALUES (?, ?, '2026-10-08 09:00:00')",
                         (cen.paciente_a2, cen.prof_a1["id"]))
    c = autenticado(client, cen.prof_a1)
    assert c.post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "x", "consulta_id": cid}).status_code == 400
    assert c.post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "x", "consulta_id": 99999}).status_code == 400
    ok = c.post(f"/api/diario/paciente/{cen.paciente_a2}", json={"evolucao_clinica": "x", "consulta_id": cid})
    assert ok.status_code == 201


def test_rotas_antigas_por_jornada_continuam(client, db_ctx):
    cen = DuasClinicas()
    jor = _jornada(db_ctx, cen.paciente_a1)
    c = autenticado(client, cen.prof_a1)
    c.post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "Antes da jornada"})
    assert c.post(f"/api/diario/jornada/{jor}", json={"evolucao_clinica": "Pela jornada"}).status_code == 201
    textos = {d["evolucao_clinica"] for d in c.get(f"/api/diario/jornada/{jor}").get_json()}
    assert textos == {"Antes da jornada", "Pela jornada"}


def test_diario_antigo_sem_paciente_id_continua_acessivel(client, db_ctx):
    cen = DuasClinicas()
    jor = _jornada(db_ctx, cen.paciente_a1)
    did = db_ctx.execute("INSERT INTO diarios_terapeuticos (jornada_id, profissional_id, evolucao_clinica) VALUES (?, ?, 'Velho')",
                         (jor, cen.prof_a1["id"]))
    c = autenticado(client, cen.prof_a1)
    assert c.get(f"/api/diario/{did}").status_code == 200
    assert c.put(f"/api/diario/{did}", json={"evolucao_clinica": "Corrigido"}).status_code == 200
    assert autenticado(client, cen.gestor_b).get(f"/api/diario/{did}").status_code == 403
    c = autenticado(client, cen.prof_a1)  # o cliente é um só: volta a ser a profissional
    assert [d["evolucao_clinica"] for d in c.get(f"/api/diario/paciente/{cen.paciente_a1}").get_json()] == ["Corrigido"]
