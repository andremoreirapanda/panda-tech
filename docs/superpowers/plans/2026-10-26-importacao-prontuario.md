# Importação do prontuário (etapas 1 e 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Importar a Ficha Clínica junto com a planilha de pacientes (sem duplicar quem já existe) e o histórico de evoluções numa segunda planilha que vira registros "Importado" no Diário, só para a equipe.

**Architecture:** Funções puras novas em `backend/importacao_service.py` (normalizar nome, converter data, impressão da linha); `blueprints/importacao_bp.py` ganha a ficha e o reconhecimento de paciente existente nas rotas de pacientes e as rotas novas de evoluções; `diarios_terapeuticos` ganha `origem` e `importacao_chave`. A tela `views/importacao.js` vira duas abas; o Diário mostra o selo.

**Tech Stack:** Flask + SQLite/Postgres (`db.py`), JS puro, pytest, `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-26-importacao-prontuario-design.md`

## Global Constraints

- Só gestor e admin_master, com o módulo `importacao_pacientes`; sem o módulo, o 403 de hoje (`_modulo_liberado_ou_403`).
- O servidor revalida tudo no `confirmar`; uma linha ruim nunca derruba o lote.
- Nada importado é compartilhado com a família nem gera notificação: `compartilhado_familia = 0`, `mensagem_familia` NULL.
- Nunca sobrescrever dado que a clínica já escreveu: na ficha, só campos vazios.
- Limites: ficha `diagnostico`/`alergias`/`medicamentos_em_uso`/`profissionais_externos` 2.000 caracteres, `observacoes_clinicas` 5.000; `evolucao` 10.000; `observacao` 5.000; 1.000 linhas de evolução por envio; pacientes continua `MAX_LINHAS_POR_LOTE = 500`.
- Datas aceitas: `AAAA-MM-DD` e `DD/MM/AAAA`; data de atendimento no futuro (data de Brasília, `ausencias_service.hoje_brasilia()`) é erro.
- Nome + nascimento comparados sem acento, sem diferença de maiúsculas e com espaços colapsados; casam pacientes da clínica **ativos ou arquivados**.
- Auditoria em cada confirmar: `log_auditoria(org_id, usuario_id, "importar", "pacientes"|"evolucoes", None, f"{n} registros")`.
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; testes no Windows com `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q` em `backend/`.

## Review Focus

1. Planilha exportada com datas como número de série do Excel (ex.: `45512`) nas colunas `paciente_nascimento`/`data_atendimento` → o front converte para `AAAA-MM-DD` como já faz em `data_nascimento` (teste Node na Task 5).
2. Nome com acento diferente entre os sistemas ("Lúcas" × "Lucas") ou espaço duplo → casa o mesmo paciente (teste na Task 2 e na Task 4).
3. Linha de evolução cujo texto, depois do prefixo "Profissional no sistema anterior: …", passa de 10.000 → o limite vale para o texto da planilha; o prefixo não reprova a linha (teste na Task 4).
4. Deploy antes da migração (sem as colunas novas) → a aba de evoluções responde 503 com mensagem clara e a importação de pacientes, o Diário e o ICT continuam funcionando (teste na Task 1 e na Task 4).
5. Evolução importada que a equipe editou depois → reimportar a mesma planilha pula a linha, não duplica (teste na Task 4).

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `backend/importacao_service.py` (novo) | Funções puras: `normalizar_nome`, `converter_data`, `chave_importacao`, `colunas_diario_importacao_existem` |
| `backend/blueprints/importacao_bp.py` | Ficha + paciente existente (rotas de pacientes); rotas de evoluções |
| `backend/ict_service.py` | Ignora `origem = 'importacao'` |
| `backend/schema.sql`, `backend/schema_postgres.sql` | Colunas e índice novos |
| `backend/migracoes/migracao_importacao_prontuario.sql`, `backend/migrar_importacao_prontuario.py` (novos) | Migração |
| `frontend/js/importacao_util.js` (novo) | Funções puras do front: normalizar datas de célula, montar linhas, dividir em envios de 1.000 |
| `frontend/js/views/importacao.js` | Duas abas, modelos, prévia e envio das evoluções |
| `frontend/js/views/diario.js`, `frontend/js/views/jornada.js` | Selo "Importado" |
| `backend/tests/test_importacao_prontuario.py`, `frontend/tests/importacao_util.test.js` (novos) | Testes |

---

### Task 1: Banco — colunas novas, migração e ICT

**Files:**
- Modify: `backend/schema.sql`, `backend/schema_postgres.sql` (bloco `CREATE TABLE diarios_terapeuticos` e índices logo abaixo)
- Create: `backend/migracoes/migracao_importacao_prontuario.sql`, `backend/migrar_importacao_prontuario.py`
- Create: `backend/importacao_service.py` (só `colunas_diario_importacao_existem` nesta task)
- Modify: `backend/ict_service.py` (consulta "Profissional acompanhou")
- Test: `backend/tests/test_importacao_prontuario.py`

**Interfaces:**
- Produces: colunas `diarios_terapeuticos.origem TEXT` e `diarios_terapeuticos.importacao_chave TEXT`; índice `idx_diario_importacao_chave ON diarios_terapeuticos(paciente_id, importacao_chave)`; `importacao_service.colunas_diario_importacao_existem() -> bool` (consulta segura; faz `get_db().rollback()` se der erro, como `plataforma_service._linha`).

- [ ] **Step 1: Testes que falham**

```python
def test_colunas_novas_do_diario(db_ctx):
    import importacao_service
    assert importacao_service.colunas_diario_importacao_existem() is True

def test_ict_ignora_diario_importado(db_ctx):
    # paciente com jornada ativa e só um diário importado de hoje
    ...  # cria paciente + jornada ativa, insere diário com origem='importacao'
    from ict_service import calcular_ict_paciente
    resultado = calcular_ict_paciente(paciente_id)
    assert resultado["componentes"]["profissional_acompanhou"] is False
    # e um diário comum (origem NULL) continua contando → True

def test_sem_colunas_responde_false(db_ctx):
    db_ctx.execute("ALTER TABLE diarios_terapeuticos DROP COLUMN importacao_chave")
    import importacao_service
    assert importacao_service.colunas_diario_importacao_existem() is False

def test_migracao_idempotente(db_ctx):
    import migrar_importacao_prontuario
    db_ctx.execute("DROP INDEX IF EXISTS idx_diario_importacao_chave")
    db_ctx.execute("ALTER TABLE diarios_terapeuticos DROP COLUMN importacao_chave")
    db_ctx.execute("ALTER TABLE diarios_terapeuticos DROP COLUMN origem")
    migrar_importacao_prontuario.migrar(); migrar_importacao_prontuario.migrar()
    import importacao_service
    assert importacao_service.colunas_diario_importacao_existem() is True
```
(Use as fixtures/factories que os testes atuais de diário e ICT já usam; o nome `db_ctx` é ilustrativo.)

- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/test_importacao_prontuario.py -q` → falha por coluna/módulo inexistente.
- [ ] **Step 3: Implementar** — colunas nos dois schemas; migração `.sql` (`ALTER TABLE … ADD COLUMN IF NOT EXISTS` ×2 + `CREATE INDEX IF NOT EXISTS`) e `.py` (mesmo padrão de `migrar_logo_plataforma.py`: Postgres executa o SQL; SQLite checa `PRAGMA table_info` antes de cada `ADD COLUMN`; imprime `(Postgres)`/`(SQLite)`); no ICT, acrescentar `AND (d.origem IS NULL OR d.origem <> 'importacao')`.
- [ ] **Step 4: Rodar e ver passar**; rodar também `tests/test_ict*.py` e `tests/test_diario*.py`.
- [ ] **Step 5: Commit** — "Diário: colunas origem e importacao_chave; ICT ignora importados".

### Task 2: Funções puras de importação (backend)

**Files:**
- Modify: `backend/importacao_service.py`
- Test: `backend/tests/test_importacao_prontuario.py`

**Interfaces:**
- Produces:
  - `normalizar_nome(texto: str) -> str` — sem acento (NFKD), minúsculas, espaços colapsados, `strip`.
  - `converter_data(texto: str) -> str | None` — `AAAA-MM-DD` ou `DD/MM/AAAA` → `AAAA-MM-DD` validada (data real); senão `None`.
  - `chave_importacao(paciente_id: int, data_iso: str, texto_original: str) -> str` — sha256 hex de `f"{paciente_id}|{data_iso}|{texto_original.strip()}"`.

- [ ] **Step 1: Testes que falham**

```python
def test_normalizar_nome():
    from importacao_service import normalizar_nome
    assert normalizar_nome("  Lúcas   ALMEIDA ") == normalizar_nome("lucas almeida") == "lucas almeida"

def test_converter_data():
    from importacao_service import converter_data
    assert converter_data("2026-08-12") == "2026-08-12"
    assert converter_data("12/08/2026") == "2026-08-12"
    assert converter_data("31/02/2026") is None
    assert converter_data("2026-8-12") is None and converter_data("") is None and converter_data(None) is None

def test_chave_importacao_estavel():
    from importacao_service import chave_importacao
    assert chave_importacao(1, "2026-08-12", " Texto ") == chave_importacao(1, "2026-08-12", "Texto")
    assert chave_importacao(1, "2026-08-12", "Texto") != chave_importacao(2, "2026-08-12", "Texto")
```

- [ ] **Step 2: Ver falhar.** - [ ] **Step 3: Implementar.** - [ ] **Step 4: Ver passar.** - [ ] **Step 5: Commit** — "Importação: funções puras de nome, data e impressão".

### Task 3: Etapa 1 — Ficha Clínica e paciente existente

**Files:**
- Modify: `backend/blueprints/importacao_bp.py` (`_validar_linha`, `preview`, `confirmar`)
- Test: `backend/tests/test_importacao_prontuario.py` (e manter verdes `tests/test_importacao_pacientes.py`)

**Interfaces:**
- Consumes: `normalizar_nome` (Task 2).
- Produces (resposta de `preview`, por linha, além das chaves de hoje): `paciente_status: "novo" | "existente"`, `paciente_arquivado: bool`, `ficha_campos: int` (colunas clínicas preenchidas), `ficha_mantidos: int` (campos que já tinham valor e foram mantidos; só em existente), `responsavel_acao: "vincular" | "ja_vinculado" | "nao_vinculado" | "sem_responsavel"`. `confirmar` devolve, por item criado/atualizado, `paciente_status`.
- Colunas da ficha (planilha → coluna): `diagnostico`→`diagnostico`, `alergias`→`alergias`, `medicamentos_em_uso`→`medicamentos_em_uso`, `profissionais_externos`→`profissionais_externos`, `observacoes_clinicas`→`observacoes`.

- [ ] **Step 1: Testes que falham** (nomes e asserções):
  - `test_ficha_em_paciente_novo` — linha com `diagnostico="TEA nível 1"` → `fichas_clinicas.diagnostico == "TEA nível 1"`, `atualizado_por` = gestor.
  - `test_paciente_existente_nao_duplica_e_so_completa_vazios` — paciente já com `alergias="Lactose"` e `diagnostico` vazio; linha com nome em maiúsculas/sem acento, `alergias="Glúten"`, `diagnostico="TDAH"` → continua 1 paciente; `alergias == "Lactose"`, `diagnostico == "TDAH"`; preview: `paciente_status == "existente"`, `ficha_mantidos == 1`.
  - `test_paciente_arquivado_conta_como_existente` — paciente `ativo=0` → não cria outro; `paciente_arquivado is True`; continua `ativo=0`.
  - `test_homonimos_dao_erro` — dois pacientes com mesmo nome+nascimento → linha inválida com erro contendo "mais de um paciente".
  - `test_existente_sem_responsavel_e_valido` — linha de paciente existente sem colunas de responsável → válida, `responsavel_acao == "sem_responsavel"`.
  - `test_existente_com_outro_email_nao_vincula` — responsável com e-mail novo → `responsavel_acao == "nao_vinculado"`, aviso contém "responsável diferente do cadastrado", nenhuma conta nova criada, nenhum vínculo novo.
  - `test_existente_com_mesmo_responsavel` — e-mail já vinculado → `"ja_vinculado"`.
  - `test_ficha_limite` — `diagnostico` com 2.001 caracteres → erro na linha.
  - `test_mesmo_paciente_duas_vezes_no_lote` — duas linhas iguais (paciente novo) → cria 1 paciente; a 2ª vira existente com aviso.
  - `test_auditoria_importar_pacientes` — confirmar grava `auditoria` com `acao="importar"`, `entidade="pacientes"`.
  - Paciente **novo** continua exigindo responsável (o teste atual de obrigatoriedade continua verde).
- [ ] **Step 2: Ver falhar.**
- [ ] **Step 3: Implementar** — `_validar_linha` passa a receber um índice `{normalizar_nome(nome)+"|"+nascimento: [linhas de pacientes]}` montado uma vez por lote (pacientes da clínica, ativos e arquivados) e o conjunto de e-mails já vinculados por paciente; no lote, a 1ª ocorrência de um paciente novo é registrada no índice para as seguintes. `confirmar`: novo → `criar_paciente_core` + `vincular_responsavel_core` (como hoje) + ficha (INSERT só com os campos preenchidos); existente → nada de paciente novo; responsável só se `responsavel_acao == "ja_vinculado"` (nada a fazer) — nunca vincula e-mail diferente; ficha: INSERT se não existe, senão UPDATE só das colunas hoje vazias (`NULL` ou `''`), `atualizado_por`/`atualizado_em` só se algo mudou. Auditoria no fim.
- [ ] **Step 4: Ver passar** — este arquivo e `tests/test_importacao_pacientes.py`, `tests/test_segundo_filho_mesmo_responsavel.py`.
- [ ] **Step 5: Commit** — "Importação: Ficha Clínica e paciente existente sem duplicar".

### Task 4: Etapa 2 — evoluções para o Diário

**Files:**
- Modify: `backend/blueprints/importacao_bp.py` (rotas novas)
- Test: `backend/tests/test_importacao_prontuario.py`

**Interfaces:**
- Consumes: `normalizar_nome`, `converter_data`, `chave_importacao`, `colunas_diario_importacao_existem` (Tasks 1–2); `db.em_lote()`; `ausencias_service.hoje_brasilia()`.
- Produces: `POST /api/importacao/evolucoes/preview` e `POST /api/importacao/evolucoes/confirmar`, corpo `{"linhas": [{paciente_nome, paciente_nascimento, data_atendimento, profissional_email, profissional_nome, evolucao, observacao}]}`, até 1.000 linhas (acima → 400). Resposta do preview: `{"linhas": [{linha, paciente_nome, data_atendimento, status: "pronta"|"aviso"|"erro"|"ja_importada", erros: [...], avisos: [...], profissional: "<nome achado ou 'você'>"}], "total", "prontas", "avisos", "erros", "ja_importadas"}`. Confirmar: `{"importadas": n, "puladas": m, "erros": [...]}` (201). Sem as colunas novas: 503 `{"erro": "A importação de evoluções precisa de uma atualização do banco. Fale com o suporte do PandaUp."}`.
- Texto gravado: `evolucao` da planilha; quando o profissional não casou e veio nome/e-mail, prefixo `"Profissional no sistema anterior: <nome ou e-mail>.\n\n"`. `origem = 'importacao'`, `importacao_chave = chave_importacao(paciente_id, data_iso, evolucao_original)`.

- [ ] **Step 1: Testes que falham** (nomes e asserções):
  - `test_evolucao_importada_vai_para_o_diario` — paciente "Lucas Almeida" 2019-03-14; linha com `"LÚCAS  almeida"`, `"14/03/2019"`, `"12/08/2026"`, e-mail da Camila → 1 registro: `paciente_id` certo, `profissional_id` = Camila, `data_atendimento == "2026-08-12"`, `origem == "importacao"`, `compartilhado_familia == 0`, `mensagem_familia is None`, `consulta_id is None`.
  - `test_profissional_nao_achado_fica_com_quem_importa` — e-mail desconhecido + `profissional_nome="Dra. Ana"` → `profissional_id` = gestor; texto começa com "Profissional no sistema anterior: Dra. Ana."; preview com aviso.
  - `test_prefixo_nao_reprova_texto_no_limite` — `evolucao` com 10.000 caracteres + profissional não achado → importa.
  - `test_evolucao_acima_do_limite` — 10.001 → erro.
  - `test_data_futura_e_paciente_inexistente_dao_erro` — data amanhã (Brasília) → erro; paciente que não existe → erro "paciente não encontrado"; homônimos → "mais de um paciente".
  - `test_reimportar_nao_duplica_mesmo_editado` — importa, edita `evolucao_clinica` via `PUT /api/diario/<id>`, importa de novo → continua 1 registro; preview marca `ja_importada`.
  - `test_duplicata_no_mesmo_lote` — duas linhas idênticas → 1 registro.
  - `test_familia_nao_ve_e_nao_e_notificada` — depois do confirmar: `GET` do Diário como responsável não traz o registro; `notificacoes` sem linha nova.
  - `test_sem_modulo_403_e_so_gestor` — profissional → 403; clínica sem módulo → 403.
  - `test_auditoria_importar_evolucoes`.
  - `test_erro_no_meio_nao_grava_nada` — monkeypatch para falhar no 2º INSERT → 0 registros gravados.
  - `test_sem_colunas_503` — `DROP COLUMN importacao_chave` → preview 503 com a mensagem; `GET` do Diário do paciente continua 200.
  - `test_mais_de_1000_linhas_400`.
- [ ] **Step 2: Ver falhar.**
- [ ] **Step 3: Implementar** — resolver pacientes com um índice por lote (como na Task 3, ativos e arquivados); profissionais por `lower(email)` entre usuários da clínica com papel `profissional`/`gestor` e `excluido_em IS NULL`; chaves já existentes do lote numa consulta (`importacao_chave IN (...)` por paciente); `jornada_id` = jornada ativa do paciente, se houver; INSERTs dentro de `with db.em_lote():`; nenhuma chamada de notificação.
- [ ] **Step 4: Ver passar** — o arquivo todo + `tests/test_diario*.py`.
- [ ] **Step 5: Commit** — "Importação: histórico de evoluções para o Diário".

### Task 5: Tela — duas abas, evoluções e selo "Importado"

**Files:**
- Create: `frontend/js/importacao_util.js` (+ `<script>` em `frontend/index.html`, antes de `views/importacao.js`)
- Modify: `frontend/js/views/importacao.js`, `frontend/js/views/diario.js`, `frontend/js/views/jornada.js` (`renderDiarioTimelineItem`)
- Test: `frontend/tests/importacao_util.test.js`

**Interfaces:**
- Consumes: rotas das Tasks 3–4 e as chaves de resposta delas.
- Produces (puras, `module.exports`):
  - `CAMPOS_EVOLUCOES_CSV = ["paciente_nome","paciente_nascimento","data_atendimento","profissional_email","profissional_nome","evolucao","observacao"]` e `CAMPOS_FICHA_CSV = ["diagnostico","alergias","medicamentos_em_uso","profissionais_externos","observacoes_clinicas"]`.
  - `colunasDeData(aba: "pacientes"|"evolucoes") -> string[]` → `["data_nascimento"]` / `["paciente_nascimento","data_atendimento"]` (usada por `_importacaoCelulaParaTexto` para converter série do Excel).
  - `dividirEmEnvios(linhas: any[], tamanho = 1000) -> any[][]`.

- [ ] **Step 1: Testes Node que falham** — `dividirEmEnvios` (2.500 → [1000,1000,500]; vazio → []); `colunasDeData` das duas abas; os dois arrays de campos com os nomes exatos acima.
- [ ] **Step 2: Ver falhar.** - [ ] **Step 3: Implementar**:
  - `IMPORTACAO_CAMPOS_CSV` passa a terminar com `CAMPOS_FICHA_CSV`; exemplos ganham valores fictícios (ex.: `diagnostico: "TEA nível 1"`).
  - `viewImportarPacientes`: abas **"Pacientes e Ficha Clínica"** e **"Histórico de evoluções"** (botões no topo; a aba ativa troca o conteúdo). Pacientes: a tabela da prévia ganha as colunas "Paciente" (novo/existente, com "arquivado" quando for o caso) e "Ficha" (`ficha_campos` e o aviso de mantidos), e os avisos de `responsavel_acao == "nao_vinculado"`.
  - Evoluções: modelo CSV (BOM) e Excel com `CAMPOS_EVOLUCOES_CSV` e 2 linhas fictícias; aviso fixo "As evoluções importadas ficam só para a equipe. Nada aparece para as famílias."; recomendação "Importe os pacientes antes das evoluções."; prévia por envio de até 1.000 (somando os contadores) e lista com status; botão "Importar N evoluções" que confirma envio por envio com barra de progresso ("Enviando 2 de 3…"); resumo final "N evoluções importadas, M puladas".
  - Diário: registro com `origem === "importacao"` mostra `<span class="badge badge-neutro">Importado</span>` e "🔒 Só a equipe vê" (no `diario.js` no lugar do selo "Interno"; na timeline da ficha ao lado da data).
- [ ] **Step 4: Ver passar** — `node --test frontend/tests/*.test.js`; `node --check` nos arquivos mexidos; conferir no navegador (servidor local com `seed.py`): baixar modelo, importar 3 evoluções de teste, ver o selo na ficha e que o responsável não vê.
- [ ] **Step 5: Commit** — "Importação: abas, evoluções e selo Importado no Diário".

### Task 6: Fechamento

**Files:** `CLAUDE.md` (item novo em "5. O que já foi feito" + linha na tabela da seção 8).

- [ ] **Step 1:** Suítes completas (`pytest -q` em `backend/` e `node --test frontend/tests/*.test.js`).
- [ ] **Step 2:** CLAUDE.md: o que foi feito, migração (`migracao_importacao_prontuario.sql` / `migrar_importacao_prontuario.py`), regras (só campos vazios, arquivado conta, e-mail diferente não vincula, impressão da linha, ICT ignora).
- [ ] **Step 3:** Revisão final do branch inteiro; corrigir o que for Crítico/Importante com teste.
- [ ] **Step 4:** PR. **Tem mudança de schema → pedir o "pode mesclar" ao usuário antes do merge** e passar o SQL da migração para o Supabase.
