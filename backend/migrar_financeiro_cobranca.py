"""
Migração (07/11/2026, Financeiro das famílias, etapa 1): acordos de pagamento,
itens de cobrança, status novos (rascunho/parcial/cancelado), formas novas,
campos de baixa/estorno e `consultas.especialidade`.

    cd backend
    python3 migrar_financeiro_cobranca.py

Confira que a saída termina com (Postgres) em produção (CLAUDE.md, 7.2).
Seguro rodar de novo. No SQLite, `cobrancas` e `pagamentos` são recriadas
(o SQLite não altera CHECK) sem perder linhas.
"""
import os

import db

_COBRANCAS = """CREATE TABLE cobrancas_novo (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    descricao       TEXT NOT NULL,
    valor_centavos  INTEGER NOT NULL,
    vencimento      TEXT NOT NULL,
    status          TEXT DEFAULT 'pendente' CHECK(status IN ('rascunho','pendente','parcial','pago','vencido','cancelado')),
    criado_em       TEXT DEFAULT (datetime('now')),
    mp_payment_id       TEXT,
    pix_qr_code          TEXT,
    pix_qr_code_base64   TEXT,
    pix_copia_cola        TEXT,
    organizacao_id  INTEGER,
    acordo_id       INTEGER,
    tipo            TEXT NOT NULL DEFAULT 'manual',
    periodo_inicio  TEXT,
    periodo_fim     TEXT,
    desconto_centavos INTEGER NOT NULL DEFAULT 0,
    desconto_motivo TEXT,
    liberada_em     TEXT,
    revisar         INTEGER NOT NULL DEFAULT 0,
    revisar_motivo  TEXT
)"""

_PAGAMENTOS = """CREATE TABLE pagamentos_novo (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cobranca_id     INTEGER NOT NULL REFERENCES cobrancas(id),
    valor_centavos  INTEGER NOT NULL,
    forma           TEXT DEFAULT 'pix' CHECK(forma IN ('pix','cartao','cartao_credito','cartao_debito','boleto','dinheiro','transferencia')),
    pago_em         TEXT DEFAULT (datetime('now')),
    recebido_por_usuario_id INTEGER,
    recebido_por_nome TEXT,
    estornado_em    TEXT,
    estorno_motivo  TEXT,
    estornado_por   INTEGER
)"""

_NOVAS = [
    """CREATE TABLE IF NOT EXISTS acordos_pagamento (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
        paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
        especialidade   TEXT NOT NULL,
        tipo            TEXT NOT NULL CHECK(tipo IN ('avulsa','mensalidade','pacote')),
        ciclo           TEXT CHECK(ciclo IN ('consulta','quinzenal','mensal')),
        vence_dias      INTEGER DEFAULT 5,
        valor_centavos  INTEGER,
        dia_vencimento  INTEGER,
        sessoes_total   INTEGER,
        parcelas        INTEGER,
        primeiro_vencimento TEXT,
        inicio          TEXT NOT NULL,
        fim             TEXT,
        status          TEXT NOT NULL DEFAULT 'ativo' CHECK(status IN ('ativo','encerrado')),
        criado_por      INTEGER,
        criado_em       TEXT DEFAULT (datetime('now')),
        encerrado_em    TEXT)""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_acordo_ativo_esp ON acordos_pagamento(paciente_id, LOWER(TRIM(especialidade))) WHERE status = 'ativo'",
    """CREATE TABLE IF NOT EXISTS cobranca_itens (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        cobranca_id     INTEGER NOT NULL REFERENCES cobrancas(id),
        consulta_id     INTEGER NOT NULL REFERENCES consultas(id),
        data_hora       TEXT,
        procedimento_nome TEXT,
        valor_centavos  INTEGER NOT NULL,
        UNIQUE(consulta_id))""",
    """CREATE TABLE IF NOT EXISTS consulta_decisao_cobranca (
        consulta_id     INTEGER PRIMARY KEY REFERENCES consultas(id),
        decisao         TEXT NOT NULL CHECK(decisao IN ('nao_cobrar','valor')),
        valor_centavos  INTEGER,
        motivo          TEXT,
        decidido_por    INTEGER,
        decidido_em     TEXT DEFAULT (datetime('now')))""",
    """CREATE TABLE IF NOT EXISTS acordo_pacote_consumo (
        consulta_id     INTEGER PRIMARY KEY REFERENCES consultas(id),
        acordo_id       INTEGER NOT NULL REFERENCES acordos_pagamento(id),
        numero          INTEGER NOT NULL)""",
]


def _colunas(conn, tabela):
    return [l["name"] for l in conn.execute(f"PRAGMA table_info({tabela})").fetchall()]


def _sql_atual(conn, tabela):
    linha = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (tabela,)).fetchone()
    return (linha or {}).get("sql") or ""


def _recriar(conn, tabela, ddl_novo):
    """Cria `<tabela>_novo`, copia as colunas em comum, troca pela original."""
    conn.execute(f"DROP TABLE IF EXISTS {tabela}_novo")
    conn.execute(ddl_novo)
    novas = set(_colunas(conn, f"{tabela}_novo"))
    comuns = ", ".join(c for c in _colunas(conn, tabela) if c in novas)
    conn.execute(f"INSERT INTO {tabela}_novo ({comuns}) SELECT {comuns} FROM {tabela}")
    conn.execute(f"DROP TABLE {tabela}")
    conn.execute(f"ALTER TABLE {tabela}_novo RENAME TO {tabela}")


def migrar():
    if db.USANDO_POSTGRES:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_financeiro_cobranca.sql")
        linhas = [l for l in open(caminho, encoding="utf-8").read().splitlines() if not l.strip().startswith("--")]
        for comando in "\n".join(linhas).split(";"):
            if comando.strip():
                db.execute(comando)
        print("✅ Financeiro (cobrança): tabelas, colunas e regras conferidas (Postgres)")
        return
    conn = db.get_db()
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")  # trocar tabela referenciada exige FK desligada
    try:
        for coluna in ("fin_cobrar_falta", "fin_repasse_falta"):
            if coluna not in _colunas(conn, "organizacoes"):
                conn.execute(f"ALTER TABLE organizacoes ADD COLUMN {coluna} INTEGER NOT NULL DEFAULT 0")
        if "especialidade" not in _colunas(conn, "consultas"):
            conn.execute("ALTER TABLE consultas ADD COLUMN especialidade TEXT")
        conn.execute("""UPDATE consultas SET especialidade = COALESCE(
            (SELECT NULLIF(TRIM(u.especialidade), '') FROM usuarios u WHERE u.id = consultas.profissional_id), 'Geral')
            WHERE especialidade IS NULL""")
        conn.commit()

        conn.execute("BEGIN")
        if "'rascunho'" not in _sql_atual(conn, "cobrancas"):
            _recriar(conn, "cobrancas", _COBRANCAS)
            print("✅ cobrancas recriada com os status novos (SQLite)")
        else:
            print("↷  cobrancas já tinha os status novos (SQLite), pulei")
        if "'cartao_credito'" not in _sql_atual(conn, "pagamentos"):
            _recriar(conn, "pagamentos", _PAGAMENTOS)
            print("✅ pagamentos recriada com as formas novas (SQLite)")
        else:
            print("↷  pagamentos já tinha as formas novas (SQLite), pulei")
        conn.execute("""UPDATE cobrancas SET organizacao_id = (SELECT p.organizacao_id FROM pacientes p WHERE p.id = cobrancas.paciente_id)
                        WHERE organizacao_id IS NULL""")
        for comando in _NOVAS:
            conn.execute(comando)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cobrancas_paciente ON cobrancas(paciente_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cobrancas_org ON cobrancas(organizacao_id, status)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cobranca_mensalidade_mes ON cobrancas(acordo_id, periodo_inicio) "
                     "WHERE tipo = 'mensalidade'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    print("✅ Financeiro (cobrança): tabelas, colunas e regras conferidas (SQLite)")


if __name__ == "__main__":
    migrar()
