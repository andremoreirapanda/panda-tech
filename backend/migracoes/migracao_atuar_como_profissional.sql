-- ----------------------------------------------------------------------------
-- Migração incremental — Gestor pode opcionalmente atuar como profissional
-- (insight do usuário): "o gestor poder se inserir como um profissional da
-- clínica com o mesmo login e senha que está cadastrado, essa opção ser
-- opcional". Adiciona a flag `atua_como_profissional` em `usuarios` — quando
-- ligada, o gestor reaproveita as colunas já existentes
-- (especialidade/tipo_registro/numero_registro/cor_agenda) e passa a poder
-- ser atribuído em consultas e vinculado a pacientes como profissional (ver
-- pessoas_bp.py e agenda_bp.py).
--
-- Rodar isoladamente (não é o schema_postgres.sql inteiro) porque o banco de
-- produção já tem a tabela `usuarios` criada — reaplicar o schema inteiro
-- erraria em "relation already exists" antes de chegar aqui. Usa
-- `ADD COLUMN IF NOT EXISTS`, mesmo padrão idempotente já usado em
-- migracao_frequencia_missao.sql. DEFAULT 0 preserva o comportamento de
-- sempre (desligado) para todo usuário já existente.
-- ----------------------------------------------------------------------------

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS atua_como_profissional INTEGER NOT NULL DEFAULT 0;
