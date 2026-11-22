-- Conciliação automática do repasse: origens novas dos ajustes ('status', 'recredito')
-- e fim do índice único por sessão (a deduplicação passa a ser feita pelo serviço).
-- Seguro rodar de novo.
ALTER TABLE repasse_ajustes DROP CONSTRAINT IF EXISTS repasse_ajustes_origem_check;
ALTER TABLE repasse_ajustes ADD CONSTRAINT repasse_ajustes_origem_check CHECK (origem IN ('manual','estorno','status','recredito'));
DROP INDEX IF EXISTS idx_ajuste_estorno_consulta;
CREATE INDEX IF NOT EXISTS idx_ajuste_consulta ON repasse_ajustes(consulta_id);
