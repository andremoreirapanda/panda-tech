# Financeiro etapa 2 — Fechamento de caixa — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relatório de conferência do que entrou no caixa num período (só gestor): totais por forma de pagamento e por quem recebeu, lista dos recebimentos e dos estornos, com PDF e Excel.

**Architecture:** Só leitura sobre `pagamentos` (etapa 1). Um serviço puro de montagem (`caixa_service.py`) alimenta duas rotas (`/financeiro/caixa` em JSON e `/financeiro/caixa/pdf`); o PDF sai pelo reportlab, como o relatório da jornada; o Excel é montado no navegador com a biblioteca que a importação já usa. Uma correção de horário entra junto: a baixa manual sem data e o estorno passam a gravar a hora de Brasília.

**Tech Stack:** Flask, SQLite (testes) / Postgres (produção), reportlab, JS puro, `frontend/js/vendor/xlsx.mini.min.js`.

**Spec:** `docs/superpowers/specs/2026-11-07-financeiro-clinica-design.md` (seção 5; permissões na seção 3; restrições na seção 8).

## Global Constraints

- Só **gestor** (e `admin_master`) acessa; secretária, profissional e responsável → 403. Módulo `financeiro` inativo → mesma resposta das outras rotas do financeiro (`_org_financeiro_ou_erro`).
- Valores sempre em centavos (inteiro).
- Período padrão: hoje (data de Brasília, `ausencias_service.hoje_brasilia()`); no máximo **366 dias**; `de > ate` → 400.
- Sem "abrir/fechar caixa" e sem saldo inicial: é relatório, nada é gravado.
- Sem migração de banco.
- Texto visível ao usuário em português e com o nome **PandaUp** (teste `test_nome_pandaup.py` varre strings).
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Decisões (do construtor, para o usuário conferir)

1. **Estorno é saída no dia do estorno**, não apaga a entrada do dia do pagamento. Recebido = pagamentos com `pago_em` no período (inclusive os estornados depois, marcados como "estornado"); Estornado = pagamentos com `estornado_em` no período; **Líquido = Recebido − Estornado**. Assim, o fechamento de um dia que já passou não muda quando alguém estorna depois. O estorno conta na forma de pagamento e em "quem recebeu" do pagamento original.
2. **Horário**: `pagamentos.pago_em` e `pagamentos.estornado_em` passam a ser **horário de Brasília**. Hoje, a baixa manual sem data cai no padrão do banco (UTC) e o estorno grava UTC (`_agora_iso`). Os dois passam a usar `agora_brasilia_iso()`. A baixa com data escolhida e o webhook já gravam `<data> 12:00:00` (local). Linhas antigas não são convertidas (nenhuma clínica usava a cobrança antes desta versão).
3. **Quem recebeu** = `recebido_por_nome`; vazio aparece como "Não informado". O Mercado Pago já grava "Mercado Pago".
4. Filtros "quem recebeu" e "forma" valem para as duas listas e para os totais; as opções dos filtros vêm de todos os pagamentos do período (sem os filtros), para o select não esvaziar.
5. Excel no navegador (sem dependência nova no servidor): uma planilha "Recebimentos", uma "Estornos" e uma "Resumo".

## Review Focus

1. Pagamento estornado no mesmo dia em que foi recebido → aparece nas duas listas e o líquido do dia dá 0 para ele (teste em Task 1).
2. Pagamento recebido antes do período e estornado dentro dele → só entra em Estornos e deixa o líquido negativo se não houver outras entradas (teste em Task 1).
3. Baixa feita às 22h de Brasília cai no dia certo (era UTC → dia seguinte) (teste em Task 1).
4. Pagamento de outra clínica nunca aparece; paciente arquivado aparece (teste em Task 1).
5. Período sem nenhum pagamento → tela e PDF com "Nenhum recebimento no período", totais zerados, sem erro (teste em Task 2 e passo de navegador em Task 3).

---

### Task 1: Serviço do caixa e horário de Brasília nos pagamentos

**Files:**
- Create: `backend/caixa_service.py`
- Modify: `backend/ausencias_service.py` (nova `agora_brasilia_iso`), `backend/blueprints/financeiro_bp.py` (baixa manual sem data e estorno)
- Test: `backend/tests/test_financeiro_caixa.py`

**Interfaces:**
- Produces:
  - `ausencias_service.agora_brasilia_iso() -> str` — `"AAAA-MM-DD HH:MM:SS"` em Brasília (UTC−3), mesma base de `hoje_brasilia()`.
  - `caixa_service.fechamento(org_id: int, de: str, ate: str, recebido_por: str | None = None, forma: str | None = None) -> dict` com:
    ```
    {"de", "ate",
     "recebimentos": [{"id", "pago_em", "paciente_nome", "cobranca_id", "cobranca_descricao",
                       "forma", "valor_centavos", "recebido_por", "estornado": bool}],   # por pago_em, id
     "estornos": [{"id", "estornado_em", "pago_em", "paciente_nome", "cobranca_id", "cobranca_descricao",
                   "forma", "valor_centavos", "recebido_por", "motivo"}],              # por estornado_em, id
     "por_forma": [{"forma", "recebido_centavos", "estornado_centavos", "liquido_centavos"}],   # só formas com movimento, ordem de FORMAS_BAIXA, outras no fim
     "por_quem":  [{"recebido_por", "recebido_centavos", "estornado_centavos", "liquido_centavos"}],  # por nome
     "totais": {"recebido_centavos", "estornado_centavos", "liquido_centavos", "quantidade"},
     "opcoes": {"quem": [nomes ordenados], "formas": [formas presentes]}}
    ```
    `recebido_por` vazio/nulo vira `"Não informado"` (também no filtro). Filtra pela clínica com `COALESCE(cb.organizacao_id, p.organizacao_id) = ?`, igual a `_montar_cobrancas`.
  - `caixa_service.validar_periodo(de, ate, hoje: str) -> tuple[str, str] | str` — devolve `(de, ate)` ISO ou a mensagem de erro; vazio = hoje; aceita `AAAA-MM-DD`; `de > ate` → `"A data inicial é depois da final."`; mais de 366 dias → `"Escolha um período de até 1 ano."`.

- [ ] **Step 1: Testes que falham** em `backend/tests/test_financeiro_caixa.py` (use os mesmos ajudantes de cenário de `test_cobranca_baixa.py`: clínica com módulo financeiro, paciente, cobrança, inserção direta em `pagamentos`):
  - `test_agora_brasilia_iso_tres_horas_antes_do_utc` — com `ausencias_service._agora_utc` simulado em `2026-11-10 01:30:00`, devolve `"2026-11-09 22:30:00"`.
  - `test_baixa_manual_sem_data_grava_hora_de_brasilia` — mesma simulação; `POST /api/financeiro/cobranca/<id>/pagar` sem `data` → `pagamentos.pago_em == "2026-11-09 22:30:00"`.
  - `test_estorno_grava_hora_de_brasilia` — mesma simulação no estorno → `estornado_em == "2026-11-09 22:30:00"`.
  - `test_totais_por_forma_e_por_quem` — 3 pagamentos no dia (pix 10000 "Ana", dinheiro 5000 "Ana", pix 2500 "Mercado Pago") → `totais == {"recebido_centavos": 17500, "estornado_centavos": 0, "liquido_centavos": 17500, "quantidade": 3}`, `por_forma[0] == {"forma": "pix", "recebido_centavos": 12500, "estornado_centavos": 0, "liquido_centavos": 12500}`, `por_quem` com "Ana" = 15000.
  - `test_estornado_no_mesmo_dia_entra_e_sai` — pagamento de 10000 com `pago_em` e `estornado_em` no dia → está em `recebimentos` com `estornado: True` e em `estornos`; `liquido_centavos == 0`.
  - `test_estorno_de_pagamento_antigo_so_sai` — `pago_em` 01/11, `estornado_em` 09/11; fechamento de 09/11 → `recebimentos == []`, `estornos` com 1 item, `liquido_centavos == -10000`; fechamento de 01/11 → recebido 10000 com `estornado: True`, estornado 0.
  - `test_filtros_quem_e_forma` — `recebido_por="Ana"` e `forma="pix"` deixam só o pix da Ana, e `opcoes["quem"] == ["Ana", "Mercado Pago"]` mesmo com o filtro.
  - `test_sem_nome_vira_nao_informado` — pagamento com `recebido_por_nome` NULL aparece como `"Não informado"` e o filtro `"Não informado"` o encontra.
  - `test_outra_clinica_nao_aparece` e `test_paciente_arquivado_aparece`.
  - `test_validar_periodo` — `("", "", "2026-11-09") -> ("2026-11-09", "2026-11-09")`; `("2026-11-10", "2026-11-09", ...)` → mensagem de "depois da final"; `("2025-01-01", "2026-11-09", ...)` → "até 1 ano"; `("09/11/2026", ...)` → `"Data inválida."`.

- [ ] **Step 2: Rodar e ver falhar**
  Run: `cd backend && PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest tests/test_financeiro_caixa.py -q`
  Expected: FAIL (módulo `caixa_service` não existe).

- [ ] **Step 3: Implementar**
  - `agora_brasilia_iso()` em `ausencias_service.py` a partir de `_agora_utc() - timedelta(hours=3)`.
  - Em `financeiro_bp.py`: a baixa sem data passa `pago_em = ausencias_service.agora_brasilia_iso()` (some o ramo do INSERT sem `pago_em`); o estorno grava `ausencias_service.agora_brasilia_iso()` em vez de `_agora_iso()`. Não mexer em outros usos de `_agora_iso`.
  - `caixa_service.py`: duas consultas (`substr(pg.pago_em, 1, 10) BETWEEN ? AND ?` e `substr(pg.estornado_em, 1, 10) BETWEEN ? AND ?`), cada uma com o JOIN em `cobrancas`/`pacientes`; agregação em Python.

- [ ] **Step 4: Rodar e ver passar** — mesmo comando; depois `tests/test_cobranca_baixa.py tests/test_financeiro_revisao_final.py tests/test_cobranca_listagens.py` para garantir que a mudança de horário não quebrou nada.

- [ ] **Step 5: Commit** — `Financeiro: serviço do fechamento de caixa e horário de Brasília nos pagamentos`.

### Task 2: Rotas do caixa (JSON e PDF)

**Files:**
- Create: `backend/caixa_pdf.py`
- Modify: `backend/blueprints/financeiro_bp.py`
- Test: `backend/tests/test_financeiro_caixa.py` (acrescentar)

**Interfaces:**
- Consumes: `caixa_service.fechamento`, `caixa_service.validar_periodo`.
- Produces:
  - `GET /api/financeiro/caixa?de=&ate=&recebido_por=&forma=` → JSON de `fechamento` + `"clinica_nome"`. Erro de período → 400 `{"erro": msg}`.
  - `GET /api/financeiro/caixa/pdf?...` (mesmos parâmetros) → `application/pdf`, `Content-Disposition: attachment; filename=caixa-<de>-a-<ate>.pdf`.
  - `caixa_pdf.gerar_caixa_pdf(dados: dict, clinica_nome: str, logo_base64: str | None, emitido_em: str) -> bytes`.
  - Ambas com `@login_required`, `@papel_required("gestor", "admin_master")` e `_org_financeiro_ou_erro()`.

- [ ] **Step 1: Testes que falham**
  - `test_caixa_so_gestor` — gestor 200; secretária, profissional e responsável 403 (JSON e PDF).
  - `test_caixa_sem_modulo` — clínica sem o módulo financeiro → mesmo status que `GET /api/financeiro/cobrancas` devolve nessa situação.
  - `test_caixa_periodo_invalido_400` — `de=2026-11-10&ate=2026-11-09` → 400 com `"A data inicial é depois da final."`.
  - `test_caixa_padrao_hoje` — sem parâmetros → `de == ate == hoje de Brasília`.
  - `test_caixa_pdf_baixa` — resposta começa com `b"%PDF"`, `mimetype == "application/pdf"`, nome do arquivo com as duas datas; também com período vazio (sem pagamentos) e com logo PNG válido em `organizacoes.logo_base64` (com e sem prefixo `data:image/png;base64,`); logo inválido não derruba (PDF sai sem logo).

- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/test_financeiro_caixa.py -q`.

- [ ] **Step 3: Implementar**
  - `caixa_pdf.py`: A4 com `SimpleDocTemplate`, mesmos estilos de `relatorio_service._estilos()` (importar a função). Cabeçalho: logo (se decodificar; altura ~1,6 cm, proporção mantida), nome da clínica, "Fechamento de caixa", período (`DD/MM/AAAA a DD/MM/AAAA`, ou um só dia), "Emitido em DD/MM/AAAA HH:MM" e, se houver, os filtros usados. Depois: tabela Resumo (Recebido, Estornado, Líquido), tabela "Por forma de pagamento", tabela "Por quem recebeu", tabela "Recebimentos" (Data/hora, Paciente, Cobrança, Forma, Quem recebeu, Valor; estornado com "(estornado)" na forma) e tabela "Estornos" (Data do estorno, Paciente, Cobrança, Forma, Motivo, Valor). Lista vazia → parágrafo "Nenhum recebimento no período." / "Nenhum estorno no período." Rodapé "Gerado pelo PandaUp". Rótulos das formas iguais aos do front (`rotuloForma`: Pix, Dinheiro, Cartão de crédito, Cartão de débito, Transferência, Cartão, Boleto). Datas mostradas como `DD/MM/AAAA HH:MM`.
  - Rotas em `financeiro_bp.py`, ao lado de `/pendencias`.

- [ ] **Step 4: Rodar e ver passar.**

- [ ] **Step 5: Commit** — `Financeiro: rotas do fechamento de caixa (JSON e PDF)`.

### Task 3: Tela do fechamento de caixa, Excel e documentação

**Files:**
- Create: `frontend/js/views/financeiro_caixa.js`
- Modify: `frontend/js/financeiro_util.js` (funções puras), `frontend/js/views/importacao.js` (carregador do Excel vira compartilhado), `frontend/js/util.js` (recebe o carregador), `frontend/js/views/financeiro.js` (botão), `frontend/js/app.js` (rota), `frontend/index.html` (script novo, depois de `financeiro.js`), `CLAUDE.md`
- Test: `frontend/tests/financeiro_util.test.js` (acrescentar)

**Interfaces:**
- Consumes: as rotas da Task 2; `Api.baixarArquivo(caminho, nome)` para o PDF.
- Produces:
  - `carregarBibliotecaExcel(): Promise<void>` em `util.js` (o `_importacaoCarregarXlsxLib` atual, renomeado e movido; `importacao.js` passa a chamar este).
  - `planilhasCaixa(dados) -> {Resumo: any[][], Recebimentos: any[][], Estornos: any[][]}` em `financeiro_util.js`: cada uma com linha de cabeçalho; valores em **reais como número** (`12.5`, não texto), datas como texto `DD/MM/AAAA HH:MM`, forma pelo `rotuloForma`, estornado marcado na coluna "Situação" ("Estornado"/"Recebido").
  - `viewCaixaGestor(app)` em `financeiro_caixa.js`; rota `rota("/gestor/financeiro/caixa", ["gestor"], (app) => viewCaixaGestor(app))`.

- [ ] **Step 1: Testes que falham** em `financeiro_util.test.js`:
  - `planilhasCaixa: cabeçalhos e valores em reais` — com um recebimento pix de 12500 ("Ana", `pago_em` `"2026-11-09 14:05:00"`) e um estorno de 2500: `Recebimentos[0]` é `["Data/hora", "Paciente", "Cobrança", "Forma", "Quem recebeu", "Situação", "Valor (R$)"]`, `Recebimentos[1][0] === "09/11/2026 14:05"`, `Recebimentos[1][6] === 125`, `Estornos[1][6] === 25`, e `Resumo` contém a linha `["Líquido", 100]`.
  - `planilhasCaixa: sem movimento` — listas vazias → cada planilha só com o cabeçalho, e o Resumo com zeros.

- [ ] **Step 2: Rodar e ver falhar** — `node --test frontend/tests/financeiro_util.test.js`.

- [ ] **Step 3: Implementar**
  - Tela (cartões e `kpiCard` como o resto do Financeiro): filtros De / Até (padrão hoje), Quem recebeu e Forma (selects de `opcoes`, "Todos" no topo); atalhos "Hoje", "Ontem" e "Este mês"; 3 KPIs (Recebido, Estornado, Líquido); cartões "Por forma de pagamento" e "Por quem recebeu"; lista dos recebimentos (estornado com o valor riscado e o selo "Estornado"); cartão "Estornos" só se houver; botões "📄 Baixar PDF" (`Api.baixarArquivo` com os filtros) e "📊 Baixar Excel" (`carregarBibliotecaExcel()` → `XLSX.utils.aoa_to_sheet` por planilha → `XLSX.writeFile(wb, "caixa-<de>-a-<ate>.xlsx")`). Vazio: "Nenhum recebimento no período." Datas pela `formatarDataHoraLocal` (o horário já é de Brasília; nunca `formatarDataHora`).
  - No topo de `viewFinanceiroGestor`, só quando `ehGestor`: botão "🧾 Fechamento de caixa" → `#/gestor/financeiro/caixa`. O menu lateral continua marcando "Financeiro" nessa tela.
  - `CLAUDE.md`: item novo **5aw** (o que foi feito, as decisões 1–5 acima, testes, "sem migração") e a linha do fechamento de caixa na tabela da seção 8; na seção 7, a etapa 2 marcada como feita.

- [ ] **Step 4: Verificar**
  - `node --test frontend/tests/*.test.js` → tudo passa.
  - Suíte completa do backend (comando da seção 4 do CLAUDE.md) → tudo passa.
  - Navegador (servidor local, banco do `seed.py` + `migrar_financeiro_cobranca.py`): gestor abre o caixa de hoje vazio (sem erro no console), dá duas baixas (pix e dinheiro) e um estorno, confere KPIs e cartões, baixa PDF e Excel; a secretária não vê o botão e `#/secretaria/financeiro/caixa` não abre.

- [ ] **Step 5: Commit** — `Financeiro: tela do fechamento de caixa com PDF e Excel`.
