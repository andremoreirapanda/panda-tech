# Financeiro — outros relatórios (6.5) — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar o Financeiro com os relatórios da seção 6.5: extrato do paciente em PDF e Excel (sessão por sessão) e, numa página de Relatórios, cobranças em aberto e vencidas, pacotes e mensalidades acabando e sessões sem acordo, todos com Excel.

**Architecture:** Só leitura sobre o que a etapa 1 grava. `relatorios_service.py` monta os dados (reaproveitando `acordos_service`, `cobranca_service.pendencias` e a classificação das sessões); `extrato_pdf.py` gera o PDF no padrão de `caixa_pdf.py`; o Excel é montado no navegador (`financeiro_util` + `carregarBibliotecaExcel`). Sem migração.

**Tech Stack:** Flask, reportlab, JS puro, SheetJS (`frontend/js/vendor/xlsx.mini.min.js`).

**Spec:** `docs/superpowers/specs/2026-11-07-financeiro-clinica-design.md` seção 6.5 + decisões do usuário de 23/11/2026: (1) o extrato mostra as **sessões uma a uma** (data, procedimento e valor); (2) a **secretária pode baixar** o PDF do extrato.

## Global Constraints

- **Extrato do paciente**: gestor, secretária e admin da clínica do paciente; profissional e responsável → 403; paciente de outra clínica → 404. Módulo `financeiro` inativo → resposta de `_org_financeiro_ou_erro`.
- **Página de Relatórios** (os outros três): **só gestor** (e admin) → `#/gestor/financeiro/relatorios`.
- O extrato **nunca** mostra repasse, regra do profissional, observação interna da cobrança (`revisar_motivo`) nem texto clínico — é um documento para entregar à família.
- Valores em centavos; datas de consulta em horário local (`formatarDataHoraLocal` no front); "hoje" = `ausencias_service.hoje_brasilia()`.
- Período: padrão do extrato = **últimos 3 meses até hoje**; demais relatórios conforme cada task; limite de 1 ano (`caixa_service.validar_periodo`).
- Rodar `cobranca_service.sincronizar(org)` antes de montar (fora de `em_lote`), como as outras telas.
- Texto em português, produto PandaUp. Commits com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Decisões (do construtor)

1. Situação de cada sessão no extrato: "Cobrança: <descrição>" (avulsa, com o status dela), "Pacote: sessão N de M", "Mensalidade MM/AAAA", "Sem acordo" ou "Não cobrada" (decisão "não cobrar" ou antes da data de corte). Valor da sessão = valor no item da cobrança, senão o valor do procedimento no dia (rótulo "valor de referência" quando coberta por pacote/mensalidade).
2. Entram no extrato as sessões **realizadas** e as **faltas cobradas** do período (as que geram cobrança); as cobranças do período por vencimento (sem rascunho nem cancelada) e os pagamentos do período (estornados aparecem marcados e não somam).
3. Totais do extrato: cobrado (a pagar das cobranças do período), pago no período e **saldo em aberto hoje** do paciente (todas as cobranças abertas, de qualquer período).
4. "Pacotes acabando": restantes ≤ N (padrão 2, escolhível 0–5); "mensalidades terminando": `fim` dentro do período escolhido (padrão: mês atual e o próximo).

## Review Focus

1. Paciente de outra clínica no extrato (id na URL) → 404, inclusive para a secretária (teste em Task 1).
2. Sessão coberta por mensalidade/pacote não pode somar duas vezes no "cobrado" (o cobrado vem das cobranças, não das sessões) (teste em Task 1).
3. Pagamento estornado aparece riscado/marcado e não entra no "pago" (teste em Task 1).
4. Período sem nada → PDF e Excel com "Nenhum…" e totais zerados, sem erro (Tasks 1 e 3).
5. Nome de paciente/descrição com `<`, `&` → escapado no PDF e na tela (Tasks 1 e 3).

---

### Task 1: Extrato do paciente (dados, rota e PDF)

**Files:** Create `backend/relatorios_service.py`, `backend/extrato_pdf.py`, `backend/tests/test_extrato_paciente.py`; Modify `backend/blueprints/financeiro_bp.py`.

**Interfaces — Produces:**
- `relatorios_service.extrato_paciente(org_id, paciente_id, de, ate, hoje=None) -> dict`:
  `{"paciente": {"id","nome","nascimento"}, "de","ate", "sessoes": [{"consulta_id","data_hora","especialidade","profissional_nome","procedimento_nome","valor_centavos","situacao"}], "cobrancas": [{"id","descricao","vencimento","status","a_pagar_centavos","pago_centavos","saldo_centavos"}], "pagamentos": [{"id","pago_em","forma","valor_centavos","cobranca_descricao","estornado": bool}], "totais": {"cobrado_centavos","pago_centavos","saldo_aberto_centavos"}}`.
- `GET /api/financeiro/paciente/<id>/extrato?de&ate` (JSON) e `GET /api/financeiro/paciente/<id>/extrato/pdf?de&ate` (PDF `extrato-<nome-sem-acento>-<de>-a-<ate>.pdf`): `@login_required`, `@papel_required("gestor","secretaria","admin_master")`, paciente da clínica (404 se não), `_org_financeiro_ou_erro`.
- `extrato_pdf.gerar_extrato_pdf(dados, clinica_nome, logo_base64, emitido_em) -> bytes`: logo, clínica, "Extrato financeiro", paciente, período, emitido em; tabelas Sessões, Cobranças, Pagamentos; quadro de totais; "Gerado pelo PandaUp". Reaproveita `caixa_pdf._logo/_moeda/_data/_data_hora/_tabela` e escapa texto.

- [ ] Testes que falham: avulsa por consulta com 2 sessões (uma paga, outra em aberto) + pacote com 3 sessões consumidas + mensalidade com 2 sessões → `sessoes` com 7 linhas e as situações da decisão 1; `cobrado` = soma dos a pagar das cobranças do período (sem dobrar as sessões); pagamento estornado marcado e fora do `pago`; `saldo_aberto` inclui cobrança vencida antes do período; secretária 200; profissional e responsável 403; outra clínica 404; sem módulo 403; período inválido 400; PDF começa com `%PDF`, sem e com logo, com nome `<b>&` escapado, período vazio; o JSON não traz `revisar_motivo` nem nada de repasse.
- [ ] Ver falhar → implementar → ver passar (`tests/test_extrato_paciente.py` + `tests/test_cobranca_listagens.py tests/test_nome_pandaup.py`) → commit `Financeiro: extrato do paciente em PDF`.

### Task 2: Relatórios da clínica (dados e rotas)

**Files:** Modify `backend/relatorios_service.py`, `backend/blueprints/financeiro_bp.py`; Create `backend/tests/test_relatorios_financeiro.py`.

**Interfaces — Produces** (todas `@papel_required("gestor","admin_master")` + `_org_financeiro_ou_erro`):
- `GET /api/financeiro/relatorios/em-aberto?especialidade=&paciente_id=` → `{"cobrancas": [{"id","paciente_id","paciente_nome","descricao","vencimento","status","a_pagar_centavos","pago_centavos","saldo_centavos","dias_atraso"}], "totais": {"em_aberto_centavos","vencido_centavos","quantidade"}}` — pendente/parcial/vencido (sem rascunho/cancelada), ordem por vencimento; `dias_atraso` = dias entre o vencimento e hoje (0 se não venceu).
- `GET /api/financeiro/relatorios/acabando?restantes=2&de=&ate=` → `{"pacotes": [...], "mensalidades": [...]}` (decisão 4), com paciente, especialidade, sessões total/usadas/restantes ou valor e fim.
- `GET /api/financeiro/relatorios/sem-acordo?de=&ate=&profissional_id=&especialidade=` → `{"sessoes": [{"consulta_id","data_hora","paciente_id","paciente_nome","profissional_nome","especialidade","procedimento_nome","valor_centavos"}], "totais": {"quantidade","valor_centavos"}}` — mesma definição de "sem acordo" das pendências (`acordos_service.sessoes_sem_acordo`), filtrada pelo período (padrão: mês atual).

- [ ] Testes que falham: cada relatório com números (inclui cobrança parcial com saldo, vencida com dias de atraso, rascunho fora); filtros; só gestor (secretária, profissional, responsável 403); outra clínica nunca aparece; sem módulo 403; período inválido 400.
- [ ] Ver falhar → implementar → ver passar (+ `tests/test_cobranca_listagens.py`) → suíte completa uma vez → commit `Financeiro: relatórios de cobranças em aberto, acabando e sem acordo`.

### Task 3: Telas, Excel e documentação

**Files:** Create `frontend/js/views/financeiro_relatorios.js`; Modify `frontend/js/financeiro_util.js` (+ testes), `frontend/js/views/financeiro_ficha.js` (botões do extrato), `frontend/js/views/financeiro.js` (botão "📑 Relatórios", só gestor), `frontend/js/app.js`, `frontend/index.html`, `CLAUDE.md`.

**Interfaces — Produces:**
- `financeiro_util.planilhasExtrato(dados) -> {Sessões, Cobranças, Pagamentos, Resumo}` e `planilhaRelatorio(tipo, dados) -> any[][]` (`tipo` = `"em-aberto"|"pacotes"|"mensalidades"|"sem-acordo"`), valores em reais como número, datas "DD/MM/AAAA" (ou "DD/MM/AAAA HH:MM"), cabeçalho na 1ª linha.
- Ficha do paciente (cartão Financeiro, gestor e secretária): período (padrão últimos 3 meses) + "📄 Extrato em PDF" (`Api.baixarArquivo`) + "📊 Excel".
- `viewRelatoriosFinanceiro(app)` em `#/gestor/financeiro/relatorios`: três cartões (Em aberto e vencidas; Pacotes e mensalidades acabando; Sessões sem acordo), cada um com seus filtros, tabela, totais, "Nenhum…" quando vazio, botão Excel e link para a ficha do paciente.

- [ ] Testes que falham (Node): `planilhasExtrato` (cabeçalhos, sessão com valor 150 em reais, estornado marcado, vazio só cabeçalho) e `planilhaRelatorio` para os 4 tipos.
- [ ] Ver falhar → implementar → `node --check`, `node --test frontend/tests/*.test.js`; navegador (gestor: Relatórios com os 3 cartões e Excel; ficha: PDF e Excel do extrato; secretária: extrato sim, Relatórios não) → `CLAUDE.md` item 5ay + tabela da seção 8 + seção 7 (Financeiro 6.5 feito) → commit `Financeiro: telas dos relatórios e do extrato`.
