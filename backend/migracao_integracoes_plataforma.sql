-- ----------------------------------------------------------------------------
-- Migração incremental — tabelas de Integrações da Plataforma + Cobrança de
-- Planos (Admin > Integrações, cadastro de clínica com PIX automático).
--
-- Rodar isoladamente (não é o schema_postgres.sql inteiro) porque o banco de
-- produção já tem as tabelas originais criadas — reaplicar o schema inteiro
-- erraria em "relation already exists" antes de chegar aqui. Usa
-- `CREATE TABLE IF NOT EXISTS` para poder ser executado mais de uma vez com
-- segurança (idempotente), igual ao padrão já usado no db-setup.yml.
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS integracoes_plataforma (
    id                SERIAL PRIMARY KEY,
    tipo              TEXT NOT NULL UNIQUE,
    status            TEXT DEFAULT 'desconectado' CHECK(status IN ('desconectado','conectado')),
    configuracao_json TEXT
);

CREATE TABLE IF NOT EXISTS cobrancas_planos (
    id                 SERIAL PRIMARY KEY,
    organizacao_id     INTEGER NOT NULL REFERENCES organizacoes(id),
    plano_codigo       TEXT NOT NULL,
    valor_centavos     INTEGER NOT NULL,
    status             TEXT DEFAULT 'pendente' CHECK(status IN ('pendente','pago','cancelada')),
    forma_confirmacao  TEXT CHECK(forma_confirmacao IN ('mercadopago_pix','manual')),
    mp_payment_id      TEXT,
    pix_qr_code        TEXT,
    pix_qr_code_base64 TEXT,
    pix_copia_cola     TEXT,
    criado_em          TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')),
    pago_em            TEXT
);
