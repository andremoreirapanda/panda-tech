# White Label completo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `white_label` module real: gated colors/names plus app name/icon, a per-clinic login page, and a customizable Mundo da Criança (font, animated background, default mascot, celebration text).

**Architecture:** One backend rule file (`identidade_service.py`) computes the *effective* identity (clinic values with the module, Panda Tech defaults without). `/auth/me` returns the effective identity, so the whole front-end obeys the gate without per-screen checks. A new public blueprint serves the clinic login data and images (icon, mascot, scene) by `endereco_login`. Front-end gets a shared animated-scene file (`cenarios_animados.js`, later reused by Pandoo PR B), theme extensions in `util.js`, and new groups in Configurações.

**Tech Stack:** Flask + SQLite/Postgres (`db.py`), vanilla JS globals (no build), pytest, `node --test`, Playwright (via `uv run --no-project --with playwright`).

**Spec:** `docs/superpowers/specs/2026-09-25-white-label-completo-design.md`

## Global Constraints

- Tests from `backend/`: `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q` ; front: `node --test frontend/tests/*.test.js` (from repo root).
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- CSP: `script-src 'self'` (no inline JS), `img-src 'self' data:` (no `blob:`), fonts only from fonts.googleapis/gstatic.
- Defaults: cores `#5B4FE9`/`#FFB84D`; nomes "Lumi"/"XP"/"Medalha"; app "Panda Tech"; login message "Entre com sua conta para continuar a jornada."; fonte `fredoka`; fundo `estrelas`; mascote `🐻`; comemoração "Muito bem!!".
- Limits: `endereco_login` `^[a-z0-9](?:[a-z0-9-]{1,38})[a-z0-9]$` (3–40, unique); `app_nome` ≤ 30; `login_mensagem` ≤ 120; `mundo_comemoracao` ≤ 40; texts refuse `<` and `>`; icon and mascot images PNG/JPEG/WebP ≤ 500 KB.
- `mundo_fonte` ∈ {fredoka, baloo, nunito, escolar}; `mundo_fundo` ∈ {estrelas, bambu, mar, espaco, clinica, pandoo}; `mundo_mascote` ∈ `MASCOTES_VALIDOS` ∪ {"clinica"}.
- Logo (`logo_base64`, `logo_emoji`) and clinic `nome` are never gated.
- Never touch `backend/habilitar_rls_encanto_em_casa.sql`.

## Review Focus

1. Clinic without the module but with stored custom values: `/auth/me` must return defaults, Configurações must show stored values (locked), turning the module on must restore them — cached `localStorage` session must refresh on page load (else old colors linger).
2. Public routes must never leak data of a clinic without the module / inactive / `status_comercial = 'cancelada'`, and never return commercial fields.
3. `avatar_mascote = "clinica"` must not print the literal word "clinica" anywhere (lists, selects, agenda) — every display goes through `emojiMascote()`.
4. `mundo_fundo = clinica` or `pandoo`→`clinica` without a scene image must fall back to `estrelas` in the front and be refused (400) on PUT.
5. Partial PUT bodies (onboarding, other screens) must not erase WL fields.

---

### Task 1: Schema, migration and seeds

**Files:**
- Modify: `backend/schema.sql` (organizacoes, before `criado_em`)
- Create: `backend/migracoes/migracao_white_label.sql`, `backend/migrar_white_label.py`
- Modify: `.github/workflows/db-setup.yml`, `.github/workflows/tests.yml` (smoke job runs every migration — add this one next to `migracao_recursos_planos.sql`)
- Modify: `backend/seed.py` (demo clinic gets `endereco_login = 'clinica-encantar'`)
- Test: `backend/tests/test_white_label_schema.py`

**Interfaces:** Produces columns `endereco_login, app_nome, app_icone_base64, login_mensagem, mundo_fonte, mundo_fundo, mundo_mascote, mundo_mascote_imagem, mundo_comemoracao` (all TEXT, NULL default) and unique index `idx_organizacoes_endereco_login`.

- [ ] **Step 1: Failing test**

```python
"""White Label completo (25/09/2026): colunas novas em organizacoes."""
import db
import migrar_white_label

COLUNAS = ["endereco_login", "app_nome", "app_icone_base64", "login_mensagem", "mundo_fonte",
           "mundo_fundo", "mundo_mascote", "mundo_mascote_imagem", "mundo_comemoracao"]


def test_colunas_existem(db_ctx):
    linhas = db.get_db().execute("PRAGMA table_info(organizacoes)").fetchall()
    nomes = {l["name"] for l in linhas}
    assert set(COLUNAS) <= nomes


def test_endereco_unico(db_ctx):
    db.execute("INSERT INTO organizacoes (nome, endereco_login) VALUES ('A', 'abc')")
    import pytest, sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO organizacoes (nome, endereco_login) VALUES ('B', 'abc')")
    db.execute("INSERT INTO organizacoes (nome) VALUES ('C')")
    db.execute("INSERT INTO organizacoes (nome) VALUES ('D')")  # NULL repetido pode


def test_migracao_idempotente(db_ctx, capsys):
    migrar_white_label.migrar()
    migrar_white_label.migrar()
    assert "já existia" in capsys.readouterr().out
```

- [ ] **Step 2: Run** `pytest tests/test_white_label_schema.py -q` → FAIL (no module / no column).
- [ ] **Step 3: Implement.** In `schema.sql`, after `pandoo_cenario_tom TEXT,`:

```sql
    -- White Label completo (25/09/2026): só valem com o módulo white_label;
    -- NULL = padrão Panda Tech (ver identidade_service.PADROES).
    endereco_login        TEXT,
    app_nome              TEXT,
    app_icone_base64      TEXT,
    login_mensagem        TEXT,
    mundo_fonte           TEXT,
    mundo_fundo           TEXT,
    mundo_mascote         TEXT,
    mundo_mascote_imagem  TEXT,
    mundo_comemoracao     TEXT,
```
and after the table: `CREATE UNIQUE INDEX IF NOT EXISTS idx_organizacoes_endereco_login ON organizacoes(endereco_login);` (SQLite and Postgres both allow many NULLs in a unique index).

`migracoes/migracao_white_label.sql`: header comment in the house style + 9 `ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS <col> TEXT;` + the `CREATE UNIQUE INDEX IF NOT EXISTS`.

`migrar_white_label.py`: copy `migrar_horario_agenda.py` with `COLUNAS = [(c, "TEXT") for c in (...)]`, and after the loop run `db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_organizacoes_endereco_login ON organizacoes(endereco_login)")` (commit for SQLite via `db.get_db().commit()` if `db.execute` doesn't autocommit — check how `db.execute` behaves and follow it).

Workflows: add a step "Aplicar migração incremental (white label)" running `psql ... -f backend/migracoes/migracao_white_label.sql` in `db-setup.yml`, and the same file in the smoke list in `tests.yml`.

Seed: in the demo clinic INSERT/UPDATE set `endereco_login = 'clinica-encantar'`.

- [ ] **Step 4: Run** the test → PASS; full suite green.
- [ ] **Step 5: Commit** "White Label: colunas novas e migração".

---

### Task 2: `identidade_service.py` — effective identity, validation, address

**Files:**
- Create: `backend/identidade_service.py`
- Modify: `backend/blueprints/admin_bp.py` (`_slug_plano` uses shared `slug_de`)
- Test: `backend/tests/test_identidade_service.py`

**Interfaces — Produces:**
- `PADROES: dict` (keys below)
- `CAMPOS_GATED: tuple` = ("cor_primaria","cor_secundaria","nome_ia","nome_moeda_gamificacao","nome_medalha_generico","app_nome","login_mensagem","mundo_fonte","mundo_fundo","mundo_mascote","mundo_comemoracao")
- `FONTES = ("fredoka","baloo","nunito","escolar")`, `FUNDOS = ("estrelas","bambu","mar","espaco","clinica","pandoo")`
- `slug_de(texto, existe: callable, padrao="clinica") -> str`
- `gerar_endereco_login(nome) -> str` (unique in `organizacoes`)
- `garantir_endereco_login(org_id) -> str` (fills when NULL)
- `validar_endereco_login(valor, org_id) -> (valor|None, erro|None, status)` status 400/409
- `validar_texto(valor, maximo, rotulo) -> (valor|None, erro|None)` (empty → None)
- `mime_imagem(b64) -> "image/png"|"image/jpeg"|"image/webp"|None`
- `imagem_pequena_valida(b64) -> bool` (≤ 500 KB and `mime_imagem` not None)
- `versao_imagens(org) -> str` (10 hex chars of sha1 over icon+mascot+scene; "" if none)
- `identidade_efetiva(org: dict, ativo: bool) -> dict`

- [ ] **Step 1: Failing tests**

```python
"""White Label completo: regra única da identidade efetiva."""
import base64
import db
import identidade_service as ids

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
JPG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64).decode()
WEBP = base64.b64encode(b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64).decode()
GIF = base64.b64encode(b"GIF89a" + b"\x00" * 64).decode()

ORG = {"nome": "Clínica X", "logo_emoji": "🌈", "logo_base64": None, "cor_primaria": "#112233",
       "cor_secundaria": "#445566", "nome_ia": "Nina", "nome_moeda_gamificacao": "Estrelinhas",
       "nome_medalha_generico": "Troféu", "app_nome": "Clínica X App", "login_mensagem": "Oi!",
       "mundo_fonte": "baloo", "mundo_fundo": "mar", "mundo_mascote": "🦊", "mundo_comemoracao": "Arrasou!",
       "endereco_login": "clinica-x", "app_icone_base64": None, "mundo_mascote_imagem": None,
       "pandoo_cenario_padrao": "bambu", "pandoo_cenario_imagem": None, "pandoo_cenario_tom": None}


def test_com_modulo_valem_os_da_clinica():
    e = ids.identidade_efetiva(dict(ORG), True)
    assert e["cor_primaria"] == "#112233" and e["nome_moeda_gamificacao"] == "Estrelinhas"
    assert e["mundo_fundo"] == "mar" and e["app_nome"] == "Clínica X App" and e["white_label_ativo"] is True


def test_sem_modulo_valem_os_padroes_mas_logo_e_nome_passam():
    e = ids.identidade_efetiva(dict(ORG), False)
    for campo in ids.CAMPOS_GATED:
        assert e[campo] == ids.PADROES[campo], campo
    assert e["nome"] == "Clínica X" and e["logo_emoji"] == "🌈" and e["white_label_ativo"] is False


def test_null_vira_padrao_com_modulo():
    org = dict(ORG, app_nome=None, mundo_fonte=None, cor_primaria=None)
    e = ids.identidade_efetiva(org, True)
    assert e["app_nome"] == "Panda Tech" and e["mundo_fonte"] == "fredoka" and e["cor_primaria"] == "#5B4FE9"


def test_imagens_nao_vao_no_efetivo_mas_flags_sim():
    org = dict(ORG, app_icone_base64=PNG, mundo_mascote_imagem=PNG)
    e = ids.identidade_efetiva(org, True)
    assert "app_icone_base64" not in e and "mundo_mascote_imagem" not in e
    assert e["tem_icone"] is True and e["tem_mascote_imagem"] is True and e["versao_imagens"]
    e2 = ids.identidade_efetiva(org, False)
    assert e2["tem_icone"] is False and e2["tem_mascote_imagem"] is False


def test_mime_imagem():
    assert ids.mime_imagem(PNG) == "image/png"
    assert ids.mime_imagem(JPG) == "image/jpeg"
    assert ids.mime_imagem(WEBP) == "image/webp"
    assert ids.mime_imagem(GIF) is None
    assert ids.mime_imagem("não é base64 \" onerror=") is None


def test_imagem_pequena_valida_limite():
    grande = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * (501 * 1024)).decode()
    assert ids.imagem_pequena_valida(PNG) and not ids.imagem_pequena_valida(grande)


def test_validar_texto():
    assert ids.validar_texto("  Olá  ", 10, "Nome") == ("Olá", None)
    assert ids.validar_texto("", 10, "Nome") == (None, None)
    assert ids.validar_texto("x" * 11, 10, "Nome")[1]
    assert ids.validar_texto("<b>", 10, "Nome")[1]


def test_slug_e_endereco(db_ctx):
    assert ids.slug_de("Clínica Ênçantar!!", lambda s: False) == "clinica-encantar"
    db.execute("INSERT INTO organizacoes (nome, endereco_login) VALUES ('A', 'clinica-encantar')")
    assert ids.gerar_endereco_login("Clínica Encantar") == "clinica-encantar-2"
    assert ids.gerar_endereco_login("!!") == "clinica"


def test_validar_endereco(db_ctx):
    a = db.execute("INSERT INTO organizacoes (nome, endereco_login) VALUES ('A', 'ocupado')")
    b = db.execute("INSERT INTO organizacoes (nome) VALUES ('B')")
    assert ids.validar_endereco_login("Minha-Clinica", b) == ("minha-clinica", None, 200)
    assert ids.validar_endereco_login("ab", b)[2] == 400
    assert ids.validar_endereco_login("com espaço", b)[2] == 400
    assert ids.validar_endereco_login("-abc", b)[2] == 400
    assert ids.validar_endereco_login("ocupado", b)[2] == 409
    assert ids.validar_endereco_login("ocupado", a) == ("ocupado", None, 200)


def test_garantir_endereco(db_ctx):
    org = db.execute("INSERT INTO organizacoes (nome) VALUES ('Clínica Sol')")
    assert ids.garantir_endereco_login(org) == "clinica-sol"
    assert ids.garantir_endereco_login(org) == "clinica-sol"
```

- [ ] **Step 2: Run** → FAIL (module missing).
- [ ] **Step 3: Implement** `identidade_service.py`:

```python
"""White Label completo (spec 25/09/2026): a regra única da identidade da
clínica. Com o módulo white_label, valem os valores da clínica (NULL vira o
padrão); sem ele, valem os padrões Panda Tech — os valores da clínica ficam
guardados e voltam se o módulo for ligado de novo. Logo e nome da clínica
nunca são travados."""
import hashlib
import re
import unicodedata

from db import query_one, execute
from validacao_arquivo import _decodificar_binario

PADROES = {
    "cor_primaria": "#5B4FE9", "cor_secundaria": "#FFB84D",
    "nome_ia": "Lumi", "nome_moeda_gamificacao": "XP", "nome_medalha_generico": "Medalha",
    "app_nome": "Panda Tech", "login_mensagem": "Entre com sua conta para continuar a jornada.",
    "mundo_fonte": "fredoka", "mundo_fundo": "estrelas", "mundo_mascote": "🐻",
    "mundo_comemoracao": "Muito bem!!",
}
CAMPOS_GATED = tuple(PADROES)
FONTES = ("fredoka", "baloo", "nunito", "escolar")
FUNDOS = ("estrelas", "bambu", "mar", "espaco", "clinica", "pandoo")
MAX_IMAGEM_PEQUENA = 500 * 1024
_ENDERECO = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
_PASSAM_SEMPRE = ("id", "nome", "logo_emoji", "logo_base64", "plano", "especialidades_json",
                  "agenda_permissao_total_padrao", "agenda_hora_inicio", "agenda_hora_fim",
                  "pandoo_cenario_padrao", "pandoo_cenario_tom", "endereco_login")


def slug_de(texto, existe, padrao="clinica"):
    base = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:36].strip("-") or padrao
    valor, n = base, 2
    while existe(valor):
        valor, n = f"{base}-{n}", n + 1
    return valor


def _endereco_existe(valor):
    return bool(query_one("SELECT 1 FROM organizacoes WHERE endereco_login = ?", (valor,)))


def gerar_endereco_login(nome):
    base = slug_de(nome, lambda s: False)
    if len(base) < 3:
        base = "clinica"
    return slug_de(base, _endereco_existe)


def garantir_endereco_login(org_id):
    org = query_one("SELECT nome, endereco_login FROM organizacoes WHERE id = ?", (org_id,))
    if not org:
        return None
    if org["endereco_login"]:
        return org["endereco_login"]
    valor = gerar_endereco_login(org["nome"])
    execute("UPDATE organizacoes SET endereco_login = ? WHERE id = ?", (valor, org_id))
    return valor


def validar_endereco_login(valor, org_id):
    valor = (valor or "").strip().lower()
    if not _ENDERECO.match(valor):
        return None, "Endereço inválido: use de 3 a 40 letras minúsculas, números e hífens (sem começar ou terminar com hífen).", 400
    dono = query_one("SELECT id FROM organizacoes WHERE endereco_login = ?", (valor,))
    if dono and dono["id"] != org_id:
        return None, "Este endereço já está em uso por outra clínica.", 409
    return valor, None, 200


def validar_texto(valor, maximo, rotulo):
    valor = (valor or "").strip() if isinstance(valor, str) or valor is None else None
    if valor is None:
        return None, f"{rotulo} inválido."
    if not valor:
        return None, None
    if len(valor) > maximo:
        return None, f"{rotulo}: até {maximo} caracteres."
    if "<" in valor or ">" in valor:
        return None, f"{rotulo}: não use os caracteres < e >."
    return valor, None


def mime_imagem(b64):
    binario = _decodificar_binario(b64) if isinstance(b64, str) else None
    if not binario:
        return None
    if binario.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if binario.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if binario[:4] == b"RIFF" and binario[8:12] == b"WEBP":
        return "image/webp"
    return None


def imagem_pequena_valida(b64):
    return isinstance(b64, str) and len(b64) * 3 // 4 <= MAX_IMAGEM_PEQUENA and mime_imagem(b64) is not None


def versao_imagens(org):
    partes = [org.get("app_icone_base64") or "", org.get("mundo_mascote_imagem") or "", org.get("pandoo_cenario_imagem") or ""]
    if not any(partes):
        return ""
    return hashlib.sha1("|".join(partes).encode()).hexdigest()[:10]


def identidade_efetiva(org, ativo):
    e = {k: org.get(k) for k in _PASSAM_SEMPRE if k in org}
    for campo, padrao in PADROES.items():
        e[campo] = (org.get(campo) or padrao) if ativo else padrao
    e["white_label_ativo"] = bool(ativo)
    e["tem_icone"] = bool(ativo and org.get("app_icone_base64"))
    e["tem_mascote_imagem"] = bool(ativo and org.get("mundo_mascote_imagem"))
    e["tem_cenario_imagem"] = bool(ativo and org.get("pandoo_cenario_imagem"))
    e["versao_imagens"] = versao_imagens(org) if ativo else ""
    if e["mundo_mascote"] == "clinica" and not e["tem_mascote_imagem"]:
        e["mundo_mascote"] = PADROES["mundo_mascote"]
    return e
```

In `admin_bp._slug_plano`: `return slug_de(nome, lambda c: bool(query_one("SELECT 1 FROM planos WHERE codigo = ?", (c,))), padrao="plano")` (import `slug_de`; drop now-unused `unicodedata` import only if nothing else uses it). Note `slug_de` truncates to 36 chars — plan codes existing tests must still pass (run `test_planos_configuraveis_api.py`).

- [ ] **Step 4: Run** new tests + `tests/test_planos_configuraveis_api.py` → PASS.
- [ ] **Step 5: Commit** "White Label: identidade_service (identidade efetiva, validações, endereço)".

---

### Task 3: `/auth/me`, Configurações API (GET/PUT organização), clinic creation, module text

**Files:**
- Modify: `backend/blueprints/auth_bp.py` (`CAMPOS_ORG`, `_org_com_modulos`)
- Modify: `backend/blueprints/pessoas_bp.py` (`obter_organizacao`, `atualizar_organizacao`)
- Modify: `backend/blueprints/admin_bp.py` (`criar_clinica` sets `endereco_login`)
- Modify: `backend/modulos_service.py` (white_label description)
- Test: `backend/tests/test_white_label_api.py`

**Interfaces:** Consumes Task 2. Produces: `/auth/me` → `organizacao` = `identidade_efetiva(...)` + `modulos_habilitados` + `especialidades`; `GET /pessoas/organizacao` adds `white_label_ativo`, `endereco_login` (generated if NULL); `PUT` accepts the new fields.

- [ ] **Step 1: Failing tests**

```python
"""White Label completo: trava real do módulo e campos novos em Configurações."""
import base64
import db
from factories import DuasClinicas
from conftest import autenticado
from modulos_service import definir_liberacao_admin

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def _me_org(client, u):
    return autenticado(client, u).get("/api/auth/me").get_json()["organizacao"]


def test_sem_modulo_me_devolve_padroes_e_guarda_valores(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    assert c.put("/api/pessoas/organizacao", json={"cor_primaria": "#112233", "nome_moeda_gamificacao": "Estrelinhas",
                                                   "mundo_fundo": "mar"}).status_code == 200
    org = _me_org(client, cen.gestor_a)
    assert org["cor_primaria"] == "#5B4FE9" and org["nome_moeda_gamificacao"] == "XP" and org["mundo_fundo"] == "estrelas"
    guardado = autenticado(client, cen.gestor_a).get("/api/pessoas/organizacao").get_json()
    assert guardado["cor_primaria"] == "#112233" and guardado["white_label_ativo"] is False
    definir_liberacao_admin(cen.org_a, "white_label", True)
    org = _me_org(client, cen.gestor_a)
    assert org["cor_primaria"] == "#112233" and org["mundo_fundo"] == "mar" and org["white_label_ativo"] is True


def test_me_nao_carrega_imagens_grandes(client, db_ctx):
    cen = DuasClinicas()
    definir_liberacao_admin(cen.org_a, "white_label", True)
    autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={"app_icone_base64": PNG})
    org = _me_org(client, cen.gestor_a)
    assert "app_icone_base64" not in org and org["tem_icone"] is True and org["versao_imagens"]


def test_campos_novos_salvam_e_put_parcial_nao_apaga(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    corpo = {"app_nome": "Encantar App", "login_mensagem": "Bem-vindo!", "mundo_fonte": "nunito",
             "mundo_fundo": "espaco", "mundo_mascote": "🦊", "mundo_comemoracao": "Arrasou!",
             "app_icone_base64": PNG, "mundo_mascote_imagem": PNG, "endereco_login": "encantar"}
    assert c.put("/api/pessoas/organizacao", json=corpo).status_code == 200
    autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={"nome": "Outro nome"})
    o = db.query_one("SELECT * FROM organizacoes WHERE id = ?", (cen.org_a,))
    for k, v in corpo.items():
        assert o[k] == v, k


def test_limpar_campo_texto_volta_ao_padrao(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    c.put("/api/pessoas/organizacao", json={"app_nome": "X"})
    autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={"app_nome": ""})
    assert db.query_one("SELECT app_nome FROM organizacoes WHERE id = ?", (cen.org_a,))["app_nome"] is None


def test_recusas(client, db_ctx):
    cen = DuasClinicas()
    ruins = [{"app_nome": "x" * 31}, {"login_mensagem": "x" * 121}, {"mundo_comemoracao": "x" * 41},
             {"mundo_comemoracao": "<b>oi</b>"}, {"mundo_fonte": "comic"}, {"mundo_fundo": "praia"},
             {"mundo_mascote": "🐙"}, {"mundo_mascote": "clinica"}, {"mundo_fundo": "clinica"},
             {"app_icone_base64": base64.b64encode(b"GIF89a" + b"\x00" * 10).decode()},
             {"mundo_mascote_imagem": "not base64 \" onerror="}, {"endereco_login": "a b"}]
    for corpo in ruins:
        r = autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json=corpo)
        assert r.status_code == 400, corpo


def test_mascote_e_fundo_clinica_com_imagem(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    r = c.put("/api/pessoas/organizacao", json={"mundo_mascote_imagem": PNG, "mundo_mascote": "clinica",
                                                 "pandoo_cenario_imagem": PNG, "mundo_fundo": "clinica"})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_endereco_repetido_409_e_gerado_na_leitura(client, db_ctx):
    cen = DuasClinicas()
    end_b = autenticado(client, cen.gestor_b).get("/api/pessoas/organizacao").get_json()["endereco_login"]
    assert end_b == "clinica-b"
    r = autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={"endereco_login": "clinica-b"})
    assert r.status_code == 409


def test_criar_clinica_gera_endereco(client, db_ctx):
    from factories import novo_usuario
    import planos_padrao
    planos_padrao.criar_planos_padrao_para_teste()
    admin = novo_usuario(None, "Admin", "admin@x.com", "admin_master")
    r = autenticado(client, admin).post("/api/admin/clinicas", json={"nome": "Clínica Nova Vida", "plano": "starter",
                                                                     "gestor_email": "g@nova.com"})
    assert r.status_code == 201, r.get_data(as_text=True)
    o = db.query_one("SELECT endereco_login FROM organizacoes WHERE id = ?", (r.get_json()["id"],))
    assert o["endereco_login"] == "clinica-nova-vida"
```

(If `criar_planos_padrao_para_teste` / admin creation helpers differ, copy the setup used in `tests/test_planos_configuraveis_api.py`.)

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**

`auth_bp.py`: `CAMPOS_ORG` adds `endereco_login, app_nome, app_icone_base64, login_mensagem, mundo_fonte, mundo_fundo, mundo_mascote, mundo_mascote_imagem, mundo_comemoracao, pandoo_cenario_imagem`; `_org_com_modulos`:

```python
def _org_com_modulos(organizacao_id):
    org = query_one(f"SELECT {CAMPOS_ORG} FROM organizacoes WHERE id = ?", (organizacao_id,))
    if not org:
        return None
    modulos = modulos_habilitados_clinica(organizacao_id, org["plano"])
    # White Label completo (25/09/2026): a identidade devolvida já é a efetiva —
    # sem o módulo, cores/nomes/Mundo voltam ao padrão Panda Tech.
    efetiva = identidade_efetiva(org, "white_label" in modulos)
    efetiva["modulos_habilitados"] = sorted(modulos)
    efetiva["especialidades"] = json.loads(efetiva.pop("especialidades_json", None) or "[]")
    return efetiva
```

`pessoas_bp.obter_organizacao`: after loading, `org["endereco_login"] = garantir_endereco_login(org["id"])`, `org["white_label_ativo"] = modulo_ativo_para_clinica(org["id"], org["plano"], "white_label")`.

`pessoas_bp.atualizar_organizacao`: before the `UPDATE`, a block (partial-body rule — only keys present in `body`):

```python
    # White Label completo (25/09/2026): salva mesmo sem o módulo (fica
    # guardado; quem decide se vale é identidade_efetiva). Só mexe no que veio.
    wl = {c: org_atual.get(c) for c in ("endereco_login", "app_nome", "app_icone_base64", "login_mensagem",
                                         "mundo_fonte", "mundo_fundo", "mundo_mascote", "mundo_mascote_imagem",
                                         "mundo_comemoracao")}
    for campo, maximo, rotulo in (("app_nome", 30, "Nome do app"), ("login_mensagem", 120, "Mensagem de boas-vindas"),
                                  ("mundo_comemoracao", 40, "Texto da comemoração")):
        if campo in body:
            wl[campo], erro = validar_texto(body.get(campo), maximo, rotulo)
            if erro:
                return jsonify({"erro": erro}), 400
    for campo, opcoes, rotulo in (("mundo_fonte", FONTES, "Fonte"), ("mundo_fundo", FUNDOS, "Fundo")):
        if campo in body:
            valor = body.get(campo) or None
            if valor is not None and valor not in opcoes:
                return jsonify({"erro": f"{rotulo} inválido."}), 400
            wl[campo] = valor
    for campo, rotulo in (("app_icone_base64", "Ícone do app"), ("mundo_mascote_imagem", "Imagem do mascote")):
        if campo in body:
            valor = body.get(campo) or None
            if valor is not None and not imagem_pequena_valida(valor):
                return jsonify({"erro": f"{rotulo} inválido: envie PNG, JPG ou WebP de até 500 KB."}), 400
            wl[campo] = valor
    if "mundo_mascote" in body:
        valor = body.get("mundo_mascote") or None
        if valor is not None and valor != "clinica" and valor not in MASCOTES_VALIDOS:
            return jsonify({"erro": "Escolha um dos mascotes disponíveis."}), 400
        wl["mundo_mascote"] = valor
    if wl["mundo_mascote"] == "clinica" and not wl["mundo_mascote_imagem"]:
        return jsonify({"erro": "Envie a imagem do mascote da clínica para usá-la como padrão."}), 400
    if wl["mundo_fundo"] == "clinica" and not cen_imagem:
        return jsonify({"erro": "Envie a imagem da clínica para usar como fundo."}), 400
    if "endereco_login" in body:
        wl["endereco_login"], erro, status = validar_endereco_login(body.get("endereco_login"), u["organizacao_id"])
        if erro:
            return jsonify({"erro": erro}), status
```
(this block goes AFTER the Pandoo scene block so `cen_imagem` is final), then extend the `UPDATE` with the 9 columns and values `wl[...]`. `MASCOTES_VALIDOS` is defined later in the module — fine at call time.

`admin_bp.criar_clinica`: after `org_id = execute(...)`: `execute("UPDATE organizacoes SET endereco_login = ? WHERE id = ?", (gerar_endereco_login(nome), org_id))`.

`modulos_service.py` white_label description:
"Deixa o app com a cara da clínica: cores, nomes do assistente, da moeda e da medalha, nome e ícone do app no celular, tela de login própria com a marca e a mensagem da clínica, e um Mundo da Criança personalizado (fonte, fundo animado, mascote e texto da comemoração)."

- [ ] **Step 4: Run** new file + `tests/test_pandoo_cenario.py tests/test_auth.py` + full suite → PASS (fix any test that read custom colors from `/auth/me` without the module: give it the module via `definir_liberacao_admin`, never loosen the rule).
- [ ] **Step 5: Commit** "White Label: trava real do módulo e campos novos na organização".

---

### Task 4: Public blueprint (login data, icon, mascot, scene, manifest)

**Files:**
- Create: `backend/blueprints/publico_bp.py`; Modify: `backend/app.py` (import + `register_blueprint`)
- Test: `backend/tests/test_white_label_publico.py`

**Interfaces:** Produces `GET /api/publico/clinica/<endereco>` → `{nome, logo_emoji, logo_base64, cor_primaria, cor_secundaria, app_nome, login_mensagem, mundo_mascote, tem_mascote_imagem, tem_icone, versao_imagens, endereco_login}`; `GET .../icone`, `.../mascote`, `.../cenario` (image bytes); `GET .../manifest.webmanifest`.

- [ ] **Step 1: Failing tests**

```python
"""White Label completo: rotas públicas da tela de login da clínica."""
import base64
import db
from factories import DuasClinicas
from modulos_service import definir_liberacao_admin

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PNG = base64.b64encode(PNG_BYTES).decode()


def _prep(com_modulo=True, **campos):
    cen = DuasClinicas()
    campos.setdefault("endereco_login", "clinica-a")
    sets = ", ".join(f"{k} = ?" for k in campos)
    db.execute(f"UPDATE organizacoes SET {sets} WHERE id = ?", (*campos.values(), cen.org_a))
    if com_modulo:
        definir_liberacao_admin(cen.org_a, "white_label", True)
    return cen


def test_dados_publicos_sem_campos_comerciais(client, db_ctx):
    _prep(app_nome="Encantar", login_mensagem="Oi!", contato_email="segredo@x.com", cnpj="123")
    r = client.get("/api/publico/clinica/clinica-a")
    assert r.status_code == 200
    d = r.get_json()
    assert d["app_nome"] == "Encantar" and d["login_mensagem"] == "Oi!"
    texto = r.get_data(as_text=True)
    assert "segredo@x.com" not in texto and "cnpj" not in d and "plano" not in d and "status_comercial" not in d


def test_404_sem_modulo_inativa_cancelada_ou_inexistente(client, db_ctx):
    _prep(com_modulo=False)
    assert client.get("/api/publico/clinica/clinica-a").status_code == 404
    assert client.get("/api/publico/clinica/nao-existe").status_code == 404


def test_404_cancelada_e_inativa(client, db_ctx):
    cen = _prep(status_comercial="cancelada")
    assert client.get("/api/publico/clinica/clinica-a").status_code == 404
    db.execute("UPDATE organizacoes SET status_comercial = 'ativa', ativo = 0 WHERE id = ?", (cen.org_a,))
    assert client.get("/api/publico/clinica/clinica-a").status_code == 404
    assert client.get("/api/publico/clinica/clinica-a/icone").status_code == 404


def test_imagens_com_content_type(client, db_ctx):
    _prep(app_icone_base64=PNG, mundo_mascote_imagem=PNG, pandoo_cenario_imagem=PNG)
    for rota in ("icone", "mascote", "cenario"):
        r = client.get(f"/api/publico/clinica/clinica-a/{rota}")
        assert r.status_code == 200 and r.mimetype == "image/png" and r.data == PNG_BYTES, rota
        assert "max-age" in r.headers.get("Cache-Control", "")


def test_imagem_ausente_404(client, db_ctx):
    _prep()
    assert client.get("/api/publico/clinica/clinica-a/icone").status_code == 404


def test_manifest(client, db_ctx):
    _prep(app_nome="Encantar", app_icone_base64=PNG, cor_primaria="#112233")
    r = client.get("/api/publico/clinica/clinica-a/manifest.webmanifest")
    assert r.status_code == 200 and r.mimetype == "application/manifest+json"
    m = r.get_json(force=True)
    assert m["name"] == "Encantar" and m["short_name"] == "Encantar" and m["theme_color"] == "#112233"
    assert m["start_url"] == "/#/entrar/clinica-a" and m["display"] == "standalone"
    assert m["icons"][0]["src"].startswith("/api/publico/clinica/clinica-a/icone")
```

- [ ] **Step 2: Run** → FAIL (404 on everything / blueprint missing — the first test fails).
- [ ] **Step 3: Implement** `publico_bp.py`:

```python
"""White Label completo (25/09/2026): rotas SEM login para a tela de login
própria da clínica (#/entrar/<endereco>) e para as imagens da identidade
(ícone do app, mascote, cenário) — usadas como URL porque a CSP não deixa
usar blob: e o manifest precisa de URL. Só respondem para clínica ativa,
não cancelada e com o módulo white_label; nunca devolvem dado comercial."""
import json

from flask import Blueprint, jsonify, Response, abort

from db import query_one
from identidade_service import identidade_efetiva, mime_imagem
from modulos_service import modulo_ativo_para_clinica
from validacao_arquivo import _decodificar_binario

bp = Blueprint("publico", __name__, url_prefix="/api/publico")

_CAMPOS = """id, nome, plano, ativo, status_comercial, logo_emoji, logo_base64, cor_primaria, cor_secundaria,
             nome_ia, nome_moeda_gamificacao, nome_medalha_generico, app_nome, app_icone_base64, login_mensagem,
             mundo_fonte, mundo_fundo, mundo_mascote, mundo_mascote_imagem, mundo_comemoracao, endereco_login,
             pandoo_cenario_padrao, pandoo_cenario_imagem, pandoo_cenario_tom"""


def _clinica(endereco):
    org = query_one(f"SELECT {_CAMPOS} FROM organizacoes WHERE endereco_login = ?", ((endereco or "").lower(),))
    if not org or not org["ativo"] or org["status_comercial"] == "cancelada":
        abort(404)
    if not modulo_ativo_para_clinica(org["id"], org["plano"], "white_label"):
        abort(404)
    return org


@bp.get("/clinica/<endereco>")
def dados_login(endereco):
    org = _clinica(endereco)
    e = identidade_efetiva(org, True)
    return jsonify({k: e[k] for k in ("nome", "logo_emoji", "logo_base64", "cor_primaria", "cor_secundaria",
                                      "app_nome", "login_mensagem", "mundo_mascote", "tem_mascote_imagem",
                                      "tem_icone", "versao_imagens", "endereco_login")})


def _imagem(b64):
    mime = mime_imagem(b64) if b64 else None
    if not mime:
        abort(404)
    resp = Response(_decodificar_binario(b64), mimetype=mime)
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@bp.get("/clinica/<endereco>/icone")
def icone(endereco):
    return _imagem(_clinica(endereco)["app_icone_base64"])


@bp.get("/clinica/<endereco>/mascote")
def mascote(endereco):
    return _imagem(_clinica(endereco)["mundo_mascote_imagem"])


@bp.get("/clinica/<endereco>/cenario")
def cenario(endereco):
    return _imagem(_clinica(endereco)["pandoo_cenario_imagem"])


@bp.get("/clinica/<endereco>/manifest.webmanifest")
def manifest(endereco):
    org = _clinica(endereco)
    e = identidade_efetiva(org, True)
    icones = []
    if e["tem_icone"]:
        icones.append({"src": f"/api/publico/clinica/{org['endereco_login']}/icone?v={e['versao_imagens']}",
                       "sizes": "512x512", "type": mime_imagem(org["app_icone_base64"])})
    corpo = {"name": e["app_nome"], "short_name": e["app_nome"][:12] if len(e["app_nome"]) > 12 else e["app_nome"],
             "start_url": f"/#/entrar/{org['endereco_login']}", "display": "standalone",
             "background_color": "#FFFFFF", "theme_color": e["cor_primaria"], "icons": icones}
    return Response(json.dumps(corpo, ensure_ascii=False), mimetype="application/manifest+json")
```
(test uses "Encantar" ≤ 12 so `short_name == name`.) Check `add_cors_headers` in `app.py` doesn't force `application/json`/no-store on these responses; if it sets `Cache-Control: no-store` for `/api/`, exempt `/api/publico/` images.

- [ ] **Step 4: Run** → PASS; full suite green.
- [ ] **Step 5: Commit** "White Label: rotas públicas (login da clínica, ícone, mascote, cenário, manifest)".

---

### Task 5: Default mascot for new patients + "clinica" mascot choice

**Files:**
- Modify: `backend/blueprints/pessoas_bp.py` (`criar_paciente_core`, `PUT /pacientes/<id>/mascote` at ~l.1135)
- Test: `backend/tests/test_white_label_mascote.py`

**Interfaces:** Produces helper `mascote_padrao_clinica(org_id) -> str` (effective `mundo_mascote`), `mascote_aceito(org_id, valor) -> bool`.

- [ ] **Step 1: Failing tests**

```python
"""White Label completo: mascote padrão da clínica para pacientes novos."""
import base64
import db
from factories import DuasClinicas
from conftest import autenticado
from modulos_service import definir_liberacao_admin
from blueprints.pessoas_bp import criar_paciente_core

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def _masc(pid):
    return db.query_one("SELECT avatar_mascote FROM pacientes WHERE id = ?", (pid,))["avatar_mascote"]


def test_sem_escolha_usa_mascote_da_clinica_com_modulo(db_ctx):
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET mundo_mascote = '🦊' WHERE id = ?", (cen.org_a,))
    pid = criar_paciente_core(cen.org_a, "Sem módulo", "2019-01-01")
    assert _masc(pid if isinstance(pid, int) else pid["id"]) == "🐻"
    definir_liberacao_admin(cen.org_a, "white_label", True)
    pid = criar_paciente_core(cen.org_a, "Com módulo", "2019-01-01")
    assert _masc(pid if isinstance(pid, int) else pid["id"]) == "🦊"


def test_mascote_clinica_so_com_imagem_e_modulo(client, db_ctx):
    cen = DuasClinicas()
    from factories import vincular_responsavel
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    rota = f"/api/pessoas/pacientes/{cen.paciente_a1}/mascote"
    assert autenticado(client, cen.resp_a1).put(rota, json={"avatar_mascote": "clinica"}).status_code == 400
    db.execute("UPDATE organizacoes SET mundo_mascote_imagem = ? WHERE id = ?", (PNG, cen.org_a))
    assert autenticado(client, cen.resp_a1).put(rota, json={"avatar_mascote": "clinica"}).status_code == 400
    definir_liberacao_admin(cen.org_a, "white_label", True)
    assert autenticado(client, cen.resp_a1).put(rota, json={"avatar_mascote": "clinica"}).status_code == 200
    assert _masc(cen.paciente_a1) == "clinica"
```
(Read `criar_paciente_core`'s return value and the mascot route's permission rules first; adjust the two `pid` lines / who calls the route to match reality — the assertions stay.)

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** in `pessoas_bp.py`:

```python
def _org_identidade(org_id):
    org = query_one("SELECT * FROM organizacoes WHERE id = ?", (org_id,))
    return identidade_efetiva(org, modulo_ativo_para_clinica(org_id, org["plano"], "white_label")) if org else None


def mascote_padrao_clinica(org_id):
    e = _org_identidade(org_id)
    return (e or {}).get("mundo_mascote") or "🐻"


def mascote_aceito(org_id, valor):
    if valor in MASCOTES_VALIDOS:
        return True
    return valor == "clinica" and bool((_org_identidade(org_id) or {}).get("tem_mascote_imagem"))
```
`criar_paciente_core`: `if not mascote_aceito(organizacao_id, avatar_mascote): avatar_mascote = mascote_padrao_clinica(organizacao_id)`.
Mascot route: replace `if mascote not in MASCOTES_VALIDOS` with `if not mascote_aceito(<org of the patient>, mascote)`.
Also check `importacao_bp` for its own avatar validation and route it through `mascote_aceito`/`mascote_padrao_clinica` the same way if present.

- [ ] **Step 4: Run** → PASS; `tests/test_mascote_paciente.py tests/test_importacao_pacientes.py` + full suite green.
- [ ] **Step 5: Commit** "White Label: mascote padrão da clínica para pacientes novos".

---

### Task 6: Shared animated scenes + upload profiles (front, pure parts tested)

**Files:**
- Create: `frontend/js/cenarios_animados.js`, `frontend/tests/cenarios_animados.test.js`
- Modify: `frontend/css/components.css` (scene CSS), `frontend/index.html` (script after `mascote.js`)
- Modify: `frontend/js/envio_arquivos.js` (profiles `icone`, `cenario`), `frontend/tests/envio_arquivos.test.js`

**Interfaces — Produces:**
- `TONS_CENARIO = {estrelas:"claro", bambu:"escuro", mar:"escuro", espaco:"escuro"}`
- `cenarioDoMundo(org) -> {tipo, imagemUrl, tom}`; tipo ∈ estrelas|bambu|mar|espaco|clinica. Rules: fundo `pandoo` → `org.pandoo_cenario_padrao || "bambu"`; tipo `clinica` needs `org.tem_cenario_imagem` and `org.endereco_login`, else `estrelas`; `imagemUrl = /api/publico/clinica/<endereco>/cenario?v=<versao_imagens>`; tom `clinica` = `org.pandoo_cenario_tom || "claro"`.
- `montarCenarioAnimado(elemento, cenario)` — fills `elemento` (class `cenario-animado c-<tipo>`) with the elements; returns tom.
- Profiles `PERFIS_ENVIO.icone` (texto "📐 PNG com fundo transparente, JPG ou WebP · ideal 512 × 512 px (quadrado) · até 15 MB", ladoMax 512, limiteSaidaKB 480, manterTransparencia true, ladoMinAviso 192) and `PERFIS_ENVIO.cenario` (texto "📐 JPG, PNG ou WebP · ideal 1600 × 1600 px (quadrada) · até 15 MB · deixe o mais importante no centro", ladoMax 1600, limiteSaidaKB 780, manterTransparencia false, ladoMinAviso 800). Both `tiposAceitos: _TIPOS_IMAGEM, maxImagemMB: 15, maxOutrosMB: 0`.

- [ ] **Step 1: Failing tests** `frontend/tests/cenarios_animados.test.js`:

```js
// White Label completo (25/09/2026): cenários animados compartilhados.
const test = require("node:test");
const assert = require("node:assert/strict");
const c = require("../js/cenarios_animados.js");

const base = { endereco_login: "enc", versao_imagens: "abc", tem_cenario_imagem: false };

test("fundos prontos com o tom certo", () => {
    assert.deepEqual(c.cenarioDoMundo({ ...base, mundo_fundo: "estrelas" }), { tipo: "estrelas", imagemUrl: null, tom: "claro" });
    assert.deepEqual(c.cenarioDoMundo({ ...base, mundo_fundo: "mar" }), { tipo: "mar", imagemUrl: null, tom: "escuro" });
    assert.deepEqual(c.cenarioDoMundo({}), { tipo: "estrelas", imagemUrl: null, tom: "claro" });
});

test("'pandoo' segue o cenário padrão dos jogos", () => {
    assert.equal(c.cenarioDoMundo({ ...base, mundo_fundo: "pandoo", pandoo_cenario_padrao: "espaco" }).tipo, "espaco");
    assert.equal(c.cenarioDoMundo({ ...base, mundo_fundo: "pandoo" }).tipo, "bambu");
});

test("imagem da clínica com URL versionada, ou estrelas sem imagem", () => {
    const org = { ...base, mundo_fundo: "clinica", tem_cenario_imagem: true, pandoo_cenario_tom: "escuro" };
    assert.deepEqual(c.cenarioDoMundo(org), { tipo: "clinica", imagemUrl: "/api/publico/clinica/enc/cenario?v=abc", tom: "escuro" });
    assert.equal(c.cenarioDoMundo({ ...org, tem_cenario_imagem: false }).tipo, "estrelas");
    assert.equal(c.cenarioDoMundo({ ...base, mundo_fundo: "pandoo", pandoo_cenario_padrao: "clinica" }).tipo, "estrelas");
    assert.equal(c.cenarioDoMundo({ ...org, pandoo_cenario_tom: null }).tom, "claro");
});

test("endereço com caractere estranho não entra na URL", () => {
    const org = { ...base, endereco_login: "a\"b", mundo_fundo: "clinica", tem_cenario_imagem: true };
    assert.equal(c.cenarioDoMundo(org).tipo, "estrelas");
});
```
and in `envio_arquivos.test.js`:
```js
test("perfis do White Label: ícone e cenário", () => {
    assert.match(e.PERFIS_ENVIO.icone.texto, /512 × 512 px/);
    assert.equal(e.PERFIS_ENVIO.icone.manterTransparencia, true);
    assert.match(e.PERFIS_ENVIO.cenario.texto, /1600 × 1600 px/);
    assert.equal(e.validarEntradaEnvio(arq("f.png", "image/png", 4 * MB), "icone").ok, true);
});
```
(reuse the file's existing `arq`/`MB` helpers.)

- [ ] **Step 2: Run** `node --test frontend/tests/*.test.js` → FAIL.
- [ ] **Step 3: Implement** `cenarios_animados.js` — pure part:

```js
// ============================================================================
// cenarios_animados.js — Cenários animados (White Label completo, 25/09/2026)
// Usados no Mundo da Criança e, depois, pelo Pandoo (PR B). Visual copiado da
// prévia aprovada do Pandoo. A imagem da clínica vem por URL pública (a CSP
// não deixa usar blob:).
// ============================================================================
const TONS_CENARIO = { estrelas: "claro", bambu: "escuro", mar: "escuro", espaco: "escuro" };
const _ENDERECO_SEGURO = /^[a-z0-9-]{3,40}$/;

function cenarioDoMundo(org) {
    org = org || {};
    let tipo = org.mundo_fundo || "estrelas";
    if (tipo === "pandoo") tipo = org.pandoo_cenario_padrao || "bambu";
    if (tipo === "clinica") {
        if (org.tem_cenario_imagem && _ENDERECO_SEGURO.test(org.endereco_login || "")) {
            return { tipo: "clinica", imagemUrl: `/api/publico/clinica/${org.endereco_login}/cenario?v=${encodeURIComponent(org.versao_imagens || "")}`,
                     tom: org.pandoo_cenario_tom === "escuro" ? "escuro" : "claro" };
        }
        tipo = "estrelas";
    }
    if (!TONS_CENARIO[tipo]) tipo = "estrelas";
    return { tipo, imagemUrl: null, tom: TONS_CENARIO[tipo] };
}
```
DOM part `montarCenarioAnimado(elemento, cen)`: port of `montarCenario` from `.superpowers/brainstorm/490-1790374652/content/white-label-v3.html` (bambu: 8 hastes + 10 folhas; mar: 14 bolhas + 4 peixes 🐟🐠🐡🐢; espaco: 50 estrelas + 🪐 + 🚀; clinica: `elemento.style.backgroundImage = url("<imagemUrl>")` + 10 brilhos; estrelas: empty — the shell's own texture shows). Uses only numbers/fixed emoji in the generated HTML. Sets `elemento.className = "cenario-animado c-" + cen.tipo`, `aria-hidden="true"`, returns `cen.tom`. Export both with the `module.exports` guard used in `envio_arquivos.js`.

CSS (components.css) — port v3 scene CSS renamed under `.cenario-animado` (`.c-bambu .haste`, `.folha`, `.c-mar .bolha`, `.peixe`, `.c-espaco .estrela`, `.planeta`, `.c-clinica` `background:center/cover`, `.brilho`, keyframes `wlBalanca`, `wlFolha` (translate to `110vh`), `wlBolha` (`-110vh`), `wlNadar` (`-60px` → `540px`), `wlPisca`, `wlFlutua`), plus:
```css
.cenario-animado { position:absolute; inset:0; z-index:0; overflow:hidden; pointer-events:none; }
.cenario-animado .el { position:absolute; }
.cenario-animado.c-estrelas { display:none; }
@media (prefers-reduced-motion: reduce) { .cenario-animado .el { animation:none !important; } }
```
Profiles in `envio_arquivos.js` as in Interfaces.

- [ ] **Step 4: Run** node tests → PASS.
- [ ] **Step 5: Commit** "White Label: cenários animados compartilhados e perfis de envio".

---

### Task 7: Theme — fonts, title/icons/manifest, mascot helpers, session refresh

**Files:**
- Modify: `frontend/js/util.js` (`aplicarTemaClinica`, new pure helpers, `emojiMascote`), `frontend/js/mascote.js` (`svgMascote` image), `frontend/js/app.js` (refresh `/auth/me` on load), `frontend/css/layout.css` (`--fonte-crianca` inside `.shell-crianca`), `frontend/css/tokens.css` (`--fonte-crianca` default)
- Test: `frontend/tests/identidade.test.js`

**Interfaces — Produces (pure, exported under the `module.exports` guard at the end of util.js — check util.js already has one; `util_datas.test.js` requires it):**
- `FONTES_CRIANCA = { fredoka: {familia:"'Fredoka', system-ui, sans-serif", google:null}, baloo: {familia:"'Baloo 2', system-ui, sans-serif", google:"Baloo+2:wght@500;600;700"}, nunito: {familia:"'Nunito', system-ui, sans-serif", google:"Nunito:wght@600;700;800"}, escolar: {familia:"'Patrick Hand', system-ui, sans-serif", google:"Patrick+Hand"} }`
- `fonteCrianca(codigo) -> {familia, url|null}` (unknown → fredoka)
- `linksIdentidade(org) -> {titulo, favicon, manifest|null}`: with `tem_icone` + valid `endereco_login` → `/api/publico/clinica/<e>/icone?v=<v>`, else the 🐼 SVG data URL currently in index.html; manifest only when `white_label_ativo` and valid endereço; titulo `org.app_nome || "Panda Tech"` (default page title stays "Panda Tech — Plataforma de Desenvolvimento Infantil" when `app_nome` is the default).
- `emojiMascote(valor, org) -> string`: `"clinica"` → `org.logo_emoji || "🐻"`; anything else → valor.
- `urlMascoteClinica(org) -> string|null`.

- [ ] **Step 1: Failing tests** `frontend/tests/identidade.test.js`:

```js
const test = require("node:test");
const assert = require("node:assert/strict");
const u = require("../js/util.js");

test("fonte da criança: família e URL do Google Fonts só quando precisa", () => {
    assert.equal(u.fonteCrianca("fredoka").url, null);
    assert.match(u.fonteCrianca("baloo").url, /^https:\/\/fonts\.googleapis\.com\/css2\?family=Baloo\+2/);
    assert.match(u.fonteCrianca("escolar").familia, /Patrick Hand/);
    assert.equal(u.fonteCrianca("comic").familia, u.fonteCrianca("fredoka").familia);
});

test("links de identidade: padrão e da clínica", () => {
    const padrao = u.linksIdentidade({ app_nome: "Panda Tech", white_label_ativo: false });
    assert.equal(padrao.titulo, "Panda Tech — Plataforma de Desenvolvimento Infantil");
    assert.match(padrao.favicon, /^data:image\/svg\+xml/);
    assert.equal(padrao.manifest, null);
    const wl = u.linksIdentidade({ app_nome: "Encantar", white_label_ativo: true, tem_icone: true, endereco_login: "enc", versao_imagens: "v1" });
    assert.equal(wl.titulo, "Encantar");
    assert.equal(wl.favicon, "/api/publico/clinica/enc/icone?v=v1");
    assert.equal(wl.manifest, "/api/publico/clinica/enc/manifest.webmanifest");
});

test("emojiMascote nunca mostra a palavra 'clinica'", () => {
    assert.equal(u.emojiMascote("🦊", {}), "🦊");
    assert.equal(u.emojiMascote("clinica", { logo_emoji: "🌈" }), "🌈");
    assert.equal(u.emojiMascote("clinica", {}), "🐻");
});
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - util.js helpers above; `aplicarTemaClinica(org)` additionally: `raiz.setProperty("--fonte-crianca", fonteCrianca(org.mundo_fonte).familia)`; inject/update `<link id="link-fonte-crianca" rel="stylesheet">` when `url` (remove when null); set `document.title`; set/update `<link rel="icon">`, `<link rel="apple-touch-icon">`, `<meta name="apple-mobile-web-app-title">`, and `<link rel="manifest">` (add/remove). Guard all DOM work with `typeof document !== "undefined"`.
  - Add `function restaurarIdentidadePadrao()` = `aplicarTemaClinica({})`-equivalent that resets CSS vars to defaults and the links (used by logout and the default login screen).
  - tokens.css `:root { --fonte-crianca: 'Fredoka', system-ui, sans-serif; }`; layout.css `.shell-crianca { --fonte-display: var(--fonte-crianca); }` and `.modal-caixa.fonte-crianca { --fonte-display: var(--fonte-crianca); }`.
  - mascote.js: `svgMascote({ emoji, ..., imagemUrl = null })` → when `emoji === "clinica"`: if `imagemUrl` given render `<image href="${imagemUrl}" x="30" y="36" width="60" height="60" preserveAspectRatio="xMidYMid meet"/>` instead of the `<text>`, else fall back to "🐻". Callers pass `imagemUrl: urlMascoteClinica(Sessao.usuario?.organizacao)`.
  - Replace raw mascot display with `emojiMascote(x.avatar_mascote, Sessao.usuario?.organizacao)` (still wrapped in `escapeHtml`) at: `agenda.js:537,591`, `comunicacao.js:27`, `dashboard_profissional.js:34`, `diario.js:64`, `financeiro.js:21`, `jornada.js:25`, `pacientes.js:21,189`, `responsavel.js:34` (+ any other hit of `grep -rn "avatar_mascote" frontend/js/views`). `svgMascote` callers (`crianca.js:33,128`, `jornada.js:326`, `responsavel.js:47`) pass `imagemUrl`.
  - app.js: after the initial `aplicarTemaClinica(...)`, refresh:
```js
// White Label completo (25/09/2026): a sessão guardada pode ter cores/nomes
// antigos (ex.: módulo desligado depois do login) — atualiza em segundo plano.
if (Sessao.logado()) {
    Api.get("/auth/me").then(me => {
        const u = Sessao.usuario;
        if (u && me && me.organizacao) { u.organizacao = me.organizacao; Sessao.usuario = u; aplicarTemaClinica(me.organizacao); }
    }).catch(() => {});
}
```
- [ ] **Step 4: Run** node tests → PASS; `grep -rn "avatar_mascote)" frontend/js/views` shows no raw display left.
- [ ] **Step 5: Commit** "White Label: tema com fonte, título, ícone e manifest; mascote da clínica".

---

### Task 8: Mundo da Criança

**Files:** Modify `frontend/js/views/crianca.js`, `frontend/css/layout.css`.

**Interfaces:** Consumes `cenarioDoMundo`, `montarCenarioAnimado`, `urlMascoteClinica`.

- [ ] **Step 1:** Add to crianca.js:
```js
// White Label completo (25/09/2026): fundo animado da clínica por trás do Mundo.
function renderShellCrianca(app, conteudo) {
    const org = (Sessao.usuario && Sessao.usuario.organizacao) || {};
    const cen = cenarioDoMundo(org);
    app.innerHTML = `<div class="shell-crianca" data-tom="${cen.tom}" data-fundo="${cen.tipo}"><div class="cenario-animado" id="cenario-mundo"></div><div class="shell-crianca-conteudo">${conteudo}</div></div>`;
    montarCenarioAnimado(document.getElementById("cenario-mundo"), cen);
}
```
Replace the three `app.innerHTML = \`<div class="shell-crianca">${conteudo}</div>\`` with `renderShellCrianca(app, conteudo)`. Mark text that sits directly on the background with class `sobre-cenario`: the greeting block (`h1` + `p` under the mascot) and section `h3` titles ("🗺️ Missões de hoje", etc.) in all three views.
- [ ] **Step 2:** layout.css:
```css
.shell-crianca-conteudo { position: relative; z-index: 1; display: flex; flex-direction: column; flex: 1; }
.shell-crianca:not([data-fundo="estrelas"]) { background-image: none; }
.shell-crianca[data-tom="escuro"] .sobre-cenario { color: #fff; text-shadow: 0 2px 0 #0004; }
.shell-crianca[data-tom="escuro"] .sobre-cenario .texto-suave, .shell-crianca[data-tom="escuro"] p.sobre-cenario { color: #ffffffd9; }
.shell-crianca[data-tom="escuro"] .sobre-cenario-pilula { background: #0000002a; border-radius: 16px; padding: 4px 12px; display: inline-block; }
```
(wrap greeting h1+p in a `span.sobre-cenario-pilula` block when tom escuro is applied — simplest: always wrap, the pill is transparent in light tone.)
- [ ] **Step 3:** `mostrarCelebracao`: title text `escapeHtml(Sessao.usuario?.organizacao?.mundo_comemoracao || "Muito bem!!")`, `modal-caixa` gets class `fonte-crianca`. Mascot calls pass `imagemUrl: urlMascoteClinica(org)`.
- [ ] **Step 4: Verify** in the browser (Task 11 script) — skip here; run node + pytest suites to make sure nothing else broke.
- [ ] **Step 5: Commit** "White Label: Mundo da Criança com fundo animado, fonte e comemoração da clínica".

---

### Task 9: Clinic login page + logout back to it

**Files:** Modify `frontend/js/views/login.js`, `frontend/js/router.js`, `frontend/js/app.js`, `frontend/js/shell.js`, `frontend/js/api.js`.

**Interfaces:** Produces route `#/entrar/:endereco` (public), `Sessao.enderecoLogin` (localStorage `encanto_endereco_login`, try/catch, NOT cleared by `Sessao.limpar()`), `urlLoginPosSaida() -> "#/entrar/<e>" | "#/login"`.

- [ ] **Step 1:** router.js `despachar`: treat `caminho.startsWith("/entrar/")` as public (like `/login`) and, when logged, redirect to the home page (same as `/login`).
- [ ] **Step 2:** app.js `rota("/entrar/:endereco", null, (app, p) => viewLoginClinica(app, p))`.
- [ ] **Step 3:** login.js: refactor `viewLogin(app, clinica = null)` so the left panel is built by `painelLogin(clinica)`: with `clinica` → background `linear-gradient(160deg, <cor_primaria>, <escurecerCor(cor_primaria,0.3)>)` (colors through `corSegura`), logo (`renderLogoClinica`-style img from `logo_base64` via `base64Seguro`, or `logo_emoji`), mascot (`svgMascote` with `imagemUrl` `/api/publico/clinica/<e>/mascote?v=` when `tem_mascote_imagem`), `app_nome` as title, `login_mensagem` as subtitle, footer `<p class="texto-xs" style="opacity:.8">tecnologia Panda Tech 🐼</p>`; without → today's panel unchanged. The right-side subtitle uses `clinica.login_mensagem` when present. `viewLoginClinica(app, {endereco})`: `try { clinica = await Api.get(\`/publico/clinica/${encodeURIComponent(endereco)}\`) } catch { clinica = null }` (404 → silent default login), apply `aplicarTemaClinica(clinica)` only for colors/title/icon when present, else `restaurarIdentidadePadrao()`. On successful login keep `Sessao.enderecoLogin = endereco` when `clinica` (if the user logs into another clinic, overwrite with `dados.usuario.organizacao.endereco_login` when its `white_label_ativo`, else clear).
  Check `Api.get` works unauthenticated (no token) — it should just omit the header.
- [ ] **Step 4:** shell.js logout and the child-world exit/any other `location.hash = "#/login"` after `Sessao.limpar()`: `restaurarIdentidadePadrao(); location.hash = urlLoginPosSaida();`. On plain `#/login` render call `restaurarIdentidadePadrao()` too.
- [ ] **Step 5:** node + pytest suites green; commit "White Label: tela de login da clínica e volta para ela ao sair".

---

### Task 10: Configurações (gestor), onboarding, patient form

**Files:** Modify `frontend/js/views/financeiro.js` (identity card ~l.397-470 + submit ~l.628-670), `frontend/js/views/onboarding.js`, `frontend/js/views/pacientes.js`, `frontend/css/components.css` (option cards).

- [ ] **Step 1:** In the identity card, after the "Personalização" block, add (all rendered from the GET `/pessoas/organizacao` stored values `org`):
  - trava: `const wlAtivo = org.white_label_ativo;` — when false, wrap colors (`cf-cor1`, `cf-cor2`), the 3 names and the new groups in `<fieldset class="wl-travado" disabled>` with a notice `<div class="aviso-wl">🔒 Disponível com o módulo <strong>Identidade Visual Própria</strong>. O que você salvar fica guardado e passa a valer quando o módulo for liberado — fale com a Panda Tech.</div>` and the badge `<span class="selo-wl">Identidade Visual Própria</span>` on each group title.
  - **📱 Aplicativo**: `cf-app-nome` (maxlength 30, placeholder "Panda Tech"), ícone upload `cf-app-icone` with `renderOrientacaoEnvio("icone")`, preview `<img>` (data URL from the prepared base64 or stored `org.app_icone_base64` via `base64Seguro`), button "Remover ícone".
  - **🔑 Tela de login**: `cf-endereco` (prefix text `${location.origin}/#/entrar/`), button "Copiar link" (`navigator.clipboard?.writeText(...)`), `cf-login-msg` (textarea maxlength 120), hint "A tela mostra o logo, as cores, o mascote e esta mensagem."
  - **🧒 Mundo da Criança**: font cards `.opcao-cartao[data-fonte]` (4, each rendered in its own font — call `fonteCrianca(c).url` and inject the link so the card shows the real font), background cards `.opcao-cartao[data-fundo]` (estrelas, bambu, mar, espaco, clinica, pandoo — labels "Estrelinhas (atual)", "Bambuzal", "Fundo do mar", "Espaço", "Imagem da clínica", "Igual ao Pandoo"; mini swatches as in v3), scene image upload `cf-cenario-img` (perfil `cenario`; shown when fundo = clinica or when `pandoo_cenario_padrao = clinica`; saves to `pandoo_cenario_imagem`; tone computed like the Pandoo preview — average luminance > 0.6 → "claro" — by drawing the prepared image on a 32×32 canvas; send `pandoo_cenario_tom`), mascot grid `MASCOTES_DISPONIVEIS` + "🖼️ Imagem da clínica" with upload `cf-mascote-img` (perfil `icone`), `cf-comemoracao` (maxlength 40), live mini-preview reusing `montarCenarioAnimado` in a 180×320 box.
- [ ] **Step 2:** Submit: send new keys only when `wlAtivo` OR when changed (simplest: always send; server stores regardless). Images: send only when a new file was chosen (or `null` when removed). After `Api.put`, replace `Object.assign(u.organizacao, body)` with `const me = await Api.get("/auth/me"); u.organizacao = me.organizacao;` so the session gets the *effective* identity.
- [ ] **Step 3:** onboarding.js identity step: render the two color inputs only if `(Sessao.usuario.organizacao.modulos_habilitados || []).includes("white_label")`; the submit sends colors only when rendered.
- [ ] **Step 4:** pacientes.js `np-avatar`: options = `MASCOTES_DISPONIVEIS` (+ `<option value="clinica">🖼️ Mascote da clínica</option>` when `org.tem_mascote_imagem`), preselected `org.mundo_mascote`. responsavel.js `abrirModalTrocarMascote`: add the "clinica" button (showing the image via `<img src=urlMascoteClinica(org)>`) when `tem_mascote_imagem`.
- [ ] **Step 5:** node + pytest suites green; commit "White Label: Configurações com Aplicativo, Tela de login e Mundo da Criança".

---

### Task 11: Browser check + docs

**Files:** Modify `CLAUDE.md` (item 5r, section 6 bullet, section 7 pending migration), `docs/superpowers/plans/2026-09-25-pandoo-fase1-tela.md` on branch `pandoo-fase1-tela` is NOT touched here (note in CLAUDE.md pending list instead).

- [ ] **Step 1:** Recreate local DB (`rm -f encanto.db && seed.py`), restart the server, run a Playwright script (scratchpad) that:
  1. logs in as gestor (`andre@clinicaencantar.com.br`), opens Configurações, sets app name "Encantar", fundo "mar", fonte "baloo", comemoração "Arrasou!", saves; checks `document.title === "Encantar"` and `--fonte-crianca` contains "Baloo";
  2. as responsável `ana@familia.com` enters the Mundo: `.cenario-animado.c-mar` exists, `.shell-crianca[data-tom="escuro"]`; screenshot;
  3. logs out → lands on `#/entrar/clinica-encantar` (panel with clinic name); screenshot;
  4. as admin, removes white_label from the demo clinic (switch its plan to starter via API) → gestor's `/auth/me` shows `cor_primaria #5B4FE9`, Configurações shows the lock notice; `#/entrar/clinica-encantar` falls back to the default login; screenshots.
  Collect `pageerror`s — must be empty; CSP violations in console must be empty.
- [ ] **Step 2:** Update CLAUDE.md: item **5r) White Label completo** (what it does, `identidade_service`, public routes, `cenarios_animados.js` shared with Pandoo PR B, migration), section 6 bullet "Identidade da clínica: quem manda é `identidade_service.identidade_efetiva`; `/auth/me` já devolve a efetiva", section 7: migration pending (`migracao_white_label.sql` BEFORE `git pull`), Pandoo PR B must reuse `cenarios_animados.js` and the `cenario` profile, WL item removed from "próximo".
- [ ] **Step 3:** Full suites; commit "White Label: documentação".
