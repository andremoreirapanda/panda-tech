-- Importação do prontuário (26/10/2026): evoluções importadas de outro sistema
-- viram registros do Diário marcados com origem = 'importacao' e uma impressão
-- da linha (importacao_chave), para não importar a mesma evolução duas vezes.
-- Seguro rodar mais de uma vez.
-- Rodar no SQL Editor do Supabase (produção) ou com `python migrar_importacao_prontuario.py`.
ALTER TABLE diarios_terapeuticos ADD COLUMN IF NOT EXISTS origem TEXT;
ALTER TABLE diarios_terapeuticos ADD COLUMN IF NOT EXISTS importacao_chave TEXT;
CREATE INDEX IF NOT EXISTS idx_diario_importacao_chave ON diarios_terapeuticos(paciente_id, importacao_chave);
