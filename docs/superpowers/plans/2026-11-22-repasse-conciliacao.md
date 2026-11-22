# Repasse — conciliação automática das sessões já repassadas — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** As três decisões do usuário de 22/11/2026 sobre o repasse (etapa 3 do Financeiro, já em `main`): (1) mensalidade com base "valor do procedimento" nunca repassa mais que o líquido do mês; (2) sessão paga de novo depois de um estorno é recreditada sozinha; (3) sessão que deixa de contar (vira falta sem repasse, desmarcada, cancelada) depois de repassada gera o ajuste negativo sozinha — e volta, se a sessão voltar a contar.

**Architecture:** Uma única função de conciliação em `repasse_service` substitui o `avisar_estorno`: para cada sessão já repassada, calcula o **alvo** (0 se a sessão conta e está paga; −valor do profissional se não) e o **atual** (soma dos ajustes automáticos dela) e cria/apaga ajustes até o atual bater com o alvo. Roda depois de estorno, de baixa, de mudança de status da consulta, ao abrir o relatório e antes de fechar. Sessão que deixou de contar não ocupa mais a vaga do pacote nem a parte da mensalidade.

**Tech Stack:** Flask, SQLite (testes) / Postgres (produção), JS puro.

**Spec:** `docs/superpowers/specs/2026-11-07-financeiro-clinica-design.md` seção 6 + decisões do usuário de 22/11/2026 (registradas no `CLAUDE.md`, item 5ax, "decisões pendentes" → resolvidas: as três "sim").

## Global Constraints

- Só gestor vê repasse e ajustes; profissional nunca. Valores em centavos.
- Nunca repassar mais que o líquido cobrado (pacote, mensalidade rateada **e agora mensalidade por procedimento**).
- Uma sessão nunca é repassada duas vezes (`repasse_itens.consulta_id` único — não muda).
- Ajuste de conciliação **pendente** que perde o motivo é **apagado** (não vira par +/−); ajuste **já usado num fechamento** é compensado por um novo ajuste de sinal contrário. Ajuste **dispensado** pelo gestor conta como aplicado (não gera outro) e é apagado se o motivo acabar.
- A conciliação nunca derruba quem a chamou (estorno, baixa, status, relatório): falha vira `log_evento` `aviso_repasse_falhou`.
- Gestores notificados (tipo `cobranca_familia`) só quando a conciliação **cria** ajuste.
- Migração nova `backend/migracoes/migracao_repasse_conciliacao.sql` + `backend/migrar_repasse_conciliacao.py`, idempotente, mais os dois schemas. **Produção já tem a migração do repasse aplicada** — esta é outra, e precisa rodar antes do deploy.
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Decisões (do construtor)

1. Origens dos ajustes: `manual`, `estorno` (família deixou de pagar), `status` (sessão deixou de contar) e `recredito` (positivo, desfaz um `estorno`/`status` já usado num fechamento). Rótulos na tela: "Manual", "Estorno", "Sessão desmarcada/falta", "Recrédito".
2. "Sessão conta" = `_repassavel` com o status **atual** (realizada; faltou só com `fin_repasse_falta` e falta cobrada). Status que não estão no relatório (cancelada, desmarcadas, falta justificada) não contam.
3. Sessão repassada que não conta mais sai do "já repassado" do pacote (libera a vaga) e da mensalidade (libera a parte do mês). Sessão que conta mas não está paga (estorno) continua ocupando.
4. Dispensa: um ajuste dispensado continua contando no "atual" (o gestor decidiu não cobrar); se o motivo acabar, ele é apagado e nada novo é criado.

## Review Focus

1. Estorno → ajuste −v; família paga de novo antes do próximo fechamento → o ajuste some (teste em Task 2).
2. Estorno → fechamento desconta −v → família paga de novo → ajuste +v "Recrédito" (teste em Task 2).
3. Sessão de pacote repassada vira falta sem repasse → −v e a vaga é liberada para a próxima sessão paga; volta a ser finalizada → o −v pendente some e a vaga volta (teste em Task 2).
4. Conciliar duas vezes seguidas não cria nada na segunda (idempotente), inclusive com ajuste dispensado (teste em Task 2).
5. Mensalidade por procedimento: 8 sessões de R$ 150 num mês de R$ 600 pago → soma das bases = R$ 600 (teste em Task 2).

---

### Task 1: Banco — origens novas e índice

**Files:** Create `backend/migracoes/migracao_repasse_conciliacao.sql`, `backend/migrar_repasse_conciliacao.py`; Modify `backend/schema.sql`, `backend/schema_postgres.sql`, `.github/workflows/tests.yml` (rodar o `.sql` novo no smoke Postgres, depois do do repasse); Test `backend/tests/test_financeiro_repasse_schema.py`.

**Interfaces — Produces:**
- `repasse_ajustes.origem` aceita `'manual','estorno','status','recredito'` (Postgres: `DROP CONSTRAINT IF EXISTS repasse_ajustes_origem_check` + `ADD CONSTRAINT ... CHECK (...)`; SQLite: recriar a tabela no `migrar_*.py` preservando as linhas, como `migrar_financeiro_cobranca.py` faz com `cobrancas`).
- Sai o índice único `idx_ajuste_estorno_consulta`; entra `idx_ajuste_consulta` (não único) em `repasse_ajustes(consulta_id)`.

- [ ] Testes que falham: inserir origem `status` e `recredito` passa, `outra` falha; dois ajustes `estorno` da mesma sessão passam; `migrar()` duas vezes num banco com a estrutura **anterior** (com o índice único e o CHECK antigo, com linhas) não perde linhas.
- [ ] Ver falhar → implementar → ver passar (`tests/test_financeiro_repasse_schema.py`) → commit `Financeiro: origens novas dos ajustes do repasse`.

### Task 2: Conciliação, teto da mensalidade e ganchos

**Files:** Modify `backend/repasse_service.py`, `backend/blueprints/financeiro_bp.py` (estorno e baixa), `backend/pagamento_service.py` (webhook aprovado e reversão), `backend/blueprints/agenda_bp.py` (mudança de status, Atender e edição da consulta); Test `backend/tests/test_repasse_conciliacao.py` (novo) e os existentes de repasse.

**Interfaces — Produces:**
- `repasse_service.conciliar(org_id, consulta_ids=None, origem_evento="", entidade=None, entidade_id=None) -> int` — concilia as sessões já repassadas da clínica (todas, ou só as dadas); devolve quantos ajustes criou ou apagou. Nunca levanta exceção. Trava a linha de `repasse_itens` da sessão (`SELECT ... FOR UPDATE` no Postgres, como `_travar_cobranca`) dentro de um `em_lote()` **por sessão**.
- Alvo por sessão: `0` se conta (decisão 2) **e** está paga (regra atual de `_avaliar`, base 'procedimento'); senão `−profissional_centavos` do item. Origem do negativo: `status` se não conta, `estorno` se conta mas não está paga.
- Atual = soma de **todos** os ajustes `estorno`/`status`/`recredito` da sessão (inclusive dispensados).
- Para chegar ao alvo: primeiro apaga ajustes **pendentes** (não usados em fechamento) cuja remoção aproxima do alvo; o que faltar vira um ajuste novo pendente (`recredito` se positivo; `estorno`/`status` se negativo).
- `avisar_estorno` e `avisar_estorno_das_sessoes` passam a chamar `conciliar` (manter os nomes como atalhos, para não mexer em quem chama).
- Ganchos depois do commit, em transação própria: estorno manual, baixa manual (`/pagar`), webhook aprovado e reversão do Mercado Pago (as cobranças da sessão), mudança de status em `agenda_bp` (rota de status, Atender, edição/arrastar, exclusão não — já bloqueada). Também no começo de `relatorio` (só gestor chama) e de `fechar`, para a tela sempre refletir o estado.
- `_repassados`: sessão repassada que **não conta** (decisão 2) não entra no "já repassado" do pacote (contagem e bases) nem da mensalidade.
- `_bases_mensalidades` com base `procedimento`: as bases das pendentes, em ordem cronológica, limitadas a `max(0, líquido − já repassado do acordo/mês − bases já dadas nesta rodada)`.
- Notificação: uma por chamada que **criou** ajuste, com o total; "Recrédito" no texto quando for positivo.

- [ ] Testes que falham (todos com números): os 5 do Review Focus; dispensar um `estorno` e a família pagar de novo → o dispensado é apagado e nada é criado; estorno → fechamento → pago de novo → estornado de novo → novo −v (não fica travado pelo índice); mudança de status pela rota da agenda dispara a conciliação; falha na conciliação não derruba a baixa nem o status; outra clínica nunca é tocada; os testes atuais de estorno continuam passando (ajustar só o que mudou de propósito: o índice único saiu).
- [ ] Ver falhar → implementar → ver passar: `tests/test_repasse_*.py tests/test_cobranca_baixa.py tests/test_financeiro_revisao_final.py tests/test_agenda*.py`; suíte completa uma vez → commit `Financeiro: conciliação automática do repasse e teto da mensalidade`.

### Task 3: Tela, PDF/Excel e documentação

**Files:** Modify `frontend/js/views/financeiro_repasse.js`, `frontend/js/financeiro_util.js` (rótulo da origem), `backend/repasse_pdf.py`, `CLAUDE.md`; Test `frontend/tests/financeiro_util.test.js`.

- [ ] `rotuloOrigemAjuste(origem)` → "Manual" | "Estorno" | "Sessão desmarcada/falta" | "Recrédito" (teste); a lista de ajustes e o PDF mostram o rótulo; o botão de excluir diz "Dispensar" para os automáticos e "Excluir" para o manual.
- [ ] `CLAUDE.md` item 5ax: as três decisões resolvidas, a conciliação, as origens, a migração nova e o passo em produção (rodar `migracao_repasse_conciliacao.sql` antes do `git pull`).
- [ ] `node --test frontend/tests/*.test.js`, `node --check`, suíte do backend → commit `Financeiro: rótulos da conciliação do repasse`.
