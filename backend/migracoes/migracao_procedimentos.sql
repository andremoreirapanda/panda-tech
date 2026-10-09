-- ----------------------------------------------------------------------------
-- Migração incremental — Procedimentos (09/10/2026)
--
-- Cadastro de procedimentos com valor (só o gestor) e, na consulta, o
-- procedimento e o valor do dia em que foi marcada. Idempotente.
-- Rodar ANTES do `git pull`.
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS procedimentos (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    codigo          TEXT,
    nome            TEXT NOT NULL,
    valor_centavos  INTEGER NOT NULL DEFAULT 0,
    ativo           INTEGER NOT NULL DEFAULT 1,
    ordem           INTEGER NOT NULL DEFAULT 0,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')),
    atualizado_em   TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_procedimento_nome ON procedimentos(organizacao_id, LOWER(TRIM(nome)));

ALTER TABLE consultas ADD COLUMN IF NOT EXISTS procedimento_id INTEGER REFERENCES procedimentos(id);

ALTER TABLE consultas ADD COLUMN IF NOT EXISTS procedimento_valor_centavos INTEGER;
