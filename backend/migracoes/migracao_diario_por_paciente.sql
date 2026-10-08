-- ----------------------------------------------------------------------------
-- Migração incremental — Diário Terapêutico por paciente (08/10/2026)
--
-- O diário passa a ser do paciente (coluna `paciente_id`, preenchida a partir
-- da jornada nos registros antigos) e a jornada vira opcional. Idempotente.
-- Rodar ANTES do `git pull`.
-- ----------------------------------------------------------------------------

ALTER TABLE diarios_terapeuticos ADD COLUMN IF NOT EXISTS paciente_id INTEGER REFERENCES pacientes(id);

UPDATE diarios_terapeuticos d SET paciente_id = j.paciente_id
  FROM jornadas j WHERE j.id = d.jornada_id AND d.paciente_id IS NULL;

ALTER TABLE diarios_terapeuticos ALTER COLUMN jornada_id DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_diarios_paciente ON diarios_terapeuticos(paciente_id, data_atendimento);
