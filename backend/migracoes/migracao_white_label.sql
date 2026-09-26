-- ----------------------------------------------------------------------------
-- Migração incremental — White Label completo (25/09/2026)
--
-- Colunas novas em `organizacoes` (NULL = padrão Panda Tech) e o índice único
-- do endereço da tela de login da clínica (#/entrar/<endereco>). Só ADD
-- COLUMN / CREATE INDEX IF NOT EXISTS — seguro rodar mais de uma vez.
-- Rodar ANTES do `git pull` no servidor: o login lê as colunas novas.
-- ----------------------------------------------------------------------------

ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS endereco_login TEXT;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS app_nome TEXT;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS app_icone_base64 TEXT;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS login_mensagem TEXT;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS mundo_fonte TEXT;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS mundo_fundo TEXT;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS mundo_mascote TEXT;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS mundo_mascote_imagem TEXT;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS mundo_comemoracao TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_organizacoes_endereco_login ON organizacoes(endereco_login);
