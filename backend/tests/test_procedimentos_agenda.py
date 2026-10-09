"""Procedimento no agendamento (spec 09/10/2026, parte A)."""
from datetime import date, timedelta

from factories import DuasClinicas, novo_usuario, vincular_responsavel
from conftest import autenticado

DIA = (date.today() + timedelta(days=3)).isoformat()


def _procs(client, cen, itens=None):
    itens = itens or [{"nome": "Sessão", "valor": "230,00"}, {"nome": "Avaliação", "valor": "260,00"},
                      {"nome": "Antigo", "valor": "100,00", "ativo": False}]
    assert autenticado(client, cen.gestor_a).put("/api/procedimentos", json={"procedimentos": itens}).status_code == 200
    return {p["nome"]: p for p in autenticado(client, cen.gestor_a).get("/api/procedimentos").get_json()}


def _agendar(client, cen, hora="09:00", **extra):
    return autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a1["id"],
        "data_hora": f"{DIA} {hora}:00", "duracao_min": 50, **extra})


def _consulta(db_ctx, cid):
    return db_ctx.query_one("SELECT procedimento_id, procedimento_valor_centavos FROM consultas WHERE id = ?", (cid,))


def test_obrigatorio_so_com_cadastro(client, db_ctx):
    cen = DuasClinicas()
    assert _agendar(client, cen).status_code == 201          # sem cadastro: livre
    procs = _procs(client, cen)
    r = _agendar(client, cen, hora="10:00")
    assert r.status_code == 400 and "procedimento" in r.get_json()["erro"].lower()
    r = _agendar(client, cen, hora="10:00", procedimento_id=procs["Sessão"]["id"])
    assert r.status_code == 201
    assert _consulta(db_ctx, r.get_json()["id"]) == {"procedimento_id": procs["Sessão"]["id"], "procedimento_valor_centavos": 23000}


def test_desativado_ou_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    procs = _procs(client, cen)
    assert _agendar(client, cen, procedimento_id=procs["Antigo"]["id"]).status_code == 400
    autenticado(client, cen.gestor_b).put("/api/procedimentos", json={"procedimentos": [{"nome": "B", "valor": 1}]})
    outro = autenticado(client, cen.gestor_b).get("/api/procedimentos").get_json()[0]
    assert _agendar(client, cen, procedimento_id=outro["id"]).status_code == 400
    assert _agendar(client, cen, procedimento_id="abc").status_code == 400


def test_serie_leva_o_procedimento(client, db_ctx):
    cen = DuasClinicas()
    procs = _procs(client, cen)
    corpo = {"paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a1["id"], "data_hora": f"{DIA} 09:00:00",
             "duracao_min": 50, "frequencia": "semanal", "repeticoes": 3}
    c = autenticado(client, cen.gestor_a)
    assert c.post("/api/agenda/recorrente", json=corpo).status_code == 400
    r = c.post("/api/agenda/recorrente", json={**corpo, "procedimento_id": procs["Avaliação"]["id"]})
    assert r.status_code == 201
    assert all(_consulta(db_ctx, i) == {"procedimento_id": procs["Avaliação"]["id"], "procedimento_valor_centavos": 26000}
               for i in r.get_json()["ids"])


def test_valor_guardado_nao_muda_com_o_preco(client, db_ctx):
    cen = DuasClinicas()
    procs = _procs(client, cen)
    cid = _agendar(client, cen, procedimento_id=procs["Sessão"]["id"]).get_json()["id"]
    lista = [{"id": p["id"], "nome": p["nome"], "valor": "999,00" if p["nome"] == "Sessão" else p["valor_centavos"] / 100,
              "ativo": bool(p["ativo"])} for p in procs.values()]
    assert autenticado(client, cen.gestor_a).put("/api/procedimentos", json={"procedimentos": lista}).status_code == 200
    assert _consulta(db_ctx, cid)["procedimento_valor_centavos"] == 23000


def test_editar_consulta(client, db_ctx):
    cen = DuasClinicas()
    procs = _procs(client, cen)
    cid = _agendar(client, cen, procedimento_id=procs["Sessão"]["id"]).get_json()["id"]
    c = autenticado(client, cen.gestor_a)
    db_ctx.execute("UPDATE procedimentos SET valor_centavos = 50000 WHERE id = ?", (procs["Sessão"]["id"],))
    assert c.put(f"/api/agenda/{cid}", json={"procedimento_id": procs["Sessão"]["id"], "observacoes": "x"}).status_code == 200
    assert _consulta(db_ctx, cid)["procedimento_valor_centavos"] == 23000         # mesmo procedimento: mantém
    assert c.put(f"/api/agenda/{cid}", json={"procedimento_id": procs["Avaliação"]["id"]}).status_code == 200
    assert _consulta(db_ctx, cid) == {"procedimento_id": procs["Avaliação"]["id"], "procedimento_valor_centavos": 26000}
    assert c.put(f"/api/agenda/{cid}", json={"procedimento_id": None}).status_code == 400
    assert c.put(f"/api/agenda/{cid}", json={"observacoes": "só obs"}).status_code == 200        # sem a chave: ok
    assert c.put(f"/api/agenda/{cid}/status", json={"status": "confirmada"}).status_code == 200


def test_editar_consulta_antiga_e_desativado_depois(client, db_ctx):
    cen = DuasClinicas()
    antiga = _agendar(client, cen).get_json()["id"]          # antes do cadastro
    procs = _procs(client, cen)
    c = autenticado(client, cen.gestor_a)
    assert c.put(f"/api/agenda/{antiga}", json={"data_hora": f"{DIA} 15:00:00"}).status_code == 200   # arrastar
    assert c.put(f"/api/agenda/{antiga}", json={"procedimento_id": None}).status_code == 400
    cid = _agendar(client, cen, hora="11:00", procedimento_id=procs["Sessão"]["id"]).get_json()["id"]
    db_ctx.execute("UPDATE procedimentos SET ativo = 0 WHERE id = ?", (procs["Sessão"]["id"],))
    assert c.put(f"/api/agenda/{cid}", json={"procedimento_id": procs["Sessão"]["id"], "observacoes": "y"}).status_code == 200


def test_listagem_esconde_valor_e_procedimento(client, db_ctx):
    cen = DuasClinicas()
    procs = _procs(client, cen)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    cid = _agendar(client, cen, procedimento_id=procs["Sessão"]["id"]).get_json()["id"]
    sec = novo_usuario(cen.org_a, "Sec", "sec@a.com", "secretaria")

    def item(quem):
        return next(x for x in autenticado(client, quem).get("/api/agenda").get_json() if x["id"] == cid)

    g = item(cen.gestor_a)
    assert g["procedimento_nome"] == "Sessão" and g["procedimento_valor_centavos"] == 23000
    for quem in (cen.prof_a1, sec):
        x = item(quem)
        assert x["procedimento_nome"] == "Sessão" and "procedimento_valor_centavos" not in x
    r = item(cen.resp_a1)
    assert not {"procedimento_id", "procedimento_nome", "procedimento_valor_centavos"} & set(r)
