# Atender / Evoluir (parte 3b) — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Atender a consulta pela agenda: página de evolução ligada ao Diário, status novos, histórico, faixa de atraso e permissões da secretária.

**Architecture:** Status novos no CHECK de `consultas`; `diarios_terapeuticos.observacao` + índice único por consulta; rotas `GET/PUT /api/agenda/<id>/atendimento` em `agenda_bp`; view nova `atendimento.js`; pop-up da consulta ganha "Atender"/faixa de atraso e regras da secretária.

**Tech Stack:** Flask + SQLite/Postgres; JS puro; pytest; node --test.

**Spec:** `docs/superpowers/specs/2026-10-08-atender-evoluir-design.md`

## Global Constraints

- Windows: `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q <arquivo>` em `backend/`; `node --test frontend/tests/*.test.js` na raiz.
- Commits com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Status que liberam horário: `cancelada`, `desmarcada_profissional`, `falta_justificada`. Desfecho: `realizada`, `faltou`, `falta_justificada`, `desmarcada_profissional`.
- Família nunca vê `evolucao_clinica` nem `observacao`.
- Atender: só gestor da clínica e profissional da consulta.

## Review Focus

1. **Profissional que não é o da consulta (mesmo com agenda total)** abre `/atendimento` → 403. Teste na Task 3.
2. **Salvar duas vezes** não cria dois registros no Diário (atualiza o mesmo; índice único). Teste na Task 3.
3. **Desfecho "falta" sem texto** não cria registro vazio no Diário. Teste na Task 3.
4. **Família**: registro do atendimento aparece sem evolução e sem observação. Teste na Task 3.
5. **Consulta desmarcada pelo profissional libera o horário** para outra consulta sem pedir encaixe. Teste na Task 2.

---

### Task 1: Schema e migração
Files: `backend/schema.sql`, `backend/schema_postgres.sql`, `backend/migracoes/migracao_atender.sql`, `backend/migrar_atender.py`, test `backend/tests/test_atender_schema.py`.
- [ ] Teste: consulta aceita `falta_justificada`/`desmarcada_profissional` (INSERT direto) e recusa `xyz` (IntegrityError); `diarios_terapeuticos.observacao` existe; dois diários com o mesmo `consulta_id` → IntegrityError; migração idempotente (SQLite: coluna + índice; o CHECK do SQLite só muda recriando o banco — documentado).
- [ ] SQL Postgres: `ALTER TABLE consultas DROP CONSTRAINT IF EXISTS consultas_status_check; ALTER TABLE consultas ADD CONSTRAINT consultas_status_check CHECK (status IN (...7 valores...)); ALTER TABLE diarios_terapeuticos ADD COLUMN IF NOT EXISTS observacao TEXT;` desduplicar diários por consulta (mantém MAX(id), zera `consulta_id` dos outros) e `CREATE UNIQUE INDEX IF NOT EXISTS idx_diario_por_consulta ...`.
- [ ] Commit.

### Task 2: Status novos e horário liberado
Files: `backend/blueprints/agenda_bp.py`, `backend/ausencias_service.py`, `backend/blueprints/pessoas_bp.py`, test `backend/tests/test_atender_status.py`.
- [ ] Testes: PUT status aceita os novos; secretária com `realizada` → 403 (gestor/profissional ok); consulta `desmarcada_profissional`/`falta_justificada` não gera encaixe para outra no mesmo horário; reativar `desmarcada_profissional`→`agendada` sobre horário ocupado pede encaixe; `consultas_no_periodo` ignora os novos status que liberam; exclusão da equipe não é bloqueada por consulta futura `desmarcada_profissional`.
- [ ] Implementar constante `STATUS_LIBERAM_HORARIO` (em `ausencias_service`, reusada por agenda_bp e pessoas_bp), trocar os `!= 'cancelada'` relevantes. Commit.

### Task 3: API de atendimento
Files: `backend/blueprints/agenda_bp.py` (ou `backend/atendimento_service.py` para as consultas puras), test `backend/tests/test_atendimento.py`.
- [ ] Testes (spec "Testes" backend): permissões GET/PUT (profissional da consulta 200; gestor 200; outro profissional, inclusive com agenda total, 403; secretária 403; outra clínica 403/404); sessão N por especialidade; histórico (só desfechos, mais recente primeiro, com descrição/observação/especialidade/profissional); atraso_dias (>1 dia, agendada/confirmada; finalizada → 0); PUT valida status e descrição; cria diário (consulta_id, paciente_id, observação, data_atendimento = data da consulta, autor); segunda gravação atualiza o mesmo e gera auditoria; falta sem texto não cria diário; família notificada só na criação; família vê o registro sem evolução/observação; listagem `/agenda` traz `diario_id`.
- [ ] Implementar. `_serializar_diario` passa a esconder `observacao` da família. Commit.

### Task 4: Front — status, cores, atraso
Files: `frontend/js/atendimento_util.js` (novo, puro), `frontend/tests/atendimento_util.test.js`, `frontend/index.html`, `frontend/css/tokens.css`, `frontend/js/views/agenda.js` (`STATUS_CONSULTA_INFO`, `renderConsultaLinha`).
- [ ] Node test de `diasDeAtraso({data_hora, status}, hojeChave)` (0 para desfecho/futuro/ontem; N para mais de 1 dia; aceita "9:00:00").
- [ ] Status novos e rótulos; tokens de cor. Commit.

### Task 5: Pop-up da consulta
Files: `frontend/js/views/agenda.js` (`abrirModalEditarConsulta`).
- [ ] Botão "▶ Atender"/"✏️ Ver/editar evolução" para gestor e profissional da consulta (não cancelada) → `#/<base>/atender/<id>`; faixa de atraso; secretária sem "Finalizado" no select.
- [ ] Browser: profissional, gestor, secretária. Commit.

### Task 6: Página Atender
Files: `frontend/js/views/atendimento.js` (novo), `frontend/js/app.js` (rotas), `frontend/index.html`, `frontend/css/components.css`.
- [ ] View conforme spec e prévia; salvar → toast e volta para a agenda; histórico em tabela com `overflow-x:auto`.
- [ ] Browser: atender, salvar Finalizado, reabrir (Ver/editar), falta justificada, histórico, faixa de atraso, celular. Commit.

### Task 7: Fechamento
- [ ] Suítes completas; CLAUDE.md (item `ad)`, seção 6 se couber, seção 7: 3b feita, migração pendente; próximos PRs: repetição avançada e ausências no Geral); revisão final (revisor novo); correções; PR. **Schema: perguntar antes de mesclar** e passar o SQL.
