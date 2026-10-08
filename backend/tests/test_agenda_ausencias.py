"""Rotas das ausências da agenda (spec 07/10/2026)."""
from factories import DuasClinicas, novo_usuario

from conftest import autenticado

ALMOCO = {"data_inicio": "2026-10-05", "data_fim": "", "dia_inteiro": False,
          "hora_inicio": "12:00", "hora_fim": "13:00", "dias_semana": "12345", "motivo": "Almoço"}


def _criar(client, usuario, **extra):
    return autenticado(client, usuario).post("/api/agenda/ausencias", json={**ALMOCO, **extra})


def test_profissional_lanca_a_propria_e_ignora_outro_id(client, db_ctx):
    cen = DuasClinicas()
    r = _criar(client, cen.prof_a1)
    assert r.status_code == 201, r.get_data(as_text=True)
    linha = db_ctx.query_one("SELECT * FROM ausencias_profissional WHERE id = ?", (r.get_json()["id"],))
    assert linha["profissional_id"] == cen.prof_a1["id"] and linha["organizacao_id"] == cen.org_a
    r2 = _criar(client, cen.prof_a1, profissional_id=cen.prof_a2["id"])
    assert r2.status_code == 403


def test_gestor_e_secretaria_lancam_para_qualquer_profissional(client, db_ctx):
    cen = DuasClinicas()
    sec = novo_usuario(cen.org_a, "Secretária A", "sec@a.com", "secretaria")
    assert _criar(client, cen.gestor_a, profissional_id=cen.prof_a2["id"]).status_code == 201
    assert _criar(client, sec, profissional_id=cen.prof_a1["id"]).status_code == 201


def test_nao_lanca_para_profissional_de_outra_clinica_ou_excluido(client, db_ctx):
    cen = DuasClinicas()
    assert _criar(client, cen.gestor_a, profissional_id=cen.prof_b1["id"]).status_code == 400
    db_ctx.execute("UPDATE usuarios SET excluido_em = '2026-10-01' WHERE id = ?", (cen.prof_a2["id"],))
    assert _criar(client, cen.gestor_a, profissional_id=cen.prof_a2["id"]).status_code == 400


def test_validacao_devolve_400(client, db_ctx):
    cen = DuasClinicas()
    r = _criar(client, cen.prof_a1, hora_fim="11:00")
    assert r.status_code == 400 and "fim" in r.get_json()["erro"]


def test_get_devolve_ocorrencias_e_pode_editar(client, db_ctx):
    cen = DuasClinicas()
    _criar(client, cen.prof_a1)
    _criar(client, cen.gestor_a, profissional_id=cen.prof_a2["id"], motivo="Curso")
    r = autenticado(client, cen.gestor_a).get("/api/agenda/ausencias?inicio=2026-10-04&fim=2026-10-10")
    assert r.status_code == 200
    itens = r.get_json()
    assert len(itens) == 10  # 5 dias x 2 profissionais
    assert all(i["pode_editar"] for i in itens)
    assert {i["profissional_nome"] for i in itens} == {"Prof A1", "Prof A2"}


def test_ausencia_sem_fim_aparece_no_futuro(client, db_ctx):
    cen = DuasClinicas()
    _criar(client, cen.prof_a1)
    r = autenticado(client, cen.prof_a1).get("/api/agenda/ausencias?inicio=2030-03-03&fim=2030-03-09")
    assert len(r.get_json()) == 5


def test_profissional_comum_ve_so_as_dele(client, db_ctx):
    cen = DuasClinicas()
    _criar(client, cen.prof_a1)
    _criar(client, cen.gestor_a, profissional_id=cen.prof_a2["id"])
    itens = autenticado(client, cen.prof_a1).get("/api/agenda/ausencias?inicio=2026-10-04&fim=2026-10-10").get_json()
    assert {i["profissional_id"] for i in itens} == {cen.prof_a1["id"]}


def test_permissao_total_ve_todas_mas_so_edita_as_dele(client, db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("UPDATE usuarios SET agenda_permissao_total = 1 WHERE id = ?", (cen.prof_a1["id"],))
    cen.prof_a1["agenda_permissao_total"] = 1
    id_a2 = _criar(client, cen.gestor_a, profissional_id=cen.prof_a2["id"]).get_json()["id"]
    itens = autenticado(client, cen.prof_a1).get("/api/agenda/ausencias?inicio=2026-10-04&fim=2026-10-10").get_json()
    assert {i["profissional_id"] for i in itens} == {cen.prof_a2["id"]}
    assert not any(i["pode_editar"] for i in itens)
    assert autenticado(client, cen.prof_a1).put(f"/api/agenda/ausencias/{id_a2}", json=ALMOCO).status_code == 403
    assert autenticado(client, cen.prof_a1).delete(f"/api/agenda/ausencias/{id_a2}").status_code == 403


def test_responsavel_nao_ve(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.resp_a1).get("/api/agenda/ausencias?inicio=2026-10-04&fim=2026-10-10")
    assert r.status_code == 403


def test_intervalo_invalido_ou_longo(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    assert c.get("/api/agenda/ausencias?inicio=2026-10-10&fim=2026-10-04").status_code == 400
    assert c.get("/api/agenda/ausencias?inicio=2026-01-01&fim=2026-03-31").status_code == 400
    assert c.get("/api/agenda/ausencias?inicio=x&fim=y").status_code == 400


def test_outra_clinica_nao_edita_nem_apaga(client, db_ctx):
    cen = DuasClinicas()
    id_a = _criar(client, cen.prof_a1).get_json()["id"]
    assert autenticado(client, cen.gestor_b).put(f"/api/agenda/ausencias/{id_a}", json=ALMOCO).status_code == 404
    assert autenticado(client, cen.gestor_b).delete(f"/api/agenda/ausencias/{id_a}").status_code == 404


def test_editar_e_apagar(client, db_ctx):
    cen = DuasClinicas()
    id_a = _criar(client, cen.prof_a1).get_json()["id"]
    r = autenticado(client, cen.prof_a1).put(f"/api/agenda/ausencias/{id_a}", json={**ALMOCO, "motivo": "Almoço longo", "hora_fim": "14:00"})
    assert r.status_code == 200
    assert db_ctx.query_one("SELECT hora_fim, motivo FROM ausencias_profissional WHERE id = ?", (id_a,)) == {"hora_fim": "14:00", "motivo": "Almoço longo"}
    assert autenticado(client, cen.gestor_a).delete(f"/api/agenda/ausencias/{id_a}").status_code == 200
    assert db_ctx.query_one("SELECT 1 FROM ausencias_profissional WHERE id = ?", (id_a,)) is None


def test_lista_consultas_ja_marcadas_no_periodo(client, db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("""INSERT INTO consultas (paciente_id, profissional_id, data_hora, duracao_min)
                      VALUES (?, ?, '2099-10-05 12:30:00', 50)""", (cen.paciente_a1, cen.prof_a1["id"]))
    db_ctx.execute("""INSERT INTO consultas (paciente_id, profissional_id, data_hora, duracao_min)
                      VALUES (?, ?, '2099-10-05 15:00:00', 50)""", (cen.paciente_a1, cen.prof_a1["id"]))
    r = _criar(client, cen.prof_a1, data_inicio="2099-10-05", data_fim="2099-10-09")
    lista = r.get_json()["consultas_no_periodo"]
    assert [c["data_hora"] for c in lista] == ["2099-10-05 12:30:00"]
    assert lista[0]["paciente_nome"] == "Paciente A1"
