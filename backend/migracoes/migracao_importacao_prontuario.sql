-- Importação do prontuário (26/10/2026): evoluções importadas de outro sistema
-- viram registros do Diário marcados com origem = 'importacao' e uma impressão
-- da linha (importacao_chave), para não importar a mesma evolução duas vezes.
-- A ficha ganha "Observações da equipe" (observacoes_equipe), que a família não vê.
-- Seguro rodar mais de uma vez.
-- Rodar no SQL Editor do Supabase (produção) ou com `python migrar_importacao_prontuario.py`.
ALTER TABLE diarios_terapeuticos ADD COLUMN IF NOT EXISTS origem TEXT;
ALTER TABLE diarios_terapeuticos ADD COLUMN IF NOT EXISTS importacao_chave TEXT;
ALTER TABLE fichas_clinicas ADD COLUMN IF NOT EXISTS observacoes_equipe TEXT;
CREATE INDEX IF NOT EXISTS idx_diario_importacao_chave ON diarios_terapeuticos(paciente_id, importacao_chave);
