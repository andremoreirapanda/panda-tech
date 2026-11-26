-- IA fase 1, ditado por voz (25/11/2026): minutos no plano (NULL = herda da base), uso e créditos
-- extras por clínica/mês. Ninguém ganha o ditado no deploy: apaga as linhas `ia` que o módulo
-- (antes oculto) deixou em planos_modulos e modulos_clinica. O Admin liga plano a plano depois.
-- Rodar ANTES do deploy (senão as clínicas Pro veem o módulo, com 0 minutos). Seguro rodar de novo.
ALTER TABLE planos ADD COLUMN IF NOT EXISTS ia_minutos_mes INTEGER;

CREATE TABLE IF NOT EXISTS ia_uso (
    id                        SERIAL PRIMARY KEY,
    organizacao_id            INTEGER NOT NULL REFERENCES organizacoes(id),
    usuario_id                INTEGER REFERENCES usuarios(id),
    recurso                   TEXT NOT NULL,
    mes                       TEXT NOT NULL,
    segundos                  INTEGER NOT NULL DEFAULT 0,
    modelo                    TEXT,
    custo_estimado_micro_usd  INTEGER,
    sucesso                   INTEGER NOT NULL DEFAULT 1,
    criado_em                 TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_ia_uso_org_mes ON ia_uso(organizacao_id, mes);

CREATE TABLE IF NOT EXISTS ia_creditos (
    id                SERIAL PRIMARY KEY,
    organizacao_id    INTEGER NOT NULL REFERENCES organizacoes(id),
    mes               TEXT NOT NULL,
    minutos           INTEGER NOT NULL,
    motivo            TEXT,
    criado_por        INTEGER REFERENCES usuarios(id),
    criado_em         TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_ia_creditos_org_mes ON ia_creditos(organizacao_id, mes);

DELETE FROM planos_modulos WHERE modulo_codigo = 'ia';
DELETE FROM modulos_clinica WHERE modulo_codigo = 'ia';
