"""Sequência de dias mostrada na hora (ajustes da família/criança, 12/10/2026)."""
from datetime import date, timedelta

import gamificacao_service as gs
from factories import DuasClinicas
from conftest import autenticado


def test_sequencia_efetiva():
    hoje = date(2026, 10, 12)
    assert gs.sequencia_efetiva({"sequencia_dias": 3, "ultima_atividade_em": "2026-10-12 09:00:00"}, hoje) == 3
    assert gs.sequencia_efetiva({"sequencia_dias": 3, "ultima_atividade_em": "2026-10-11 20:00:00"}, hoje) == 3
    assert gs.sequencia_efetiva({"sequencia_dias": 3, "ultima_atividade_em": "2026-10-08 09:00:00"}, hoje) == 0
    assert gs.sequencia_efetiva({"sequencia_dias": 0, "ultima_atividade_em": None}, hoje) == 0
    assert gs.sequencia_efetiva(None, hoje) == 0


def test_ficha_mostra_sequencia_quebrada_como_zero(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, cen.prof_a1).post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json={
        "objetivo_principal": "Fala", "especialidade": "Fonoaudiologia", "titulo": "P1", "objetivos": ["A"]})
    antigo = (date.today() - timedelta(days=4)).isoformat() + " 10:00:00"
    db_ctx.execute("INSERT OR REPLACE INTO gamificacao_paciente (paciente_id, xp_total, sequencia_dias, ultima_atividade_em) VALUES (?, 40, 3, ?)",
                   (cen.paciente_a1, antigo))
    g = autenticado(client, cen.gestor_a).get(f"/api/jornada/paciente/{cen.paciente_a1}").get_json()["gamificacao"]
    assert g["sequencia_dias"] == 0 and g["xp_total"] == 40
