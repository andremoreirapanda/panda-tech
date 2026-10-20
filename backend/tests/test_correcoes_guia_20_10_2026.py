"""
Correções achadas ao montar o Guia de Primeiros Passos (20/10/2026).

- "Marquei hoje!" numa missão de vários dias: o aviso da criança dizia sempre
  "Dia N/7". A resposta de concluir-dia passa a trazer `dias_exigidos` (a
  frequência da missão), que a tela usa no lugar do 7 fixo.
"""
from factories import DuasClinicas, vincular_responsavel

from conftest import autenticado


def _missao_de_frequencia(client, db_ctx, cen, dias):
    jornada_id = db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (cen.paciente_a1, "Objetivo geral"),
    )
    plano_id = db_ctx.execute(
        "INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
        (jornada_id, cen.prof_a1["id"], "Plano"),
    )
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão de vários dias", "tipo": "semanal", "frequencia_dias": dias,
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    missao_id = r.get_json()["id"]
    db_ctx.execute("UPDATE missoes SET status = 'iniciada' WHERE id = ?", (missao_id,))
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    return missao_id


def test_concluir_dia_informa_quantos_dias_a_missao_exige(client, db_ctx):
    cen = DuasClinicas()
    missao_id = _missao_de_frequencia(client, db_ctx, cen, 5)

    resp = autenticado(client, cen.resp_a1).post(f"/api/jornada/missao/{missao_id}/concluir-dia")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    corpo = resp.get_json()
    assert corpo["dias_concluidos"] == 1
    assert corpo["dias_exigidos"] == 5
    assert corpo["semana_completa"] is False


def test_concluir_ultimo_dia_tambem_informa_dias_exigidos(client, db_ctx):
    cen = DuasClinicas()
    missao_id = _missao_de_frequencia(client, db_ctx, cen, 2)
    db_ctx.execute("INSERT INTO missao_dias_concluidos (missao_id, data) VALUES (?, '2026-01-01')", (missao_id,))

    resp = autenticado(client, cen.resp_a1).post(f"/api/jornada/missao/{missao_id}/concluir-dia")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    corpo = resp.get_json()
    assert corpo["semana_completa"] is True
    assert corpo["dias_exigidos"] == 2
