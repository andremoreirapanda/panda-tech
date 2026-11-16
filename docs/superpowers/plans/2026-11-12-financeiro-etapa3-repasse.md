# Financeiro etapa 3 — Repasse aos profissionais — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O gestor define quanto cada profissional recebe por sessão, vê o relatório de atendimentos pagos e ainda não repassados, lança ajustes e marca o repasse como pago, com PDF e Excel.

**Architecture:** Regras puras em `repasse_regras.py` (qual regra vale, base, valor, liberação do pacote); `repasse_service.py` monta o relatório a partir das cobranças da etapa 1 (sem gravar nada) e grava o fechamento ao "marcar como pago" num `db.em_lote()`. A regra é aplicada no fechamento e o valor fica gravado na linha (`repasse_itens`); `UNIQUE(consulta_id)` impede pagar a mesma sessão duas vezes. Telas: regras na Equipe/Configurações e relatório em `#/gestor/financeiro/repasse`.

**Tech Stack:** Flask, SQLite (testes) / Postgres (produção), reportlab, JS puro, `frontend/js/vendor/xlsx.mini.min.js`.

**Spec:** `docs/superpowers/specs/2026-11-07-financeiro-clinica-design.md` — seção 6 (6.1 a 6.4), permissões na seção 3, restrições na seção 8.

## Global Constraints

- **Só gestor** (e `admin_master`) vê regras, configuração da base, relatório, ajustes e fechamentos; secretária, profissional e responsável → 403. **O profissional não vê nem o próprio repasse.** Módulo `financeiro` inativo → mesma resposta de `_org_financeiro_ou_erro`.
- Valores em centavos (inteiro); percentual guardado em **centésimos de ponto** (`6500` = 65,00%), de 0 a 10000.
- Datas da consulta são horário local; "hoje" = `ausencias_service.hoje_brasilia()`.
- Mudar regra ou base depois **não altera fechamento pago** (o valor fica gravado na linha).
- **Uma sessão nunca entra em dois fechamentos** (índice único em `repasse_itens.consulta_id`).
- Fechamento, ajuste e desfazer fechamento vão para a **auditoria**.
- Migração em `backend/migracoes/migracao_financeiro_repasse.sql` + `backend/migrar_financeiro_repasse.py`, idempotente, e as mesmas tabelas em `schema.sql` e `schema_postgres.sql`. Avisar o usuário do passo em produção.
- Nada de RLS (regra 2 do projeto); anotar as tabelas novas na lista de RLS da seção 7 do `CLAUDE.md`.
- Texto visível em português, nome **PandaUp** (`test_nome_pandaup.py`).
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Decisões (do construtor, para o usuário conferir)

1. **0% e R$ 0,00 são regras válidas**: servem para o dono da clínica que atende e não recebe repasse ("sem repasse"), sem cair no aviso "a definir".
2. **Quem é o profissional da sessão** = `consultas.profissional_id` (inclui gestor que atende).
3. **Estorno depois do repasse pago** → o sistema cria sozinho um **ajuste negativo pendente** (origem `estorno`) para aquele profissional, com o valor que foi repassado pelas sessões que deixaram de estar pagas; ele aparece no próximo relatório, e o gestor pode excluí-lo. Uma vez por sessão (não duplica).
4. **Desfazer fechamento** (só gestor, com motivo): apaga o fechamento e as linhas; as sessões voltam ao relatório; ajustes daquele fechamento voltam a pendentes. Para corrigir engano de clique.
5. **Período do relatório**: entram as sessões **pagas e não repassadas com data até o fim do período** (também de meses anteriores, como diz a spec); "aguardando pagamento" lista só as sessões **dentro do período**.
6. **Mensalidade sem cobrança do mês** (mês ainda não gerado ou cobrança cancelada) → a sessão fica "aguardando pagamento".
7. **Outros relatórios (6.5)** ficam para um plano próprio depois; este plano é só o repasse (6.1 a 6.4).

## Review Focus

1. Cobrança avulsa paga em parte → nenhuma sessão dela entra; ela aparece em "aguardando pagamento" (teste em Task 3).
2. Pacote de 10 sessões por R$ 1.000 com R$ 350 pagos → só as sessões 1 a 3 entram; a 4ª aguarda (teste em Task 2 e Task 3).
3. Mesma sessão em dois fechamentos ao mesmo tempo (dois cliques, duas abas) → o segundo dá 409 e nada é gravado (teste em Task 4).
4. Mudar a regra depois de marcar como pago → o fechamento antigo mantém os valores (teste em Task 4).
5. Pagamento estornado depois do repasse pago → aparece o ajuste negativo pendente no próximo relatório, uma vez só (teste em Task 4).

---

### Task 1: Banco — regras, base, fechamentos e ajustes

**Files:**
- Create: `backend/migracoes/migracao_financeiro_repasse.sql`, `backend/migrar_financeiro_repasse.py`
- Modify: `backend/schema.sql`, `backend/schema_postgres.sql`, `.github/workflows/tests.yml` (rodar a migração nova no job `smoke (Postgres)`, como a da etapa 1)
- Test: `backend/tests/test_financeiro_repasse_schema.py`

**Interfaces:**
- Produces (tabelas e colunas):
  - `organizacoes.fin_repasse_base TEXT NOT NULL DEFAULT 'procedimento'` — `'procedimento'` ou `'rateado'` (6.2).
  - `regras_repasse (id, organizacao_id, profissional_id, procedimento_id NULL, tipo_acordo NULL CHECK IN ('avulsa','mensalidade','pacote'), modo CHECK IN ('percentual','fixo'), percentual_centesimos INTEGER NULL, valor_centavos INTEGER NULL, atualizado_em, atualizado_por)`; índice único `(profissional_id, COALESCE(procedimento_id, 0), COALESCE(tipo_acordo, ''))`.
  - `repasses (id, organizacao_id, profissional_id, periodo_de, periodo_ate, total_sessoes_centavos, total_profissional_centavos, total_ajustes_centavos, a_pagar_centavos, quantidade, pago_em, pago_por, criado_em)`.
  - `repasse_itens (id, repasse_id REFERENCES repasses(id), consulta_id UNIQUE REFERENCES consultas(id), data_hora, paciente_nome, especialidade, descricao, sessao_numero NULL, sessao_total NULL, tipo_acordo NULL, base_centavos, regra_modo, regra_percentual_centesimos NULL, regra_valor_centavos NULL, profissional_centavos, clinica_centavos)`.
  - `repasse_ajustes (id, organizacao_id, profissional_id, repasse_id NULL REFERENCES repasses(id), descricao, valor_centavos /* com sinal */, origem CHECK IN ('manual','estorno'), consulta_id NULL, criado_por, criado_em)`; índice único parcial `(consulta_id) WHERE origem = 'estorno'`.
- Índices: `regras_repasse(organizacao_id, profissional_id)`, `repasses(organizacao_id, profissional_id)`, `repasse_ajustes(organizacao_id, profissional_id) WHERE repasse_id IS NULL` (SQLite aceita índice parcial).

- [ ] **Step 1: Testes que falham** — `test_financeiro_repasse_schema.py`: as colunas e tabelas existem no banco de teste; `fin_repasse_base` começa `'procedimento'`; inserir duas linhas em `repasse_itens` com o mesmo `consulta_id` dá `IntegrityError`; inserir dois ajustes `origem='estorno'` com o mesmo `consulta_id` dá `IntegrityError`, e dois `manual` sem consulta passam; a regra repetida para o mesmo `(profissional, procedimento, tipo)` (inclusive com os dois NULL) dá `IntegrityError`; `migrar_financeiro_repasse.migrar()` roda duas vezes num banco criado com o schema **anterior** (sem as tabelas) sem erro e termina com tudo criado.
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/test_financeiro_repasse_schema.py -q`.
- [ ] **Step 3: Implementar** a migração `.sql` (Postgres, `IF NOT EXISTS`) e o `migrar_*.py` no padrão de `migrar_financeiro_cobranca.py` (SQLite e Postgres, imprime `(SQLite)`/`(Postgres)` no fim); as tabelas nos dois schemas; o passo no CI.
- [ ] **Step 4: Rodar e ver passar** + `pytest tests/test_financeiro_cobranca_schema.py -q`.
- [ ] **Step 5: Commit** — `Financeiro: tabelas do repasse aos profissionais`.

### Task 2: Regras puras do repasse

**Files:**
- Create: `backend/repasse_regras.py`
- Test: `backend/tests/test_repasse_regras.py`

**Interfaces:**
- Produces (funções puras, sem banco):
  - `escolher_regra(regras: list[dict], procedimento_id: int | None, tipo_acordo: str | None) -> dict | None` — ordem **procedimento + tipo > procedimento > tipo > padrão** (padrão = os dois NULL).
  - `valor_profissional(regra: dict, base_centavos: int) -> int` — percentual: `round(base * percentual_centesimos / 10000)`; fixo: `valor_centavos` (ignora a base).
  - `bases_avulsa(itens: list[int], desconto: int) -> list[int]` — usa `cobranca_regras.ratear_desconto`.
  - `base_rateada_mensalidade(cobrado: int, sessoes_do_mes: int) -> int` — `cobrado // sessoes`, e a última sessão do mês leva o resto: expor também `rateio_igual(total: int, n: int) -> list[int]` (soma exata = total).
  - `pacote_liberadas(valor_pacote: int, sessoes_total: int, pago: int) -> int` — maior k com `pago >= k * valor_pacote / sessoes_total` (comparar em inteiros: `pago * sessoes_total >= k * valor_pacote`), entre 0 e `sessoes_total`.
  - `rotulo_regra(regra: dict) -> str` — `"65%"`, `"65,5%"`, `"R$ 80,00 fixo"`; `None` → `"a definir"`.

- [ ] **Step 1: Testes que falham**:
  - `escolher_regra`: com padrão 60%, tipo `pacote` 50%, procedimento 7 65%, procedimento 7 + `pacote` 70% → (7, `pacote`) = 70%; (7, `avulsa`) = 65%; (8, `pacote`) = 50%; (8, `avulsa`) = 60%; lista vazia → `None`; só exceções sem padrão e nenhuma bate → `None`.
  - `valor_profissional`: 6500 sobre 23000 → 14950; 6550 sobre 10001 → 6551 (arredonda); fixo 8000 sobre 23000 → 8000; 0% → 0.
  - `bases_avulsa([15000, 15000, 5000], 3500)` soma 31500 e respeita a proporção; sem desconto devolve igual.
  - `rateio_igual(100000, 3) == [33333, 33333, 33334]`; `rateio_igual(0, 2) == [0, 0]`.
  - `pacote_liberadas(100000, 10, 35000) == 3`; `(100000, 10, 0) == 0`; `(100000, 10, 100000) == 10`; `(100000, 3, 33334) == 1`; `(100000, 3, 33333) == 0`; pago acima do total → `sessoes_total`.
  - `rotulo_regra`.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `Financeiro: regras puras do repasse`.

### Task 3: Relatório de atendimentos (cálculo, sem gravar)

**Files:**
- Create: `backend/repasse_service.py`
- Test: `backend/tests/test_repasse_relatorio.py`

**Interfaces:**
- Consumes: Task 1 (tabelas), Task 2 (regras puras), `acordos_service.acordos_por_paciente` / `acordo_da_sessao` / `sessoes_que_contam`, `cobranca_regras.ratear_desconto`.
- Produces: `repasse_service.relatorio(org_id: int, de: str, ate: str, profissional_id: int | None = None, especialidade: str | None = None, hoje: str | None = None) -> dict`:
  ```
  {"de", "ate", "base": "procedimento"|"rateado",
   "profissionais": [{"profissional_id", "nome", "registro",   # "CRFa 2-12345" ou ""
      "sessoes": [{"consulta_id", "data_hora", "paciente_nome", "especialidade", "descricao",
                   "sessao_numero", "sessao_total", "tipo_acordo", "base_centavos",
                   "regra": {...} | None, "regra_rotulo", "profissional_centavos" | None,
                   "clinica_centavos" | None}],
      "por_especialidade": [{"especialidade", "quantidade", "base_centavos", "profissional_centavos"}],
      "ajustes": [{"id", "descricao", "valor_centavos", "origem"}],     # pendentes (repasse_id NULL)
      "total_sessoes_centavos", "total_profissional_centavos", "total_ajustes_centavos",
      "a_pagar_centavos", "sem_regra": bool}],
   "aguardando": [{"consulta_id", "data_hora", "paciente_nome", "profissional_nome", "motivo"}],
   "ja_pagas": [{"consulta_id", "pago_em", "repasse_id"}]}     # sessões do período já num fechamento
  ```
  e `repasse_service.validar_periodo(de, ate, hoje)` (padrão = **mês anterior** inteiro; reaproveitar `caixa_service.validar_periodo` para o formato e o limite de 1 ano).
- Regras do cálculo (spec 6.2/6.3, decisões 2, 5 e 6):
  - Sessão candidata: consulta da clínica com `status = 'realizada'`, ou `'faltou'` com `organizacoes.fin_repasse_falta = 1` **e** a falta cobrada (está num item de cobrança, no consumo do pacote ou coberta por mensalidade com `fin_cobrar_falta`); `data_hora` até `ate`; **sem** linha em `repasse_itens`.
  - **Avulsa** (está em `cobranca_itens`): paga quando a cobrança tem `status = 'pago'`; base = parte da sessão em `bases_avulsa` (itens da cobrança, desconto da cobrança). Item retirado da cobrança não existe → sessão não tem repasse (não aparece em nenhuma lista).
  - **Pacote** (está em `acordo_pacote_consumo`): pago do pacote = soma dos pagamentos **não estornados** das cobranças `tipo = 'pacote'` daquele acordo; sessão nº k paga quando `k <= pacote_liberadas(...)`. Base: `'procedimento'` → `procedimento_valor_centavos` da consulta; `'rateado'` → `rateio_igual(valor_do_pacote − descontos das parcelas, sessoes_total)[k-1]`.
  - **Mensalidade** (coberta por acordo `mensalidade` via `acordo_da_sessao`): paga quando a cobrança `tipo='mensalidade'` daquele acordo com `periodo_inicio` = 1º dia do mês da sessão tem `status = 'pago'`; sem essa cobrança → aguardando ("mensalidade do mês ainda não gerada"). Base: `'procedimento'` → valor do procedimento × (1 − desconto/valor da cobrança); `'rateado'` → `rateio_igual(valor − desconto da cobrança, sessões que contam daquele acordo no mês)` na ordem cronológica.
  - Regra: `escolher_regra` com as regras do profissional, `consultas.procedimento_id` e o tipo do acordo (avulsa sem acordo — decisão "valor" das pendências — conta como `avulsa`). Sem regra → `profissional_centavos = None`, `regra_rotulo = "a definir"`, `sem_regra = True` no profissional e o total dele soma só as sessões com regra.
  - `aguardando`: sessões candidatas **do período** (`de` a `ate`) ainda não pagas, com `motivo` ("Cobrança em aberto", "Pago em parte", "Pacote: pago até a sessão N", "Mensalidade de MM/AAAA em aberto", "Mensalidade do mês ainda não gerada", "Sessão sem acordo").
  - Filtros `profissional_id` e `especialidade` (compara com `cobranca_regras.mesma_especialidade`) valem para as três listas.
  - Ajustes pendentes do profissional entram no total: `a_pagar = total_profissional + total_ajustes` (pode ser negativo; a tela avisa).
  - Rode `cobranca_service.sincronizar(org_id)` **fora** de qualquer `em_lote` antes de calcular (como as outras telas).

- [ ] **Step 1: Testes que falham** (cenário próprio, no padrão de `test_cobranca_baixa._cenario`: clínica Pro, dois profissionais, procedimentos de R$ 230 e R$ 150, regras):
  - `test_avulsa_paga_entra_com_percentual` — 2 sessões de R$ 230 por consulta pagas, regra 65% → 2 linhas, `profissional_centavos == 14950` cada, `clinica_centavos == 8050`.
  - `test_avulsa_paga_em_parte_aguarda` — cobrança `parcial` → nada em `profissionais[...]["sessoes"]`, 1 em `aguardando` com motivo "Pago em parte".
  - `test_desconto_reduz_a_base` — cobrança mensal (período) com 3 sessões (230, 230, 150) e desconto de R$ 61 paga → bases somam 54900 e seguem a proporção.
  - `test_pacote_libera_na_ordem` — pacote 10 × R$ 1.000, R$ 350 pagos, 5 sessões feitas → só as nº 1–3 entram; nº 4 e 5 em `aguardando` ("Pacote: pago até a sessão 3"); base `'rateado'` = 10000 cada; base `'procedimento'` = valor do procedimento.
  - `test_mensalidade_paga_rateada` — mensalidade R$ 800 do mês paga, 4 sessões → base `'rateado'` 20000 cada; mês em aberto → todas aguardando.
  - `test_falta_so_com_as_duas_chaves` — falta cobrada com `fin_repasse_falta = 0` não entra; com 1 entra; falta não cobrada nunca.
  - `test_excecao_por_procedimento_vence_padrao` e `test_sem_regra_a_definir` (`sem_regra`, total só das com regra).
  - `test_pago_antes_do_periodo_entra_ate_o_fim` — sessão de 2 meses atrás paga agora entra no relatório do mês passado; sessão depois de `ate` não entra.
  - `test_filtros_profissional_e_especialidade`.
  - `test_outra_clinica_nunca_aparece`.
  - `test_validar_periodo_padrao_mes_anterior` — hoje 2026-11-12 → `("2026-10-01", "2026-10-31")`; janeiro → dezembro do ano anterior.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** (consultas por clínica, sem N+1: buscar de uma vez itens, cobranças, consumos, pagamentos e regras da clínica e agrupar em Python).
- [ ] **Step 4: Rodar e ver passar** + `tests/test_cobranca_sincronizar.py`.
- [ ] **Step 5: Commit** — `Financeiro: relatório de atendimentos do repasse`.

### Task 4: Fechar repasse, ajustes, desfazer e aviso de estorno

**Files:**
- Modify: `backend/repasse_service.py`, `backend/blueprints/financeiro_bp.py` (estorno manual), `backend/pagamento_service.py` (alerta de reversão do Mercado Pago)
- Test: `backend/tests/test_repasse_fechamento.py`

**Interfaces:**
- Produces:
  - `repasse_service.fechar(org_id, profissional_id, de, ate, consulta_ids: list[int], usuario) -> dict` — recalcula o relatório, confere que **as sessões enviadas são exatamente as liberadas desse profissional** (diferença → `ValueError("O relatório mudou. Atualize a página e confira de novo.")`, rota 409), recusa se alguma sessão não tem regra (`ValueError("Defina a regra de repasse de <nome> antes de marcar como pago.")`), grava `repasses` + `repasse_itens` + liga os ajustes pendentes (`repasse_id`) num `em_lote()`; `IntegrityError` no `UNIQUE(consulta_id)` → `ValueError` de "já foi incluída em outro repasse" (409). Auditoria `repasse_pago`.
  - `repasse_service.desfazer(org_id, repasse_id, motivo, usuario)` — motivo obrigatório; apaga itens e fechamento, solta os ajustes (`repasse_id = NULL`); auditoria `repasse_desfeito`.
  - `repasse_service.criar_ajuste(org_id, profissional_id, descricao, valor_centavos, usuario)` (descrição até 200, valor ≠ 0 com sinal, até ±R$ 100.000) e `excluir_ajuste(org_id, ajuste_id, usuario)` (só pendente).
  - `repasse_service.avisar_estorno(cobranca_id)` — para cada sessão da cobrança que está em `repasse_itens` e **deixou de estar paga** (pela mesma regra da Task 3), cria o ajuste `origem='estorno'`, `consulta_id`, valor `−profissional_centavos`, descrição "Estorno: <paciente> em DD/MM — já repassado em DD/MM"; ignora a duplicata (índice único) e notifica os gestores (tipo `cobranca_familia`). Chamada **depois** do commit do estorno manual (`estornar_pagamento`) e do alerta de reversão do Mercado Pago, em transação própria; falha nunca desfaz o estorno (`log_evento` `aviso_repasse_falhou`).
  - `repasse_service.listar_fechamentos(org_id, profissional_id=None) -> list` e `detalhe_fechamento(org_id, repasse_id) -> dict` (com itens e ajustes).

- [ ] **Step 1: Testes que falham**:
  - `test_fechar_grava_valores_e_tira_do_relatorio` — depois de fechar, as sessões saem do relatório e aparecem em `ja_pagas`; `a_pagar` gravado = itens + ajustes.
  - `test_mudar_regra_nao_muda_fechamento` — fecha com 65%, muda para 70%: `detalhe_fechamento` continua 65% e o valor antigo.
  - `test_relatorio_mudou_409` — enviar uma sessão a mais ou a menos → erro, nada gravado.
  - `test_sessao_sem_regra_bloqueia` e `test_dois_fechamentos_da_mesma_sessao` (simula corrida: insere o item antes do segundo `fechar` → 409, nada gravado, ajustes continuam pendentes).
  - `test_ajuste_entra_no_proximo_fechamento` e `test_excluir_ajuste_ja_fechado_409`.
  - `test_desfazer_devolve_sessoes_e_ajustes` (motivo obrigatório; auditoria).
  - `test_estorno_depois_do_repasse_vira_ajuste_negativo_uma_vez` — fecha, estorna o pagamento pela rota, roda `avisar_estorno` de novo → um ajuste só, de `−14950`; gestor notificado.
  - `test_estorno_antes_do_repasse_nao_gera_ajuste`.
  - `test_falha_no_aviso_nao_desfaz_estorno` (monkeypatch quebrando `criar_notificacao`).
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar e ver passar** + `tests/test_cobranca_baixa.py tests/test_financeiro_revisao_final.py`.
- [ ] **Step 5: Commit** — `Financeiro: fechar repasse, ajustes e aviso de estorno`.

### Task 5: Rotas, regras e PDF

**Files:**
- Create: `backend/repasse_pdf.py`
- Modify: `backend/blueprints/financeiro_bp.py`
- Test: `backend/tests/test_repasse_rotas.py`

**Interfaces:**
- Produces (todas `@login_required`, `@papel_required("gestor", "admin_master")`, `_org_financeiro_ou_erro()`):
  - `GET /api/financeiro/repasse/regras` → `{"base": ..., "profissionais": [{"id", "nome", "especialidade", "regras": [...]}], "procedimentos": [{"id", "nome", "valor_centavos"}]}` (profissionais = profissionais e gestores ativos da clínica, não excluídos).
  - `PUT /api/financeiro/repasse/regras/<profissional_id>` com `{"regras": [{"procedimento_id"|null, "tipo_acordo"|null, "modo", "percentual"|"valor_centavos"}]}` — substitui a lista do profissional; valida tudo antes (percentual 0–100 com até 2 casas, valor 0–R$ 100.000, procedimento da clínica, tipo válido, sem repetição, no máximo uma padrão); profissional de outra clínica → 404. Auditoria `regras_repasse`.
  - `PUT /api/financeiro/config` passa a aceitar `repasse_base` (`'procedimento'|'rateado'`; outro → 400) e o `GET` devolve.
  - `GET /api/financeiro/repasse?de&ate&profissional_id&especialidade` → `relatorio(...)`; período inválido → 400.
  - `GET /api/financeiro/repasse/pdf?de&ate&profissional_id` (profissional obrigatório no PDF) → PDF: logo, nome da clínica, "Relatório de atendimentos", período, emitido em, profissional (nome + registro), tabela das sessões (data/hora, paciente, procedimento/acordo, sessão N de M, especialidade, base, regra, profissional, clínica), totais por especialidade, ajustes, **valor a pagar** e linha de assinatura ("Assinatura do profissional" e data). Reaproveita `caixa_pdf._logo`, `_moeda`, `_data_hora`, `_tabela`.
  - `POST /api/financeiro/repasse/fechar` `{profissional_id, de, ate, consulta_ids}` → 201 `{repasse_id}`; erros de `fechar` → 409.
  - `GET /api/financeiro/repasse/fechamentos?profissional_id=` e `GET /api/financeiro/repasse/fechamentos/<id>`; `GET /api/financeiro/repasse/fechamentos/<id>/pdf` (mesmo PDF, com "Pago em DD/MM/AAAA").
  - `POST /api/financeiro/repasse/fechamentos/<id>/desfazer` `{motivo}`.
  - `POST /api/financeiro/repasse/ajustes` `{profissional_id, descricao, valor_centavos}` → 201; `DELETE /api/financeiro/repasse/ajustes/<id>`.

- [ ] **Step 1: Testes que falham**: `test_so_gestor` (cada rota: secretária, profissional — inclusive o próprio repasse — e responsável → 403); `test_sem_modulo_403`; `test_outra_clinica_404` (regras, fechamento, ajuste, PDF de fechamento de outra clínica); `test_salvar_regras_valida` (percentual 100,01 → 400; dois padrões → 400; procedimento de outra clínica → 400; nada gravado); `test_config_repasse_base`; `test_pdf_relatorio_e_fechamento` (`%PDF`, com e sem logo, com registro do conselho); `test_fechar_pela_rota_e_desfazer`.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar e ver passar** + `tests/test_financeiro_caixa.py tests/test_cobranca_listagens.py tests/test_nome_pandaup.py`.
- [ ] **Step 5: Commit** — `Financeiro: rotas e PDF do repasse`.

### Task 6: Telas, Excel e documentação

**Files:**
- Create: `frontend/js/views/financeiro_repasse.js`
- Modify: `frontend/js/financeiro_util.js` (funções puras), `frontend/js/views/financeiro.js` (botão "💼 Repasse aos profissionais" ao lado do "Fechamento de caixa", e o campo da base em Configurações → Financeiro), `frontend/js/app.js` (rotas), `frontend/index.html`, `CLAUDE.md`
- Test: `frontend/tests/financeiro_util.test.js`

**Interfaces:**
- Produces:
  - `financeiro_util.lerPercentual(texto) -> number | null` (`"65"`, `"65,5"`, `"65.50"` → 6500/6550; vazio, negativo, > 100 ou 3 casas → `null`) e `rotuloRegraRepasse(regra) -> string` (igual ao `rotulo_regra` do backend).
  - `financeiro_util.planilhaRepasse(dadosDoProfissional, de, ate) -> any[][]` — cabeçalho `["Data/hora", "Paciente", "Procedimento/Acordo", "Sessão", "Especialidade", "Base (R$)", "Regra", "Profissional (R$)", "Clínica (R$)"]`, uma linha por sessão (valores em reais como número; "a definir" vira célula vazia), depois uma linha em branco, os ajustes (`["Ajuste", descrição, ..., valor]`) e `["Valor a pagar", ..., a_pagar]`.
  - `viewRepasseGestor(app)` → `#/gestor/financeiro/repasse`: filtros (período, padrão mês anterior; profissional ou todos; especialidade), um cartão por profissional (sessões, totais por especialidade, ajustes com "+ Ajuste" e 🗑️, aviso "a definir" com link para as regras, **a pagar**, botões "📄 PDF", "📊 Excel" e **"Marcar como pago"** com confirmação mostrando o valor), lista "Aguardando pagamento da família" (recolhida) e "Já pagas"; aba/cartão "Fechamentos pagos" com ver PDF e "Desfazer" (pede motivo).
  - Regras: `viewRegrasRepasse(app)` → `#/gestor/financeiro/repasse/regras`: um cartão por profissional com a regra padrão (% ou valor fixo) e as exceções (procedimento e/ou tipo de acordo), salvar por profissional. Link a partir do relatório e da Equipe (botão "💼 Repasse" na linha do profissional, só gestor).
- Pop-ups de dinheiro com `data-modal-preparado` (fora do rascunho automático), como os da etapa 1. Datas pela `formatarDataHoraLocal`.

- [ ] **Step 1: Testes que falham** em `financeiro_util.test.js`: `lerPercentual` (casos acima), `rotuloRegraRepasse` (`65%`, `65,5%`, `R$ 80,00 fixo`, `a definir`) e `planilhaRepasse` (cabeçalho, linha com 149,5 e "65%", sessão sem regra com célula vazia, ajuste negativo e a linha "Valor a pagar").
- [ ] **Step 2: Rodar e ver falhar** — `node --test frontend/tests/financeiro_util.test.js`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Verificar**
  - `node --test frontend/tests/*.test.js` e a suíte completa do backend passam.
  - Navegador (banco do `seed.py` + `migrar_financeiro_cobranca.py` + `migrar_financeiro_repasse.py`): gestor define 65% padrão e 70% numa exceção; cria acordo avulsa por consulta, finaliza 2 sessões, dá baixa → as 2 aparecem no relatório com os valores; lança um ajuste; baixa PDF e Excel; marca como pago → somem e aparecem em "Fechamentos pagos"; estorna um pagamento → ajuste negativo aparece; desfaz o fechamento. Secretária e profissional não veem botão nem rota. Sem erro no console.
  - `CLAUDE.md`: item **5ax** (o que foi feito, decisões 1–7, passo manual da migração em produção), linha na tabela da seção 8, seção 7 com a etapa 3 feita e 6.5 pendente, e as tabelas novas na lista de RLS.
- [ ] **Step 5: Commit** — `Financeiro: telas do repasse aos profissionais`.
