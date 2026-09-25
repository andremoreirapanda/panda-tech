-- ----------------------------------------------------------------------------
-- Migração incremental — Horário de funcionamento da agenda (24/09/2026)
--
-- Duas colunas novas em `organizacoes`, 'HH:MM', NULL por padrão (= faixa
-- automática na grade da agenda). ADD COLUMN IF NOT EXISTS é idempotente —
-- seguro rodar mais de uma vez.
-- ----------------------------------------------------------------------------

ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS agenda_hora_inicio TEXT;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS agenda_hora_fim TEXT;
