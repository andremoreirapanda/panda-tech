-- Logo da plataforma (14/10/2026): uma linha só (id = 1), enviada pelo Admin
-- em Perfil da Plataforma. Seguro rodar mais de uma vez.
-- Rodar no SQL Editor do Supabase (produção) ou com `python migrar_logo_plataforma.py`.
CREATE TABLE IF NOT EXISTS plataforma_identidade (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    logo_base64   TEXT,
    atualizado_em TEXT
);
