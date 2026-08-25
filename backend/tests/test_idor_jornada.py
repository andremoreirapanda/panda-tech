"""
Regressão para o achado de IDOR na Jornada (auditoria de segurança de
25/08/2026): uma missão só pode referenciar exercícios públicos (acervo da
plataforma) ou do acervo da própria clínica — nunca do acervo privado de
outra clínica.
"""
from factories import DuasClinicas

from conftest import autenticado


def _preparar_jornada(db_ctx, cen):
    jornada_id = db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (cen.paciente_a1, "Objetivo geral"),
    )
    plano_id = db_ctx.execute(
        "INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, ?)",
        (jornada_id, cen.prof_a1["id"], "Plano 1", "2026-01-01"),
    )
    ex_publico = db_ctx.execute("INSERT INTO exercicios (organizacao_id, titulo, tipo) VALUES (NULL, ?, 'atividade')", ("Exercício Público",))
    ex_org_a = db_ctx.execute("INSERT INTO exercicios (organizacao_id, titulo, tipo) VALUES (?, ?, 'atividade')", (cen.org_a, "Exercício da Clínica A"))
    ex_org_b = db_ctx.execute("INSERT INTO exercicios (organizacao_id, titulo, tipo) VALUES (?, ?, 'atividade')", (cen.org_b, "Exercício PRIVADO da Clínica B"))
    return plano_id, ex_publico, ex_org_a, ex_org_b


def test_criar_missao_filtra_exercicio_privado_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    plano_id, ex_publico, ex_org_a, ex_org_b = _preparar_jornada(db_ctx, cen)

    r = autenticado(client, cen.prof_a1).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão teste", "exercicios_ids": [ex_publico, ex_org_a, ex_org_b],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    missao_id = r.get_json()["id"]

    ligados = {a["exercicio_id"] for a in db_ctx.query("SELECT exercicio_id FROM atividades WHERE missao_id = ?", (missao_id,))}
    assert ex_publico in ligados
    assert ex_org_a in ligados
    assert ex_org_b not in ligados


def test_editar_missao_tambem_filtra_exercicio_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    plano_id, ex_publico, ex_org_a, ex_org_b = _preparar_jornada(db_ctx, cen)

    r = autenticado(client, cen.prof_a1).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão teste", "exercicios_ids": [ex_org_a],
    })
    missao_id = r.get_json()["id"]

    r = autenticado(client, cen.prof_a1).put(f"/api/jornada/missao/{missao_id}", json={
        "titulo": "Missão editada", "exercicios_ids": [ex_org_b],
    })
    assert r.status_code == 200, r.get_data(as_text=True)

    ligados = db_ctx.query("SELECT exercicio_id FROM atividades WHERE missao_id = ?", (missao_id,))
    assert len(ligados) == 0
