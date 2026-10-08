"""
Migração não-destrutiva (spec 07/10/2026): tabela `ausencias_profissional` e
coluna `organizacoes.agenda_duracao_padrao` (padrão 50 min).

    cd backend
    python3 migrar_ausencias_agenda.py

Confira que a saída termina com (Postgres) em produção — sem DATABASE_URL o
script grava no SQLite local (CLAUDE.md, seção 7.2). Seguro rodar de novo.
"""
import os

import db

DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS ausencias_profissional (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id INTEGER NOT NULL REFERENCES organizacoes(id),
    profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
    data_inicio TEXT NOT NULL, data_fim TEXT, dia_inteiro INTEGER NOT NULL DEFAULT 0,
    hora_inicio TEXT, hora_fim TEXT, dias_semana TEXT NOT NULL DEFAULT '123456', motivo TEXT,
    criado_por INTEGER REFERENCES usuarios(id), criado_em TEXT DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS idx_ausencias_prof ON ausencias_profissional(profissional_id, data_inicio);
"""


def migrar():
    if db.USANDO_POSTGRES:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_ausencias_agenda.sql")
        linhas = [l for l in open(caminho, encoding="utf-8").read().splitlines() if not l.strip().startswith("--")]
        for comando in "\n".join(linhas).split(";"):
            if comando.strip():
                db.execute(comando)
        print("✅ Ausências da agenda: tabela, índice e coluna conferidos (Postgres)")
        return
    conn = db.get_db()
    existentes = {l["name"] for l in conn.execute("PRAGMA table_info(organizacoes)").fetchall()}
    if "agenda_duracao_padrao" in existentes:
        print("↷  organizacoes.agenda_duracao_padrao já existia (SQLite), pulei")
    else:
        conn.execute("ALTER TABLE organizacoes ADD COLUMN agenda_duracao_padrao INTEGER DEFAULT 50")
        print("✅ organizacoes.agenda_duracao_padrao adicionada (SQLite)")
    conn.executescript(DDL_SQLITE)
    conn.commit()
    print("✅ Ausências da agenda: tabela e índice conferidos (SQLite)")


if __name__ == "__main__":
    migrar()
