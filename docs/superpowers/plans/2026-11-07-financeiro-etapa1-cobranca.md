# Financeiro — Etapa 1: Cobrança das famílias — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cada paciente ganha acordos de pagamento (avulsa por consulta/quinzenal/mensal, mensalidade, pacote); as cobranças nascem da agenda, a clínica dá baixa e a família vê o extrato.

**Architecture:** Regras puras de datas e valores em `backend/cobranca_regras.py` (sem banco). Um serviço `backend/cobranca_service.py` faz a sincronização idempotente agenda → cobranças, chamada ao abrir as telas do financeiro e por um script de cron opcional. As rotas ficam em `backend/blueprints/financeiro_bp.py` (amplia o atual). As telas ficam em `frontend/js/views/financeiro.js` (lista de cobranças e configuração), mais um cartão "Financeiro" na ficha (`frontend/js/views/financeiro_ficha.js`, usado pela ficha do gestor e pela da secretária), com funções puras em `frontend/js/financeiro_util.js`.

**Tech Stack:** Flask, SQLite (testes/local) e Postgres (produção), SPA em JS puro, pytest, `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-07-financeiro-clinica-design.md` (seções 3, 4 e 8; etapas 2 e 3 ficam para planos próprios).

## Global Constraints

- Valores sempre em **centavos (inteiro)**; arredondamento ao centavo com `round()` só no fim de cada conta.
- `consultas.data_hora` é horário **local**; "hoje" = `ausencias_service.hoje_brasilia()` (data de Brasília).
- Quem vê o quê (spec, seção 3): acordos e cobranças/baixa → **gestor, secretária e admin_master**; configuração do financeiro, estorno e pendências → **só gestor e admin_master**; profissional → nada; responsável → só o extrato dele (`financeiro_visivel_para_usuario`).
- Tudo exige o módulo `financeiro` ativo na clínica (`_financeiro_habilitado_para`, que já existe); outra clínica → 404 (não 403) nas rotas por id.
- Falta justificada, `desmarcada_profissional` e `cancelada` **nunca** geram cobrança; `faltou` só com `organizacoes.fin_cobrar_falta = 1`.
- Mudar acordo vale dali para frente; o que já virou cobrança não muda sozinho.
- Uma sessão entra em no máximo **uma** cobrança (índice único em `cobranca_itens.consulta_id`).
- Mensalidade de mês incompleto = `round(valor × dias_de_vigência_no_mês ÷ dias_do_mês)`.
- Vencimento de cobrança de período = fim do período + `vence_dias` (padrão **5**).
- Quinzena: dias **1–15** e **16–último dia** do mês.
- Sem RLS, sem criptografia de campo. Migração em `backend/migracoes/*.sql` + `backend/migrar_*.py`, segura para rodar de novo.
- Cobrança, liberação, baixa, estorno, "não cobrar" e mudança de acordo → `log_auditoria`.
- Textos de tela com o nome **PandaUp** quando citarem a plataforma (testes `test_nome_pandaup.py` / `nome_pandaup.test.js`).
- Toda mensagem de commit termina com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Rodar testes: `cd backend && PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q` e `node --test frontend/tests/*.test.js`.

## Review Focus

1. **Sessão muda de status depois de cobrada** (finalizada → falta justificada; falta → finalizada): o item sai de cobrança ainda não paga; numa cobrança paga ou parcial gera o aviso "revisar", nunca altera valor pago. Teste em Task 4 (`test_status_volta_atras_*`).
2. **Duas sincronizações seguidas ou simultâneas** não duplicam cobrança nem item (índice único + `em_lote`). Teste em Task 4 (`test_sincronizar_duas_vezes_nao_duplica`).
3. **Paciente com acordo "todas" e outro específico**: a consulta vai para o específico. Teste em Task 2 (`test_acordo_especifico_vence_todas`) e Task 4.
4. **Responsável vendo rascunho ou cobrança de outro paciente**: rascunho e cancelada nunca aparecem para a família; IDOR entre clínicas e entre pacientes → 404/403. Teste em Task 6 (`test_familia_nao_ve_rascunho`, `test_idor_cobranca_outra_clinica`).
5. **Pacote acabou**: a 11ª sessão de um pacote de 10 vira "sem acordo" (pendência), não estoura nem vira cobrança. Teste em Task 4 (`test_pacote_esgotado_vira_pendencia`).

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `backend/migracoes/migracao_financeiro_cobranca.sql` (novo) | Migração Postgres |
| `backend/migrar_financeiro_cobranca.py` (novo) | Migração SQLite/Postgres, idempotente |
| `backend/schema.sql`, `backend/schema_postgres.sql` | Tabelas/colunas novas no banco novo |
| `backend/cobranca_regras.py` (novo) | Regras puras: períodos, proporcional, rateio, escolha do acordo |
| `backend/acordos_service.py` (novo) | Validar/criar/editar/encerrar acordo; parcelas do pacote |
| `backend/cobranca_service.py` (novo) | Sincronizar agenda → cobranças, pendências, status vencido |
| `backend/gerar_cobrancas_clinicas.py` (novo) | Script de cron: sincroniza todas as clínicas com o módulo |
| `backend/blueprints/financeiro_bp.py` | Rotas novas (acordos, cobranças, baixa, pendências, config, extrato) |
| `backend/blueprints/agenda_bp.py` | Gravar `consultas.especialidade`; "sessão N de M" no atendimento |
| `backend/pagamento_service.py` | Webhook grava `recebido_por_nome = 'Mercado Pago'` |
| `frontend/js/financeiro_util.js` (novo) | Funções puras: rótulos de status/forma/ciclo, totais, validação do formulário de acordo |
| `frontend/js/views/financeiro.js` | Tela Cobranças (gestor/secretária), Configurações → Financeiro, extrato da família |
| `frontend/js/views/financeiro_ficha.js` (novo) | Cartão "Financeiro" da ficha: acordos + extrato |
| `frontend/js/views/jornada.js`, `frontend/js/views/pacientes.js` | Chamam o cartão da ficha |
| `frontend/js/shell.js`, `frontend/js/app.js`, `frontend/index.html` | Menu/rota da secretária, scripts novos |

---

### Task 1: Banco — acordos, itens, status novos, especialidade na consulta

**Files:**
- Create: `backend/migracoes/migracao_financeiro_cobranca.sql`, `backend/migrar_financeiro_cobranca.py`
- Modify: `backend/schema.sql`, `backend/schema_postgres.sql`, `backend/seed.py` (só se algum INSERT em `cobrancas`/`pagamentos` usar status/forma que deixem de existir — não devem)
- Test: `backend/tests/test_financeiro_cobranca_schema.py`

**Interfaces:**
- Produces (schema, iguais em SQLite e Postgres):
  - `organizacoes.fin_cobrar_falta INTEGER NOT NULL DEFAULT 0`, `organizacoes.fin_repasse_falta INTEGER NOT NULL DEFAULT 0`
  - `consultas.especialidade TEXT` (cópia de quem atende; migração preenche: `COALESCE(NULLIF(TRIM(u.especialidade),''),'Geral')` do `profissional_id`)
  - `acordos_pagamento(id, organizacao_id NOT NULL, paciente_id NOT NULL, especialidade TEXT NOT NULL /* 'Geral', 'Fonoaudiologia'..., ou '*' = todas */, tipo TEXT CHECK IN ('avulsa','mensalidade','pacote'), ciclo TEXT CHECK IN ('consulta','quinzenal','mensal') /* só avulsa */, vence_dias INTEGER DEFAULT 5, valor_centavos INTEGER /* mensalidade e pacote */, dia_vencimento INTEGER /* mensalidade, 1–28 */, sessoes_total INTEGER /* pacote */, parcelas INTEGER /* pacote */, primeiro_vencimento TEXT /* pacote, YYYY-MM-DD */, inicio TEXT NOT NULL, fim TEXT /* NULL = sem fim */, status TEXT CHECK IN ('ativo','encerrado') DEFAULT 'ativo', criado_por INTEGER, criado_em, encerrado_em)`
  - índice único parcial `idx_acordo_ativo_esp` em `(paciente_id, LOWER(TRIM(especialidade))) WHERE status='ativo'`
  - `cobrancas` ganha: `organizacao_id INTEGER`, `acordo_id INTEGER`, `tipo TEXT` (`'avulsa'|'periodo'|'mensalidade'|'pacote'|'manual'`, padrão `'manual'`), `periodo_inicio TEXT`, `periodo_fim TEXT`, `desconto_centavos INTEGER NOT NULL DEFAULT 0`, `desconto_motivo TEXT`, `liberada_em TEXT`, `revisar INTEGER NOT NULL DEFAULT 0`, `revisar_motivo TEXT`; status CHECK passa a `('rascunho','pendente','parcial','pago','vencido','cancelado')`. `valor_centavos` = **bruto** (soma dos itens ou valor do acordo); a pagar = `valor_centavos − desconto_centavos`.
  - `cobranca_itens(id, cobranca_id NOT NULL, consulta_id NOT NULL, data_hora TEXT, procedimento_nome TEXT, valor_centavos INTEGER NOT NULL)` + `UNIQUE(consulta_id)`
  - `pagamentos` ganha: `recebido_por_usuario_id INTEGER`, `recebido_por_nome TEXT`, `estornado_em TEXT`, `estorno_motivo TEXT`, `estornado_por INTEGER`; forma CHECK passa a `('pix','cartao','cartao_credito','cartao_debito','boleto','dinheiro','transferencia')`; `pago_em` passa a aceitar data informada.
  - `consulta_decisao_cobranca(consulta_id PRIMARY KEY, decisao TEXT CHECK IN ('nao_cobrar','valor'), valor_centavos INTEGER, motivo TEXT, decidido_por INTEGER, decidido_em TEXT)` — "não cobrar" e "valor informado" de sessões pendentes.
  - `acordo_pacote_consumo(consulta_id PRIMARY KEY, acordo_id NOT NULL, numero INTEGER NOT NULL)` — "sessão N de M".
- Produces (funções): `migrar_financeiro_cobranca.migrar() -> None` (imprime `(SQLite)`/`(Postgres)` no fim como os outros).

- [ ] **Step 1: Escrever os testes**: `test_colunas_e_tabelas_existem` (PRAGMA de cada tabela/coluna acima), `test_status_rascunho_e_cancelado_aceitos`, `test_forma_cartao_credito_aceita`, `test_item_mesma_consulta_duas_vezes_falha` (IntegrityError), `test_dois_acordos_ativos_mesma_especialidade_falha` (" fono " × "Fono"), `test_migracao_idempotente` (crie no teste, com `sqlite3`, um banco com as tabelas `organizacoes`/`usuarios`/`pacientes`/`consultas`/`cobrancas`/`pagamentos` no formato **antigo** — copie as definições atuais do `schema.sql` para o teste —, 1 linha em cada; aponte `db.DB_PATH` para ele, rode `migrar()` 2×, confira as colunas novas e que as linhas sobreviveram) e `test_migracao_preenche_especialidade` (profissional com " Fono " → "Fono"; sem especialidade → "Geral").
- [ ] **Step 2: Rodar e ver falhar** — `...pytest -q tests/test_financeiro_cobranca_schema.py` → FAIL (colunas ausentes).
- [ ] **Step 3: Atualizar `schema.sql` e `schema_postgres.sql`** com o formato final.
- [ ] **Step 4: Escrever a migração.** Postgres: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, `DROP CONSTRAINT IF EXISTS cobrancas_status_check` / `pagamentos_forma_check` e recriar, `CREATE TABLE/INDEX IF NOT EXISTS`, `UPDATE consultas ... WHERE especialidade IS NULL`. SQLite: para o CHECK novo, recriar `cobrancas` e `pagamentos` (`CREATE TABLE x_novo`, `INSERT ... SELECT`, `DROP`, `ALTER ... RENAME`) dentro de uma transação, só se o CHECK atual não tiver `'rascunho'` (leia `sqlite_master.sql`). Nenhuma clínica usa cobrança em produção (spec, seção 8), mas a migração não pode perder linhas.
- [ ] **Step 5: Rodar os testes da task e a suíte inteira** → PASS.
- [ ] **Step 6: Commit** `Financeiro: banco das cobranças (acordos, itens, status novos)`.

---

### Task 2: Regras puras de cobrança

**Files:**
- Create: `backend/cobranca_regras.py`
- Test: `backend/tests/test_cobranca_regras.py`

**Interfaces:**
- Produces:
  - `normalizar_especialidade(texto: str | None) -> str` — `TRIM`, vazio/None → `"Geral"`.
  - `mesma_especialidade(a: str, b: str) -> bool` — ignora caixa e espaços nas pontas.
  - `escolher_acordo(acordos: list[dict], especialidade: str, data: str) -> dict | None` — só ativos vigentes na data (`inicio <= data` e `fim` nulo ou `>= data`); específico vence `'*'`.
  - `status_gera_cobranca(status: str, cobrar_falta: bool) -> bool` — `realizada` sempre; `faltou` se `cobrar_falta`; resto nunca.
  - `periodo_da_data(data: str, ciclo: str) -> tuple[str, str]` — `consulta` → (data, data); `quinzenal` → 1–15 ou 16–fim; `mensal` → mês.
  - `vencimento_do_periodo(fim: str, vence_dias: int) -> str`.
  - `mensalidade_do_mes(valor: int, ano: int, mes: int, inicio: str, fim: str | None) -> int` — proporcional (Global Constraints); 0 se o acordo não cobre nenhum dia do mês.
  - `ratear_desconto(valores: list[int], desconto: int) -> list[int]` — devolve o valor líquido de cada item; proporcional ao valor; a sobra de arredondamento vai para o maior item; soma dos líquidos = soma − desconto. (Usada na etapa 3; testada aqui.)
  - `parcelas_do_pacote(valor: int, parcelas: int, primeiro_vencimento: str) -> list[tuple[str, int]]` — vencimentos mensais (dia > fim do mês → último dia); a diferença de centavos vai na 1ª parcela.

- [ ] **Step 1: Testes** (valores exatos):
  - `periodo_da_data("2026-11-15","quinzenal") == ("2026-11-01","2026-11-15")`; `("2026-11-16","quinzenal") → ("2026-11-16","2026-11-30")`; `("2026-02-20","mensal") → ("2026-02-01","2026-02-28")`.
  - `vencimento_do_periodo("2026-11-30", 5) == "2026-12-05"`.
  - `mensalidade_do_mes(60000, 2026, 11, "2026-11-16", None) == 30000` (15 de 30 dias); `(60000, 2026, 11, "2026-10-01", "2026-11-10") == 20000`; `(60000, 2026, 12, "2026-10-01", "2026-11-10") == 0`.
  - `ratear_desconto([23000, 23000, 20500], 6650) == [20700, 20700, 18450]` (soma 59850) — confira a conta no teste.
  - `parcelas_do_pacote(100000, 3, "2026-01-31") == [("2026-01-31", 33334), ("2026-02-28", 33333), ("2026-03-31", 33333)]`.
  - `test_acordo_especifico_vence_todas`; `test_acordo_fora_da_vigencia_ignorado`; `status_gera_cobranca("faltou", False) is False`, `("falta_justificada", True) is False`; `normalizar_especialidade("  ") == "Geral"`.
- [ ] **Step 2: Rodar** → FAIL (módulo não existe).
- [ ] **Step 3: Implementar** com `datetime.date`/`calendar.monthrange`, sem banco.
- [ ] **Step 4: Rodar** → PASS.
- [ ] **Step 5: Commit** `Financeiro: regras puras de cobrança`.

---

### Task 3: Especialidade gravada na consulta + acordos (serviço e rotas)

**Files:**
- Create: `backend/acordos_service.py`
- Modify: `backend/blueprints/agenda_bp.py` (os 3 pontos que gravam `profissional_id`: INSERT avulso ~l.287, INSERT da série ~l.395, UPDATE da edição ~l.479), `backend/blueprints/financeiro_bp.py`
- Test: `backend/tests/test_acordos_pagamento.py`

**Interfaces:**
- Consumes: `cobranca_regras.normalizar_especialidade`, `parcelas_do_pacote`.
- Produces:
  - `agenda_bp._especialidade_de(profissional_id: int) -> str` usada nos 3 pontos.
  - `acordos_service.validar(corpo: dict, hoje: str) -> tuple[dict | None, str | None]` — devolve `(dados_limpos, erro)`. Regras: `tipo` obrigatório; `especialidade` texto até 60 ou `'*'`; avulsa exige `ciclo` e aceita `vence_dias` 0–60; mensalidade exige `valor_centavos` 1–100.000.000 e `dia_vencimento` 1–28; pacote exige `sessoes_total` 1–200, `valor_centavos`, `parcelas` 1–24, `primeiro_vencimento`; `inicio` obrigatório (padrão hoje), `fim` ≥ `inicio`.
  - `acordos_service.criar(org_id: int, paciente_id: int, dados: dict, usuario: dict, incluir_consultas: list[int]) -> int` — grava; se pacote, cria as parcelas em `cobrancas` (`tipo='pacote'`, `status='pendente'`); `incluir_consultas` = ids de sessões "sem acordo" do paciente que passam a valer por este acordo (o `inicio` efetivo vira a menor data entre `inicio` e a data delas). Conflito com acordo ativo da mesma especialidade → `ValueError("Já existe um acordo ativo para essa especialidade.")`.
  - `acordos_service.encerrar(acordo_id: int, data_fim: str, usuario: dict) -> None`.
  - Rotas (gestor, secretária, admin_master; módulo financeiro; paciente da mesma clínica senão 404):
    - `GET /api/financeiro/paciente/<id>/acordos` → `[{...acordo, "sessoes_usadas": int | None}]`
    - `POST /api/financeiro/paciente/<id>/acordos` (corpo + `incluir_consultas`) → 201 `{"id"}`; 400 erro de validação; 409 conflito.
    - `PUT /api/financeiro/acordos/<id>` → só `fim`, `vence_dias`, `dia_vencimento` e `valor_centavos` da mensalidade (vale para as próximas); tipo/especialidade não mudam (encerre e crie outro).
    - `POST /api/financeiro/acordos/<id>/encerrar` `{fim}`.
    - `GET /api/financeiro/paciente/<id>/sem-acordo?especialidade=` → sessões que contam e não têm acordo nem decisão (para o pop-up de criar acordo).

- [ ] **Step 1: Testes**: `test_consulta_grava_especialidade_de_quem_atende` (criar avulsa, série e reatribuir na edição); `test_gestor_sem_especialidade_vira_geral`; `test_criar_acordo_avulsa_mensal`; `test_criar_pacote_cria_parcelas` (3 parcelas, valores da Task 2); `test_acordo_duplicado_409`; `test_validacao_400` (parametrizado: sem tipo, dia_vencimento 31, pacote sem sessões, fim antes do início); `test_profissional_403`; `test_responsavel_403`; `test_secretaria_pode`; `test_outra_clinica_404`; `test_sem_modulo_403`; `test_incluir_consultas_sem_acordo`; `test_encerrar_acordo`; `test_auditoria_registrada`.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Implementar** serviço, gravação da especialidade e rotas.
- [ ] **Step 4: Rodar a task e a suíte de agenda** (`tests/test_agenda*.py tests/test_procedimentos_agenda.py tests/test_repeticao_avancada.py`) → PASS.
- [ ] **Step 5: Commit** `Financeiro: acordos de pagamento e especialidade na consulta`.

---

### Task 4: Sincronização agenda → cobranças e pendências

**Files:**
- Create: `backend/cobranca_service.py`, `backend/gerar_cobrancas_clinicas.py`
- Test: `backend/tests/test_cobranca_sincronizar.py`

**Interfaces:**
- Consumes: Task 2 inteira; tabelas da Task 1.
- Produces:
  - `cobranca_service.sincronizar(org_id: int, hoje: str | None = None) -> dict` — idempotente, dentro de `db.em_lote()`; devolve `{"criadas": int, "itens": int, "revisar": int}`. Faz, nesta ordem:
    1. **Sessões que contam** (status por `status_gera_cobranca`, sem item, sem decisão `nao_cobrar`, consulta da clínica com `date(data_hora) <= hoje`): escolhe o acordo (`escolher_acordo`) pela `consultas.especialidade`.
       - avulsa `consulta` → cobrança `tipo='avulsa'`, `status='pendente'`, vencimento = data + `vence_dias`, 1 item.
       - avulsa `quinzenal`/`mensal` → item na cobrança `tipo='periodo'` do período (`periodo_da_data`) em `rascunho` desse acordo; se a cobrança do período já foi liberada (status ≠ rascunho), vai para a cobrança `rascunho` do **próximo** período (cria se preciso). Cobrança de período cujo `periodo_fim >= hoje` fica `rascunho` e não aparece em "Para conferir" (campo `aberta: true` na listagem).
       - pacote → grava `acordo_pacote_consumo` com o próximo número; se `numero > sessoes_total`, não consome: a sessão vira pendência "sem acordo".
       - mensalidade → não gera item (coberta).
       - valor da sessão: `consulta_decisao_cobranca.valor_centavos` se houver, senão `procedimento_valor_centavos`; **nulo ou 0 → pendência "sem valor"**, nada é criado.
    2. **Mensalidades**: para cada acordo mensalidade ativo, uma cobrança `tipo='mensalidade'` por mês de `inicio` até o mês de `hoje` que ainda não exista (`periodo_inicio` = 1º dia do mês), valor `mensalidade_do_mes`, vencimento = `dia_vencimento` do mês, `status='pendente'`; valor 0 não cria.
    3. **Volta atrás**: item cuja consulta deixou de contar (status, consulta excluída) → se a cobrança está `rascunho`/`pendente`/`vencido` sem pagamento, remove o item, recalcula `valor_centavos` e cancela se ficar vazia; se `parcial`/`pago`, marca `revisar=1` com `revisar_motivo` ("Sessão de dd/mm virou Falta justificada") e mantém. Consumo de pacote de consulta que deixou de contar é apagado e os números posteriores são refeitos.
    4. **Vencidas**: `pendente`/`parcial` com vencimento < hoje → `vencido`.
  - `cobranca_service.pendencias(org_id: int, hoje: str | None = None) -> dict` → `{"sem_acordo": [...], "sem_valor": [...], "pacotes_acabando": [...], "mensalidades_terminando": [...], "vencidas": [...], "revisar": [...]}`; cada sessão com `consulta_id, paciente_id, paciente_nome, data_hora, profissional_nome, especialidade, procedimento_nome`; pacote "acabando" = ≤ 2 sessões restantes; mensalidade terminando = `fim` no mês corrente.
  - `cobranca_service.sessao_do_pacote(consulta_id: int) -> dict | None` → `{"numero": int, "total": int}`.
  - `gerar_cobrancas_clinicas.py`: `main()` chama `sincronizar` para cada clínica ativa com o módulo `financeiro`; imprime uma linha por clínica e `(SQLite)`/`(Postgres)` no fim (CLAUDE.md 7.2).

- [ ] **Step 1: Testes** (use `DuasClinicas` + procedimentos com valor; datas fixas passando `hoje`):
  `test_avulsa_por_consulta_cria_cobranca_ao_finalizar`; `test_falta_so_cobra_com_configuracao`; `test_falta_justificada_nunca_cobra`; `test_quinzenal_agrupa_em_rascunho` (3 sessões de 03, 10 e 14/11 → 1 cobrança com 3 itens, `periodo_fim` 15/11, vencimento 20/11); `test_sessao_atrasada_vai_para_proximo_periodo` (período 1–15 liberado; sessão do dia 14 finalizada depois → entra no 16–30); `test_mensalidade_proporcional_e_sem_itens`; `test_mensalidade_cria_meses_ate_hoje_sem_repetir`; `test_pacote_consome_em_ordem` (sessão 3 de 10); `test_pacote_esgotado_vira_pendencia`; `test_acordo_especifico_vence_todas`; `test_sem_acordo_vira_pendencia`; `test_sem_valor_vira_pendencia` (procedimento nulo); `test_decisao_nao_cobrar_some_da_pendencia`; `test_status_volta_atras_remove_item_de_cobranca_aberta`; `test_status_volta_atras_em_cobranca_paga_marca_revisar`; `test_vencida_muda_status`; `test_sincronizar_duas_vezes_nao_duplica`; `test_consulta_futura_nao_cobra`; `test_isolamento_entre_clinicas`; `test_script_cron_roda` (chama `main()` com `hoje` via variável ou parâmetro).
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Implementar.** Leia as consultas do período e os acordos de uma vez (como a série recorrente faz), não uma consulta por vez com várias queries.
- [ ] **Step 4: Rodar a task e a suíte inteira** → PASS.
- [ ] **Step 5: Commit** `Financeiro: sincronização da agenda com as cobranças`.

---

### Task 5: Baixa, estorno, liberar, desconto e decisões de pendência

**Files:**
- Modify: `backend/blueprints/financeiro_bp.py`, `backend/pagamento_service.py`
- Test: `backend/tests/test_cobranca_baixa.py`

**Interfaces:**
- Consumes: `cobranca_service.sincronizar`.
- Produces (rotas; mesma clínica senão 404; módulo financeiro):
  - `POST /api/financeiro/cobranca/<id>/pagar` (substitui a atual) — gestor/secretária/admin; corpo `{valor_centavos?, forma, data?}`; forma em `('pix','dinheiro','cartao_credito','cartao_debito','transferencia')`; valor padrão = saldo; valor > saldo → 400; grava `recebido_por_usuario_id`/`recebido_por_nome` do usuário; status vira `parcial` ou `pago`. Rascunho/cancelada → 409.
  - `POST /api/financeiro/pagamento/<id>/estornar` `{motivo}` — **só gestor/admin**; motivo obrigatório; marca o pagamento estornado e recalcula o status da cobrança (`pendente`/`vencido`/`parcial`).
  - `POST /api/financeiro/cobranca/<id>/liberar` — gestor/secretária; só `rascunho` de período já encerrado (`periodo_fim < hoje`), senão 409; status `pendente`, `liberada_em`; notifica o responsável (`criar_notificacao`, título "Nova cobrança disponível", sem valores clínicos).
  - `PUT /api/financeiro/cobranca/<id>/conferir` `{desconto_centavos, desconto_motivo, remover_itens: [item_id]}` — gestor/secretária; só `rascunho`; desconto ≤ valor e motivo obrigatório se desconto > 0; item removido vira decisão `nao_cobrar` com motivo "Retirado na conferência".
  - `POST /api/financeiro/cobranca/<id>/cancelar` `{motivo}` — gestor/admin; só sem pagamento ativo; itens viram `nao_cobrar`.
  - `POST /api/financeiro/cobranca/<id>/resolver-revisao` — gestor/admin; zera `revisar`.
  - `POST /api/financeiro/sessoes/<consulta_id>/decisao` `{decisao: 'nao_cobrar'|'valor', valor_centavos?, motivo?}` — gestor/secretária; `nao_cobrar` exige motivo; `valor` exige 1–100.000.000.
  - `POST /api/financeiro/paciente/<id>/cobrar-avulsas` `{consulta_ids}` — gestor/secretária; cria uma cobrança `tipo='avulsa'` `pendente` com essas sessões "sem acordo" (vencimento hoje + 5).
  - `POST /api/financeiro/cobranca` (atual, manual) passa a gravar `organizacao_id`, `tipo='manual'` e aceitar secretária; valida valor > 0 e vencimento.
  - `pagamento_service`: ao registrar o pagamento do webhook, `recebido_por_nome='Mercado Pago'` e a forma que já usa; continua idempotente.
  - Cada rota acima chama `log_auditoria`.

- [ ] **Step 1: Testes**: `test_baixa_total_e_parcial` (pagar 10000 de 23000 → parcial; mais 13000 → pago); `test_baixa_maior_que_saldo_400`; `test_baixa_rascunho_409`; `test_secretaria_da_baixa`; `test_profissional_nao_da_baixa_403`; `test_responsavel_nao_da_baixa_403` (regressão da correção de segurança já existente); `test_estorno_so_gestor`; `test_estorno_volta_status`; `test_liberar_so_periodo_encerrado`; `test_conferir_desconto_e_remover_item`; `test_desconto_sem_motivo_400`; `test_cancelar_com_pagamento_409`; `test_decisao_valor_gera_cobranca_na_proxima_sincronizacao`; `test_cobrar_avulsas`; `test_webhook_grava_mercado_pago` (simule como `test_assinatura_recorrente_cartao.py` faz); `test_idor_cobranca_outra_clinica` (todas as rotas → 404); `test_auditoria`.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar a task, `tests/test_idor_financeiro.py` e a suíte inteira** → PASS (ajuste `test_idor_financeiro.py` só se uma regra nova da spec mudar a expectativa, e diga qual no commit).
- [ ] **Step 5: Commit** `Financeiro: baixa, estorno, conferência e pendências`.

---

### Task 6: Listagens, configuração e extrato da família (API)

**Files:**
- Modify: `backend/blueprints/financeiro_bp.py`, `backend/blueprints/agenda_bp.py` (atendimento)
- Test: `backend/tests/test_cobranca_listagens.py`

**Interfaces:**
- Consumes: `sincronizar`, `pendencias`, `sessao_do_pacote`.
- Produces:
  - `GET /api/financeiro/cobrancas?de=&ate=&status=&paciente_id=&especialidade=` — gestor/secretária/admin; chama `sincronizar` antes; filtra por vencimento; devolve `{"cobrancas": [{id, paciente_id, paciente_nome, tipo, descricao, especialidade, periodo_inicio, periodo_fim, vencimento, status, aberta, valor_centavos, desconto_centavos, a_pagar_centavos, pago_centavos, saldo_centavos, revisar, revisar_motivo, itens: [...], pagamentos: [...]}], "totais": {"recebido_centavos" (pagamentos não estornados com data no intervalo), "em_aberto_centavos", "vencido_centavos"}, "para_conferir": int}`.
  - `GET /api/financeiro/pendencias` — **só gestor/admin**; chama `sincronizar`; devolve `cobranca_service.pendencias`.
  - `GET /api/financeiro/config` e `PUT /api/financeiro/config` `{cobrar_falta: bool, repasse_falta: bool}` — **só gestor/admin**.
  - `GET /api/financeiro/paciente/<id>` (rota atual, usada pela família e pela ficha) passa a chamar `sincronizar` e devolver a mesma forma de cobrança acima, **sem** `rascunho` e `cancelado` para o responsável, e sem `revisar`/`revisar_motivo`/`recebido_por_*` para ele.
  - `GET /api/financeiro/clinica/resumo` (dashboard atual) passa a usar `a_pagar − pago` e os status novos.
  - `GET /api/agenda/<id>/atendimento` ganha `"pacote": {"numero", "total"} | null`.

- [ ] **Step 1: Testes**: `test_lista_chama_sincronizar`; `test_filtros`; `test_totais_ignoram_estorno`; `test_para_conferir_conta_so_periodos_encerrados`; `test_pendencias_so_gestor` (secretária 403); `test_config_so_gestor`; `test_familia_nao_ve_rascunho`; `test_familia_nao_ve_quem_recebeu`; `test_familia_de_outro_paciente_403`; `test_resumo_com_status_novos`; `test_atendimento_mostra_sessao_do_pacote`.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar a suíte inteira** → PASS.
- [ ] **Step 5: Commit** `Financeiro: listagens, configuração e extrato da família`.

---

### Task 7: Tela Cobranças e Configurações → Financeiro

**Files:**
- Create: `frontend/js/financeiro_util.js`, `frontend/tests/financeiro_util.test.js`
- Modify: `frontend/js/views/financeiro.js`, `frontend/js/shell.js` (item "💳 Financeiro" no menu da secretária, `modulo: "financeiro"`), `frontend/js/app.js` (`rota("/secretaria/financeiro", ["secretaria"], viewFinanceiroGestor)`), `frontend/index.html` (script novo)

**Interfaces:**
- Consumes: rotas das Tasks 5 e 6.
- Produces (`financeiro_util.js`, exportado para Node como os outros `*_util.js`):
  - `rotuloStatusCobranca(status, aberta) -> string` — rascunho aberto "Em andamento"; rascunho encerrado "Para conferir"; pendente "Em aberto"; parcial "Pago em parte"; pago "Pago"; vencido "Vencido"; cancelado "Cancelado".
  - `rotuloForma(forma) -> string` — pix "Pix", dinheiro "Dinheiro", cartao_credito "Cartão de crédito", cartao_debito "Cartão de débito", cartao "Cartão", transferencia "Transferência", boleto "Boleto".
  - `rotuloAcordo(acordo) -> string` — "Por sessão · a cada consulta" / "· a cada 15 dias" / "· mensal"; "Mensalidade · R$ 600,00 · vence dia 10"; "Pacote · 10 sessões · R$ 1.000,00 em 3x".
  - `lerValorReais(texto) -> number | null` (centavos; aceita "1.234,56", "1234,5", "230").
  - `validarAcordo(form) -> string | null` — mesmas regras de `acordos_service.validar`, mensagem em português.
- Tela `viewFinanceiroGestor` (gestor e secretária):
  - topo: `kpiCard` Recebido no período / Em aberto / Vencido;
  - filtros: período (padrão: mês atual), status, busca de paciente (reaproveite `busca_paciente.js`);
  - bloco **"Para conferir (N)"**: cada rascunho encerrado com itens, campo de desconto + motivo, "tirar" item, botão **Liberar**;
  - lista: paciente, descrição/tipo, vencimento, a pagar, pago, status, ações **Receber** (pop-up: valor, forma, data), **Pix** (fluxo atual `gerar-pix`), ⋯ (ver itens e pagamentos; gestor: estornar, cancelar, resolver revisão);
  - **só gestor**: cartão "Pendências" com as listas de `/pendencias` e ações por sessão: "Criar acordo" (abre o pop-up de acordo da Task 8 já com o paciente e a especialidade), "Cobrar como avulsa", "Não cobrar" (motivo), "Informar valor".
- `viewDashboardGestor` (`dashboard_gestor.js`), **só com o módulo**: cartão "💳 Pendências do financeiro" com as contagens de `/pendencias` (sem acordo, sem valor, pacotes acabando, vencidas, a revisar, para conferir) e link para `#/gestor/financeiro`; carregado à parte, sem atrasar o resto do dashboard, e some se a chamada falhar.
- `viewConfiguracoes`: cartão **"💳 Financeiro"** (só gestor, só com o módulo) com as duas chaves e um botão Salvar próprio, no padrão dos outros cartões.

- [ ] **Step 1: Testes Node** de cada função do util (valores acima, `lerValorReais("1.234,56") === 123456`, `lerValorReais("abc") === null`).
- [ ] **Step 2: Rodar** `node --test frontend/tests/financeiro_util.test.js` → FAIL.
- [ ] **Step 3: Implementar util e telas.** Valores com `formatarMoeda`; datas puras com `formatarData`; datas de consulta com `formatarDataHoraLocal`. Pop-ups `.modal-fundo` (o rascunho automático de `modais.js` serve).
- [ ] **Step 4: Rodar** Node e `node --check` nos arquivos alterados → PASS; subir o servidor local e conferir com Playwright como gestor e secretária: receber parcial, liberar um período, estornar (gestor), secretária sem cartão de pendências e sem config.
- [ ] **Step 5: Commit** `Financeiro: tela de cobranças e configuração`.

---

### Task 8: Cartão "Financeiro" na ficha, extrato da família e "sessão N de M"

**Files:**
- Create: `frontend/js/views/financeiro_ficha.js`
- Modify: `frontend/js/views/jornada.js` (`renderColunaLateral`/`viewJornadaPaciente`: chama o cartão para gestor), `frontend/js/views/pacientes.js` (`viewPacienteSecretaria`), `frontend/js/views/financeiro.js` (`viewFinanceiroResponsavel`), `frontend/js/views/atendimento.js` e o pop-up da consulta em `agenda.js` (selo "Sessão 3 de 10"), `frontend/index.html`

**Interfaces:**
- Consumes: rotas das Tasks 3, 5 e 6; `financeiro_util.js`.
- Produces:
  - `renderCartaoFinanceiroFicha(pacienteId: number, alvo: HTMLElement) -> Promise<void>` — só desenha para gestor/secretária e com o módulo; lista acordos ativos (`rotuloAcordo`, "sessões usadas" no pacote), botões **+ Novo acordo**, editar (campos permitidos), encerrar; extrato resumido (últimas 6 cobranças, com status) e link para a tela de Cobranças filtrada pelo paciente.
  - `abrirModalAcordo(pacienteId: number, opcoes: {especialidade?: string, acordo?: object}) -> void` — tipo (3 cartões-botão), especialidade (select com as da clínica + "Todas as especialidades"), campos por tipo; ao abrir, busca `/sem-acordo` e mostra as sessões sem acordo com caixas marcadas para incluir.
  - Família (`viewFinanceiroResponsavel`): cada cobrança com as sessões (data, procedimento, valor), desconto, pago, saldo e o botão de Pix atual; sem rascunho/cancelada (já vem filtrado da API).
  - Selo "Sessão N de M" quando `pacote` vier no atendimento e na consulta da agenda (o `GET /api/agenda` pode ganhar `pacote_numero`/`pacote_total` só para gestor/secretária/profissional; sem valores).

- [ ] **Step 1: Testes Node** de qualquer função pura nova (ex.: `resumoExtratoFamilia(cobrancas)` se criar) no `financeiro_util.test.js`.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar** Node + `node --check`; Playwright: criar acordo quinzenal incluindo sessões antigas, mensalidade começando dia 16 (valor proporcional na lista), pacote de 10 (selo "Sessão 1 de 10" no Atender), família vendo o extrato, profissional sem cartão financeiro na ficha.
- [ ] **Step 5: Commit** `Financeiro: acordos na ficha e extrato da família`.

---

### Task 9: Fechamento — suíte, CLAUDE.md e PR

**Files:**
- Modify: `CLAUDE.md` (seção 5: item novo "Financeiro etapa 1"; seção 7: etapas 2 e 3 pendentes; seção 8: arquivos novos), `docs/superpowers/specs/2026-11-07-financeiro-clinica-design.md` só se algo mudou na construção

- [ ] **Step 1: Rodar a suíte backend inteira e o Node** → tudo PASS; anotar as contagens.
- [ ] **Step 2: Atualizar CLAUDE.md** com: regras-chave (acordo por especialidade, `'*'` = todas; sincronização idempotente ao abrir as telas; rascunho → conferir → liberar; quem vê o quê), migração (`migracoes/migracao_financeiro_cobranca.sql` ou `migrar_financeiro_cobranca.py`), script de cron opcional `gerar_cobrancas_clinicas.py`, contagens de testes.
- [ ] **Step 3: Commit, push e PR** para `main`. Mudança de **schema e cobrança** → pela regra do CLAUDE.md, **perguntar ao usuário antes do merge** mesmo com CI verde.
- [ ] **Step 4: Avisar o passo manual em produção**: rodar a migração (SQL no Supabase ou `migrar_financeiro_cobranca.py` conferindo `(Postgres)`), `git pull` + `touch tmp/restart.txt`; cron opcional.
