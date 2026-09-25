-- ----------------------------------------------------------------------------
-- Migração incremental — Pandoo fase 1 (25/09/2026). Idempotente.
-- ----------------------------------------------------------------------------
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS pandoo_cenario_padrao TEXT DEFAULT 'bambu';
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS pandoo_cenario_imagem TEXT;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS pandoo_cenario_tom TEXT;
ALTER TABLE modulos_clinica ADD COLUMN IF NOT EXISTS liberado_admin INTEGER DEFAULT 0;

CREATE TABLE IF NOT EXISTS pandoo_jogos (
    exercicio_id    INTEGER PRIMARY KEY REFERENCES exercicios(id),
    modelo          TEXT NOT NULL,
    conteudo_json   TEXT NOT NULL,
    regras_json     TEXT NOT NULL DEFAULT '{}',
    cenario         TEXT,
    total_itens     INTEGER DEFAULT 0,
    atualizado_em   TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS pandoo_resultados (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    exercicio_id    INTEGER NOT NULL REFERENCES exercicios(id),
    missao_id       INTEGER REFERENCES missoes(id),
    atividade_id    INTEGER REFERENCES atividades(id),
    modelo          TEXT NOT NULL,
    iniciado_em     TEXT,
    finalizado_em   TEXT,
    encerrado_antes INTEGER DEFAULT 0,
    total_rodadas   INTEGER DEFAULT 0,
    acertos         INTEGER DEFAULT 0,
    a_treinar       INTEGER DEFAULT 0,
    detalhes_json   TEXT NOT NULL DEFAULT '[]',
    usuario_id      INTEGER REFERENCES usuarios(id),
    data_local      TEXT NOT NULL,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_pandoo_res_paciente ON pandoo_resultados(paciente_id);
CREATE INDEX IF NOT EXISTS idx_pandoo_res_missao ON pandoo_resultados(missao_id, atividade_id, data_local);
