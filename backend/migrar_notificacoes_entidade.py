"""
Migração não-destrutiva: adiciona as colunas `entidade` (texto) e
`entidade_id` (inteiro) à tabela `notificacoes` — identificam do que trata
cada notificação (hoje: 'paciente' para missao/conquista/diario/mensagem,
'assinatura' para financeiro), usadas pelo frontend pra levar o clique no
sininho direto pra tela certa em vez de só abrir o painel.

Mesmo padrão de `migrar_cobrancas_planos_avulsas.py` — usa `db.py`, funciona
tanto local (SQLite) quanto em produção (Postgres via DATABASE_URL).

Rodar uma vez, depois de atualizar o código (git pull):

    cd backend
    source /caminho/do/virtualenv/bin/activate   # em produção, o mesmo
                                                   # ambiente do passenger_wsgi
    python3 migrar_notificacoes_entidade.py

É seguro rodar mais de uma vez — se as colunas já existirem, o script
detecta e não faz nada.
"""
import db

COLUNAS = [
    ("entidade", "TEXT"),
    ("entidade_id", "INTEGER"),
]


def _coluna_existe_sqlite(conn, tabela, coluna):
    linhas = conn.execute(f"PRAGMA table_info({tabela})").fetchall()
    return any(l["name"] == coluna for l in linhas)


def _coluna_existe_postgres(coluna):
    linha = db.query_one(
        "SELECT 1 FROM information_schema.columns WHERE table_name = 'notificacoes' AND column_name = ?",
        (coluna,),
    )
    return bool(linha)


def migrar():
    if db.USANDO_POSTGRES:
        for coluna, tipo in COLUNAS:
            if _coluna_existe_postgres(coluna):
                print(f"↷  notificacoes.{coluna} já existia (Postgres), pulei")
                continue
            db.execute(f"ALTER TABLE notificacoes ADD COLUMN {coluna} {tipo}")
            print(f"✅ notificacoes.{coluna} adicionada (Postgres)")
    else:
        conn = db.get_db()
        for coluna, tipo in COLUNAS:
            if _coluna_existe_sqlite(conn, "notificacoes", coluna):
                print(f"↷  notificacoes.{coluna} já existia (SQLite), pulei")
                continue
            conn.execute(f"ALTER TABLE notificacoes ADD COLUMN {coluna} {tipo}")
            conn.commit()
            print(f"✅ notificacoes.{coluna} adicionada (SQLite)")


if __name__ == "__main__":
    migrar()
