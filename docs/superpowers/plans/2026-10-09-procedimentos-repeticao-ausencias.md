# Procedimentos, repetição avançada e ausências no Geral — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cadastro de procedimentos com valor (gestor) ligado ao agendamento; repetição de agendamento com as opções da Clínica Ágil; ausências nas visões Lista/Semana/Mês do modo Geral.

**Architecture:** Parte A: tabela `procedimentos` + 2 colunas em `consultas`, blueprint novo `procedimentos_bp`, view `procedimentos.js`, select nos pop-ups da agenda. Parte B: função pura `recorrencia_service.gerar_datas` usada por `POST /api/agenda/recorrente` (com `previa`), painel novo no pop-up. Parte C: só front — carregar ausências pelo período da visão e desenhá-las com funções puras de `agenda_ausencias.js`.

**Tech Stack:** Flask + SQLite/Postgres; JS puro; pytest; node --test.

**Spec:** `docs/superpowers/specs/2026-10-09-procedimentos-repeticao-ausencias-design.md`

## Global Constraints

- Windows: em `backend/`, `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q <arquivo>`; na raiz, `node --test frontend/tests/*.test.js`.
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Três PRs, nesta ordem: A → B → C**, cada um com suíte completa, PR, CI. A tem schema: **perguntar antes de mesclar** e passar o SQL. B e C: merge automático com testes e CI verdes.
- Valor do procedimento: **só o gestor** vê, também na API. Responsável não vê procedimento.
- Procedimento obrigatório só se a clínica tem ≥ 1 ativo; no `PUT /agenda/<id>` só se a chave `procedimento_id` vier no corpo.
- `procedimento_valor_centavos` = valor do cadastro no momento em que o procedimento é gravado ou trocado; manter o mesmo não muda.
- Valor de 0 a 10.000.000 centavos; nome até 120, único por clínica (LOWER/TRIM); código até 30.
- Repetição: no máximo 12 meses depois da 1ª data e 300 consultas; sem fim = 12 meses.
- Consultas não têm `organizacao_id`: a clínica vem do paciente (`pacientes.organizacao_id`).
- `schema.sql` e `schema_postgres.sql` mudam juntos (o CI tem smoke em Postgres).

## Review Focus

1. **Salvar a lista de procedimentos com um usado removido** não grava nada (nem as outras linhas). Teste na Task 2.
2. **Profissional/secretária nunca recebem valor**, nem em `/procedimentos` nem em `/agenda`. Teste nas Tasks 2 e 3.
3. **Editar consulta antiga sem mandar `procedimento_id`** (arrastar, status, só observação) continua funcionando com cadastro existente. Teste na Task 3.
4. **Mensal "dia 31"** e **"5ª terça"** caem no último dia/última terça; meses desmarcados pulam. Teste na Task 6.
5. **Ausência de vários dias** (ex.: férias de 2 semanas) aparece em todos os dias da Semana/Mês e uma vez por dia na Lista, respeitando o filtro de profissionais. Teste na Task 9.

---

## Parte A — Procedimentos (PR 1, branch `procedimentos-agenda`)

### Task 1: Schema e migração
Files: `backend/schema.sql`, `backend/schema_postgres.sql`, `backend/migracoes/migracao_procedimentos.sql`, `backend/migrar_procedimentos.py`, test `backend/tests/test_procedimentos_schema.py`.

- [ ] Teste (falha primeiro): tabela `procedimentos` existe com as colunas da spec; `consultas.procedimento_id` e `consultas.procedimento_valor_centavos` existem; dois procedimentos com o mesmo nome (`"Sessão"` e `" sessão "`) na mesma clínica → `IntegrityError` (ou subclasse); mesmo nome em outra clínica → ok; `migrar_procedimentos.migrar()` roda duas vezes sem erro.
- [ ] SQL (SQLite):
```sql
CREATE TABLE procedimentos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    codigo          TEXT,
    nome            TEXT NOT NULL,
    valor_centavos  INTEGER NOT NULL DEFAULT 0,
    ativo           INTEGER NOT NULL DEFAULT 1,
    ordem           INTEGER NOT NULL DEFAULT 0,
    criado_em       TEXT DEFAULT (datetime('now')),
    atualizado_em   TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX idx_procedimento_nome ON procedimentos(organizacao_id, LOWER(TRIM(nome)));
-- em consultas:
    procedimento_id INTEGER REFERENCES procedimentos(id),
    procedimento_valor_centavos INTEGER,
```
  Postgres: `SERIAL PRIMARY KEY`, `TIMESTAMP DEFAULT NOW()` conforme o padrão do `schema_postgres.sql`.
- [ ] `migracao_procedimentos.sql` (Postgres, idempotente): `CREATE TABLE IF NOT EXISTS procedimentos (...)`, `CREATE UNIQUE INDEX IF NOT EXISTS idx_procedimento_nome ...`, `ALTER TABLE consultas ADD COLUMN IF NOT EXISTS procedimento_id INTEGER REFERENCES procedimentos(id)`, `ALTER TABLE consultas ADD COLUMN IF NOT EXISTS procedimento_valor_centavos INTEGER`.
- [ ] `migrar_procedimentos.py` no padrão de `migrar_atender.py` (Postgres lê o `.sql`; SQLite cria tabela/índice com `IF NOT EXISTS` e adiciona colunas se faltarem via `PRAGMA table_info`), imprime `(Postgres)`/`(SQLite)`.
- [ ] Commit.

### Task 2: API de procedimentos
Files: `backend/procedimentos_service.py` (novo), `backend/blueprints/procedimentos_bp.py` (novo), `backend/app.py` (registrar), test `backend/tests/test_procedimentos.py`.

Interfaces (Produces):
- `procedimentos_service.reais_para_centavos(valor) -> int | None` (aceita int/float/str "230", "230,00", "1.230,50", "R$ 230,00"; None se inválido ou negativo ou > 10_000_000).
- `procedimentos_service.ativos_da_clinica(org_id) -> list[dict]` (`id, nome, codigo`, por `ordem`).
- `procedimentos_service.clinica_tem_ativos(org_id) -> bool`.
- `procedimentos_service.procedimento_valido(org_id, procedimento_id, permitir_id=None) -> dict | None` (da clínica e ativo; `permitir_id` aceita esse id mesmo desativado).
- Rotas `GET /api/procedimentos`, `PUT /api/procedimentos` (prefixo do blueprint `/api/procedimentos`).

- [ ] Testes (falham primeiro):
  - `reais_para_centavos`: "230,00"→23000, "1.230,50"→123050, 230.5→23050, 230→23000, "R$ 15"→1500, "-1"→None, "abc"→None, "" → None, 10_000_001 reais → None.
  - GET gestor: lista com `valor_centavos`, `ativo`, `em_uso`; profissional e secretária: só ativos e **sem** `valor_centavos`; responsável → 403.
  - PUT só gestor (profissional/secretária → 403); cria 3, reordena (ordem segue a lista), edita valor e nome, desativa.
  - PUT com nome repetido na lista ("Sessão" e " sessão ") → 400 e nada gravado; nome vazio → 400; código com 31 caracteres → 400; valor inválido → 400 com o nome da linha.
  - PUT omitindo um procedimento usado numa consulta → 409 e **nenhuma** outra mudança gravada (ex.: o valor alterado de outra linha continua o antigo); omitindo um não usado → apagado.
  - PUT com `id` de outra clínica → 400.
  - Auditoria gravada (`entidade = 'procedimentos'`).
- [ ] Implementar. PUT valida tudo (normaliza, confere duplicados entre si e com nada fora da lista, confere ids da clínica e removidos usados) **antes** de qualquer `execute`; depois apaga removidos, atualiza existentes (`atualizado_em`), insere novos. Para não esbarrar no índice único ao trocar nomes entre linhas, atualizar primeiro com nome temporário `"__tmp__<id>"` só se houver troca cruzada — ou, mais simples: apagar removidos, depois atualizar/inserir em ordem; troca cruzada de nomes entre duas linhas é rejeitada pelo índice → capturar `IntegrityError` (checar pela MRO, como na rodada rápida) e devolver 409 "Nomes trocados entre linhas: salve em duas etapas". Registrar em `app.py`.
- [ ] Commit.

### Task 3: Procedimento nas consultas (API)
Files: `backend/blueprints/agenda_bp.py`, test `backend/tests/test_procedimentos_agenda.py`.

Interfaces: Consumes `procedimento_valido`, `clinica_tem_ativos`, valor do cadastro.

- [ ] Testes (falham primeiro):
  - Clínica com procedimentos: `POST /api/agenda` sem `procedimento_id` → 400 "Escolha o procedimento"; com um ativo → 201 e `procedimento_valor_centavos` = valor do cadastro; com desativado ou de outra clínica → 400.
  - Clínica sem procedimentos: agendar sem → 201 (comportamento atual).
  - `POST /api/agenda/recorrente` sem → 400; com → todas as consultas da série com o mesmo `procedimento_id` e valor.
  - Mudar o preço no cadastro não muda `procedimento_valor_centavos` da consulta já marcada.
  - `PUT /api/agenda/<id>` trocando o procedimento → valor novo; mandando o mesmo → valor antigo mantido; com `procedimento_id: null` com cadastro → 400; **sem a chave** (só observação / arrastar) → 200; consulta com procedimento desativado depois, reenviando o mesmo id → 200.
  - `GET /api/agenda`: gestor recebe `procedimento_nome` e `procedimento_valor_centavos`; profissional e secretária recebem `procedimento_nome` e **não** a chave `procedimento_valor_centavos`; responsável não recebe `procedimento_id`, `procedimento_nome` nem o valor.
- [ ] Implementar: helper `_procedimento_do_corpo(body, org_id, atual_id=None) -> (proc_id, valor, erro)`; usar em `criar_consulta`, `criar_consulta_recorrente` (antes de gerar datas) e `editar_consulta` (só se `"procedimento_id" in body`; mesmo id = mantém valor). `listar_consultas`: `LEFT JOIN procedimentos pr ON pr.id = c.procedimento_id` + `pr.nome AS procedimento_nome`; depois do `query`, para papel ≠ gestor/admin_master, `pop("procedimento_valor_centavos")`; para responsável, `pop` de `procedimento_id` e `procedimento_nome` também.
- [ ] Commit.

### Task 4: Tela de Procedimentos (gestor)
Files: `frontend/js/procedimentos_util.js` (novo, puro), `frontend/tests/procedimentos_util.test.js`, `frontend/js/views/procedimentos.js` (novo), `frontend/js/shell.js` (menu), `frontend/js/app.js` (rota), `frontend/index.html`, `frontend/css/components.css`.

Interfaces (Produces): `reaisParaCentavos(texto) -> number|null`, `centavosParaReais(n) -> "1.230,50"`.

- [ ] Node test (falha primeiro): mesmos casos do backend para `reaisParaCentavos`; `centavosParaReais(123050) === "1.230,50"`, `(0) === "0,00"`, `(5) === "0,05"`.
- [ ] View `viewProcedimentos(app)`: igual à prévia (aviso, tabela com ⋮⋮ arrastar via `draggable` + `dragover`/`drop` para reordenar, Desativar, Código, Procedimento, Valor, Remover/🔒 com "usado em N consultas", linha desativada riscada, "+ Nova linha", "Salvar" → `PUT /procedimentos`, toast; erro 400/409 mostra a mensagem do backend). Valor reformatado ao sair do campo; linha com valor inválido fica com borda vermelha e o Salvar avisa. Estado vazio. Tabela dentro de `overflow-x:auto`.
- [ ] Menu do gestor: `{ rota: "#/gestor/procedimentos", icone: "💲", label: "Procedimentos" }` antes de Configurações; rota em `app.js`; scripts no `index.html` (util antes das views).
- [ ] Browser (gestor): criar 3, reordenar, desativar, remover não usado, tentar remover usado (409), recarregar mantém ordem; 400px sem rolagem lateral da página. Commit.

### Task 5: Select no agendamento + fechamento da Parte A
Files: `frontend/js/views/agenda.js` (pop-ups de agendar e editar), `CLAUDE.md`.

- [ ] Ao abrir a agenda (gestor/profissional/secretária), `GET /procedimentos` uma vez (lista de ativos; para o gestor, filtrar `ativo`). Se vazia, nada muda nos pop-ups.
- [ ] Pop-up de agendar (único e série): select "Procedimento *" depois do profissional, "Selecione…" + nomes; validação no front ("Escolha o procedimento") e `procedimento_id` no corpo.
- [ ] Pop-up de editar: mesmo select com o atual selecionado; se o atual não está entre os ativos, opção extra `"<nome> (desativado)"`; sempre envia `procedimento_id`. Mostrar o nome do procedimento no topo do pop-up (junto do paciente).
- [ ] Browser: gestor agenda com procedimento; profissional e secretária veem o select sem valor (conferir a resposta de `/agenda` no console sem `procedimento_valor_centavos`); clínica sem cadastro não vê o campo; editar consulta antiga pede o procedimento; arrastar não pede.
- [ ] CLAUDE.md: item `ae)` na seção 5 (Parte A), seção 7 (migração `migracao_procedimentos.sql` pendente), seção 8 (linhas novas). Suíte completa + Node. Revisão final da Parte A (revisor novo, model fable) sobre o diff da parte; corrigir Críticos/Importantes com TDD; PR "Procedimentos com valor no agendamento (parte A)"; **perguntar antes de mesclar** e passar o SQL.

---

## Parte B — Repetição avançada (PR 2, branch `repeticao-avancada`, a partir do `main` com a Parte A)

### Task 6: Função de datas
Files: `backend/recorrencia_service.py` (novo), test `backend/tests/test_recorrencia_service.py`.

Interfaces (Produces):
```python
def gerar_datas(regra: dict, inicio: datetime, hoje: date | None = None) -> list[tuple[str, int]]:
    """[("YYYY-MM-DD HH:MM:SS", duracao_min), ...] em ordem; levanta ValueError("mensagem") se a regra é inválida."""
```
`regra` (já normalizada pela rota):
```python
{
  "frequencia": "semanal" | "quinzenal" | "mensal" | "semanas",
  "a_cada": 1..12,                 # só "semanas"; semanal=1, quinzenal=2
  "dias": {"1": {"inicio": "09:00", "fim": "09:50"}, "3": {...}},  # 0=domingo..6=sábado; ausente = só o dia de `inicio` com o horário dele
  "mensal_por": "dia_mes" | "dia_semana",   # só mensal
  "meses": [1..12] | None,          # None = todos
  "data_limite": "YYYY-MM-DD" | None,
  "quantidade": int | None,         # 1..300
}
```
Constantes: `LIMITE_CONSULTAS = 300`, `LIMITE_MESES = 12`.

- [ ] Testes (falham primeiro), início numa segunda 2026-10-12 09:00 e 50 min, salvo quando o teste diz outro horário:
  - semanal, dias seg 09:00–09:50 e qua 14:00–15:00, quantidade 4 → seg 12, qua 14, seg 19, qua 21, com durações 50 e 60.
  - quinzenal só seg, quantidade 3 → 12/10, 26/10, 09/11.
  - "semanas" a cada 3, quantidade 3 → 12/10, 02/11, 23/11.
  - semanal com dia anterior ao início na mesma semana (domingo marcado) → o domingo 11/10 **não** entra (nada antes de `inicio`).
  - mensal dia_mes a partir de 31/01/2027, quantidade 3 → 31/01, 28/02, 31/03.
  - mensal dia_semana a partir de 13/10/2026 (2ª terça) quantidade 3 → 13/10, 10/11, 08/12; a partir de 29/12/2026 (5ª terça) → 29/12, depois a última terça de jan/2027 (26/01).
  - meses [10, 12] semanal seg quantidade 6 → só datas de outubro e dezembro.
  - data_limite 2026-10-31 semanal seg → 12, 19, 26.
  - sem fim → última data ≤ início + 12 meses; nenhuma depois.
  - data_limite além de 12 meses → ValueError; quantidade 301 → ValueError; série sem fim que passaria de 300 (todos os dias da semana) → ValueError "A repetição passa de 300 consultas; diminua os dias ou o período" (não corta sozinho).
  - dia sem horário válido ou fim ≤ início → ValueError; nenhum dia marcado em semanal → ValueError; meses vazio → ValueError.
- [ ] Implementar (laço por semana/mês a partir de `inicio`, usando `calendar.monthrange` para o último dia; "última X do mês" = maior dia do mês com o mesmo `weekday`). Commit.

### Task 7: Rota com regra nova e prévia
Files: `backend/blueprints/agenda_bp.py` (`criar_consulta_recorrente`), test `backend/tests/test_repeticao_avancada.py`.

- [ ] Testes (falham primeiro):
  - corpo novo `{"paciente_id", "profissional_id", "data_hora", "procedimento_id"?, "repeticao": {regra}}` → cria todas com o mesmo `serie_recorrencia_id`, durações por dia.
  - `"previa": true` → 200 `{"datas": [{"data_hora", "duracao_min", "ausente": bool, "ocupada": bool}], "total": N, "primeira", "ultima"}` e **nenhuma** consulta criada.
  - corpo antigo (`frequencia` + `repeticoes`) continua criando como antes (testes atuais seguem verdes).
  - regra inválida → 400 com a mensagem do ValueError.
  - ausência pula a data (`datas_puladas`); encaixe pede confirmação (409 `pode_encaixar`), com `encaixe: true` cria.
  - procedimento obrigatório vale para a série (já coberto na Task 3; repetir 1 caso com `repeticao`).
- [ ] Implementar: se `repeticao` no corpo → normalizar e `gerar_datas`; senão traduzir o corpo antigo para uma regra (`semanal`/`quinzenal`/`mensal dia_mes`, `quantidade = repeticoes`, sem `dias`). Checagens de ausência/encaixe por (data, duração) de cada item. Commit.

### Task 8: Painel de repetição no pop-up + fechamento da Parte B
Files: `frontend/js/views/agenda.js` (pop-up de agendar), `frontend/js/repeticao_util.js` (novo, puro), `frontend/tests/repeticao_util.test.js`, `frontend/index.html`, `frontend/css/components.css`, `CLAUDE.md`.

Interfaces: `montarRegraRepeticao(estadoDoFormulario) -> {regra} | {erro}` (puro: valida dias marcados, horários, fim > início, quantidade 1–300, data limite ≥ data inicial).

- [ ] Node test (falha primeiro) de `montarRegraRepeticao`: semanal com 2 dias; "Todos os dias" marca 0–6; mensal envia `mensal_por`; meses "todos" → `null`; sem fim → sem `data_limite`/`quantidade`; erros com mensagem.
- [ ] Painel (ao ligar "Repetir"): Frequência (Semanal | Quinzenal | Mensal | A cada N semanas + campo N); Dias da semana com início/fim por dia (começa marcado o dia da data, com o horário do agendamento) e "Todos os dias"; Mensal: rádio "No mesmo dia do mês" / "No mesmo dia da semana" (texto explica com a data escolhida, ex.: "toda 2ª terça-feira"); Meses (12 caixas + "Todos os meses"); Até quando: Data limite **ou** Quantidade (preencher um limpa o outro) e dica "Sem limite: até 12 meses".
- [ ] Prévia: ao mudar qualquer campo (debounce 400 ms), `POST /agenda/recorrente` com `previa: true` → "Serão criadas N consultas, de dd/mm/aaaa a dd/mm/aaaa" + "Datas com ausência (serão puladas): …" + "Horário ocupado (pede encaixe): …". Erro 400 aparece no lugar da prévia.
- [ ] Browser: série seg+qua com horários diferentes; quinzenal; mensal 2ª terça; meses só out/dez; data limite; sem fim; excluir "esta e as futuras" numa série de dois dias; 400px.
- [ ] CLAUDE.md item `af)`; suíte + Node; revisão final da Parte B; PR "Repetição avançada do agendamento (parte B)"; merge automático com CI verde.

---

## Parte C — Ausências no modo Geral (PR 3, branch `ausencias-modo-geral`, a partir do `main` com A e B)

### Task 9: Funções puras
Files: `frontend/js/agenda_ausencias.js`, `frontend/tests/agenda_ausencias.test.js`.

Interfaces (Produces):
- `periodoDaVisao(visao, dataReferencia, hoje) -> {inicio: "YYYY-MM-DD", fim: "YYYY-MM-DD"}` — semana: domingo–sábado; mês: as 42 células (`inicioDaSemana(1º do mês)` + 41); lista: hoje → hoje+29; dia: o dia.
- `ausenciasPorDia(ocorrencias, profsVisiveis /* Set|null */) -> {"YYYY-MM-DD": [ocorrencia, ...]}` — ordena por início (dia inteiro primeiro); `null` = todos.
- `rotuloAusencia(o) -> "Camila · 08:00–12:00"` / `"Camila · dia inteiro"` (primeiro nome).

Formato da ocorrência = o que `GET /api/agenda/ausencias` já devolve (conferir no código: `data`, `profissional_id`, `profissional_nome`, `dia_inteiro`, `hora_inicio`, `hora_fim`, `motivo`, `id`).

- [ ] Node tests (falham primeiro): período de cada visão (mês de outubro/2026 começa em 27/09 e termina em 07/11); férias de 2 semanas aparecem em todos os dias; filtro de profissionais; ordenação; rótulos.
- [ ] Implementar. Commit.

### Task 10: Desenhar nas visões + fechamento da Parte C
Files: `frontend/js/views/agenda.js`, `frontend/css/components.css`, `CLAUDE.md`.

- [ ] `carregarAusencias` passa a usar `periodoDaVisao(visaoAtual, …)` (modo Geral) e a semana (Por Profissional) — chave de cache por período.
- [ ] Semana: chips `.agenda-chip-ausencia` (cinza listrado, mesmo padrão do bloco da grade) antes das consultas, `title` com o motivo, `data-idx` → abre o pop-up de ausência existente (mesmas permissões; sem permissão, só leitura).
- [ ] Mês: linha "⛔ N ausente(s)" na célula; a célula com ausência também abre o pop-up do dia, que lista as ausências no topo (`abrirModalConsultasDoDia` recebe as ocorrências do dia).
- [ ] Lista: cartão "Ausências dos próximos 30 dias" acima de "Próximas consultas" (uma linha por ocorrência: data, profissional, horário, motivo; clique abre o pop-up); some se não houver.
- [ ] Filtro da lista lateral aplicado; responsável não carrega nem vê.
- [ ] Browser: ausência de dia inteiro e de horário, férias de 2 semanas, filtro, clicar abre/edita, secretária e profissional; 400px.
- [ ] CLAUDE.md item `ag)` e seção 7 (tirar os dois PRs pendentes); suíte + Node; revisão final da Parte C; PR "Ausências nas visões do modo Geral (parte C)"; merge automático com CI verde.
