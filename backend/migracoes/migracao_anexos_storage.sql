-- Anexos do Diário no Supabase Storage (25/11/2026): o arquivo fica no Storage e o banco guarda
-- só o caminho (storage_path) e o tipo (mime); conteudo_base64 passa a aceitar NULL.
-- Rodar ANTES de criar as variáveis SUPABASE_URL / SUPABASE_SERVICE_KEY no servidor.
-- O bucket privado é criado pelo próprio app na primeira vez. Seguro rodar de novo.
ALTER TABLE diario_anexos ALTER COLUMN conteudo_base64 DROP NOT NULL;
ALTER TABLE diario_anexos ADD COLUMN IF NOT EXISTS storage_path TEXT;
ALTER TABLE diario_anexos ADD COLUMN IF NOT EXISTS mime TEXT;
