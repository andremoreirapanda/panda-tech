"""Atender/Evoluir (spec 08/10/2026): status novos, observação e um diário por consulta."""
import sqlite3

import pytest

import db
import migrar_atender
from factories import DuasClinicas


def _consulta(cen, status):
    return db.execute("INSERT INTO consultas (paciente_id, profissional_id, data_hora, status) VALUES (?, ?, '2026-10-08 09:00:00', ?)",
                      (cen.paciente_a1, cen.prof_a1["id"], status))


def test_status_novos_sao_aceitos_e_invalidos_recusados(db_ctx):
    cen = DuasClinicas()
    assert _consulta(cen, "falta_justificada") and _consulta(cen, "desmarcada_profissional")
    with pytest.raises(sqlite3.IntegrityError):
        _consulta(cen, "xyz")
    db.get_db().rollback()


def test_diario_tem_observacao_e_um_por_consulta(db_ctx):
    cen = DuasClinicas()
    nomes = {l["name"] for l in db.get_db().execute("PRAGMA table_info(diarios_terapeuticos)").fetchall()}
    assert "observacao" in nomes
    cid = _consulta(cen, "realizada")
    db.execute("INSERT INTO diarios_terapeuticos (paciente_id, profissional_id, consulta_id, evolucao_clinica) VALUES (?, ?, ?, 'a')",
               (cen.paciente_a1, cen.prof_a1["id"], cid))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO diarios_terapeuticos (paciente_id, profissional_id, consulta_id, evolucao_clinica) VALUES (?, ?, ?, 'b')",
                   (cen.paciente_a1, cen.prof_a1["id"], cid))
    db.get_db().rollback()


def test_migracao_idempotente(db_ctx, capsys):
    migrar_atender.migrar()
    migrar_atender.migrar()
    assert "já existia" in capsys.readouterr().out
