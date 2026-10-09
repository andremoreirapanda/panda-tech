"""
Migração (08/10/2026, Atender/Evoluir): status novos em `consultas`, coluna
`diarios_terapeuticos.observacao` e índice único `idx_diario_por_consulta`.

    cd backend
    python3 migrar_atender.py

Confira que a saída termina com (Postgres) em produção (CLAUDE.md, 7.2).
Seguro rodar de novo. No SQLite a regra de status (CHECK) só muda recriando
o banco local com o `seed.py` — o SQLite não altera CHECK de tabela existente.
"""
import os

import db


def migrar():
    if db.USANDO_POSTGRES:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_atender.sql")
        linhas = [l for l in open(caminho, encoding="utf-8").read().splitlines() if not l.strip().startswith("--")]
        for comando in "\n".join(linhas).split(";"):
            if comando.strip():
                db.execute(comando)
        print("✅ Atender: status, observação e índice conferidos (Postgres)")
        return
    conn = db.get_db()
    existentes = {l["name"] for l in conn.execute("PRAGMA table_info(diarios_terapeuticos)").fetchall()}
    if "observacao" in existentes:
        print("↷  diarios_terapeuticos.observacao já existia (SQLite), pulei")
    else:
        conn.execute("ALTER TABLE diarios_terapeuticos ADD COLUMN observacao TEXT")
        print("✅ diarios_terapeuticos.observacao adicionada (SQLite)")
    conn.execute("""UPDATE diarios_terapeuticos SET consulta_id = NULL WHERE consulta_id IS NOT NULL AND id NOT IN (
                    SELECT MAX(id) FROM diarios_terapeuticos WHERE consulta_id IS NOT NULL GROUP BY consulta_id)""")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_diario_por_consulta ON diarios_terapeuticos(consulta_id) WHERE consulta_id IS NOT NULL")
    conn.commit()
    print("✅ Atender: índice conferido (SQLite)")


if __name__ == "__main__":
    migrar()
