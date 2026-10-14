"""
Migração não-destrutiva: logo da plataforma (14/10/2026) — tabela
`plataforma_identidade` (uma linha só, id = 1).

Mesmo padrão dos outros `migrar_*.py` — usa `db.py`, funciona tanto local
(SQLite) quanto em produção (Postgres via DATABASE_URL). Em produção, prefira
rodar `migracoes/migracao_logo_plataforma.sql` no SQL Editor do Supabase.

    cd backend
    python3 migrar_logo_plataforma.py

Confira que a saída termina com (Postgres) em produção — sem DATABASE_URL
no ambiente o script grava no SQLite local (ver CLAUDE.md, seção 7.2).
É seguro rodar mais de uma vez (CREATE TABLE IF NOT EXISTS).
"""
import os

import db

SQL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_logo_plataforma.sql")


def migrar():
    with open(SQL, encoding="utf-8") as f:
        comando = "\n".join(l for l in f.read().splitlines() if not l.strip().startswith("--")).strip().rstrip(";")
    if db.USANDO_POSTGRES:
        db.execute(comando)
    else:
        conn = db.get_db()
        conn.execute(comando)
        conn.commit()
    print(f"✅ tabela plataforma_identidade pronta ({'Postgres' if db.USANDO_POSTGRES else 'SQLite'})")


if __name__ == "__main__":
    migrar()
