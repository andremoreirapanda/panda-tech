"""Rodada rápida antes da parte 3b (08/10/2026): encaixe de consultas, medalha
sem rascunho e um plano ativo por especialidade garantido no banco."""
import sqlite3

import pytest

from factories import DuasClinicas

from conftest import autenticado


def _agendar(client, cen, data_hora, duracao=50, prof=None, **extra):
    prof = prof or cen.prof_a1
    return autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": prof["id"], "data_hora": data_hora,
        "duracao_min": duracao, **extra})


# ---------------------------------------------------------------- consultas sobrepostas (encaixe)

def test_sobreposta_pede_encaixe_e_com_encaixe_agenda(client, db_ctx):
    cen = DuasClinicas()
    assert _agendar(client, cen, "2026-10-13 14:00:00").status_code == 201
    r = _agendar(client, cen, "2026-10-13 14:30:00")
    assert r.status_code == 409
    corpo = r.get_json()
    assert corpo["pode_encaixar"] is True and "Paciente A1" in corpo["erro"] and "14:00" in corpo["erro"]
    assert _agendar(client, cen, "2026-10-13 14:30:00", encaixe=True).status_code == 201


def test_encostada_cancelada_ou_de_outro_profissional_nao_conflitam(client, db_ctx):
    cen = DuasClinicas()
    cid = _agendar(client, cen, "2026-10-13 14:00:00").get_json()["id"]
    assert _agendar(client, cen, "2026-10-13 14:50:00").status_code == 201          # encosta no fim
    assert _agendar(client, cen, "2026-10-13 14:10:00", prof=cen.prof_a2).status_code == 201
    autenticado(client, cen.gestor_a).put(f"/api/agenda/{cid}/status", json={"status": "cancelada"})
    assert _agendar(client, cen, "2026-10-13 14:00:00", duracao=40).status_code == 201


def test_editar_para_horario_ocupado_pede_encaixe(client, db_ctx):
    cen = DuasClinicas()
    _agendar(client, cen, "2026-10-13 14:00:00")
    outra = _agendar(client, cen, "2026-10-13 16:00:00").get_json()["id"]
    c = autenticado(client, cen.gestor_a)
    assert c.put(f"/api/agenda/{outra}", json={"observacoes": "x"}).status_code == 200   # não conflita consigo mesma
    r = c.put(f"/api/agenda/{outra}", json={"data_hora": "2026-10-13 14:20:00"})
    assert r.status_code == 409 and r.get_json()["pode_encaixar"] is True
    assert c.put(f"/api/agenda/{outra}", json={"data_hora": "2026-10-13 14:20:00", "encaixe": True}).status_code == 200


def test_recorrente_com_horario_ocupado_pede_encaixe(client, db_ctx):
    cen = DuasClinicas()
    _agendar(client, cen, "2026-10-20 09:00:00")
    corpo = {"paciente_id": cen.paciente_a2, "profissional_id": cen.prof_a1["id"], "data_hora": "2026-10-13 09:00:00",
             "frequencia": "semanal", "repeticoes": 3, "duracao_min": 50}
    c = autenticado(client, cen.gestor_a)
    r = c.post("/api/agenda/recorrente", json=corpo)
    assert r.status_code == 409 and r.get_json()["pode_encaixar"] is True and "20/10" in r.get_json()["erro"]
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM consultas")["n"] == 1
    assert c.post("/api/agenda/recorrente", json={**corpo, "encaixe": True}).status_code == 201


def test_reativar_cancelada_sobre_outra_pede_encaixe(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    cid = _agendar(client, cen, "2026-10-13 14:00:00").get_json()["id"]
    c.put(f"/api/agenda/{cid}/status", json={"status": "cancelada"})
    _agendar(client, cen, "2026-10-13 14:00:00")
    r = c.put(f"/api/agenda/{cid}/status", json={"status": "agendada"})
    assert r.status_code == 409 and r.get_json()["pode_encaixar"] is True
    assert c.put(f"/api/agenda/{cid}/status", json={"status": "agendada", "encaixe": True}).status_code == 200


def test_ausencia_continua_bloqueando_mesmo_com_encaixe(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, cen.gestor_a).post("/api/agenda/ausencias", json={
        "profissional_id": cen.prof_a1["id"], "data_inicio": "2026-10-13", "data_fim": "2026-10-13", "dia_inteiro": True,
        "dias_semana": "0123456", "motivo": "Curso"})
    r = _agendar(client, cen, "2026-10-13 14:00:00", encaixe=True)
    assert r.status_code == 409 and not r.get_json().get("pode_encaixar")


# ---------------------------------------------------------------- "Semana Completa" ignora rascunho

def test_semana_completa_ignora_missao_em_rascunho(client, db_ctx):
    import gamificacao_service as gs
    cen = DuasClinicas()
    jor = db_ctx.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, 'O')", (cen.paciente_a1,))
    plano = db_ctx.execute("""INSERT INTO planos_terapeuticos (jornada_id, profissional_id, especialidade, titulo, data_inicio)
                              VALUES (?, ?, 'Fonoaudiologia', 'P', '2026-10-01')""", (jor, cen.prof_a1["id"]))
    feita = db_ctx.execute("INSERT INTO missoes (plano_id, titulo, status) VALUES (?, 'Feita', 'concluida')", (plano,))
    db_ctx.execute("INSERT INTO missoes (plano_id, titulo, status) VALUES (?, 'Ainda escrevendo', 'rascunho')", (plano,))
    gs.processar_missao_concluida(cen.paciente_a1, db_ctx.query_one("SELECT * FROM missoes WHERE id = ?", (feita,)))
    assert db_ctx.query_one("""SELECT 1 FROM medalhas_paciente mp JOIN medalhas m ON m.id = mp.medalha_id
                               WHERE mp.paciente_id = ? AND m.nome = 'Semana Completa'""", (cen.paciente_a1,))


# ---------------------------------------------------------------- um plano ativo por especialidade (banco)

def _jornada_com_plano(db_ctx, cen, esp="Fonoaudiologia"):
    jor = db_ctx.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, 'O')", (cen.paciente_a1,))
    db_ctx.execute("""INSERT INTO planos_terapeuticos (jornada_id, profissional_id, especialidade, titulo, data_inicio)
                      VALUES (?, ?, ?, 'P1', '2026-10-01')""", (jor, cen.prof_a1["id"], esp))
    return jor


def test_banco_recusa_dois_planos_ativos_da_mesma_especialidade(client, db_ctx):
    cen = DuasClinicas()
    jor = _jornada_com_plano(db_ctx, cen)
    with pytest.raises(sqlite3.IntegrityError):
        db_ctx.execute("""INSERT INTO planos_terapeuticos (jornada_id, profissional_id, especialidade, titulo, data_inicio)
                          VALUES (?, ?, ' fonoaudiologia', 'P2', '2026-10-02')""", (jor, cen.prof_a1["id"]))
    db_ctx.get_db().rollback()
    db_ctx.execute("""INSERT INTO planos_terapeuticos (jornada_id, profissional_id, especialidade, titulo, data_inicio, status)
                      VALUES (?, ?, 'Fonoaudiologia', 'Velho', '2026-09-01', 'encerrado')""", (jor, cen.prof_a1["id"]))


def test_criar_plano_em_corrida_responde_409(client, db_ctx, monkeypatch):
    from blueprints import jornada_bp
    cen = DuasClinicas()
    jor = _jornada_com_plano(db_ctx, cen)
    original = jornada_bp.execute
    # Simula o outro clique: o UPDATE que encerra o anterior "não vê" o plano ativo.
    monkeypatch.setattr(jornada_bp, "execute",
                        lambda sql, params=(): None if "SET status='encerrado'" in sql else original(sql, params))
    r = autenticado(client, cen.prof_a1).post(f"/api/jornada/jornada/{jor}/criar-plano",
                                               json={"titulo": "P2", "objetivos": ["X"], "especialidade": "Fonoaudiologia"})
    assert r.status_code == 409


def test_migracao_encerra_duplicados_e_cria_o_indice(db_ctx, capsys):
    import migrar_plano_unico_especialidade as mig
    conn = db_ctx.get_db()
    conn.execute("DROP INDEX IF EXISTS idx_plano_ativo_especialidade")
    cen = DuasClinicas()
    jor = _jornada_com_plano(db_ctx, cen)
    novo = db_ctx.execute("""INSERT INTO planos_terapeuticos (jornada_id, profissional_id, especialidade, titulo, data_inicio)
                             VALUES (?, ?, 'fonoaudiologia', 'P2', '2026-10-02')""", (jor, cen.prof_a1["id"]))
    mig.migrar()
    mig.migrar()
    ativos = db_ctx.query("SELECT id FROM planos_terapeuticos WHERE status = 'ativo'")
    assert [p["id"] for p in ativos] == [novo]   # fica o mais novo
    nomes = {r["name"] for r in conn.execute("PRAGMA index_list(planos_terapeuticos)").fetchall()}
    assert "idx_plano_ativo_especialidade" in nomes
