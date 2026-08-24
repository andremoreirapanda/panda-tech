"""
Migração não-destrutiva: adiciona a coluna `descricao` (texto livre, opcional)
à tabela `cobrancas_planos`, usada pela cobrança avulsa das clínicas
(Admin > Cobranças das Clínicas > "Cobrança avulsa").

Diferente de `migrar_integracoes.py` (que só sabe falar SQLite direto via
`sqlite3.connect`), este script funciona tanto local (SQLite) quanto em
produção (Postgres via DATABASE_URL) — usa `db.py`, que já escolhe o
backend certo sozinho, exatamente como o resto do backend faz.

Rodar uma vez, depois de atualizar o código (git pull):

    cd backend
    source /caminho/do/virtualenv/bin/activate   # em produção, o mesmo
                                                   # ambiente do passenger_wsgi
    python3 migrar_cobrancas_planos_avulsas.py

É seguro rodar mais de uma vez — se a coluna já existir, o script detecta e
não faz nada.
"""
import db


def _coluna_existe_sqlite(conn, tabela, coluna):
    linhas = conn.execute(f"PRAGMA table_info({tabela})").fetchall()
    return any(l["name"] == coluna for l in linhas)


def _coluna_existe_postgres(coluna):
    # `?` de propósito — a própria db.query_one() já traduz para `%s` no
    # Postgres (ver `_preparar_sql` em db.py), mesma convenção do resto do
    # backend.
    linha = db.query_one(
        "SELECT 1 FROM information_schema.columns WHERE table_name = 'cobrancas_planos' AND column_name = ?",
        (coluna,),
    )
    return bool(linha)


def migrar():
    if db.USANDO_POSTGRES:
        if _coluna_existe_postgres("descricao"):
            print("↷  cobrancas_planos.descricao já existia (Postgres), pulei")
            return
        db.execute("ALTER TABLE cobrancas_planos ADD COLUMN descricao TEXT")
        print("✅ cobrancas_planos.descricao adicionada (Postgres)")
    else:
        conn = db.get_db()
        if _coluna_existe_sqlite(conn, "cobrancas_planos", "descricao"):
            print("↷  cobrancas_planos.descricao já existia (SQLite), pulei")
            return
        conn.execute("ALTER TABLE cobrancas_planos ADD COLUMN descricao TEXT")
        conn.commit()
        print("✅ cobrancas_planos.descricao adicionada (SQLite)")


if __name__ == "__main__":
    migrar()
