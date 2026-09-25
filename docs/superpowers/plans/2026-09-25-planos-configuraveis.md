# Planos configuráveis + módulos extras — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Admin creates/edits plans on screen, choosing modules with checkboxes (with live inheritance from a base plan and an optional "available until" date), and grants extra modules per clinic; patients become unlimited in every plan.

**Architecture:** Plan→module mapping moves from `MODULOS_POR_PLANO` (code) to a new table `planos_modulos` + `planos.plano_base_id` (live inheritance, resolved recursively in `modulos_service`). Per-clinic extras reuse `modulos_clinica.liberado_admin` for any optional module (the Pandoo-only special case goes away). Canonical default plans live in a new `backend/planos_padrao.py`, shared by the migration, `seed.py`, `seed_producao.py` and tests.

**Tech Stack:** Flask + SQLite (tests) / Postgres (prod) via `backend/db.py`, pytest, vanilla JS admin screens, Playwright (Python via `uv`) for the browser pass.

**Spec:** `docs/superpowers/specs/2026-09-25-planos-configuraveis-design.md`

## Global Constraints

- Branch `planos-configuraveis` (spec already committed). Schema change + plans/billing area → **ask the user before merging**; migration in Supabase **before** `git pull`.
- Result after migration must equal today's behavior: `starter` → no optional module; `pro` → `financeiro, ia, analytics_avancado, integracoes, importacao_pacientes`; `enterprise` → base `pro` + `white_label`. Pandoo in no plan. Existing `liberado_admin` rows (Pandoo released) keep working.
- Inheritance: only modules (not price/limits); child only adds; max depth 10; cycles refused on write (400) and ignored on read (no infinite loop).
- `disponivel_ate` (`YYYY-MM-DD`, optional): after that date the plan cannot be assigned (clinic creation / plan change); clinics already on it keep everything.
- Patients unlimited: no code path blocks by `limite_pacientes`; the migration sets it NULL; the field disappears from the admin UI and from `/admin/clinicas` payloads. Professional/secretary limits unchanged.
- Tests: from `backend/`, `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q <files>`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; comments in pt-BR explaining the why, citing "planos configuráveis, 25/09/2026".

## Review Focus

1. **A clinic loses a module after the migration** (e.g. enterprise without `white_label`, pro without `importacao_pacientes`, a Pandoo extra dropped) → must not happen. Task 1 test compares the post-migration result with the old mapping for each default plan.
2. **Changing a base plan** (add/remove a module) → every descendant changes immediately, including grandchildren; removing from the child a module that comes from the base is impossible. Task 2/3 tests.
3. **Cycle via PUT** (A base B, then B base A; or A base A) → 400, nothing saved. Task 3.
4. **Expired promotion** → cannot be picked when creating a clinic or changing plans (400), but a clinic already on it still has its modules and appears normally. Task 3.
5. **Extras** → the gestor cannot switch off an extra (toggle refused), a module already in the plan cannot be granted as extra (400), and removing the extra removes access immediately. Task 4.

---

### Task 1: Tabelas, planos padrão e migração

**Files:**
- Create: `backend/planos_padrao.py`
- Modify: `backend/schema.sql`, `backend/schema_postgres.sql`
- Create: `backend/migracoes/migracao_planos_configuraveis.sql`, `backend/migrar_planos_configuraveis.py`
- Modify: `backend/seed.py`, `backend/seed_producao.py` (write `planos_modulos` + `plano_base_id`, `limite_pacientes` NULL)
- Modify: `.github/workflows/db-setup.yml`, `.github/workflows/tests.yml` (smoke: apply the new `.sql`)
- Test: `backend/tests/test_planos_configuraveis_migracao.py`

**Interfaces:**
- Produces:
  - table `planos_modulos(id, plano_id → planos.id, modulo_codigo TEXT NOT NULL, UNIQUE(plano_id, modulo_codigo))`; `planos.plano_base_id INTEGER NULL REFERENCES planos(id)`; `planos.disponivel_ate TEXT NULL`
  - `planos_padrao.MODULOS_PADRAO = {"starter": [], "pro": ["financeiro","ia","analytics_avancado","integracoes","importacao_pacientes"], "enterprise": ["white_label"]}` and `planos_padrao.BASE_PADRAO = {"enterprise": "pro"}`
  - `planos_padrao.aplicar_modulos_padrao() -> None` — for each default code that exists in `planos` and has **no** rows in `planos_modulos`, inserts its own modules and sets `plano_base_id` from `BASE_PADRAO`; also `UPDATE planos SET limite_pacientes = NULL`. Idempotent, never overwrites Admin changes.
  - `planos_padrao.criar_planos_padrao_para_teste() -> None` — inserts the three default plans (codes/nomes/preços) if missing, then `aplicar_modulos_padrao()`. Used by tests that need `pro`/`enterprise`.

- [ ] **Step 1: Failing test** — `backend/tests/test_planos_configuraveis_migracao.py`:

```python
"""Planos configuráveis (25/09/2026): a migração leva o mapa antigo de
módulos por plano (que estava no código) para o banco sem mudar o resultado."""
import db
import planos_padrao


def _modulos(codigo):
    from modulos_service import modulos_do_plano
    return sorted(modulos_do_plano(codigo))


def test_resultado_igual_ao_mapa_antigo(db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    assert _modulos("starter") == []
    assert _modulos("pro") == sorted(["financeiro", "ia", "analytics_avancado", "integracoes", "importacao_pacientes"])
    assert _modulos("enterprise") == sorted(["financeiro", "ia", "analytics_avancado", "integracoes",
                                              "importacao_pacientes", "white_label"])


def test_enterprise_herda_de_pro(db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    ent = db.query_one("SELECT plano_base_id FROM planos WHERE codigo = 'enterprise'")
    pro = db.query_one("SELECT id FROM planos WHERE codigo = 'pro'")
    assert ent["plano_base_id"] == pro["id"]


def test_idempotente_e_nao_sobrescreve_ajuste_do_admin(db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    pro = db.query_one("SELECT id FROM planos WHERE codigo = 'pro'")["id"]
    db.execute("DELETE FROM planos_modulos WHERE plano_id = ? AND modulo_codigo = 'ia'", (pro,))
    planos_padrao.aplicar_modulos_padrao()
    assert "ia" not in _modulos("pro")


def test_pacientes_ilimitados(db_ctx):
    db.execute("INSERT INTO planos (codigo, nome, preco_mensal_centavos, limite_pacientes) VALUES ('pro', 'Pro', 1, 30)")
    planos_padrao.aplicar_modulos_padrao()
    assert db.query_one("SELECT limite_pacientes FROM planos WHERE codigo = 'pro'")["limite_pacientes"] is None
```

- [ ] **Step 2: Run — expect FAIL** (`No module named 'planos_padrao'`).

- [ ] **Step 3: Schema** — `schema.sql` / `schema_postgres.sql`: in `planos`, after `ativo INTEGER DEFAULT 1` add (with the comma on the previous line):
```sql
    -- Planos configuráveis (25/09/2026): herança viva de módulos e validade
    -- de promoção. Ver planos_modulos e modulos_service.modulos_do_plano.
    plano_base_id           INTEGER REFERENCES planos(id),
    disponivel_ate          TEXT
```
and right after the `planos` table:
```sql
-- Módulos marcados no PRÓPRIO plano (os herdados vêm de plano_base_id).
CREATE TABLE planos_modulos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,   -- Postgres: SERIAL PRIMARY KEY
    plano_id        INTEGER NOT NULL REFERENCES planos(id),
    modulo_codigo   TEXT NOT NULL,
    UNIQUE(plano_id, modulo_codigo)
);
```

- [ ] **Step 4: `backend/planos_padrao.py`**

```python
"""
Planos configuráveis (25/09/2026): o mapa de módulos por plano saiu do
código (antes: modulos_service.MODULOS_POR_PLANO) e foi para o banco
(planos_modulos + planos.plano_base_id). Este arquivo guarda só o PONTO DE
PARTIDA dos três planos originais, usado pela migração, pelos seeds e pelos
testes. Depois disso quem manda é o Admin, pela tela.
"""
from db import query, query_one, execute

MODULOS_PADRAO = {
    "starter": [],
    "pro": ["financeiro", "ia", "analytics_avancado", "integracoes", "importacao_pacientes"],
    "enterprise": ["white_label"],
}
BASE_PADRAO = {"enterprise": "pro"}
PLANOS_PADRAO_TESTE = [("starter", "Starter", 14970, 1), ("pro", "Pro", 29970, 2), ("enterprise", "Enterprise", 149700, 3)]


def aplicar_modulos_padrao():
    """Idempotente: só preenche plano padrão que ainda não tem nenhuma linha
    em planos_modulos (não desfaz ajuste feito pelo Admin)."""
    for codigo, modulos in MODULOS_PADRAO.items():
        plano = query_one("SELECT id, plano_base_id FROM planos WHERE codigo = ?", (codigo,))
        if not plano:
            continue
        ja_tem = query_one("SELECT 1 FROM planos_modulos WHERE plano_id = ?", (plano["id"],))
        if ja_tem or (not modulos and plano.get("plano_base_id")):
            continue
        for m in modulos:
            execute("INSERT INTO planos_modulos (plano_id, modulo_codigo) VALUES (?, ?)", (plano["id"], m))
        base = BASE_PADRAO.get(codigo)
        if base and not plano.get("plano_base_id"):
            base_row = query_one("SELECT id FROM planos WHERE codigo = ?", (base,))
            if base_row:
                execute("UPDATE planos SET plano_base_id = ? WHERE id = ?", (base_row["id"], plano["id"]))
    execute("UPDATE planos SET limite_pacientes = NULL WHERE limite_pacientes IS NOT NULL")


def criar_planos_padrao_para_teste():
    for codigo, nome, preco, ordem in PLANOS_PADRAO_TESTE:
        if not query_one("SELECT 1 FROM planos WHERE codigo = ?", (codigo,)):
            execute("INSERT INTO planos (codigo, nome, preco_mensal_centavos, ordem) VALUES (?, ?, ?, ?)",
                    (codigo, nome, preco, ordem))
    aplicar_modulos_padrao()
```

(`planos_modulos` has an `id`, so `db.execute`'s `RETURNING id` works on Postgres.)

- [ ] **Step 5: Migration** — `backend/migracoes/migracao_planos_configuraveis.sql` (Postgres, idempotent):
```sql
-- Migração incremental — planos configuráveis (25/09/2026). Idempotente.
ALTER TABLE planos ADD COLUMN IF NOT EXISTS plano_base_id INTEGER REFERENCES planos(id);
ALTER TABLE planos ADD COLUMN IF NOT EXISTS disponivel_ate TEXT;
CREATE TABLE IF NOT EXISTS planos_modulos (
    id SERIAL PRIMARY KEY,
    plano_id INTEGER NOT NULL REFERENCES planos(id),
    modulo_codigo TEXT NOT NULL,
    UNIQUE(plano_id, modulo_codigo)
);
-- Mesmo resultado do mapa que estava no código (só preenche se o plano ainda não tem linhas).
INSERT INTO planos_modulos (plano_id, modulo_codigo)
SELECT p.id, m.codigo FROM planos p
JOIN (VALUES ('pro','financeiro'),('pro','ia'),('pro','analytics_avancado'),('pro','integracoes'),
             ('pro','importacao_pacientes'),('enterprise','white_label')) AS m(plano, codigo) ON m.plano = p.codigo
WHERE NOT EXISTS (SELECT 1 FROM planos_modulos x WHERE x.plano_id = p.id)
ON CONFLICT (plano_id, modulo_codigo) DO NOTHING;
UPDATE planos SET plano_base_id = (SELECT id FROM planos WHERE codigo = 'pro')
WHERE codigo = 'enterprise' AND plano_base_id IS NULL;
-- Pacientes ilimitados em todos os planos (decisão do usuário, 25/09/2026).
UPDATE planos SET limite_pacientes = NULL;
```
Careful with the `NOT EXISTS`: for `pro`, the first `('pro', …)` row inserted makes the next ones fail the `NOT EXISTS` only if the statement re-evaluates per row — in Postgres the subquery sees the snapshot at statement start, so all `pro` rows are inserted in one go. Keep it as one statement.

`backend/migrar_planos_configuraveis.py` — same shape as `migrar_pandoo.py`: Postgres → run the `.sql` statements (split by `;`, skipping comment lines); SQLite → add the two columns via PRAGMA check, `CREATE TABLE IF NOT EXISTS planos_modulos (...)` (SQLite DDL), then `planos_padrao.aplicar_modulos_padrao()`. Print `(Postgres)`/`(SQLite)` at the end.

Seeds: in `seed.py` and `seed_producao.py`, keep inserting the plans (set `limite_pacientes` to `None` for all three) and call `planos_padrao.aplicar_modulos_padrao()` right after the plans are inserted (adapt: `seed.py` uses a raw `conn`; commit before calling, since `aplicar_modulos_padrao` uses `db`).

Workflows: `db-setup.yml` step "planos configuráveis" (same shape as the others); `tests.yml` smoke: `psql ... -f migracoes/migracao_planos_configuraveis.sql`.

- [ ] **Step 6: Run** — the 4 tests pass **after Task 2** (they call `modulos_do_plano`, which still reads the old dict). Run now and expect `test_resultado_igual_ao_mapa_antigo`/`test_enterprise_herda_de_pro`/`test_pacientes_ilimitados`/`test_idempotente…` → the first passes by accident (old dict), `test_idempotente…` FAILS (old dict ignores the DB). That failure is the RED for Task 2. Commit Task 1 with the schema/migration/seed changes: "Planos configuráveis: tabela de módulos por plano e migração". Run `migrar_planos_configuraveis.py` twice on a DB built from `git show main:backend/schema.sql` (+ a `pro` plan row with `limite_pacientes = 30`): adds, then skips; `pro` has the 5 modules; `limite_pacientes` NULL.

### Task 2: Regras de módulos lidas do banco (herança + extras)

**Files:**
- Modify: `backend/modulos_service.py`
- Modify: `backend/tests/test_pandoo_modulo.py`, `backend/tests/test_idor_financeiro.py`, `backend/tests/test_importacao_pacientes.py` (use `criar_planos_padrao_para_teste()` where they rely on `pro`)
- Test: `backend/tests/test_planos_configuraveis_modulos.py`

**Interfaces:**
- Produces:
  - `modulos_do_plano(codigo_plano) -> list[str]` (own + inherited, sorted, cycle-safe, depth ≤ 10)
  - `modulos_proprios_do_plano(plano_id) -> list[str]`, `cadeia_de_bases(plano_id) -> list[int]` (ids from the direct base upwards)
  - `modulos_extras_clinica(organizacao_id) -> set[str]`
  - `modulos_habilitados_clinica(org_id, codigo_plano)` = plan modules with `habilitado` ∪ extras (`liberado_admin = 1`)
  - `definir_liberacao_admin(org_id, codigo, liberado)` — any code in `MODULOS_OPCIONAIS`
  - `CODIGOS_OPCIONAIS = {m["codigo"] for m in MODULOS_OPCIONAIS}`
  - Removed: `MODULOS_POR_PLANO`, `MODULOS_SO_ADMIN` (fix every import — `admin_bp.py`)

- [ ] **Step 1: Failing tests** — `backend/tests/test_planos_configuraveis_modulos.py`:

```python
"""Planos configuráveis (25/09/2026): módulos por plano vêm do banco, com
herança viva, e extras por clínica valem para qualquer módulo."""
import db
import planos_padrao
from factories import DuasClinicas
from modulos_service import (modulos_do_plano, modulos_habilitados_clinica, modulo_ativo_para_clinica,
                             definir_liberacao_admin)


def _plano(codigo, base=None, modulos=()):
    base_id = db.query_one("SELECT id FROM planos WHERE codigo = ?", (base,))["id"] if base else None
    pid = db.execute("INSERT INTO planos (codigo, nome, preco_mensal_centavos, plano_base_id) VALUES (?, ?, 0, ?)",
                     (codigo, codigo.title(), base_id))
    for m in modulos:
        db.execute("INSERT INTO planos_modulos (plano_id, modulo_codigo) VALUES (?, ?)", (pid, m))
    return pid


def test_heranca_em_cadeia_e_viva(db_ctx):
    a = _plano("a", modulos=["financeiro"])
    _plano("b", base="a", modulos=["ia"])
    _plano("c", base="b", modulos=["pandoo"])
    assert modulos_do_plano("c") == ["financeiro", "ia", "pandoo"]
    db.execute("INSERT INTO planos_modulos (plano_id, modulo_codigo) VALUES (?, 'white_label')", (a,))
    assert "white_label" in modulos_do_plano("c")  # mudou a base → mudou o neto na hora


def test_ciclo_no_banco_nao_trava(db_ctx):
    a = _plano("a", modulos=["financeiro"])
    b = _plano("b", base="a", modulos=["ia"])
    db.execute("UPDATE planos SET plano_base_id = ? WHERE id = ?", (b, a))  # ciclo forçado direto no banco
    assert modulos_do_plano("a") == ["financeiro", "ia"]


def test_plano_inexistente_nao_libera_nada(db_ctx):
    assert modulos_do_plano("nao-existe") == []


def test_clinica_recebe_modulos_do_plano_e_extras(db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET plano = 'starter' WHERE id = ?", (cen.org_a,))
    assert modulos_habilitados_clinica(cen.org_a, "starter") == set()
    definir_liberacao_admin(cen.org_a, "financeiro", True)
    assert modulo_ativo_para_clinica(cen.org_a, "starter", "financeiro")
    definir_liberacao_admin(cen.org_a, "financeiro", False)
    assert not modulo_ativo_para_clinica(cen.org_a, "starter", "financeiro")


def test_gestor_desligou_modulo_do_plano(db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    assert modulo_ativo_para_clinica(cen.org_a, "pro", "ia")
    db.execute("UPDATE modulos_clinica SET habilitado = 0 WHERE organizacao_id = ? AND modulo_codigo = 'ia'", (cen.org_a,))
    assert not modulo_ativo_para_clinica(cen.org_a, "pro", "ia")
```

- [ ] **Step 2: Run — expect FAIL** (old dict: `c` → `[]`).

- [ ] **Step 3: Implement** in `modulos_service.py`:
  - delete `MODULOS_POR_PLANO` and `MODULOS_SO_ADMIN` (+ their comments); keep `MODULOS_OPCIONAIS` (drop the `"so_admin": True` key from the Pandoo entry); add `CODIGOS_OPCIONAIS`.
  - ```python
    _PROFUNDIDADE_MAX = 10

    def cadeia_de_bases(plano_id):
        """Ids das bases, da mais próxima para cima; para em ciclo ou em 10 níveis."""
        vistos, atual, cadeia = {plano_id}, plano_id, []
        for _ in range(_PROFUNDIDADE_MAX):
            linha = query_one("SELECT plano_base_id FROM planos WHERE id = ?", (atual,))
            base = linha and linha.get("plano_base_id")
            if not base or base in vistos:
                break
            cadeia.append(base)
            vistos.add(base)
            atual = base
        return cadeia

    def modulos_proprios_do_plano(plano_id):
        return sorted(l["modulo_codigo"] for l in query(
            "SELECT modulo_codigo FROM planos_modulos WHERE plano_id = ?", (plano_id,)))

    def modulos_do_plano(codigo_plano):
        plano = query_one("SELECT id FROM planos WHERE codigo = ?", (codigo_plano,))
        if not plano:
            return []
        modulos = set()
        for pid in [plano["id"]] + cadeia_de_bases(plano["id"]):
            modulos.update(modulos_proprios_do_plano(pid))
        return sorted(m for m in modulos if m in CODIGOS_OPCIONAIS)

    def modulos_extras_clinica(organizacao_id):
        return {l["modulo_codigo"] for l in query(
            "SELECT modulo_codigo FROM modulos_clinica WHERE organizacao_id = ? AND liberado_admin = 1 AND habilitado = 1",
            (organizacao_id,)) if l["modulo_codigo"] in CODIGOS_OPCIONAIS}
    ```
  - `modulos_habilitados_clinica`: plan part as today (`_garantir_linhas_clinica` + `habilitado` filter against `modulos_do_plano`) **∪** `modulos_extras_clinica(org)`.
  - `definir_liberacao_admin`: reject codes outside `CODIGOS_OPCIONAIS` (raise `ValueError`).
- [ ] **Step 4: Fix dependents** — `admin_bp.py` import (`MODULOS_SO_ADMIN` gone: temporarily compute `o["modulos_so_admin"]` from `modulos_extras_clinica` until Task 4 replaces it); `modulos_bp.py` unchanged API for now. Tests relying on `pro`: add `planos_padrao.criar_planos_padrao_para_teste()` at the start of each test in `test_idor_financeiro.py` (its helper that switches to `pro`) and `test_importacao_pacientes.py` (where it sets `plano = 'pro'`), removing their manual `INSERT INTO planos ('pro', …)` if it would collide (the limit test is rewritten in Task 5 — mark it `pytest.mark.skip(reason="reescrito na Task 5")` for now and ledger it). `test_pandoo_modulo.py`: `test_admin_so_libera_modulo_so_admin` becomes "Admin libera qualquer módulo opcional como extra" (expects 200 for `financeiro`; 400 for `"inexistente"`); keep the other tests; update `test_listagens_mostram_o_estado` in Task 4.
- [ ] **Step 5: Run** new tests + `test_planos_configuraveis_migracao.py` (now all 4 pass) + the three adjusted files → PASS. Commit — "Planos configuráveis: módulos lidos do banco, com herança e extras".

### Task 3: API de planos (listar, criar, editar, validade)

**Files:**
- Modify: `backend/blueprints/admin_bp.py` (`listar_planos`, new `criar_plano`, `atualizar_plano_definicao`, `_plano_valido`)
- Test: `backend/tests/test_planos_configuraveis_api.py`

**Interfaces:**
- Produces:
  - `GET /api/admin/planos[?incluir_inativos=1]` → each plan + `plano_base_id, plano_base_nome, disponivel_ate, promocao_encerrada, modulos_proprios, modulos_herdados, modulos_efetivos, total_clinicas` (inativos only for admin with the flag). Also `GET /api/admin/modulos-disponiveis` → `MODULOS_OPCIONAIS` (for the form's checkboxes).
  - `POST /api/admin/planos` → 201 `{"codigo"}`
  - `PUT /api/admin/planos/<codigo>` accepts `plano_base_id, disponivel_ate, modulos, ativo` (+ existing fields); ignores `limite_pacientes`.

- [ ] **Step 1: Failing tests** — `backend/tests/test_planos_configuraveis_api.py`:

```python
"""Planos configuráveis (25/09/2026): API do Admin."""
from datetime import date, timedelta

import db
import planos_padrao
from factories import DuasClinicas, novo_usuario
from conftest import autenticado


def _admin():
    return novo_usuario(None, "Admin", "admin@saas.com", "admin_master")


def _c(client):
    return autenticado(client, _admin())


def test_criar_plano_a_partir_de_outro(client, db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    c = _c(client)
    pro = db.query_one("SELECT id FROM planos WHERE codigo = 'pro'")["id"]
    r = c.post("/api/admin/planos", json={"nome": "Promoção Primavera", "preco_mensal_centavos": 9900,
                                          "plano_base_id": pro, "modulos": ["pandoo"], "disponivel_ate": "2099-12-31"})
    assert r.status_code == 201, r.get_data(as_text=True)
    codigo = r.get_json()["codigo"]
    assert codigo == "promocao-primavera"
    p = next(x for x in c.get("/api/admin/planos").get_json() if x["codigo"] == codigo)
    assert p["modulos_proprios"] == ["pandoo"]
    assert "financeiro" in p["modulos_herdados"] and "pandoo" in p["modulos_efetivos"]
    assert p["plano_base_nome"] == "Pro" and p["promocao_encerrada"] is False


def test_codigo_unico_e_nome_obrigatorio(client, db_ctx):
    c = _c(client)
    assert c.post("/api/admin/planos", json={"nome": "Básico", "preco_mensal_centavos": 0}).get_json()["codigo"] == "basico"
    assert c.post("/api/admin/planos", json={"nome": "Basico", "preco_mensal_centavos": 0}).get_json()["codigo"] == "basico-2"
    assert c.post("/api/admin/planos", json={"nome": "  ", "preco_mensal_centavos": 0}).status_code == 400


def test_modulo_desconhecido_recusado(client, db_ctx):
    assert _c(client).post("/api/admin/planos", json={"nome": "X", "preco_mensal_centavos": 0, "modulos": ["voar"]}).status_code == 400


def test_ciclo_recusado(client, db_ctx):
    c = _c(client)
    a = c.post("/api/admin/planos", json={"nome": "A", "preco_mensal_centavos": 0}).get_json()["codigo"]
    a_id = db.query_one("SELECT id FROM planos WHERE codigo = ?", (a,))["id"]
    b = c.post("/api/admin/planos", json={"nome": "B", "preco_mensal_centavos": 0, "plano_base_id": a_id}).get_json()["codigo"]
    b_id = db.query_one("SELECT id FROM planos WHERE codigo = ?", (b,))["id"]
    assert c.put(f"/api/admin/planos/{a}", json={"plano_base_id": b_id}).status_code == 400
    assert c.put(f"/api/admin/planos/{a}", json={"plano_base_id": a_id}).status_code == 400
    assert db.query_one("SELECT plano_base_id FROM planos WHERE id = ?", (a_id,))["plano_base_id"] is None


def test_editar_modulos_da_base_muda_o_filho(client, db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    c = _c(client)
    c.put("/api/admin/planos/pro", json={"modulos": ["financeiro", "ia", "analytics_avancado", "integracoes", "importacao_pacientes", "pandoo"]})
    ent = next(x for x in c.get("/api/admin/planos").get_json() if x["codigo"] == "enterprise")
    assert "pandoo" in ent["modulos_efetivos"] and "pandoo" in ent["modulos_herdados"]


def test_nao_desativa_base_de_plano_ativo(client, db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    c = _c(client)
    r = c.put("/api/admin/planos/pro", json={"ativo": False})
    assert r.status_code == 409 and "Enterprise" in r.get_json()["erro"]
    assert c.put("/api/admin/planos/starter", json={"ativo": False}).status_code == 200


def test_promocao_vencida_nao_e_atribuivel_mas_clinica_nela_continua(client, db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    c = _c(client)
    ontem = (date.today() - timedelta(days=1)).isoformat()
    codigo = c.post("/api/admin/planos", json={"nome": "Promo", "preco_mensal_centavos": 100, "modulos": ["ia"],
                                               "disponivel_ate": "2099-01-01"}).get_json()["codigo"]
    cen = DuasClinicas()
    assert c.put(f"/api/admin/clinicas/{cen.org_a}/plano", json={"plano": codigo}).status_code == 200
    c.put(f"/api/admin/planos/{codigo}", json={"disponivel_ate": ontem})
    assert c.put(f"/api/admin/clinicas/{cen.org_b}/plano", json={"plano": codigo}).status_code == 400
    from modulos_service import modulo_ativo_para_clinica
    assert modulo_ativo_para_clinica(cen.org_a, codigo, "ia")
    p = next(x for x in c.get("/api/admin/planos").get_json() if x["codigo"] == codigo)
    assert p["promocao_encerrada"] is True and p["total_clinicas"] == 1


def test_limite_de_pacientes_ignorado(client, db_ctx):
    c = _c(client)
    codigo = c.post("/api/admin/planos", json={"nome": "L", "preco_mensal_centavos": 0, "limite_pacientes": 5}).get_json()["codigo"]
    assert db.query_one("SELECT limite_pacientes FROM planos WHERE codigo = ?", (codigo,))["limite_pacientes"] is None


def test_gestor_nao_cria_nem_edita_plano(client, db_ctx):
    cen = DuasClinicas()
    g = autenticado(client, cen.gestor_a)
    assert g.post("/api/admin/planos", json={"nome": "X", "preco_mensal_centavos": 0}).status_code == 403
```

Check first the body shape of `PUT /api/admin/clinicas/<id>/plano` (`grep -n "def atualizar_plano" -A12 backend/blueprints/admin_bp.py`) and adjust `{"plano": codigo}` if the key differs.

- [ ] **Step 2: Run — expect FAIL**.

- [ ] **Step 3: Implement** in `admin_bp.py`:
  - helpers:
    ```python
    import re, unicodedata
    from datetime import date

    def _slug_plano(nome):
        base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
        base = re.sub(r"[^a-z0-9]+", "-", base).strip("-") or "plano"
        codigo, n = base, 2
        while query_one("SELECT 1 FROM planos WHERE codigo = ?", (codigo,)):
            codigo, n = f"{base}-{n}", n + 1
        return codigo

    def _promocao_encerrada(plano):
        return bool(plano.get("disponivel_ate")) and plano["disponivel_ate"] < date.today().isoformat()
    ```
  - `_plano_valido(codigo)`: `SELECT * ... ativo = 1` and `not _promocao_encerrada(p)`.
  - `_validar_definicao(body, plano_atual=None) -> (dados, erro)`: shared by POST/PUT — nome (strip, required), preço (≥ 0 int), limites prof/sec (same rules as today), cor, recursos, `modulos` (list ⊆ `CODIGOS_OPCIONAIS` else 400 "Módulo desconhecido: X"), `plano_base_id` (exists; not itself; not a descendant: `plano_atual["id"] in cadeia_de_bases(nova_base) or nova_base == plano_atual["id"]` → 400 "Esse plano base criaria um ciclo."), `disponivel_ate` (`""`/None → None; else `date.fromisoformat` ok), `ativo`.
  - `POST /planos` (admin_master): validate → `INSERT INTO planos (codigo, nome, preco_mensal_centavos, limite_profissionais, limite_secretarias, recursos_json, cor, ordem, plano_base_id, disponivel_ate, ativo)` with `ordem = (SELECT COALESCE(MAX(ordem),0)+1)` computed in Python; insert `planos_modulos`; `log_auditoria(None, u["id"], "criar_plano", "plano", None, codigo)`; 201 `{"codigo"}`.
  - `PUT /planos/<codigo>`: validate; when `ativo` goes false and there is an active plan with `plano_base_id = this.id` → 409 `f"Este plano é base de: {nomes}. Troque a base deles antes de desativar."`; update columns (drop `limite_pacientes` from the UPDATE); when `modulos` is present → replace this plan's rows in `planos_modulos` (DELETE + INSERT).
  - `GET /planos`: admin_master sees inactive with `?incluir_inativos=1`; for each plan add the fields listed in Interfaces (`modulos_herdados` = efetivos − próprios; `total_clinicas` = `COUNT(*) FROM organizacoes WHERE plano = codigo`). Gestor: unchanged (active only) — also hide `promocao_encerrada` plans? No: the gestor listing is informational; keep active ones.
  - `GET /modulos-disponiveis` (admin_master): `jsonify(MODULOS_OPCIONAIS)`.
- [ ] **Step 4: Run — expect PASS** + existing admin tests (`grep -l "/api/admin/planos\|/api/admin/clinicas" tests/*.py`).
- [ ] **Step 5: Commit** — "Planos configuráveis: API do Admin (criar, editar, herança, validade)".

### Task 4: Módulos da clínica no Admin e para o gestor

**Files:**
- Modify: `backend/blueprints/admin_bp.py` (`_enriquecer_clinica`, `liberar_modulo_so_admin` → generic)
- Modify: `backend/blueprints/modulos_bp.py` (`listar`: `origem`; toggle refuses extras)
- Modify: `backend/tests/test_pandoo_modulo.py` (`test_listagens_mostram_o_estado`)
- Test: `backend/tests/test_planos_configuraveis_extras.py`

**Interfaces:**
- Produces: `/admin/clinicas` items: `modulos = {"do_plano": [...], "extras": [...]}` (no `modulos_so_admin`, no `limite_pacientes`, no `uso_pacientes_pct`); `PUT /admin/clinicas/<id>/modulos/<codigo>` for any optional module (400 if unknown or already in the plan); `GET /modulos` items: `origem: "plano"|"extra"|None`; `POST /modulos/<codigo>/toggle` → 403 for extras/not in plan (unchanged message for not-in-plan).

- [ ] **Step 1: Failing tests** — `backend/tests/test_planos_configuraveis_extras.py`:

```python
"""Planos configuráveis (25/09/2026): módulos extras por clínica."""
import db
import planos_padrao
from factories import DuasClinicas, novo_usuario
from conftest import autenticado


def _prep(client):
    planos_padrao.criar_planos_padrao_para_teste()
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    admin = autenticado(client, novo_usuario(None, "Admin", "admin@saas.com", "admin_master"))
    return cen, admin


def test_admin_libera_extra_e_lista_mostra(client, db_ctx):
    cen, admin = _prep(client)
    assert admin.put(f"/api/admin/clinicas/{cen.org_a}/modulos/white_label", json={"liberado": True}).status_code == 200
    a = next(c for c in admin.get("/api/admin/clinicas").get_json() if c["id"] == cen.org_a)
    assert "white_label" in a["modulos"]["extras"] and "financeiro" in a["modulos"]["do_plano"]
    assert "limite_pacientes" not in a and "uso_pacientes_pct" not in a and "modulos_so_admin" not in a


def test_modulo_do_plano_nao_vira_extra(client, db_ctx):
    cen, admin = _prep(client)
    r = admin.put(f"/api/admin/clinicas/{cen.org_a}/modulos/financeiro", json={"liberado": True})
    assert r.status_code == 400 and "plano" in r.get_json()["erro"]


def test_gestor_ve_origem_e_nao_desliga_extra(client, db_ctx):
    cen, admin = _prep(client)
    admin.put(f"/api/admin/clinicas/{cen.org_a}/modulos/white_label", json={"liberado": True})
    g = autenticado(client, cen.gestor_a)
    mods = {m["codigo"]: m for m in g.get("/api/modulos").get_json()}
    assert mods["white_label"]["origem"] == "extra" and mods["financeiro"]["origem"] == "plano"
    assert mods["pandoo"]["origem"] is None
    assert g.post("/api/modulos/white_label/toggle").status_code == 403
    assert g.post("/api/modulos/ia/toggle").status_code == 200  # módulo do plano: pode desligar


def test_desligar_extra_tira_acesso_na_hora(client, db_ctx):
    cen, admin = _prep(client)
    admin.put(f"/api/admin/clinicas/{cen.org_a}/modulos/pandoo", json={"liberado": True})
    g = autenticado(client, cen.gestor_a)
    assert "pandoo" in g.get("/api/auth/me").get_json()["organizacao"]["modulos_habilitados"]
    admin.put(f"/api/admin/clinicas/{cen.org_a}/modulos/pandoo", json={"liberado": False})
    assert "pandoo" not in g.get("/api/auth/me").get_json()["organizacao"]["modulos_habilitados"]
```

- [ ] **Step 2: Run — expect FAIL**.
- [ ] **Step 3: Implement**
  - `_enriquecer_clinica`: remove `limite_pacientes`, `uso_pacientes_pct` (and `limite_pac` usage); replace the `modulos_so_admin` block with `o["modulos"] = {"do_plano": modulos_do_plano(o["plano"]), "extras": sorted(modulos_extras_clinica(o["id"]))}` (keep `pandoo_cenario_tem_imagem`). Check `frontend/js/views/admin.js` for uses of `uso_pacientes_pct`/`limite_pacientes` and remove them there in Task 6.
  - rename `liberar_modulo_so_admin` → `liberar_modulo_extra`: `codigo not in CODIGOS_OPCIONAIS` → 400 "Módulo desconhecido."; `codigo in modulos_do_plano(org.plano)` → 400 "Este módulo já vem no plano da clínica."; else `definir_liberacao_admin`.
  - `modulos_bp.listar`: `origem = "plano" if codigo in liberados_plano else ("extra" if codigo in extras else None)`; keep `liberado_pelo_plano`, `habilitado`; drop `so_admin`.
  - `modulos_bp` toggle: unchanged check (`codigo not in modulos_do_plano(...)` → 403) — extras are never in the plan, so they're already refused.
  - `test_pandoo_modulo.py::test_listagens_mostram_o_estado`: assert on `a["modulos"]["extras"] == ["pandoo"]` and `pandoo["origem"] == "extra"`.
- [ ] **Step 4: Run — expect PASS** (+ all `test_pandoo_*`).
- [ ] **Step 5: Commit** — "Planos configuráveis: módulos extras por clínica".

### Task 5: Pacientes ilimitados

**Files:**
- Modify: `backend/blueprints/pessoas_bp.py` (`_limite_do_plano_excedido`: "pacientes" branch returns None; drop the call at ~l.449), `backend/blueprints/importacao_bp.py` (`_limite_do_plano_excedido_para_lote` removed and its call)
- Modify: `backend/tests/test_importacao_pacientes.py` (rewrite the skipped limit test)
- Test: `backend/tests/test_planos_configuraveis_pacientes.py`

- [ ] **Step 1: Failing test** — `backend/tests/test_planos_configuraveis_pacientes.py`:

```python
"""Planos configuráveis (25/09/2026): pacientes ilimitados em todos os planos,
mesmo que um valor antigo tenha ficado em planos.limite_pacientes."""
import db
from factories import DuasClinicas
from conftest import autenticado


def test_cadastro_passa_do_antigo_limite(client, db_ctx):
    cen = DuasClinicas()
    db.execute("INSERT INTO planos (codigo, nome, preco_mensal_centavos, limite_pacientes) VALUES ('mini', 'Mini', 0, 1)")
    db.execute("UPDATE organizacoes SET plano = 'mini' WHERE id = ?", (cen.org_a,))
    c = autenticado(client, cen.gestor_a)
    for i in range(3):
        r = c.post("/api/pessoas/pacientes", json={"nome": f"Novo {i}", "data_nascimento": "2019-01-01"})
        assert r.status_code in (200, 201), r.get_data(as_text=True)
```

Confirm the patient-creation route/body (`grep -n "@bp.post(\"/pacientes\")" -A25 backend/blueprints/pessoas_bp.py`) and adjust the payload. In `test_importacao_pacientes.py`, rewrite the former limit test as `test_confirmar_nao_limita_quantidade_de_pacientes` (plan with `limite_pacientes = 3`, confirm a lot of 5 → all imported).

- [ ] **Step 2: Run — expect FAIL** (403 "permite até 1 paciente").
- [ ] **Step 3: Implement** — remove the patient branch/calls; keep professionals/secretaries untouched; update the docstring ("pacientes ilimitados desde 25/09/2026").
- [ ] **Step 4: Run — expect PASS** + `test_importacao_pacientes.py` + `test_gestor_atua_como_profissional.py`.
- [ ] **Step 5: Commit** — "Planos configuráveis: pacientes ilimitados".

### Task 6: Telas do Admin (planos e clínica) e tela Módulos do gestor

**Files:**
- Modify: `frontend/js/views/admin.js` (`viewAdminPlanos` ~l.342, `abrirModalEditarPlano` ~l.370 → create/edit form; `abrirModalDetalheClinica` ~l.125: modules section, plan select filter, remove patient usage; `renderCartaoClinica` ~l.94 if it shows patient usage)
- Modify: `frontend/js/views/modulos.js` (`origem`, text "Fale com a Panda Tech", remove `NOME_PLANO_MINIMO`)

- [ ] **Step 1: Planos screen**
  - `viewAdminPlanos`: `Promise.all([Api.get("/admin/planos?incluir_inativos=1"), Api.get("/admin/modulos-disponiveis")])`; top action "+ Novo plano"; cards: name, price, "herda de {plano_base_nome}", validity badge ("Promoção até dd/mm/aaaa" / "Promoção encerrada"), "Inativo" badge, "{total_clinicas} clínica(s)", limits line **without patients** ("Profissionais: … · Secretárias: …"), module chips (`modulos_efetivos` mapped to icon + name), recursos list, ✏️ edit.
  - `abrirModalPlano(plano | null, planos, modulos)` (replaces `abrirModalEditarPlano`): fields nome, preço, limite de profissionais, limite de secretárias, cor (`<input type="color">`), recursos (textarea), ativo (checkbox, edit only), "Começar a partir do plano…" (select of other active plans, excluding itself and its descendants — compute descendants client-side from `plano_base_id`), "Disponível até" (`type="date"`, hint "para promoções — depois disso não dá para escolher este plano para novas clínicas"), and **Módulos**: one checkbox row per module (icon + name + description). When a base is chosen, modules coming from the base chain are `checked disabled` with "vem do plano {nome}" (compute from the selected base's `modulos_efetivos`); changing the base select re-renders this block; own modules = the enabled checked boxes.
  - Submit: POST (new) or PUT (edit) with `{nome, preco_mensal_centavos, limite_profissionais, limite_secretarias, cor, recursos, plano_base_id, disponivel_ate, modulos, ativo}`; toast; close; `despachar()`.
- [ ] **Step 2: Clinic detail** — in `abrirModalDetalheClinica`:
  - remove patient usage/limit display;
  - new `cartao-flat` "🧩 Módulos da clínica": for each module from `/admin/modulos-disponiveis` (load it once in `viewAdminClinicas` alongside clinics/plans): if in `c.modulos.do_plano` → "✓ do plano" (muted); else a `.chave-toggle` labeled "Extra" (`checked` if in `c.modulos.extras`) → `PUT /admin/clinicas/${c.id}/modulos/${codigo}` `{liberado}`; success toast "Módulo liberado como extra." / "Extra removido."; error → revert + toast; update `c.modulos.extras`.
  - plan `<select>` (change plan / create clinic form): only `ativo` plans without `promocao_encerrada`, **plus** the clinic's current plan (so it still displays).
- [ ] **Step 3: Gestor Módulos** — `modulos.js`: `origem === "extra"` → badge "Liberado pela Panda Tech" (no toggle, not faded); `origem === null` → current faded card with "Fora do plano" and the note "Fale com a Panda Tech para incluir no seu plano." (remove `NOME_PLANO_MINIMO`); `origem === "plano"` → toggle as today.
- [ ] **Step 4:** `node --check` changed files; `grep -rn "limite_pacientes\|uso_pacientes_pct\|modulos_so_admin" frontend/js` → none left (except unrelated). Commit — "Planos configuráveis: telas do Admin e do gestor".

### Task 7: Verificação, docs e PR

- [ ] **Step 1: Full suites** — backend `pytest -q` all green; `node --test frontend/tests/*.test.js` green.
- [ ] **Step 2: Browser** (fresh seed + `app.py`; Playwright via `uv`; mind the login rate limit and the CSP `wait_for_function` issue — poll with `page.evaluate`):
  1. Admin → Planos: 3 default plans; Enterprise shows "herda de Pro" and all Pro modules as chips.
  2. "+ Novo plano" "Promoção Primavera", base Pro, marca Pandoo, validade futura → card with badge "Promoção até …"; open edit → Pro modules checked+disabled "vem do plano Pro".
  3. Edit Pro: marca White Label → Enterprise and Promoção Primavera show it too.
  4. Try base cycle via UI (Pro base = Promoção Primavera) → error toast, nothing changes.
  5. Clínica: detail → Módulos da clínica: "✓ do plano" for Pro ones; liga "Extra" Pandoo → gestor (re-login) sees "🎮 Pandoo"… (menu item only appears after PR B — check `/auth/me` `modulos_habilitados` contains `pandoo` instead) and Módulos screen shows "Liberado pela Panda Tech".
  6. Validade no passado para a promoção → não aparece no select de plano da clínica; clínica que já estava nela continua com os módulos.
  7. No patient limit shown anywhere in the Admin.
  8. Console without errors.
- [ ] **Step 3: CLAUDE.md** — section 5 new item `q) Planos configuráveis + módulos extras (25/09/2026)`; section 6: replace the Pandoo bullet's "módulo só-Admin (`MODULOS_SO_ADMIN`)" with the new rule (planos no banco, herança viva, extras por clínica, `planos_padrao.py` só como ponto de partida), and update any mention of `MODULOS_POR_PLANO`; section 7: pending migration (planos configuráveis, **antes** do `git pull`), White Label completo (próximo), Pandoo PR B (depois, Tarefa 9 passa a usar "Módulos da clínica"); section 8 rows.
- [ ] **Step 4: PR** — push, PR (summary; **passo manual**: `backend/migracoes/migracao_planos_configuraveis.sql` no Supabase — "Run" normal, sem aviso de RLS esperado além do da tabela nova `planos_modulos`, escolher "Run without RLS" como nas outras — **antes** do `git pull`), CI green → **ask the user before merging**.
