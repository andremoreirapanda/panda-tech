-- ----------------------------------------------------------------------------
-- Migração incremental — Perfil "Secretária" (insight do usuário, 31/08/2026)
--
-- 1) `usuarios.papel` só aceitava 'admin_master' | 'gestor' | 'profissional' |
--    'responsavel' — passa a aceitar também 'secretaria'. DROP CONSTRAINT
--    IF EXISTS + ADD CONSTRAINT é idempotente — seguro rodar mais de uma vez.
--    "usuarios_papel_check" é o nome que o Postgres dá automaticamente a um
--    CHECK inline sem nome explícito (convenção <tabela>_<coluna>_check),
--    que é como a tabela foi criada originalmente em schema_postgres.sql
--    (mesmo padrão já usado em migracao_forma_pagamento_cartao.sql).
--
-- 2) `planos.limite_secretarias` — quantas secretárias cada plano permite
--    cadastrar (NULL = ilimitado, 0 = não incluído). ADD COLUMN IF NOT
--    EXISTS é idempotente. Os valores de partida abaixo só são aplicados
--    UMA vez (a condição "IS NULL" evita sobrescrever um ajuste manual feito
--    depois pelo Admin em Planos): Starter fica em 0 (recurso pago à parte),
--    Pro ganha 1 de cortesia, Enterprise fica ilimitado (NULL, já é o
--    padrão da coluna nova).
-- ----------------------------------------------------------------------------

ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_papel_check;
ALTER TABLE usuarios ADD CONSTRAINT usuarios_papel_check
    CHECK (papel IN ('admin_master', 'gestor', 'profissional', 'responsavel', 'secretaria'));

ALTER TABLE planos ADD COLUMN IF NOT EXISTS limite_secretarias INTEGER;

UPDATE planos SET limite_secretarias = 0 WHERE codigo = 'starter' AND limite_secretarias IS NULL;
UPDATE planos SET limite_secretarias = 1 WHERE codigo = 'pro' AND limite_secretarias IS NULL;
-- 'enterprise' fica NULL (ilimitado) — já é o padrão da coluna recém-criada.
