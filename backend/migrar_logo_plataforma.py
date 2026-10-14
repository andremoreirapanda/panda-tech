"""
Migração não-destrutiva: logo da plataforma — tabela `plataforma_identidade`
(14/10/2026, uma linha só, id = 1) e a coluna `logo_login_base64` (15/10/2026,
logo para o fundo roxo do login).

Mesmo padrão dos outros `migrar_*.py` — usa `db.py`, funciona tanto local
(SQLite) quanto em produção (Postgres via DATABASE_URL). Em produção, prefira
rodar `migracoes/migracao_logo_plataforma.sql` no SQL Editor do Supabase.

    cd backend
    python3 migrar_logo_plataforma.py

Confira que a saída termina com (Postgres) em produção — sem DATABASE_URL
no ambiente o script grava no SQLite local (ver CLAUDE.md, seção 7.2).
É seguro rodar mais de uma vez.
"""
import db

CRIAR = """CREATE TABLE IF NOT EXISTS plataforma_identidade (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    logo_base64       TEXT,
    logo_login_base64 TEXT,
    atualizado_em     TEXT
)"""


def migrar():
    if db.USANDO_POSTGRES:
        db.execute(CRIAR)
        db.execute("ALTER TABLE plataforma_identidade ADD COLUMN IF NOT EXISTS logo_login_base64 TEXT")
    else:
        conn = db.get_db()
        conn.execute(CRIAR)
        colunas = [l["name"] for l in conn.execute("PRAGMA table_info(plataforma_identidade)").fetchall()]
        if "logo_login_base64" not in colunas:
            conn.execute("ALTER TABLE plataforma_identidade ADD COLUMN logo_login_base64 TEXT")
        conn.commit()
    print(f"✅ tabela plataforma_identidade pronta ({'Postgres' if db.USANDO_POSTGRES else 'SQLite'})")


if __name__ == "__main__":
    migrar()
