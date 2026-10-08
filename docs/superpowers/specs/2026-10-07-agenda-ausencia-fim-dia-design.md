# Agenda: hora de fim livre, Ausência e visão Dia — design

Data: 07/10/2026. Parte 2 da comparação com a Clínica Ágil (a parte 1, menu
com a Agenda em primeiro, é o PR #38; a parte 3, Atender/Evoluir, terá spec
própria).

## Objetivo

Deixar a agenda do Panda Tech no nível do uso diário de uma clínica:

1. Toda consulta tem **início e fim** livres (hoje a duração é fixa em 50 min
   na tela).
2. O profissional pode ficar **ausente** (almoço, férias, curso) e ninguém
   consegue agendar por cima.
3. Uma **visão Dia**: um profissional (modo "Por Profissional") ou todos lado
   a lado (modo "Geral").

Fora do escopo: esticar a consulta pela borda na grade, status novos,
repetição personalizada de consultas, horário próprio por profissional,
Atender/Evoluir (parte 3).

## Decisões do usuário (07/10/2026)

| Pergunta | Decisão |
|---|---|
| Ausência bloqueia ou avisa? | **Bloqueia** — não dá para agendar por cima. |
| Quem lança ausência? | O próprio profissional (só as dele); gestor e secretária para qualquer profissional da clínica. |
| Visão Dia | **As duas**: "Por Profissional" → um profissional; "Geral" → todos lado a lado. |
| Fim padrão da consulta | **Duração padrão da clínica** (Configurações), começa em 50 min. |
| Formato da ausência | **Período + repetição**: data início/fim (fim vazio = sem fim), dia inteiro ou horário, dias da semana, motivo. |
| Série recorrente que cai numa ausência | Cria as demais e **avisa as datas puladas**. |
| Ausência lançada sobre consultas existentes | **Permite** e **lista** as consultas do período para remarcar/cancelar. |

## Dados

### Tabela nova `ausencias_profissional`

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | PK | |
| `organizacao_id` | FK `organizacoes` | clínica do profissional |
| `profissional_id` | FK `usuarios` | profissional ausente |
| `data_inicio` | TEXT `YYYY-MM-DD` | obrigatória |
| `data_fim` | TEXT `YYYY-MM-DD` ou NULL | NULL = sem fim; se preenchida, ≥ `data_inicio` |
| `dia_inteiro` | INTEGER 0/1 | 1 = o dia todo |
| `hora_inicio` / `hora_fim` | TEXT `HH:MM` ou NULL | obrigatórias se `dia_inteiro = 0`; início < fim |
| `dias_semana` | TEXT | dígitos de 0 (dom) a 6 (sáb), ex. `"12345"`; ao menos um dia |
| `motivo` | TEXT ou NULL | até 120 caracteres |
| `criado_por` | FK `usuarios` | quem lançou |
| `criado_em` | TEXT | padrão agora |

Índice em `(profissional_id, data_inicio)`. Entra em `schema.sql`,
`schema_postgres.sql`, `migracoes/migracao_ausencias_agenda.sql` (idempotente:
`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`) e
`migrar_ausencias_agenda.py`.

Uma ausência é **uma linha com a regra**; as ocorrências são calculadas na
hora (o almoço "seg a sex, sem fim" é uma linha só).

### Coluna nova `organizacoes.agenda_duracao_padrao`

INTEGER, padrão 50, válido de 5 a 240. Exposta no `/auth/me` (lista
`CAMPOS_ORG` de `auth_bp.py`/`identidade_service.py`) e editada em
`PUT /pessoas/organizacao`, junto com o horário da agenda.

### `consultas.duracao_min`

Já existe. Passa a ser **validada** em criar, criar recorrente e editar:
inteiro de 5 a 480 (hoje aceita qualquer valor). Sem `duracao_min` no corpo,
o padrão vira o `agenda_duracao_padrao` da clínica (não mais 50 fixo).

## Backend

### `ausencias_service.py` (novo, funções puras + consultas)

- `validar_ausencia(body)` → `(dados_normalizados, erro)`.
- `ausencia_cobre(ausencia, data, ini_min, fim_min)` → bool: a regra vale
  nesse dia (dentro do período e no dia da semana) e o intervalo
  `[ini_min, fim_min)` se sobrepõe ao horário dela (ou ela é dia inteiro).
  Uma consulta que **encosta** na ausência (termina 12:00, ausência começa
  12:00) não conflita.
- `conflito_ausencia(profissional_id, data_hora, duracao_min)` → a primeira
  ausência que bate, ou None. Consulta que atravessa a meia-noite é tratada
  só no dia de início (caso irreal na clínica).
- `ocorrencias(ausencias, data_ini, data_fim)` → lista de
  `{ausencia_id, data, dia_inteiro, hora_inicio, hora_fim, motivo, profissional_id}`
  para desenhar a grade.

### Rotas (`agenda_bp.py`)

- `GET /api/agenda/ausencias?inicio=YYYY-MM-DD&fim=YYYY-MM-DD` → ocorrências
  no intervalo (máx. 62 dias), das ausências que o usuário pode ver: gestor,
  secretária e profissional com `agenda_permissao_total` veem a clínica toda;
  profissional comum vê só as dele; responsável → 403. Cada item traz
  `pode_editar`.
- `POST /api/agenda/ausencias` → cria. Profissional comum: `profissional_id`
  é sempre ele mesmo (outro id → 403). Gestor/secretária: profissional ativo,
  não excluído, da mesma clínica (`_profissional_da_mesma_clinica`). Resposta
  201 com `id` e `consultas_no_periodo` (consultas não canceladas, de hoje em
  diante, que caem na regra: id, data_hora, paciente_nome).
- `PUT /api/agenda/ausencias/<id>` → edita a regra inteira (mesmas
  validações e mesma resposta com `consultas_no_periodo`).
- `DELETE /api/agenda/ausencias/<id>` → apaga a regra inteira.
- Permissão de editar/apagar: o próprio profissional (se a ausência é dele),
  ou gestor/secretária da mesma clínica. Outra clínica → 404.

### Bloqueio nas consultas

`criar_consulta`, `editar_consulta` (quando muda data, hora, duração ou
profissional) e `criar_consulta_recorrente` chamam `conflito_ausencia`:

- Criar/editar: conflito → **409** `{"erro": "Fulano está ausente nesse horário (Férias).", "ausencia_id": …}`.
- Recorrente: as ocorrências em conflito são **puladas**; a resposta ganha
  `datas_puladas: ["YYYY-MM-DD", …]`. Se todas caírem em ausência → 409.
  `serie_recorrencia_id` continua sendo o id da primeira consulta criada.
- Consulta cancelada não é checada (editar uma cancelada não muda horário).

### Auditoria

`log_auditoria` em criar/editar/apagar ausência (`entidade = "ausencia"`).

## Front-end

### Arquivos

- `frontend/js/agenda_ausencias.js` (novo, puro, testado em
  `frontend/tests/agenda_ausencias.test.js`): `ocorrenciasNoDia`,
  `intervaloBloqueado(ocorrencias, profissionalId, chaveDia, iniMin, fimMin)`,
  `calcularFim(inicioHHMM, duracaoMin)`, `duracaoEntre(inicio, fim)`.
- `frontend/js/views/agenda_ausencia_modal.js` (novo): parte "Ausência" do
  pop-up e o pop-up de editar/apagar ausência.
- `frontend/js/views/agenda.js`: hora de fim, visão Dia, desenho das
  ausências e o seletor "Consulta | Ausência".
- `frontend/js/agenda_faixa.js`: `calcularFaixaAgenda` passa a considerar
  também as ocorrências de ausência com horário (para não esconder nada).

### Pop-up "Agendar"

- No topo, **"Consulta | Ausência"**.
- **Consulta**: Início e **Fim**. Fim inicial = início + `agenda_duracao_padrao`
  (do `/auth/me`; 50 se ausente). Mudar o início desloca o fim mantendo a
  duração; o fim é editável. Fim ≤ início → erro no próprio campo. Envia
  `duracao_min`. Na série recorrente, `datas_puladas` vira um aviso depois de
  salvar ("Não agendado em 14/10 e 21/10: profissional ausente").
- **Ausência**: profissional (para o profissional comum, fixo nele), data de
  início, data de fim (vazio = sem fim), ☐ Dia inteiro (marcado esconde as
  horas), início/fim, dias da semana (seg–sáb marcados por padrão quando o
  período tem mais de um dia; com um dia só, marca o dia da semana dele),
  motivo. Abrindo o pop-up por um clique na grade, data, hora e profissional
  vêm preenchidos. Depois de salvar, se `consultas_no_periodo` não estiver
  vazio, mostra a lista ("Há N consultas nesse período — remarque ou cancele").
- Clicar num bloco de ausência abre o pop-up dela (editar/apagar) para quem
  tem `pode_editar`; para os demais, só mostra motivo e período.

### Pop-up de editar consulta

Ganha **Início** e **Fim** (mesma regra do "Agendar").

### Grade

- Ausência = bloco **cinza listrado** "Ausente · motivo" atrás das consultas;
  dia inteiro ocupa a coluna toda.
- Clique ou arraste num trecho bloqueado não abre o "Agendar" (avisa
  "Profissional ausente nesse horário").
- Arrastar uma consulta mantém a duração; se o backend devolver 409, a
  consulta volta ao lugar e a mensagem aparece (o front também checa antes
  com `intervaloBloqueado`, mas quem manda é o backend).

### Visão Dia

- **Por Profissional**: botões **Dia | Semana** ao lado das setas. Dia = uma
  coluna larga do profissional selecionado; setas andam 1 dia; "Hoje" volta
  para hoje.
- **Geral**: botões **Dia | Lista | Semana | Mês**. Dia = **uma coluna por
  profissional** (ativos e não excluídos, os que o usuário pode ver). Na
  visão Dia, a lista lateral é filtro: clicar mostra/esconde a coluna; "Todos"
  mostra todos. Nas demais visões do modo Geral, a lista lateral continua
  como hoje. Mais colunas do que cabem → rolagem horizontal, com a coluna
  de horas fixa. Clique num horário vazio → "Agendar" com profissional e hora
  da coluna; arrastar para outra coluna troca o profissional (mesmas regras
  de bloqueio e vínculo automático).
- A faixa horária é a mesma da grade atual (`calcularFaixaAgenda`).

### Configurações

Campo **"Duração padrão da consulta (min)"** no cartão do horário da agenda
(`financeiro.js`, junto de "Abre às"/"Fecha às").

## Erros e casos de borda

- Ausência com `data_fim` < `data_inicio`, hora fim ≤ início, nenhum dia da
  semana ou motivo longo → 400 com mensagem em português.
- Ausência de profissional arquivado/excluído → 400 (mesma regra das
  consultas).
- `GET /ausencias` com intervalo > 62 dias ou datas inválidas → 400.
- Profissional comum tentando ver/editar ausência de outro → 403/404.
- Clínica sem `agenda_duracao_padrao` (antes da migração) → front usa 50.

## Testes

- **Backend** (`backend/tests/test_agenda_ausencias.py`, novo): validação;
  `ausencia_cobre` (período, dia da semana, sem fim, dia inteiro, borda que
  encosta); permissões (profissional só as dele, secretária/gestor para
  todos, outra clínica, responsável); bloqueio em criar/editar/arrastar/
  reatribuir; série recorrente com `datas_puladas` e com tudo bloqueado;
  `consultas_no_periodo`; `duracao_min` inválida; padrão da clínica.
- **Front** (Node): `agenda_ausencias.test.js` e casos novos em
  `agenda_faixa.test.js`.
- **Playwright** de fumaça: lançar almoço seg–sex, ver o bloco, tentar
  agendar por cima, visão Dia nos dois modos.

## Produção

Mudança de schema: rodar `backend/migracoes/migracao_ausencias_agenda.sql`
no Supabase (ou `migrar_ausencias_agenda.py`, conferindo `(Postgres)`)
**antes** do `git pull` + `touch tmp/restart.txt`.
