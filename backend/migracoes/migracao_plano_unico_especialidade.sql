-- ----------------------------------------------------------------------------
-- Migração incremental — Um plano ativo por especialidade no banco (08/10/2026)
--
-- Se já houver dois planos ativos da mesma especialidade na mesma jornada
-- (ignorando caixa/espaços), fica o mais novo e os outros são encerrados.
-- Depois cria o índice único que impede isso de novo. Idempotente.
-- ----------------------------------------------------------------------------

UPDATE planos_terapeuticos SET status = 'encerrado'
 WHERE status = 'ativo' AND especialidade IS NOT NULL AND id NOT IN (
   SELECT MAX(id) FROM planos_terapeuticos
    WHERE status = 'ativo' AND especialidade IS NOT NULL
    GROUP BY jornada_id, LOWER(TRIM(especialidade)));

CREATE UNIQUE INDEX IF NOT EXISTS idx_plano_ativo_especialidade
  ON planos_terapeuticos (jornada_id, LOWER(TRIM(especialidade))) WHERE status = 'ativo';
