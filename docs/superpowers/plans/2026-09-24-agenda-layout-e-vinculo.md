# Agenda: novo layout, horário da clínica e vínculo automático — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vincular automaticamente ao paciente o profissional que o atende, permitir que a clínica defina o horário de funcionamento da agenda e redesenhar a agenda (lista lateral de profissionais + semana inteira numa tela).

**Architecture:** Backend Flask: um helper em `agenda_bp.py` garante o vínculo em `profissionais_pacientes` nas rotas de criar/reatribuir consulta; duas colunas novas em `organizacoes` guardam o horário, validado em `validacao_campos.py` e exposto em `CAMPOS_ORG`. Front-end SPA em JS puro: a lógica de faixa horária/posicionamento vai para um arquivo novo de funções puras (`frontend/js/agenda_faixa.js`, testado com `node --test`); `agenda.js` passa a montar uma página de altura fixa (`100vh`) com grade posicionada em porcentagem.

**Tech Stack:** Python 3.11 + Flask + pytest (SQLite nos testes, Postgres em produção); JS puro sem build; Node 24 só para `node --test`.

**Spec:** `docs/superpowers/specs/2026-09-24-agenda-layout-e-vinculo-design.md`

## Global Constraints

- Dois PRs: **PR 1** = Task 1 (branch `vinculo-automatico-agenda`, já criado, contém a spec); **PR 2** = Tasks 2–6 (branch `agenda-layout-horario`, criado a partir do `main` depois do merge do PR 1).
- PR 1 sem schema → merge automático após testes locais + CI verdes (`gh pr merge --merge --delete-branch`). PR 2 tem schema → **perguntar ao usuário antes do merge** e avisar do passo manual de migração.
- Comandos de teste sempre de dentro de `backend/`: `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q` (Git Bash). `PYTHONUTF8=1` é obrigatório no Windows.
- `gh` fica em `"/c/Program Files/GitHub CLI/gh.exe"`.
- Toda mensagem de commit termina com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; corpo do PR termina com `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Não implementar RLS nem criptografia de campo; não tocar em `backend/habilitar_rls_encanto_em_casa.sql`.
- Horário da clínica: `HH:MM` 00:00–23:59, **qualquer minuto** (ex.: 19:15), ambos vazios = automático, início < fim.
- Faixa automática: mínimo **08:00–18:00**, arredondada para hora cheia; consulta fora da faixa estica a faixa (arredondando a extensão para hora cheia).
- Clique/arraste na grade: arredonda para **múltiplos de 15 min**, sempre dentro da faixa.
- Colunas: **segunda a sábado**; domingo só se houver consulta do profissional naquele domingo.
- A agenda do responsável (lista no shell mobile) não muda.
- Texto de interface em português do Brasil; comentários no estilo do código vizinho (explicam o porquê, citando "spec 24/09/2026").

## Review Focus

1. **Consulta fora do horário configurado** (antes da abertura, depois do fechamento, ou terminando perto da meia-noite) → a grade estica e a consulta aparece inteira; nunca fica escondida. Testado em `agenda_faixa.test.js` (Task 4).
2. **Horário incompleto ou inválido vindo do banco** (só início preenchido, início ≥ fim, texto estranho gravado antes da validação) → a agenda cai no modo automático em vez de quebrar. Testado na Task 4.
3. **Clicar ou soltar rente à borda de cima/baixo da grade** → horário preso dentro da faixa e múltiplo de 15 min (ou o próprio início picado). Testado na Task 4.
4. **Outras telas salvando a clínica sem os campos novos** (onboarding e Configurações mandam `PUT /pessoas/organizacao` com corpo parcial) → o horário salvo continua intacto. Testado na Task 2.
5. **"Hoje" depois das 21h** (fuso de Brasília): `paraChaveDia` usa `toISOString` (UTC) e marca o dia seguinte como hoje. Corrigido e testado na Task 4 (`paraChaveDia` passa a usar data local).

---

## PR 1 — Vínculo automático ao agendar

### Task 1: Vínculo automático do profissional ao agendar

**Files:**
- Modify: `backend/blueprints/agenda_bp.py` (imports l.12-16; `criar_consulta` ~l.123-150; `criar_consulta_recorrente` ~l.154-225; `editar_consulta` ~l.228-268)
- Create: `backend/tests/test_vinculo_automatico_agenda.py`
- Modify: `CLAUDE.md` (seção 5, novo item; "Estado atual")

**Interfaces:**
- Consumes: `db.query_one`, `db.execute`, `db.log_auditoria(organizacao_id, usuario_id, acao, entidade, entidade_id, detalhes="")`; factories `DuasClinicas` (gestor_a, prof_a1, prof_a2, paciente_a1 — prof_a1 já vinculado como principal ao paciente_a1; prof_a2 não vinculado).
- Produces: `_garantir_vinculo_profissional(usuario, org_id, profissional_id, paciente_id) -> None` (interno de `agenda_bp.py`).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_vinculo_automatico_agenda.py`:

```python
"""
Vínculo automático ao agendar (spec 24/09/2026): quem atende um paciente
passa a fazer parte da equipe dele (`profissionais_pacientes`) — com isso
ganha acesso de edição (plano, missões, diário), não só de visualização.
Vale ao criar consulta (única ou recorrente) e ao reatribuir a consulta a
outro profissional; gestores não ganham vínculo (já têm acesso total).
"""
from factories import DuasClinicas

from conftest import autenticado


def _vinculo(db_ctx, profissional_id, paciente_id):
    return db_ctx.query_one(
        "SELECT * FROM profissionais_pacientes WHERE usuario_id = ? AND paciente_id = ?",
        (profissional_id, paciente_id),
    )


def test_profissional_agenda_paciente_de_outro_e_ganha_vinculo(client, db_ctx):
    cen = DuasClinicas()
    assert _vinculo(db_ctx, cen.prof_a2["id"], cen.paciente_a1) is None
    r = autenticado(client, cen.prof_a2).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "data_hora": "2026-10-01 09:00:00",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    v = _vinculo(db_ctx, cen.prof_a2["id"], cen.paciente_a1)
    assert v is not None
    assert v["principal"] == 0  # paciente já tinha o prof_a1 como principal


def test_vinculo_libera_edicao_do_paciente(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a2)
    assert c.put(f"/api/pessoas/pacientes/{cen.paciente_a1}", json={"nome": "Paciente A1"}).status_code == 403
    c.post("/api/agenda", json={"paciente_id": cen.paciente_a1, "data_hora": "2026-10-01 09:00:00"})
    r = c.put(f"/api/pessoas/pacientes/{cen.paciente_a1}", json={"nome": "Paciente A1"})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_gestor_agenda_para_profissional_e_vincula_o_profissional(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a2["id"], "data_hora": "2026-10-02 10:00:00",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    assert _vinculo(db_ctx, cen.prof_a2["id"], cen.paciente_a1) is not None
    assert _vinculo(db_ctx, cen.gestor_a["id"], cen.paciente_a1) is None


def test_consulta_marcada_para_gestor_nao_cria_vinculo(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.gestor_a["id"], "data_hora": "2026-10-02 11:00:00",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    assert _vinculo(db_ctx, cen.gestor_a["id"], cen.paciente_a1) is None


def test_primeiro_vinculo_do_paciente_vira_principal(client, db_ctx):
    cen = DuasClinicas()
    # paciente novo, sem ninguém na equipe
    novo = db_ctx.execute(
        "INSERT INTO pacientes (organizacao_id, nome, data_nascimento) VALUES (?, ?, ?)",
        (cen.org_a, "Paciente Novo", "2020-01-01"),
    )
    autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": novo, "profissional_id": cen.prof_a2["id"], "data_hora": "2026-10-03 09:00:00",
    })
    assert _vinculo(db_ctx, cen.prof_a2["id"], novo)["principal"] == 1


def test_agendar_de_novo_nao_duplica_vinculo(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)  # já vinculado ao paciente_a1
    for hora in ("09:00", "10:00"):
        r = c.post("/api/agenda", json={"paciente_id": cen.paciente_a1, "data_hora": f"2026-10-05 {hora}:00"})
        assert r.status_code == 201, r.get_data(as_text=True)
    total = db_ctx.query_one(
        "SELECT COUNT(*) AS n FROM profissionais_pacientes WHERE usuario_id = ? AND paciente_id = ?",
        (cen.prof_a1["id"], cen.paciente_a1),
    )["n"]
    assert total == 1


def test_agendamento_recorrente_cria_vinculo(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/agenda/recorrente", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a2["id"],
        "data_hora": "2026-10-06 14:00:00", "frequencia": "semanal", "repeticoes": 3,
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    assert _vinculo(db_ctx, cen.prof_a2["id"], cen.paciente_a1) is not None


def test_reatribuir_consulta_vincula_o_novo_profissional(client, db_ctx):
    cen = DuasClinicas()
    consulta_id = db_ctx.execute(
        "INSERT INTO consultas (paciente_id, profissional_id, data_hora) VALUES (?, ?, ?)",
        (cen.paciente_a1, cen.prof_a1["id"], "2026-10-07 09:00:00"),
    )
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{consulta_id}", json={"profissional_id": cen.prof_a2["id"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert _vinculo(db_ctx, cen.prof_a2["id"], cen.paciente_a1) is not None


def test_cancelar_consulta_mantem_vinculo(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a2)
    consulta_id = c.post("/api/agenda", json={"paciente_id": cen.paciente_a1, "data_hora": "2026-10-08 09:00:00"}).get_json()["id"]
    assert c.delete(f"/api/agenda/{consulta_id}").status_code == 200
    assert _vinculo(db_ctx, cen.prof_a2["id"], cen.paciente_a1) is not None


def test_vinculo_criado_fica_na_auditoria(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, cen.prof_a2).post("/api/agenda", json={"paciente_id": cen.paciente_a1, "data_hora": "2026-10-09 09:00:00"})
    log = db_ctx.query_one(
        "SELECT * FROM auditoria WHERE acao = 'vincular' AND entidade = 'profissional_paciente' AND entidade_id = ?",
        (cen.paciente_a1,),
    )
    assert log is not None
```

Before running: confirm the audit table name used by `db.log_auditoria` (`grep -n "def log_auditoria" -A12 backend/db.py`) and the DELETE route's success status (`grep -n "def excluir_consulta" -A40 backend/blueprints/agenda_bp.py | grep jsonify`); adjust `auditoria` / `200` in the last two tests if they differ.

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q tests/test_vinculo_automatico_agenda.py`
Expected: FAIL in the tests that assert a vínculo exists (e.g. `assert v is not None`); `test_consulta_marcada_para_gestor_nao_cria_vinculo` and `test_agendar_de_novo_nao_duplica_vinculo` may already pass.

- [ ] **Step 3: Implement the helper and call it**

In `backend/blueprints/agenda_bp.py`, change the import line:

```python
from db import query, query_one, execute, log_evento, log_auditoria
```

Add after `_profissional_da_mesma_clinica` (keep the file's comment style):

```python
def _garantir_vinculo_profissional(usuario, org_id, profissional_id, paciente_id):
    """Vínculo automático ao agendar (spec 24/09/2026): quem atende o
    paciente passa a fazer parte da equipe dele em `profissionais_pacientes`
    — e com isso ganha acesso de EDIÇÃO (plano, missões, diário; ver
    auth.paciente_editavel), não só de visualização. Permanente: cancelar
    ou excluir a consulta não desfaz; o gestor desvincula pela ficha.
    Gestor (inclusive o que atua como profissional) não precisa de vínculo —
    já tem acesso total. `principal` segue a mesma regra de
    pessoas_bp.vincular_profissional: só se o paciente ainda não tem um."""
    prof = query_one("SELECT id, nome, papel FROM usuarios WHERE id = ?", (profissional_id,))
    if not prof or prof["papel"] != "profissional":
        return
    ja_vinculado = query_one(
        "SELECT 1 FROM profissionais_pacientes WHERE usuario_id = ? AND paciente_id = ?",
        (profissional_id, paciente_id),
    )
    if ja_vinculado:
        return
    ja_tem_principal = query_one(
        "SELECT 1 FROM profissionais_pacientes WHERE paciente_id = ? AND principal = 1", (paciente_id,)
    )
    execute(
        "INSERT INTO profissionais_pacientes (usuario_id, paciente_id, principal) VALUES (?, ?, ?)",
        (profissional_id, paciente_id, 0 if ja_tem_principal else 1),
    )
    log_auditoria(org_id, usuario["id"], "vincular", "profissional_paciente", paciente_id, prof["nome"])
```

In `criar_consulta`, right after the `INSERT INTO consultas` (before `log_evento`):

```python
    _garantir_vinculo_profissional(u, org_id, profissional_id, paciente_id)
```

In `criar_consulta_recorrente`, after the `for` loop (before `log_evento(... "consulta_recorrente_agendada" ...)`):

```python
    _garantir_vinculo_profissional(u, org_id, profissional_id, paciente_id)
```

In `editar_consulta`, after the `UPDATE consultas ...` execute (before `log_evento`):

```python
    if novo_profissional_id != consulta["profissional_id"]:
        _garantir_vinculo_profissional(u, org_id, novo_profissional_id, consulta["paciente_id"])
```

Also update the module docstring (l.1-10): add a paragraph "Vínculo automático (spec 24/09/2026): agendar ou reatribuir uma consulta vincula o profissional que atende ao paciente — ver `_garantir_vinculo_profissional`."

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q tests/test_vinculo_automatico_agenda.py`
Expected: 10 passed.
Run: `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q`
Expected: 257 passed (247 + 10). If an existing test asserted that a profissional stays unlinked after scheduling, read it: it reflects the old rule — update it and mention it in the PR.

- [ ] **Step 5: Update CLAUDE.md**

In section 5 add, after item `k)`:

```markdown
### l) Vínculo automático ao agendar (24/09/2026)
Agendar (consulta única ou recorrente) ou reatribuir uma consulta vincula o
profissional que atende ao paciente em `profissionais_pacientes`
(`_garantir_vinculo_profissional` em `agenda_bp.py`), dando acesso de
edição a plano, missões e diário. É permanente (cancelar não desfaz; o
gestor desvincula pela ficha); consulta marcada para gestor não cria
vínculo. Testes em `backend/tests/test_vinculo_automatico_agenda.py`.
```

Update the test count in the "Estado atual" paragraph to the number from Step 4.

- [ ] **Step 6: Commit, PR, CI, merge**

```bash
git add backend/blueprints/agenda_bp.py backend/tests/test_vinculo_automatico_agenda.py CLAUDE.md docs/superpowers/plans
git commit -F - <<'EOF'
Vincula automaticamente ao paciente o profissional que o atende

Agendar (única ou recorrente) ou reatribuir uma consulta cria o vínculo em
profissionais_pacientes, liberando plano, missões e diário para quem
atende. Inclui a spec e o plano da mudança da agenda.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git push -u origin vinculo-automatico-agenda
"/c/Program Files/GitHub CLI/gh.exe" pr create --base main --title "Vínculo automático do profissional ao agendar" --body "..."
"/c/Program Files/GitHub CLI/gh.exe" pr checks <N> --watch --interval 20
"/c/Program Files/GitHub CLI/gh.exe" pr merge <N> --merge --delete-branch
git checkout main && git pull --ff-only
```

PR body: what changed, no schema/no manual step, test count, ending with the Claude Code line. Merge only if all checks pass; after merge rerun the full suite on `main`.

---

## PR 2 — Horário de funcionamento + layout da agenda

Start: `git checkout main && git pull --ff-only && git checkout -b agenda-layout-horario`.

### Task 2: Horário de funcionamento — schema, migração e API

**Files:**
- Modify: `backend/schema.sql:61` and `backend/schema_postgres.sql:63` (after `agenda_permissao_total_padrao`)
- Create: `backend/migracoes/migracao_horario_agenda.sql`
- Create: `backend/migrar_horario_agenda.py`
- Modify: `.github/workflows/db-setup.yml` (new step after "perfil Secretária")
- Modify: `backend/validacao_campos.py` (new function)
- Modify: `backend/blueprints/pessoas_bp.py` (`atualizar_organizacao` ~l.1171-1205; import of `validacao_campos`)
- Modify: `backend/blueprints/auth_bp.py:19-21` (`CAMPOS_ORG`)
- Create: `backend/tests/test_horario_agenda.py`

**Interfaces:**
- Produces: columns `organizacoes.agenda_hora_inicio TEXT`, `organizacoes.agenda_hora_fim TEXT` (NULL = automático); `validar_horario_agenda(inicio, fim) -> tuple[str|None, str|None, str|None]` returning `(inicio, fim, erro)`; `PUT /api/pessoas/organizacao` accepts `agenda_hora_inicio`/`agenda_hora_fim`; `GET /api/auth/me` → `organizacao.agenda_hora_inicio/fim`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_horario_agenda.py`:

```python
"""
Horário de funcionamento da agenda (spec 24/09/2026): o gestor define
início e fim (HH:MM, qualquer minuto) em Configurações e a grade da agenda
se enquadra nessa faixa. Ambos vazios = modo automático.
"""
from factories import DuasClinicas

from conftest import autenticado


def _org(db_ctx, org_id):
    return db_ctx.query_one("SELECT agenda_hora_inicio, agenda_hora_fim FROM organizacoes WHERE id = ?", (org_id,))


def test_gestor_salva_horario_picado(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={
        "agenda_hora_inicio": "08:00", "agenda_hora_fim": "19:15",
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert _org(db_ctx, cen.org_a) == {"agenda_hora_inicio": "08:00", "agenda_hora_fim": "19:15"}


def test_horario_aparece_no_auth_me(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    c.put("/api/pessoas/organizacao", json={"agenda_hora_inicio": "07:30", "agenda_hora_fim": "18:00"})
    org = c.get("/api/auth/me").get_json()["organizacao"]
    assert org["agenda_hora_inicio"] == "07:30"
    assert org["agenda_hora_fim"] == "18:00"


def test_campos_vazios_voltam_para_automatico(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    c.put("/api/pessoas/organizacao", json={"agenda_hora_inicio": "08:00", "agenda_hora_fim": "18:00"})
    r = c.put("/api/pessoas/organizacao", json={"agenda_hora_inicio": "", "agenda_hora_fim": ""})
    assert r.status_code == 200
    assert _org(db_ctx, cen.org_a) == {"agenda_hora_inicio": None, "agenda_hora_fim": None}


def test_put_sem_os_campos_mantem_o_horario(client, db_ctx):
    """Onboarding e outras telas salvam a clínica com corpo parcial — não
    podem apagar o horário sem querer."""
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    c.put("/api/pessoas/organizacao", json={"agenda_hora_inicio": "08:00", "agenda_hora_fim": "19:15"})
    r = c.put("/api/pessoas/organizacao", json={"nome": "Clínica A renomeada"})
    assert r.status_code == 200
    assert _org(db_ctx, cen.org_a) == {"agenda_hora_inicio": "08:00", "agenda_hora_fim": "19:15"}


def test_rejeita_formatos_invalidos(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    for inicio, fim in [("8h", "18:00"), ("25:00", "26:00"), ("08:60", "18:00"), ("08:00", ""), ("", "18:00"), ("8:00", "18:00")]:
        r = c.put("/api/pessoas/organizacao", json={"agenda_hora_inicio": inicio, "agenda_hora_fim": fim})
        assert r.status_code == 400, (inicio, fim, r.get_data(as_text=True))
    assert _org(db_ctx, cen.org_a) == {"agenda_hora_inicio": None, "agenda_hora_fim": None}


def test_rejeita_inicio_depois_ou_igual_ao_fim(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    for inicio, fim in [("19:00", "08:00"), ("08:00", "08:00")]:
        r = c.put("/api/pessoas/organizacao", json={"agenda_hora_inicio": inicio, "agenda_hora_fim": fim})
        assert r.status_code == 400, (inicio, fim)


def test_profissional_nao_altera_horario(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.prof_a1).put("/api/pessoas/organizacao", json={
        "agenda_hora_inicio": "08:00", "agenda_hora_fim": "18:00",
    })
    assert r.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q tests/test_horario_agenda.py`
Expected: FAIL/ERROR with `no such column: agenda_hora_inicio` (the 403 test passes).

- [ ] **Step 3: Schema + migration files**

`backend/schema.sql`, after line 61 (`agenda_permissao_total_padrao INTEGER DEFAULT 0,`):

```sql
    -- Horário de funcionamento da agenda (spec 24/09/2026): 'HH:MM', qualquer
    -- minuto. NULL nos dois = a grade se ajusta sozinha às consultas da semana.
    agenda_hora_inicio TEXT,
    agenda_hora_fim    TEXT,
```

Same block in `backend/schema_postgres.sql` after line 63.

Create `backend/migracoes/migracao_horario_agenda.sql`:

```sql
-- ----------------------------------------------------------------------------
-- Migração incremental — Horário de funcionamento da agenda (24/09/2026)
--
-- Duas colunas novas em `organizacoes`, 'HH:MM', NULL por padrão (= faixa
-- automática na grade da agenda). ADD COLUMN IF NOT EXISTS é idempotente —
-- seguro rodar mais de uma vez.
-- ----------------------------------------------------------------------------

ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS agenda_hora_inicio TEXT;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS agenda_hora_fim TEXT;
```

Create `backend/migrar_horario_agenda.py` (same pattern as `migrar_senha_alterada_em.py`):

```python
"""
Migração não-destrutiva: adiciona `agenda_hora_inicio` e `agenda_hora_fim`
(texto 'HH:MM') à tabela `organizacoes` — horário de funcionamento da
agenda (spec 24/09/2026). NULL = a grade se ajusta sozinha às consultas.

Mesmo padrão de `migrar_senha_alterada_em.py` — usa `db.py`, funciona
tanto local (SQLite) quanto em produção (Postgres via DATABASE_URL).

Rodar uma vez, depois de atualizar o código (git pull):

    cd backend
    source /caminho/do/virtualenv/bin/activate
    python3 migrar_horario_agenda.py

Confira que a saída termina com (Postgres) em produção — sem DATABASE_URL
no ambiente o script grava no SQLite local (ver CLAUDE.md, seção 7.2).
É seguro rodar mais de uma vez.
"""
import db

TABELA = "organizacoes"
COLUNAS = [("agenda_hora_inicio", "TEXT"), ("agenda_hora_fim", "TEXT")]


def _coluna_existe_sqlite(conn, coluna):
    linhas = conn.execute(f"PRAGMA table_info({TABELA})").fetchall()
    return any(l["name"] == coluna for l in linhas)


def _coluna_existe_postgres(coluna):
    linha = db.query_one(
        "SELECT 1 FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
        (TABELA, coluna),
    )
    return bool(linha)


def migrar():
    for coluna, tipo in COLUNAS:
        if db.USANDO_POSTGRES:
            if _coluna_existe_postgres(coluna):
                print(f"↷  {TABELA}.{coluna} já existia (Postgres), pulei")
                continue
            db.execute(f"ALTER TABLE {TABELA} ADD COLUMN {coluna} {tipo}")
            print(f"✅ {TABELA}.{coluna} adicionada (Postgres)")
        else:
            conn = db.get_db()
            if _coluna_existe_sqlite(conn, coluna):
                print(f"↷  {TABELA}.{coluna} já existia (SQLite), pulei")
                continue
            conn.execute(f"ALTER TABLE {TABELA} ADD COLUMN {coluna} {tipo}")
            conn.commit()
            print(f"✅ {TABELA}.{coluna} adicionada (SQLite)")


if __name__ == "__main__":
    migrar()
```

`.github/workflows/db-setup.yml`, after the "perfil Secretária" step:

```yaml
      - name: Aplicar migração incremental (horário de funcionamento da agenda)
        # ADD COLUMN IF NOT EXISTS — idempotente, mesmo padrão dos passos acima.
        run: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migracoes/migracao_horario_agenda.sql
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

- [ ] **Step 4: Validation + API**

Append to `backend/validacao_campos.py` (add `import re` at the top if it is not there):

```python
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def validar_horario_agenda(inicio, fim):
    """Horário de funcionamento da agenda (spec 24/09/2026). Devolve
    (inicio, fim, erro): os dois vazios = (None, None, None), ou seja, modo
    automático; senão os dois precisam ser 'HH:MM' (qualquer minuto — 19:15
    vale) com início antes do fim. Comparar as strings funciona porque o
    formato tem sempre dois dígitos."""
    inicio = (inicio or "").strip()
    fim = (fim or "").strip()
    if not inicio and not fim:
        return None, None, None
    if not (_HHMM.match(inicio) and _HHMM.match(fim)):
        return None, None, "Horário de funcionamento inválido — preencha início e fim no formato HH:MM (ex.: 08:00 e 19:15)."
    if inicio >= fim:
        return None, None, "O horário de abertura precisa ser antes do horário de fechamento."
    return inicio, fim, None
```

In `backend/blueprints/pessoas_bp.py`, import `validar_horario_agenda` next to the existing `validacao_campos` import (`grep -n "validacao_campos" backend/blueprints/pessoas_bp.py`). In `atualizar_organizacao`, right after `org_atual = query_one(...)`:

```python
    # Horário de funcionamento da agenda (spec 24/09/2026) — só mexe se o
    # corpo trouxer os campos: onboarding e outras telas salvam a clínica
    # com corpo parcial e não podem apagar o horário sem querer.
    hora_inicio, hora_fim = org_atual.get("agenda_hora_inicio"), org_atual.get("agenda_hora_fim")
    if "agenda_hora_inicio" in body or "agenda_hora_fim" in body:
        hora_inicio, hora_fim, erro_horario = validar_horario_agenda(
            body.get("agenda_hora_inicio"), body.get("agenda_hora_fim"))
        if erro_horario:
            return jsonify({"erro": erro_horario}), 400
```

Extend the `UPDATE organizacoes SET ...` — add `, agenda_hora_inicio = ?, agenda_hora_fim = ?` right before ` WHERE id = ?`, and add `hora_inicio, hora_fim,` to the params right before `u["organizacao_id"]`.

In `backend/blueprints/auth_bp.py`:

```python
CAMPOS_ORG = """id, nome, cor_primaria, cor_secundaria, logo_emoji, logo_base64, plano,
                nome_ia, nome_moeda_gamificacao, nome_medalha_generico, especialidades_json,
                agenda_permissao_total_padrao, agenda_hora_inicio, agenda_hora_fim"""
```

- [ ] **Step 5: Run the new tests, then the full suite**

Run: `... -m pytest -q tests/test_horario_agenda.py` → 7 passed.
Run the full suite → all pass (previous total + 7).
Run the migration against a copy of a local DB to prove idempotency: `cp encanto.db /tmp/x.db` is not needed — just run `PYTHONUTF8=1 venv/Scripts/python.exe migrar_horario_agenda.py` twice from `backend/` (after `seed.py` if `encanto.db` doesn't exist). Expected: first run "adicionada (SQLite)" twice (or "já existia" if the seed's schema already has them — it does, since `seed.py` uses `schema.sql`), second run "já existia" twice.

- [ ] **Step 6: Commit**

```bash
git add backend/schema.sql backend/schema_postgres.sql backend/migracoes/migracao_horario_agenda.sql backend/migrar_horario_agenda.py .github/workflows/db-setup.yml backend/validacao_campos.py backend/blueprints/pessoas_bp.py backend/blueprints/auth_bp.py backend/tests/test_horario_agenda.py
git commit -F - <<'EOF'
Horário de funcionamento da agenda: colunas, migração e API

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 3: Campo de horário em Configurações

**Files:**
- Modify: `frontend/js/views/financeiro.js` (`viewConfiguracoes`: HTML after the address block ~l.435; submit handler ~l.623-656)

**Interfaces:**
- Consumes: `org.agenda_hora_inicio/fim` from `GET /pessoas/organizacao` (SELECT *), `PUT /pessoas/organizacao` from Task 2.
- Produces: after saving, `Sessao.usuario.organizacao.agenda_hora_inicio/fim` updated (via the existing `Object.assign(u.organizacao, body)`), read by the agenda in Task 5.

- [ ] **Step 1: Add the fields**

In `viewConfiguracoes`, right after the `</div>` that closes the Bairro/Cidade/UF row (~l.435) and before the `<hr>` of "🩺 Especialidades":

```html
          <hr style="border:none; border-top:1px solid var(--cor-borda); margin:20px 0;" />
          <p class="texto-sm" style="font-weight:700; margin-bottom:4px;">🕒 Horário de funcionamento da agenda</p>
          <p class="texto-xs texto-suave" style="margin-bottom:12px;">A grade da agenda mostra essa faixa de horário. Deixe os dois em branco para ela se ajustar sozinha às consultas da semana.</p>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Abre às</label><input type="time" id="cf-agenda-inicio" value="${escapeHtml(org.agenda_hora_inicio || "")}" /></div>
            <div class="campo" style="flex:1;"><label>Fecha às</label><input type="time" id="cf-agenda-fim" value="${escapeHtml(org.agenda_hora_fim || "")}" /></div>
          </div>
```

- [ ] **Step 2: Send them on submit**

In the `form-config` submit handler, before `const body = {`:

```js
        const agendaInicio = document.getElementById("cf-agenda-inicio").value;
        const agendaFim = document.getElementById("cf-agenda-fim").value;
        if (!!agendaInicio !== !!agendaFim) { Toast.erro("Preencha o horário de abertura e o de fechamento da agenda, ou deixe os dois em branco."); return; }
        if (agendaInicio && agendaInicio >= agendaFim) { Toast.erro("O horário de abertura da agenda precisa ser antes do de fechamento."); return; }
```

Add to `body`: `agenda_hora_inicio: agendaInicio, agenda_hora_fim: agendaFim,`. Replace `await Api.put("/pessoas/organizacao", body);` with:

```js
        try {
            await Api.put("/pessoas/organizacao", body);
        } catch (err) { Toast.erro(err.message); return; }
```

(`<input type="time">` returns `HH:MM` or `""`, the exact format the backend expects. After saving, `Object.assign(u.organizacao, body)` stores `""` for cleared fields — the agenda treats `""` as "automático".)

- [ ] **Step 3: Manual check**

Start the server (see CLAUDE.md §4), log in as `andre@clinicaencantar.com.br` / `gestor123`, open Configurações: set 08:00–19:15 → "Configurações salvas!"; reload → values persist; set only one → toast error, nothing saved; clear both → saved.

- [ ] **Step 4: Commit**

```bash
git add frontend/js/views/financeiro.js
git commit -F - <<'EOF'
Configurações: campo de horário de funcionamento da agenda

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 4: Funções puras da faixa horária (`agenda_faixa.js`) + testes em Node

**Files:**
- Create: `frontend/js/agenda_faixa.js`
- Create: `frontend/tests/agenda_faixa.test.js`
- Modify: `frontend/index.html:38` (script tag before `views/agenda.js`)
- Modify: `frontend/js/views/agenda.js:32` (remove `paraChaveDia`, now in `agenda_faixa.js`)
- Modify: `.github/workflows/tests.yml` (new job `js`)

**Interfaces:**
- Produces (globals in the browser, `module.exports` in Node):
  - `hhmmParaMinutos(hhmm: string) -> number|null`
  - `minutosParaHHMM(minutos: number) -> "HH:MM"` (wraps at 24h)
  - `calcularFaixaAgenda(consultas: {data_hora, duracao_min}[], horaInicioClinica?: string, horaFimClinica?: string) -> {ini: number, fim: number}` (minutes of the day)
  - `minutoNaFaixa(yPx: number, alturaPx: number, faixa) -> number` (multiple of 15, clamped)
  - `precisaDomingo(chaveDomingo: "YYYY-MM-DD", consultas) -> boolean`
  - `paraChaveDia(data: Date) -> "YYYY-MM-DD"` (local date)
  - constants `AGENDA_FAIXA_PADRAO = {ini: 480, fim: 1080}`, `AGENDA_PASSO_MIN = 15`, `AGENDA_DURACAO_PADRAO = 50`

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/agenda_faixa.test.js`:

```js
// Testes das funções puras da grade da agenda (spec 24/09/2026).
// Rodar: node --test frontend/tests/*.test.js
process.env.TZ = "America/Sao_Paulo";
const test = require("node:test");
const assert = require("node:assert/strict");
const f = require("../js/agenda_faixa.js");

const c = (dataHora, duracao = 50) => ({ data_hora: dataHora, duracao_min: duracao });

test("hhmmParaMinutos aceita HH:MM e recusa o resto", () => {
    assert.equal(f.hhmmParaMinutos("08:00"), 480);
    assert.equal(f.hhmmParaMinutos("19:15"), 1155);
    for (const ruim of ["", null, undefined, "8:00", "24:00", "08:60", "08h", "abc"]) {
        assert.equal(f.hhmmParaMinutos(ruim), null, String(ruim));
    }
});

test("minutosParaHHMM formata e dá a volta na meia-noite", () => {
    assert.equal(f.minutosParaHHMM(1155), "19:15");
    assert.equal(f.minutosParaHHMM(1440 + 10), "00:10");
});

test("sem horário e sem consultas: 08:00-18:00", () => {
    assert.deepEqual(f.calcularFaixaAgenda([], null, null), { ini: 480, fim: 1080 });
});

test("automático estica para as consultas, em hora cheia", () => {
    const faixa = f.calcularFaixaAgenda([c("2026-09-21 07:30:00", 45), c("2026-09-22 18:40:00", 45)]);
    assert.deepEqual(faixa, { ini: 420, fim: 1200 }); // 07:00-20:00
});

test("horário da clínica é usado no minuto exato", () => {
    assert.deepEqual(f.calcularFaixaAgenda([c("2026-09-21 09:00:00")], "08:10", "19:15"), { ini: 490, fim: 1155 });
});

test("consulta fora do horário da clínica estica a faixa (hora cheia)", () => {
    const faixa = f.calcularFaixaAgenda([c("2026-09-21 19:30:00", 45), c("2026-09-22 07:20:00", 30)], "08:00", "19:15");
    assert.deepEqual(faixa, { ini: 420, fim: 1260 }); // 07:00-21:00
});

test("consulta perto da meia-noite não passa de 24:00", () => {
    const faixa = f.calcularFaixaAgenda([c("2026-09-21 23:30:00", 50)]);
    assert.equal(faixa.fim, 1440);
});

test("horário da clínica incompleto ou invertido cai no automático", () => {
    assert.deepEqual(f.calcularFaixaAgenda([], "08:00", ""), { ini: 480, fim: 1080 });
    assert.deepEqual(f.calcularFaixaAgenda([], "19:00", "08:00"), { ini: 480, fim: 1080 });
    assert.deepEqual(f.calcularFaixaAgenda([], "lixo", "18:00"), { ini: 480, fim: 1080 });
});

test("consulta com data_hora estranha é ignorada", () => {
    assert.deepEqual(f.calcularFaixaAgenda([{ data_hora: "", duracao_min: 50 }, { data_hora: null }]), { ini: 480, fim: 1080 });
});

test("minutoNaFaixa arredonda para baixo em 15 min e prende na faixa", () => {
    const faixa = { ini: 480, fim: 1080 }; // 08:00-18:00, 600 min
    assert.equal(f.minutoNaFaixa(0, 600, faixa), 480);
    assert.equal(f.minutoNaFaixa(70, 600, faixa), 540); // 09:10 -> 09:00
    assert.equal(f.minutoNaFaixa(-30, 600, faixa), 480);
    assert.equal(f.minutoNaFaixa(9999, 600, faixa), 1065); // último passo: 17:45
});

test("minutoNaFaixa com início picado não devolve horário antes da abertura", () => {
    const faixa = { ini: 490, fim: 1155 }; // 08:10-19:15
    assert.equal(f.minutoNaFaixa(0, 665, faixa), 490);
    assert.equal(f.minutoNaFaixa(3, 665, faixa), 490);
});

test("precisaDomingo só com consulta naquele domingo", () => {
    assert.equal(f.precisaDomingo("2026-09-20", [c("2026-09-21 09:00:00")]), false);
    assert.equal(f.precisaDomingo("2026-09-20", [c("2026-09-20 10:00:00")]), true);
});

test("paraChaveDia usa a data local (22h em Brasília ainda é o mesmo dia)", () => {
    assert.equal(f.paraChaveDia(new Date(2026, 8, 24, 22, 30)), "2026-09-24");
    assert.equal(f.paraChaveDia(new Date(2026, 8, 24, 0, 5)), "2026-09-24");
});
```

- [ ] **Step 2: Run to verify it fails**

Run (repo root): `node --test frontend/tests/*.test.js`
Expected: FAIL — `Cannot find module '../js/agenda_faixa.js'`.

- [ ] **Step 3: Implement**

Create `frontend/js/agenda_faixa.js`:

```js
// ============================================================================
// Agenda — faixa horária da grade "Por Profissional" (spec 24/09/2026)
//
// Funções puras (sem DOM) usadas por views/agenda.js: qual faixa de horário
// a grade mostra, onde cada consulta cai nela e qual horário corresponde a
// um clique. Ficam separadas pra poderem ser testadas com `node --test`
// (frontend/tests/agenda_faixa.test.js) — no navegador viram globais, como
// o resto do front-end.
// ============================================================================

const AGENDA_FAIXA_PADRAO = { ini: 8 * 60, fim: 18 * 60 }; // mínimo do modo automático
const AGENDA_PASSO_MIN = 15;       // clique/arraste encaixam de 15 em 15 min (combina com horário picado)
const AGENDA_DURACAO_PADRAO = 50;  // mesmo padrão de consultas.duracao_min no backend

function hhmmParaMinutos(hhmm) {
    const m = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(hhmm || "");
    return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : null;
}

function minutosParaHHMM(minutos) {
    const t = ((minutos % 1440) + 1440) % 1440;
    return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
}

// Faixa exibida, em minutos do dia. Com horário da clínica válido, usa ele no
// minuto exato (08:10–19:15 fica 08:10–19:15); sem ele, parte de 08:00–18:00.
// Nos dois casos, consulta fora da faixa estica a faixa até a hora cheia mais
// próxima — nada fica escondido. Horário incompleto/invertido (dado antigo ou
// gravado antes da validação) cai no automático em vez de quebrar a grade.
function calcularFaixaAgenda(consultas, horaInicioClinica, horaFimClinica) {
    const iniClinica = hhmmParaMinutos(horaInicioClinica);
    const fimClinica = hhmmParaMinutos(horaFimClinica);
    const temHorario = iniClinica !== null && fimClinica !== null && iniClinica < fimClinica;
    let ini = temHorario ? iniClinica : AGENDA_FAIXA_PADRAO.ini;
    let fim = temHorario ? fimClinica : AGENDA_FAIXA_PADRAO.fim;
    (consultas || []).forEach(c => {
        const inicioConsulta = hhmmParaMinutos(String((c && c.data_hora) || "").slice(11, 16));
        if (inicioConsulta === null) return;
        const fimConsulta = Math.min(1440, inicioConsulta + ((c.duracao_min) || AGENDA_DURACAO_PADRAO));
        if (inicioConsulta < ini) ini = Math.floor(inicioConsulta / 60) * 60;
        if (fimConsulta > fim) fim = Math.min(1440, Math.ceil(fimConsulta / 60) * 60);
    });
    return { ini, fim };
}

// Posição vertical (px dentro da coluna) -> horário, de 15 em 15 min, para
// baixo (clicar em 09:10 abre 09:00), preso entre a abertura e o último
// passo antes do fechamento.
function minutoNaFaixa(yPx, alturaPx, faixa) {
    const bruto = faixa.ini + (yPx / alturaPx) * (faixa.fim - faixa.ini);
    const passo = Math.floor(bruto / AGENDA_PASSO_MIN) * AGENDA_PASSO_MIN;
    const ultimo = Math.max(faixa.ini, Math.ceil(faixa.fim / AGENDA_PASSO_MIN) * AGENDA_PASSO_MIN - AGENDA_PASSO_MIN);
    return Math.min(Math.max(passo, faixa.ini), ultimo);
}

// Semana da grade é segunda a sábado; domingo só entra se tiver consulta.
function precisaDomingo(chaveDomingo, consultas) {
    return (consultas || []).some(c => String(c.data_hora || "").slice(0, 10) === chaveDomingo);
}

// Chave "YYYY-MM-DD" pela data LOCAL. Antes usava toISOString() (UTC), que
// depois das 21h em Brasília já apontava para o dia seguinte.
function paraChaveDia(data) {
    return `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, "0")}-${String(data.getDate()).padStart(2, "0")}`;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        AGENDA_FAIXA_PADRAO, AGENDA_PASSO_MIN, AGENDA_DURACAO_PADRAO,
        hhmmParaMinutos, minutosParaHHMM, calcularFaixaAgenda, minutoNaFaixa, precisaDomingo, paraChaveDia,
    };
}
```

Note on `minutoNaFaixa`'s last step: for `fim = 1155` (19:15) → `ceil(1155/15)*15 - 15 = 1140` (19:00); for `fim = 1080` → 1065 (17:45), matching the test.

In `frontend/index.html`, add before `<script src="/js/views/agenda.js"></script>`:

```html
<script src="/js/agenda_faixa.js"></script>
```

In `frontend/js/views/agenda.js`, delete line 32 (`function paraChaveDia(data) { return data.toISOString().slice(0, 10); }`) — the global from `agenda_faixa.js` replaces it. Check nothing else defines/uses it differently: `grep -rn "paraChaveDia" frontend/js`.

In `.github/workflows/tests.yml`, add a job at the same level as `testes` / `smoke-postgres`:

```yaml
  js:
    name: node --test (front-end)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: node --test frontend/tests/*.test.js
```

- [ ] **Step 4: Run to verify it passes**

Run: `node --test frontend/tests/*.test.js`
Expected: all tests pass (13).

- [ ] **Step 5: Commit**

```bash
git add frontend/js/agenda_faixa.js frontend/tests/agenda_faixa.test.js frontend/index.html frontend/js/views/agenda.js .github/workflows/tests.yml
git commit -F - <<'EOF'
Agenda: funções puras da faixa horária, com testes em node --test

Também corrige paraChaveDia, que usava UTC e marcava o dia seguinte como
hoje depois das 21h.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 5: Novo layout da agenda

**Files:**
- Modify: `frontend/js/views/agenda.js` (constants l.7-9; `viewAgenda` l.34-428)
- Modify: `frontend/css/components.css` (agenda "Por Profissional" block ~l.244-276 and its `@media (max-width: 900px)`)

**Interfaces:**
- Consumes: from Task 4 — `calcularFaixaAgenda`, `minutoNaFaixa`, `minutosParaHHMM`, `hhmmParaMinutos`, `precisaDomingo`, `paraChaveDia`, `AGENDA_DURACAO_PADRAO`; `Sessao.usuario.organizacao.agenda_hora_inicio/fim` (Tasks 2–3); existing `renderAvatarUsuario(usuario, px)` (util.js), `corSegura`, `escapeHtml`, `formatarData`, `renderShellSidebar`, `anexarEventosShell`, `abrirModalNovaConsulta({profissionalId, data, hora}, cb)`, `abrirModalEditarConsulta`.
- Produces: nothing consumed elsewhere.

This task has no automated test (the suite has no DOM tests); it is verified in Task 6.

- [ ] **Step 1: Remove the pixel constants**

Delete `AGENDA_HORA_INICIO`, `AGENDA_HORA_FIM`, `AGENDA_ALTURA_SLOT` (l.7-9). Add below `inicioDaSemana`:

```js
// Dias mostrados na grade "Por Profissional": segunda a sábado; domingo só
// se o profissional tiver consulta nele (spec 24/09/2026).
function diasDaGradeSemana(inicioDomingo, consultasDoProf) {
    const dias = Array.from({ length: 7 }, (_, i) => { const d = new Date(inicioDomingo); d.setDate(d.getDate() + i); return d; });
    return precisaDomingo(paraChaveDia(dias[0]), consultasDoProf) ? dias : dias.slice(1);
}
```

- [ ] **Step 2: New state + top bar pieces**

Inside `viewAgenda`, next to the other `let` state:

```js
    let filtroProfissional = "";
    let faixaAtual = null; // faixa da grade renderizada — usada no clique/arraste
```

Replace `renderToggleModo` and `renderSeletorVisao` with:

```js
    function renderToggleModo() {
        return `
        <div class="linha gap-2">
          <button type="button" class="botao botao-sm ${modoVisao === "geral" ? "botao-primario" : "botao-secundario"} btn-modo-agenda" data-modo="geral">🏥 Geral da Clínica</button>
          <button type="button" class="botao botao-sm ${modoVisao === "porProfissional" ? "botao-primario" : "botao-secundario"} btn-modo-agenda" data-modo="porProfissional">👤 Por Profissional</button>
        </div>`;
    }

    function renderBotoesVisao() {
        const opcoes = [["lista", "📋 Lista"], ["semana", "🗓️ Semana"], ["mes", "📆 Mês"]];
        return `
        <div class="linha gap-2">
          ${opcoes.map(([v, label]) => `<button type="button" class="botao botao-sm ${visaoAtual === v ? "botao-primario" : "botao-secundario"} btn-visao-agenda" data-visao="${v}">${label}</button>`).join("")}
        </div>`;
    }

    function renderNavSemana() {
        const inicio = inicioDaSemana(dataReferencia);
        const fim = new Date(inicio); fim.setDate(fim.getDate() + 6);
        return `
        <div class="linha gap-1" style="align-items:center;">
          <button type="button" class="botao-icone" id="btn-semana-anterior" title="Semana anterior">←</button>
          <button type="button" class="botao botao-sm botao-secundario" id="btn-hoje">Hoje</button>
          <button type="button" class="botao-icone" id="btn-semana-proxima" title="Próxima semana">→</button>
          <strong class="texto-sm" style="margin-left:6px; white-space:nowrap;">${formatarData(paraChaveDia(inicio))} – ${formatarData(paraChaveDia(fim))}</strong>
        </div>`;
    }

    function renderListaProfissionais() {
        const termo = filtroProfissional.trim().toLowerCase();
        const itemTodos = modoVisao === "geral" ? `
          <li><button type="button" class="agenda-item-prof ativo" data-todos="1">
            <span class="agenda-item-avatar">🏥</span>
            <span><span class="agenda-item-nome">Todos</span><br><span class="agenda-item-esp">Agenda geral da clínica</span></span>
          </button></li>` : "";
        return `
        <aside class="agenda-lista-profs">
          <input type="search" id="agenda-filtro-prof" placeholder="🔍 Filtrar profissional" value="${escapeHtml(filtroProfissional)}" />
          <ul>
            ${itemTodos}
            ${profissionaisTodos.map(p => {
                const nomeBusca = (p.nome || "").toLowerCase();
                const ativo = modoVisao === "porProfissional" && p.id === profissionalSelecionadoId;
                return `
                <li data-nome="${escapeHtml(nomeBusca)}" style="${termo && !nomeBusca.includes(termo) ? "display:none;" : ""}">
                  <button type="button" class="agenda-item-prof btn-selecionar-profissional ${ativo ? "ativo" : ""}" data-id="${p.id}">
                    <span class="agenda-item-avatar" style="border-color:${corSegura(p.cor_agenda, "var(--cor-marca)")};">${renderAvatarUsuario(p, 30)}</span>
                    <span><span class="agenda-item-nome">${escapeHtml(p.nome)}</span><br><span class="agenda-item-esp">${escapeHtml(p.especialidade || "")}</span></span>
                  </button>
                </li>`;
            }).join("")}
          </ul>
        </aside>`;
    }
```

(`renderLegendaProfissionais` and `renderLegendaStatus` stay as they are.)

- [ ] **Step 3: Rewrite `renderVisaoPorProfissional`**

Replace the whole function (l.220-307) with:

```js
    function renderVisaoPorProfissional() {
        if (!profissionaisTodos.length) {
            return `<div class="cartao estado-vazio"><p>Nenhum profissional cadastrado ainda.</p></div>`;
        }
        const profSelecionado = profissionaisTodos.find(p => p.id === profissionalSelecionadoId) || profissionaisTodos[0];
        const inicio = inicioDaSemana(dataReferencia);
        const consultasDoProf = consultas.filter(c => c.profissional_id === profSelecionado.id);
        const dias = diasDaGradeSemana(inicio, consultasDoProf);
        const chaves = dias.map(paraChaveDia);
        const daSemana = consultasDoProf.filter(c => chaves.includes(c.data_hora.slice(0, 10)));
        const org = Sessao.usuario.organizacao || {};
        faixaAtual = calcularFaixaAgenda(daSemana, org.agenda_hora_inicio, org.agenda_hora_fim);
        const total = faixaAtual.fim - faixaAtual.ini;
        const pct = m => ((m - faixaAtual.ini) / total) * 100;
        const hojeChave = paraChaveDia(new Date());
        const editavel = podeEditarAgendaDe(profSelecionado.id);

        const linhas = [];
        for (let m = Math.ceil(faixaAtual.ini / 30) * 30; m < faixaAtual.fim; m += 30) {
            linhas.push(`<div class="agenda-linha-hora ${m % 60 ? "meia" : ""}" style="top:${pct(m)}%;"></div>`);
        }
        const rotulos = [];
        for (let m = Math.ceil(faixaAtual.ini / 60) * 60; m < faixaAtual.fim; m += 60) {
            rotulos.push(`<div class="agenda-rotulo-hora" style="top:${pct(m)}%; ${m === faixaAtual.ini ? "transform:none;" : ""}">${minutosParaHHMM(m)}</div>`);
        }

        function renderBloco(c) {
            const inicioMin = hhmmParaMinutos(c.data_hora.slice(11, 16));
            if (inicioMin === null) return "";
            const duracao = c.duracao_min || AGENDA_DURACAO_PADRAO;
            const info = STATUS_CONSULTA_INFO[c.status] || STATUS_CONSULTA_INFO.agendada;
            const desmarcada = c.status === "cancelada";
            return `
            <div class="agenda-bloco-consulta btn-abrir-editar-consulta ${desmarcada ? "status-desmarcada" : ""}" data-id="${c.id}"
                 draggable="${podeEditarAgendaDe(c.profissional_id) ? "true" : "false"}"
                 style="top:${pct(inicioMin)}%; height:calc(${(duracao / total) * 100}% - 2px); ${desmarcada ? "" : `border-color:${info.cor};`}"
                 title="${escapeHtml(`${info.label} · ${c.paciente_nome || ""}`)}">
              <div class="agenda-bloco-hora">${info.icone}${formatarHoraCurta(c.data_hora)} – ${minutosParaHHMM(inicioMin + duracao)}</div>
              <div class="agenda-bloco-nome">${escapeHtml(c.paciente_nome || "")}</div>
            </div>`;
        }

        return `
        <section class="agenda-cartao-grade">
          <div class="linha gap-2" style="align-items:baseline; flex-wrap:wrap; margin-bottom:6px;">
            <span class="agenda-ponto-cor" style="background:${corSegura(profSelecionado.cor_agenda, "var(--cor-marca)")}; width:12px; height:12px;"></span>
            <strong>${escapeHtml(profSelecionado.nome)}</strong>
            <span class="texto-xs texto-suave">${escapeHtml(profSelecionado.especialidade || "")}</span>
            <span class="texto-xs texto-suave">· ${editavel ? "clique num horário livre para agendar, ou arraste uma consulta para remarcar" : "somente visualização — só o Gestor ou quem atende pode editar esta agenda"}</span>
          </div>
          <div class="agenda-grade-cab" style="--agenda-dias:${dias.length};">
            <div></div>
            ${dias.map(d => `
              <div class="agenda-grade-dia ${paraChaveDia(d) === hojeChave ? "hoje" : ""}">${DIAS_SEMANA_ABREV[d.getDay()]} <strong>${d.getDate()}</strong></div>`).join("")}
          </div>
          <div class="agenda-grade-corpo" style="--agenda-dias:${dias.length};">
            <div class="agenda-coluna-horas">${rotulos.join("")}</div>
            ${dias.map(d => {
                const chave = paraChaveDia(d);
                return `
                <div class="agenda-coluna-grade droppable-dia ${editavel ? "btn-slot-vazio editavel" : ""} ${chave === hojeChave ? "hoje" : ""}" data-dia="${chave}">
                  ${linhas.join("")}
                  ${daSemana.filter(c => c.data_hora.slice(0, 10) === chave).map(renderBloco).join("")}
                </div>`;
            }).join("")}
          </div>
          <div style="margin-top:8px;">${renderLegendaStatus()}</div>
        </section>`;
    }
```

(`renderLegendaStatus` has `margin-bottom:10px` inline; change it to `margin-bottom:0` there — it is only used here.)

- [ ] **Step 4: Rewrite `renderizarTudo`**

```js
    function renderizarTudo() {
        let conteudo;
        let acoes = "";
        if (base === "responsavel") {
            conteudo = renderListaView();
        } else {
            const area = modoVisao === "porProfissional"
                ? renderVisaoPorProfissional()
                : `<div style="margin-bottom:12px;">${visaoAtual !== "lista" ? renderLegendaProfissionais() : ""}</div>`
                  + (visaoAtual === "lista" ? renderListaView() : visaoAtual === "semana" ? renderSemanaView() : renderMesView());
            conteudo = `<div class="agenda-corpo">${renderListaProfissionais()}<div class="agenda-area">${area}</div></div>`;
            acoes = renderToggleModo()
                + (modoVisao === "porProfissional" ? renderNavSemana() : renderBotoesVisao())
                + (podeGerenciar ? `<button class="botao botao-primario botao-sm" id="btn-nova-consulta">+ Agendar</button>` : "");
        }
        const app2 = document.getElementById("app");
        app2.innerHTML = montarShell(conteudo, acoes);
        if (base !== "responsavel") {
            // Página da agenda ocupa a tela inteira, sem rolar (spec 24/09/2026)
            // — a classe some sozinha quando outra tela redesenha o #app.
            const shell = app2.querySelector(".shell");
            if (shell) shell.classList.add("shell-agenda");
            anexarEventosShell();
        }
        conectarEventos();
    }
```

- [ ] **Step 5: Events**

In `conectarEventos`:

Replace the `.btn-selecionar-profissional` handler with:

```js
        document.querySelectorAll(".btn-selecionar-profissional").forEach(btn => btn.addEventListener("click", () => {
            profissionalSelecionadoId = parseInt(btn.dataset.id);
            modoVisao = "porProfissional"; // no modo Geral, clicar num profissional abre a agenda dele
            renderizarTudo();
        }));
        const filtro = document.getElementById("agenda-filtro-prof");
        if (filtro) filtro.addEventListener("input", () => {
            // Filtra sem redesenhar a tela (mantém o foco no campo).
            filtroProfissional = filtro.value;
            const termo = filtroProfissional.trim().toLowerCase();
            document.querySelectorAll(".agenda-lista-profs li[data-nome]").forEach(li => {
                li.style.display = !termo || li.dataset.nome.includes(termo) ? "" : "none";
            });
        });
        const btnHoje = document.getElementById("btn-hoje");
        if (btnHoje) btnHoje.addEventListener("click", () => { dataReferencia = new Date(); renderizarTudo(); });
```

Replace the empty-slot click handler (`// Clique num horário livre ...` block) with:

```js
        // Clique num horário livre da grade "Por Profissional" — abre já preenchido.
        document.querySelectorAll(".btn-slot-vazio").forEach(coluna => coluna.addEventListener("click", (e) => {
            if (e.target.closest(".agenda-bloco-consulta") || !faixaAtual) return;
            const profSelecionado = profissionaisTodos.find(p => p.id === profissionalSelecionadoId);
            if (!profSelecionado || !podeEditarAgendaDe(profSelecionado.id)) return;
            const rect = coluna.getBoundingClientRect();
            const minuto = minutoNaFaixa(e.clientY - rect.top, rect.height, faixaAtual);
            abrirModalNovaConsulta({ profissionalId: profSelecionado.id, data: coluna.dataset.dia, hora: minutosParaHHMM(minuto) }, recarregarConsultas);
        }));
```

In the `drop` handler, replace the lines from `const rect = ...` through `const novaDataHora = ...` with:

```js
                const rect = coluna.getBoundingClientRect();
                const hhmm = minutosParaHHMM(minutoNaFaixa(e.clientY - rect.top, rect.height, faixaAtual));
                const novaDataHora = `${coluna.dataset.dia} ${hhmm}:00`;
```

and the toast to `` `Consulta remarcada para ${formatarData(coluna.dataset.dia)} às ${hhmm}.` ``. Add `if (!idArrastando || !faixaAtual) return;` in place of `if (!idArrastando) return;`.

Leave the `btn-semana-anterior/proxima` and `btn-mes-*` handlers as they are (the Geral semana/mês views still render their own nav with those ids; only one set exists on screen at a time).

- [ ] **Step 6: CSS**

In `frontend/css/components.css`, replace the rules from `.agenda-pills-profissionais` through `.agenda-bloco-consulta.status-desmarcada` (and the pills rules inside the following `@media (max-width: 900px)`) with:

```css
/* ---------------------------------------------------------------- Agenda — página numa tela só (spec 24/09/2026)
   Lista de profissionais à esquerda + grade da semana ocupando a altura
   que sobra, sem rolar a página. Posições da grade em % da faixa horária
   (ver agenda_faixa.js), então ela encolhe/estica com a janela. */
.shell-agenda .shell-conteudo { max-width: none; height: 100vh; display: flex; flex-direction: column; padding: var(--esp-5) var(--esp-6); }
.shell-agenda .shell-topo { margin-bottom: var(--esp-3); gap: var(--esp-3); flex-wrap: wrap; }
.shell-agenda .shell-topo > .linha { flex-wrap: wrap; justify-content: flex-end; }
.shell-agenda .shell-conteudo > .surgir { flex: 1; min-height: 0; display: flex; flex-direction: column; }

.agenda-corpo { flex: 1; min-height: 0; display: grid; grid-template-columns: 230px minmax(0, 1fr); gap: 12px; }
.agenda-area { min-height: 0; display: flex; flex-direction: column; overflow: auto; }

.agenda-lista-profs { background: var(--cor-superficie); border: 1px solid var(--cor-borda); border-radius: 14px; display: flex; flex-direction: column; min-height: 0; }
.agenda-lista-profs input { margin: 10px; padding: 8px 10px; border: 1.5px solid var(--cor-borda); border-radius: 10px; font: inherit; font-size: 13px; }
.agenda-lista-profs ul { list-style: none; margin: 0; padding: 0 6px 8px; overflow-y: auto; }
.agenda-item-prof { display: flex; gap: 10px; align-items: center; width: 100%; padding: 8px; border: 0; border-radius: 10px; background: none; text-align: left; font: inherit; color: inherit; cursor: pointer; }
.agenda-item-prof:hover { background: var(--cor-fundo-alt); }
.agenda-item-prof.ativo { background: var(--cor-marca-clara); }
.agenda-item-prof.ativo .agenda-item-nome { color: var(--cor-marca); font-weight: 700; }
.agenda-item-avatar { width: 36px; height: 36px; flex-shrink: 0; display: grid; place-items: center; border-radius: 50%; border: 2.5px solid var(--cor-borda); overflow: hidden; }
.agenda-item-nome { font-weight: 600; font-size: 13px; line-height: 1.2; }
.agenda-item-esp { font-size: 11px; color: var(--cor-tinta-suave); }

.agenda-cartao-grade { flex: 1; min-height: 0; display: flex; flex-direction: column; background: var(--cor-superficie); border: 1px solid var(--cor-borda); border-radius: 14px; padding: 10px 12px 8px; }
.agenda-grade-cab, .agenda-grade-corpo { display: grid; grid-template-columns: 48px repeat(var(--agenda-dias, 6), minmax(0, 1fr)); column-gap: 2px; }
.agenda-grade-corpo { flex: 1; min-height: 360px; }
.agenda-grade-dia { text-align: center; font-size: 12px; color: var(--cor-tinta-suave); padding: 4px 0; border-radius: 6px; }
.agenda-grade-dia.hoje { background: var(--cor-marca-clara); color: var(--cor-marca); }
.agenda-coluna-horas { position: relative; }
.agenda-rotulo-hora { position: absolute; right: 6px; transform: translateY(-50%); font-size: 10.5px; color: var(--cor-tinta-suave); }
.agenda-coluna-grade { position: relative; background: var(--cor-fundo-alt); border-radius: 4px; overflow: hidden; }
.agenda-coluna-grade.hoje { background: var(--cor-marca-clara); }
.agenda-coluna-grade.editavel { cursor: pointer; }
.agenda-linha-hora { position: absolute; left: 0; right: 0; border-top: 1px solid var(--cor-borda); pointer-events: none; }
.agenda-linha-hora.meia { border-top-style: dashed; opacity: .6; }
.agenda-bloco-consulta {
    position: absolute; left: 2px; right: 2px; z-index: 2; overflow: hidden; border-radius: 6px; padding: 2px 6px;
    background: var(--cor-superficie); color: var(--cor-tinta); border: 1px solid var(--cor-borda); border-left-width: 4px;
    line-height: 1.25; box-shadow: var(--sombra-sm); cursor: pointer; transition: opacity .1s ease;
}
.agenda-bloco-consulta[draggable="true"] { cursor: grab; }
.agenda-bloco-consulta.arrastando { opacity: .4; }
.agenda-bloco-consulta:hover { box-shadow: var(--sombra-md); z-index: 3; }
.agenda-bloco-hora { font-size: 11px; font-weight: 700; white-space: nowrap; }
.agenda-bloco-nome { font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* "Sessão Desmarcada": sem cor de status (é branca), então borda tracejada + riscado. */
.agenda-bloco-consulta.status-desmarcada { color: var(--cor-tinta-suave); border-style: dashed; text-decoration: line-through; }

@media (max-width: 900px) {
    /* No celular a página volta a rolar; a lista de profissionais vira uma faixa horizontal. */
    .shell-agenda .shell-conteudo { height: auto; padding: var(--esp-4); }
    .agenda-corpo { grid-template-columns: 1fr; }
    .agenda-lista-profs input { display: none; }
    .agenda-lista-profs ul { display: flex; gap: 6px; overflow-x: auto; padding: 6px; }
    .agenda-item-prof { width: auto; flex-shrink: 0; white-space: nowrap; }
    .agenda-cartao-grade { overflow-x: auto; }
    .agenda-grade-cab, .agenda-grade-corpo { grid-template-columns: 40px repeat(var(--agenda-dias, 6), minmax(90px, 1fr)); }
    .agenda-grade-corpo { min-height: 640px; }
}
```

Keep `.agenda-ponto-cor` (still used). Check nothing else uses the removed classes: `grep -rn "agenda-pill\|agenda-slot-vazio\|agenda-grade-horaria" frontend/` → only old CSS (now removed).

- [ ] **Step 7: Syntax check + commit**

Run: `node --check frontend/js/views/agenda.js && node --check frontend/js/agenda_faixa.js && node --test frontend/tests/*.test.js`
Expected: no output from `--check`, tests pass.

```bash
git add frontend/js/views/agenda.js frontend/css/components.css
git commit -F - <<'EOF'
Agenda: lista lateral de profissionais e semana inteira numa tela

A grade "Por Profissional" usa a faixa de horário da clínica (ou a
automática), posicionada em % da altura disponível; clique e arraste
encaixam de 15 em 15 min.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 6: Verificação no navegador, docs e PR 2

**Files:**
- Modify: `CLAUDE.md` (sections 5, 6, 7, 8)
- Scratch only (not committed): Playwright script in the session scratchpad

- [ ] **Step 1: Local server with seed data**

From `backend/`: `rm -f encanto.db && PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe seed.py`, then start `app.py` in the background (same env vars).

- [ ] **Step 2: Browser checks (Playwright)**

Use the Playwright MCP tools if connected; otherwise `uv run --with playwright python <script>` after `uv run --with playwright playwright install chromium`. Log in through the UI as `andre@clinicaencantar.com.br` / `gestor123` (gestor) and later `camila@clinicaencantar.com.br` / `prof123`. Create test consultas through the UI or `POST /api/agenda` with the token from `localStorage.encanto_token`, in the current week, including one at 19:30 and one on Sunday. Check, at viewport **1366×768**:

1. `#/gestor/agenda` opens in "Por Profissional"; `document.documentElement.scrollHeight <= window.innerHeight` (no page scroll); screenshot.
2. Lista lateral: filtro esconde/mostra profissionais; clicar troca a grade.
3. Sem horário configurado: faixa 08:00–18:00 esticada até 20:00 pela consulta das 19:30; coluna de domingo aparece só na semana com consulta no domingo.
4. Configurações → 08:00–19:15 → voltar à agenda: rótulo final antes de 19:15, consulta das 19:30 ainda visível (faixa esticada).
5. Clicar num horário livre abre "Nova consulta" com hora múltipla de 15 min dentro da faixa; arrastar uma consulta remarca (toast com o horário).
6. "Geral da Clínica": item "Todos" ativo; Lista/Semana/Mês funcionam; clicar num profissional abre a agenda dele.
7. Profissional (camila): vê a própria agenda editável; agenda de colega mostra "somente visualização".
8. Viewport 390×844: lista vira faixa horizontal, página rola, grade legível.
9. Console sem erros.

Fix anything found (with a commit per fix) before continuing.

- [ ] **Step 3: Full test run**

From `backend/`: full pytest suite → all pass. From repo root: `node --test frontend/tests/*.test.js` → all pass.

- [ ] **Step 4: Update CLAUDE.md**

- Section 5: new item `m) Horário de funcionamento + novo layout da agenda (24/09/2026)` summarizing: columns `organizacoes.agenda_hora_inicio/fim` (migração `migracoes/migracao_horario_agenda.sql` / `migrar_horario_agenda.py`), campo em Configurações, `agenda_faixa.js` + `node --test` (job `js` no CI), layout `.shell-agenda`, `paraChaveDia` local.
- Section 6: a "Grade da agenda" bullet: posições em % da faixa de `calcularFaixaAgenda`; clique/arraste via `minutoNaFaixa` (15 min); qualquer mudança na grade passa por `agenda_faixa.js` e seus testes.
- Section 7: pending production step — run the migration (until the user confirms it ran).
- Section 8 table: rows for `frontend/js/agenda_faixa.js` / `frontend/tests/agenda_faixa.test.js` and `frontend/js/views/agenda.js`.
- Update the test count in "Estado atual".

Commit: `git add CLAUDE.md && git commit` (message ending with the co-author line).

- [ ] **Step 5: Push, PR, CI — then ask before merging**

```bash
git push -u origin agenda-layout-horario
"/c/Program Files/GitHub CLI/gh.exe" pr create --base main --title "Agenda numa tela só, lista de profissionais e horário da clínica" --body "..."
"/c/Program Files/GitHub CLI/gh.exe" pr checks <N> --watch --interval 20
```

PR body: summary, screenshots description, **passo manual em produção** (rodar `backend/migracoes/migracao_horario_agenda.sql` no SQL Editor do Supabase ou `python3 migrar_horario_agenda.py` conferindo `(Postgres)`, depois `git pull` + `touch tmp/restart.txt`), test counts, Claude Code line.

With CI green: **stop and ask the user to approve the merge** (schema change). Tell them the deploy order: migração no Supabase **antes** do `git pull` no servidor (o `CAMPOS_ORG` novo lê as colunas no login — sem elas, `/auth/me` quebra).
