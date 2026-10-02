-- ----------------------------------------------------------------------------
-- Migração incremental — Excluir alguém da Equipe (01/10/2026)
--
-- Coluna nova em `usuarios` (NULL = não excluído). Quem é excluído e tem
-- histórico continua na tabela (o nome aparece nos registros antigos), mas
-- some da Equipe para sempre. Idempotente. Rodar ANTES do `git pull`.
-- ----------------------------------------------------------------------------

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS excluido_em TEXT;
