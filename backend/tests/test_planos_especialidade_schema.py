"""Planos por especialidade (spec 08/10/2026): schema e migração."""
import db
import migrar_planos_especialidade


def _base():
    org = db.execute("INSERT INTO organizacoes (nome) VALUES ('X')")
    pac = db.execute("INSERT INTO pacientes (organizacao_id, nome, data_nascimento) VALUES (?, 'P', '2020-01-01')", (org,))
    jor = db.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, 'O')", (pac,))
    return org, jor


def _prof(org, email, esp):
    return db.execute("INSERT INTO usuarios (organizacao_id, nome, email, senha_hash, senha_salt, papel, especialidade) "
                      "VALUES (?, 'Pr', ?, 'h', 's', 'profissional', ?)", (org, email, esp))


def test_coluna_existe(db_ctx):
    nomes = {l["name"] for l in db.get_db().execute("PRAGMA table_info(planos_terapeuticos)").fetchall()}
    assert "especialidade" in nomes


def test_migracao_preenche_com_especialidade_do_criador_ou_geral(db_ctx, capsys):
    org, jor = _base()
    fono, sem = _prof(org, "f@x.com", "Fonoaudiologia"), _prof(org, "s@x.com", "  ")
    p1 = db.execute("INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, 'A', '2026-10-01')", (jor, fono))
    p2 = db.execute("INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio, status) VALUES (?, ?, 'B', '2026-10-01', 'encerrado')", (jor, sem))
    migrar_planos_especialidade.migrar()
    migrar_planos_especialidade.migrar()
    esp = {r["id"]: r["especialidade"] for r in db.query("SELECT id, especialidade FROM planos_terapeuticos")}
    assert esp == {p1: "Fonoaudiologia", p2: "Geral"}
    assert "já existia" in capsys.readouterr().out
