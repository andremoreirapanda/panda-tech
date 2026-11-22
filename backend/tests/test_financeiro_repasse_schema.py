"""Financeiro etapa 3: tabelas do repasse aos profissionais."""
import sqlite3

import pytest

import db
import migrar_financeiro_repasse
from factories import DuasClinicas


def _cols(tabela):
    return {l["name"] for l in db.get_db().execute(f"PRAGMA table_info({tabela})").fetchall()}


def _existe(tabela):
    return bool(db.query_one("SELECT 1 AS x FROM sqlite_master WHERE type = 'table' AND name = ?", (tabela,)))


def test_colunas_e_tabelas_existem(db_ctx):
    assert "fin_repasse_base" in _cols("organizacoes")
    assert {"id", "organizacao_id", "profissional_id", "procedimento_id", "tipo_acordo", "modo",
            "percentual_centesimos", "valor_centavos", "atualizado_em", "atualizado_por"} <= _cols("regras_repasse")
    assert {"id", "organizacao_id", "profissional_id", "periodo_de", "periodo_ate", "total_sessoes_centavos",
            "total_profissional_centavos", "total_ajustes_centavos", "a_pagar_centavos", "quantidade",
            "pago_em", "pago_por", "criado_em"} <= _cols("repasses")
    assert {"id", "repasse_id", "consulta_id", "data_hora", "paciente_nome", "especialidade", "descricao",
            "sessao_numero", "sessao_total", "tipo_acordo", "base_centavos", "regra_modo",
            "regra_percentual_centesimos", "regra_valor_centavos", "profissional_centavos",
            "clinica_centavos"} <= _cols("repasse_itens")
    assert {"id", "organizacao_id", "profissional_id", "repasse_id", "descricao", "valor_centavos",
            "origem", "consulta_id", "criado_por", "criado_em", "dispensado_em"} <= _cols("repasse_ajustes")


def test_base_do_repasse_comeca_em_procedimento(db_ctx):
    cen = DuasClinicas()
    org = db.query_one("SELECT fin_repasse_base FROM organizacoes WHERE id = ?", (cen.org_a,))
    assert org["fin_repasse_base"] == "procedimento"


def _repasse(cen):
    return db.execute(
        "INSERT INTO repasses (organizacao_id, profissional_id, periodo_de, periodo_ate) VALUES (?, ?, '2026-11-01', '2026-11-30')",
        (cen.org_a, cen.prof_a1["id"]))


def _consulta(cen, hora):
    return db.execute(
        "INSERT INTO consultas (paciente_id, profissional_id, data_hora) VALUES (?, ?, ?)",
        (cen.paciente_a1, cen.prof_a1["id"], hora))


def test_consulta_so_entra_em_um_repasse(db_ctx):
    cen = DuasClinicas()
    rep = _repasse(cen)
    cons = _consulta(cen, "2026-11-02 09:00:00")
    db.execute("INSERT INTO repasse_itens (repasse_id, consulta_id) VALUES (?, ?)", (rep, cons))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO repasse_itens (repasse_id, consulta_id) VALUES (?, ?)", (rep, cons))
    db.get_db().rollback()


def _ajuste(cen, origem, consulta_id=None):
    return db.execute(
        "INSERT INTO repasse_ajustes (organizacao_id, profissional_id, descricao, valor_centavos, origem, consulta_id) "
        "VALUES (?, ?, 'x', -100, ?, ?)", (cen.org_a, cen.prof_a1["id"], origem, consulta_id))


def test_ajustes_de_estorno_da_mesma_sessao_podem_repetir(db_ctx):
    """Conciliação: o índice único saiu; a deduplicação passa a ser feita pelo serviço."""
    cen = DuasClinicas()
    cons = _consulta(cen, "2026-11-02 09:00:00")
    _ajuste(cen, "estorno", cons)
    _ajuste(cen, "estorno", cons)
    assert db.query_one("SELECT COUNT(*) AS n FROM repasse_ajustes WHERE consulta_id = ?", (cons,))["n"] == 2


def test_origens_novas_dos_ajustes(db_ctx):
    cen = DuasClinicas()
    cons = _consulta(cen, "2026-11-02 09:00:00")
    for origem in ("manual", "estorno", "status", "recredito"):
        _ajuste(cen, origem, cons)
    with pytest.raises(sqlite3.IntegrityError):
        _ajuste(cen, "outra", cons)
    db.get_db().rollback()


def test_indice_de_consulta_nao_e_unico(db_ctx):
    indices = {l["name"]: l for l in db.query("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = 'repasse_ajustes'")}
    assert "idx_ajuste_estorno_consulta" not in indices
    assert "idx_ajuste_consulta" in indices and "UNIQUE" not in indices["idx_ajuste_consulta"]["sql"].upper()


def _recriar_estrutura_anterior(cen):
    """repasse_ajustes como estava em produção: CHECK de 2 origens + índice único, com linhas."""
    conn = db.get_db()
    conn.execute("DROP TABLE repasse_ajustes")
    conn.execute("""CREATE TABLE repasse_ajustes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organizacao_id INTEGER NOT NULL REFERENCES organizacoes(id),
        profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
        repasse_id INTEGER REFERENCES repasses(id),
        descricao TEXT NOT NULL, valor_centavos INTEGER NOT NULL,
        origem TEXT NOT NULL CHECK(origem IN ('manual','estorno')),
        consulta_id INTEGER, criado_por INTEGER, criado_em TEXT DEFAULT (datetime('now')), dispensado_em TEXT)""")
    conn.execute("CREATE UNIQUE INDEX idx_ajuste_estorno_consulta ON repasse_ajustes(consulta_id) WHERE origem = 'estorno'")
    conn.execute("CREATE INDEX idx_ajustes_abertos ON repasse_ajustes(organizacao_id, profissional_id) WHERE repasse_id IS NULL")
    conn.commit()
    cons = _consulta(cen, "2026-11-02 09:00:00")
    _ajuste(cen, "estorno", cons)
    _ajuste(cen, "manual")
    conn.execute("UPDATE repasse_ajustes SET dispensado_em = '2026-11-03 10:00:00' WHERE origem = 'manual'")
    conn.commit()
    return cons


def test_migrar_conciliacao_preserva_linhas_da_estrutura_anterior(db_ctx):
    import migrar_repasse_conciliacao
    cen = DuasClinicas()
    cons = _recriar_estrutura_anterior(cen)
    antes = [dict(l) for l in db.query("SELECT * FROM repasse_ajustes ORDER BY id")]
    assert len(antes) == 2
    migrar_repasse_conciliacao.migrar()
    migrar_repasse_conciliacao.migrar()
    assert [dict(l) for l in db.query("SELECT * FROM repasse_ajustes ORDER BY id")] == antes
    _ajuste(cen, "estorno", cons)      # o índice único saiu
    _ajuste(cen, "status", cons)
    _ajuste(cen, "recredito", cons)
    with pytest.raises(sqlite3.IntegrityError):
        _ajuste(cen, "outra", cons)
    db.get_db().rollback()
    nomes = {l["name"] for l in db.query("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'repasse_ajustes'")}
    assert "idx_ajuste_estorno_consulta" not in nomes and {"idx_ajuste_consulta", "idx_ajustes_abertos"} <= nomes


def test_migrar_repasse_antigo_nao_recria_o_indice_unico(db_ctx):
    cen = DuasClinicas()
    _recriar_estrutura_anterior(cen)
    import migrar_repasse_conciliacao
    migrar_repasse_conciliacao.migrar()
    migrar_financeiro_repasse.migrar()
    nomes = {l["name"] for l in db.query("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'repasse_ajustes'")}
    assert "idx_ajuste_estorno_consulta" not in nomes


def test_sql_do_postgres_da_conciliacao():
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sql = open(os.path.join(base, "migracoes", "migracao_repasse_conciliacao.sql"), encoding="utf-8").read()
    assert "DROP CONSTRAINT IF EXISTS repasse_ajustes_origem_check" in sql
    assert "'manual','estorno','status','recredito'" in sql
    assert "DROP INDEX IF EXISTS idx_ajuste_estorno_consulta" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_ajuste_consulta ON repasse_ajustes(consulta_id)" in sql
    for arq in ("schema.sql", "schema_postgres.sql"):
        schema = open(os.path.join(base, arq), encoding="utf-8").read()
        assert "'manual','estorno','status','recredito'" in schema
        assert "idx_ajuste_estorno_consulta" not in schema and "CREATE INDEX idx_ajuste_consulta" in schema


def test_ajustes_manuais_sem_consulta_repetem(db_ctx):
    cen = DuasClinicas()
    _ajuste(cen, "manual")
    _ajuste(cen, "manual")
    with pytest.raises(sqlite3.IntegrityError):
        _ajuste(cen, "inventada")
    db.get_db().rollback()


def _regra(cen, proc, tipo):
    return db.execute(
        "INSERT INTO regras_repasse (organizacao_id, profissional_id, procedimento_id, tipo_acordo, modo, percentual_centesimos) "
        "VALUES (?, ?, ?, ?, 'percentual', 5000)", (cen.org_a, cen.prof_a1["id"], proc, tipo))


def test_regra_unica_por_profissional_procedimento_e_tipo(db_ctx):
    cen = DuasClinicas()
    _regra(cen, None, None)
    _regra(cen, None, "avulsa")
    with pytest.raises(sqlite3.IntegrityError):
        _regra(cen, None, None)
    with pytest.raises(sqlite3.IntegrityError):
        _regra(cen, None, "avulsa")
    with pytest.raises(sqlite3.IntegrityError):
        _regra(cen, None, "inventado")
    db.get_db().rollback()


def test_migrar_roda_duas_vezes_sobre_o_schema_anterior(db_ctx):
    conn = db.get_db()
    for tabela in ("repasse_ajustes", "repasse_itens", "repasses", "regras_repasse"):
        conn.execute(f"DROP TABLE {tabela}")
    conn.execute("ALTER TABLE organizacoes DROP COLUMN fin_repasse_base")
    conn.commit()
    assert "fin_repasse_base" not in _cols("organizacoes")
    migrar_financeiro_repasse.migrar()
    migrar_financeiro_repasse.migrar()
    assert "fin_repasse_base" in _cols("organizacoes")
    for tabela in ("regras_repasse", "repasses", "repasse_itens", "repasse_ajustes"):
        assert _existe(tabela)
    cen = DuasClinicas()
    _regra(cen, None, None)
    with pytest.raises(sqlite3.IntegrityError):
        _regra(cen, None, None)
    db.get_db().rollback()


def test_migrar_acrescenta_dispensado_em_na_tabela_antiga(db_ctx):
    """Base que já tinha `repasse_ajustes` sem a coluna (primeira versão da migração)."""
    conn = db.get_db()
    conn.execute("ALTER TABLE repasse_ajustes DROP COLUMN dispensado_em")
    conn.commit()
    assert "dispensado_em" not in _cols("repasse_ajustes")
    migrar_financeiro_repasse.migrar()
    migrar_financeiro_repasse.migrar()
    assert "dispensado_em" in _cols("repasse_ajustes")


def test_sql_do_postgres_tem_dispensado_em():
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sql = open(os.path.join(base, "migracoes", "migracao_financeiro_repasse.sql"), encoding="utf-8").read()
    assert "ALTER TABLE repasse_ajustes ADD COLUMN IF NOT EXISTS dispensado_em TEXT" in sql
    schema_pg = open(os.path.join(base, "schema_postgres.sql"), encoding="utf-8").read()
    assert "dispensado_em" in schema_pg


def test_repasse_itens_guarda_acordo_e_mes(db_ctx):
    """Revisão final: o item lembra o acordo (pacote/mensalidade) e o mês da mensalidade."""
    assert {"acordo_id", "mes"} <= _cols("repasse_itens")


def test_migrar_acrescenta_acordo_e_mes_na_tabela_antiga(db_ctx):
    conn = db.get_db()
    conn.execute("ALTER TABLE repasse_itens DROP COLUMN acordo_id")
    conn.execute("ALTER TABLE repasse_itens DROP COLUMN mes")
    conn.commit()
    migrar_financeiro_repasse.migrar()
    migrar_financeiro_repasse.migrar()
    assert {"acordo_id", "mes"} <= _cols("repasse_itens")


def test_sql_do_postgres_tem_acordo_e_mes():
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sql = open(os.path.join(base, "migracoes", "migracao_financeiro_repasse.sql"), encoding="utf-8").read()
    assert "ALTER TABLE repasse_itens ADD COLUMN IF NOT EXISTS acordo_id INTEGER" in sql
    assert "ALTER TABLE repasse_itens ADD COLUMN IF NOT EXISTS mes TEXT" in sql
    schema_pg = open(os.path.join(base, "schema_postgres.sql"), encoding="utf-8").read()
    bloco = schema_pg[schema_pg.index("CREATE TABLE repasse_itens"):]
    bloco = bloco[:bloco.index(");")]
    assert "acordo_id" in bloco and "mes " in bloco
