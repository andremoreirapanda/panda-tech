-- ----------------------------------------------------------------------------
-- Migração incremental — Agenda: Ausência e duração padrão (07/10/2026)
--
-- Tabela nova `ausencias_profissional` e coluna `organizacoes.agenda_duracao_padrao`
-- (padrão 50). Idempotente. Rodar ANTES do `git pull`.
-- ----------------------------------------------------------------------------

ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS agenda_duracao_padrao INTEGER DEFAULT 50;

CREATE TABLE IF NOT EXISTS ausencias_profissional (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
    data_inicio     TEXT NOT NULL,
    data_fim        TEXT,
    dia_inteiro     INTEGER NOT NULL DEFAULT 0,
    hora_inicio     TEXT,
    hora_fim        TEXT,
    dias_semana     TEXT NOT NULL DEFAULT '123456',
    motivo          TEXT,
    criado_por      INTEGER REFERENCES usuarios(id),
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE INDEX IF NOT EXISTS idx_ausencias_prof ON ausencias_profissional(profissional_id, data_inicio);
