-- ============================================================================
-- ENCANTO EM CASA — Plataforma de Desenvolvimento Infantil
-- Schema do banco de dados (SQLite)
--
-- Organizado por Domínio de Negócio, seguindo o Documento 08 (Arquitetura da
-- Informação) e o Documento 09 (Domain Map). Cada tabela pertence a UM único
-- domínio (princípio "uma informação, um dono").
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- CORE DA PLATAFORMA (Documento 07, seção 2)
-- Autenticação, Organizações, Permissões, Auditoria, Notificações
-- ----------------------------------------------------------------------------

CREATE TABLE organizacoes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT NOT NULL,
    cor_primaria    TEXT DEFAULT '#5B4FE9',
    cor_secundaria  TEXT DEFAULT '#FFB84D',
    logo_emoji      TEXT DEFAULT '🌟',              -- usado como fallback se nenhuma imagem for enviada
    logo_base64     TEXT,                            -- logo real da clínica, upload (mesmo padrão do Diário/Biblioteca)
    logo_nome       TEXT,
    plano           TEXT DEFAULT 'starter',           -- referencia planos.codigo
    ativo           INTEGER DEFAULT 1,
    -- Dados institucionais da clínica (Doc 31/32)
    cnpj                    TEXT,
    telefone                TEXT,                       -- telefone principal da clínica (distinto do contato comercial)
    endereco_cep            TEXT,
    endereco_logradouro     TEXT,
    endereco_numero         TEXT,
    endereco_bairro         TEXT,
    endereco_cidade         TEXT,
    endereco_uf             TEXT,
    -- Dados comerciais (Módulo 11 - Administração / comercialização da plataforma)
    status_comercial      TEXT DEFAULT 'trial' CHECK(status_comercial IN ('trial','ativa','inadimplente','cancelada')),
    data_inicio_trial     TEXT DEFAULT (date('now')),
    dias_trial             INTEGER DEFAULT 14,
    assinatura_inicio      TEXT,                       -- quando virou cliente pagante
    contato_nome            TEXT,                       -- pessoa do time comercial responsável / decisor na clínica
    contato_email           TEXT,
    contato_telefone        TEXT,
    origem_lead              TEXT,                       -- indicação | inbound | outbound | evento
    observacoes_comerciais TEXT,
    -- Personalização (White Label leve — Doc 018 / Doc 022)
    nome_ia                 TEXT DEFAULT 'Lumi',           -- nome do assistente de IA
    nome_moeda_gamificacao TEXT DEFAULT 'XP',              -- nome da "moeda" de gamificação
    nome_medalha_generico  TEXT DEFAULT 'Medalha',         -- nome genérico usado para conquistas
    especialidades_json     TEXT DEFAULT '[]',              -- área de atuação da clínica (lista JSON de strings)
    -- Onboarding guiado (Doc 31A/32/33) — TTFV (Time To First Value)
    onboarding_concluido    INTEGER DEFAULT 0,
    onboarding_concluido_em TEXT,
    -- Permissão de agenda "padrão da clínica" (insight do usuário): quando
    -- ligado, TODO profissional (os já cadastrados e os próximos) ganha
    -- `agenda_permissao_total` de uma vez, sem o gestor precisar abrir o
    -- cadastro de cada um individualmente — ver PUT
    -- /api/pessoas/equipe/agenda-permissao-total-padrao. A caixinha
    -- individual no cadastro de cada profissional continua existindo, para
    -- abrir uma exceção pontual mesmo com o padrão desligado.
    agenda_permissao_total_padrao INTEGER DEFAULT 0,
    criado_em       TEXT DEFAULT (datetime('now'))
);

-- Módulos opcionais habilitados por clínica (Feature Flags — Doc 22A, camada "Clínica")
-- Módulos obrigatórios (jornada, biblioteca, comunicação, diário, gamificação, agenda)
-- não aparecem aqui — estão sempre ativos. Só os OPCIONAIS têm linha aqui.
CREATE TABLE modulos_clinica (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    modulo_codigo   TEXT NOT NULL,        -- financeiro | ia | analytics_avancado | integracoes | white_label
    habilitado      INTEGER DEFAULT 1,
    UNIQUE(organizacao_id, modulo_codigo)
);

-- Redefinição de senha com token de uso único (Doc 35/36) — também reaproveitada
-- para o convite de ativação de conta (mesma mecânica: "defina sua senha").
CREATE TABLE tokens_redefinicao_senha (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    token           TEXT NOT NULL UNIQUE,
    tipo            TEXT DEFAULT 'redefinicao' CHECK(tipo IN ('redefinicao','convite')),
    expira_em       TEXT NOT NULL,
    usado           INTEGER DEFAULT 0,
    criado_em       TEXT DEFAULT (datetime('now'))
);

-- Planos comerciais (preço, limites, recursos) — editável pelo Admin do SaaS
CREATE TABLE planos (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo                  TEXT UNIQUE NOT NULL,       -- starter | pro | enterprise
    nome                    TEXT NOT NULL,
    preco_mensal_centavos   INTEGER NOT NULL,
    limite_pacientes        INTEGER,                     -- NULL = ilimitado
    limite_profissionais    INTEGER,                     -- NULL = ilimitado
    recursos_json            TEXT,                        -- lista JSON de strings (bullets do plano)
    cor                       TEXT DEFAULT '#5B4FE9',
    ordem                    INTEGER DEFAULT 1,
    ativo                    INTEGER DEFAULT 1
);

-- Usuário = identidade autenticada. Um usuário pode ter um papel entre:
-- admin_master | gestor | profissional | responsavel
-- (Documento 08: "Uma mesma pessoa pode exercer mais de um papel")
CREATE TABLE usuarios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id  INTEGER REFERENCES organizacoes(id),  -- NULL para admin_master (SaaS)
    nome            TEXT NOT NULL,
    email           TEXT NOT NULL,
    senha_hash      TEXT NOT NULL,
    senha_salt      TEXT NOT NULL,
    papel           TEXT NOT NULL CHECK(papel IN ('admin_master','gestor','profissional','responsavel')),
    especialidade   TEXT,                               -- só para profissional (fono, TO, psico, psicopedagogia...)
    telefone        TEXT,
    avatar_emoji    TEXT DEFAULT '🙂',
    avatar_base64   TEXT,                            -- foto de perfil real (upload), opcional — emoji é o fallback
    avatar_nome     TEXT,
    ativo           INTEGER DEFAULT 1,
    -- Agenda (insight do usuário): cada profissional tem uma cor própria pra
    -- se destacar no calendário, e o gestor pode dar a um profissional
    -- específico o mesmo direito de gerenciar a agenda de QUALQUER paciente
    -- da clínica (por padrão, um profissional só mexe na agenda dos
    -- pacientes vinculados a ele).
    cor_agenda                TEXT DEFAULT '#5B4FE9',
    agenda_permissao_total    INTEGER DEFAULT 0,
    -- Registro profissional (ex: CRFa, CREFITO, CRP...) — só relevante pra papel='profissional'
    -- (ou papel='gestor' com atua_como_profissional=1, ver abaixo).
    tipo_registro              TEXT,
    numero_registro            TEXT,
    -- Insight do usuário: o gestor pode, opcionalmente, também atuar como
    -- profissional da própria clínica, usando a MESMA conta (mesmo
    -- login/senha) — sem precisar criar um segundo cadastro. Quando ligado,
    -- reaproveita especialidade/tipo_registro/numero_registro/cor_agenda
    -- (as mesmas colunas acima) e passa a poder ser atribuído em consultas
    -- e vinculado a pacientes como profissional (ver pessoas_bp.py e
    -- agenda_bp.py). Só faz sentido para papel='gestor'.
    atua_como_profissional     INTEGER NOT NULL DEFAULT 0,
    -- Feature Flags, camada "Usuário" (Doc 22A): permite ao gestor sobrescrever a
    -- visibilidade de um módulo para um responsável específico. NULL = herda da clínica.
    financeiro_habilitado_override INTEGER DEFAULT NULL,
    -- Correção de auditoria: carimbo da última troca de senha, embutido no JWT
    -- (claim "pwd_ts") e conferido a cada requisição — permite invalidar todos
    -- os tokens emitidos ANTES da troca assim que a senha muda (redefinição
    -- por token). Sem isso, um token roubado continuava válido por até 12h
    -- mesmo depois da vítima trocar a senha pra se proteger.
    senha_alterada_em TEXT DEFAULT NULL,
    criado_em       TEXT DEFAULT (datetime('now')),
    UNIQUE(organizacao_id, email)
);

-- Auditoria (Core) — "quem alterou, quando, o que mudou" (Doc 07)
CREATE TABLE auditoria (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id  INTEGER,
    usuario_id      INTEGER,
    acao            TEXT NOT NULL,
    entidade        TEXT NOT NULL,
    entidade_id     INTEGER,
    detalhes        TEXT,
    criado_em       TEXT DEFAULT (datetime('now'))
);

-- Notificações (Core) — central única (Doc 07)
CREATE TABLE notificacoes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    titulo          TEXT NOT NULL,
    mensagem        TEXT NOT NULL,
    tipo            TEXT DEFAULT 'info',                -- info | missao | conquista | diario | mensagem | financeiro | agenda
    -- `entidade`/`entidade_id` (agosto/2026): do que essa notificação trata —
    -- hoje 'paciente' (missao/conquista/diario/mensagem, todas escopadas a um
    -- paciente) ou 'assinatura' (financeiro) — usados pelo frontend pra levar
    -- o clique no sininho direto pra tela certa, em vez de só abrir o painel.
    entidade        TEXT,
    entidade_id     INTEGER,
    lida            INTEGER DEFAULT 0,
    criado_em       TEXT DEFAULT (datetime('now'))
);

-- Eventos (Core/transversal) — plataforma orientada a eventos (Doc 08: "Fluxo da Informação")
-- Toda ação relevante publica um evento aqui. Indicadores e IA leem daqui.
CREATE TABLE eventos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id  INTEGER,
    tipo            TEXT NOT NULL,                      -- ex: 'missao_concluida', 'pagamento_confirmado'
    entidade        TEXT NOT NULL,                      -- ex: 'missao', 'paciente'
    entidade_id     INTEGER,
    paciente_id     INTEGER,
    payload_json    TEXT,
    criado_em       TEXT DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 1 — PESSOAS (Documento 09 / Módulo 01)
-- Fonte oficial de identidade de pessoas e organizações.
-- ----------------------------------------------------------------------------

CREATE TABLE pacientes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id      INTEGER NOT NULL REFERENCES organizacoes(id),
    nome                TEXT NOT NULL,
    data_nascimento     TEXT NOT NULL,
    avatar_mascote      TEXT DEFAULT '🐻',
    foto_base64         TEXT,                        -- foto real da criança (upload), opcional — mascote é o fallback
    foto_nome           TEXT,
    genero              TEXT,
    ativo               INTEGER DEFAULT 1,
    criado_em           TEXT DEFAULT (datetime('now'))
);

-- Ficha clínica (Doc 34 — ClinicalProfile): diagnóstico, alergias, medicações
-- e profissionais externos, separados da identidade básica do paciente. Um
-- registro por paciente, criado sob demanda — NADA aqui é obrigatório;
-- a jornada terapêutica funciona normalmente sem esse preenchimento.
CREATE TABLE fichas_clinicas (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id             INTEGER NOT NULL UNIQUE REFERENCES pacientes(id),
    diagnostico             TEXT,
    alergias                TEXT,
    medicamentos_em_uso     TEXT,
    profissionais_externos  TEXT,     -- ex: pediatra, neuropediatra, outros especialistas fora da clínica
    observacoes             TEXT,
    atualizado_por          INTEGER REFERENCES usuarios(id),
    atualizado_em           TEXT DEFAULT (datetime('now'))
);

-- Vínculo N:N responsável <-> paciente (Doc 08: "um paciente pode ter vários responsáveis")
CREATE TABLE responsaveis_pacientes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),   -- papel = responsavel
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    parentesco      TEXT DEFAULT 'Responsável',
    UNIQUE(usuario_id, paciente_id)
);

-- Vínculo N:N profissional <-> paciente (Doc 08: "modelo interdisciplinar")
CREATE TABLE profissionais_pacientes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),   -- papel = profissional
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    principal       INTEGER DEFAULT 0,
    UNIQUE(usuario_id, paciente_id)
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 2 — JORNADA TERAPÊUTICA (Documento 09 / Módulo 02)
-- Entidade central do ecossistema (PD-009-001).
-- ----------------------------------------------------------------------------

CREATE TABLE jornadas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id         INTEGER NOT NULL REFERENCES pacientes(id),
    objetivo_principal  TEXT NOT NULL,
    status              TEXT DEFAULT 'ativa' CHECK(status IN ('ativa','encerrada')),
    criado_em           TEXT DEFAULT (datetime('now'))
);

-- Plano Terapêutico NÃO é a Jornada (Doc 08). Uma jornada tem vários planos ao longo do tempo.
CREATE TABLE planos_terapeuticos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    jornada_id      INTEGER NOT NULL REFERENCES jornadas(id),
    profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
    titulo          TEXT NOT NULL,                       -- ex: "Plano Março"
    data_inicio     TEXT NOT NULL,
    data_fim        TEXT,
    status          TEXT DEFAULT 'ativo' CHECK(status IN ('ativo','encerrado')),
    criado_em       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE objetivos_terapeuticos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plano_id        INTEGER NOT NULL REFERENCES planos_terapeuticos(id),
    descricao       TEXT NOT NULL,
    status          TEXT DEFAULT 'em_andamento' CHECK(status IN ('em_andamento','alcancado')),
    criado_em       TEXT DEFAULT (datetime('now'))
);

-- Missão — "o coração do aplicativo infantil" (Doc 08)
CREATE TABLE missoes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plano_id        INTEGER NOT NULL REFERENCES planos_terapeuticos(id),
    objetivo_id     INTEGER REFERENCES objetivos_terapeuticos(id),
    titulo          TEXT NOT NULL,
    descricao       TEXT,
    prazo           TEXT,
    -- Ciclo de vida (Doc 30/31, US-017/019): rascunho → pendente (publicada) →
    -- iniciada (US-021, activity_started) → concluida (US-022, activity_completed)
    status          TEXT DEFAULT 'pendente' CHECK(status IN ('rascunho','pendente','iniciada','concluida','atrasada')),
    recompensa_xp   INTEGER DEFAULT 10,
    tempo_estimado_min INTEGER DEFAULT 10,
    -- Diária vs Semanal (insight do usuário): a diária conclui de uma vez só
    -- (comportamento de sempre); a semanal precisa de 1 check por dia real,
    -- 7 dias seguidos — não dá pra marcar tudo de uma vez (ver
    -- missao_dias_concluidos e o endpoint /concluir-dia).
    tipo            TEXT DEFAULT 'diaria' CHECK(tipo IN ('diaria','semanal')),
    -- Quantidade de dias de check exigida para uma missão 'semanal' fechar
    -- (achado de UAT, 26/08/2026: o valor era fixo em 7 no código — virou
    -- configurável por missão. NULL/7 preserva o comportamento de sempre
    -- para missões já existentes). Não se aplica a missões 'diaria'.
    frequencia_dias INTEGER DEFAULT 7,
    publicada_em    TEXT,
    iniciada_em     TEXT,
    concluida_em    TEXT,
    criado_em       TEXT DEFAULT (datetime('now'))
);

-- Atividade = exercício vinculado a uma missão (Doc 013: "cada missão contém uma ou mais atividades")
CREATE TABLE atividades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    missao_id       INTEGER NOT NULL REFERENCES missoes(id),
    exercicio_id    INTEGER NOT NULL REFERENCES exercicios(id),
    ordem           INTEGER DEFAULT 1,
    concluida       INTEGER DEFAULT 0
);

-- Dias concluídos de uma missão SEMANAL — um check por dia real, não dá pra
-- marcar retroativo nem adiantar (o endpoint só aceita a data de hoje).
CREATE TABLE missao_dias_concluidos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    missao_id       INTEGER NOT NULL REFERENCES missoes(id),
    data            TEXT NOT NULL,     -- 'YYYY-MM-DD', sempre a data do servidor no momento do check
    concluido_em    TEXT DEFAULT (datetime('now')),
    UNIQUE(missao_id, data)
);

-- ============================================================================
-- MÓDULO 07 — DIÁRIO TERAPÊUTICO
-- "Registrar e compartilhar a evolução clínica da criança em linguagem
--  acessível para a família." Substitui o antigo registro simples de
--  'evolução' por um formato estruturado e compartilhável.
-- ============================================================================
CREATE TABLE diarios_terapeuticos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    jornada_id          INTEGER NOT NULL REFERENCES jornadas(id),
    profissional_id     INTEGER NOT NULL REFERENCES usuarios(id),
    consulta_id         INTEGER REFERENCES consultas(id),
    data_atendimento    TEXT NOT NULL DEFAULT (date('now')),
    evolucao_clinica    TEXT NOT NULL,              -- linguagem técnica, registro clínico
    pontos_positivos_json TEXT DEFAULT '[]',          -- lista JSON de strings
    pontos_atencao_json    TEXT DEFAULT '[]',          -- lista JSON de strings
    objetivo_semana        TEXT,
    mensagem_familia       TEXT,                        -- linguagem acessível, escrita para os pais lerem
    compartilhado_familia  INTEGER DEFAULT 1,           -- FR-010: compartilhado automaticamente por padrão
    criado_em               TEXT DEFAULT (datetime('now'))
);

-- Anexos opcionais do diário (foto, áudio ou vídeo curto da sessão)
CREATE TABLE diario_anexos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    diario_id           INTEGER NOT NULL REFERENCES diarios_terapeuticos(id),
    tipo                TEXT NOT NULL CHECK(tipo IN ('foto','audio','video')),
    nome_arquivo        TEXT,
    conteudo_base64     TEXT NOT NULL,               -- armazenado inline (adequado para anexos pequenos de demonstração)
    tamanho_bytes        INTEGER,
    criado_em             TEXT DEFAULT (datetime('now'))
);

-- Marcos / WOW moments (Documento 11)
CREATE TABLE marcos_terapeuticos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    jornada_id      INTEGER NOT NULL REFERENCES jornadas(id),
    titulo          TEXT NOT NULL,
    descricao       TEXT,
    criado_em       TEXT DEFAULT (datetime('now'))
);

-- Feedback da família sobre uma missão (Doc 013 D-02)
CREATE TABLE feedbacks_familia (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    missao_id       INTEGER NOT NULL REFERENCES missoes(id),
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    texto           TEXT,
    humor            TEXT,                                -- emoji de humor da criança na atividade
    criado_em       TEXT DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 3 — BIBLIOTECA TERAPÊUTICA (Documento 09 / Módulo 03)
-- ----------------------------------------------------------------------------

CREATE TABLE categorias_exercicio (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    nome            TEXT NOT NULL,
    icone_emoji     TEXT DEFAULT '📘'
);

CREATE TABLE exercicios (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    -- NULL = Biblioteca da Plataforma (conteúdo do SaaS, visível a todas as
    -- clínicas, só o Admin edita). Com valor = Biblioteca da Clínica (Doc 31A/32).
    organizacao_id      INTEGER REFERENCES organizacoes(id),
    categoria_id        INTEGER REFERENCES categorias_exercicio(id),
    titulo              TEXT NOT NULL,
    descricao           TEXT,
    tipo                TEXT DEFAULT 'atividade' CHECK(tipo IN ('video','pdf','imagem','jogo','link','atividade')),
    conteudo_url        TEXT,                              -- usado quando o conteúdo é um link externo
    arquivo_nome         TEXT,                              -- usado quando o conteúdo é um upload real
    arquivo_base64       TEXT,                              -- armazenado inline (adequado para arquivos pequenos de demonstração)
    arquivo_tamanho_bytes INTEGER,
    faixa_etaria_min    INTEGER DEFAULT 2,
    faixa_etaria_max    INTEGER DEFAULT 12,
    dificuldade         TEXT DEFAULT 'facil' CHECK(dificuldade IN ('facil','medio','dificil')),
    especialidade       TEXT,
    tags                TEXT,                             -- csv simples
    favoritos_count     INTEGER DEFAULT 0,
    ativo               INTEGER DEFAULT 1,
    criado_em           TEXT DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 4 — COMUNICAÇÃO (Documento 09 / Módulo 04)
-- ----------------------------------------------------------------------------

CREATE TABLE conversas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    criado_em       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE mensagens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversa_id     INTEGER NOT NULL REFERENCES conversas(id),
    autor_id        INTEGER NOT NULL REFERENCES usuarios(id),
    tipo            TEXT DEFAULT 'texto' CHECK(tipo IN ('texto','imagem','audio','video','sistema')),
    conteudo        TEXT NOT NULL,
    anexo_nome        TEXT,                              -- usado quando tipo = imagem/audio/video
    anexo_base64      TEXT,                              -- armazenado inline (mesmo padrão do Diário/Biblioteca)
    anexo_tamanho_bytes INTEGER,
    reacao          TEXT,
    criado_em       TEXT DEFAULT (datetime('now'))
);

-- Mural / avisos da clínica (Doc 10, Módulo 04)
CREATE TABLE avisos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    autor_id        INTEGER NOT NULL REFERENCES usuarios(id),
    titulo          TEXT NOT NULL,
    conteudo        TEXT NOT NULL,
    -- 'todos' = equipe e famílias | 'equipe' = só gestor/profissional | 'familias' = só responsáveis
    publico         TEXT DEFAULT 'todos' CHECK(publico IN ('todos','equipe','familias')),
    criado_em       TEXT DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 5 — AGENDA (Documento 09 / Módulo 05)
-- ----------------------------------------------------------------------------

-- Disponibilidade semanal do profissional (insight do usuário): cada
-- profissional define, por dia da semana, se está ausente e o horário de
-- atendimento. Usado pro gestor/família saberem os dias livres na Agenda.
CREATE TABLE disponibilidade_profissional (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    dia_semana      INTEGER NOT NULL CHECK(dia_semana BETWEEN 0 AND 6),  -- 0=domingo ... 6=sábado
    ausente         INTEGER DEFAULT 0,
    hora_inicio     TEXT DEFAULT '08:00',
    hora_fim        TEXT DEFAULT '18:00',
    UNIQUE(usuario_id, dia_semana)
);

CREATE TABLE consultas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
    data_hora       TEXT NOT NULL,
    duracao_min     INTEGER DEFAULT 50,
    status          TEXT DEFAULT 'agendada' CHECK(status IN ('agendada','confirmada','realizada','cancelada','faltou')),
    observacoes     TEXT,
    -- Agendamento recorrente (insight do usuário): consultas geradas juntas
    -- numa série compartilham esse valor — usa o id da primeira consulta da
    -- série. NULL = consulta avulsa, sem recorrência.
    serie_recorrencia_id INTEGER,
    -- Encaixe pra integração real com Google Calendar (Doc 26). Enquanto a
    -- integração de verdade não existe (precisa de OAuth + rede externa),
    -- esses campos ficam vazios; ver calendar_sync_service.py.
    google_event_id     TEXT,
    google_sincronizado_em TEXT,
    criado_em       TEXT DEFAULT (datetime('now'))
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
    mascote_estagio INTEGER DEFAULT 1                    -- mascote evolui com o nível
);

CREATE TABLE medalhas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT NOT NULL,
    descricao       TEXT,
    icone_emoji     TEXT DEFAULT '🏅',
    criterio        TEXT                                  -- descrição textual do critério
);

CREATE TABLE medalhas_paciente (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    medalha_id      INTEGER NOT NULL REFERENCES medalhas(id),
    conquistado_em  TEXT DEFAULT (datetime('now')),
    UNIQUE(paciente_id, medalha_id)
);

CREATE TABLE recompensas_bau (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    nome            TEXT NOT NULL,
    icone_emoji     TEXT DEFAULT '🎁',
    desbloqueado    INTEGER DEFAULT 0,
    criado_em       TEXT DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 7 — FINANCEIRO (Documento 09 / Módulo 07)
-- Posicionamento: facilita, não substitui o ERP (Doc 10 / Doc 013 BR-013-005).
-- ----------------------------------------------------------------------------

CREATE TABLE cobrancas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    descricao       TEXT NOT NULL,
    valor_centavos  INTEGER NOT NULL,
    vencimento      TEXT NOT NULL,
    status          TEXT DEFAULT 'pendente' CHECK(status IN ('pendente','pago','vencido')),
    criado_em       TEXT DEFAULT (datetime('now')),
    -- Integração real com o Mercado Pago (ver pagamento_service.py) — NULL
    -- enquanto a cobrança não tiver um PIX gerado pelo app.
    mp_payment_id       TEXT,
    pix_qr_code          TEXT,
    pix_qr_code_base64   TEXT,
    pix_copia_cola        TEXT
);

CREATE TABLE pagamentos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cobranca_id     INTEGER NOT NULL REFERENCES cobrancas(id),
    valor_centavos  INTEGER NOT NULL,
    -- 'dinheiro'/'transferencia' adicionados nesta rodada — usados na
    -- confirmação manual (fora do app) feita pelo Gestor/Admin, ver
    -- financeiro_bp.py::registrar_pagamento().
    forma           TEXT DEFAULT 'pix' CHECK(forma IN ('pix','cartao','boleto','dinheiro','transferencia')),
    pago_em         TEXT DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- DOMÍNIO 8 — INDICADORES: não possui tabelas próprias.
-- "Não cria dados. Apenas interpreta eventos." (Documento 09)
-- As queries de indicadores são calculadas sobre as tabelas acima + eventos.
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- DOMÍNIO 10 — INTEGRAÇÕES (stub simbólico — Fase 2 no roadmap)
-- ----------------------------------------------------------------------------

CREATE TABLE integracoes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    tipo            TEXT NOT NULL,                        -- erp | whatsapp | google_calendar | pagamento
    status          TEXT DEFAULT 'desconectado' CHECK(status IN ('desconectado','conectado')),
    configuracao_json TEXT
);

-- Integrações da PRÓPRIA Panda Tech (não de uma clínica) — ex: o Mercado
-- Pago que cobra as clínicas pelo plano. Sem organizacao_id de propósito:
-- é uma configuração única da plataforma.
CREATE TABLE integracoes_plataforma (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
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
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id     INTEGER NOT NULL REFERENCES organizacoes(id),
    plano_codigo       TEXT NOT NULL,
    valor_centavos     INTEGER NOT NULL,
    status             TEXT DEFAULT 'pendente' CHECK(status IN ('pendente','pago','cancelada')),
    forma_confirmacao  TEXT CHECK(forma_confirmacao IN ('mercadopago_pix','mercadopago_cartao','manual')),
    mp_payment_id      TEXT,
    pix_qr_code        TEXT,
    pix_qr_code_base64 TEXT,
    pix_copia_cola     TEXT,
    criado_em          TEXT DEFAULT (datetime('now')),
    pago_em            TEXT,
    -- Texto livre opcional (ex: "Taxa de setup", "Ajuste retroativo") — só
    -- preenchido em cobranças avulsas criadas manualmente pelo Admin; nas
    -- cobranças mensais normais fica NULL e a listagem usa o nome do plano.
    -- Em banco já existente (produção), é adicionada por
    -- migrar_cobrancas_planos_avulsas.py em vez de nascer aqui.
    descricao          TEXT
);

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
