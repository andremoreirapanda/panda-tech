"""
Migração (09/10/2026, Procedimentos): tabela `procedimentos`, índice
`idx_procedimento_nome` e as colunas `consultas.procedimento_id` /
`consultas.procedimento_valor_centavos`.

    cd backend
    python3 migrar_procedimentos.py

Confira que a saída termina com (Postgres) em produção (CLAUDE.md, 7.2).
Seguro rodar de novo.
"""
import os

import db


def migrar():
    if db.USANDO_POSTGRES:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_procedimentos.sql")
        linhas = [l for l in open(caminho, encoding="utf-8").read().splitlines() if not l.strip().startswith("--")]
        for comando in "\n".join(linhas).split(";"):
            if comando.strip():
                db.execute(comando)
        print("✅ Procedimentos: tabela, índice e colunas conferidos (Postgres)")
        return
    conn = db.get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS procedimentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organizacao_id INTEGER NOT NULL REFERENCES organizacoes(id),
        codigo TEXT, nome TEXT NOT NULL, valor_centavos INTEGER NOT NULL DEFAULT 0,
        ativo INTEGER NOT NULL DEFAULT 1, ordem INTEGER NOT NULL DEFAULT 0,
        criado_em TEXT DEFAULT (datetime('now')), atualizado_em TEXT DEFAULT (datetime('now')))""")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_procedimento_nome ON procedimentos(organizacao_id, LOWER(TRIM(nome)))")
    existentes = {l["name"] for l in conn.execute("PRAGMA table_info(consultas)").fetchall()}
    for coluna, tipo in (("procedimento_id", "INTEGER REFERENCES procedimentos(id)"), ("procedimento_valor_centavos", "INTEGER")):
        if coluna in existentes:
            print(f"↷  consultas.{coluna} já existia (SQLite), pulei")
        else:
            conn.execute(f"ALTER TABLE consultas ADD COLUMN {coluna} {tipo}")
            print(f"✅ consultas.{coluna} adicionada (SQLite)")
    conn.commit()
    print("✅ Procedimentos: tabela e índice conferidos (SQLite)")


if __name__ == "__main__":
    migrar()
