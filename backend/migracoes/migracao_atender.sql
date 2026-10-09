-- ----------------------------------------------------------------------------
-- Migração incremental — Atender/Evoluir (08/10/2026)
--
-- Status novos da consulta (falta justificada, desmarcada pelo profissional),
-- observação no Diário e um registro do Diário por consulta. Idempotente.
-- Rodar ANTES do `git pull`.
-- ----------------------------------------------------------------------------

ALTER TABLE consultas DROP CONSTRAINT IF EXISTS consultas_status_check;

ALTER TABLE consultas ADD CONSTRAINT consultas_status_check
  CHECK (status IN ('agendada','confirmada','realizada','cancelada','faltou','falta_justificada','desmarcada_profissional'));

ALTER TABLE diarios_terapeuticos ADD COLUMN IF NOT EXISTS observacao TEXT;

UPDATE diarios_terapeuticos SET consulta_id = NULL
 WHERE consulta_id IS NOT NULL AND id NOT IN (
   SELECT MAX(id) FROM diarios_terapeuticos WHERE consulta_id IS NOT NULL GROUP BY consulta_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_diario_por_consulta
  ON diarios_terapeuticos(consulta_id) WHERE consulta_id IS NOT NULL;
