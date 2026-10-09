"""Procedimentos (spec 09/10/2026): tabela, índice de nome e colunas na consulta."""
import sqlite3

import pytest

import db
import migrar_procedimentos
from factories import DuasClinicas


def _proc(org_id, nome):
    return db.execute("INSERT INTO procedimentos (organizacao_id, nome, valor_centavos) VALUES (?, ?, 23000)", (org_id, nome))


def test_tabela_e_colunas_existem(db_ctx):
    cols = {l["name"] for l in db.get_db().execute("PRAGMA table_info(procedimentos)").fetchall()}
    assert {"id", "organizacao_id", "codigo", "nome", "valor_centavos", "ativo", "ordem", "criado_em", "atualizado_em"} <= cols
    cols_c = {l["name"] for l in db.get_db().execute("PRAGMA table_info(consultas)").fetchall()}
    assert {"procedimento_id", "procedimento_valor_centavos"} <= cols_c


def test_nome_unico_por_clinica_ignorando_caixa_e_espacos(db_ctx):
    cen = DuasClinicas()
    _proc(cen.org_a, "Sessão")
    with pytest.raises(sqlite3.IntegrityError):
        _proc(cen.org_a, " sessão ")
    db.get_db().rollback()
    assert _proc(cen.org_b, "Sessão")


def test_migracao_idempotente(db_ctx, capsys):
    migrar_procedimentos.migrar()
    migrar_procedimentos.migrar()
    assert "já existia" in capsys.readouterr().out
