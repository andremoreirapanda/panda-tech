"""Repetição avançada na rota POST /api/agenda/recorrente (spec 09/10/2026, parte B)."""
from datetime import date, timedelta

from factories import DuasClinicas
from conftest import autenticado


def _proxima_segunda():
    hoje = date.today()
    return hoje + timedelta(days=(7 - hoje.weekday()) % 7 or 7)


SEG = _proxima_segunda()
QUA = SEG + timedelta(days=2)


def _corpo(cen, **extra):
    return {"paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a1["id"],
            "data_hora": f"{SEG.isoformat()} 09:00:00", "duracao_min": 50, **extra}


REGRA = {"frequencia": "semanal", "quantidade": 4,
         "dias": {"1": {"inicio": "09:00", "fim": "09:50"}, "3": {"inicio": "14:00", "fim": "15:00"}}}


def test_cria_serie_com_dias_e_horarios_proprios(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/agenda/recorrente", json=_corpo(cen, repeticao=REGRA))
    assert r.status_code == 201, r.get_data(as_text=True)
    d = r.get_json()
    linhas = db_ctx.query("SELECT data_hora, duracao_min, serie_recorrencia_id FROM consultas ORDER BY data_hora")
    assert [(l["data_hora"], l["duracao_min"]) for l in linhas] == [
        (f"{SEG} 09:00:00", 50), (f"{QUA} 14:00:00", 60),
        (f"{SEG + timedelta(days=7)} 09:00:00", 50), (f"{QUA + timedelta(days=7)} 14:00:00", 60)]
    assert {l["serie_recorrencia_id"] for l in linhas} == {d["serie_recorrencia_id"]} and d["total_criadas"] == 4


def test_previa_nao_cria_nada_e_marca_ausencia_e_ocupada(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    # ocupada: outra consulta na 1ª quarta; ausência: a 2ª segunda inteira
    c.post("/api/agenda", json={"paciente_id": cen.paciente_a2, "profissional_id": cen.prof_a1["id"],
                                "data_hora": f"{QUA} 14:00:00", "duracao_min": 50})
    seg2 = (SEG + timedelta(days=7)).isoformat()
    assert c.post("/api/agenda/ausencias", json={"profissional_id": cen.prof_a1["id"], "data_inicio": seg2, "data_fim": seg2,
                                                  "dia_inteiro": True, "dias_semana": "1", "motivo": "Curso"}).status_code == 201
    antes = db_ctx.query_one("SELECT COUNT(*) AS n FROM consultas")["n"]
    r = c.post("/api/agenda/recorrente", json=_corpo(cen, repeticao=REGRA, previa=True))
    assert r.status_code == 200, r.get_data(as_text=True)
    d = r.get_json()
    assert d["total"] == 4 and d["primeira"] == f"{SEG} 09:00:00" and d["ultima"] == f"{QUA + timedelta(days=7)} 14:00:00"
    assert [(x["ausente"], x["ocupada"]) for x in d["datas"]] == [(False, False), (False, True), (True, False), (False, False)]
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM consultas")["n"] == antes


def test_ausencia_pula_e_encaixe_pede_confirmacao(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    seg2 = (SEG + timedelta(days=7)).isoformat()
    c.post("/api/agenda/ausencias", json={"profissional_id": cen.prof_a1["id"], "data_inicio": seg2, "data_fim": seg2,
                                          "dia_inteiro": True, "dias_semana": "1", "motivo": "Curso"})
    c.post("/api/agenda", json={"paciente_id": cen.paciente_a2, "profissional_id": cen.prof_a1["id"],
                                "data_hora": f"{QUA} 14:00:00", "duracao_min": 50})
    r = c.post("/api/agenda/recorrente", json=_corpo(cen, repeticao=REGRA))
    assert r.status_code == 409 and r.get_json()["pode_encaixar"]
    r = c.post("/api/agenda/recorrente", json=_corpo(cen, repeticao=REGRA, encaixe=True))
    assert r.status_code == 201
    assert r.get_json()["total_criadas"] == 3 and r.get_json()["datas_puladas"] == [seg2]


def test_regra_invalida_da_400(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/agenda/recorrente",
                                              json=_corpo(cen, repeticao={"frequencia": "semanal", "dias": {}}))
    assert r.status_code == 400 and "dia" in r.get_json()["erro"]
    r = autenticado(client, cen.gestor_a).post("/api/agenda/recorrente", json=_corpo(cen, repeticao="semanal"))
    assert r.status_code == 400


def test_corpo_antigo_continua_valendo(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/agenda/recorrente", json=_corpo(cen, frequencia="quinzenal", repeticoes=3))
    assert r.status_code == 201 and r.get_json()["total_criadas"] == 3
    datas = [l["data_hora"][:10] for l in db_ctx.query("SELECT data_hora FROM consultas ORDER BY data_hora")]
    assert datas == [SEG.isoformat(), (SEG + timedelta(days=14)).isoformat(), (SEG + timedelta(days=28)).isoformat()]


def test_procedimento_vale_para_a_serie_nova(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    c.put("/api/procedimentos", json={"procedimentos": [{"nome": "Sessão", "valor": "230,00"}]})
    pid = c.get("/api/procedimentos").get_json()[0]["id"]
    assert c.post("/api/agenda/recorrente", json=_corpo(cen, repeticao=REGRA)).status_code == 400
    assert c.post("/api/agenda/recorrente", json=_corpo(cen, repeticao=REGRA, procedimento_id=pid)).status_code == 201
    assert {l["procedimento_id"] for l in db_ctx.query("SELECT procedimento_id FROM consultas")} == {pid}
