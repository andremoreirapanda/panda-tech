"""
Migração (25/11/2026, IA fase 1 — ditado por voz): `planos.ia_minutos_mes`, tabelas
`ia_uso` e `ia_creditos`, e remoção das linhas do módulo `ia` em `planos_modulos` e
`modulos_clinica` (ninguém ganha o ditado automaticamente no deploy).

    cd backend
    python3 migrar_ia_ditado.py

Rodar ANTES do deploy. Confira que a saída termina com (Postgres) em produção
(CLAUDE.md, 7.2). Seguro rodar de novo.
"""
import os

import db

_USO = """CREATE TABLE IF NOT EXISTS ia_uso (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id            INTEGER NOT NULL REFERENCES organizacoes(id),
    usuario_id                INTEGER REFERENCES usuarios(id),
    recurso                   TEXT NOT NULL,
    mes                       TEXT NOT NULL,
    segundos                  INTEGER NOT NULL DEFAULT 0,
    modelo                    TEXT,
    custo_estimado_micro_usd  INTEGER,
    sucesso                   INTEGER NOT NULL DEFAULT 1,
    criado_em                 TEXT DEFAULT (datetime('now'))
)"""

_CREDITOS = """CREATE TABLE IF NOT EXISTS ia_creditos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id    INTEGER NOT NULL REFERENCES organizacoes(id),
    mes               TEXT NOT NULL,
    minutos           INTEGER NOT NULL,
    motivo            TEXT,
    criado_por        INTEGER REFERENCES usuarios(id),
    criado_em         TEXT DEFAULT (datetime('now'))
)"""


def _colunas(conn, tabela):
    return [l["name"] for l in conn.execute(f"PRAGMA table_info({tabela})").fetchall()]


def migrar():
    if db.USANDO_POSTGRES:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_ia_ditado.sql")
        linhas = [l for l in open(caminho, encoding="utf-8").read().splitlines() if not l.strip().startswith("--")]
        for comando in "\n".join(linhas).split(";"):
            if comando.strip():
                db.execute(comando)
        print("✅ IA ditado: coluna, tabelas e módulo conferidos (Postgres)")
        return
    conn = db.get_db()
    if "ia_minutos_mes" not in _colunas(conn, "planos"):
        conn.execute("ALTER TABLE planos ADD COLUMN ia_minutos_mes INTEGER")
    conn.execute(_USO)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ia_uso_org_mes ON ia_uso(organizacao_id, mes)")
    conn.execute(_CREDITOS)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ia_creditos_org_mes ON ia_creditos(organizacao_id, mes)")
    conn.execute("DELETE FROM planos_modulos WHERE modulo_codigo = 'ia'")
    conn.execute("DELETE FROM modulos_clinica WHERE modulo_codigo = 'ia'")
    conn.commit()
    print("✅ IA ditado: coluna, tabelas e módulo conferidos (SQLite)")


if __name__ == "__main__":
    migrar()
