"""Agenda com Ausência (spec 07/10/2026): tabela nova e duração padrão da clínica."""
import db
import migrar_ausencias_agenda


def test_tabela_ausencias_existe(db_ctx):
    nomes = {l["name"] for l in db.get_db().execute("PRAGMA table_info(ausencias_profissional)").fetchall()}
    assert {"id", "organizacao_id", "profissional_id", "data_inicio", "data_fim", "dia_inteiro",
            "hora_inicio", "hora_fim", "dias_semana", "motivo", "criado_por", "criado_em"} <= nomes


def test_duracao_padrao_comeca_em_50(db_ctx):
    org_id = db.execute("INSERT INTO organizacoes (nome) VALUES ('X')")
    assert db.query_one("SELECT agenda_duracao_padrao FROM organizacoes WHERE id = ?", (org_id,))["agenda_duracao_padrao"] == 50


def test_migracao_idempotente(db_ctx, capsys):
    migrar_ausencias_agenda.migrar()
    migrar_ausencias_agenda.migrar()
    assert "já existia" in capsys.readouterr().out
