# Jornada e Diário por paciente — design (parte 3a)

Data: 08/10/2026. Parte 3a da comparação com a Clínica Ágil. A parte 3b
(Atender/Evoluir a partir da consulta, status novos, histórico de
atendimentos) depende desta e terá spec própria.

## Objetivo

1. O **Diário Terapêutico passa a ser do paciente**, não da jornada: dá para
   registrar e ver o diário mesmo sem jornada ativa.
2. A **jornada fica só para planejar** objetivos e missões.
3. **"Iniciar jornada terapêutica"** abre um único pop-up (objetivo principal +
   título do plano + objetivos) em vez do `prompt()` do navegador seguido do
   "Novo plano".
4. O **Objetivo Principal** pode ser editado depois.

Fora do escopo: botão "Atender", status novos de consulta, histórico de
atendimentos (parte 3b).

## Decisões do usuário (07–08/10/2026)

| Pergunta | Decisão |
|---|---|
| Diário de paciente sem jornada | **Diário sem jornada** — ligado ao paciente (opção C). |
| Papel da jornada | Só planejamento de objetivos e missões. |
| Iniciar jornada | Um pop-up no formato do plano terapêutico, sem `prompt()`. |
| Objetivo principal | **Campo próprio** no topo do pop-up (opção A) e editável depois (✏️ no cartão). |

## Dados

`diarios_terapeuticos`:

- Coluna nova **`paciente_id INTEGER REFERENCES pacientes(id)`**, preenchida nos
  registros antigos a partir de `jornadas.paciente_id`. Todo registro novo grava
  o paciente.
- **`jornada_id` passa a ser opcional** (sem `NOT NULL`). Registro novo grava a
  jornada ativa quando existir (mantém ICT/relatório/marcos coerentes); sem
  jornada, fica NULL.
- Índice em `(paciente_id, data_atendimento)`.

Migração `backend/migracoes/migracao_diario_por_paciente.sql` (idempotente):

```sql
ALTER TABLE diarios_terapeuticos ADD COLUMN IF NOT EXISTS paciente_id INTEGER REFERENCES pacientes(id);
UPDATE diarios_terapeuticos d SET paciente_id = j.paciente_id
  FROM jornadas j WHERE j.id = d.jornada_id AND d.paciente_id IS NULL;
ALTER TABLE diarios_terapeuticos ALTER COLUMN jornada_id DROP NOT NULL;
CREATE INDEX IF NOT EXISTS idx_diarios_paciente ON diarios_terapeuticos(paciente_id, data_atendimento);
```

e `backend/migrar_diario_por_paciente.py` (Postgres: roda o `.sql`; SQLite:
adiciona a coluna e preenche — o `NOT NULL` antigo de `jornada_id` só some
num banco local recriado pelo `seed.py`, o que já é o procedimento normal).
`schema.sql` e `schema_postgres.sql` já nascem com a coluna e sem o `NOT NULL`.

## Backend

### Diário (`diario_bp.py`)

- **`GET /api/diario/paciente/<paciente_id>`** — histórico completo, mais
  recente primeiro. Acesso: `paciente_acessivel`. Responsável só vê
  `compartilhado_familia = 1` e nunca `evolucao_clinica` (mesma regra de hoje).
- **`POST /api/diario/paciente/<paciente_id>`** — cria. Acesso:
  `paciente_editavel` (equipe da clínica; papéis profissional e gestor, como
  hoje). Grava `paciente_id`, `jornada_id` = jornada ativa (ou NULL),
  `consulta_id` se vier no corpo e for uma consulta **desse paciente** (senão
  400). Notifica a família como hoje.
- **Rotas antigas** `GET/POST /api/diario/jornada/<jornada_id>` continuam, como
  atalho: resolvem a jornada → paciente e devolvem o mesmo que as novas
  (o GET passa a listar todos os diários do paciente).
- `obter_diario`, `editar_diario`, anexos: resolvem o paciente por
  `diarios_terapeuticos.paciente_id` (não mais pela jornada).

### Ficha (`jornada_bp.py`, dados do paciente)

- `diarios_recentes` (5 últimos, pelo paciente) vem **sempre**, inclusive no
  caso sem jornada (hoje o retorno sem jornada é só `paciente`, `jornada: None`,
  `planos: []`). Mesmo filtro da família.

### Iniciar jornada e objetivo principal (`jornada_bp.py`)

- **`POST /api/jornada/paciente/<paciente_id>/iniciar`** — corpo
  `{objetivo_principal, titulo, objetivos: [..]}`. Valida tudo antes de gravar:
  objetivo principal obrigatório (até 300 caracteres), título obrigatório (até
  120), pelo menos um objetivo não vazio. Já existe jornada ativa → 409. Cria a
  jornada e o primeiro plano (com os objetivos) e devolve
  `{jornada_id, plano_id}` (201). Mesmos `log_evento` de hoje
  (`jornada_criada`, `plano_iniciado`). Permissão: `paciente_editavel`.
- **`PUT /api/jornada/jornada/<jornada_id>`** — corpo `{objetivo_principal}`
  (obrigatório, até 300). Permissão: `paciente_editavel` do paciente da
  jornada; outra clínica → 403.
- `POST /criar-jornada` antigo continua existindo (não é mais usado pela tela).

### ICT e relatório

- `ict_service`: "profissional acompanhou" conta diários por **`paciente_id`**
  na janela.
- `relatorio_service` já usa `diarios_recentes` dos dados da ficha — passa a
  pegar os do paciente automaticamente.

### Seed

`seed.py` grava `paciente_id` nos diários de demonstração.

## Front-end

- **Ficha sem jornada** (`jornada.js`): mostra o cartão **📔 Diário
  Terapêutico** (com "+ Novo Diário" para quem pode editar e "Ver histórico
  completo" quando houver registros) e, abaixo, o cartão "Ainda não tem uma
  jornada terapêutica" com o botão.
- **"Iniciar jornada terapêutica"** → pop-up: **Objetivo principal**
  (obrigatório), **Título do plano** (obrigatório), **Objetivos (um por linha)**
  (obrigatório) → "Iniciar jornada" → `POST /iniciar`. Sem `prompt()`.
- **Cartão "🎯 Objetivo Principal"**: botão ✏️ (só para quem pode editar) →
  pop-up com o texto → `PUT /jornada/jornada/<id>`.
- `diario.js`: "Novo Diário" e "Histórico" usam as rotas por paciente
  (`abrirModalNovoDiario(paciente)`, `abrirModalHistoricoDiario(pacienteId)`).
- `responsavel.js`: lista o diário pelo paciente, com ou sem jornada.

## Erros e casos de borda

- Paciente de outra clínica → 403 em todas as rotas novas.
- `consulta_id` de outro paciente → 400.
- Registros antigos sem `paciente_id` (antes da migração) não existem depois
  dela; o código não precisa de fallback.
- Iniciar com jornada ativa (ex.: duas abas) → 409, nada criado.

## Testes

Backend (`backend/tests/test_diario_por_paciente.py`, `test_iniciar_jornada.py`):
diário sem jornada (criar, listar, aparecer na ficha); diário com jornada grava
as duas colunas; família não vê evolução clínica nem não compartilhados; rotas
antigas funcionam; `consulta_id` de outro paciente → 400; IDOR entre clínicas;
iniciar cria jornada + plano + objetivos, 400 sem cada campo (nada criado), 409
com jornada ativa; editar objetivo principal (ok, vazio → 400, outra clínica →
403); ICT conta diário por paciente. Atualizar `tests_postgres` para a rota
nova. Migração idempotente (SQLite).

Playwright de fumaça: paciente sem jornada → Novo Diário → aparece; Iniciar
jornada pelo pop-up; editar objetivo principal; família vê o diário
compartilhado.

## Produção

Rodar `backend/migracoes/migracao_diario_por_paciente.sql` no Supabase (ou
`migrar_diario_por_paciente.py`, conferindo `(Postgres)`) **antes** do
`git pull` + `touch tmp/restart.txt`.
