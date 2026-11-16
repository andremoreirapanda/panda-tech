"""
Migração (12/11/2026, Financeiro etapa 3): repasse aos profissionais —
`organizacoes.fin_repasse_base`, `regras_repasse`, `repasses`, `repasse_itens`
e `repasse_ajustes` (com `dispensado_em`, acrescentada depois — a migração a cria se faltar).

    cd backend
    python3 migrar_financeiro_repasse.py

Confira que a saída termina com (Postgres) em produção (CLAUDE.md, 7.2).
Seguro rodar de novo.
"""
import os

import db

_NOVAS = [
    """CREATE TABLE IF NOT EXISTS regras_repasse (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
        profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
        procedimento_id INTEGER REFERENCES procedimentos(id),
        tipo_acordo     TEXT CHECK(tipo_acordo IN ('avulsa','mensalidade','pacote')),
        modo            TEXT NOT NULL CHECK(modo IN ('percentual','fixo')),
        percentual_centesimos INTEGER,
        valor_centavos  INTEGER,
        atualizado_em   TEXT DEFAULT (datetime('now')),
        atualizado_por  INTEGER)""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_regra_repasse_unica ON regras_repasse(profissional_id, COALESCE(procedimento_id, 0), COALESCE(tipo_acordo, ''))",
    "CREATE INDEX IF NOT EXISTS idx_regras_repasse_org ON regras_repasse(organizacao_id, profissional_id)",
    """CREATE TABLE IF NOT EXISTS repasses (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
        profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
        periodo_de      TEXT NOT NULL,
        periodo_ate     TEXT NOT NULL,
        total_sessoes_centavos INTEGER NOT NULL DEFAULT 0,
        total_profissional_centavos INTEGER NOT NULL DEFAULT 0,
        total_ajustes_centavos INTEGER NOT NULL DEFAULT 0,
        a_pagar_centavos INTEGER NOT NULL DEFAULT 0,
        quantidade      INTEGER NOT NULL DEFAULT 0,
        pago_em         TEXT,
        pago_por        INTEGER,
        criado_em       TEXT DEFAULT (datetime('now')))""",
    "CREATE INDEX IF NOT EXISTS idx_repasses_org ON repasses(organizacao_id, profissional_id)",
    """CREATE TABLE IF NOT EXISTS repasse_itens (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        repasse_id      INTEGER NOT NULL REFERENCES repasses(id),
        consulta_id     INTEGER NOT NULL UNIQUE REFERENCES consultas(id),
        data_hora       TEXT,
        paciente_nome   TEXT,
        especialidade   TEXT,
        descricao       TEXT,
        sessao_numero   INTEGER,
        sessao_total    INTEGER,
        tipo_acordo     TEXT,
        base_centavos   INTEGER NOT NULL DEFAULT 0,
        regra_modo      TEXT,
        regra_percentual_centesimos INTEGER,
        regra_valor_centavos INTEGER,
        profissional_centavos INTEGER NOT NULL DEFAULT 0,
        clinica_centavos INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS repasse_ajustes (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
        profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
        repasse_id      INTEGER REFERENCES repasses(id),
        descricao       TEXT NOT NULL,
        valor_centavos  INTEGER NOT NULL,
        origem          TEXT NOT NULL CHECK(origem IN ('manual','estorno')),
        consulta_id     INTEGER,
        criado_por      INTEGER,
        criado_em       TEXT DEFAULT (datetime('now')),
        dispensado_em   TEXT)""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_ajuste_estorno_consulta ON repasse_ajustes(consulta_id) WHERE origem = 'estorno'",
    "CREATE INDEX IF NOT EXISTS idx_ajustes_abertos ON repasse_ajustes(organizacao_id, profissional_id) WHERE repasse_id IS NULL",
]


def _colunas(conn, tabela):
    return [l["name"] for l in conn.execute(f"PRAGMA table_info({tabela})").fetchall()]


def migrar():
    if db.USANDO_POSTGRES:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_financeiro_repasse.sql")
        linhas = [l for l in open(caminho, encoding="utf-8").read().splitlines() if not l.strip().startswith("--")]
        for comando in "\n".join(linhas).split(";"):
            if comando.strip():
                db.execute(comando)
        print("✅ Financeiro (repasse): tabelas, colunas e índices conferidos (Postgres)")
        return
    conn = db.get_db()
    conn.commit()
    try:
        if "fin_repasse_base" not in _colunas(conn, "organizacoes"):
            conn.execute("ALTER TABLE organizacoes ADD COLUMN fin_repasse_base TEXT NOT NULL DEFAULT 'procedimento'")
        for comando in _NOVAS:
            conn.execute(comando)
        if "dispensado_em" not in _colunas(conn, "repasse_ajustes"):   # tabela criada antes da coluna
            conn.execute("ALTER TABLE repasse_ajustes ADD COLUMN dispensado_em TEXT")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    print("✅ Financeiro (repasse): tabelas, colunas e índices conferidos (SQLite)")


if __name__ == "__main__":
    migrar()
