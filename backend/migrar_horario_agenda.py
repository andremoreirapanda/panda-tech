"""
Migração não-destrutiva: adiciona `agenda_hora_inicio` e `agenda_hora_fim`
(texto 'HH:MM') à tabela `organizacoes` — horário de funcionamento da
agenda (spec 24/09/2026). NULL = a grade se ajusta sozinha às consultas.

Mesmo padrão de `migrar_senha_alterada_em.py` — usa `db.py`, funciona
tanto local (SQLite) quanto em produção (Postgres via DATABASE_URL).

Rodar uma vez, depois de atualizar o código (git pull):

    cd backend
    source /caminho/do/virtualenv/bin/activate   # em produção, o mesmo
                                                   # ambiente do passenger_wsgi
    python3 migrar_horario_agenda.py

Confira que a saída termina com (Postgres) em produção — sem DATABASE_URL
no ambiente o script grava no SQLite local (ver CLAUDE.md, seção 7.2).
É seguro rodar mais de uma vez — coluna que já existe é pulada.
"""
import db

TABELA = "organizacoes"
COLUNAS = [("agenda_hora_inicio", "TEXT"), ("agenda_hora_fim", "TEXT")]


def _coluna_existe_sqlite(conn, coluna):
    linhas = conn.execute(f"PRAGMA table_info({TABELA})").fetchall()
    return any(l["name"] == coluna for l in linhas)


def _coluna_existe_postgres(coluna):
    linha = db.query_one(
        "SELECT 1 FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
        (TABELA, coluna),
    )
    return bool(linha)


def migrar():
    for coluna, tipo in COLUNAS:
        if db.USANDO_POSTGRES:
            if _coluna_existe_postgres(coluna):
                print(f"↷  {TABELA}.{coluna} já existia (Postgres), pulei")
                continue
            db.execute(f"ALTER TABLE {TABELA} ADD COLUMN {coluna} {tipo}")
            print(f"✅ {TABELA}.{coluna} adicionada (Postgres)")
        else:
            conn = db.get_db()
            if _coluna_existe_sqlite(conn, coluna):
                print(f"↷  {TABELA}.{coluna} já existia (SQLite), pulei")
                continue
            conn.execute(f"ALTER TABLE {TABELA} ADD COLUMN {coluna} {tipo}")
            conn.commit()
            print(f"✅ {TABELA}.{coluna} adicionada (SQLite)")


if __name__ == "__main__":
    migrar()
