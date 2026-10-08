"""Diário por paciente (spec 08/10/2026): schema e migração."""
import db
import migrar_diario_por_paciente


def test_coluna_paciente_e_jornada_opcional(db_ctx):
    cols = {l["name"]: l for l in db.get_db().execute("PRAGMA table_info(diarios_terapeuticos)").fetchall()}
    assert "paciente_id" in cols
    assert cols["jornada_id"]["notnull"] == 0


def test_migracao_preenche_paciente_e_e_idempotente(db_ctx, capsys):
    org = db.execute("INSERT INTO organizacoes (nome) VALUES ('X')")
    pac = db.execute("INSERT INTO pacientes (organizacao_id, nome, data_nascimento) VALUES (?, 'P', '2020-01-01')", (org,))
    prof = db.execute("INSERT INTO usuarios (organizacao_id, nome, email, senha_hash, senha_salt, papel) VALUES (?, 'Pr', 'p@x.com', 'h', 's', 'profissional')", (org,))
    jor = db.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, 'O')", (pac,))
    d = db.execute("INSERT INTO diarios_terapeuticos (jornada_id, profissional_id, evolucao_clinica) VALUES (?, ?, 'E')", (jor, prof))
    migrar_diario_por_paciente.migrar()
    migrar_diario_por_paciente.migrar()
    assert db.query_one("SELECT paciente_id FROM diarios_terapeuticos WHERE id = ?", (d,))["paciente_id"] == pac
    assert "já existia" in capsys.readouterr().out
