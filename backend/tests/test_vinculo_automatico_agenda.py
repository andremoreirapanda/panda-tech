"""
Vínculo automático ao agendar (spec 24/09/2026): quem atende um paciente
passa a fazer parte da equipe dele (`profissionais_pacientes`) — com isso
ganha acesso de edição (plano, missões, diário), não só de visualização.
Vale ao criar consulta (única ou recorrente) e ao reatribuir a consulta a
outro profissional; gestores não ganham vínculo (já têm acesso total).
"""
from factories import DuasClinicas

from conftest import autenticado


def _vinculo(db_ctx, profissional_id, paciente_id):
    return db_ctx.query_one(
        "SELECT * FROM profissionais_pacientes WHERE usuario_id = ? AND paciente_id = ?",
        (profissional_id, paciente_id),
    )


def test_profissional_agenda_paciente_de_outro_e_ganha_vinculo(client, db_ctx):
    cen = DuasClinicas()
    assert _vinculo(db_ctx, cen.prof_a2["id"], cen.paciente_a1) is None
    r = autenticado(client, cen.prof_a2).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "data_hora": "2026-10-01 09:00:00",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    v = _vinculo(db_ctx, cen.prof_a2["id"], cen.paciente_a1)
    assert v is not None
    assert v["principal"] == 0  # paciente já tinha o prof_a1 como principal


def test_vinculo_libera_edicao_do_paciente(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a2)
    assert c.put(f"/api/pessoas/pacientes/{cen.paciente_a1}", json={"nome": "Paciente A1"}).status_code == 403
    c.post("/api/agenda", json={"paciente_id": cen.paciente_a1, "data_hora": "2026-10-01 09:00:00"})
    r = c.put(f"/api/pessoas/pacientes/{cen.paciente_a1}", json={"nome": "Paciente A1"})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_gestor_agenda_para_profissional_e_vincula_o_profissional(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a2["id"], "data_hora": "2026-10-02 10:00:00",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    assert _vinculo(db_ctx, cen.prof_a2["id"], cen.paciente_a1) is not None
    assert _vinculo(db_ctx, cen.gestor_a["id"], cen.paciente_a1) is None


def test_consulta_marcada_para_gestor_nao_cria_vinculo(client, db_ctx):
    cen = DuasClinicas()
    # só dá pra marcar consulta para o gestor quando ele "atua como profissional"
    db_ctx.execute("UPDATE usuarios SET atua_como_profissional = 1 WHERE id = ?", (cen.gestor_a["id"],))
    r = autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.gestor_a["id"], "data_hora": "2026-10-02 11:00:00",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    assert _vinculo(db_ctx, cen.gestor_a["id"], cen.paciente_a1) is None


def test_primeiro_vinculo_do_paciente_vira_principal(client, db_ctx):
    cen = DuasClinicas()
    # paciente novo, sem ninguém na equipe
    novo = db_ctx.execute(
        "INSERT INTO pacientes (organizacao_id, nome, data_nascimento) VALUES (?, ?, ?)",
        (cen.org_a, "Paciente Novo", "2020-01-01"),
    )
    autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": novo, "profissional_id": cen.prof_a2["id"], "data_hora": "2026-10-03 09:00:00",
    })
    assert _vinculo(db_ctx, cen.prof_a2["id"], novo)["principal"] == 1


def test_agendar_de_novo_nao_duplica_vinculo(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)  # já vinculado ao paciente_a1
    for hora in ("09:00", "10:00"):
        r = c.post("/api/agenda", json={"paciente_id": cen.paciente_a1, "data_hora": f"2026-10-05 {hora}:00"})
        assert r.status_code == 201, r.get_data(as_text=True)
    total = db_ctx.query_one(
        "SELECT COUNT(*) AS n FROM profissionais_pacientes WHERE usuario_id = ? AND paciente_id = ?",
        (cen.prof_a1["id"], cen.paciente_a1),
    )["n"]
    assert total == 1


def test_agendamento_recorrente_cria_vinculo(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/agenda/recorrente", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a2["id"],
        "data_hora": "2026-10-06 14:00:00", "frequencia": "semanal", "repeticoes": 3,
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    assert _vinculo(db_ctx, cen.prof_a2["id"], cen.paciente_a1) is not None


def test_reatribuir_consulta_vincula_o_novo_profissional(client, db_ctx):
    cen = DuasClinicas()
    consulta_id = db_ctx.execute(
        "INSERT INTO consultas (paciente_id, profissional_id, data_hora) VALUES (?, ?, ?)",
        (cen.paciente_a1, cen.prof_a1["id"], "2026-10-07 09:00:00"),
    )
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{consulta_id}", json={"profissional_id": cen.prof_a2["id"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert _vinculo(db_ctx, cen.prof_a2["id"], cen.paciente_a1) is not None


def test_cancelar_consulta_mantem_vinculo(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a2)
    consulta_id = c.post("/api/agenda", json={"paciente_id": cen.paciente_a1, "data_hora": "2026-10-08 09:00:00"}).get_json()["id"]
    assert c.delete(f"/api/agenda/{consulta_id}").status_code == 200
    assert _vinculo(db_ctx, cen.prof_a2["id"], cen.paciente_a1) is not None


def test_vinculo_criado_fica_na_auditoria(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, cen.prof_a2).post("/api/agenda", json={"paciente_id": cen.paciente_a1, "data_hora": "2026-10-09 09:00:00"})
    log = db_ctx.query_one(
        "SELECT * FROM auditoria WHERE acao = 'vincular' AND entidade = 'profissional_paciente' AND entidade_id = ?",
        (cen.paciente_a1,),
    )
    assert log is not None


def test_vinculo_concorrente_nao_quebra_o_agendamento(db_ctx, monkeypatch):
    """Duplo clique em "Agendar": duas requisições passam juntas pela
    checagem "já vinculado?" e a segunda batia no UNIQUE(usuario_id,
    paciente_id) — erro 500 com a consulta já gravada. Simula a corrida
    fazendo a checagem não enxergar o vínculo que já existe."""
    from blueprints import agenda_bp as ag
    cen = DuasClinicas()  # prof_a1 já está vinculado ao paciente_a1
    consultar_de_verdade = ag.query_one

    def query_one_sem_ver_vinculo(sql, params=()):
        if "FROM profissionais_pacientes WHERE usuario_id" in sql:
            return None
        return consultar_de_verdade(sql, params)

    monkeypatch.setattr(ag, "query_one", query_one_sem_ver_vinculo)
    ag._garantir_vinculo_profissional(cen.gestor_a, cen.org_a, cen.prof_a1["id"], cen.paciente_a1)
    total = db_ctx.query_one(
        "SELECT COUNT(*) AS n FROM profissionais_pacientes WHERE usuario_id = ? AND paciente_id = ?",
        (cen.prof_a1["id"], cen.paciente_a1),
    )["n"]
    assert total == 1
