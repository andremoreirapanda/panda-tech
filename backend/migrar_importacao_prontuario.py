"""
Migração não-destrutiva: importação do prontuário (26/10/2026) — colunas
`origem` e `importacao_chave` em `diarios_terapeuticos` e o índice
`idx_diario_importacao_chave`.

Mesmo padrão dos outros `migrar_*.py` — usa `db.py`, funciona tanto local
(SQLite) quanto em produção (Postgres via DATABASE_URL). Em produção, prefira
rodar `migracoes/migracao_importacao_prontuario.sql` no SQL Editor do Supabase.

    cd backend
    python3 migrar_importacao_prontuario.py

Confira que a saída termina com (Postgres) em produção — sem DATABASE_URL
no ambiente o script grava no SQLite local (ver CLAUDE.md, seção 7.2).
É seguro rodar mais de uma vez.
"""
import db

INDICE = "CREATE INDEX IF NOT EXISTS idx_diario_importacao_chave ON diarios_terapeuticos(paciente_id, importacao_chave)"


def migrar():
    if db.USANDO_POSTGRES:
        db.execute("ALTER TABLE diarios_terapeuticos ADD COLUMN IF NOT EXISTS origem TEXT")
        db.execute("ALTER TABLE diarios_terapeuticos ADD COLUMN IF NOT EXISTS importacao_chave TEXT")
        db.execute(INDICE)
    else:
        conn = db.get_db()
        colunas = [l["name"] for l in conn.execute("PRAGMA table_info(diarios_terapeuticos)").fetchall()]
        for coluna in ("origem", "importacao_chave"):
            if coluna not in colunas:
                conn.execute(f"ALTER TABLE diarios_terapeuticos ADD COLUMN {coluna} TEXT")
        conn.execute(INDICE)
        conn.commit()
    print(f"✅ diarios_terapeuticos pronta para a importação ({'Postgres' if db.USANDO_POSTGRES else 'SQLite'})")


if __name__ == "__main__":
    migrar()
