-- ----------------------------------------------------------------------------
-- Migração incremental — frequência configurável de missões 'semanal'
-- (achado de UAT, 26/08/2026): o número de dias de check exigido pra fechar
-- uma missão semanal era fixo em 7 no código (jornada_bp.py). Virou
-- configurável por missão, guardado em `missoes.frequencia_dias`.
--
-- Rodar isoladamente (não é o schema_postgres.sql inteiro) porque o banco de
-- produção já tem a tabela `missoes` criada — reaplicar o schema inteiro
-- erraria em "relation already exists" antes de chegar aqui. Usa
-- `ADD COLUMN IF NOT EXISTS` para poder ser executado mais de uma vez com
-- segurança (idempotente), igual ao padrão já usado em
-- migracao_integracoes_plataforma.sql. DEFAULT 7 preserva o comportamento de
-- sempre para toda missão semanal já existente antes desta migração.
-- ----------------------------------------------------------------------------

ALTER TABLE missoes ADD COLUMN IF NOT EXISTS frequencia_dias INTEGER DEFAULT 7;
