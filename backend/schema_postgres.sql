-- ============================================================================
-- ENCANTO EM CASA — Plataforma de Desenvolvimento Infantil
-- Schema do banco de dados (PostgreSQL / Supabase)
--
-- Convertido a partir de schema.sql (SQLite) para o piloto com clínica e
-- clientes reais. Principais diferenças em relação ao original SQLite:
--   - INTEGER PRIMARY KEY AUTOINCREMENT  -> SERIAL / GENERATED... (identidade)
--   - DEFAULT (date('now')) / (datetime('now')) -> expressão equivalente em
--     Postgres, produzindo o MESMO formato de texto ('YYYY-MM-DD' /
--     'YYYY-MM-DD HH24:MI:SS', em UTC) que o app já espera ao fazer
--     `datetime.strptime(...)` no lado Python.
--   - 3 colunas que referenciavam uma tabela ainda não criada (SQLite permite,
--     Postgres não) tiveram a FK movida para um ALTER TABLE no fim do arquivo:
--     tokens_redefinicao_senha.usuario_id, atividades.exercicio_id,
--     diarios_terapeuticos.consulta_id.
--   - Tipos (INTEGER para flags booleanas/dados, TEXT para tudo mais) foram
--     mantidos IGUAIS ao SQLite de propósito — o código Python em db.py/
--     blueprints/*.py já lida com 0/1 e strings de data, então manter os
--     mesmos tipos evita ter que reescrever toda a camada de aplicação.
--
-- Uso: psql "$DATABASE_URL" -f schema_postgres.sql
--      (ou rode via migrar_postgres.py, que também popula os dados mínimos)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- CORE DA PLATAFORMA (Documento 07, seção 2)
-- Autenticação, Organizações, Permissões, Auditoria, Notificações
-- ----------------------------------------------------------------------------

CREATE TABLE organizacoes (
    id              SERIAL PRIMARY KEY,
    nome            TEXT NOT NULL,
    cor_primaria    TEXT DEFAULT '#5B4FE9',
    cor_secundaria  TEXT DEFAULT '#FFB84D',
    logo_emoji      TEXT DEFAULT '🌟',
    logo_base64     TEXT,
    logo_nome       TEXT,
    plano           TEXT DEFAULT 'starter',
    ativo           INTEGER DEFAULT 1,
    cnpj                    TEXT,
    telefone                TEXT,
    endereco_cep            TEXT,
    endereco_logradouro     TEXT,
    endereco_numero         TEXT,
    endereco_bairro         TEXT,
    endereco_cidade         TEXT,
    endereco_uf             TEXT,
    status_comercial      TEXT DEFAULT 'trial' CHECK(status_comercial IN ('trial','ativa','inadimplente','cancelada')),
    data_inicio_trial     TEXT DEFAULT (to_char(CURRENT_DATE, 'YYYY-MM-DD')),
    dias_trial             INTEGER DEFAULT 14,
    assinatura_inicio      TEXT,
    contato_nome            TEXT,
    contato_email           TEXT,
    contato_telefone        TEXT,
    origem_lead              TEXT,
    observacoes_comerciais TEXT,
    nome_ia                 TEXT DEFAULT 'Lumi',
    nome_moeda_gamificacao TEXT DEFAULT 'XP',
    nome_medalha_generico  TEXT DEFAULT 'Medalha',
    especialidades_json     TEXT DEFAULT '[]',
    onboarding_concluido    INTEGER DEFAULT 0,
    onboarding_concluido_em TEXT,
    agenda_permissao_total_padrao INTEGER DEFAULT 0,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE modulos_clinica (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    modulo_codigo   TEXT NOT NULL,
    habilitado      INTEGER DEFAULT 1,
    UNIQUE(organizacao_id, modulo_codigo)
);

CREATE TABLE planos (
    id                      SERIAL PRIMARY KEY,
    codigo                  TEXT UNIQUE NOT NULL,
    nome                    TEXT NOT NULL,
    preco_mensal_centavos   INTEGER NOT NULL,
    limite_pacientes        INTEGER,
    limite_profissionais    INTEGER,
    recursos_json            TEXT,
    cor                       TEXT DEFAULT '#5B4FE9',
    ordem                    INTEGER DEFAULT 1,
    ativo                    INTEGER DEFAULT 1
);

CREATE TABLE usuarios (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER REFERENCES organizacoes(id),
    nome            TEXT NOT NULL,
    email           TEXT NOT NULL,
    senha_hash      TEXT NOT NULL,
    senha_salt      TEXT NOT NULL,
    papel           TEXT NOT NULL CHECK(papel IN ('admin_master','gestor','profissional','responsavel')),
    especialidade   TEXT,
    telefone        TEXT,
    avatar_emoji    TEXT DEFAULT '🙂',
    avatar_base64   TEXT,
    avatar_nome     TEXT,
    ativo           INTEGER DEFAULT 1,
    cor_agenda                TEXT DEFAULT '#5B4FE9',
    agenda_permissao_total    INTEGER DEFAULT 0,
    tipo_registro              TEXT,
    numero_registro            TEXT,
    financeiro_habilitado_override INTEGER DEFAULT NULL,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')),
    UNIQUE(organizacao_id, email)
);

-- (movida para o fim do arquivo, depois que `usuarios` já existe)
CREATE TABLE tokens_redefinicao_senha (
    id              SERIAL PRIMARY KEY,
    usuario_id      INTEGER NOT NULL,
    token           TEXT NOT NULL UNIQUE,
    tipo            TEXT DEFAULT 'redefinicao' CHECK(tipo IN ('redefinicao','convite')),
    expira_em       TEXT NOT NULL,
    usado           INTEGER DEFAULT 0,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE auditoria (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER,
    usuario_id      INTEGER,
    acao            TEXT NOT NULL,
    entidade        TEXT NOT NULL,
    entidade_id     INTEGER,
    detalhes        TEXT,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE notificacoes (
    id              SERIAL PRIMARY KEY,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    titulo          TEXT NOT NULL,
    mensagem        TEXT NOT NULL,
    tipo            TEXT DEFAULT 'info',
    lida            INTEGER DEFAULT 0,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE eventos (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER,
    tipo            TEXT NOT NULL,
    entidade        TEXT NOT NULL,
    entidade_id     INTEGER,
    paciente_id     INTEGER,
    payload_json    TEXT,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 1 — PESSOAS (Documento 09 / Módulo 01)
-- ----------------------------------------------------------------------------

CREATE TABLE pacientes (
    id                  SERIAL PRIMARY KEY,
    organizacao_id      INTEGER NOT NULL REFERENCES organizacoes(id),
    nome                TEXT NOT NULL,
    data_nascimento     TEXT NOT NULL,
    avatar_mascote      TEXT DEFAULT '🐻',
    foto_base64         TEXT,
    foto_nome           TEXT,
    genero              TEXT,
    ativo               INTEGER DEFAULT 1,
    criado_em           TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE fichas_clinicas (
    id                      SERIAL PRIMARY KEY,
    paciente_id             INTEGER NOT NULL UNIQUE REFERENCES pacientes(id),
    diagnostico             TEXT,
    alergias                TEXT,
    medicamentos_em_uso     TEXT,
    profissionais_externos  TEXT,
    observacoes             TEXT,
    atualizado_por          INTEGER REFERENCES usuarios(id),
    atualizado_em           TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE responsaveis_pacientes (
    id              SERIAL PRIMARY KEY,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    parentesco      TEXT DEFAULT 'Responsável',
    UNIQUE(usuario_id, paciente_id)
);

CREATE TABLE profissionais_pacientes (
    id              SERIAL PRIMARY KEY,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    principal       INTEGER DEFAULT 0,
    UNIQUE(usuario_id, paciente_id)
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 2 — JORNADA TERAPÊUTICA (Documento 09 / Módulo 02)
-- ----------------------------------------------------------------------------

CREATE TABLE jornadas (
    id                  SERIAL PRIMARY KEY,
    paciente_id         INTEGER NOT NULL REFERENCES pacientes(id),
    objetivo_principal  TEXT NOT NULL,
    status              TEXT DEFAULT 'ativa' CHECK(status IN ('ativa','encerrada')),
    criado_em           TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE planos_terapeuticos (
    id              SERIAL PRIMARY KEY,
    jornada_id      INTEGER NOT NULL REFERENCES jornadas(id),
    profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
    titulo          TEXT NOT NULL,
    data_inicio     TEXT NOT NULL,
    data_fim        TEXT,
    status          TEXT DEFAULT 'ativo' CHECK(status IN ('ativo','encerrado')),
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE objetivos_terapeuticos (
    id              SERIAL PRIMARY KEY,
    plano_id        INTEGER NOT NULL REFERENCES planos_terapeuticos(id),
    descricao       TEXT NOT NULL,
    status          TEXT DEFAULT 'em_andamento' CHECK(status IN ('em_andamento','alcancado')),
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE missoes (
    id              SERIAL PRIMARY KEY,
    plano_id        INTEGER NOT NULL REFERENCES planos_terapeuticos(id),
    objetivo_id     INTEGER REFERENCES objetivos_terapeuticos(id),
    titulo          TEXT NOT NULL,
    descricao       TEXT,
    prazo           TEXT,
    status          TEXT DEFAULT 'pendente' CHECK(status IN ('rascunho','pendente','iniciada','concluida','atrasada')),
    recompensa_xp   INTEGER DEFAULT 10,
    tempo_estimado_min INTEGER DEFAULT 10,
    tipo            TEXT DEFAULT 'diaria' CHECK(tipo IN ('diaria','semanal')),
    publicada_em    TEXT,
    iniciada_em     TEXT,
    concluida_em    TEXT,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 3 — BIBLIOTECA TERAPÊUTICA (Documento 09 / Módulo 03)
-- Criada ANTES de `atividades` (que referencia `exercicios`) — no SQLite
-- original essa tabela vinha depois, mas o Postgres exige a ordem certa.
-- ----------------------------------------------------------------------------

CREATE TABLE categorias_exercicio (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    nome            TEXT NOT NULL,
    icone_emoji     TEXT DEFAULT '📘'
);

CREATE TABLE exercicios (
    id                  SERIAL PRIMARY KEY,
    organizacao_id      INTEGER REFERENCES organizacoes(id),
    categoria_id        INTEGER REFERENCES categorias_exercicio(id),
    titulo              TEXT NOT NULL,
    descricao           TEXT,
    tipo                TEXT DEFAULT 'atividade' CHECK(tipo IN ('video','pdf','imagem','jogo','link','atividade')),
    conteudo_url        TEXT,
    arquivo_nome         TEXT,
    arquivo_base64       TEXT,
    arquivo_tamanho_bytes INTEGER,
    faixa_etaria_min    INTEGER DEFAULT 2,
    faixa_etaria_max    INTEGER DEFAULT 12,
    dificuldade         TEXT DEFAULT 'facil' CHECK(dificuldade IN ('facil','medio','dificil')),
    especialidade       TEXT,
    tags                TEXT,
    favoritos_count     INTEGER DEFAULT 0,
    ativo               INTEGER DEFAULT 1,
    criado_em           TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

-- Atividade = exercício vinculado a uma missão
CREATE TABLE atividades (
    id              SERIAL PRIMARY KEY,
    missao_id       INTEGER NOT NULL REFERENCES missoes(id),
    exercicio_id    INTEGER NOT NULL REFERENCES exercicios(id),
    ordem           INTEGER DEFAULT 1,
    concluida       INTEGER DEFAULT 0
);

CREATE TABLE missao_dias_concluidos (
    id              SERIAL PRIMARY KEY,
    missao_id       INTEGER NOT NULL REFERENCES missoes(id),
    data            TEXT NOT NULL,
    concluido_em    TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')),
    UNIQUE(missao_id, data)
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 5 — AGENDA (Documento 09 / Módulo 05)
-- Criada ANTES do Diário Terapêutico (que referencia `consultas`) — mesma
-- razão da Biblioteca acima.
-- ----------------------------------------------------------------------------

CREATE TABLE disponibilidade_profissional (
    id              SERIAL PRIMARY KEY,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    dia_semana      INTEGER NOT NULL CHECK(dia_semana BETWEEN 0 AND 6),
    ausente         INTEGER DEFAULT 0,
    hora_inicio     TEXT DEFAULT '08:00',
    hora_fim        TEXT DEFAULT '18:00',
    UNIQUE(usuario_id, dia_semana)
);

CREATE TABLE consultas (
    id              SERIAL PRIMARY KEY,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
    data_hora       TEXT NOT NULL,
    duracao_min     INTEGER DEFAULT 50,
    status          TEXT DEFAULT 'agendada' CHECK(status IN ('agendada','confirmada','realizada','cancelada','faltou')),
    observacoes     TEXT,
    serie_recorrencia_id INTEGER,
    google_event_id     TEXT,
    google_sincronizado_em TEXT,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

-- ============================================================================
-- MÓDULO 07 — DIÁRIO TERAPÊUTICO
-- ============================================================================
CREATE TABLE diarios_terapeuticos (
    id                  SERIAL PRIMARY KEY,
    jornada_id          INTEGER NOT NULL REFERENCES jornadas(id),
    profissional_id     INTEGER NOT NULL REFERENCES usuarios(id),
    consulta_id         INTEGER REFERENCES consultas(id),
    data_atendimento    TEXT NOT NULL DEFAULT (to_char(CURRENT_DATE, 'YYYY-MM-DD')),
    evolucao_clinica    TEXT NOT NULL,
    pontos_positivos_json TEXT DEFAULT '[]',
    pontos_atencao_json    TEXT DEFAULT '[]',
    objetivo_semana        TEXT,
    mensagem_familia       TEXT,
    compartilhado_familia  INTEGER DEFAULT 1,
    criado_em               TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE diario_anexos (
    id                  SERIAL PRIMARY KEY,
    diario_id           INTEGER NOT NULL REFERENCES diarios_terapeuticos(id),
    tipo                TEXT NOT NULL CHECK(tipo IN ('foto','audio','video')),
    nome_arquivo        TEXT,
    conteudo_base64     TEXT NOT NULL,
    tamanho_bytes        INTEGER,
    criado_em             TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE marcos_terapeuticos (
    id              SERIAL PRIMARY KEY,
    jornada_id      INTEGER NOT NULL REFERENCES jornadas(id),
    titulo          TEXT NOT NULL,
    descricao       TEXT,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE feedbacks_familia (
    id              SERIAL PRIMARY KEY,
    missao_id       INTEGER NOT NULL REFERENCES missoes(id),
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    texto           TEXT,
    humor            TEXT,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 4 — COMUNICAÇÃO (Documento 09 / Módulo 04)
-- ----------------------------------------------------------------------------

CREATE TABLE conversas (
    id              SERIAL PRIMARY KEY,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE mensagens (
    id              SERIAL PRIMARY KEY,
    conversa_id     INTEGER NOT NULL REFERENCES conversas(id),
    autor_id        INTEGER NOT NULL REFERENCES usuarios(id),
    tipo            TEXT DEFAULT 'texto' CHECK(tipo IN ('texto','imagem','audio','video','sistema')),
    conteudo        TEXT NOT NULL,
    anexo_nome        TEXT,
    anexo_base64      TEXT,
    anexo_tamanho_bytes INTEGER,
    reacao          TEXT,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE avisos (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    autor_id        INTEGER NOT NULL REFERENCES usuarios(id),
    titulo          TEXT NOT NULL,
    conteudo        TEXT NOT NULL,
    publico         TEXT DEFAULT 'todos' CHECK(publico IN ('todos','equipe','familias')),
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 6 — GAMIFICAÇÃO (Documento 09 / Módulo 06)
-- ----------------------------------------------------------------------------

CREATE TABLE gamificacao_paciente (
    paciente_id     INTEGER PRIMARY KEY REFERENCES pacientes(id),
    xp_total        INTEGER DEFAULT 0,
    nivel           INTEGER DEFAULT 1,
    estrelas        INTEGER DEFAULT 0,
    sequencia_dias  INTEGER DEFAULT 0,
    ultima_atividade_em TEXT,
    mascote_estagio INTEGER DEFAULT 1
);

CREATE TABLE medalhas (
    id              SERIAL PRIMARY KEY,
    nome            TEXT NOT NULL,
    descricao       TEXT,
    icone_emoji     TEXT DEFAULT '🏅',
    criterio        TEXT
);

CREATE TABLE medalhas_paciente (
    id              SERIAL PRIMARY KEY,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    medalha_id      INTEGER NOT NULL REFERENCES medalhas(id),
    conquistado_em  TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')),
    UNIQUE(paciente_id, medalha_id)
);

CREATE TABLE recompensas_bau (
    id              SERIAL PRIMARY KEY,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    nome            TEXT NOT NULL,
    icone_emoji     TEXT DEFAULT '🎁',
    desbloqueado    INTEGER DEFAULT 0,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 7 — FINANCEIRO (Documento 09 / Módulo 07)
-- ----------------------------------------------------------------------------

CREATE TABLE cobrancas (
    id              SERIAL PRIMARY KEY,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    descricao       TEXT NOT NULL,
    valor_centavos  INTEGER NOT NULL,
    vencimento      TEXT NOT NULL,
    status          TEXT DEFAULT 'pendente' CHECK(status IN ('pendente','pago','vencido')),
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')),
    mp_payment_id       TEXT,
    pix_qr_code          TEXT,
    pix_qr_code_base64   TEXT,
    pix_copia_cola        TEXT
);

CREATE TABLE pagamentos (
    id              SERIAL PRIMARY KEY,
    cobranca_id     INTEGER NOT NULL REFERENCES cobrancas(id),
    valor_centavos  INTEGER NOT NULL,
    forma           TEXT DEFAULT 'pix' CHECK(forma IN ('pix','cartao','boleto','dinheiro','transferencia')),
    pago_em         TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 10 — INTEGRAÇÕES
-- ----------------------------------------------------------------------------

CREATE TABLE integracoes (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    tipo            TEXT NOT NULL,
    status          TEXT DEFAULT 'desconectado' CHECK(status IN ('desconectado','conectado')),
    configuracao_json TEXT
);

-- Integrações da PRÓPRIA Panda Tech (não de uma clínica) — ex: o Mercado
-- Pago que cobra as clínicas pelo plano. Sem organizacao_id de propósito:
-- é uma configuração única da plataforma.
CREATE TABLE integracoes_plataforma (
    id                SERIAL PRIMARY KEY,
    tipo              TEXT NOT NULL UNIQUE,
    status            TEXT DEFAULT 'desconectado' CHECK(status IN ('desconectado','conectado')),
    configuracao_json TEXT
);

-- ----------------------------------------------------------------------------
-- Cobrança de PLANOS (Panda Tech cobrando as clínicas pela assinatura) —
-- diferente de `cobrancas`/`pagamentos` acima, que são a clínica cobrando
-- as famílias. Ver pagamento_plataforma_service.py.
-- ----------------------------------------------------------------------------

CREATE TABLE cobrancas_planos (
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

-- ----------------------------------------------------------------------------
-- Foreign keys "adiadas" — apontam para tabelas criadas depois delas no
-- SQLite original. Adicionadas aqui, agora que todas as tabelas existem.
-- ----------------------------------------------------------------------------
ALTER TABLE tokens_redefinicao_senha ADD CONSTRAINT fk_token_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id);

-- ----------------------------------------------------------------------------
-- Índices de performance para consultas mais comuns
-- ----------------------------------------------------------------------------
CREATE INDEX idx_usuarios_org ON usuarios(organizacao_id);
CREATE INDEX idx_pacientes_org ON pacientes(organizacao_id);
CREATE INDEX idx_resp_pac_usuario ON responsaveis_pacientes(usuario_id);
CREATE INDEX idx_resp_pac_paciente ON responsaveis_pacientes(paciente_id);
CREATE INDEX idx_prof_pac_usuario ON profissionais_pacientes(usuario_id);
CREATE INDEX idx_prof_pac_paciente ON profissionais_pacientes(paciente_id);
CREATE INDEX idx_jornadas_paciente ON jornadas(paciente_id);
CREATE INDEX idx_planos_jornada ON planos_terapeuticos(jornada_id);
CREATE INDEX idx_missoes_plano ON missoes(plano_id);
CREATE INDEX idx_diarios_jornada ON diarios_terapeuticos(jornada_id);
CREATE INDEX idx_diario_anexos_diario ON diario_anexos(diario_id);
CREATE INDEX idx_consultas_paciente ON consultas(paciente_id);
CREATE INDEX idx_consultas_profissional ON consultas(profissional_id);
CREATE INDEX idx_mensagens_conversa ON mensagens(conversa_id);
CREATE INDEX idx_eventos_org ON eventos(organizacao_id, criado_em);
CREATE INDEX idx_cobrancas_paciente ON cobrancas(paciente_id);
