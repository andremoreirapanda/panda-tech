"""
Migração não-destrutiva (spec 08/10/2026): `planos_terapeuticos.especialidade`,
preenchida com a especialidade de quem criou o plano (ou 'Geral').

    cd backend
    python3 migrar_planos_especialidade.py

Confira que a saída termina com (Postgres) em produção — sem DATABASE_URL o
script grava no SQLite local (CLAUDE.md, seção 7.2). Seguro rodar de novo.
"""
import os

import db

PREENCHER_SQLITE = [
    """UPDATE planos_terapeuticos SET especialidade = (
         SELECT COALESCE(NULLIF(TRIM(u.especialidade), ''), 'Geral') FROM usuarios u
         WHERE u.id = planos_terapeuticos.profissional_id)
       WHERE especialidade IS NULL""",
    "UPDATE planos_terapeuticos SET especialidade = 'Geral' WHERE especialidade IS NULL",
]


def migrar():
    if db.USANDO_POSTGRES:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_planos_especialidade.sql")
        linhas = [l for l in open(caminho, encoding="utf-8").read().splitlines() if not l.strip().startswith("--")]
        for comando in "\n".join(linhas).split(";"):
            if comando.strip():
                db.execute(comando)
        print("✅ Planos por especialidade: coluna e preenchimento conferidos (Postgres)")
        return
    conn = db.get_db()
    existentes = {l["name"] for l in conn.execute("PRAGMA table_info(planos_terapeuticos)").fetchall()}
    if "especialidade" in existentes:
        print("↷  planos_terapeuticos.especialidade já existia (SQLite), pulei")
    else:
        conn.execute("ALTER TABLE planos_terapeuticos ADD COLUMN especialidade TEXT")
        print("✅ planos_terapeuticos.especialidade adicionada (SQLite)")
    for sql in PREENCHER_SQLITE:
        conn.execute(sql)
    conn.commit()
    print("✅ Planos por especialidade: preenchimento conferido (SQLite)")


if __name__ == "__main__":
    migrar()
