# Jornada e Diário por paciente (parte 3a) — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O Diário Terapêutico passa a ser do paciente (funciona sem jornada); "Iniciar jornada" cria jornada + primeiro plano num pop-up único; o objetivo principal fica editável.

**Architecture:** `diarios_terapeuticos` ganha `paciente_id` (preenchido a partir da jornada nos registros antigos) e `jornada_id` vira opcional. Um helper único resolve "de qual paciente é este diário" (pela coluna nova, com a jornada como reserva), usado por todas as rotas do Diário. Rotas novas por paciente; as antigas por jornada viram atalhos. Duas rotas novas na jornada (`/iniciar` e `PUT` do objetivo). O front troca as chamadas e ganha dois pop-ups.

**Tech Stack:** Flask + SQLite (testes) / Postgres (produção); JS puro; `pytest`, `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-08-jornada-diario-por-paciente-design.md` (prévia aprovada pelo usuário: https://claude.ai/artifact/5VNuXtHEn3EqN9RrJ2bP5o)

## Global Constraints

- Windows: `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q <arquivo>` dentro de `backend/`; front `node --test frontend/tests/*.test.js` na raiz.
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Textos em português do Brasil. Nada de `prompt()`/`confirm()` novos.
- Família (`responsavel`) só vê diários `compartilhado_familia = 1` e **nunca** `evolucao_clinica`.
- Criar diário: papéis `profissional` e `gestor` com `paciente_editavel`. Ler: `paciente_acessivel`.
- Limites: objetivo principal ≤ 300 caracteres, título do plano ≤ 120, pelo menos 1 objetivo não vazio.

## Review Focus

1. **Diário antigo sem `paciente_id`** (criado direto no banco, como os testes de IDOR fazem) — continua acessível pela jornada (helper com reserva). Teste na Task 2.
2. **Família de outra clínica pedindo `/diario/paciente/<id>`** — 403. Teste na Task 2.
3. **"Iniciar" com um objetivo só de espaços** (`["  "]`) — conta como vazio → 400, nada criado. Teste na Task 4.
4. **Ficha sem jornada para a família** — diários compartilhados aparecem, sem evolução clínica. Teste na Task 3.
5. **`consulta_id` de consulta de outro paciente ou inexistente** — 400. Teste na Task 2.

---

### Task 1: Schema, migração e seed

**Files:** `backend/schema.sql`, `backend/schema_postgres.sql` (tabela `diarios_terapeuticos`), `backend/migracoes/migracao_diario_por_paciente.sql` (novo), `backend/migrar_diario_por_paciente.py` (novo), `backend/seed.py` (INSERT de diários ~linha 356), Test: `backend/tests/test_diario_por_paciente_schema.py`.

**Produces:** coluna `diarios_terapeuticos.paciente_id`; `jornada_id` sem `NOT NULL`; índice `idx_diarios_paciente`; `migrar_diario_por_paciente.migrar()`.

- [ ] Teste (falha primeiro):

```python
"""Diário por paciente (spec 08/10/2026): schema e migração."""
import db
import migrar_diario_por_paciente


def test_coluna_paciente_e_jornada_opcional(db_ctx):
    cols = {l["name"]: l for l in db.get_db().execute("PRAGMA table_info(diarios_terapeuticos)").fetchall()}
    assert "paciente_id" in cols
    assert cols["jornada_id"]["notnull"] == 0


def test_migracao_preenche_paciente_e_e_idempotente(db_ctx, capsys):
    org = db.execute("INSERT INTO organizacoes (nome) VALUES ('X')")
    pac = db.execute("INSERT INTO pacientes (organizacao_id, nome, data_nascimento) VALUES (?, 'P', '2020-01-01')", (org,))
    prof = db.execute("INSERT INTO usuarios (organizacao_id, nome, email, senha_hash, senha_salt, papel) VALUES (?, 'Pr', 'p@x.com', 'h', 's', 'profissional')", (org,))
    jor = db.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, 'O')", (pac,))
    d = db.execute("INSERT INTO diarios_terapeuticos (jornada_id, profissional_id, evolucao_clinica) VALUES (?, ?, 'E')", (jor, prof))
    migrar_diario_por_paciente.migrar()
    migrar_diario_por_paciente.migrar()
    assert db.query_one("SELECT paciente_id FROM diarios_terapeuticos WHERE id = ?", (d,))["paciente_id"] == pac
    assert "já existia" in capsys.readouterr().out
```

(Confira as colunas obrigatórias de `usuarios` em `schema.sql` e ajuste o INSERT se faltar alguma.)

- [ ] Implementação:
  - `schema.sql` e `schema_postgres.sql`: em `diarios_terapeuticos`, `jornada_id INTEGER REFERENCES jornadas(id),` (sem `NOT NULL`, comentário "opcional desde 08/10/2026: o diário é do paciente") e logo depois `paciente_id INTEGER REFERENCES pacientes(id),`; depois da tabela, `CREATE INDEX idx_diarios_paciente ON diarios_terapeuticos(paciente_id, data_atendimento);`.
  - `migracoes/migracao_diario_por_paciente.sql`: o SQL da spec (cabeçalho no padrão dos outros, "Rodar ANTES do git pull").
  - `migrar_diario_por_paciente.py`: Postgres roda o `.sql` (mesmo padrão de `migrar_ausencias_agenda.py`); SQLite adiciona a coluna se faltar (`↷ … já existia (SQLite), pulei`), roda `UPDATE diarios_terapeuticos SET paciente_id = (SELECT paciente_id FROM jornadas j WHERE j.id = diarios_terapeuticos.jornada_id) WHERE paciente_id IS NULL`, cria o índice com `IF NOT EXISTS`. Docstring avisando que o `NOT NULL` antigo só some recriando o banco local.
  - `seed.py`: INSERT de diários passa a incluir `paciente_id`.
- [ ] Rodar o teste (2 passed) e commit "Diário: coluna paciente_id e jornada opcional (schema + migração)".

---

### Task 2: Rotas do Diário por paciente

**Files:** `backend/blueprints/diario_bp.py`; Test: `backend/tests/test_diario_por_paciente.py`.

**Consumes:** Task 1. **Produces:**
- `_paciente_do_diario(diario: dict) -> int | None` (usa `paciente_id`; se NULL, `jornadas.paciente_id`).
- `GET/POST /api/diario/paciente/<paciente_id>`; `GET/POST /api/diario/jornada/<jornada_id>` delegam para elas.
- `obter_diario`, `editar_diario`, `adicionar_anexo`, `obter_anexo` usam `_paciente_do_diario`.

- [ ] Testes (falham primeiro). Usar `DuasClinicas`, `autenticado`, `vincular_responsavel` de `factories`:

```python
"""Diário por paciente (spec 08/10/2026)."""
from factories import DuasClinicas, vincular_responsavel

from conftest import autenticado


def _jornada(db_ctx, paciente_id):
    return db_ctx.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, 'O')", (paciente_id,))


def test_cria_e_lista_diario_sem_jornada(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)
    r = c.post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "Sessão 1"})
    assert r.status_code == 201, r.get_data(as_text=True)
    linha = db_ctx.query_one("SELECT paciente_id, jornada_id FROM diarios_terapeuticos WHERE id = ?", (r.get_json()["id"],))
    assert linha == {"paciente_id": cen.paciente_a1, "jornada_id": None}
    lista = c.get(f"/api/diario/paciente/{cen.paciente_a1}").get_json()
    assert [d["evolucao_clinica"] for d in lista] == ["Sessão 1"]


def test_com_jornada_grava_as_duas_colunas(client, db_ctx):
    cen = DuasClinicas()
    jor = _jornada(db_ctx, cen.paciente_a1)
    r = autenticado(client, cen.prof_a1).post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "E"})
    assert db_ctx.query_one("SELECT jornada_id FROM diarios_terapeuticos WHERE id = ?", (r.get_json()["id"],))["jornada_id"] == jor


def test_familia_ve_so_compartilhado_e_sem_evolucao(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    c = autenticado(client, cen.prof_a1)
    c.post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "Técnico", "mensagem_familia": "Oi"})
    c.post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "Privado", "compartilhado_familia": False})
    lista = autenticado(client, cen.resp_a1).get(f"/api/diario/paciente/{cen.paciente_a1}").get_json()
    assert len(lista) == 1 and lista[0]["evolucao_clinica"] is None and lista[0]["mensagem_familia"] == "Oi"


def test_outra_clinica_nao_le_nem_cria(client, db_ctx):
    cen = DuasClinicas()
    assert autenticado(client, cen.prof_b1).post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "x"}).status_code == 403
    assert autenticado(client, cen.resp_b1).get(f"/api/diario/paciente/{cen.paciente_a1}").status_code == 403


def test_consulta_de_outro_paciente_da_400(client, db_ctx):
    cen = DuasClinicas()
    cid = db_ctx.execute("INSERT INTO consultas (paciente_id, profissional_id, data_hora) VALUES (?, ?, '2026-10-08 09:00:00')",
                         (cen.paciente_a2, cen.prof_a1["id"]))
    c = autenticado(client, cen.prof_a1)
    assert c.post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "x", "consulta_id": cid}).status_code == 400
    assert c.post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "x", "consulta_id": 99999}).status_code == 400
    ok = c.post(f"/api/diario/paciente/{cen.paciente_a2}", json={"evolucao_clinica": "x", "consulta_id": cid})
    assert ok.status_code == 201


def test_rotas_antigas_por_jornada_continuam(client, db_ctx):
    cen = DuasClinicas()
    jor = _jornada(db_ctx, cen.paciente_a1)
    c = autenticado(client, cen.prof_a1)
    c.post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "Antes da jornada"})
    assert c.post(f"/api/diario/jornada/{jor}", json={"evolucao_clinica": "Pela jornada"}).status_code == 201
    textos = {d["evolucao_clinica"] for d in c.get(f"/api/diario/jornada/{jor}").get_json()}
    assert textos == {"Antes da jornada", "Pela jornada"}


def test_diario_antigo_sem_paciente_id_continua_acessivel(client, db_ctx):
    cen = DuasClinicas()
    jor = _jornada(db_ctx, cen.paciente_a1)
    did = db_ctx.execute("INSERT INTO diarios_terapeuticos (jornada_id, profissional_id, evolucao_clinica) VALUES (?, ?, 'Velho')",
                         (jor, cen.prof_a1["id"]))
    c = autenticado(client, cen.prof_a1)
    assert c.get(f"/api/diario/{did}").status_code == 200
    assert c.put(f"/api/diario/{did}", json={"evolucao_clinica": "Corrigido"}).status_code == 200
    assert autenticado(client, cen.gestor_b).get(f"/api/diario/{did}").status_code == 403
```

- [ ] Implementação em `diario_bp.py`:

```python
def _paciente_do_diario(diario):
    """De qual paciente é o registro (spec 08/10/2026): a coluna nova; para
    registro antigo ainda sem ela, a jornada."""
    if diario.get("paciente_id"):
        return diario["paciente_id"]
    if diario.get("jornada_id"):
        j = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (diario["jornada_id"],))
        return j["paciente_id"] if j else None
    return None
```

  - `_listar_do_paciente(paciente_id)` (corpo do GET): `WHERE (d.paciente_id = ? OR (d.paciente_id IS NULL AND d.jornada_id IN (SELECT id FROM jornadas WHERE paciente_id = ?)))`, mesmo filtro/serialização da família de hoje.
  - `_criar_para_paciente(paciente_id, body)` (corpo do POST): checa `_pode_registrar_diario`, `evolucao_clinica` obrigatória, valida `consulta_id` (`SELECT 1 FROM consultas WHERE id = ? AND paciente_id = ?` → senão 400 "Consulta inválida para este paciente."), `jornada_id` = jornada ativa ou None, INSERT com `paciente_id`, notifica família como hoje.
  - Rotas novas `GET/POST /paciente/<int:paciente_id>` (404 se paciente não existe; `paciente_acessivel` no GET). Rotas por jornada: buscam a jornada (404 se não existe) e chamam as mesmas funções com `jornada["paciente_id"]`.
  - `obter_diario`, `editar_diario`, `adicionar_anexo`, `obter_anexo`: troque a busca `jornadas` por `_paciente_do_diario(diario)`; None → 403.
- [ ] Rodar `test_diario_por_paciente.py` + `test_idor_diario.py` (todos passam) e commit "Diário: rotas por paciente (as por jornada viram atalhos)".

---

### Task 3: Ficha sem jornada traz o Diário; ICT por paciente

**Files:** `backend/blueprints/jornada_bp.py` (`_montar_bundle_jornada`), `backend/ict_service.py:71-74`; Test: `backend/tests/test_diario_por_paciente.py` (acrescentar).

- [ ] Testes:

```python
def test_ficha_sem_jornada_traz_diarios_recentes(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    autenticado(client, cen.prof_a1).post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "Técnico", "mensagem_familia": "Oi"})
    dados = autenticado(client, cen.prof_a1).get(f"/api/jornada/paciente/{cen.paciente_a1}").get_json()
    assert dados["jornada"] is None and [d["evolucao_clinica"] for d in dados["diarios_recentes"]] == ["Técnico"]
    fam = autenticado(client, cen.resp_a1).get(f"/api/jornada/paciente/{cen.paciente_a1}").get_json()
    assert fam["diarios_recentes"][0]["evolucao_clinica"] is None


def test_ict_conta_diario_sem_jornada_ligada(client, db_ctx):
    import ict_service
    cen = DuasClinicas()
    jor = _jornada(db_ctx, cen.paciente_a1)
    db_ctx.execute("INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, 'P', date('now'))", (jor, cen.prof_a1["id"]))
    db_ctx.execute("INSERT INTO diarios_terapeuticos (paciente_id, profissional_id, evolucao_clinica) VALUES (?, ?, 'E')", (cen.paciente_a1, cen.prof_a1["id"]))
    assert ict_service.calcular_ict_paciente(cen.paciente_a1)["componentes"]["profissional"] == 1.0
```

(Confira em `ict_service.py` o nome real da chave do componente "profissional acompanhou" e ajuste o teste a ele.)

- [ ] Implementação: extrair a consulta de `diarios_recentes` para `_diarios_recentes(paciente_id)` (WHERE pelo paciente, mesmo critério da Task 2, LIMIT 5, filtro da família) e incluir `"diarios_recentes": ...` também no retorno sem jornada. No ICT, contar `WHERE (paciente_id = ? OR jornada_id = ?) AND criado_em >= ?`.
- [ ] Rodar os testes + `test_idor_jornada.py` e commit "Ficha: Diário aparece sem jornada; ICT conta pelo paciente".

---

### Task 4: Iniciar jornada (com plano) e editar objetivo principal

**Files:** `backend/blueprints/jornada_bp.py` (rotas novas perto de `criar_jornada`); Test: `backend/tests/test_iniciar_jornada.py`.

**Produces:** `POST /api/jornada/paciente/<id>/iniciar` → 201 `{jornada_id, plano_id}`; `PUT /api/jornada/jornada/<id>` → 200 `{ok: true}`.

- [ ] Testes:

```python
"""Iniciar jornada num passo só e editar objetivo principal (spec 08/10/2026)."""
from factories import DuasClinicas

from conftest import autenticado

CORPO = {"objetivo_principal": "Falar com autonomia", "titulo": "Plano Out/2026", "objetivos": ["Vocabulário", "Fonema /r/"]}


def test_iniciar_cria_jornada_plano_e_objetivos(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.prof_a1).post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=CORPO)
    assert r.status_code == 201, r.get_data(as_text=True)
    ids = r.get_json()
    assert db_ctx.query_one("SELECT objetivo_principal FROM jornadas WHERE id = ?", (ids["jornada_id"],))["objetivo_principal"] == "Falar com autonomia"
    assert db_ctx.query_one("SELECT titulo, jornada_id FROM planos_terapeuticos WHERE id = ?", (ids["plano_id"],)) == {"titulo": "Plano Out/2026", "jornada_id": ids["jornada_id"]}
    assert [o["descricao"] for o in db_ctx.query("SELECT descricao FROM objetivos_terapeuticos WHERE plano_id = ? ORDER BY id", (ids["plano_id"],))] == ["Vocabulário", "Fonema /r/"]


def test_iniciar_valida_tudo_antes_de_gravar(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)
    for ruim in ({**CORPO, "objetivo_principal": " "}, {**CORPO, "titulo": ""}, {**CORPO, "objetivos": ["  "]},
                 {**CORPO, "objetivos": []}, {**CORPO, "objetivo_principal": "x" * 301}, {**CORPO, "titulo": "x" * 121}):
        assert c.post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=ruim).status_code == 400, ruim
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM jornadas")["n"] == 0


def test_iniciar_com_jornada_ativa_da_409_e_outra_clinica_403(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)
    assert c.post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=CORPO).status_code == 201
    assert c.post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=CORPO).status_code == 409
    assert autenticado(client, cen.prof_b1).post(f"/api/jornada/paciente/{cen.paciente_a2}/iniciar", json=CORPO).status_code == 403


def test_editar_objetivo_principal(client, db_ctx):
    cen = DuasClinicas()
    jor = autenticado(client, cen.prof_a1).post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=CORPO).get_json()["jornada_id"]
    c = autenticado(client, cen.prof_a2)
    assert c.put(f"/api/jornada/jornada/{jor}", json={"objetivo_principal": "Novo objetivo"}).status_code == 200
    assert db_ctx.query_one("SELECT objetivo_principal FROM jornadas WHERE id = ?", (jor,))["objetivo_principal"] == "Novo objetivo"
    assert c.put(f"/api/jornada/jornada/{jor}", json={"objetivo_principal": "  "}).status_code == 400
    assert autenticado(client, cen.gestor_b).put(f"/api/jornada/jornada/{jor}", json={"objetivo_principal": "X"}).status_code == 403
    assert c.put("/api/jornada/jornada/99999", json={"objetivo_principal": "X"}).status_code == 404
```

- [ ] Implementação: função `_validar_inicio(body) -> (dados, erro)` (strip, limites, objetivos filtrados); rota `/iniciar` com `@papel_required("profissional", "gestor", "admin_master")` (igual a `criar_jornada`), `paciente_editavel`, 409 se ativa, INSERT jornada + plano (`hoje_sql()`) + objetivos, `log_evento` `jornada_criada` e `plano_iniciado`. Rota `PUT /jornada/<int:jornada_id>`: 404 se não existe, `paciente_editavel` → 403, valida e faz UPDATE.
- [ ] Rodar e commit "Jornada: iniciar com plano num passo e editar objetivo principal".

---

### Task 5: Front — Diário pelo paciente (ficha, família, histórico)

**Files:** `frontend/js/views/diario.js` (`abrirModalNovoDiario`, `abrirModalHistoricoDiario`), `frontend/js/views/jornada.js` (cartão do Diário extraído em `renderCartaoDiario(dados, podeEditar)`, usado com e sem jornada; eventos do Diário ligados nos dois casos), `frontend/js/views/responsavel.js:28`.

- [ ] `abrirModalNovoDiario(paciente)` → `Api.post(\`/diario/paciente/${paciente.id}\`, …)`; `abrirModalHistoricoDiario(pacienteId)` → `Api.get(\`/diario/paciente/${pacienteId}\`)`. Atualize os chamadores.
- [ ] `jornada.js`: `renderCartaoDiario(dados, podeEditar)` com o HTML atual do cartão (marcos só se `dados.marcos`); `renderJornadaConteudoPrincipal` passa a usá-lo; o ramo sem jornada mostra `renderCartaoDiario(...)` e, abaixo, o cartão "Ainda não tem uma jornada". Função `anexarEventosDiario(dados)` (novo diário, histórico, `.btn-ver-diario`) chamada sempre; tirar esses três de `anexarEventosJornada`.
- [ ] `responsavel.js`: `const diarios = await Api.get(\`/diario/paciente/${pacienteId}\`);` (sem depender da jornada).
- [ ] Verificar no navegador (seed recriado): paciente sem jornada → Novo Diário → aparece; família (`ana@familia.com`) vê o diário compartilhado. `node --test` passa. Commit "Ficha: Diário pelo paciente, com ou sem jornada".

---

### Task 6: Front — pop-up "Iniciar jornada" e editar objetivo principal

**Files:** `frontend/js/views/jornada.js`.

- [ ] `abrirModalIniciarJornada(pacienteId)`: campos `ij-objetivo-principal` (textarea, maxlength 300, dica "O grande objetivo da jornada. Pode ser editado depois."), `ij-titulo` (maxlength 120, placeholder "Ex: Plano Outubro/2026"), `ij-objetivos` (textarea, um por linha); botões "Iniciar jornada" / "Cancelar"; POST `/jornada/paciente/${pacienteId}/iniciar`; sucesso → `Toast.sucesso("Jornada iniciada!")` + `despachar()`. Substitui o `prompt()` do `btn-iniciar-jornada`.
- [ ] Cartão "🎯 Objetivo Principal": botão `btn-editar-objetivo` (✏️, `botao-icone`, só com `podeEditar`) → `abrirModalEditarObjetivo(jornada)` com textarea (maxlength 300) → PUT `/jornada/jornada/${id}` → `despachar()`.
- [ ] Verificar no navegador: iniciar pelo pop-up cria jornada + plano; ✏️ edita; campos vazios mostram o erro do servidor. Commit "Ficha: Iniciar jornada num pop-up e editar objetivo principal".

---

### Task 7: Fechamento

- [ ] `backend/tests_postgres/test_smoke_fluxo_principal.py`: o POST do diário passa a ser `/api/diario/paciente/{paciente_id}`.
- [ ] Suítes completas (backend + Node). Playwright de fumaça (Tasks 5–6 juntas). Apagar `.playwright-mcp/`.
- [ ] CLAUDE.md: item `z)` na seção 5 (Diário por paciente, rotas, pop-ups, migração, totais de testes); seção 7: 3a feita, migração pendente, próxima é 3c (planos por especialidade); tabela da seção 8 se couber.
- [ ] Revisão final do branch (revisor novo), correções, push, PR. **Mudança de schema: perguntar antes de mesclar** e passar o SQL do Supabase.
