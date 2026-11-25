"""
Migração (25/11/2026, anexos do Diário no Supabase Storage): `diario_anexos` ganha
`storage_path` e `mime`, e `conteudo_base64` passa a aceitar NULL.

    cd backend
    python3 migrar_anexos_storage.py

Confira que a saída termina com (Postgres) em produção (CLAUDE.md, 7.2).
Seguro rodar de novo. No SQLite, `diario_anexos` é recriada (o SQLite não tira
NOT NULL) sem perder linhas.
"""
import os

import db

_ANEXOS = """CREATE TABLE diario_anexos_novo (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    diario_id           INTEGER NOT NULL REFERENCES diarios_terapeuticos(id),
    tipo                TEXT NOT NULL CHECK(tipo IN ('foto','audio','video')),
    nome_arquivo        TEXT,
    conteudo_base64     TEXT,
    tamanho_bytes        INTEGER,
    storage_path        TEXT,
    mime                TEXT,
    criado_em             TEXT DEFAULT (datetime('now'))
)"""


def _colunas(conn, tabela):
    return [l["name"] for l in conn.execute(f"PRAGMA table_info({tabela})").fetchall()]


def migrar():
    if db.USANDO_POSTGRES:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_anexos_storage.sql")
        linhas = [l for l in open(caminho, encoding="utf-8").read().splitlines() if not l.strip().startswith("--")]
        for comando in "\n".join(linhas).split(";"):
            if comando.strip():
                db.execute(comando)
        print("✅ Anexos do Diário: colunas storage_path e mime conferidas (Postgres)")
        return
    conn = db.get_db()
    if "storage_path" in _colunas(conn, "diario_anexos"):
        print("✅ Anexos do Diário: nada a fazer (SQLite)")
        return
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute("DROP TABLE IF EXISTS diario_anexos_novo")
        conn.execute(_ANEXOS)
        comuns = ", ".join(_colunas(conn, "diario_anexos"))
        conn.execute(f"INSERT INTO diario_anexos_novo ({comuns}) SELECT {comuns} FROM diario_anexos")
        conn.execute("DROP TABLE diario_anexos")
        conn.execute("ALTER TABLE diario_anexos_novo RENAME TO diario_anexos")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_diario_anexos_diario ON diario_anexos(diario_id)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    print("✅ Anexos do Diário: tabela recriada com storage_path e mime (SQLite)")


if __name__ == "__main__":
    migrar()
