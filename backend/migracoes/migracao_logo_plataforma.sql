-- Logo da plataforma (14/10/2026): uma linha só (id = 1), enviada pelo Admin
-- em Perfil da Plataforma. 15/10/2026: coluna do logo para o login (fundo roxo).
-- Seguro rodar mais de uma vez.
-- Rodar no SQL Editor do Supabase (produção) ou com `python migrar_logo_plataforma.py`.
CREATE TABLE IF NOT EXISTS plataforma_identidade (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    logo_base64       TEXT,
    logo_login_base64 TEXT,
    atualizado_em     TEXT
);
ALTER TABLE plataforma_identidade ADD COLUMN IF NOT EXISTS logo_login_base64 TEXT;
