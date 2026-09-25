# Pandoo fase 1 — PR A (backend) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend of the Pandoo game builder: schema + migration, admin-only module, content validation, game CRUD (as `exercicios.tipo='jogo'`), match results, mission gating and the clinic's default scene — all tested, no UI yet.

**Architecture:** New `backend/pandoo_service.py` (pure validation/normalization, unit-tested) and `backend/blueprints/pandoo_bp.py` (`/api/pandoo`). Small hooks in `modulos_service.py`, `modulos_bp.py`, `admin_bp.py`, `biblioteca_bp.py`, `jornada_bp.py`, `pessoas_bp.py`, `auth_bp.py`, `db.py`. New tables `pandoo_jogos` (1:1 with `exercicios`) and `pandoo_resultados`.

**Tech Stack:** Flask, SQLite (tests/local) + Postgres (prod) through `backend/db.py`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-25-pandoo-fase1-design.md`

## Global Constraints

- Branch `pandoo-fase1` (already has the spec, rebased on `main`). This PR changes the schema → **ask the user before merging**; migration runs in Supabase **before** `git pull`.
- Tests from `backend/`: `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q <files>` (Git Bash).
- Module code `pandoo` is in **no plan**; only the Admin releases it per clinic. A gestor cannot enable it.
- Module off: create/edit/list-for-creation return 403 and games disappear from the Biblioteca listing; `GET /api/pandoo/jogos/<id>` and `POST /api/pandoo/resultados` keep working (games already in missions stay playable).
- Content v1: `{"versao": 1, "itens": [{"id", "pergunta": {"texto","imagem","audio"}, "resposta": {...}, "distratores": [], "grupo": null}]}`; roleta requires `pergunta.imagem` in every item.
- Limits: 2–24 items; text ≤ 80 chars; image ≤ 300 KB (decoded); audio ≤ 600 KB; whole content JSON ≤ 10 MB; clinic scene image ≤ 800 KB. Types checked by magic bytes (`validacao_arquivo`); audio also accepts WebM (EBML header `1A 45 DF A3`).
- Scenes: `bambu`, `mar`, `espaco`, `clinica`; tom `claro`/`escuro`. Default scene `bambu`.
- Roleta rules: `{"fim": "todas"|"giros", "giros": 1–100 (default 10), "mostrar_palavra": bool, "som": bool, "voz": bool}`.
- Result item values: `"conseguiu"` | `"treinar"`.
- Mission gating: diária → needs ≥1 result with that `missao_id` + `atividade_id`; semanal → same **with `data_local` = today** (`date.today().isoformat()`, same convention as `concluir_dia_missao`). 409 with `{"erro": "Jogue o jogo da missão para liberar 🎮", "jogos_pendentes": [atividade_ids]}`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Comments in Portuguese, explaining the why, citing "Pandoo, 25/09/2026".

## Review Focus

1. **Cross-clinic access** — a professional/responsável of clinic B reading, editing or posting results for clinic A's game or patient → 403. Tests in Tasks 4 and 5.
2. **Result posted with a mismatched mission/activity** (activity of another mission, other patient's mission, activity pointing to a different game) → 400, nothing saved. Task 5.
3. **Weekly mission played yesterday but not today** → "Marquei hoje" blocked today; played today → allowed. Task 6 (the test inserts yesterday's `data_local` directly).
4. **Payload abuse** — 25 items, 400 KB image, non-image bytes labeled as image, HTML in text, 11 MB content → 400 with a clear message; text is stored as given (the front escapes) but trimmed/limited. Task 3.
5. **Postgres-only breakage** — `pandoo_jogos` has no `id` column: `db.execute` must not append `RETURNING id` (add to `_TABELAS_SEM_ID_AUTO`). Task 1, plus the CI Postgres smoke applying the migration.

---

### Task 1: Schema, migration and CI

**Files:**
- Modify: `backend/schema.sql`, `backend/schema_postgres.sql`
- Create: `backend/migracoes/migracao_pandoo.sql`, `backend/migrar_pandoo.py`
- Modify: `backend/db.py:36` (`_TABELAS_SEM_ID_AUTO`)
- Modify: `.github/workflows/db-setup.yml`, `.github/workflows/tests.yml` (smoke job: apply the new `.sql` after the schema)
- Test: `backend/tests/test_pandoo_schema.py`

**Interfaces:**
- Produces tables/columns used by every later task:
  - `pandoo_jogos(exercicio_id PK→exercicios, modelo, conteudo_json, regras_json, cenario NULL, total_itens, atualizado_em)`
  - `pandoo_resultados(id, organizacao_id, paciente_id, exercicio_id, missao_id NULL, atividade_id NULL, modelo, iniciado_em, finalizado_em, encerrado_antes, total_rodadas, acertos, a_treinar, detalhes_json, usuario_id, data_local, criado_em)`
  - `organizacoes.pandoo_cenario_padrao TEXT DEFAULT 'bambu'`, `.pandoo_cenario_imagem TEXT`, `.pandoo_cenario_tom TEXT`
  - `modulos_clinica.liberado_admin INTEGER DEFAULT 0`

- [ ] **Step 1: Failing test** — `backend/tests/test_pandoo_schema.py`:

```python
"""Pandoo (25/09/2026): tabelas e colunas novas existem no schema de teste,
e pandoo_jogos (sem coluna id) grava pelo db.execute sem quebrar."""
import db
from factories import nova_organizacao, novo_exercicio


def _colunas(tabela):
    return {c["name"] for c in db.query(f"PRAGMA table_info({tabela})")}


def test_tabelas_e_colunas_novas(db_ctx):
    assert {"exercicio_id", "modelo", "conteudo_json", "regras_json", "cenario", "total_itens", "atualizado_em"} <= _colunas("pandoo_jogos")
    assert {"organizacao_id", "paciente_id", "exercicio_id", "missao_id", "atividade_id", "modelo", "encerrado_antes",
            "total_rodadas", "acertos", "a_treinar", "detalhes_json", "usuario_id", "data_local"} <= _colunas("pandoo_resultados")
    assert {"pandoo_cenario_padrao", "pandoo_cenario_imagem", "pandoo_cenario_tom"} <= _colunas("organizacoes")
    assert "liberado_admin" in _colunas("modulos_clinica")


def test_pandoo_jogos_sem_id_grava_pelo_execute(db_ctx):
    org = nova_organizacao()
    ex = novo_exercicio(org, "Roleta", tipo="jogo")
    db.execute("INSERT INTO pandoo_jogos (exercicio_id, modelo, conteudo_json, regras_json, total_itens) VALUES (?, ?, ?, ?, ?)",
               (ex["id"], "roleta", '{"versao":1,"itens":[]}', "{}", 0))
    assert db.query_one("SELECT modelo FROM pandoo_jogos WHERE exercicio_id = ?", (ex["id"],))["modelo"] == "roleta"


def test_cenario_padrao_da_clinica_e_bambu(db_ctx):
    org = nova_organizacao()
    assert db.query_one("SELECT pandoo_cenario_padrao FROM organizacoes WHERE id = ?", (org,))["pandoo_cenario_padrao"] == "bambu"


def test_tabela_sem_id_registrada_no_db():
    assert "pandoo_jogos" in db._TABELAS_SEM_ID_AUTO
```

Confirm first: `grep -n "def novo_exercicio" -A12 backend/tests/factories.py` (returns a row dict; `tipo` goes through `**extra`).

- [ ] **Step 2: Run — expect FAIL** (`no such table: pandoo_jogos` / assertion on `_TABELAS_SEM_ID_AUTO`):
`... -m pytest -q tests/test_pandoo_schema.py`

- [ ] **Step 3: Schema**

`backend/schema.sql` — in `organizacoes`, after `agenda_hora_fim    TEXT,`:
```sql
    -- Pandoo (25/09/2026): cenário padrão dos jogos da clínica. 'clinica' usa
    -- a imagem enviada; o tom (claro/escuro) decide a cor dos textos por cima.
    pandoo_cenario_padrao TEXT DEFAULT 'bambu',
    pandoo_cenario_imagem TEXT,
    pandoo_cenario_tom    TEXT,
```
In `modulos_clinica`, after `habilitado      INTEGER DEFAULT 1,`:
```sql
    liberado_admin  INTEGER DEFAULT 0,     -- módulos que não entram em plano (ex.: pandoo): só o Admin libera
```
Before the first `CREATE INDEX` line of the file, add:
```sql
-- ----------------------------------------------------------------------------
-- Pandoo (25/09/2026) — jogos educativos. O jogo é um exercício (tipo='jogo');
-- aqui fica o conteúdo no formato único e as regras do modelo.
-- ----------------------------------------------------------------------------
CREATE TABLE pandoo_jogos (
    exercicio_id    INTEGER PRIMARY KEY REFERENCES exercicios(id),
    modelo          TEXT NOT NULL,
    conteudo_json   TEXT NOT NULL,
    regras_json     TEXT NOT NULL DEFAULT '{}',
    cenario         TEXT,                                   -- NULL = padrão da clínica
    total_itens     INTEGER DEFAULT 0,
    atualizado_em   TEXT DEFAULT (datetime('now'))
);

-- Uma linha por partida jogada (missão, prévia do responsável ou "jogar de novo").
CREATE TABLE pandoo_resultados (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    exercicio_id    INTEGER NOT NULL REFERENCES exercicios(id),
    missao_id       INTEGER REFERENCES missoes(id),
    atividade_id    INTEGER REFERENCES atividades(id),
    modelo          TEXT NOT NULL,
    iniciado_em     TEXT,
    finalizado_em   TEXT,
    encerrado_antes INTEGER DEFAULT 0,
    total_rodadas   INTEGER DEFAULT 0,
    acertos         INTEGER DEFAULT 0,
    a_treinar       INTEGER DEFAULT 0,
    detalhes_json   TEXT NOT NULL DEFAULT '[]',
    usuario_id      INTEGER REFERENCES usuarios(id),
    data_local      TEXT NOT NULL,                          -- dia da partida (missão semanal)
    criado_em       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_pandoo_res_paciente ON pandoo_resultados(paciente_id);
CREATE INDEX idx_pandoo_res_missao ON pandoo_resultados(missao_id, atividade_id, data_local);
```

`backend/schema_postgres.sql` — the same, with `id SERIAL PRIMARY KEY` in `pandoo_resultados`, and `DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))` for `atualizado_em`/`criado_em`. Place the two tables after `atividades` and `exercicios` exist (end of the table section, before the indexes).

`backend/db.py:36`: `_TABELAS_SEM_ID_AUTO = {"gamificacao_paciente", "pandoo_jogos"}` (+ one-line comment: sem coluna `id`, chave é `exercicio_id`).

- [ ] **Step 4: Migration files**

`backend/migracoes/migracao_pandoo.sql`:
```sql
-- ----------------------------------------------------------------------------
-- Migração incremental — Pandoo fase 1 (25/09/2026). Idempotente.
-- ----------------------------------------------------------------------------
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS pandoo_cenario_padrao TEXT DEFAULT 'bambu';
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS pandoo_cenario_imagem TEXT;
ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS pandoo_cenario_tom TEXT;
ALTER TABLE modulos_clinica ADD COLUMN IF NOT EXISTS liberado_admin INTEGER DEFAULT 0;

CREATE TABLE IF NOT EXISTS pandoo_jogos (
    exercicio_id    INTEGER PRIMARY KEY REFERENCES exercicios(id),
    modelo          TEXT NOT NULL,
    conteudo_json   TEXT NOT NULL,
    regras_json     TEXT NOT NULL DEFAULT '{}',
    cenario         TEXT,
    total_itens     INTEGER DEFAULT 0,
    atualizado_em   TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS pandoo_resultados (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    exercicio_id    INTEGER NOT NULL REFERENCES exercicios(id),
    missao_id       INTEGER REFERENCES missoes(id),
    atividade_id    INTEGER REFERENCES atividades(id),
    modelo          TEXT NOT NULL,
    iniciado_em     TEXT,
    finalizado_em   TEXT,
    encerrado_antes INTEGER DEFAULT 0,
    total_rodadas   INTEGER DEFAULT 0,
    acertos         INTEGER DEFAULT 0,
    a_treinar       INTEGER DEFAULT 0,
    detalhes_json   TEXT NOT NULL DEFAULT '[]',
    usuario_id      INTEGER REFERENCES usuarios(id),
    data_local      TEXT NOT NULL,
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_pandoo_res_paciente ON pandoo_resultados(paciente_id);
CREATE INDEX IF NOT EXISTS idx_pandoo_res_missao ON pandoo_resultados(missao_id, atividade_id, data_local);
```

`backend/migrar_pandoo.py` (same shape as `migrar_horario_agenda.py`; SQLite has no `ADD COLUMN IF NOT EXISTS`, so columns go through PRAGMA; tables use the SQLite DDL):
```python
"""
Migração não-destrutiva do Pandoo fase 1 (25/09/2026): colunas de cenário em
`organizacoes`, `modulos_clinica.liberado_admin` e as tabelas `pandoo_jogos`
e `pandoo_resultados`. Em produção (Postgres) aplica
`migracoes/migracao_pandoo.sql`; local (SQLite) usa o DDL equivalente.

    cd backend && python3 migrar_pandoo.py

Confira que a saída termina com (Postgres) em produção (ver CLAUDE.md, seção
7.2). Seguro rodar mais de uma vez.
"""
import os
import db

COLUNAS = [
    ("organizacoes", "pandoo_cenario_padrao", "TEXT DEFAULT 'bambu'"),
    ("organizacoes", "pandoo_cenario_imagem", "TEXT"),
    ("organizacoes", "pandoo_cenario_tom", "TEXT"),
    ("modulos_clinica", "liberado_admin", "INTEGER DEFAULT 0"),
]

DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS pandoo_jogos (
    exercicio_id INTEGER PRIMARY KEY REFERENCES exercicios(id), modelo TEXT NOT NULL,
    conteudo_json TEXT NOT NULL, regras_json TEXT NOT NULL DEFAULT '{}', cenario TEXT,
    total_itens INTEGER DEFAULT 0, atualizado_em TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS pandoo_resultados (
    id INTEGER PRIMARY KEY AUTOINCREMENT, organizacao_id INTEGER NOT NULL REFERENCES organizacoes(id),
    paciente_id INTEGER NOT NULL REFERENCES pacientes(id), exercicio_id INTEGER NOT NULL REFERENCES exercicios(id),
    missao_id INTEGER REFERENCES missoes(id), atividade_id INTEGER REFERENCES atividades(id), modelo TEXT NOT NULL,
    iniciado_em TEXT, finalizado_em TEXT, encerrado_antes INTEGER DEFAULT 0, total_rodadas INTEGER DEFAULT 0,
    acertos INTEGER DEFAULT 0, a_treinar INTEGER DEFAULT 0, detalhes_json TEXT NOT NULL DEFAULT '[]',
    usuario_id INTEGER REFERENCES usuarios(id), data_local TEXT NOT NULL, criado_em TEXT DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS idx_pandoo_res_paciente ON pandoo_resultados(paciente_id);
CREATE INDEX IF NOT EXISTS idx_pandoo_res_missao ON pandoo_resultados(missao_id, atividade_id, data_local);
"""


def migrar():
    if db.USANDO_POSTGRES:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_pandoo.sql")
        sql = open(caminho, encoding="utf-8").read()
        linhas = [l for l in sql.splitlines() if not l.strip().startswith("--")]
        for comando in "\n".join(linhas).split(";"):
            if comando.strip():
                db.execute(comando)
        print("✅ Pandoo: colunas, tabelas e índices conferidos (Postgres)")
        return
    conn = db.get_db()
    for tabela, coluna, tipo in COLUNAS:
        existentes = {l["name"] for l in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}
        if coluna in existentes:
            print(f"↷  {tabela}.{coluna} já existia (SQLite), pulei")
            continue
        conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
        print(f"✅ {tabela}.{coluna} adicionada (SQLite)")
    conn.executescript(DDL_SQLITE)
    conn.commit()
    print("✅ Pandoo: tabelas e índices conferidos (SQLite)")


if __name__ == "__main__":
    migrar()
```

Workflows:
- `.github/workflows/db-setup.yml`: new step after "horário de funcionamento da agenda": `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migracoes/migracao_pandoo.sql`, same `env` shape.
- `.github/workflows/tests.yml` smoke job: after the existing `migracoes/migracao_frequencia_missao.sql` line add `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migracoes/migracao_pandoo.sql` (proves the file is valid Postgres and idempotent on top of the new schema).

- [ ] **Step 5: Run — expect PASS** (4 tests). Then run `migrar_pandoo.py` twice against a DB built from the **previous** schema (`git show main:backend/schema.sql` into the scratchpad, same method used for `migrar_horario_agenda.py`): first run adds, second run skips; no error.

- [ ] **Step 6: Commit** — `git add` the files above; message "Pandoo: tabelas, colunas e migração".

### Task 2: Módulo liberado só pelo Admin

**Files:**
- Modify: `backend/modulos_service.py` (`MODULOS_OPCIONAIS`, new `MODULOS_SO_ADMIN`, `modulos_habilitados_clinica`, new `definir_liberacao_admin`)
- Modify: `backend/blueprints/modulos_bp.py` (`listar`: `so_admin` flag)
- Modify: `backend/blueprints/admin_bp.py` (new route; `_enriquecer_clinica` adds `modulos_so_admin`)
- Test: `backend/tests/test_pandoo_modulo.py`

**Interfaces:**
- Produces: `MODULOS_SO_ADMIN = {"pandoo"}`; `definir_liberacao_admin(organizacao_id, codigo, liberado: bool) -> None`; `PUT /api/admin/clinicas/<org_id>/modulos/<codigo>` body `{"liberado": bool}` → `{"ok": true, "liberado": bool}`; `GET /api/admin/clinicas` items gain `modulos_so_admin: {"pandoo": bool}`; `GET /api/modulos` items gain `so_admin: bool`.
- Consumes: `modulo_ativo_para_clinica(org_id, plano, codigo)` (existing) — later tasks call it with `"pandoo"`.

- [ ] **Step 1: Failing tests** — `backend/tests/test_pandoo_modulo.py`:

```python
"""Pandoo (25/09/2026): módulo pago que não entra em nenhum plano — só o
Admin do SaaS libera, clínica por clínica."""
import db
from factories import DuasClinicas, novo_usuario
from conftest import autenticado
from modulos_service import modulo_ativo_para_clinica


def _admin(db_ctx):
    return novo_usuario(None, "Admin", "admin@saas.com", "admin_master")


def _ativo(org_id):
    plano = db.query_one("SELECT plano FROM organizacoes WHERE id = ?", (org_id,))["plano"]
    return modulo_ativo_para_clinica(org_id, plano, "pandoo")


def test_pandoo_comeca_desligado_em_qualquer_plano(db_ctx):
    cen = DuasClinicas()
    for plano in ("starter", "pro", "enterprise", "premium"):
        db.execute("UPDATE organizacoes SET plano = ? WHERE id = ?", (plano, cen.org_a))
        assert not _ativo(cen.org_a), plano


def test_admin_libera_e_desliga(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, _admin(db_ctx))
    r = c.put(f"/api/admin/clinicas/{cen.org_a}/modulos/pandoo", json={"liberado": True})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert _ativo(cen.org_a) and not _ativo(cen.org_b)
    c.put(f"/api/admin/clinicas/{cen.org_a}/modulos/pandoo", json={"liberado": False})
    assert not _ativo(cen.org_a)


def test_liberacao_vale_mesmo_trocando_de_plano(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, _admin(db_ctx)).put(f"/api/admin/clinicas/{cen.org_a}/modulos/pandoo", json={"liberado": True})
    db.execute("UPDATE organizacoes SET plano = 'starter' WHERE id = ?", (cen.org_a,))
    assert _ativo(cen.org_a)


def test_gestor_nao_liga_sozinho(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/modulos/pandoo/toggle")
    assert r.status_code == 403
    assert not _ativo(cen.org_a)
    r = autenticado(client, cen.gestor_a).put(f"/api/admin/clinicas/{cen.org_a}/modulos/pandoo", json={"liberado": True})
    assert r.status_code == 403


def test_admin_so_libera_modulo_so_admin(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, _admin(db_ctx)).put(f"/api/admin/clinicas/{cen.org_a}/modulos/financeiro", json={"liberado": True})
    assert r.status_code == 400


def test_listagens_mostram_o_estado(client, db_ctx):
    cen = DuasClinicas()
    admin = _admin(db_ctx)
    autenticado(client, admin).put(f"/api/admin/clinicas/{cen.org_a}/modulos/pandoo", json={"liberado": True})
    clinicas = autenticado(client, admin).get("/api/admin/clinicas").get_json()
    a = next(c for c in clinicas if c["id"] == cen.org_a)
    assert a["modulos_so_admin"] == {"pandoo": True}
    mods = autenticado(client, cen.gestor_a).get("/api/modulos").get_json()
    pandoo = next(m for m in mods if m["codigo"] == "pandoo")
    assert pandoo["so_admin"] is True and pandoo["habilitado"] is True
```

Before running: check `novo_usuario` accepts `org_id=None` for `admin_master` (`usuarios.organizacao_id` nullable) and the shape of `GET /api/admin/clinicas` (list vs `{"clinicas": [...]}`) — adapt the two lookups if needed.

- [ ] **Step 2: Run — expect FAIL** (404 on the admin route / `KeyError`).

- [ ] **Step 3: Implement**

`modulos_service.py`:
```python
# Pandoo (25/09/2026): módulo pago que não entra em nenhum plano — o Admin do
# SaaS libera clínica por clínica (modulos_clinica.liberado_admin). O gestor
# não liga sozinho (a rota de toggle só aceita módulos do plano).
MODULOS_SO_ADMIN = {"pandoo"}
```
Append to `MODULOS_OPCIONAIS`:
```python
    {"codigo": "pandoo", "nome": "Pandoo", "icone": "🎮", "so_admin": True,
     "descricao": "Jogos educativos criados pela clínica (roleta e outros), usados nas missões."},
```
In `modulos_habilitados_clinica`, after computing `habilitados` from the plan:
```python
    habilitados |= {l["modulo_codigo"] for l in linhas
                    if l["modulo_codigo"] in MODULOS_SO_ADMIN and l["habilitado"] and l.get("liberado_admin")}
```
and change the `SELECT` to `SELECT modulo_codigo, habilitado, liberado_admin FROM modulos_clinica ...`.

New function:
```python
def definir_liberacao_admin(organizacao_id, codigo, liberado):
    """Liga/desliga um módulo só-Admin numa clínica (linha criada se faltar)."""
    valor = 1 if liberado else 0
    linha = query_one("SELECT id FROM modulos_clinica WHERE organizacao_id = ? AND modulo_codigo = ?",
                      (organizacao_id, codigo))
    if linha:
        execute("UPDATE modulos_clinica SET liberado_admin = ?, habilitado = ? WHERE id = ?", (valor, valor, linha["id"]))
    else:
        execute("INSERT INTO modulos_clinica (organizacao_id, modulo_codigo, habilitado, liberado_admin) VALUES (?, ?, ?, ?)",
                (organizacao_id, codigo, valor, valor))
```
(`query_one`/`execute` are already imported there — confirm.)

`modulos_bp.py` `listar`: add `"so_admin": bool(m.get("so_admin")),` to each item.

`admin_bp.py` — import `MODULOS_SO_ADMIN, definir_liberacao_admin, modulos_habilitados_clinica` from `modulos_service`; in `_enriquecer_clinica`:
```python
    habilitados = modulos_habilitados_clinica(o["id"], o["plano"])
    o["modulos_so_admin"] = {codigo: codigo in habilitados for codigo in sorted(MODULOS_SO_ADMIN)}
```
New route (same decorators as the other `/clinicas/<org_id>/...` routes):
```python
@bp.put("/clinicas/<int:org_id>/modulos/<codigo>")
@login_required
@papel_required("admin_master")
def liberar_modulo_so_admin(org_id, codigo):
    """Pandoo (25/09/2026): o Admin liga/desliga um módulo que não entra em plano."""
    if codigo not in MODULOS_SO_ADMIN:
        return jsonify({"erro": "Este módulo é liberado pelo plano da clínica, não por aqui."}), 400
    if not query_one("SELECT 1 FROM organizacoes WHERE id = ?", (org_id,)):
        return jsonify({"erro": "Clínica não encontrada."}), 404
    liberado = bool((request.get_json(force=True, silent=True) or {}).get("liberado"))
    definir_liberacao_admin(org_id, codigo, liberado)
    log_auditoria(org_id, g.usuario["id"], "liberar_modulo" if liberado else "bloquear_modulo", "modulo_clinica", org_id, codigo)
    return jsonify({"ok": True, "liberado": liberado})
```

- [ ] **Step 4: Run — expect PASS** (6); run `tests/test_modulos*.py` too (existing module tests must still pass — `grep -l modulos backend/tests/*.py`).

- [ ] **Step 5: Commit** — "Pandoo: módulo liberado só pelo Admin, clínica por clínica".

### Task 3: `pandoo_service.py` — validação do conteúdo, regras e resultado

**Files:**
- Create: `backend/pandoo_service.py`
- Test: `backend/tests/test_pandoo_service.py`

**Interfaces:**
- Produces:
  - `MODELOS = {"roleta"}`, `CENARIOS = {"bambu", "mar", "espaco", "clinica"}`, `TONS = {"claro", "escuro"}`
  - `class ErroPandoo(ValueError)`
  - `validar_jogo(modelo, conteudo, regras, cenario) -> (conteudo_normalizado: dict, regras_normalizadas: dict)` (raises `ErroPandoo`)
  - `calcular_resultado(detalhes) -> dict` with keys `total_rodadas, acertos, a_treinar, detalhes` (raises `ErroPandoo`)
  - `imagem_cenario_valida(b64) -> bool`

- [ ] **Step 1: Failing tests** — `backend/tests/test_pandoo_service.py`:

```python
"""Pandoo (25/09/2026): validação do conteúdo único, das regras da roleta e
do resultado de uma partida."""
import base64
import json

import pytest

import pandoo_service as ps

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
MP3 = base64.b64encode(b"ID3" + b"\x00" * 64).decode()
WEBM = base64.b64encode(b"\x1a\x45\xdf\xa3" + b"\x00" * 64).decode()
TEXTO_FALSO = base64.b64encode(b"<script>alert(1)</script>").decode()


def _item(i, **p):
    return {"id": f"i{i}", "pergunta": {"texto": f"Palavra {i}", "imagem": PNG, **p}}


def _conteudo(n=3, **p):
    return {"versao": 1, "itens": [_item(i, **p) for i in range(n)]}


def test_roleta_valida_e_normaliza():
    conteudo, regras = ps.validar_jogo("roleta", _conteudo(), {}, None)
    item = conteudo["itens"][0]
    assert item["resposta"] == {"texto": "", "imagem": None, "audio": None}
    assert item["distratores"] == [] and item["grupo"] is None
    assert regras == {"fim": "todas", "giros": 10, "mostrar_palavra": True, "som": True, "voz": True}


def test_regras_por_giros_limitadas():
    _, regras = ps.validar_jogo("roleta", _conteudo(), {"fim": "giros", "giros": 500, "voz": False}, "mar")
    assert regras["fim"] == "giros" and regras["giros"] == 100 and regras["voz"] is False


@pytest.mark.parametrize("modelo,conteudo,cenario,trecho", [
    ("quiz", _conteudo(), None, "modelo"),
    ("roleta", {"versao": 2, "itens": []}, None, "versão"),
    ("roleta", _conteudo(1), None, "2 a 24"),
    ("roleta", _conteudo(25), None, "2 a 24"),
    ("roleta", _conteudo(), "praia", "cenário"),
])
def test_recusas_basicas(modelo, conteudo, cenario, trecho):
    with pytest.raises(ps.ErroPandoo, match=trecho):
        ps.validar_jogo(modelo, conteudo, {}, cenario)


def test_roleta_exige_imagem_em_cada_item():
    c = _conteudo()
    c["itens"][1]["pergunta"]["imagem"] = None
    with pytest.raises(ps.ErroPandoo, match="imagem"):
        ps.validar_jogo("roleta", c, {}, None)


def test_imagem_falsa_ou_grande_recusada():
    with pytest.raises(ps.ErroPandoo, match="imagem"):
        ps.validar_jogo("roleta", _conteudo(imagem=TEXTO_FALSO), {}, None)
    grande = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * (310 * 1024)).decode()
    with pytest.raises(ps.ErroPandoo, match="300 KB"):
        ps.validar_jogo("roleta", _conteudo(imagem=grande), {}, None)


def test_audio_mp3_e_webm_aceitos_texto_nao():
    ps.validar_jogo("roleta", _conteudo(audio=MP3), {}, None)
    ps.validar_jogo("roleta", _conteudo(audio=WEBM), {}, None)
    with pytest.raises(ps.ErroPandoo, match="áudio"):
        ps.validar_jogo("roleta", _conteudo(audio=TEXTO_FALSO), {}, None)


def test_texto_cortado_e_ids_unicos():
    c = _conteudo()
    c["itens"][0]["pergunta"]["texto"] = "  " + "x" * 200 + "  "
    conteudo, _ = ps.validar_jogo("roleta", c, {}, None)
    assert len(conteudo["itens"][0]["pergunta"]["texto"]) == 80
    c = _conteudo()
    c["itens"][1]["id"] = "i0"
    with pytest.raises(ps.ErroPandoo, match="repetid"):
        ps.validar_jogo("roleta", c, {}, None)


def test_conteudo_total_acima_de_10_mb():
    imagem = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * (290 * 1024)).decode()
    c = {"versao": 1, "itens": [_item(i, imagem=imagem, audio=base64.b64encode(b"ID3" + b"\x00" * (590 * 1024)).decode()) for i in range(24)]}
    with pytest.raises(ps.ErroPandoo, match="10 MB"):
        ps.validar_jogo("roleta", c, {}, None)


def test_calcular_resultado():
    r = ps.calcular_resultado([
        {"item_id": "i1", "texto": "Rato", "resultado": "conseguiu"},
        {"item_id": "i2", "texto": "Rosa", "resultado": "treinar"},
        {"item_id": "i3", "texto": "Rei", "resultado": "conseguiu"},
    ])
    assert (r["total_rodadas"], r["acertos"], r["a_treinar"]) == (3, 2, 1)
    assert r["detalhes"][0] == {"item_id": "i1", "texto": "Rato", "resultado": "conseguiu"}


def test_resultado_invalido():
    with pytest.raises(ps.ErroPandoo):
        ps.calcular_resultado([{"item_id": "i1", "resultado": "talvez"}])
    with pytest.raises(ps.ErroPandoo):
        ps.calcular_resultado("não é lista")
    with pytest.raises(ps.ErroPandoo):
        ps.calcular_resultado([{"item_id": "i", "resultado": "conseguiu"}] * 501)


def test_partida_encerrada_sem_rodadas_e_valida():
    assert ps.calcular_resultado([])["total_rodadas"] == 0


def test_imagem_cenario():
    assert ps.imagem_cenario_valida(PNG)
    assert not ps.imagem_cenario_valida(TEXTO_FALSO)
    grande = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * (810 * 1024)).decode()
    assert not ps.imagem_cenario_valida(grande)
```

- [ ] **Step 2: Run — expect FAIL** (`No module named 'pandoo_service'`).

- [ ] **Step 3: Implement** — `backend/pandoo_service.py`:

```python
"""
Pandoo (25/09/2026) — regras puras dos jogos: valida e normaliza o conteúdo
no formato único (v1), as regras de cada modelo e o resultado de uma partida.
Sem acesso a banco — as rotas ficam em blueprints/pandoo_bp.py.
"""
import base64
import binascii
import json

from validacao_arquivo import validar_arquivo_base64

MODELOS = {"roleta"}
CENARIOS = {"bambu", "mar", "espaco", "clinica"}
TONS = {"claro", "escuro"}

MIN_ITENS, MAX_ITENS = 2, 24
MAX_TEXTO = 80
MAX_IMAGEM = 300 * 1024
MAX_AUDIO = 600 * 1024
MAX_CONTEUDO = 10 * 1024 * 1024
MAX_IMAGEM_CENARIO = 800 * 1024
MAX_RODADAS = 500

REGRAS_PADRAO = {"roleta": {"fim": "todas", "giros": 10, "mostrar_palavra": True, "som": True, "voz": True}}
_EBML = b"\x1a\x45\xdf\xa3"  # WebM: o Chrome grava voz nesse formato


class ErroPandoo(ValueError):
    pass


def _bytes_b64(b64):
    return len(b64) * 3 // 4


def _eh_webm(b64):
    try:
        return base64.b64decode(b64[:16] + "=" * (-len(b64[:16]) % 4))[:4] == _EBML
    except (binascii.Error, ValueError):
        return False


def _midia(valor, tipo, limite, rotulo_limite, posicao):
    if valor in (None, ""):
        return None
    if not isinstance(valor, str):
        raise ErroPandoo(f"Item {posicao}: {tipo} inválida.")
    if _bytes_b64(valor) > limite:
        raise ErroPandoo(f"Item {posicao}: {tipo} passa de {rotulo_limite}.")
    categoria = "imagem" if tipo == "imagem" else "audio"
    ok, _ = validar_arquivo_base64(valor, categoria)
    if not ok and not (tipo == "áudio" and _eh_webm(valor)):
        raise ErroPandoo(f"Item {posicao}: o arquivo enviado não é um(a) {tipo} válido(a).")
    return valor


def _lado(bruto, posicao, exigir_imagem):
    bruto = bruto if isinstance(bruto, dict) else {}
    texto = str(bruto.get("texto") or "").strip()[:MAX_TEXTO]
    imagem = _midia(bruto.get("imagem"), "imagem", MAX_IMAGEM, "300 KB", posicao)
    audio = _midia(bruto.get("audio"), "áudio", MAX_AUDIO, "600 KB", posicao)
    if exigir_imagem and not imagem:
        raise ErroPandoo(f"Item {posicao}: a roleta precisa de uma imagem em cada figura.")
    return {"texto": texto, "imagem": imagem, "audio": audio}


def _regras(modelo, regras):
    padrao = dict(REGRAS_PADRAO[modelo])
    regras = regras if isinstance(regras, dict) else {}
    if regras.get("fim") in ("todas", "giros"):
        padrao["fim"] = regras["fim"]
    try:
        padrao["giros"] = max(1, min(100, int(regras.get("giros", padrao["giros"]))))
    except (TypeError, ValueError):
        pass
    for chave in ("mostrar_palavra", "som", "voz"):
        if chave in regras:
            padrao[chave] = bool(regras[chave])
    return padrao


def validar_jogo(modelo, conteudo, regras, cenario):
    if modelo not in MODELOS:
        raise ErroPandoo("Esse modelo de jogo ainda não existe.")
    if cenario is not None and cenario not in CENARIOS:
        raise ErroPandoo("Cenário inválido.")
    if not isinstance(conteudo, dict) or conteudo.get("versao") != 1:
        raise ErroPandoo("Conteúdo em versão desconhecida.")
    itens = conteudo.get("itens")
    if not isinstance(itens, list) or not (MIN_ITENS <= len(itens) <= MAX_ITENS):
        raise ErroPandoo(f"O jogo precisa ter de {MIN_ITENS} a {MAX_ITENS} itens.")
    normalizados, ids = [], set()
    for posicao, bruto in enumerate(itens, start=1):
        bruto = bruto if isinstance(bruto, dict) else {}
        item_id = str(bruto.get("id") or "").strip()[:40]
        if not item_id:
            raise ErroPandoo(f"Item {posicao}: sem identificador.")
        if item_id in ids:
            raise ErroPandoo(f"Item {posicao}: identificador repetido.")
        ids.add(item_id)
        distratores = bruto.get("distratores") if isinstance(bruto.get("distratores"), list) else []
        normalizados.append({
            "id": item_id,
            "pergunta": _lado(bruto.get("pergunta"), posicao, exigir_imagem=(modelo == "roleta")),
            "resposta": _lado(bruto.get("resposta"), posicao, exigir_imagem=False),
            "distratores": [str(d).strip()[:MAX_TEXTO] for d in distratores[:10]],
            "grupo": (str(bruto["grupo"]).strip()[:MAX_TEXTO] or None) if bruto.get("grupo") else None,
        })
    resultado = {"versao": 1, "itens": normalizados}
    if len(json.dumps(resultado)) > MAX_CONTEUDO:
        raise ErroPandoo("O jogo ficou pesado demais (limite de 10 MB). Use imagens e áudios menores ou menos itens.")
    return resultado, _regras(modelo, regras)


def calcular_resultado(detalhes):
    if not isinstance(detalhes, list) or len(detalhes) > MAX_RODADAS:
        raise ErroPandoo("Resultado inválido.")
    limpos = []
    for d in detalhes:
        if not isinstance(d, dict) or d.get("resultado") not in ("conseguiu", "treinar"):
            raise ErroPandoo("Resultado inválido.")
        limpos.append({"item_id": str(d.get("item_id") or "")[:40], "texto": str(d.get("texto") or "")[:MAX_TEXTO],
                       "resultado": d["resultado"]})
    acertos = sum(1 for d in limpos if d["resultado"] == "conseguiu")
    return {"total_rodadas": len(limpos), "acertos": acertos, "a_treinar": len(limpos) - acertos, "detalhes": limpos}


def imagem_cenario_valida(b64):
    if not isinstance(b64, str) or not b64 or _bytes_b64(b64) > MAX_IMAGEM_CENARIO:
        return False
    return validar_arquivo_base64(b64, "imagem")[0]
```

Check `validar_arquivo_base64(b64, "audio")` accepts the `ID3…` fixture (`grep -n "def _e_audio" -A12 backend/validacao_arquivo.py`); if its minimum length/header rules differ, adjust the fixtures in the test, not the rule.

- [ ] **Step 4: Run — expect PASS**.

- [ ] **Step 5: Commit** — "Pandoo: validação do conteúdo, regras da roleta e resultado".

### Task 4: Rotas de jogos + Biblioteca

**Files:**
- Create: `backend/blueprints/pandoo_bp.py`
- Modify: `backend/app.py` (import + `app.register_blueprint(pandoo_bp.bp)`)
- Modify: `backend/blueprints/biblioteca_bp.py` (`CAMPOS_LISTAGEM` + `tipo`; listing hides games when the module is off; PUT/duplicar refuse games)
- Test: `backend/tests/test_pandoo_jogos.py`

**Interfaces:**
- Consumes: `pandoo_service.validar_jogo/ErroPandoo/CENARIOS`, `modulo_ativo_para_clinica`, `biblioteca_bp._pode_editar(exercicio, usuario)`, `biblioteca_bp._resolver_categoria_id(categoria_id, organizacao_id)`.
- Produces:
  - `GET /api/pandoo/jogos` → `[{"id", "titulo", "modelo", "categoria_id", "total_itens", "atualizado_em"}]` (gestor/profissional; module required)
  - `GET /api/pandoo/jogos/<id>` → `{"id","titulo","descricao","categoria_id","modelo","conteudo","regras","cenario","cenario_efetivo": {"tipo","imagem","tom"},"pode_editar"}` (any logged user of the clinic; no module check)
  - `POST /api/pandoo/jogos` → 201 `{"id"}`; `PUT /api/pandoo/jogos/<id>` → `{"ok": true}` (gestor/profissional; module required)
  - helpers in `pandoo_bp`: `_pandoo_ativo(org_id) -> bool`, `_cenario_efetivo(org_id, cenario_jogo) -> dict`

- [ ] **Step 1: Failing tests** — `backend/tests/test_pandoo_jogos.py`:

```python
"""Pandoo (25/09/2026): criar/editar/ler jogos, isolamento entre clínicas e
integração com a Biblioteca."""
import base64

import db
from factories import DuasClinicas, novo_exercicio, vincular_responsavel
from conftest import autenticado
from modulos_service import definir_liberacao_admin

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def _conteudo(n=3):
    return {"versao": 1, "itens": [{"id": f"i{i}", "pergunta": {"texto": f"P{i}", "imagem": PNG}} for i in range(n)]}


def _corpo(**extra):
    return {"titulo": "Roleta do /R/", "modelo": "roleta", "conteudo": _conteudo(), "regras": {"fim": "giros", "giros": 5}, **extra}


def _liberar(org):
    definir_liberacao_admin(org, "pandoo", True)


def _criar(client, usuario, **extra):
    return autenticado(client, usuario).post("/api/pandoo/jogos", json=_corpo(**extra))


def test_modulo_desligado_bloqueia_criacao_e_lista(client, db_ctx):
    cen = DuasClinicas()
    assert _criar(client, cen.prof_a1).status_code == 403
    assert autenticado(client, cen.prof_a1).get("/api/pandoo/jogos").status_code == 403


def test_profissional_cria_e_le(client, db_ctx):
    cen = DuasClinicas()
    _liberar(cen.org_a)
    r = _criar(client, cen.prof_a1)
    assert r.status_code == 201, r.get_data(as_text=True)
    jogo_id = r.get_json()["id"]
    ex = db.query_one("SELECT * FROM exercicios WHERE id = ?", (jogo_id,))
    assert ex["tipo"] == "jogo" and ex["organizacao_id"] == cen.org_a
    j = autenticado(client, cen.prof_a1).get(f"/api/pandoo/jogos/{jogo_id}").get_json()
    assert j["modelo"] == "roleta" and len(j["conteudo"]["itens"]) == 3
    assert j["regras"]["giros"] == 5 and j["cenario"] is None
    assert j["cenario_efetivo"] == {"tipo": "bambu", "imagem": None, "tom": "escuro"}
    lista = autenticado(client, cen.prof_a1).get("/api/pandoo/jogos").get_json()
    assert [x["id"] for x in lista] == [jogo_id] and lista[0]["total_itens"] == 3


def test_conteudo_invalido_400_sem_gravar(client, db_ctx):
    cen = DuasClinicas()
    _liberar(cen.org_a)
    r = autenticado(client, cen.prof_a1).post("/api/pandoo/jogos", json=_corpo(conteudo=_conteudo(1)))
    assert r.status_code == 400 and "2 a 24" in r.get_json()["erro"]
    assert db.query_one("SELECT COUNT(*) AS n FROM exercicios WHERE tipo = 'jogo'")["n"] == 0


def test_editar(client, db_ctx):
    cen = DuasClinicas()
    _liberar(cen.org_a)
    jogo_id = _criar(client, cen.prof_a1).get_json()["id"]
    r = autenticado(client, cen.prof_a2).put(f"/api/pandoo/jogos/{jogo_id}", json=_corpo(titulo="Nova", conteudo=_conteudo(4), cenario="mar"))
    assert r.status_code == 200, r.get_data(as_text=True)
    j = autenticado(client, cen.prof_a1).get(f"/api/pandoo/jogos/{jogo_id}").get_json()
    assert j["titulo"] == "Nova" and len(j["conteudo"]["itens"]) == 4 and j["cenario"] == "mar"


def test_outra_clinica_nao_le_nem_edita(client, db_ctx):
    cen = DuasClinicas()
    _liberar(cen.org_a)
    _liberar(cen.org_b)
    jogo_id = _criar(client, cen.prof_a1).get_json()["id"]
    assert autenticado(client, cen.prof_b1).get(f"/api/pandoo/jogos/{jogo_id}").status_code == 403
    assert autenticado(client, cen.gestor_b).put(f"/api/pandoo/jogos/{jogo_id}", json=_corpo()).status_code == 403
    assert autenticado(client, cen.resp_b1).get(f"/api/pandoo/jogos/{jogo_id}").status_code == 403


def test_responsavel_da_clinica_le_mesmo_com_modulo_desligado(client, db_ctx):
    cen = DuasClinicas()
    _liberar(cen.org_a)
    jogo_id = _criar(client, cen.prof_a1).get_json()["id"]
    definir_liberacao_admin(cen.org_a, "pandoo", False)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    assert autenticado(client, cen.resp_a1).get(f"/api/pandoo/jogos/{jogo_id}").status_code == 200


def test_pasta_de_outra_clinica_recusada(client, db_ctx):
    cen = DuasClinicas()
    _liberar(cen.org_a)
    pasta_b = db.execute("INSERT INTO categorias_exercicio (organizacao_id, nome) VALUES (?, ?)", (cen.org_b, "B"))
    assert _criar(client, cen.prof_a1, categoria_id=pasta_b).status_code == 400


def test_biblioteca_lista_jogo_com_tipo_e_esconde_sem_modulo(client, db_ctx):
    cen = DuasClinicas()
    _liberar(cen.org_a)
    jogo_id = _criar(client, cen.prof_a1).get_json()["id"]
    lista = autenticado(client, cen.prof_a1).get("/api/biblioteca/exercicios").get_json()
    itens = lista if isinstance(lista, list) else lista.get("exercicios", lista)
    jogo = next(e for e in itens if e["id"] == jogo_id)
    assert jogo["tipo"] == "jogo"
    definir_liberacao_admin(cen.org_a, "pandoo", False)
    lista = autenticado(client, cen.prof_a1).get("/api/biblioteca/exercicios").get_json()
    itens = lista if isinstance(lista, list) else lista.get("exercicios", lista)
    assert jogo_id not in [e["id"] for e in itens]


def test_biblioteca_nao_edita_nem_duplica_jogo(client, db_ctx):
    cen = DuasClinicas()
    _liberar(cen.org_a)
    jogo_id = _criar(client, cen.prof_a1).get_json()["id"]
    c = autenticado(client, cen.prof_a1)
    r = c.put(f"/api/biblioteca/exercicios/{jogo_id}", json={"titulo": "x", "midias": [{"tipo": "link", "conteudo_url": "https://a.b"}]})
    assert r.status_code == 409 and "Pandoo" in r.get_json()["erro"]
    assert c.post(f"/api/biblioteca/exercicios/{jogo_id}/duplicar").status_code == 409
    assert db.query_one("SELECT modelo FROM pandoo_jogos WHERE exercicio_id = ?", (jogo_id,))["modelo"] == "roleta"


def test_exercicio_comum_nao_e_jogo(client, db_ctx):
    cen = DuasClinicas()
    _liberar(cen.org_a)
    ex = novo_exercicio(cen.org_a, "Comum")
    assert autenticado(client, cen.prof_a1).get(f"/api/pandoo/jogos/{ex['id']}").status_code == 404
```

Before running: confirm the Biblioteca listing's JSON shape (list or object) and adjust `itens =` once for the whole file.

- [ ] **Step 2: Run — expect FAIL** (404 on `/api/pandoo/...`).

- [ ] **Step 3: Implement `pandoo_bp.py`**

```python
"""
Pandoo (25/09/2026) — jogos educativos da clínica. O jogo é um exercício
(`exercicios.tipo = 'jogo'`, aparece na Biblioteca e nas missões) com o
conteúdo e as regras em `pandoo_jogos`. Criar/editar/listar exige o módulo
liberado pelo Admin; ler um jogo e salvar resultado não — jogos já colocados
em missões continuam jogáveis se o módulo for desligado.
"""
import json

from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute, log_auditoria, agora_sql
from auth import login_required, papel_required
from modulos_service import modulo_ativo_para_clinica
from pandoo_service import validar_jogo, ErroPandoo
from blueprints.biblioteca_bp import _pode_editar, _resolver_categoria_id

bp = Blueprint("pandoo", __name__, url_prefix="/api/pandoo")

ERRO_MODULO = {"erro": "O Pandoo não está liberado para esta clínica. Fale com a Panda Tech para ativar."}


def _pandoo_ativo(org_id):
    org = query_one("SELECT plano FROM organizacoes WHERE id = ?", (org_id,))
    return bool(org) and modulo_ativo_para_clinica(org_id, org["plano"], "pandoo")


def _cenario_efetivo(org_id, cenario_jogo):
    org = query_one("SELECT pandoo_cenario_padrao, pandoo_cenario_imagem, pandoo_cenario_tom FROM organizacoes WHERE id = ?", (org_id,)) or {}
    tipo = cenario_jogo or org.get("pandoo_cenario_padrao") or "bambu"
    if tipo == "clinica" and org.get("pandoo_cenario_imagem"):
        return {"tipo": "clinica", "imagem": org["pandoo_cenario_imagem"], "tom": org.get("pandoo_cenario_tom") or "claro"}
    if tipo == "clinica":
        tipo = "bambu"  # imagem ainda não enviada: cai no cenário pronto
    return {"tipo": tipo, "imagem": None, "tom": "escuro"}


def _jogo_ou_erro(exercicio_id):
    ex = query_one("SELECT * FROM exercicios WHERE id = ?", (exercicio_id,))
    if not ex or ex.get("tipo") != "jogo":
        return None, None, (jsonify({"erro": "Jogo não encontrado."}), 404)
    jogo = query_one("SELECT * FROM pandoo_jogos WHERE exercicio_id = ?", (exercicio_id,))
    if not jogo:
        return None, None, (jsonify({"erro": "Jogo não encontrado."}), 404)
    return ex, jogo, None


def _dados_do_corpo(body, org_id):
    titulo = str(body.get("titulo") or "").strip()[:120]
    if not titulo:
        raise ErroPandoo("Dê um nome ao jogo.")
    conteudo, regras = validar_jogo(body.get("modelo"), body.get("conteudo"), body.get("regras"), body.get("cenario") or None)
    try:
        categoria_id = _resolver_categoria_id(body.get("categoria_id"), org_id)
    except ValueError as e:
        raise ErroPandoo(str(e))
    return {
        "titulo": titulo, "descricao": str(body.get("descricao") or "").strip()[:500],
        "categoria_id": categoria_id, "modelo": body["modelo"], "cenario": body.get("cenario") or None,
        "conteudo": conteudo, "regras": regras,
    }


@bp.get("/jogos")
@login_required
@papel_required("gestor", "profissional")
def listar_jogos():
    u = g.usuario
    if not _pandoo_ativo(u["organizacao_id"]):
        return jsonify(ERRO_MODULO), 403
    linhas = query(
        """SELECT e.id, e.titulo, e.categoria_id, p.modelo, p.total_itens, p.atualizado_em
           FROM exercicios e JOIN pandoo_jogos p ON p.exercicio_id = e.id
           WHERE e.organizacao_id = ? AND e.tipo = 'jogo' AND e.ativo = 1
           ORDER BY p.atualizado_em DESC, e.id DESC""",
        (u["organizacao_id"],),
    )
    return jsonify(linhas)


@bp.get("/jogos/<int:exercicio_id>")
@login_required
def obter_jogo(exercicio_id):
    u = g.usuario
    ex, jogo, erro = _jogo_ou_erro(exercicio_id)
    if erro:
        return erro
    if ex["organizacao_id"] != u["organizacao_id"]:
        return jsonify({"erro": "Sem acesso a este jogo."}), 403
    return jsonify({
        "id": ex["id"], "titulo": ex["titulo"], "descricao": ex["descricao"], "categoria_id": ex["categoria_id"],
        "modelo": jogo["modelo"], "conteudo": json.loads(jogo["conteudo_json"]), "regras": json.loads(jogo["regras_json"]),
        "cenario": jogo["cenario"], "cenario_efetivo": _cenario_efetivo(ex["organizacao_id"], jogo["cenario"]),
        "pode_editar": u["papel"] in ("gestor", "profissional") and _pode_editar(ex, u),
    })


@bp.post("/jogos")
@login_required
@papel_required("gestor", "profissional")
def criar_jogo():
    u = g.usuario
    if not _pandoo_ativo(u["organizacao_id"]):
        return jsonify(ERRO_MODULO), 403
    try:
        d = _dados_do_corpo(request.get_json(force=True, silent=True) or {}, u["organizacao_id"])
    except ErroPandoo as e:
        return jsonify({"erro": str(e)}), 400
    ex_id = execute(
        """INSERT INTO exercicios (organizacao_id, categoria_id, titulo, descricao, tipo)
           VALUES (?, ?, ?, ?, 'jogo')""",
        (u["organizacao_id"], d["categoria_id"], d["titulo"], d["descricao"]),
    )
    execute(
        """INSERT INTO pandoo_jogos (exercicio_id, modelo, conteudo_json, regras_json, cenario, total_itens, atualizado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (ex_id, d["modelo"], json.dumps(d["conteudo"]), json.dumps(d["regras"]), d["cenario"], len(d["conteudo"]["itens"]), agora_sql()),
    )
    log_auditoria(u["organizacao_id"], u["id"], "criar", "pandoo_jogo", ex_id, d["titulo"])
    return jsonify({"id": ex_id}), 201


@bp.put("/jogos/<int:exercicio_id>")
@login_required
@papel_required("gestor", "profissional")
def editar_jogo(exercicio_id):
    u = g.usuario
    ex, _, erro = _jogo_ou_erro(exercicio_id)
    if erro:
        return erro
    if not _pode_editar(ex, u):
        return jsonify({"erro": "Sem permissão para editar este jogo."}), 403
    if not _pandoo_ativo(u["organizacao_id"]):
        return jsonify(ERRO_MODULO), 403
    try:
        d = _dados_do_corpo(request.get_json(force=True, silent=True) or {}, ex["organizacao_id"])
    except ErroPandoo as e:
        return jsonify({"erro": str(e)}), 400
    execute("UPDATE exercicios SET titulo = ?, descricao = ?, categoria_id = ? WHERE id = ?",
            (d["titulo"], d["descricao"], d["categoria_id"], exercicio_id))
    execute(
        """UPDATE pandoo_jogos SET modelo = ?, conteudo_json = ?, regras_json = ?, cenario = ?, total_itens = ?, atualizado_em = ?
           WHERE exercicio_id = ?""",
        (d["modelo"], json.dumps(d["conteudo"]), json.dumps(d["regras"]), d["cenario"], len(d["conteudo"]["itens"]), agora_sql(), exercicio_id),
    )
    log_auditoria(u["organizacao_id"], u["id"], "editar", "pandoo_jogo", exercicio_id, d["titulo"])
    return jsonify({"ok": True})
```

(Confirm `agora_sql` and `log_auditoria` are exported by `db.py`, and `_resolver_categoria_id(None, org)` returns `None` without raising.)

`backend/app.py`: add `pandoo_bp` to the `from blueprints import (...)` list and `app.register_blueprint(pandoo_bp.bp)` after `importacao_bp`.

`biblioteca_bp.py`:
- Add `tipo` to `CAMPOS_LISTAGEM` (same table prefix as the other columns there).
- In the listing route, after the org/escopo filters: when `not _pandoo_ativo_para(u)` add `AND COALESCE(e.tipo, '') != 'jogo'` (use the same alias the query uses). Implement `_pandoo_ativo_para(u)` locally in `biblioteca_bp.py` (import `modulo_ativo_para_clinica` and look up the plan) — **don't** import from `pandoo_bp` (circular import: `pandoo_bp` imports `biblioteca_bp`). Admin (`organizacao_id` None) sees platform content only, so no game ever shows there.
- In `editar_exercicio` and `duplicar_exercicio`, right after loading `ex` and the 404 check:
```python
    if ex.get("tipo") == "jogo":
        return jsonify({"erro": "Este é um jogo do Pandoo — edite pelo Pandoo."}), 409
```

- [ ] **Step 4: Run — expect PASS** (11) + `tests/test_biblioteca.py` (existing must stay green).

- [ ] **Step 5: Commit** — "Pandoo: rotas de jogos e integração com a Biblioteca".

### Task 5: Resultados das partidas

**Files:**
- Modify: `backend/blueprints/pandoo_bp.py`
- Test: `backend/tests/test_pandoo_resultados.py`

**Interfaces:**
- Consumes: `calcular_resultado`, `auth.paciente_acessivel`.
- Produces:
  - `POST /api/pandoo/resultados` body `{paciente_id, exercicio_id, missao_id?, atividade_id?, iniciado_em?, encerrado_antes?, detalhes: [...]}` → 201 `{"id","total_rodadas","acertos","a_treinar"}`
  - `GET /api/pandoo/resultados?paciente_id=` → `{"partidas": [...≤50, newest first, each with "titulo" and "detalhes"], "por_jogo": [{"exercicio_id","titulo","itens": [{"texto","conseguiu","total"}]}]}` (gestor/profissional/admin_master)

- [ ] **Step 1: Failing tests** — `backend/tests/test_pandoo_resultados.py`:

```python
"""Pandoo (25/09/2026): salvar e consultar resultados de partidas."""
import base64
from datetime import date

import db
from factories import DuasClinicas, vincular_responsavel
from conftest import autenticado
from modulos_service import definir_liberacao_admin

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
DET = [{"item_id": "i0", "texto": "Rato", "resultado": "conseguiu"}, {"item_id": "i1", "texto": "Rosa", "resultado": "treinar"}]


def _jogo(client, cen):
    definir_liberacao_admin(cen.org_a, "pandoo", True)
    corpo = {"titulo": "Roleta", "modelo": "roleta",
             "conteudo": {"versao": 1, "itens": [{"id": f"i{i}", "pergunta": {"texto": f"P{i}", "imagem": PNG}} for i in range(3)]}}
    return autenticado(client, cen.prof_a1).post("/api/pandoo/jogos", json=corpo).get_json()["id"]


def _missao(client, cen, jogo_id, tipo="diaria", paciente=None):
    paciente = paciente or cen.paciente_a1
    jornada = db.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)", (paciente, "Obj"))
    plano = db.execute("INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
                       (jornada, cen.prof_a1["id"], "Plano"))
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano}/criar-missao",
                                              json={"titulo": "M", "tipo": tipo, "frequencia_dias": 3, "exercicios_ids": [jogo_id]})
    missao_id = r.get_json()["id"]
    atividade_id = db.query_one("SELECT id FROM atividades WHERE missao_id = ?", (missao_id,))["id"]
    return missao_id, atividade_id


def test_responsavel_salva_partida_da_missao(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    missao, atividade = _missao(client, cen, jogo)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    r = autenticado(client, cen.resp_a1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": jogo, "missao_id": missao, "atividade_id": atividade,
        "encerrado_antes": True, "detalhes": DET})
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["acertos"] == 1 and r.get_json()["a_treinar"] == 1
    linha = db.query_one("SELECT * FROM pandoo_resultados WHERE id = ?", (r.get_json()["id"],))
    assert linha["encerrado_antes"] == 1 and linha["data_local"] == date.today().isoformat()
    assert linha["usuario_id"] == cen.resp_a1["id"] and linha["modelo"] == "roleta"


def test_numeros_recalculados_no_servidor(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    r = autenticado(client, cen.prof_a1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": jogo, "acertos": 99, "detalhes": DET})
    assert r.status_code == 201 and r.get_json()["acertos"] == 1


def test_responsavel_sem_vinculo_nao_salva(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    r = autenticado(client, cen.resp_a1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": jogo, "detalhes": DET})
    assert r.status_code == 403


def test_outra_clinica_nao_salva(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    r = autenticado(client, cen.prof_b1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": jogo, "detalhes": DET})
    assert r.status_code == 403


def test_missao_e_atividade_incoerentes_400(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    m1, a1 = _missao(client, cen, jogo)
    m2, a2 = _missao(client, cen, jogo, paciente=cen.paciente_a2)
    c = autenticado(client, cen.prof_a1)
    base = {"paciente_id": cen.paciente_a1, "exercicio_id": jogo, "detalhes": DET}
    assert c.post("/api/pandoo/resultados", json={**base, "missao_id": m1, "atividade_id": a2}).status_code == 400
    assert c.post("/api/pandoo/resultados", json={**base, "missao_id": m2, "atividade_id": a2}).status_code == 400
    assert c.post("/api/pandoo/resultados", json={**base, "missao_id": m1}).status_code == 400
    assert db.query_one("SELECT COUNT(*) AS n FROM pandoo_resultados")["n"] == 0


def test_atividade_de_outro_exercicio_400(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    outro = db.execute("INSERT INTO exercicios (organizacao_id, titulo, tipo) VALUES (?, ?, 'jogo')", (cen.org_a, "Outro"))
    db.execute("INSERT INTO pandoo_jogos (exercicio_id, modelo, conteudo_json, regras_json, total_itens) VALUES (?, 'roleta', '{}', '{}', 0)", (outro,))
    m, a = _missao(client, cen, jogo)
    r = autenticado(client, cen.prof_a1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": outro, "missao_id": m, "atividade_id": a, "detalhes": DET})
    assert r.status_code == 400


def test_detalhes_invalidos_400(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    r = autenticado(client, cen.prof_a1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": jogo, "detalhes": [{"item_id": "i0", "resultado": "talvez"}]})
    assert r.status_code == 400


def test_profissional_ve_partidas_e_resumo_por_figura(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    c = autenticado(client, cen.prof_a1)
    for det in (DET, [{"item_id": "i0", "texto": "Rato", "resultado": "conseguiu"}]):
        c.post("/api/pandoo/resultados", json={"paciente_id": cen.paciente_a1, "exercicio_id": jogo, "detalhes": det})
    r = c.get(f"/api/pandoo/resultados?paciente_id={cen.paciente_a1}").get_json()
    assert len(r["partidas"]) == 2 and r["partidas"][0]["titulo"] == "Roleta"
    itens = {i["texto"]: i for i in r["por_jogo"][0]["itens"]}
    assert (itens["Rato"]["conseguiu"], itens["Rato"]["total"]) == (2, 2)
    assert (itens["Rosa"]["conseguiu"], itens["Rosa"]["total"]) == (0, 1)
    assert autenticado(client, cen.prof_b1).get(f"/api/pandoo/resultados?paciente_id={cen.paciente_a1}").status_code == 403
    assert autenticado(client, cen.resp_a1).get(f"/api/pandoo/resultados?paciente_id={cen.paciente_a1}").status_code == 403
```

- [ ] **Step 2: Run — expect FAIL** (404/405 on `/api/pandoo/resultados`).

- [ ] **Step 3: Implement** — append to `pandoo_bp.py` (add `from datetime import date`, `from auth import paciente_acessivel`, `from pandoo_service import calcular_resultado`):

```python
def _paciente_da_missao(missao_id):
    linha = query_one(
        """SELECT j.paciente_id FROM missoes m JOIN planos_terapeuticos p ON p.id = m.plano_id
           JOIN jornadas j ON j.id = p.jornada_id WHERE m.id = ?""",
        (missao_id,),
    )
    return linha["paciente_id"] if linha else None


@bp.post("/resultados")
@login_required
def salvar_resultado():
    """Uma partida terminada (ou encerrada em "Finalizar jogo"). Os números
    são recalculados aqui a partir dos detalhes — o navegador não decide."""
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    try:
        paciente_id = int(body.get("paciente_id"))
        exercicio_id = int(body.get("exercicio_id"))
    except (TypeError, ValueError):
        return jsonify({"erro": "Paciente e jogo são obrigatórios."}), 400
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Você não tem acesso a este paciente."}), 403
    paciente = query_one("SELECT organizacao_id FROM pacientes WHERE id = ?", (paciente_id,))
    ex, jogo, erro = _jogo_ou_erro(exercicio_id)
    if erro:
        return erro
    if not paciente or ex["organizacao_id"] != paciente["organizacao_id"]:
        return jsonify({"erro": "Sem acesso a este jogo."}), 403

    missao_id, atividade_id = body.get("missao_id"), body.get("atividade_id")
    if missao_id or atividade_id:
        atividade = query_one("SELECT * FROM atividades WHERE id = ?", (atividade_id,)) if atividade_id else None
        if (not atividade or str(atividade["missao_id"]) != str(missao_id)
                or atividade["exercicio_id"] != exercicio_id or _paciente_da_missao(missao_id) != paciente_id):
            return jsonify({"erro": "Missão e atividade não conferem com este jogo e paciente."}), 400

    try:
        r = calcular_resultado(body.get("detalhes"))
    except ErroPandoo as e:
        return jsonify({"erro": str(e)}), 400
    novo_id = execute(
        """INSERT INTO pandoo_resultados (organizacao_id, paciente_id, exercicio_id, missao_id, atividade_id, modelo,
               iniciado_em, finalizado_em, encerrado_antes, total_rodadas, acertos, a_treinar, detalhes_json, usuario_id, data_local)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (paciente["organizacao_id"], paciente_id, exercicio_id, missao_id or None, atividade_id or None, jogo["modelo"],
         str(body.get("iniciado_em") or "")[:25] or None, agora_sql(), 1 if body.get("encerrado_antes") else 0,
         r["total_rodadas"], r["acertos"], r["a_treinar"], json.dumps(r["detalhes"], ensure_ascii=False), u["id"],
         date.today().isoformat()),
    )
    return jsonify({"id": novo_id, "total_rodadas": r["total_rodadas"], "acertos": r["acertos"], "a_treinar": r["a_treinar"]}), 201


@bp.get("/resultados")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def listar_resultados():
    try:
        paciente_id = int(request.args.get("paciente_id"))
    except (TypeError, ValueError):
        return jsonify({"erro": "Informe o paciente."}), 400
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Você não tem acesso a este paciente."}), 403
    partidas = query(
        """SELECT r.id, r.exercicio_id, e.titulo, r.modelo, r.finalizado_em, r.data_local, r.encerrado_antes,
                  r.total_rodadas, r.acertos, r.a_treinar, r.detalhes_json, r.missao_id
           FROM pandoo_resultados r JOIN exercicios e ON e.id = r.exercicio_id
           WHERE r.paciente_id = ? ORDER BY r.id DESC LIMIT 50""",
        (paciente_id,),
    )
    por_jogo = {}
    for p in partidas:
        p["detalhes"] = json.loads(p.pop("detalhes_json") or "[]")
        jogo = por_jogo.setdefault(p["exercicio_id"], {"exercicio_id": p["exercicio_id"], "titulo": p["titulo"], "itens": {}})
        for d in p["detalhes"]:
            chave = d.get("texto") or d.get("item_id")
            item = jogo["itens"].setdefault(chave, {"texto": chave, "conseguiu": 0, "total": 0})
            item["total"] += 1
            item["conseguiu"] += 1 if d["resultado"] == "conseguiu" else 0
    resumo = [{**j, "itens": sorted(j["itens"].values(), key=lambda i: i["texto"])} for j in por_jogo.values()]
    return jsonify({"partidas": partidas, "por_jogo": resumo})
```

(`paciente_acessivel` already refuses responsáveis without a link and other clinics; for `listar_resultados` the `papel_required` excludes responsáveis entirely.)

- [ ] **Step 4: Run — expect PASS** (8).

- [ ] **Step 5: Commit** — "Pandoo: salvar e consultar resultados das partidas".

### Task 6: Missão só conclui depois de jogar

**Files:**
- Modify: `backend/blueprints/jornada_bp.py` (atividades SQL in the bundle ~l.120 and `GET /missao/<id>` ~l.510 → shared helper; `concluir_missao` ~l.582; `concluir_dia_missao` ~l.638)
- Test: `backend/tests/test_pandoo_missao.py`

**Interfaces:**
- Produces: atividades returned to the front gain `exercicio_tipo` (`"jogo"` or other) and `jogo_jogado` (bool, only meaningful for games); helper `_jogos_pendentes(missao) -> list[int]` in `jornada_bp.py`.

- [ ] **Step 1: Failing tests** — `backend/tests/test_pandoo_missao.py` (reuse `_jogo`/`_missao`/`DET` by copying them from `test_pandoo_resultados.py` — tests stay independent):

```python
"""Pandoo (25/09/2026): missão com jogo só conclui depois de jogar
(diária: uma partida na missão; semanal: uma partida no dia)."""
import base64
from datetime import date, timedelta

import db
from factories import DuasClinicas, vincular_responsavel, novo_exercicio
from conftest import autenticado
from modulos_service import definir_liberacao_admin

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
DET = [{"item_id": "i0", "texto": "Rato", "resultado": "conseguiu"}]


def _jogo(client, cen):
    definir_liberacao_admin(cen.org_a, "pandoo", True)
    corpo = {"titulo": "Roleta", "modelo": "roleta",
             "conteudo": {"versao": 1, "itens": [{"id": f"i{i}", "pergunta": {"texto": f"P{i}", "imagem": PNG}} for i in range(3)]}}
    return autenticado(client, cen.prof_a1).post("/api/pandoo/jogos", json=corpo).get_json()["id"]


def _missao(client, cen, exercicios, tipo="diaria"):
    jornada = db.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)", (cen.paciente_a1, "Obj"))
    plano = db.execute("INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
                       (jornada, cen.prof_a1["id"], "Plano"))
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano}/criar-missao",
                                              json={"titulo": "M", "tipo": tipo, "frequencia_dias": 3, "exercicios_ids": exercicios})
    return r.get_json()["id"]


def _jogar(client, cen, missao_id, jogo_id, data_local=None):
    atividade = db.query_one("SELECT id FROM atividades WHERE missao_id = ? AND exercicio_id = ?", (missao_id, jogo_id))["id"]
    r = autenticado(client, cen.resp_a1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": jogo_id, "missao_id": missao_id, "atividade_id": atividade, "detalhes": DET})
    assert r.status_code == 201, r.get_data(as_text=True)
    if data_local:
        db.execute("UPDATE pandoo_resultados SET data_local = ? WHERE id = ?", (data_local, r.get_json()["id"]))
    return atividade


def _prep(client, cen, tipo="diaria"):
    jogo = _jogo(client, cen)
    comum = novo_exercicio(cen.org_a, "Vídeo")["id"]
    missao = _missao(client, cen, [jogo, comum], tipo)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    return jogo, missao


def test_diaria_bloqueada_sem_jogar_e_liberada_depois(client, db_ctx):
    cen = DuasClinicas()
    jogo, missao = _prep(client, cen)
    c = autenticado(client, cen.resp_a1)
    r = c.post(f"/api/jornada/missao/{missao}/concluir")
    assert r.status_code == 409 and "Jogue" in r.get_json()["erro"]
    assert len(r.get_json()["jogos_pendentes"]) == 1
    assert db.query_one("SELECT status FROM missoes WHERE id = ?", (missao,))["status"] != "concluida"
    _jogar(client, cen, missao, jogo)
    assert c.post(f"/api/jornada/missao/{missao}/concluir").status_code == 200


def test_semanal_exige_partida_no_dia(client, db_ctx):
    cen = DuasClinicas()
    jogo, missao = _prep(client, cen, "semanal")
    c = autenticado(client, cen.resp_a1)
    ontem = (date.today() - timedelta(days=1)).isoformat()
    _jogar(client, cen, missao, jogo, data_local=ontem)
    assert c.post(f"/api/jornada/missao/{missao}/concluir-dia").status_code == 409
    _jogar(client, cen, missao, jogo)
    assert c.post(f"/api/jornada/missao/{missao}/concluir-dia").status_code == 200


def test_missao_sem_jogo_segue_como_antes(client, db_ctx):
    cen = DuasClinicas()
    comum = novo_exercicio(cen.org_a, "Vídeo")["id"]
    missao = _missao(client, cen, [comum])
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    assert autenticado(client, cen.resp_a1).post(f"/api/jornada/missao/{missao}/concluir").status_code == 200


def test_bundle_informa_tipo_e_se_jogou(client, db_ctx):
    cen = DuasClinicas()
    jogo, missao = _prep(client, cen)
    c = autenticado(client, cen.resp_a1)

    def atividades():
        m = c.get(f"/api/jornada/missao/{missao}").get_json()
        return {a["exercicio_id"]: a for a in m["atividades"]}

    a = atividades()
    assert a[jogo]["exercicio_tipo"] == "jogo" and a[jogo]["jogo_jogado"] is False
    _jogar(client, cen, missao, jogo)
    assert atividades()[jogo]["jogo_jogado"] is True
```

Before running: confirm the JSON shape of `GET /api/jornada/missao/<id>` (does it return `{"atividades": [...]}` at top level or nested under `missao`?) and of the bundle `GET /api/jornada/paciente/<id>`; adjust `atividades()` accordingly. Also confirm `criar-missao` accepts both a game and a common exercise in `exercicios_ids` (`_exercicio_visivel_na_clinica`).

- [ ] **Step 2: Run — expect FAIL** (200 instead of 409; missing `exercicio_tipo`).

- [ ] **Step 3: Implement** in `jornada_bp.py` (add `from datetime import date` if absent):

```python
# Pandoo (25/09/2026): atividade que é jogo precisa de partida salva antes de
# concluir — diária: uma partida nesta missão; semanal: uma partida hoje.
def _jogo_jogado(missao, atividade_id):
    sql = "SELECT 1 FROM pandoo_resultados WHERE missao_id = ? AND atividade_id = ?"
    params = [missao["id"], atividade_id]
    if missao.get("tipo") == "semanal":
        sql += " AND data_local = ?"
        params.append(date.today().isoformat())
    return bool(query_one(sql, tuple(params)))


def _atividades_da_missao(missao):
    linhas = query(
        """SELECT a.id, a.ordem, a.concluida, e.id as exercicio_id, e.titulo, e.descricao, e.tipo as exercicio_tipo,
                  (e.arquivo_base64 IS NOT NULL AND e.arquivo_base64 != '') as tem_arquivo,
                  (SELECT mi.tipo FROM midias_exercicio mi WHERE mi.exercicio_id = e.id ORDER BY mi.ordem, mi.id LIMIT 1) as midia_capa_tipo
           FROM atividades a JOIN exercicios e ON e.id = a.exercicio_id
           WHERE a.missao_id = ? ORDER BY a.ordem""",
        (missao["id"],),
    )
    for a in linhas:
        a["jogo_jogado"] = a["exercicio_tipo"] == "jogo" and _jogo_jogado(missao, a["id"])
    return linhas


def _jogos_pendentes(missao):
    return [a["id"] for a in _atividades_da_missao(missao) if a["exercicio_tipo"] == "jogo" and not a["jogo_jogado"]]
```

Replace the two duplicated atividades queries (bundle ~l.120 and `GET /missao/<id>` ~l.510) with `_atividades_da_missao(missao_row)` — keep whatever variable/key those routes use today (the SELECT list above is the same columns plus `exercicio_tipo`). The helper needs the mission row (`id`, `tipo`); both places have it.

In `concluir_missao`, right after the `paciente_acessivel` 403 (before the first `UPDATE atividades`):
```python
    pendentes = _jogos_pendentes(missao)
    if pendentes:
        return jsonify({"erro": "Jogue o jogo da missão para liberar 🎮", "jogos_pendentes": pendentes}), 409
```
Same block in `concluir_dia_missao`, right after its `paciente_acessivel` 403 (before the "já marcou hoje" check).

- [ ] **Step 4: Run — expect PASS** (4) + `tests/test_missao_frequencia_prazo_02_09_2026.py` and any `tests/test_jornada*.py` (existing mission tests must stay green).

- [ ] **Step 5: Commit** — "Pandoo: missão só conclui depois de jogar".

### Task 7: Cenário padrão da clínica

**Files:**
- Modify: `backend/blueprints/pessoas_bp.py` (`atualizar_organizacao`)
- Modify: `backend/blueprints/auth_bp.py` (`CAMPOS_ORG`: `pandoo_cenario_padrao, pandoo_cenario_tom` — **not** the image, it's heavy)
- Test: `backend/tests/test_pandoo_cenario.py`

**Interfaces:**
- Consumes: `pandoo_service.CENARIOS`, `TONS`, `imagem_cenario_valida`; `pandoo_bp._cenario_efetivo` (Task 4) reads the columns.
- Produces: `PUT /api/pessoas/organizacao` accepts `pandoo_cenario_padrao`, `pandoo_cenario_imagem` (`""` clears), `pandoo_cenario_tom`; `/auth/me` → `organizacao.pandoo_cenario_padrao/tom`; `GET /api/pessoas/organizacao` already returns all columns (SELECT *).

- [ ] **Step 1: Failing tests** — `backend/tests/test_pandoo_cenario.py`:

```python
"""Pandoo (25/09/2026): cenário padrão da clínica (Configurações do gestor)."""
import base64

import db
from factories import DuasClinicas
from conftest import autenticado
from modulos_service import definir_liberacao_admin

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def _org(org_id):
    return db.query_one("SELECT pandoo_cenario_padrao, pandoo_cenario_imagem, pandoo_cenario_tom FROM organizacoes WHERE id = ?", (org_id,))


def test_gestor_escolhe_cenario_pronto(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={"pandoo_cenario_padrao": "mar"})
    assert r.status_code == 200
    assert _org(cen.org_a)["pandoo_cenario_padrao"] == "mar"
    me = autenticado(client, cen.gestor_a).get("/api/auth/me").get_json()
    assert me["organizacao"]["pandoo_cenario_padrao"] == "mar"


def test_imagem_da_clinica_com_tom(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    r = c.put("/api/pessoas/organizacao", json={"pandoo_cenario_padrao": "clinica", "pandoo_cenario_imagem": PNG, "pandoo_cenario_tom": "claro"})
    assert r.status_code == 200, r.get_data(as_text=True)
    o = _org(cen.org_a)
    assert (o["pandoo_cenario_padrao"], o["pandoo_cenario_tom"]) == ("clinica", "claro") and o["pandoo_cenario_imagem"] == PNG


def test_recusas(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    assert c.put("/api/pessoas/organizacao", json={"pandoo_cenario_padrao": "praia"}).status_code == 400
    assert c.put("/api/pessoas/organizacao", json={"pandoo_cenario_tom": "cinza"}).status_code == 400
    falso = base64.b64encode(b"<svg onload=alert(1)>").decode()
    assert c.put("/api/pessoas/organizacao", json={"pandoo_cenario_imagem": falso}).status_code == 400
    assert c.put("/api/pessoas/organizacao", json={"pandoo_cenario_padrao": "clinica"}).status_code == 400  # sem imagem enviada


def test_put_sem_campos_nao_mexe_no_cenario(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    c.put("/api/pessoas/organizacao", json={"pandoo_cenario_padrao": "espaco"})
    c.put("/api/pessoas/organizacao", json={"nome": "Outra"})
    assert _org(cen.org_a)["pandoo_cenario_padrao"] == "espaco"


def test_jogo_usa_padrao_da_clinica(client, db_ctx):
    cen = DuasClinicas()
    definir_liberacao_admin(cen.org_a, "pandoo", True)
    autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={
        "pandoo_cenario_padrao": "clinica", "pandoo_cenario_imagem": PNG, "pandoo_cenario_tom": "claro"})
    corpo = {"titulo": "R", "modelo": "roleta",
             "conteudo": {"versao": 1, "itens": [{"id": f"i{i}", "pergunta": {"texto": "x", "imagem": PNG}} for i in range(2)]}}
    jogo = autenticado(client, cen.prof_a1).post("/api/pandoo/jogos", json=corpo).get_json()["id"]
    efetivo = autenticado(client, cen.prof_a1).get(f"/api/pandoo/jogos/{jogo}").get_json()["cenario_efetivo"]
    assert efetivo == {"tipo": "clinica", "imagem": PNG, "tom": "claro"}
```

- [ ] **Step 2: Run — expect FAIL**.

- [ ] **Step 3: Implement** in `atualizar_organizacao`, next to the agenda-hours block (import `CENARIOS, TONS, imagem_cenario_valida` from `pandoo_service`):

```python
    # Pandoo (25/09/2026): cenário padrão dos jogos — só mexe no que veio no corpo.
    cen_padrao = org_atual.get("pandoo_cenario_padrao") or "bambu"
    cen_imagem = org_atual.get("pandoo_cenario_imagem")
    cen_tom = org_atual.get("pandoo_cenario_tom")
    if "pandoo_cenario_imagem" in body:
        cen_imagem = body.get("pandoo_cenario_imagem") or None
        if cen_imagem and not imagem_cenario_valida(cen_imagem):
            return jsonify({"erro": "Imagem do cenário inválida: envie JPG, PNG ou WebP de até 800 KB."}), 400
    if "pandoo_cenario_tom" in body:
        cen_tom = body.get("pandoo_cenario_tom") or None
        if cen_tom and cen_tom not in TONS:
            return jsonify({"erro": "Tom do cenário inválido."}), 400
    if "pandoo_cenario_padrao" in body:
        cen_padrao = body.get("pandoo_cenario_padrao")
        if cen_padrao not in CENARIOS:
            return jsonify({"erro": "Cenário inválido."}), 400
    if cen_padrao == "clinica" and not cen_imagem:
        return jsonify({"erro": "Envie a imagem da clínica para usar como cenário."}), 400
```
Extend the `UPDATE organizacoes` with `, pandoo_cenario_padrao = ?, pandoo_cenario_imagem = ?, pandoo_cenario_tom = ?` before `WHERE id = ?` and `cen_padrao, cen_imagem, cen_tom,` in the params before `u["organizacao_id"]`.

`auth_bp.py` `CAMPOS_ORG`: append `, pandoo_cenario_padrao, pandoo_cenario_tom`.

- [ ] **Step 4: Run — expect PASS** (5) + `tests/test_horario_agenda.py` (same route).

- [ ] **Step 5: Commit** — "Pandoo: cenário padrão da clínica".

### Task 8: Docs, suíte completa e PR

- [ ] **Step 1:** Full backend suite → all pass; `node --test frontend/tests/*.test.js` → 32 pass (unchanged).
- [ ] **Step 2: CLAUDE.md** — section 5 new item `o) Pandoo fase 1 — backend (25/09/2026)` (tables, module só-Admin, routes, mission gating, cenário, migration files); section 6 bullet "Pandoo: jogo = exercício `tipo='jogo'` + `pandoo_jogos`; Biblioteca não edita/duplica jogo; módulo só-Admin (`MODULOS_SO_ADMIN`)"; section 7 pending "migração do Pandoo em produção **antes** do `git pull`" and "PR B (tela do Pandoo) a fazer"; section 8 rows (`pandoo_service.py`, `pandoo_bp.py`, tests). Commit.
- [ ] **Step 3:** Push, open PR (summary; **passo manual**: rodar `backend/migracoes/migracao_pandoo.sql` no Supabase — ou `python3 migrar_pandoo.py` conferindo `(Postgres)` — **antes** do `git pull`; login não depende das colunas novas porque `CAMPOS_ORG` só lê colunas que a migração cria → **mesma regra da agenda: migração primeiro**), wait for CI, then **ask the user before merging** (schema).
