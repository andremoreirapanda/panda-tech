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


def _missao(db_ctx, plano_id, titulo, status="pendente"):
    return db_ctx.execute("INSERT INTO missoes (plano_id, titulo, status) VALUES (?, ?, ?)", (plano_id, titulo, status))


def _dois_planos(client, db_ctx, cen):
    ids = _iniciar(client, cen)
    to = _plano(client, cen.prof_a2, ids["jornada_id"], "Terapia Ocupacional", "TO Out").get_json()["id"]
    _missao(db_ctx, ids["plano_id"], "Fono 1", "concluida")
    _missao(db_ctx, ids["plano_id"], "Fono rascunho", "rascunho")
    m_to = _missao(db_ctx, to, "TO 1")
    _missao(db_ctx, to, "TO 2")
    return ids, to, m_to


def test_bundle_traz_os_planos_ativos_e_todas_as_missoes(client, db_ctx):
    cen = DuasClinicas()
    ids, to, m_to = _dois_planos(client, db_ctx, cen)
    db_ctx.execute("INSERT INTO feedbacks_familia (missao_id, usuario_id, texto) VALUES (?, ?, 'Gostou')", (m_to, cen.resp_a1["id"]))
    d = autenticado(client, cen.prof_a1).get(f"/api/jornada/paciente/{cen.paciente_a1}").get_json()
    assert "plano_ativo" not in d
    assert [(p["titulo"], p["especialidade"], p["missoes_total"], p["missoes_concluidas"]) for p in d["planos_ativos"]] == [
        ("Fono Out", "Fonoaudiologia", 1, 1), ("TO Out", "Terapia Ocupacional", 2, 0)]
    assert [o["descricao"] for o in d["planos_ativos"][0]["objetivos"]] == ["A"]
    assert {m["titulo"]: m["plano_especialidade"] for m in d["missoes"]} == {
        "Fono 1": "Fonoaudiologia", "Fono rascunho": "Fonoaudiologia", "TO 1": "Terapia Ocupacional", "TO 2": "Terapia Ocupacional"}
    assert all(m["plano_id"] in (ids["plano_id"], to) for m in d["missoes"])
    assert (d["missoes_total"], d["missoes_concluidas"], d["progresso_pct"]) == (3, 1, 33)
    assert [f["texto"] for f in d["feedbacks"]] == ["Gostou"]
    assert "Fonoaudiologia" in d["especialidades_disponiveis"] or d["especialidades_disponiveis"] == ["Geral"]


def test_familia_nao_ve_rascunho_de_nenhum_plano(client, db_ctx):
    cen = DuasClinicas()
    _dois_planos(client, db_ctx, cen)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    d = autenticado(client, cen.resp_a1).get(f"/api/jornada/paciente/{cen.paciente_a1}").get_json()
    assert sorted(m["titulo"] for m in d["missoes"]) == ["Fono 1", "TO 1", "TO 2"]


def test_plano_encerrado_nao_entra_e_sem_plano_fica_vazio(client, db_ctx):
    cen = DuasClinicas()
    ids, to, _ = _dois_planos(client, db_ctx, cen)
    db_ctx.execute("UPDATE planos_terapeuticos SET status = 'encerrado' WHERE id IN (?, ?)", (ids["plano_id"], to))
    d = autenticado(client, cen.prof_a1).get(f"/api/jornada/paciente/{cen.paciente_a1}").get_json()
    assert (d["planos_ativos"], d["missoes"], d["progresso_pct"]) == ([], [], 0)
    sem = autenticado(client, cen.prof_a1).get(f"/api/jornada/paciente/{cen.paciente_a2}").get_json()
    assert sem["jornada"] is None and sem["especialidades_disponiveis"]


def test_semana_completa_exige_todas_as_missoes_de_todos_os_planos(client, db_ctx):
    import gamificacao_service as gs
    gs.garantir_medalhas_padrao()
    cen = DuasClinicas()
    ids, to, m_to = _dois_planos(client, db_ctx, cen)
    medalha = lambda: db_ctx.query_one(
        """SELECT 1 FROM medalhas_paciente mp JOIN medalhas m ON m.id = mp.medalha_id
           WHERE mp.paciente_id = ? AND m.nome = 'Semana Completa'""", (cen.paciente_a1,))
    db_ctx.execute("DELETE FROM missoes WHERE titulo = 'Fono rascunho'")
    db_ctx.execute("UPDATE missoes SET status = 'concluida' WHERE id = ?", (m_to,))
    gs.processar_missao_concluida(cen.paciente_a1, db_ctx.query_one("SELECT * FROM missoes WHERE id = ?", (m_to,)))
    assert medalha() is None  # "TO 2" ainda pendente
    db_ctx.execute("UPDATE missoes SET status = 'concluida' WHERE plano_id = ?", (to,))
    gs.processar_missao_concluida(cen.paciente_a1, db_ctx.query_one("SELECT * FROM missoes WHERE id = ?", (m_to,)))
    assert medalha() is not None


def test_painel_do_profissional_e_ict_somam_os_planos(client, db_ctx):
    import ict_service
    cen = DuasClinicas()
    _dois_planos(client, db_ctx, cen)
    painel = autenticado(client, cen.prof_a1).get("/api/indicadores/profissional").get_json()
    todos = painel["dentro_planejado"] + painel["baixa_adesao"] + painel["precisa_atencao"]
    assert [p["progresso_pct"] for p in todos if p["id"] == cen.paciente_a1] == [33]
    assert ict_service.calcular_ict_paciente(cen.paciente_a1)["componentes"]["adesao_missoes_pct"] == 33


def test_pdf_tem_uma_secao_por_plano(monkeypatch):
    import relatorio_service
    capturado = []
    monkeypatch.setattr(relatorio_service.SimpleDocTemplate, "build", lambda self, story, *a, **k: capturado.extend(story))
    plano = lambda t, e: {"titulo": t, "especialidade": e, "progresso_pct": 0, "missoes_concluidas": 0, "missoes_total": 0, "missoes": []}
    dados = {"paciente": {"nome": "Carla"}, "jornada": {"objetivo_principal": "Autonomia"},
             "planos_ativos": [plano("Fono Out", "Fonoaudiologia"), plano("TO Out", "Terapia Ocupacional")]}
    relatorio_service.gerar_relatorio_pdf(dados, incluir_evolucao_clinica=False)
    textos = " ".join(getattr(f, "text", "") for f in capturado)
    assert "Plano: Fono Out · Fonoaudiologia" in textos and "Plano: TO Out · Terapia Ocupacional" in textos
