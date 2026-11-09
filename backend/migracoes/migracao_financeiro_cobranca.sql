-- ----------------------------------------------------------------------------
-- Migração incremental — Financeiro das famílias, etapa 1 (07/11/2026)
--
-- Acordos de pagamento, itens de cobrança, status novos (rascunho, parcial,
-- cancelado), formas novas (cartão de crédito/débito), campos de baixa e
-- estorno, e a especialidade na consulta. Idempotente.
-- Rodar ANTES do `git pull` e de novo depois do restart (consultas criadas no meio ficam sem especialidade).
-- ----------------------------------------------------------------------------

ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS fin_cobrar_falta INTEGER NOT NULL DEFAULT 0;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS fin_repasse_falta INTEGER NOT NULL DEFAULT 0;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS fin_cobrar_desde TEXT;

ALTER TABLE consultas ADD COLUMN IF NOT EXISTS especialidade TEXT;

UPDATE consultas SET especialidade = COALESCE(
    (SELECT NULLIF(TRIM(u.especialidade), '') FROM usuarios u WHERE u.id = consultas.profissional_id), 'Geral')
WHERE especialidade IS NULL;

ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS organizacao_id INTEGER;
ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS acordo_id INTEGER;
ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS periodo_inicio TEXT;
ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS periodo_fim TEXT;
ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS desconto_centavos INTEGER NOT NULL DEFAULT 0;
ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS desconto_motivo TEXT;
ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS liberada_em TEXT;
ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS revisar INTEGER NOT NULL DEFAULT 0;
ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS revisar_motivo TEXT;
ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS mensalidade_preco_centavos INTEGER;

UPDATE cobrancas SET organizacao_id = (SELECT p.organizacao_id FROM pacientes p WHERE p.id = cobrancas.paciente_id)
WHERE organizacao_id IS NULL;

ALTER TABLE cobrancas DROP CONSTRAINT IF EXISTS cobrancas_status_check;
ALTER TABLE cobrancas ADD CONSTRAINT cobrancas_status_check
    CHECK (status IN ('rascunho','pendente','parcial','pago','vencido','cancelado'));

ALTER TABLE pagamentos ADD COLUMN IF NOT EXISTS recebido_por_usuario_id INTEGER;
ALTER TABLE pagamentos ADD COLUMN IF NOT EXISTS recebido_por_nome TEXT;
ALTER TABLE pagamentos ADD COLUMN IF NOT EXISTS mp_payment_id TEXT;
ALTER TABLE pagamentos ADD COLUMN IF NOT EXISTS estornado_em TEXT;
ALTER TABLE pagamentos ADD COLUMN IF NOT EXISTS estorno_motivo TEXT;
ALTER TABLE pagamentos ADD COLUMN IF NOT EXISTS estornado_por INTEGER;

ALTER TABLE pagamentos DROP CONSTRAINT IF EXISTS pagamentos_forma_check;
ALTER TABLE pagamentos ADD CONSTRAINT pagamentos_forma_check
    CHECK (forma IN ('pix','cartao','cartao_credito','cartao_debito','boleto','dinheiro','transferencia'));

CREATE TABLE IF NOT EXISTS acordos_pagamento (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    especialidade   TEXT NOT NULL,
    tipo            TEXT NOT NULL CHECK(tipo IN ('avulsa','mensalidade','pacote')),
    ciclo           TEXT CHECK(ciclo IN ('consulta','quinzenal','mensal')),
    vence_dias      INTEGER DEFAULT 5,
    valor_centavos  INTEGER,
    dia_vencimento  INTEGER,
    sessoes_total   INTEGER,
    parcelas        INTEGER,
    primeiro_vencimento TEXT,
    inicio          TEXT NOT NULL,
    fim             TEXT,
    status          TEXT NOT NULL DEFAULT 'ativo' CHECK(status IN ('ativo','encerrado')),
    criado_por      INTEGER,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')),
    encerrado_em    TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_acordo_ativo_esp ON acordos_pagamento(paciente_id, LOWER(TRIM(especialidade))) WHERE status = 'ativo';

CREATE TABLE IF NOT EXISTS cobranca_itens (
    id              SERIAL PRIMARY KEY,
    cobranca_id     INTEGER NOT NULL REFERENCES cobrancas(id),
    consulta_id     INTEGER NOT NULL REFERENCES consultas(id),
    data_hora       TEXT,
    procedimento_nome TEXT,
    valor_centavos  INTEGER NOT NULL,
    UNIQUE(consulta_id)
);

CREATE TABLE IF NOT EXISTS consulta_decisao_cobranca (
    consulta_id     INTEGER PRIMARY KEY REFERENCES consultas(id),
    decisao         TEXT NOT NULL CHECK(decisao IN ('nao_cobrar','valor')),
    valor_centavos  INTEGER,
    motivo          TEXT,
    decidido_por    INTEGER,
    decidido_em     TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS acordo_pacote_consumo (
    consulta_id     INTEGER PRIMARY KEY REFERENCES consultas(id),
    acordo_id       INTEGER NOT NULL REFERENCES acordos_pagamento(id),
    numero          INTEGER NOT NULL
);

ALTER TABLE cobranca_itens ADD COLUMN IF NOT EXISTS status_origem TEXT;
ALTER TABLE acordo_pacote_consumo ADD COLUMN IF NOT EXISTS status_origem TEXT;

UPDATE cobranca_itens SET status_origem = (SELECT c.status FROM consultas c WHERE c.id = cobranca_itens.consulta_id)
WHERE status_origem IS NULL;
UPDATE acordo_pacote_consumo SET status_origem = (SELECT c.status FROM consultas c WHERE c.id = acordo_pacote_consumo.consulta_id)
WHERE status_origem IS NULL;

CREATE TABLE IF NOT EXISTS consulta_acordo_incluida (
    consulta_id     INTEGER PRIMARY KEY REFERENCES consultas(id),
    acordo_id       INTEGER NOT NULL REFERENCES acordos_pagamento(id),
    incluida        INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_cobrancas_org ON cobrancas(organizacao_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cobranca_mensalidade_mes ON cobrancas(acordo_id, periodo_inicio) WHERE tipo = 'mensalidade';
