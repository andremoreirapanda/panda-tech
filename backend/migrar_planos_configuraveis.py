"""
Migração não-destrutiva dos planos configuráveis (25/09/2026): colunas
`planos.plano_base_id` e `planos.disponivel_ate`, tabela `planos_modulos`
preenchida com o mesmo resultado do mapa que estava no código, e pacientes
ilimitados em todos os planos. Em produção (Postgres) aplica
`migracoes/migracao_planos_configuraveis.sql`; local (SQLite) usa o DDL
equivalente + planos_padrao.aplicar_modulos_padrao().

    cd backend && python3 migrar_planos_configuraveis.py

Confira que a saída termina com (Postgres) em produção (ver CLAUDE.md, seção
7.2). Seguro rodar mais de uma vez — não desfaz ajuste feito pelo Admin.
"""
import os

import db
from planos_padrao import aplicar_modulos_padrao

COLUNAS = [("plano_base_id", "INTEGER REFERENCES planos(id)"), ("disponivel_ate", "TEXT")]

DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS planos_modulos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plano_id INTEGER NOT NULL REFERENCES planos(id),
    modulo_codigo TEXT NOT NULL,
    UNIQUE(plano_id, modulo_codigo)
);
"""


def migrar():
    if db.USANDO_POSTGRES:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_planos_configuraveis.sql")
        sql = open(caminho, encoding="utf-8").read()
        linhas = [l for l in sql.splitlines() if not l.strip().startswith("--")]
        for comando in "\n".join(linhas).split(";"):
            if comando.strip():
                db.execute(comando)
        print("✅ Planos configuráveis: colunas, tabela e módulos padrão conferidos (Postgres)")
        return
    conn = db.get_db()
    existentes = {l["name"] for l in conn.execute("PRAGMA table_info(planos)").fetchall()}
    for coluna, tipo in COLUNAS:
        if coluna in existentes:
            print(f"↷  planos.{coluna} já existia (SQLite), pulei")
            continue
        conn.execute(f"ALTER TABLE planos ADD COLUMN {coluna} {tipo}")
        print(f"✅ planos.{coluna} adicionada (SQLite)")
    conn.executescript(DDL_SQLITE)
    conn.commit()
    aplicar_modulos_padrao()
    print("✅ Planos configuráveis: tabela e módulos padrão conferidos (SQLite)")


if __name__ == "__main__":
    migrar()
