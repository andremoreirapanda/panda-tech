-- ----------------------------------------------------------------------------
-- Migração incremental — Fundo da clínica no app (26/09/2026, White Label)
--
-- Duas colunas novas em `organizacoes` (NULL = fundo padrão). Idempotente.
-- Rodar ANTES do `git pull` no servidor: o login lê as colunas novas.
-- ----------------------------------------------------------------------------

ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS app_fundo TEXT;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS app_fundo_cor TEXT;
