-- ----------------------------------------------------------------------------
-- Migração incremental — Fase 1 da cobrança por cartão de crédito
-- (Plataforma → Clínicas, 26/08/2026): `cobrancas_planos.forma_confirmacao`
-- só aceitava 'mercadopago_pix' ou 'manual' — passa a aceitar também
-- 'mercadopago_cartao', usado quando o Gestor paga a assinatura da própria
-- clínica no cartão (Card Payment Brick, tela "Sua Assinatura") em vez de
-- PIX.
--
-- Rodar isoladamente (não é o schema_postgres.sql inteiro) porque o banco de
-- produção já tem a tabela `cobrancas_planos` criada. DROP CONSTRAINT
-- IF EXISTS + ADD CONSTRAINT é idempotente — seguro rodar mais de uma vez.
-- "cobrancas_planos_forma_confirmacao_check" é o nome que o Postgres dá
-- automaticamente a um CHECK inline sem nome explícito (convenção
-- <tabela>_<coluna>_check), que é como a tabela foi criada originalmente em
-- schema_postgres.sql.
-- ----------------------------------------------------------------------------

ALTER TABLE cobrancas_planos DROP CONSTRAINT IF EXISTS cobrancas_planos_forma_confirmacao_check;
ALTER TABLE cobrancas_planos ADD CONSTRAINT cobrancas_planos_forma_confirmacao_check
    CHECK (forma_confirmacao IN ('mercadopago_pix', 'mercadopago_cartao', 'manual'));
