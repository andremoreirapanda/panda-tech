"""White Label completo (25/09/2026): colunas novas em organizacoes."""
import sqlite3

import pytest

import db
import migrar_white_label

COLUNAS = ["endereco_login", "app_nome", "app_icone_base64", "login_mensagem", "mundo_fonte",
           "mundo_fundo", "mundo_mascote", "mundo_mascote_imagem", "mundo_comemoracao"]


def test_colunas_existem(db_ctx):
    linhas = db.get_db().execute("PRAGMA table_info(organizacoes)").fetchall()
    nomes = {l["name"] for l in linhas}
    assert set(COLUNAS) <= nomes


def test_endereco_unico(db_ctx):
    db.execute("INSERT INTO organizacoes (nome, endereco_login) VALUES ('A', 'abc')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO organizacoes (nome, endereco_login) VALUES ('B', 'abc')")
    db.get_db().rollback()
    db.execute("INSERT INTO organizacoes (nome) VALUES ('C')")
    db.execute("INSERT INTO organizacoes (nome) VALUES ('D')")  # NULL repetido pode


def test_migracao_idempotente(db_ctx, capsys):
    migrar_white_label.migrar()
    migrar_white_label.migrar()
    assert "já existia" in capsys.readouterr().out
