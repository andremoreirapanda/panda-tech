-- Migração (12/11/2026, Financeiro etapa 3): repasse aos profissionais.
-- Postgres / Supabase. Seguro rodar de novo.

ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS fin_repasse_base TEXT NOT NULL DEFAULT 'procedimento';

-- Financeiro etapa 3 (repasse aos profissionais, 12/11/2026)
CREATE TABLE IF NOT EXISTS regras_repasse (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
    procedimento_id INTEGER REFERENCES procedimentos(id),
    tipo_acordo     TEXT CHECK(tipo_acordo IN ('avulsa','mensalidade','pacote')),
    modo            TEXT NOT NULL CHECK(modo IN ('percentual','fixo')),
    percentual_centesimos INTEGER,
    valor_centavos  INTEGER,
    atualizado_em   TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')),
    atualizado_por  INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_regra_repasse_unica ON regras_repasse(profissional_id, COALESCE(procedimento_id, 0), COALESCE(tipo_acordo, ''));
CREATE INDEX IF NOT EXISTS idx_regras_repasse_org ON regras_repasse(organizacao_id, profissional_id);

CREATE TABLE IF NOT EXISTS repasses (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
    periodo_de      TEXT NOT NULL,
    periodo_ate     TEXT NOT NULL,
    total_sessoes_centavos INTEGER NOT NULL DEFAULT 0,
    total_profissional_centavos INTEGER NOT NULL DEFAULT 0,
    total_ajustes_centavos INTEGER NOT NULL DEFAULT 0,
    a_pagar_centavos INTEGER NOT NULL DEFAULT 0,
    quantidade      INTEGER NOT NULL DEFAULT 0,
    pago_em         TEXT,
    pago_por        INTEGER,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_repasses_org ON repasses(organizacao_id, profissional_id);

CREATE TABLE IF NOT EXISTS repasse_itens (
    id              SERIAL PRIMARY KEY,
    repasse_id      INTEGER NOT NULL REFERENCES repasses(id),
    consulta_id     INTEGER NOT NULL UNIQUE REFERENCES consultas(id),
    data_hora       TEXT,
    paciente_nome   TEXT,
    especialidade   TEXT,
    descricao       TEXT,
    sessao_numero   INTEGER,
    sessao_total    INTEGER,
    tipo_acordo     TEXT,
    base_centavos   INTEGER NOT NULL DEFAULT 0,
    regra_modo      TEXT,
    regra_percentual_centesimos INTEGER,
    regra_valor_centavos INTEGER,
    profissional_centavos INTEGER NOT NULL DEFAULT 0,
    clinica_centavos INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS repasse_ajustes (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
    repasse_id      INTEGER REFERENCES repasses(id),
    descricao       TEXT NOT NULL,
    valor_centavos  INTEGER NOT NULL,
    origem          TEXT NOT NULL CHECK(origem IN ('manual','estorno')),
    consulta_id     INTEGER,
    criado_por      INTEGER,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ajuste_estorno_consulta ON repasse_ajustes(consulta_id) WHERE origem = 'estorno';
CREATE INDEX IF NOT EXISTS idx_ajustes_abertos ON repasse_ajustes(organizacao_id, profissional_id) WHERE repasse_id IS NULL;
