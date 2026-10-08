# Planos por especialidade (parte 3c) — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vários planos ativos por criança, um por especialidade; criança e família veem todas as missões numa lista com etiqueta da especialidade.

**Architecture:** `planos_terapeuticos.especialidade` + regra "um ativo por (jornada, especialidade)". O bundle da ficha troca `plano_ativo`/`objetivos` por `planos_ativos` (cada um com objetivos, missões e progresso) e passa a mandar em `missoes` todas as missões com `plano_especialidade`. Os consumidores de "plano ativo" (gamificação, painel do profissional, ICT, PDF) passam a somar todos os planos ativos. No front, cartões por plano, select de especialidade e etiquetas.

**Tech Stack:** Flask + SQLite/Postgres; JS puro; pytest; node --test.

**Spec:** `docs/superpowers/specs/2026-10-08-planos-por-especialidade-design.md`

## Global Constraints

- Windows: `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q <arquivo>` em `backend/`; `node --test frontend/tests/*.test.js` na raiz.
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Especialidade: texto obrigatório, até 60 caracteres; "Geral" quando não há nenhuma.
- Permissão de editar plano/missão: `paciente_editavel` (sem mudança).
- Família nunca vê missão `rascunho`.

## Review Focus

1. **Plano criado com especialidade igual mas grafia diferente** ("fonoaudiologia" vs "Fonoaudiologia") — o select evita; o backend compara exato. Teste: duas grafias → dois planos (documentado), não erro 500.
2. **Medalha "Semana Completa" com um plano concluído e outro pendente** — não concede. Teste na Task 4.
3. **Família não vê rascunho de nenhum plano.** Teste na Task 3.
4. **Plano de outra jornada/clínica não entra no bundle.** Teste na Task 3.
5. **Paciente com jornada mas sem plano ativo** — bundle com `planos_ativos: []`, `missoes: []`, progresso 0, sem erro. Teste na Task 3.

---

### Task 1: Schema, migração e seed
**Files:** `backend/schema.sql`, `backend/schema_postgres.sql` (`planos_terapeuticos`), `backend/migracoes/migracao_planos_especialidade.sql` (novo), `backend/migrar_planos_especialidade.py` (novo), `backend/seed.py` (INSERT de planos com a especialidade do profissional), Test `backend/tests/test_planos_especialidade_schema.py`.
- [ ] Teste: coluna existe; migração (SQLite) preenche com `usuarios.especialidade` do criador e "Geral" quando vazia; idempotente ("já existia").
- [ ] SQL Postgres:
```sql
ALTER TABLE planos_terapeuticos ADD COLUMN IF NOT EXISTS especialidade TEXT;
UPDATE planos_terapeuticos p SET especialidade = COALESCE(NULLIF(TRIM(u.especialidade), ''), 'Geral')
  FROM usuarios u WHERE u.id = p.profissional_id AND p.especialidade IS NULL;
UPDATE planos_terapeuticos SET especialidade = 'Geral' WHERE especialidade IS NULL;
```
- [ ] Implementar, rodar, commit "Planos: coluna especialidade (schema + migração)".

### Task 2: Criar plano / iniciar jornada com especialidade; especialidades disponíveis
**Files:** `backend/blueprints/jornada_bp.py` (`criar_plano`, `_validar_inicio`, `iniciar_jornada`, helper novo), Test `backend/tests/test_planos_especialidade.py`.
**Produces:** `especialidades_disponiveis(organizacao_id) -> list[str]`; `_validar_especialidade(valor) -> (str|None, erro|None)`.
- [ ] Testes: criar plano sem especialidade → 400; com > 60 → 400; dois planos de especialidades diferentes ficam ambos `ativo`; novo plano da mesma especialidade encerra só aquele; "fonoaudiologia" e "Fonoaudiologia" são especialidades distintas (dois ativos, sem erro); iniciar jornada sem especialidade → 400 (nada criado) e com ela grava no plano; `especialidades_disponiveis` = clínica ∪ profissionais ativos não excluídos, ordenado, sem repetir, `["Geral"]` se vazio, e não inclui profissional de outra clínica.
- [ ] Implementar: `criar_plano` valida título/objetivos como hoje + especialidade, `UPDATE ... SET status='encerrado' WHERE jornada_id = ? AND status='ativo' AND especialidade = ?`; INSERT com especialidade. `_validar_inicio` exige especialidade; `iniciar_jornada` grava. Commit "Planos: especialidade obrigatória e um ativo por especialidade".

### Task 3: Bundle com vários planos
**Files:** `backend/blueprints/jornada_bp.py` (`_montar_bundle_jornada`), Test `backend/tests/test_planos_especialidade.py`.
- [ ] Testes: dois planos → `planos_ativos` com 2 itens (cada um com `objetivos`, `missoes`, `progresso_pct`, `missoes_concluidas`, `missoes_total`), `missoes` com as missões dos dois e `plano_especialidade` em cada; progresso total somado; família não recebe rascunho de nenhum plano; plano encerrado não entra; sem plano ativo → `planos_ativos == []`, `missoes == []`, `progresso_pct == 0`; `especialidades_disponiveis` presente com e sem jornada; `feedbacks` de missões dos dois planos.
- [ ] Implementar: função `_missoes_do_plano(plano_id)` (SQL atual + filtro da família + atividades/dias), loop nos planos ativos `ORDER BY id`, montar estrutura; remover `plano_ativo`/`objetivos`. Rodar também `test_idor_jornada.py`, `test_pandoo_missao.py`, `test_missao_frequencia_prazo_02_09_2026.py` e qualquer teste que leia `plano_ativo` (`grep -rn plano_ativo backend/tests`), ajustando-os para `planos_ativos`. Commit "Ficha: vários planos ativos no bundle".

### Task 4: Gamificação, painel do profissional, ICT e PDF somam os planos
**Files:** `backend/gamificacao_service.py` (~119), `backend/blueprints/indicadores_bp.py` (~120), `backend/ict_service.py` (~33), `backend/relatorio_service.py` (seção do plano), Tests no mesmo arquivo de testes.
- [ ] Testes: "Semana Completa" não é concedida com um plano concluído e outro pendente, e é concedida quando os dois estão concluídos (chame a função de gamificação que processa missão concluída, ou conclua via rota `/jornada/missao/<id>/concluir` como responsável); painel do profissional soma missões dos dois planos (`progresso_pct`); ICT adesão conta missões dos dois planos; PDF (monkeypatch em `SimpleDocTemplate.build`, como em `test_diario_por_paciente.py`) tem um título por plano com a especialidade.
- [ ] Implementar com `WHERE plano_id IN (SELECT pt.id FROM planos_terapeuticos pt JOIN jornadas j ON j.id = pt.jornada_id WHERE j.paciente_id = ? AND pt.status = 'ativo')`; PDF itera `dados["planos_ativos"]` ("Plano: <título> · <especialidade>"). Commit "Planos: medalha, painel, ICT e PDF consideram todos os planos ativos".

### Task 5: Front — etiqueta, cartões por plano e pop-ups com select
**Files:** `frontend/js/especialidades.js` (novo, puro + `module.exports`), `frontend/tests/especialidades.test.js`, `frontend/index.html`, `frontend/js/views/jornada.js`.
**Produces:** `etiquetaEspecialidade(esp, curta=false) -> string` (ícone de `ICONES_ESPECIALIDADE` ou "🩺" + nome; curta: "Fonoaudiologia"→"Fono", "Terapia Ocupacional"→"TO", "Psicopedagogia"→"Psicoped.", "Psicologia"→"Psico", "Fisioterapia"→"Fisio", senão primeira palavra); `opcoesEspecialidade(lista, minha) -> {opcoes, selecionada}`.
- [ ] Teste Node das duas funções (inclui especialidade desconhecida e lista vazia → ["Geral"]).
- [ ] Implementar `especialidades.js` (mover `ICONES_ESPECIALIDADE` para lá ou ler o global de `util.js` com reserva no Node; registre a escolha no ledger).
- [ ] `jornada.js`: `renderJornadaConteudoPrincipal` → um cartão por `planos_ativos` (título, etiqueta completa, progresso, missões via `renderListaMissoesFicha(p.missoes, ...)`, botão `.btn-nova-missao-plano[data-plano]`); "+ Novo plano" (`btn-novo-plano`) abaixo; sem planos, o cartão vazio atual. Eventos: nova/editar missão usam o plano da missão (`m.plano_id`). Pop-ups "Novo plano" e "Iniciar jornada" com `<select>` de especialidade (`dados.especialidades_disponiveis`, pré-seleção = `Sessao.usuario.especialidade`) e, no "Novo plano", aviso dinâmico quando a especialidade já tem plano ativo. Enviar `especialidade`.
- [ ] Browser: ficha com dois planos, aviso, criar missão no plano certo. Commit "Ficha: um cartão por plano e especialidade nos pop-ups".

### Task 6: Front — etiquetas na criança e na família
**Files:** `frontend/js/views/crianca.js`, `frontend/js/views/responsavel.js`, CSS em `frontend/css/components.css` (`.etiqueta-esp`).
- [ ] Na criança: abaixo do título da missão, `<span class="etiqueta-esp">${escapeHtml(etiquetaEspecialidade(m.plano_especialidade, true))}</span>` quando houver especialidade. Na família: mesma etiqueta com nome completo.
- [ ] Browser como Ana (família) e no modo criança. Commit "Missões: etiqueta da especialidade para criança e família".

### Task 7: Fechamento
- [ ] Suítes completas, Playwright de fumaça, apagar `.playwright-mcp/`.
- [ ] CLAUDE.md: item `aa)` na seção 5 (e anotar que a migração da 3a foi aplicada), seção 7 (3c feita, migração pendente; próxima é a 3b — Atender), seção 6 ("Planos e especialidade": bundle `planos_ativos`).
- [ ] Revisão final (revisor novo), correções com teste, push, PR. **Schema: perguntar antes de mesclar** e passar o SQL.
