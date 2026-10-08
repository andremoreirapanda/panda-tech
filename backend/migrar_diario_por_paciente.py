"""
Migração não-destrutiva (spec 08/10/2026): `diarios_terapeuticos.paciente_id`,
preenchida a partir da jornada, e `jornada_id` opcional.

    cd backend
    python3 migrar_diario_por_paciente.py

Confira que a saída termina com (Postgres) em produção — sem DATABASE_URL o
script grava no SQLite local (CLAUDE.md, seção 7.2). Seguro rodar de novo.
No SQLite o NOT NULL antigo de `jornada_id` só some recriando o banco local
(`seed.py`) — o SQLite não altera restrição de coluna existente.
"""
import os

import db

PREENCHER_SQLITE = """UPDATE diarios_terapeuticos SET paciente_id =
    (SELECT paciente_id FROM jornadas j WHERE j.id = diarios_terapeuticos.jornada_id)
    WHERE paciente_id IS NULL"""


def migrar():
    if db.USANDO_POSTGRES:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_diario_por_paciente.sql")
        linhas = [l for l in open(caminho, encoding="utf-8").read().splitlines() if not l.strip().startswith("--")]
        for comando in "\n".join(linhas).split(";"):
            if comando.strip():
                db.execute(comando)
        print("✅ Diário por paciente: coluna, preenchimento e índice conferidos (Postgres)")
        return
    conn = db.get_db()
    existentes = {l["name"] for l in conn.execute("PRAGMA table_info(diarios_terapeuticos)").fetchall()}
    if "paciente_id" in existentes:
        print("↷  diarios_terapeuticos.paciente_id já existia (SQLite), pulei")
    else:
        conn.execute("ALTER TABLE diarios_terapeuticos ADD COLUMN paciente_id INTEGER REFERENCES pacientes(id)")
        print("✅ diarios_terapeuticos.paciente_id adicionada (SQLite)")
    conn.execute(PREENCHER_SQLITE)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_diarios_paciente ON diarios_terapeuticos(paciente_id, data_atendimento)")
    conn.commit()
    print("✅ Diário por paciente: preenchimento e índice conferidos (SQLite)")


if __name__ == "__main__":
    migrar()
