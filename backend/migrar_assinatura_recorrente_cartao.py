"""
Migração não-destrutiva: cria a tabela `assinaturas_cartao_recorrentes`,
usada pela assinatura recorrente no cartão de crédito (Fase 2 da cobrança
por cartão, Plataforma → Clínicas, 15/09/2026) — Panda Tech cobrando a
clínica automaticamente todo mês, via "preapproval" da Mercado Pago, sem
depender do cron mensal nem do botão "Gerar cobranças agora". Ver a seção
"Assinatura recorrente no cartão" em pagamento_plataforma_service.py.

Mesmo padrão de `migrar_cobrancas_planos_avulsas.py` — funciona tanto local
(SQLite) quanto em produção (Postgres via DATABASE_URL), usando db.py, que
já escolhe o backend certo sozinho.

Rodar uma vez, depois de atualizar o código (git pull):

    cd backend
    source /caminho/do/virtualenv/bin/activate   # em produção, o mesmo
                                                   # ambiente do passenger_wsgi
    python3 migrar_assinatura_recorrente_cartao.py

É seguro rodar mais de uma vez — usa CREATE TABLE IF NOT EXISTS.
"""
import db

_SQL_SQLITE = """
CREATE TABLE IF NOT EXISTS assinaturas_cartao_recorrentes (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id     INTEGER NOT NULL UNIQUE REFERENCES organizacoes(id),
    mp_preapproval_id  TEXT,
    status             TEXT DEFAULT 'pendente' CHECK(status IN ('pendente','ativa','pausada','cancelada')),
    valor_centavos     INTEGER NOT NULL,
    criado_em          TEXT DEFAULT (datetime('now')),
    atualizado_em      TEXT
)
"""

_SQL_POSTGRES = """
CREATE TABLE IF NOT EXISTS assinaturas_cartao_recorrentes (
    id                 SERIAL PRIMARY KEY,
    organizacao_id     INTEGER NOT NULL UNIQUE REFERENCES organizacoes(id),
    mp_preapproval_id  TEXT,
    status             TEXT DEFAULT 'pendente' CHECK(status IN ('pendente','ativa','pausada','cancelada')),
    valor_centavos     INTEGER NOT NULL,
    criado_em          TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')),
    atualizado_em      TEXT
)
"""

# `cobrancas_planos.descricao` — em produção (Postgres) só existia via
# migrar_cobrancas_planos_avulsas.py; schema_postgres.sql não refletia a
# coluna (drift entre o arquivo-base e o banco real). A correção de
# 15/09/2026 em `_ja_gerada_no_mes` passou a depender dela sempre existir,
# então este script confirma/adiciona também, por segurança — idempotente,
# igual ao script de origem.
_SQL_POSTGRES_DESCRICAO = "ALTER TABLE cobrancas_planos ADD COLUMN IF NOT EXISTS descricao TEXT"


def _coluna_existe_sqlite(conn, tabela, coluna):
    linhas = conn.execute(f"PRAGMA table_info({tabela})").fetchall()
    return any(l["name"] == coluna for l in linhas)


def migrar():
    if db.USANDO_POSTGRES:
        db.execute(_SQL_POSTGRES)
        db.execute(_SQL_POSTGRES_DESCRICAO)
        print("✅ assinaturas_cartao_recorrentes pronta (Postgres)")
    else:
        conn = db.get_db()
        conn.execute(_SQL_SQLITE)
        if not _coluna_existe_sqlite(conn, "cobrancas_planos", "descricao"):
            conn.execute("ALTER TABLE cobrancas_planos ADD COLUMN descricao TEXT")
        conn.commit()
        print("✅ assinaturas_cartao_recorrentes pronta (SQLite)")


if __name__ == "__main__":
    migrar()
