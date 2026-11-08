"""Financeiro etapa 1, task 3: especialidade na consulta e acordos de pagamento."""
import pytest

import db
import planos_padrao
import acordos_service
from factories import DuasClinicas, novo_usuario

from conftest import autenticado


def _cenario(db_ctx):
    cen = DuasClinicas()
    planos_padrao.criar_planos_padrao_para_teste()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id IN (?, ?)", (cen.org_a, cen.org_b))
    db_ctx.execute("UPDATE usuarios SET especialidade = 'Fonoaudiologia' WHERE id = ?", (cen.prof_a1["id"],))
    db_ctx.execute("UPDATE usuarios SET especialidade = 'Terapia Ocupacional' WHERE id = ?", (cen.prof_a2["id"],))
    return cen


def _agendar(client, cen, quem, data_hora, prof=None):
    r = autenticado(client, quem).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": (prof or cen.prof_a1)["id"], "data_hora": data_hora})
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["id"]


def _esp(cid):
    return db.query_one("SELECT especialidade FROM consultas WHERE id = ?", (cid,))["especialidade"]


def _sessao(cen, esp="Fonoaudiologia", data="2026-10-05 09:00:00", status="realizada", prof=None):
    return db.execute(
        "INSERT INTO consultas (paciente_id, profissional_id, data_hora, status, especialidade) VALUES (?, ?, ?, ?, ?)",
        (cen.paciente_a1, (prof or cen.prof_a1)["id"], data, status, esp))


def test_consulta_grava_especialidade_de_quem_atende(client, db_ctx):
    cen = _cenario(db_ctx)
    c = _agendar(client, cen, cen.gestor_a, "2030-03-04 10:00:00")
    assert _esp(c) == "Fonoaudiologia"
    r = autenticado(client, cen.gestor_a).post("/api/agenda/recorrente", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a1["id"],
        "data_hora": "2030-04-01 10:00:00", "frequencia": "semanal", "repeticoes": 2})
    assert r.status_code == 201, r.get_data(as_text=True)
    ids = r.get_json().get("ids") or r.get_json().get("ids_criados")
    assert ids and all(_esp(i) == "Fonoaudiologia" for i in ids)
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{c}", json={"profissional_id": cen.prof_a2["id"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert _esp(c) == "Terapia Ocupacional"


def test_gestor_sem_especialidade_vira_geral(client, db_ctx):
    cen = _cenario(db_ctx)
    db_ctx.execute("UPDATE usuarios SET atua_como_profissional = 1 WHERE id = ?", (cen.gestor_a["id"],))
    c = _agendar(client, cen, cen.gestor_a, "2030-03-05 10:00:00", prof=cen.gestor_a)
    assert _esp(c) == "Geral"


def test_criar_acordo_avulsa_mensal(client, db_ctx):
    cen = _cenario(db_ctx)
    cl = autenticado(client, cen.gestor_a)
    r = cl.post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos",
                json={"tipo": "avulsa", "ciclo": "quinzenal", "especialidade": "Fonoaudiologia", "vence_dias": 3})
    assert r.status_code == 201, r.get_data(as_text=True)
    r = cl.post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos",
                json={"tipo": "mensalidade", "especialidade": "Terapia Ocupacional",
                      "valor_centavos": 40000, "dia_vencimento": 10})
    assert r.status_code == 201
    lista = cl.get(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos").get_json()
    assert len(lista) == 2 and all(a["sessoes_usadas"] is None for a in lista)


def test_criar_pacote_cria_parcelas(client, db_ctx):
    cen = _cenario(db_ctx)
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos", json={
        "tipo": "pacote", "especialidade": "*", "sessoes_total": 10, "valor_centavos": 100000,
        "parcelas": 3, "primeiro_vencimento": "2026-12-10"})
    assert r.status_code == 201, r.get_data(as_text=True)
    ps = db.query("SELECT * FROM cobrancas WHERE acordo_id = ? ORDER BY vencimento", (r.get_json()["id"],))
    assert [(p["vencimento"], p["valor_centavos"]) for p in ps] == [
        ("2026-12-10", 33334), ("2027-01-10", 33333), ("2027-02-10", 33333)]
    assert all(p["tipo"] == "pacote" and p["status"] == "pendente" and p["organizacao_id"] == cen.org_a for p in ps)
    lista = autenticado(client, cen.gestor_a).get(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos").get_json()
    assert lista[0]["sessoes_usadas"] == 0


def test_acordo_duplicado_409(client, db_ctx):
    cen = _cenario(db_ctx)
    cl = autenticado(client, cen.gestor_a)
    corpo = {"tipo": "avulsa", "ciclo": "consulta", "especialidade": "Fonoaudiologia"}
    assert cl.post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos", json=corpo).status_code == 201
    corpo["especialidade"] = " fonoaudiologia "
    r = cl.post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos", json=corpo)
    assert r.status_code == 409


@pytest.mark.parametrize("corpo", [
    {"ciclo": "consulta"},
    {"tipo": "mensalidade", "valor_centavos": 1000, "dia_vencimento": 31},
    {"tipo": "pacote", "valor_centavos": 1000, "parcelas": 1, "primeiro_vencimento": "2026-12-10"},
    {"tipo": "avulsa", "ciclo": "consulta", "inicio": "2026-10-10", "fim": "2026-10-01"},
    {"tipo": "avulsa"},
])
def test_validacao_400(client, db_ctx, corpo):
    cen = _cenario(db_ctx)
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos", json=corpo)
    assert r.status_code == 400
    assert db.query_one("SELECT COUNT(*) AS n FROM acordos_pagamento")["n"] == 0


def test_profissional_403(client, db_ctx):
    cen = _cenario(db_ctx)
    r = autenticado(client, cen.prof_a1).get(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos")
    assert r.status_code == 403


def test_responsavel_403(client, db_ctx):
    cen = _cenario(db_ctx)
    r = autenticado(client, cen.resp_a1).post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos",
                                              json={"tipo": "avulsa", "ciclo": "consulta"})
    assert r.status_code == 403


def test_secretaria_pode(client, db_ctx):
    cen = _cenario(db_ctx)
    sec = novo_usuario(cen.org_a, "Sec", "sec@a.com", "secretaria")
    r = autenticado(client, sec).post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos",
                                      json={"tipo": "avulsa", "ciclo": "mensal"})
    assert r.status_code == 201, r.get_data(as_text=True)


def test_outra_clinica_404(client, db_ctx):
    cen = _cenario(db_ctx)
    cl = autenticado(client, cen.gestor_b)
    assert cl.get(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos").status_code == 404
    assert cl.post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos",
                   json={"tipo": "avulsa", "ciclo": "mensal"}).status_code == 404
    assert cl.get(f"/api/financeiro/paciente/{cen.paciente_a1}/sem-acordo").status_code == 404
    aid = db.execute("INSERT INTO acordos_pagamento (organizacao_id, paciente_id, especialidade, tipo, ciclo, inicio)"
                     " VALUES (?, ?, 'Geral', 'avulsa', 'mensal', '2026-01-01')", (cen.org_a, cen.paciente_a1))
    assert cl.put(f"/api/financeiro/acordos/{aid}", json={"vence_dias": 2}).status_code == 404
    assert cl.post(f"/api/financeiro/acordos/{aid}/encerrar", json={"fim": "2026-12-01"}).status_code == 404


def test_sem_modulo_403(client, db_ctx):
    cen = _cenario(db_ctx)
    db_ctx.execute("UPDATE organizacoes SET plano = 'starter' WHERE id = ?", (cen.org_a,))
    r = autenticado(client, cen.gestor_a).get(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos")
    assert r.status_code == 403


def test_incluir_consultas_sem_acordo(client, db_ctx):
    cen = _cenario(db_ctx)
    s1 = _sessao(cen, data="2026-09-01 09:00:00")
    s2 = _sessao(cen, data="2026-10-05 09:00:00")
    outra_esp = _sessao(cen, esp="Terapia Ocupacional", data="2026-10-06 09:00:00", prof=cen.prof_a2)
    _sessao(cen, data="2999-01-01 09:00:00", status="agendada")
    cl = autenticado(client, cen.gestor_a)
    r = cl.get(f"/api/financeiro/paciente/{cen.paciente_a1}/sem-acordo?especialidade=Fonoaudiologia")
    assert [s["consulta_id"] for s in r.get_json()] == [s1, s2]
    assert set(r.get_json()[0]) >= {"consulta_id", "paciente_id", "paciente_nome", "data_hora",
                                    "profissional_nome", "especialidade", "procedimento_nome",
                                    "procedimento_valor_centavos"}
    r = cl.post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos", json={
        "tipo": "avulsa", "ciclo": "consulta", "especialidade": "Fonoaudiologia",
        "inicio": "2026-10-01", "incluir_consultas": [s1]})
    assert r.status_code == 201, r.get_data(as_text=True)
    a = db.query_one("SELECT * FROM acordos_pagamento WHERE id = ?", (r.get_json()["id"],))
    assert a["inicio"] == "2026-10-01"   # incluir sessão não recua o início do acordo
    r = cl.get(f"/api/financeiro/paciente/{cen.paciente_a1}/sem-acordo")
    # s1 entrou (marcada); s2, na vigência mas desmarcada, continua sem acordo
    assert [s["consulta_id"] for s in r.get_json()] == [s2, outra_esp]
    # sessão de outra especialidade não entra no acordo
    r = cl.post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos", json={
        "tipo": "avulsa", "ciclo": "consulta", "especialidade": "Psicologia", "incluir_consultas": [outra_esp]})
    assert r.status_code == 400


def test_sem_acordo_respeita_falta_e_decisao(client, db_ctx):
    cen = _cenario(db_ctx)
    falta = _sessao(cen, status="faltou", data="2026-10-01 09:00:00")
    nao = _sessao(cen, data="2026-10-02 09:00:00")
    db.execute("INSERT INTO consulta_decisao_cobranca (consulta_id, decisao) VALUES (?, 'nao_cobrar')", (nao,))
    hoje = "2026-11-08"
    assert acordos_service.sessoes_sem_acordo(cen.org_a, cen.paciente_a1, None, hoje) == []
    db.execute("UPDATE organizacoes SET fin_cobrar_falta = 1 WHERE id = ?", (cen.org_a,))
    assert [s["consulta_id"] for s in acordos_service.sessoes_sem_acordo(cen.org_a, None, None, hoje)] == [falta]


def test_encerrar_acordo(client, db_ctx):
    cen = _cenario(db_ctx)
    cl = autenticado(client, cen.gestor_a)
    aid = cl.post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos",
                  json={"tipo": "avulsa", "ciclo": "mensal", "inicio": "2026-01-01"}).get_json()["id"]
    r = cl.post(f"/api/financeiro/acordos/{aid}/encerrar", json={"fim": "2026-06-30"})
    assert r.status_code == 200
    a = db.query_one("SELECT * FROM acordos_pagamento WHERE id = ?", (aid,))
    assert (a["status"], a["fim"]) == ("encerrado", "2026-06-30") and a["encerrado_em"]
    assert cl.post(f"/api/financeiro/acordos/{aid}/encerrar", json={"fim": "2026-07-30"}).status_code == 409
    r = cl.post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos",
                json={"tipo": "avulsa", "ciclo": "mensal", "inicio": "2026-07-01"})
    assert r.status_code == 201


def test_atualizar_mensalidade(client, db_ctx):
    cen = _cenario(db_ctx)
    cl = autenticado(client, cen.gestor_a)
    aid = cl.post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos", json={
        "tipo": "mensalidade", "valor_centavos": 10000, "dia_vencimento": 5}).get_json()["id"]
    r = cl.put(f"/api/financeiro/acordos/{aid}", json={"valor_centavos": 12000, "tipo": "avulsa", "especialidade": "X"})
    assert r.status_code == 200
    a = db.query_one("SELECT * FROM acordos_pagamento WHERE id = ?", (aid,))
    assert a["valor_centavos"] == 12000 and a["tipo"] == "mensalidade" and a["especialidade"] == "Geral"


def test_auditoria_registrada(client, db_ctx):
    cen = _cenario(db_ctx)
    cl = autenticado(client, cen.gestor_a)
    aid = cl.post(f"/api/financeiro/paciente/{cen.paciente_a1}/acordos",
                  json={"tipo": "avulsa", "ciclo": "mensal"}).get_json()["id"]
    cl.post(f"/api/financeiro/acordos/{aid}/encerrar", json={})
    acoes = [r["acao"] for r in db.query(
        "SELECT acao FROM auditoria WHERE entidade = 'acordo_pagamento' AND entidade_id = ? ORDER BY id", (aid,))]
    assert acoes == ["criar", "encerrar"]
