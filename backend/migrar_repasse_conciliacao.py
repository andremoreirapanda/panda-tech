"""
Migração (22/11/2026, conciliação automática do repasse): `repasse_ajustes.origem` aceita
'status' e 'recredito' além de 'manual' e 'estorno'; sai o índice único por sessão
(`idx_ajuste_estorno_consulta`) e entra `idx_ajuste_consulta` (não único).

    cd backend
    python3 migrar_repasse_conciliacao.py

Confira que a saída termina com (Postgres) em produção (CLAUDE.md, 7.2).
Seguro rodar de novo. No SQLite, `repasse_ajustes` é recriada (o SQLite não altera CHECK)
sem perder linhas.
"""
import os

import db

_AJUSTES = """CREATE TABLE repasse_ajustes_novo (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
    repasse_id      INTEGER REFERENCES repasses(id),
    descricao       TEXT NOT NULL,
    valor_centavos  INTEGER NOT NULL,
    origem          TEXT NOT NULL CHECK(origem IN ('manual','estorno','status','recredito')),
    consulta_id     INTEGER,
    criado_por      INTEGER,
    criado_em       TEXT DEFAULT (datetime('now')),
    dispensado_em   TEXT
)"""


def _colunas(conn, tabela):
    return [l["name"] for l in conn.execute(f"PRAGMA table_info({tabela})").fetchall()]


def _sql_atual(conn, tabela):
    linha = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (tabela,)).fetchone()
    return (linha or {}).get("sql") or ""


def migrar():
    if db.USANDO_POSTGRES:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_repasse_conciliacao.sql")
        linhas = [l for l in open(caminho, encoding="utf-8").read().splitlines() if not l.strip().startswith("--")]
        for comando in "\n".join(linhas).split(";"):
            if comando.strip():
                db.execute(comando)
        print("✅ Repasse (conciliação): origens e índice conferidos (Postgres)")
        return
    conn = db.get_db()
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        if "'recredito'" not in _sql_atual(conn, "repasse_ajustes"):
            conn.execute("DROP TABLE IF EXISTS repasse_ajustes_novo")
            conn.execute(_AJUSTES)
            novas = set(_colunas(conn, "repasse_ajustes_novo"))
            comuns = ", ".join(c for c in _colunas(conn, "repasse_ajustes") if c in novas)
            conn.execute(f"INSERT INTO repasse_ajustes_novo ({comuns}) SELECT {comuns} FROM repasse_ajustes")
            conn.execute("DROP TABLE repasse_ajustes")
            conn.execute("ALTER TABLE repasse_ajustes_novo RENAME TO repasse_ajustes")
            print("✅ repasse_ajustes recriada com as origens novas (SQLite)")
        else:
            print("↷  repasse_ajustes já tinha as origens novas (SQLite), pulei")
        conn.execute("DROP INDEX IF EXISTS idx_ajuste_estorno_consulta")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ajuste_consulta ON repasse_ajustes(consulta_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ajustes_abertos ON repasse_ajustes(organizacao_id, profissional_id) WHERE repasse_id IS NULL")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    print("✅ Repasse (conciliação): origens e índice conferidos (SQLite)")


if __name__ == "__main__":
    migrar()
