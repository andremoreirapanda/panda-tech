-- ----------------------------------------------------------------------------
-- Migração incremental — Pastas da Biblioteca, até 2 níveis (insight do
-- usuário, 09/09/2026)
--
-- 1) `categorias_exercicio.organizacao_id` era NOT NULL — passa a aceitar
--    NULL, mesmo padrão já usado em `exercicios.organizacao_id` (NULL =
--    Biblioteca da Plataforma). É isso que permite o Admin do SaaS também
--    organizar seu catálogo em pastas, separado da árvore de cada clínica.
--
-- 2) `pasta_pai_id` — referência pra outra linha da própria tabela. NULL =
--    pasta de primeiro nível. Preenchido = subpasta (filha da pasta
--    apontada). O limite de 2 níveis (pasta → subpasta, sem sub-subpasta)
--    é validado só na aplicação (biblioteca_bp.py), não há CHECK de
--    profundidade no banco.
--
-- ADD COLUMN IF NOT EXISTS e DROP NOT NULL são idempotentes — seguro rodar
-- mais de uma vez.
-- ----------------------------------------------------------------------------

ALTER TABLE categorias_exercicio ALTER COLUMN organizacao_id DROP NOT NULL;
ALTER TABLE categorias_exercicio ADD COLUMN IF NOT EXISTS pasta_pai_id INTEGER REFERENCES categorias_exercicio(id);
