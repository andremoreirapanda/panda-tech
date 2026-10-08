-- ----------------------------------------------------------------------------
-- Migração incremental — Planos terapêuticos por especialidade (08/10/2026)
--
-- Coluna `especialidade` em `planos_terapeuticos`; os planos existentes recebem
-- a especialidade de quem criou, ou 'Geral'. Idempotente. Rodar ANTES do
-- `git pull`.
-- ----------------------------------------------------------------------------

ALTER TABLE planos_terapeuticos ADD COLUMN IF NOT EXISTS especialidade TEXT;

UPDATE planos_terapeuticos p SET especialidade = COALESCE(NULLIF(TRIM(u.especialidade), ''), 'Geral')
  FROM usuarios u WHERE u.id = p.profissional_id AND p.especialidade IS NULL;

UPDATE planos_terapeuticos SET especialidade = 'Geral' WHERE especialidade IS NULL;
