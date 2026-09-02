"""
Regressão para o pedido do usuário de 02/09/2026 (agenda do profissional /
jornada da criança):

1. A frequência de uma missão semanal agora pode ser trocada depois de
   criada (antes o campo ficava travado na edição) — mas sem perder
   silenciosamente dias de check já registrados.
2. Uma missão fica bloqueada para conclusão pela família/criança depois que
   o Prazo passa (profissional/gestor/admin continuam podendo fechar
   manualmente, e sempre podem reabrir estendendo o Prazo).
3. A descrição do exercício (cadastrada na Biblioteca) agora vem junto no
   bundle da jornada, para a tela da criança poder mostrá-la.
"""
from factories import DuasClinicas, vincular_responsavel

from conftest import autenticado


# ---------------------------------------------------------------- Trocar frequência depois de criada

def test_editar_missao_troca_frequencia_sem_dias_concluidos(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (cen.paciente_a1, "Objetivo geral"),
    )
    plano_id = db_ctx.execute(
        "INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
        (jornada_id, cen.prof_a1["id"], "Plano"),
    )
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão", "tipo": "semanal", "frequencia_dias": 7,
    })
    missao_id = r.get_json()["id"]

    r = autenticado(client, cen.gestor_a).put(f"/api/jornada/missao/{missao_id}", json={
        "titulo": "Missão", "tipo": "semanal", "frequencia_dias": 14,
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert db_ctx.query_one("SELECT frequencia_dias FROM missoes WHERE id = ?", (missao_id,))["frequencia_dias"] == 14


def test_editar_missao_bloqueia_baixar_frequencia_abaixo_do_ja_concluido(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (cen.paciente_a1, "Objetivo geral"),
    )
    plano_id = db_ctx.execute(
        "INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
        (jornada_id, cen.prof_a1["id"], "Plano"),
    )
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão", "tipo": "semanal", "frequencia_dias": 10,
    })
    missao_id = r.get_json()["id"]
    db_ctx.execute("UPDATE missoes SET status = 'iniciada' WHERE id = ?", (missao_id,))
    db_ctx.execute("INSERT INTO missao_dias_concluidos (missao_id, data) VALUES (?, '2026-01-01')", (missao_id,))
    db_ctx.execute("INSERT INTO missao_dias_concluidos (missao_id, data) VALUES (?, '2026-01-02')", (missao_id,))
    db_ctx.execute("INSERT INTO missao_dias_concluidos (missao_id, data) VALUES (?, '2026-01-03')", (missao_id,))

    r = autenticado(client, cen.gestor_a).put(f"/api/jornada/missao/{missao_id}", json={
        "titulo": "Missão", "tipo": "semanal", "frequencia_dias": 2,
    })
    assert r.status_code == 409, r.get_data(as_text=True)
    assert db_ctx.query_one("SELECT frequencia_dias FROM missoes WHERE id = ?", (missao_id,))["frequencia_dias"] == 10

    # Igual ao número já cumprido é permitido (só não pode ficar abaixo).
    r = autenticado(client, cen.gestor_a).put(f"/api/jornada/missao/{missao_id}", json={
        "titulo": "Missão", "tipo": "semanal", "frequencia_dias": 3,
    })
    assert r.status_code == 200, r.get_data(as_text=True)


def test_editar_missao_bloqueia_voltar_pra_uma_vez_com_dias_ja_concluidos(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (cen.paciente_a1, "Objetivo geral"),
    )
    plano_id = db_ctx.execute(
        "INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
        (jornada_id, cen.prof_a1["id"], "Plano"),
    )
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão", "tipo": "semanal", "frequencia_dias": 7,
    })
    missao_id = r.get_json()["id"]
    db_ctx.execute("UPDATE missoes SET status = 'iniciada' WHERE id = ?", (missao_id,))
    db_ctx.execute("INSERT INTO missao_dias_concluidos (missao_id, data) VALUES (?, '2026-01-01')", (missao_id,))

    r = autenticado(client, cen.gestor_a).put(f"/api/jornada/missao/{missao_id}", json={
        "titulo": "Missão", "tipo": "diaria",
    })
    assert r.status_code == 409, r.get_data(as_text=True)
    assert db_ctx.query_one("SELECT tipo FROM missoes WHERE id = ?", (missao_id,))["tipo"] == "semanal"


def test_editar_missao_sem_mandar_tipo_preserva_frequencia_existente(client, db_ctx):
    """Chamada antiga (só edita título/descrição/etc, sem tocar em `tipo`)
    continua funcionando exatamente como antes."""
    cen = DuasClinicas()
    jornada_id = db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (cen.paciente_a1, "Objetivo geral"),
    )
    plano_id = db_ctx.execute(
        "INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
        (jornada_id, cen.prof_a1["id"], "Plano"),
    )
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão", "tipo": "semanal", "frequencia_dias": 5,
    })
    missao_id = r.get_json()["id"]

    r = autenticado(client, cen.gestor_a).put(f"/api/jornada/missao/{missao_id}", json={"titulo": "Só o título mudou"})
    assert r.status_code == 200, r.get_data(as_text=True)
    missao = db_ctx.query_one("SELECT tipo, frequencia_dias, titulo FROM missoes WHERE id = ?", (missao_id,))
    assert missao["tipo"] == "semanal"
    assert missao["frequencia_dias"] == 5
    assert missao["titulo"] == "Só o título mudou"


# ---------------------------------------------------------------- Bloqueio por prazo esgotado

def test_familia_nao_completa_missao_diaria_com_prazo_vencido(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (cen.paciente_a1, "Objetivo geral"),
    )
    plano_id = db_ctx.execute(
        "INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
        (jornada_id, cen.prof_a1["id"], "Plano"),
    )
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão vencida", "prazo": "2020-01-01",
    })
    missao_id = r.get_json()["id"]
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)

    r = autenticado(client, cen.resp_a1).post(f"/api/jornada/missao/{missao_id}/concluir")
    assert r.status_code == 409, r.get_data(as_text=True)
    assert db_ctx.query_one("SELECT status FROM missoes WHERE id = ?", (missao_id,))["status"] != "concluida"


def test_profissional_ainda_pode_completar_missao_com_prazo_vencido(client, db_ctx):
    """O bloqueio é só pra família/criança — o profissional pode registrar
    manualmente (ex.: a criança fez na sessão e esqueceram de marcar no app)."""
    cen = DuasClinicas()
    jornada_id = db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (cen.paciente_a1, "Objetivo geral"),
    )
    plano_id = db_ctx.execute(
        "INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
        (jornada_id, cen.prof_a1["id"], "Plano"),
    )
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão vencida", "prazo": "2020-01-01",
    })
    missao_id = r.get_json()["id"]

    r = autenticado(client, cen.prof_a1).post(f"/api/jornada/missao/{missao_id}/concluir")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert db_ctx.query_one("SELECT status FROM missoes WHERE id = ?", (missao_id,))["status"] == "concluida"


def test_familia_nao_marca_dia_de_missao_semanal_com_prazo_vencido(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (cen.paciente_a1, "Objetivo geral"),
    )
    plano_id = db_ctx.execute(
        "INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
        (jornada_id, cen.prof_a1["id"], "Plano"),
    )
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão semanal vencida", "tipo": "semanal", "frequencia_dias": 5, "prazo": "2020-01-01",
    })
    missao_id = r.get_json()["id"]
    db_ctx.execute("UPDATE missoes SET status = 'iniciada' WHERE id = ?", (missao_id,))
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)

    r = autenticado(client, cen.resp_a1).post(f"/api/jornada/missao/{missao_id}/concluir-dia")
    assert r.status_code == 409, r.get_data(as_text=True)
    assert db_ctx.query_one("SELECT COUNT(*) as c FROM missao_dias_concluidos WHERE missao_id = ?", (missao_id,))["c"] == 0


def test_familia_completa_normalmente_missao_com_prazo_no_futuro(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (cen.paciente_a1, "Objetivo geral"),
    )
    plano_id = db_ctx.execute(
        "INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
        (jornada_id, cen.prof_a1["id"], "Plano"),
    )
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão no prazo", "prazo": "2099-12-31",
    })
    missao_id = r.get_json()["id"]
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)

    r = autenticado(client, cen.resp_a1).post(f"/api/jornada/missao/{missao_id}/concluir")
    assert r.status_code == 200, r.get_data(as_text=True)


# ---------------------------------------------------------------- Descrição do exercício no bundle da jornada

def test_bundle_da_jornada_traz_descricao_do_exercicio(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (cen.paciente_a1, "Objetivo geral"),
    )
    plano_id = db_ctx.execute(
        "INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
        (jornada_id, cen.prof_a1["id"], "Plano"),
    )
    ex_id = db_ctx.execute(
        "INSERT INTO exercicios (organizacao_id, titulo, descricao, tipo) VALUES (?, ?, ?, 'atividade')",
        (cen.org_a, "Exercício com descrição", "Faça isso e aquilo com a criança."),
    )
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão", "exercicios_ids": [ex_id],
    })
    missao_id = r.get_json()["id"]
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)

    r = autenticado(client, cen.resp_a1).get(f"/api/jornada/paciente/{cen.paciente_a1}")
    assert r.status_code == 200, r.get_data(as_text=True)
    missao = next(m for m in r.get_json()["missoes"] if m["id"] == missao_id)
    assert missao["atividades"][0]["descricao"] == "Faça isso e aquilo com a criança."

    # E também no endpoint de detalhe isolado da missão.
    r2 = autenticado(client, cen.resp_a1).get(f"/api/jornada/missao/{missao_id}")
    assert r2.status_code == 200, r2.get_data(as_text=True)
    assert r2.get_json()["atividades"][0]["descricao"] == "Faça isso e aquilo com a criança."
