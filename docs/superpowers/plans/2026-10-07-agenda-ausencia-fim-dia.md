# Agenda: hora de fim, Ausência e visão Dia — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consultas com início e fim livres (duração padrão da clínica), ausências de profissional que bloqueiam o agendamento, e visão Dia (um profissional ou todos lado a lado).

**Architecture:** Backend Flask: tabela nova `ausencias_profissional` (uma linha = uma regra com período, horário e dias da semana), serviço puro `ausencias_service.py` que diz se uma regra cobre um intervalo, rotas CRUD em `agenda_bp.py` e checagem de conflito nas rotas de consulta. Front em JS puro: funções puras em `agenda_ausencias.js` (testadas com `node --test`), pop-up de ausência em `views/agenda_ausencia_modal.js`, e a grade de `views/agenda.js` passa a ter um desenhista genérico de colunas (dias ou profissionais).

**Tech Stack:** Python 3.11 + Flask + SQLite (testes/local) / Postgres (produção); JS puro no navegador; `pytest` e `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-07-agenda-ausencia-fim-dia-design.md`

## Global Constraints

- Rodar tudo do Windows com `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1` e o venv `backend/venv/Scripts/python.exe` (ver CLAUDE.md seção 4).
- Pytest: `cd backend && PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q <arquivo>`; front: `node --test frontend/tests/*.test.js` (na raiz).
- Toda mensagem de commit termina com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Textos de tela e mensagens de erro em português do Brasil.
- `consultas.data_hora` é horário LOCAL `"YYYY-MM-DD HH:MM:SS"` (pode vir `"9:00:00"` sem zero em dados antigos).
- Duração da consulta: inteiro de **5 a 480** min. Duração padrão da clínica: **5 a 240**, começa em **50**.
- Ausência: `dias_semana` = dígitos 0 (dom) … 6 (sáb); motivo até **120** caracteres; busca de ocorrências até **62** dias.
- Ausência encostada não conflita: consulta 11:00–12:00 e ausência 12:00–13:00 convivem.
- Profissional comum lança/edita só ausência dele; gestor e secretária para qualquer profissional ativo e não excluído da clínica; responsável não vê ausências.
- CSP: nada de `blob:` nem scripts inline; JS novo entra como `<script src>` em `frontend/index.html`.
- Não usar `formatarDataHora` (UTC) para consultas — usar `formatarDataHoraLocal`/`formatarHoraLocal`/`formatarData`.

## Review Focus

1. **Série recorrente toda dentro de férias** — deve devolver 409 sem criar nenhuma consulta (nem a primeira). Teste na Task 4.
2. **Arrastar consulta para outra coluna (outro profissional) que está ausente** — o backend recusa (409) e a consulta volta ao lugar. Teste de backend na Task 4 (reatribuir com conflito).
3. **Ausência "sem fim" (data_fim vazia)** — continua valendo em datas muito à frente e entra no GET de qualquer semana futura. Teste na Task 2 e na Task 3.
4. **Profissional com `agenda_permissao_total`** — vê ausências de todos, mas não edita as dos outros (`pode_editar = false`, PUT → 403). Teste na Task 3.
5. **Editar só observação de uma consulta que hoje cai numa ausência criada depois** — não deve bloquear (só checa se mudou data/hora/duração/profissional). Teste na Task 4.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `backend/schema.sql`, `backend/schema_postgres.sql` | tabela `ausencias_profissional`, coluna `organizacoes.agenda_duracao_padrao` |
| `backend/migracoes/migracao_ausencias_agenda.sql` (novo) | migração idempotente para o Supabase |
| `backend/migrar_ausencias_agenda.py` (novo) | mesma migração via `db.py` |
| `backend/ausencias_service.py` (novo) | validar regra, "a regra cobre este intervalo?", ocorrências, conflito |
| `backend/validacao_campos.py` | `validar_duracao(valor, minimo, maximo)` |
| `backend/blueprints/agenda_bp.py` | rotas `/ausencias`, bloqueio e duração nas rotas de consulta |
| `backend/blueprints/pessoas_bp.py`, `auth_bp.py`, `identidade_service.py` | duração padrão da clínica |
| `frontend/js/agenda_ausencias.js` (novo) | funções puras do front (bloqueio, fim/duração, dias padrão) |
| `frontend/js/agenda_faixa.js` | faixa considera ausências com horário |
| `frontend/js/views/agenda_ausencia_modal.js` (novo) | pop-up de criar/editar/ver ausência e lista de consultas no período |
| `frontend/js/views/agenda.js` | Início/Fim, seletor Consulta/Ausência, grade genérica, visão Dia |
| `frontend/js/views/financeiro.js` | campo "Duração padrão da consulta" em Configurações |
| `frontend/css/components.css` | bloco de ausência, rolagem horizontal da grade |
| `frontend/index.html` | `<script>` dos dois arquivos novos |

---

### Task 1: Schema e migração

**Files:**
- Modify: `backend/schema.sql` (tabela `organizacoes`, perto da linha 64; nova tabela depois de `disponibilidade_profissional`)
- Modify: `backend/schema_postgres.sql` (mesmos pontos, linha ~66 e ~386)
- Create: `backend/migracoes/migracao_ausencias_agenda.sql`
- Create: `backend/migrar_ausencias_agenda.py`
- Test: `backend/tests/test_agenda_ausencias_schema.py`

**Interfaces:**
- Produces: tabela `ausencias_profissional(id, organizacao_id, profissional_id, data_inicio, data_fim, dia_inteiro, hora_inicio, hora_fim, dias_semana, motivo, criado_por, criado_em)`; coluna `organizacoes.agenda_duracao_padrao INTEGER DEFAULT 50`; `migrar_ausencias_agenda.migrar()`.

- [ ] **Step 1: Write the failing test**

```python
"""Agenda com Ausência (spec 07/10/2026): tabela nova e duração padrão da clínica."""
import db
import migrar_ausencias_agenda


def test_tabela_ausencias_existe(db_ctx):
    nomes = {l["name"] for l in db.get_db().execute("PRAGMA table_info(ausencias_profissional)").fetchall()}
    assert {"id", "organizacao_id", "profissional_id", "data_inicio", "data_fim", "dia_inteiro",
            "hora_inicio", "hora_fim", "dias_semana", "motivo", "criado_por", "criado_em"} <= nomes


def test_duracao_padrao_comeca_em_50(db_ctx):
    org_id = db.execute("INSERT INTO organizacoes (nome) VALUES ('X')")
    assert db.query_one("SELECT agenda_duracao_padrao FROM organizacoes WHERE id = ?", (org_id,))["agenda_duracao_padrao"] == 50


def test_migracao_idempotente(db_ctx, capsys):
    migrar_ausencias_agenda.migrar()
    migrar_ausencias_agenda.migrar()
    assert "já existia" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q tests/test_agenda_ausencias_schema.py`
Expected: FAIL (`ModuleNotFoundError: migrar_ausencias_agenda`).

- [ ] **Step 3: Implement**

`schema.sql`, dentro de `CREATE TABLE organizacoes`, logo depois de `agenda_hora_fim TEXT,`:

```sql
    agenda_duracao_padrao INTEGER DEFAULT 50,  -- minutos; fim padrão da consulta (spec 07/10/2026)
```

`schema.sql`, depois de `CREATE TABLE disponibilidade_profissional (...);`:

```sql
-- Ausência do profissional (spec 07/10/2026): uma linha = uma regra
-- (período + horário + dias da semana). Bloqueia agendar por cima.
CREATE TABLE ausencias_profissional (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
    data_inicio     TEXT NOT NULL,              -- YYYY-MM-DD
    data_fim        TEXT,                       -- NULL = sem fim
    dia_inteiro     INTEGER NOT NULL DEFAULT 0,
    hora_inicio     TEXT,                       -- HH:MM (NULL se dia inteiro)
    hora_fim        TEXT,
    dias_semana     TEXT NOT NULL DEFAULT '123456', -- 0=dom ... 6=sáb
    motivo          TEXT,
    criado_por      INTEGER REFERENCES usuarios(id),
    criado_em       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_ausencias_prof ON ausencias_profissional(profissional_id, data_inicio);
```

`schema_postgres.sql`: a mesma coluna em `organizacoes` (`agenda_duracao_padrao INTEGER DEFAULT 50,`) e a tabela com `id SERIAL PRIMARY KEY` e `criado_em TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))` (mesmo padrão das outras tabelas desse arquivo).

`backend/migracoes/migracao_ausencias_agenda.sql`:

```sql
-- ----------------------------------------------------------------------------
-- Migração incremental — Agenda: Ausência e duração padrão (07/10/2026)
--
-- Tabela nova `ausencias_profissional` e coluna `organizacoes.agenda_duracao_padrao`
-- (padrão 50). Idempotente. Rodar ANTES do `git pull`.
-- ----------------------------------------------------------------------------

ALTER TABLE organizacoes ADD COLUMN IF NOT EXISTS agenda_duracao_padrao INTEGER DEFAULT 50;

CREATE TABLE IF NOT EXISTS ausencias_profissional (
    id              SERIAL PRIMARY KEY,
    organizacao_id  INTEGER NOT NULL REFERENCES organizacoes(id),
    profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
    data_inicio     TEXT NOT NULL,
    data_fim        TEXT,
    dia_inteiro     INTEGER NOT NULL DEFAULT 0,
    hora_inicio     TEXT,
    hora_fim        TEXT,
    dias_semana     TEXT NOT NULL DEFAULT '123456',
    motivo          TEXT,
    criado_por      INTEGER REFERENCES usuarios(id),
    criado_em       TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE INDEX IF NOT EXISTS idx_ausencias_prof ON ausencias_profissional(profissional_id, data_inicio);
```

`backend/migrar_ausencias_agenda.py`:

```python
"""
Migração não-destrutiva (spec 07/10/2026): tabela `ausencias_profissional` e
coluna `organizacoes.agenda_duracao_padrao` (padrão 50 min).

    cd backend
    python3 migrar_ausencias_agenda.py

Confira que a saída termina com (Postgres) em produção — sem DATABASE_URL o
script grava no SQLite local (CLAUDE.md, seção 7.2). Seguro rodar de novo.
"""
import os

import db

DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS ausencias_profissional (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organizacao_id INTEGER NOT NULL REFERENCES organizacoes(id),
    profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
    data_inicio TEXT NOT NULL, data_fim TEXT, dia_inteiro INTEGER NOT NULL DEFAULT 0,
    hora_inicio TEXT, hora_fim TEXT, dias_semana TEXT NOT NULL DEFAULT '123456', motivo TEXT,
    criado_por INTEGER REFERENCES usuarios(id), criado_em TEXT DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS idx_ausencias_prof ON ausencias_profissional(profissional_id, data_inicio);
"""


def migrar():
    if db.USANDO_POSTGRES:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_ausencias_agenda.sql")
        linhas = [l for l in open(caminho, encoding="utf-8").read().splitlines() if not l.strip().startswith("--")]
        for comando in "\n".join(linhas).split(";"):
            if comando.strip():
                db.execute(comando)
        print("✅ Ausências da agenda: tabela, índice e coluna conferidos (Postgres)")
        return
    conn = db.get_db()
    existentes = {l["name"] for l in conn.execute("PRAGMA table_info(organizacoes)").fetchall()}
    if "agenda_duracao_padrao" in existentes:
        print("↷  organizacoes.agenda_duracao_padrao já existia (SQLite), pulei")
    else:
        conn.execute("ALTER TABLE organizacoes ADD COLUMN agenda_duracao_padrao INTEGER DEFAULT 50")
        print("✅ organizacoes.agenda_duracao_padrao adicionada (SQLite)")
    conn.executescript(DDL_SQLITE)
    conn.commit()
    print("✅ Ausências da agenda: tabela e índice conferidos (SQLite)")


if __name__ == "__main__":
    migrar()
```

- [ ] **Step 4: Run tests**

Run: `... -m pytest -q tests/test_agenda_ausencias_schema.py`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/schema.sql backend/schema_postgres.sql backend/migracoes/migracao_ausencias_agenda.sql backend/migrar_ausencias_agenda.py backend/tests/test_agenda_ausencias_schema.py
git commit -m "Agenda: tabela de ausências e duração padrão da clínica (schema + migração)"
```

---

### Task 2: `ausencias_service.py` — regras puras

**Files:**
- Create: `backend/ausencias_service.py`
- Modify: `backend/validacao_campos.py` (função nova `validar_duracao`)
- Test: `backend/tests/test_ausencias_service.py`

**Interfaces:**
- Produces:
  - `validacao_campos.validar_duracao(valor, minimo, maximo) -> (int | None, str | None)`
  - `ausencias_service.validar_ausencia(body: dict) -> (dict | None, str | None)` — dict normalizado com `data_inicio, data_fim, dia_inteiro (0/1), hora_inicio, hora_fim, dias_semana, motivo`.
  - `ausencias_service.dia_semana(data: date) -> int` (0=dom … 6=sáb)
  - `ausencias_service.ausencia_cobre(aus: dict, data: date, ini_min: int, fim_min: int) -> bool`
  - `ausencias_service.ocorrencias(ausencias: list[dict], data_ini: date, data_fim: date) -> list[dict]`
  - `ausencias_service.separar_data_hora(data_hora: str) -> (date, int) | (None, None)`

- [ ] **Step 1: Write the failing test**

```python
"""Regras puras das ausências da agenda (spec 07/10/2026)."""
from datetime import date

import ausencias_service as s
from validacao_campos import validar_duracao


def aus(**kw):
    base = {"data_inicio": "2026-10-05", "data_fim": None, "dia_inteiro": 0,
            "hora_inicio": "12:00", "hora_fim": "13:00", "dias_semana": "12345", "motivo": "Almoço"}
    base.update(kw)
    return base


def test_validar_duracao():
    assert validar_duracao("45", 5, 480) == (45, None)
    for ruim in (None, "", "abc", 4, 481, 12.5):
        assert validar_duracao(ruim, 5, 480)[1], ruim


def test_validar_ausencia_ok_e_normaliza():
    dados, erro = s.validar_ausencia({"data_inicio": "2026-10-10", "data_fim": "", "dia_inteiro": True,
                                      "hora_inicio": "09:00", "dias_semana": "5321", "motivo": "  Férias "})
    assert erro is None
    assert dados == {"data_inicio": "2026-10-10", "data_fim": None, "dia_inteiro": 1, "hora_inicio": None,
                     "hora_fim": None, "dias_semana": "1235", "motivo": "Férias"}


def test_validar_ausencia_erros():
    casos = [
        {"data_inicio": "10/10/2026"},
        {"data_inicio": "2026-10-10", "data_fim": "2026-10-09", "dia_inteiro": 1, "dias_semana": "1"},
        {"data_inicio": "2026-10-10", "dia_inteiro": 0, "hora_inicio": "13:00", "hora_fim": "12:00", "dias_semana": "1"},
        {"data_inicio": "2026-10-10", "dia_inteiro": 0, "hora_inicio": "", "hora_fim": "12:00", "dias_semana": "1"},
        {"data_inicio": "2026-10-10", "dia_inteiro": 1, "dias_semana": ""},
        {"data_inicio": "2026-10-10", "dia_inteiro": 1, "dias_semana": "78"},
        {"data_inicio": "2026-10-10", "dia_inteiro": 1, "dias_semana": "1", "motivo": "x" * 121},
    ]
    for body in casos:
        assert s.validar_ausencia(body)[1], body


def test_dia_semana_domingo_zero():
    assert s.dia_semana(date(2026, 10, 4)) == 0   # domingo
    assert s.dia_semana(date(2026, 10, 10)) == 6  # sábado


def test_cobre_horario_e_borda_que_encosta():
    a = aus()
    seg = date(2026, 10, 5)
    assert s.ausencia_cobre(a, seg, 11 * 60 + 30, 12 * 60 + 30)       # sobrepõe
    assert not s.ausencia_cobre(a, seg, 11 * 60, 12 * 60)             # termina 12:00 — encosta
    assert not s.ausencia_cobre(a, seg, 13 * 60, 14 * 60)             # começa 13:00 — encosta
    assert not s.ausencia_cobre(a, date(2026, 10, 4), 12 * 60, 12 * 60 + 30)  # domingo fora dos dias


def test_cobre_periodo_e_sem_fim():
    a = aus(data_fim="2026-10-09")
    assert not s.ausencia_cobre(a, date(2026, 10, 2), 12 * 60, 12 * 60 + 30)   # antes do início
    assert not s.ausencia_cobre(a, date(2026, 10, 12), 12 * 60, 12 * 60 + 30)  # depois do fim
    sem_fim = aus()
    assert s.ausencia_cobre(sem_fim, date(2030, 3, 4), 12 * 60, 12 * 60 + 30)  # segunda em 2030


def test_cobre_dia_inteiro():
    a = aus(dia_inteiro=1, hora_inicio=None, hora_fim=None, dias_semana="0123456")
    assert s.ausencia_cobre(a, date(2026, 10, 7), 7 * 60, 7 * 60 + 5)


def test_ocorrencias_no_intervalo():
    a = dict(aus(data_fim="2026-10-07"), id=9, profissional_id=3)
    occ = s.ocorrencias([a], date(2026, 10, 4), date(2026, 10, 10))
    assert [o["data"] for o in occ] == ["2026-10-05", "2026-10-06", "2026-10-07"]
    assert occ[0]["ausencia_id"] == 9 and occ[0]["profissional_id"] == 3
    assert occ[0]["hora_inicio"] == "12:00" and occ[0]["dias_semana"] == "12345"


def test_separar_data_hora_aceita_hora_sem_zero():
    assert s.separar_data_hora("2026-10-05 9:30:00") == (date(2026, 10, 5), 570)
    assert s.separar_data_hora("lixo") == (None, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... -m pytest -q tests/test_ausencias_service.py`
Expected: FAIL (`ModuleNotFoundError: ausencias_service`).

- [ ] **Step 3: Implement**

Em `backend/validacao_campos.py`, depois de `validar_horario_agenda`:

```python
def validar_duracao(valor, minimo, maximo):
    """Duração em minutos (consulta ou padrão da clínica, spec 07/10/2026).
    Devolve (int, None) ou (None, erro). Recusa vazio, texto, fração e fora da faixa."""
    if isinstance(valor, bool) or valor in (None, ""):
        return None, f"Informe a duração em minutos (de {minimo} a {maximo})."
    if isinstance(valor, float) and not valor.is_integer():
        return None, f"A duração precisa ser um número inteiro de minutos (de {minimo} a {maximo})."
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return None, f"A duração precisa ser um número de minutos (de {minimo} a {maximo})."
    if n < minimo or n > maximo:
        return None, f"A duração precisa ficar entre {minimo} e {maximo} minutos."
    return n, None
```

`backend/ausencias_service.py`:

```python
"""
Ausências do profissional na agenda (spec 07/10/2026).

Uma linha de `ausencias_profissional` é uma REGRA: período (data_fim NULL =
sem fim), dia inteiro ou horário, e dias da semana ("0".."6", 0 = domingo).
As ocorrências são calculadas na hora. Aqui ficam as funções puras (testadas
em tests/test_ausencias_service.py) e as consultas ao banco usadas pelas
rotas da agenda.
"""
import re
from datetime import date, datetime, timedelta

from db import query

_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DATA_HORA = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2})")
MAX_MOTIVO = 120


def _data(texto):
    texto = str(texto or "").strip()
    if not _DATA.match(texto):
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return None


def _minutos(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def dia_semana(d):
    """0 = domingo ... 6 = sábado (mesma convenção do JS getDay())."""
    return (d.weekday() + 1) % 7


def separar_data_hora(data_hora):
    m = _DATA_HORA.match(str(data_hora or ""))
    if not m:
        return None, None
    d = _data(m.group(1))
    h, mi = int(m.group(2)), int(m.group(3))
    if d is None or h > 23 or mi > 59:
        return None, None
    return d, h * 60 + mi


def validar_ausencia(body):
    inicio = _data(body.get("data_inicio"))
    if not inicio:
        return None, "Data de início inválida — use o calendário para escolher."
    fim_txt = str(body.get("data_fim") or "").strip()
    fim = None
    if fim_txt:
        fim = _data(fim_txt)
        if not fim:
            return None, "Data de fim inválida."
        if fim < inicio:
            return None, "A data de fim precisa ser igual ou depois da data de início."
    dia_inteiro = 1 if body.get("dia_inteiro") in (True, 1, "1", "true") else 0
    hora_inicio = hora_fim = None
    if not dia_inteiro:
        hora_inicio = str(body.get("hora_inicio") or "").strip()
        hora_fim = str(body.get("hora_fim") or "").strip()
        if not (_HHMM.match(hora_inicio) and _HHMM.match(hora_fim)):
            return None, "Informe o horário da ausência (início e fim) ou marque 'Dia inteiro'."
        if hora_inicio >= hora_fim:
            return None, "O horário de fim da ausência precisa ser depois do início."
    dias = str(body.get("dias_semana") or "").strip()
    if not dias or any(c not in "0123456" for c in dias):
        return None, "Escolha pelo menos um dia da semana."
    dias = "".join(sorted(set(dias)))
    motivo = str(body.get("motivo") or "").strip()
    if len(motivo) > MAX_MOTIVO:
        return None, f"O motivo pode ter no máximo {MAX_MOTIVO} caracteres."
    return {
        "data_inicio": inicio.isoformat(), "data_fim": fim.isoformat() if fim else None,
        "dia_inteiro": dia_inteiro, "hora_inicio": hora_inicio, "hora_fim": hora_fim,
        "dias_semana": dias, "motivo": motivo or None,
    }, None


def _vale_no_dia(aus, d):
    inicio = _data(aus["data_inicio"])
    fim = _data(aus.get("data_fim")) if aus.get("data_fim") else None
    if inicio is None or d < inicio or (fim and d > fim):
        return False
    return str(dia_semana(d)) in str(aus.get("dias_semana") or "")


def ausencia_cobre(aus, d, ini_min, fim_min):
    """A regra vale no dia `d` e o intervalo [ini_min, fim_min) se sobrepõe a
    ela? Encostar (terminar quando ela começa) não conta."""
    if not _vale_no_dia(aus, d):
        return False
    if aus.get("dia_inteiro"):
        return True
    a_ini, a_fim = _minutos(aus["hora_inicio"]), _minutos(aus["hora_fim"])
    return ini_min < a_fim and fim_min > a_ini


def ocorrencias(ausencias, data_ini, data_fim):
    saida = []
    d = data_ini
    while d <= data_fim:
        for a in ausencias:
            if _vale_no_dia(a, d):
                saida.append({
                    "ausencia_id": a.get("id"), "profissional_id": a.get("profissional_id"),
                    "data": d.isoformat(), "dia_inteiro": int(a.get("dia_inteiro") or 0),
                    "hora_inicio": a.get("hora_inicio"), "hora_fim": a.get("hora_fim"),
                    "motivo": a.get("motivo"), "data_inicio": a.get("data_inicio"),
                    "data_fim": a.get("data_fim"), "dias_semana": a.get("dias_semana"),
                })
        d += timedelta(days=1)
    return saida


# ------------------------------------------------------------ consultas ao banco

def ausencias_do_profissional(profissional_id, d):
    return query(
        """SELECT * FROM ausencias_profissional WHERE profissional_id = ?
           AND data_inicio <= ? AND (data_fim IS NULL OR data_fim >= ?)""",
        (profissional_id, d.isoformat(), d.isoformat()),
    )


def conflito_ausencia(profissional_id, data_hora, duracao_min):
    """Primeira ausência do profissional que bate com a consulta, ou None.
    Consulta que passa da meia-noite só é checada no dia em que começa."""
    d, ini = separar_data_hora(data_hora)
    if d is None:
        return None
    fim = min(ini + int(duracao_min or 0), 24 * 60)
    for a in ausencias_do_profissional(profissional_id, d):
        if ausencia_cobre(a, d, ini, fim):
            return a
    return None


def consultas_no_periodo(aus, hoje=None):
    """Consultas não canceladas, de hoje em diante, que caem na regra."""
    hoje = hoje or date.today()
    desde = max(hoje, _data(aus["data_inicio"]))
    params = [aus["profissional_id"], desde.isoformat()]
    sql = """SELECT c.id, c.data_hora, c.duracao_min, p.nome AS paciente_nome
             FROM consultas c JOIN pacientes p ON p.id = c.paciente_id
             WHERE c.profissional_id = ? AND c.status != 'cancelada' AND c.data_hora >= ?"""
    if aus.get("data_fim"):
        sql += " AND c.data_hora < ?"
        params.append((_data(aus["data_fim"]) + timedelta(days=1)).isoformat())
    saida = []
    for c in query(sql + " ORDER BY c.data_hora", tuple(params)):
        d, ini = separar_data_hora(c["data_hora"])
        if d and ausencia_cobre(aus, d, ini, ini + int(c["duracao_min"] or 50)):
            saida.append({"id": c["id"], "data_hora": c["data_hora"], "paciente_nome": c["paciente_nome"]})
    return saida
```

- [ ] **Step 4: Run tests**

Run: `... -m pytest -q tests/test_ausencias_service.py`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/ausencias_service.py backend/validacao_campos.py backend/tests/test_ausencias_service.py
git commit -m "Agenda: regras puras das ausências e validação de duração"
```

---

### Task 3: Rotas das ausências

**Files:**
- Modify: `backend/blueprints/agenda_bp.py` (import do serviço no topo; rotas novas no fim do arquivo)
- Test: `backend/tests/test_agenda_ausencias.py`

**Interfaces:**
- Consumes: `ausencias_service.validar_ausencia`, `ocorrencias`, `consultas_no_periodo`; `_profissional_da_mesma_clinica` (já existe em `agenda_bp.py`).
- Produces (HTTP):
  - `GET /api/agenda/ausencias?inicio=YYYY-MM-DD&fim=YYYY-MM-DD` → `[{ausencia_id, profissional_id, data, dia_inteiro, hora_inicio, hora_fim, motivo, data_inicio, data_fim, dias_semana, profissional_nome, pode_editar}]`
  - `POST /api/agenda/ausencias` body `{profissional_id?, data_inicio, data_fim?, dia_inteiro, hora_inicio?, hora_fim?, dias_semana, motivo?}` → 201 `{id, consultas_no_periodo: [{id, data_hora, paciente_nome}]}`
  - `PUT /api/agenda/ausencias/<id>` (mesmo corpo) → 200 `{ok: true, consultas_no_periodo}`
  - `DELETE /api/agenda/ausencias/<id>` → 200 `{ok: true}`

- [ ] **Step 1: Write the failing test**

```python
"""Rotas das ausências da agenda (spec 07/10/2026)."""
from factories import DuasClinicas, novo_usuario

from conftest import autenticado

ALMOCO = {"data_inicio": "2026-10-05", "data_fim": "", "dia_inteiro": False,
          "hora_inicio": "12:00", "hora_fim": "13:00", "dias_semana": "12345", "motivo": "Almoço"}


def _criar(client, usuario, **extra):
    return autenticado(client, usuario).post("/api/agenda/ausencias", json={**ALMOCO, **extra})


def test_profissional_lanca_a_propria_e_ignora_outro_id(client, db_ctx):
    cen = DuasClinicas()
    r = _criar(client, cen.prof_a1)
    assert r.status_code == 201, r.get_data(as_text=True)
    linha = db_ctx.query_one("SELECT * FROM ausencias_profissional WHERE id = ?", (r.get_json()["id"],))
    assert linha["profissional_id"] == cen.prof_a1["id"] and linha["organizacao_id"] == cen.org_a
    r2 = _criar(client, cen.prof_a1, profissional_id=cen.prof_a2["id"])
    assert r2.status_code == 403


def test_gestor_e_secretaria_lancam_para_qualquer_profissional(client, db_ctx):
    cen = DuasClinicas()
    sec = novo_usuario(cen.org_a, "Secretária A", "sec@a.com", "secretaria")
    assert _criar(client, cen.gestor_a, profissional_id=cen.prof_a2["id"]).status_code == 201
    assert _criar(client, sec, profissional_id=cen.prof_a1["id"]).status_code == 201


def test_nao_lanca_para_profissional_de_outra_clinica_ou_excluido(client, db_ctx):
    cen = DuasClinicas()
    assert _criar(client, cen.gestor_a, profissional_id=cen.prof_b1["id"]).status_code == 400
    db_ctx.execute("UPDATE usuarios SET excluido_em = '2026-10-01' WHERE id = ?", (cen.prof_a2["id"],))
    assert _criar(client, cen.gestor_a, profissional_id=cen.prof_a2["id"]).status_code == 400


def test_validacao_devolve_400(client, db_ctx):
    cen = DuasClinicas()
    r = _criar(client, cen.prof_a1, hora_fim="11:00")
    assert r.status_code == 400 and "fim" in r.get_json()["erro"]


def test_get_devolve_ocorrencias_e_pode_editar(client, db_ctx):
    cen = DuasClinicas()
    _criar(client, cen.prof_a1)
    _criar(client, cen.gestor_a, profissional_id=cen.prof_a2["id"], motivo="Curso")
    r = autenticado(client, cen.gestor_a).get("/api/agenda/ausencias?inicio=2026-10-04&fim=2026-10-10")
    assert r.status_code == 200
    itens = r.get_json()
    assert len(itens) == 10  # 5 dias x 2 profissionais
    assert all(i["pode_editar"] for i in itens)
    assert {i["profissional_nome"] for i in itens} == {"Prof A1", "Prof A2"}


def test_ausencia_sem_fim_aparece_no_futuro(client, db_ctx):
    cen = DuasClinicas()
    _criar(client, cen.prof_a1)
    r = autenticado(client, cen.prof_a1).get("/api/agenda/ausencias?inicio=2030-03-03&fim=2030-03-09")
    assert len(r.get_json()) == 5


def test_profissional_comum_ve_so_as_dele(client, db_ctx):
    cen = DuasClinicas()
    _criar(client, cen.prof_a1)
    _criar(client, cen.gestor_a, profissional_id=cen.prof_a2["id"])
    itens = autenticado(client, cen.prof_a1).get("/api/agenda/ausencias?inicio=2026-10-04&fim=2026-10-10").get_json()
    assert {i["profissional_id"] for i in itens} == {cen.prof_a1["id"]}


def test_permissao_total_ve_todas_mas_so_edita_as_dele(client, db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("UPDATE usuarios SET agenda_permissao_total = 1 WHERE id = ?", (cen.prof_a1["id"],))
    cen.prof_a1["agenda_permissao_total"] = 1
    id_a2 = _criar(client, cen.gestor_a, profissional_id=cen.prof_a2["id"]).get_json()["id"]
    itens = autenticado(client, cen.prof_a1).get("/api/agenda/ausencias?inicio=2026-10-04&fim=2026-10-10").get_json()
    assert {i["profissional_id"] for i in itens} == {cen.prof_a2["id"]}
    assert not any(i["pode_editar"] for i in itens)
    assert autenticado(client, cen.prof_a1).put(f"/api/agenda/ausencias/{id_a2}", json=ALMOCO).status_code == 403
    assert autenticado(client, cen.prof_a1).delete(f"/api/agenda/ausencias/{id_a2}").status_code == 403


def test_responsavel_nao_ve(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.resp_a1).get("/api/agenda/ausencias?inicio=2026-10-04&fim=2026-10-10")
    assert r.status_code == 403


def test_intervalo_invalido_ou_longo(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    assert c.get("/api/agenda/ausencias?inicio=2026-10-10&fim=2026-10-04").status_code == 400
    assert c.get("/api/agenda/ausencias?inicio=2026-01-01&fim=2026-03-31").status_code == 400
    assert c.get("/api/agenda/ausencias?inicio=x&fim=y").status_code == 400


def test_outra_clinica_nao_edita_nem_apaga(client, db_ctx):
    cen = DuasClinicas()
    id_a = _criar(client, cen.prof_a1).get_json()["id"]
    assert autenticado(client, cen.gestor_b).put(f"/api/agenda/ausencias/{id_a}", json=ALMOCO).status_code == 404
    assert autenticado(client, cen.gestor_b).delete(f"/api/agenda/ausencias/{id_a}").status_code == 404


def test_editar_e_apagar(client, db_ctx):
    cen = DuasClinicas()
    id_a = _criar(client, cen.prof_a1).get_json()["id"]
    r = autenticado(client, cen.prof_a1).put(f"/api/agenda/ausencias/{id_a}", json={**ALMOCO, "motivo": "Almoço longo", "hora_fim": "14:00"})
    assert r.status_code == 200
    assert db_ctx.query_one("SELECT hora_fim, motivo FROM ausencias_profissional WHERE id = ?", (id_a,)) == {"hora_fim": "14:00", "motivo": "Almoço longo"}
    assert autenticado(client, cen.gestor_a).delete(f"/api/agenda/ausencias/{id_a}").status_code == 200
    assert db_ctx.query_one("SELECT 1 FROM ausencias_profissional WHERE id = ?", (id_a,)) is None


def test_lista_consultas_ja_marcadas_no_periodo(client, db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("""INSERT INTO consultas (paciente_id, profissional_id, data_hora, duracao_min)
                      VALUES (?, ?, '2099-10-05 12:30:00', 50)""", (cen.paciente_a1, cen.prof_a1["id"]))
    db_ctx.execute("""INSERT INTO consultas (paciente_id, profissional_id, data_hora, duracao_min)
                      VALUES (?, ?, '2099-10-05 15:00:00', 50)""", (cen.paciente_a1, cen.prof_a1["id"]))
    r = _criar(client, cen.prof_a1, data_inicio="2099-10-05", data_fim="2099-10-09")
    lista = r.get_json()["consultas_no_periodo"]
    assert [c["data_hora"] for c in lista] == ["2099-10-05 12:30:00"]
    assert lista[0]["paciente_nome"] == "Paciente A1"
```

(No SQLite, `db.query_one` devolve `dict` — `dict_factory` em `db.py` —, então a comparação direta funciona.)

- [ ] **Step 2: Run test to verify it fails**

Run: `... -m pytest -q tests/test_agenda_ausencias.py`
Expected: FAIL (404 nas rotas).

- [ ] **Step 3: Implement**

No topo de `agenda_bp.py`, junto dos imports:

```python
from datetime import timedelta

import ausencias_service
```

No fim de `agenda_bp.py`:

```python
# ---------------------------------------------------------------- Ausências (spec 07/10/2026)

MAX_DIAS_AUSENCIAS = 62


def _ve_agenda_toda(u):
    return u["papel"] in ("gestor", "secretaria") or (u["papel"] == "profissional" and u.get("agenda_permissao_total"))


def _pode_editar_ausencia(u, aus):
    """Profissional: só as dele. Gestor e secretária: qualquer uma da clínica."""
    if aus["organizacao_id"] != u["organizacao_id"]:
        return False
    if u["papel"] in ("gestor", "secretaria"):
        return True
    return aus["profissional_id"] == u["id"]


def _alvo_da_ausencia(u, body):
    """Profissional da ausência, ou (None, resposta_de_erro)."""
    if u["papel"] == "profissional":
        alvo = body.get("profissional_id") or u["id"]
        if int(alvo) != u["id"]:
            return None, (jsonify({"erro": "Você só pode lançar ausências na sua própria agenda."}), 403)
        return u["id"], None
    try:
        alvo = int(body.get("profissional_id") or u["id"])
    except (TypeError, ValueError):
        return None, (jsonify({"erro": "Profissional inválido."}), 400)
    if not _profissional_da_mesma_clinica(alvo, u["organizacao_id"]):
        return None, (jsonify({"erro": "Profissional inválido para esta clínica."}), 400)
    return alvo, None


@bp.get("/ausencias")
@login_required
@papel_required("gestor", "profissional", "secretaria")
def listar_ausencias():
    u = g.usuario
    ini = ausencias_service._data(request.args.get("inicio"))
    fim = ausencias_service._data(request.args.get("fim"))
    if not ini or not fim or fim < ini:
        return jsonify({"erro": "Intervalo de datas inválido."}), 400
    if (fim - ini).days > MAX_DIAS_AUSENCIAS:
        return jsonify({"erro": f"Peça no máximo {MAX_DIAS_AUSENCIAS} dias de cada vez."}), 400
    sql = """SELECT a.*, prof.nome AS profissional_nome FROM ausencias_profissional a
             JOIN usuarios prof ON prof.id = a.profissional_id
             WHERE a.organizacao_id = ? AND a.data_inicio <= ? AND (a.data_fim IS NULL OR a.data_fim >= ?)"""
    params = [u["organizacao_id"], fim.isoformat(), ini.isoformat()]
    if not _ve_agenda_toda(u):
        sql += " AND a.profissional_id = ?"
        params.append(u["id"])
    regras = query(sql, tuple(params))
    nomes = {r["id"]: r["profissional_nome"] for r in regras}
    editaveis = {r["id"]: _pode_editar_ausencia(u, r) for r in regras}
    saida = ausencias_service.ocorrencias(regras, ini, fim)
    for o in saida:
        o["profissional_nome"] = nomes.get(o["ausencia_id"])
        o["pode_editar"] = editaveis.get(o["ausencia_id"], False)
    return jsonify(saida)


@bp.post("/ausencias")
@login_required
@papel_required("gestor", "profissional", "secretaria")
def criar_ausencia():
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    alvo, erro_resp = _alvo_da_ausencia(u, body)
    if erro_resp:
        return erro_resp
    dados, erro = ausencias_service.validar_ausencia(body)
    if erro:
        return jsonify({"erro": erro}), 400
    aus_id = execute(
        """INSERT INTO ausencias_profissional (organizacao_id, profissional_id, data_inicio, data_fim, dia_inteiro,
           hora_inicio, hora_fim, dias_semana, motivo, criado_por) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (u["organizacao_id"], alvo, dados["data_inicio"], dados["data_fim"], dados["dia_inteiro"],
         dados["hora_inicio"], dados["hora_fim"], dados["dias_semana"], dados["motivo"], u["id"]),
    )
    log_auditoria(u["organizacao_id"], u["id"], "criar", "ausencia", aus_id, dados["motivo"] or "")
    return jsonify({"id": aus_id, "consultas_no_periodo": ausencias_service.consultas_no_periodo({**dados, "profissional_id": alvo})}), 201


def _ausencia_da_clinica(u, aus_id):
    return query_one("SELECT * FROM ausencias_profissional WHERE id = ? AND organizacao_id = ?", (aus_id, u["organizacao_id"]))


@bp.put("/ausencias/<int:aus_id>")
@login_required
@papel_required("gestor", "profissional", "secretaria")
def editar_ausencia(aus_id):
    u = g.usuario
    aus = _ausencia_da_clinica(u, aus_id)
    if not aus:
        return jsonify({"erro": "Ausência não encontrada."}), 404
    if not _pode_editar_ausencia(u, aus):
        return jsonify({"erro": "Você não pode alterar esta ausência."}), 403
    body = request.get_json(force=True, silent=True) or {}
    dados, erro = ausencias_service.validar_ausencia(body)
    if erro:
        return jsonify({"erro": erro}), 400
    execute(
        """UPDATE ausencias_profissional SET data_inicio = ?, data_fim = ?, dia_inteiro = ?, hora_inicio = ?,
           hora_fim = ?, dias_semana = ?, motivo = ? WHERE id = ?""",
        (dados["data_inicio"], dados["data_fim"], dados["dia_inteiro"], dados["hora_inicio"],
         dados["hora_fim"], dados["dias_semana"], dados["motivo"], aus_id),
    )
    log_auditoria(u["organizacao_id"], u["id"], "editar", "ausencia", aus_id, dados["motivo"] or "")
    return jsonify({"ok": True, "consultas_no_periodo": ausencias_service.consultas_no_periodo({**dados, "profissional_id": aus["profissional_id"]})})


@bp.delete("/ausencias/<int:aus_id>")
@login_required
@papel_required("gestor", "profissional", "secretaria")
def excluir_ausencia(aus_id):
    u = g.usuario
    aus = _ausencia_da_clinica(u, aus_id)
    if not aus:
        return jsonify({"erro": "Ausência não encontrada."}), 404
    if not _pode_editar_ausencia(u, aus):
        return jsonify({"erro": "Você não pode apagar esta ausência."}), 403
    execute("DELETE FROM ausencias_profissional WHERE id = ?", (aus_id,))
    log_auditoria(u["organizacao_id"], u["id"], "excluir", "ausencia", aus_id, aus.get("motivo") or "")
    return jsonify({"ok": True})
```

Gestor que "atua como profissional" passa pelo ramo de gestor e pode lançar para si mesmo, porque `_profissional_da_mesma_clinica` aceita o gestor nesse caso.

- [ ] **Step 4: Run tests**

Run: `... -m pytest -q tests/test_agenda_ausencias.py`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/blueprints/agenda_bp.py backend/tests/test_agenda_ausencias.py
git commit -m "Agenda: rotas de ausências (listar, lançar, editar, apagar)"
```

---

### Task 4: Bloqueio, duração validada e padrão da clínica nas consultas

**Files:**
- Modify: `backend/blueprints/agenda_bp.py` (`criar_consulta`, `criar_consulta_recorrente`, `editar_consulta`)
- Test: `backend/tests/test_agenda_bloqueio_ausencia.py`

**Interfaces:**
- Consumes: `ausencias_service.conflito_ausencia(profissional_id, data_hora, duracao_min) -> dict | None`; `validacao_campos.validar_duracao`.
- Produces: 409 `{"erro": "<Nome> está ausente nesse horário (<motivo>).", "ausencia_id": id}`; resposta do recorrente ganha `datas_puladas: [YYYY-MM-DD]`; helper `_duracao_do_corpo(body, org_id) -> (int | None, str | None)`.

- [ ] **Step 1: Write the failing test**

```python
"""Ausência bloqueia agendar por cima; duração validada (spec 07/10/2026)."""
from factories import DuasClinicas

from conftest import autenticado

ALMOCO = {"data_inicio": "2026-10-05", "data_fim": "", "dia_inteiro": False,
          "hora_inicio": "12:00", "hora_fim": "13:00", "dias_semana": "12345", "motivo": "Almoço"}


def _ausencia(client, cen, prof, **extra):
    r = autenticado(client, cen.gestor_a).post("/api/agenda/ausencias", json={**ALMOCO, "profissional_id": prof["id"], **extra})
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["id"]


def _agendar(client, usuario, prof, data_hora, _pac, **extra):
    return autenticado(client, usuario).post("/api/agenda", json={
        "paciente_id": _pac, "profissional_id": prof["id"], "data_hora": data_hora, **extra})


def test_criar_por_cima_da_ausencia_da_409(client, db_ctx):
    cen = DuasClinicas()
    _ausencia(client, cen, cen.prof_a1)
    r = _agendar(client, cen.gestor_a, cen.prof_a1, "2026-10-06 12:30:00", _pac=cen.paciente_a1, duracao_min=30)
    assert r.status_code == 409
    assert "Prof A1 está ausente" in r.get_json()["erro"] and "Almoço" in r.get_json()["erro"]


def test_consulta_que_encosta_passa(client, db_ctx):
    cen = DuasClinicas()
    _ausencia(client, cen, cen.prof_a1)
    r = _agendar(client, cen.gestor_a, cen.prof_a1, "2026-10-06 11:00:00", _pac=cen.paciente_a1, duracao_min=60)
    assert r.status_code == 201, r.get_data(as_text=True)


def test_duracao_invalida_da_400_e_padrao_vem_da_clinica(client, db_ctx):
    cen = DuasClinicas()
    r = _agendar(client, cen.gestor_a, cen.prof_a1, "2026-10-06 09:00:00", _pac=cen.paciente_a1, duracao_min=2)
    assert r.status_code == 400
    db_ctx.execute("UPDATE organizacoes SET agenda_duracao_padrao = 45 WHERE id = ?", (cen.org_a,))
    r = _agendar(client, cen.gestor_a, cen.prof_a1, "2026-10-06 09:00:00", _pac=cen.paciente_a1)
    assert r.status_code == 201
    assert db_ctx.query_one("SELECT duracao_min FROM consultas WHERE id = ?", (r.get_json()["id"],))["duracao_min"] == 45


def test_remarcar_e_reatribuir_para_ausencia_dao_409(client, db_ctx):
    cen = DuasClinicas()
    r = _agendar(client, cen.gestor_a, cen.prof_a1, "2026-10-06 09:00:00", _pac=cen.paciente_a1, duracao_min=50)
    cid = r.get_json()["id"]
    _ausencia(client, cen, cen.prof_a1)
    _ausencia(client, cen, cen.prof_a2, hora_inicio="08:00", hora_fim="10:00", motivo="Curso")
    c = autenticado(client, cen.gestor_a)
    assert c.put(f"/api/agenda/{cid}", json={"data_hora": "2026-10-06 12:15:00"}).status_code == 409
    r2 = c.put(f"/api/agenda/{cid}", json={"profissional_id": cen.prof_a2["id"]})
    assert r2.status_code == 409 and "Curso" in r2.get_json()["erro"]
    assert c.put(f"/api/agenda/{cid}", json={"duracao_min": 300}).status_code == 409  # 09:00 + 300 min cruza o almoço


def test_editar_so_observacao_nao_checa_ausencia(client, db_ctx):
    cen = DuasClinicas()
    cid = _agendar(client, cen.gestor_a, cen.prof_a1, "2026-10-06 12:00:00", _pac=cen.paciente_a1, duracao_min=50).get_json()["id"]
    _ausencia(client, cen, cen.prof_a1)  # criada depois, por cima da consulta
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{cid}", json={"observacoes": "Trazer exames"})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_recorrente_pula_datas_da_ausencia(client, db_ctx):
    cen = DuasClinicas()
    _ausencia(client, cen, cen.prof_a1, data_inicio="2026-10-13", data_fim="2026-10-17",
              dia_inteiro=True, hora_inicio="", hora_fim="", motivo="Férias")
    r = autenticado(client, cen.gestor_a).post("/api/agenda/recorrente", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a1["id"], "data_hora": "2026-10-06 09:00:00",
        "frequencia": "semanal", "repeticoes": 3, "duracao_min": 45})
    assert r.status_code == 201, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["total_criadas"] == 2 and corpo["datas_puladas"] == ["2026-10-13"]
    datas = [c["data_hora"] for c in db_ctx.query("SELECT data_hora FROM consultas ORDER BY data_hora")]
    assert datas == ["2026-10-06 09:00:00", "2026-10-20 09:00:00"]


def test_recorrente_toda_bloqueada_nao_cria_nada(client, db_ctx):
    cen = DuasClinicas()
    _ausencia(client, cen, cen.prof_a1, data_inicio="2026-10-01", data_fim="2026-10-31",
              dia_inteiro=True, hora_inicio="", hora_fim="", dias_semana="0123456", motivo="Férias")
    r = autenticado(client, cen.gestor_a).post("/api/agenda/recorrente", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a1["id"], "data_hora": "2026-10-06 09:00:00",
        "frequencia": "semanal", "repeticoes": 3})
    assert r.status_code == 409
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM consultas")["n"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... -m pytest -q tests/test_agenda_bloqueio_ausencia.py`
Expected: FAIL (consultas criadas com 201 por cima da ausência).

- [ ] **Step 3: Implement**

Em `agenda_bp.py`, junto dos imports: `from validacao_campos import validar_duracao`. Helpers logo antes de `@bp.get("")`:

```python
DURACAO_MIN, DURACAO_MAX = 5, 480


def _duracao_do_corpo(body, org_id):
    """duracao_min do corpo (validada) ou o padrão da clínica (spec 07/10/2026)."""
    if "duracao_min" in body and body.get("duracao_min") not in (None, ""):
        return validar_duracao(body.get("duracao_min"), DURACAO_MIN, DURACAO_MAX)
    org = query_one("SELECT agenda_duracao_padrao FROM organizacoes WHERE id = ?", (org_id,))
    return int((org or {}).get("agenda_duracao_padrao") or 50), None


def _resposta_conflito(profissional_id, aus):
    prof = query_one("SELECT nome FROM usuarios WHERE id = ?", (profissional_id,))
    motivo = f" ({aus['motivo']})" if aus.get("motivo") else ""
    return jsonify({"erro": f"{(prof or {}).get('nome', 'O profissional')} está ausente nesse horário{motivo}.",
                    "ausencia_id": aus["id"]}), 409
```

`criar_consulta` — depois da checagem `_profissional_da_mesma_clinica` e antes do INSERT:

```python
    duracao, erro_dur = _duracao_do_corpo(body, org_id)
    if erro_dur:
        return jsonify({"erro": erro_dur}), 400
    aus = ausencias_service.conflito_ausencia(profissional_id, body.get("data_hora"), duracao)
    if aus:
        return _resposta_conflito(profissional_id, aus)
```

e no INSERT troque `body.get("duracao_min", 50)` por `duracao`.

`criar_consulta_recorrente` — troque `duracao_min = body.get("duracao_min", 50)` por (depois de calcular `org_id` e validar o profissional):

```python
    duracao_min, erro_dur = _duracao_do_corpo(body, org_id)
    if erro_dur:
        return jsonify({"erro": erro_dur}), 400
```

Reestruture o laço em duas fases — primeiro calcula as datas, depois insere:

```python
    datas = []
    for i in range(repeticoes):
        if frequencia == "mensal":
            ...  # mesmo cálculo de hoje, resultando em data_ocorrencia
        else:
            data_ocorrencia = data_hora_inicial + timedelta(days=FREQUENCIAS_RECORRENCIA[frequencia] * i)
        datas.append(data_ocorrencia.strftime("%Y-%m-%d %H:%M:%S"))

    livres, datas_puladas = [], []
    for dh in datas:
        if ausencias_service.conflito_ausencia(profissional_id, dh, duracao_min):
            datas_puladas.append(dh[:10])
        else:
            livres.append(dh)
    if not livres:
        prof = query_one("SELECT nome FROM usuarios WHERE id = ?", (profissional_id,))
        return jsonify({"erro": f"{(prof or {}).get('nome', 'O profissional')} está ausente em todas as datas da repetição."}), 409

    ids_criados = []
    serie_id = None
    for dh in livres:
        consulta_id = execute(
            """INSERT INTO consultas (paciente_id, profissional_id, data_hora, duracao_min, observacoes, serie_recorrencia_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (paciente_id, profissional_id, dh, duracao_min, observacoes, serie_id),
        )
        if serie_id is None:
            serie_id = consulta_id
            execute("UPDATE consultas SET serie_recorrencia_id = ? WHERE id = ?", (serie_id, consulta_id))
        ids_criados.append(consulta_id)
        sincronizar_consulta_google(consulta_id, org_id, acao="criar")
```

Mantenha o cálculo mensal existente (copie o bloco `if frequencia == "mensal": ...` de hoje para dentro do primeiro laço). Na resposta, acrescente `"datas_puladas": datas_puladas`.

`editar_consulta` — depois da checagem de troca de profissional e antes do UPDATE:

```python
    nova_data_hora = body.get("data_hora", consulta["data_hora"])
    nova_duracao = consulta["duracao_min"] or 50
    if "duracao_min" in body:
        nova_duracao, erro_dur = validar_duracao(body.get("duracao_min"), DURACAO_MIN, DURACAO_MAX)
        if erro_dur:
            return jsonify({"erro": erro_dur}), 400
    mudou_horario = (nova_data_hora != consulta["data_hora"] or nova_duracao != (consulta["duracao_min"] or 50)
                     or novo_profissional_id != consulta["profissional_id"])
    if mudou_horario and consulta["status"] != "cancelada":
        aus = ausencias_service.conflito_ausencia(novo_profissional_id, nova_data_hora, nova_duracao)
        if aus:
            return _resposta_conflito(novo_profissional_id, aus)
```

e no UPDATE use `nova_data_hora` e `nova_duracao` no lugar de `body.get("data_hora", ...)` e `body.get("duracao_min", ...)`.

- [ ] **Step 4: Run tests**

Run: `... -m pytest -q tests/test_agenda_bloqueio_ausencia.py tests/test_vinculo_automatico_agenda.py tests/test_idor_agenda.py`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add backend/blueprints/agenda_bp.py backend/tests/test_agenda_bloqueio_ausencia.py
git commit -m "Agenda: ausência bloqueia agendar, duração validada e padrão da clínica"
```

---

### Task 5: Duração padrão da clínica (API e Configurações)

**Files:**
- Modify: `backend/blueprints/pessoas_bp.py` (`atualizar_organizacao`, ~linha 1282 e o UPDATE ~1388)
- Modify: `backend/blueprints/auth_bp.py:20-24` (`CAMPOS_ORG`)
- Modify: `backend/identidade_service.py:40-42` (`_PASSAM_SEMPRE`)
- Modify: `frontend/js/views/financeiro.js` (cartão do horário ~linha 462 e envio ~linha 686)
- Test: `backend/tests/test_horario_agenda.py` (casos novos)

**Interfaces:**
- Produces: `PUT /api/pessoas/organizacao` aceita `agenda_duracao_padrao` (5–240); `/auth/me` → `organizacao.agenda_duracao_padrao`.

- [ ] **Step 1: Write the failing test** (acrescentar a `backend/tests/test_horario_agenda.py`)

```python
def test_duracao_padrao_salva_e_aparece_no_auth_me(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    assert c.put("/api/pessoas/organizacao", json={"agenda_duracao_padrao": 45}).status_code == 200
    assert c.get("/api/auth/me").get_json()["organizacao"]["agenda_duracao_padrao"] == 45


def test_duracao_padrao_invalida_da_400(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    for ruim in (4, 241, "abc"):
        assert c.put("/api/pessoas/organizacao", json={"agenda_duracao_padrao": ruim}).status_code == 400


def test_salvar_sem_o_campo_nao_mexe_na_duracao(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    c.put("/api/pessoas/organizacao", json={"agenda_duracao_padrao": 40})
    c.put("/api/pessoas/organizacao", json={"nome": "Clínica A"})
    assert db_ctx.query_one("SELECT agenda_duracao_padrao FROM organizacoes WHERE id = ?", (cen.org_a,))["agenda_duracao_padrao"] == 40
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... -m pytest -q tests/test_horario_agenda.py`
Expected: FAIL (campo ignorado / ausente no `/auth/me`).

- [ ] **Step 3: Implement**

`pessoas_bp.py`, em `atualizar_organizacao`, logo depois do bloco do horário da agenda:

```python
    # Duração padrão da consulta (spec 07/10/2026) — só mexe se vier no corpo.
    duracao_padrao = org_atual.get("agenda_duracao_padrao") or 50
    if "agenda_duracao_padrao" in body:
        duracao_padrao, erro_dur = validar_duracao(body.get("agenda_duracao_padrao"), 5, 240)
        if erro_dur:
            return jsonify({"erro": erro_dur}), 400
```

Importe `validar_duracao` de `validacao_campos` (mesmo import onde está `validar_horario_agenda`). No UPDATE, troque `agenda_hora_inicio = ?, agenda_hora_fim = ?,` por `agenda_hora_inicio = ?, agenda_hora_fim = ?, agenda_duracao_padrao = ?,` e, na tupla de parâmetros, logo depois do `hora_fim` correspondente, acrescente `duracao_padrao`.

`auth_bp.py` `CAMPOS_ORG`: `agenda_permissao_total_padrao, agenda_hora_inicio, agenda_hora_fim, agenda_duracao_padrao,`.

`identidade_service.py` `_PASSAM_SEMPRE`: acrescente `"agenda_duracao_padrao"` depois de `"agenda_hora_fim"`.

`financeiro.js`, dentro do bloco "🕒 Horário de funcionamento da agenda", depois da `div.linha` de "Abre às/Fecha às":

```js
          <div class="campo" style="max-width:260px;"><label>Duração padrão da consulta (min)</label><input type="number" id="cf-agenda-duracao" min="5" max="240" step="5" value="${escapeHtml(String(org.agenda_duracao_padrao || 50))}" /></div>
          <p class="texto-xs texto-suave" style="margin:-8px 0 12px;">Ao agendar, o horário de fim já vem com essa duração (dá para mudar em cada consulta).</p>
```

No envio (`salvarOrganizacao({...})` do mesmo formulário), antes da chamada:

```js
        const duracaoPadrao = parseInt(document.getElementById("cf-agenda-duracao").value, 10);
        if (!(duracaoPadrao >= 5 && duracaoPadrao <= 240)) { Toast.erro("A duração padrão precisa ficar entre 5 e 240 minutos."); return; }
```

e no objeto, depois de `agenda_hora_fim: agendaFim,`: `agenda_duracao_padrao: duracaoPadrao,`.

- [ ] **Step 4: Run tests**

Run: `... -m pytest -q tests/test_horario_agenda.py tests/test_white_label_api.py tests/test_identidade_service.py`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add backend/blueprints/pessoas_bp.py backend/blueprints/auth_bp.py backend/identidade_service.py frontend/js/views/financeiro.js backend/tests/test_horario_agenda.py
git commit -m "Configurações: duração padrão da consulta"
```

---

### Task 6: Funções puras do front (`agenda_ausencias.js`) e faixa com ausências

**Files:**
- Create: `frontend/js/agenda_ausencias.js`
- Modify: `frontend/js/agenda_faixa.js` (`calcularFaixaAgenda` ganha 4º parâmetro)
- Modify: `frontend/index.html` (script novo logo depois de `agenda_faixa.js`)
- Test: `frontend/tests/agenda_ausencias.test.js`, `frontend/tests/agenda_faixa.test.js`

**Interfaces:**
- Consumes: `hhmmParaMinutos`, `minutosParaHHMM` (de `agenda_faixa.js`; no Node, via `require`).
- Produces:
  - `ocorrenciasDaColuna(ocorrencias, profissionalId, chaveDia) -> ocorrencia[]`
  - `intervaloBloqueado(ocorrencias, profissionalId, chaveDia, iniMin, fimMin) -> ocorrencia | null`
  - `calcularFim(inicioHHMM, duracaoMin) -> "HH:MM" | ""` (passa de 23:59 → "23:59")
  - `duracaoEntre(inicioHHMM, fimHHMM) -> number | null` (null se inválido ou fim ≤ início)
  - `diasSemanaPadrao(dataInicio, dataFim) -> string` ("123456" se período > 1 dia ou sem fim; senão o dígito do dia)
  - `calcularFaixaAgenda(consultas, horaInicioClinica, horaFimClinica, ocorrenciasAusencia = [])`

- [ ] **Step 1: Write the failing test** (`frontend/tests/agenda_ausencias.test.js`)

```js
// Funções puras das ausências da agenda (spec 07/10/2026).
// Rodar: node --test frontend/tests/*.test.js
process.env.TZ = "America/Sao_Paulo";
const test = require("node:test");
const assert = require("node:assert/strict");
const a = require("../js/agenda_ausencias.js");

const almoco = { ausencia_id: 1, profissional_id: 7, data: "2026-10-06", dia_inteiro: 0, hora_inicio: "12:00", hora_fim: "13:00" };
const ferias = { ausencia_id: 2, profissional_id: 8, data: "2026-10-06", dia_inteiro: 1, hora_inicio: null, hora_fim: null };

test("ocorrenciasDaColuna filtra por profissional e dia", () => {
    assert.deepEqual(a.ocorrenciasDaColuna([almoco, ferias], 7, "2026-10-06"), [almoco]);
    assert.deepEqual(a.ocorrenciasDaColuna([almoco], 7, "2026-10-07"), []);
});

test("intervaloBloqueado: sobrepor bloqueia, encostar não", () => {
    assert.equal(a.intervaloBloqueado([almoco], 7, "2026-10-06", 690, 750), almoco);
    assert.equal(a.intervaloBloqueado([almoco], 7, "2026-10-06", 660, 720), null);
    assert.equal(a.intervaloBloqueado([almoco], 7, "2026-10-06", 780, 840), null);
    assert.equal(a.intervaloBloqueado([ferias], 8, "2026-10-06", 420, 425), ferias);
});

test("calcularFim e duracaoEntre", () => {
    assert.equal(a.calcularFim("09:00", 50), "09:50");
    assert.equal(a.calcularFim("23:30", 50), "23:59");
    assert.equal(a.calcularFim("", 50), "");
    assert.equal(a.duracaoEntre("09:00", "09:45"), 45);
    assert.equal(a.duracaoEntre("09:00", "09:00"), null);
    assert.equal(a.duracaoEntre("10:00", "09:00"), null);
    assert.equal(a.duracaoEntre("", "09:00"), null);
});

test("diasSemanaPadrao", () => {
    assert.equal(a.diasSemanaPadrao("2026-10-07", "2026-10-07"), "3"); // quarta
    assert.equal(a.diasSemanaPadrao("2026-10-07", ""), "123456");
    assert.equal(a.diasSemanaPadrao("2026-10-07", "2026-10-20"), "123456");
});
```

Em `frontend/tests/agenda_faixa.test.js`, acrescente:

```js
test("ausência com horário fora da faixa estica; dia inteiro não", () => {
    const aus = [{ data: "2026-10-06", dia_inteiro: 0, hora_inicio: "07:00", hora_fim: "07:30" },
                 { data: "2026-10-06", dia_inteiro: 1, hora_inicio: null, hora_fim: null }];
    assert.deepEqual(f.calcularFaixaAgenda([], null, null, aus), { ini: 420, fim: 1080 });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/*.test.js`
Expected: FAIL (`Cannot find module '../js/agenda_ausencias.js'`).

- [ ] **Step 3: Implement**

`frontend/js/agenda_ausencias.js`:

```js
// ============================================================================
// Agenda — ausências e hora de fim (spec 07/10/2026)
//
// Funções puras (sem DOM), testadas em frontend/tests/agenda_ausencias.test.js.
// No navegador viram globais; no Node, dependem de agenda_faixa.js via require.
// ============================================================================

const _faixa = (typeof module !== "undefined" && module.exports) ? require("./agenda_faixa.js") : null;
const _hhmmParaMin = (x) => (_faixa ? _faixa.hhmmParaMinutos(x) : hhmmParaMinutos(x));
const _minParaHHMM = (x) => (_faixa ? _faixa.minutosParaHHMM(x) : minutosParaHHMM(x));

function ocorrenciasDaColuna(ocorrencias, profissionalId, chaveDia) {
    return (ocorrencias || []).filter(o => o.profissional_id === profissionalId && o.data === chaveDia);
}

// Ocorrência que bate com [iniMin, fimMin) — encostar não conta.
function intervaloBloqueado(ocorrencias, profissionalId, chaveDia, iniMin, fimMin) {
    for (const o of ocorrenciasDaColuna(ocorrencias, profissionalId, chaveDia)) {
        if (o.dia_inteiro) return o;
        const ai = _hhmmParaMin(o.hora_inicio), af = _hhmmParaMin(o.hora_fim);
        if (ai !== null && af !== null && iniMin < af && fimMin > ai) return o;
    }
    return null;
}

function calcularFim(inicioHHMM, duracaoMin) {
    const ini = _hhmmParaMin(inicioHHMM);
    if (ini === null) return "";
    return _minParaHHMM(Math.min(ini + (duracaoMin || 0), 23 * 60 + 59));
}

function duracaoEntre(inicioHHMM, fimHHMM) {
    const ini = _hhmmParaMin(inicioHHMM), fim = _hhmmParaMin(fimHHMM);
    if (ini === null || fim === null || fim <= ini) return null;
    return fim - ini;
}

// Período de vários dias (ou sem fim) → seg a sáb; um dia só → o dia dele.
function diasSemanaPadrao(dataInicio, dataFim) {
    if (dataInicio && dataFim && dataInicio === dataFim) {
        return String(new Date(dataInicio + "T00:00:00").getDay());
    }
    return "123456";
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { ocorrenciasDaColuna, intervaloBloqueado, calcularFim, duracaoEntre, diasSemanaPadrao };
}
```

`agenda_faixa.js` — assinatura `function calcularFaixaAgenda(consultas, horaInicioClinica, horaFimClinica, ocorrenciasAusencia = [])` e, depois do `forEach` das consultas:

```js
    (ocorrenciasAusencia || []).forEach(o => {
        if (!o || o.dia_inteiro) return; // dia inteiro ocupa a coluna toda, não estica
        const ai = hhmmParaMinutos(o.hora_inicio), af = hhmmParaMinutos(o.hora_fim);
        if (ai === null || af === null) return;
        if (ai < ini) ini = Math.floor(ai / 60) * 60;
        if (af > fim) fim = Math.min(1440, Math.ceil(af / 60) * 60);
    });
```

Atualize o comentário acima da função ("…consultas e ausências com horário fora da faixa esticam…").

`frontend/index.html`, depois de `<script src="/js/agenda_faixa.js"></script>`:

```html
<script src="/js/agenda_ausencias.js"></script>
```

- [ ] **Step 4: Run tests**

Run: `node --test frontend/tests/*.test.js`
Expected: todos passam (77 + 5 novos).

- [ ] **Step 5: Commit**

```bash
git add frontend/js/agenda_ausencias.js frontend/js/agenda_faixa.js frontend/index.html frontend/tests/agenda_ausencias.test.js frontend/tests/agenda_faixa.test.js
git commit -m "Agenda (front): funções puras de ausência e hora de fim"
```

---

### Task 7: Início e Fim nos pop-ups de consulta

**Files:**
- Modify: `frontend/js/views/agenda.js` (`abrirModalNovaConsulta` ~linha 578, `abrirModalEditarConsulta` ~linha 687)

**Interfaces:**
- Consumes: `calcularFim`, `duracaoEntre` (Task 6); `Sessao.usuario.organizacao.agenda_duracao_padrao` (Task 5).
- Produces: `abrirModalNovaConsulta(preSelecao, aoAtualizar)` continua com a mesma assinatura; `preSelecao` aceita `{profissionalId, data, hora}`. Novo helper global `duracaoPadraoClinica() -> number`.

- [ ] **Step 1: Implement — helper e campos**

No topo de `agenda.js` (depois de `STATUS_CONSULTA_INFO`):

```js
function duracaoPadraoClinica() {
    const d = parseInt((Sessao.usuario && Sessao.usuario.organizacao && Sessao.usuario.organizacao.agenda_duracao_padrao) || 0, 10);
    return d >= 5 && d <= 240 ? d : AGENDA_DURACAO_PADRAO;
}

// Liga Início → Fim: mudar o início desloca o fim mantendo a duração; mudar o
// fim recalcula a duração. Devolve () => duracao (null se fim <= início).
function ligarInicioFim(idInicio, idFim, duracaoInicial) {
    const elIni = document.getElementById(idInicio), elFim = document.getElementById(idFim);
    let duracao = duracaoInicial;
    if (!elFim.value) elFim.value = calcularFim(elIni.value, duracao);
    elIni.addEventListener("change", () => { elFim.value = calcularFim(elIni.value, duracao); elFim.setCustomValidity(""); });
    elFim.addEventListener("change", () => {
        const d = duracaoEntre(elIni.value, elFim.value);
        elFim.setCustomValidity(d ? "" : "O fim precisa ser depois do início.");
        if (d) duracao = d;
        elFim.reportValidity();
    });
    return () => duracaoEntre(elIni.value, elFim.value);
}
```

Em `abrirModalNovaConsulta`, troque o bloco de Data/Hora por:

```js
          <div class="linha gap-4">
            <div class="campo" style="flex:1.3;"><label>Data ${ASTERISCO_OBRIGATORIO}</label><input type="date" id="ag-data" required value="${preSelecao.data || ""}" /></div>
            <div class="campo" style="flex:1;"><label>Início ${ASTERISCO_OBRIGATORIO}</label><input type="time" id="ag-hora" required value="${preSelecao.hora || "14:00"}" /></div>
            <div class="campo" style="flex:1;"><label>Fim ${ASTERISCO_OBRIGATORIO}</label><input type="time" id="ag-hora-fim" required value="" /></div>
          </div>
```

Depois de `document.body.appendChild(modal);`: `const lerDuracao = ligarInicioFim("ag-hora", "ag-hora-fim", duracaoPadraoClinica());`

No submit, antes de montar `corpoBase`:

```js
            const duracao = lerDuracao();
            if (!duracao) { Toast.erro("O horário de fim precisa ser depois do início."); return; }
```

e em `corpoBase` acrescente `duracao_min: duracao,`. No ramo recorrente, troque o toast por:

```js
                const puladas = r.datas_puladas || [];
                Toast.sucesso(`${r.total_criadas} consultas agendadas! 🔁`);
                if (puladas.length) Toast.info(`Não agendado em ${puladas.map(formatarData).join(", ")}: profissional ausente.`);
```

Em `abrirModalEditarConsulta`, troque a `div.linha` de Data/Hora por Data / Início (`ec-hora`) / Fim (`ec-hora-fim`, `value="${calcularFim(horaAtual, consulta.duracao_min || AGENDA_DURACAO_PADRAO)}"`), chame `const lerDuracaoEd = ligarInicioFim("ec-hora", "ec-hora-fim", consulta.duracao_min || AGENDA_DURACAO_PADRAO);` depois do `appendChild`, e no submit:

```js
            const duracao = lerDuracaoEd();
            if (!duracao) { Toast.erro("O horário de fim precisa ser depois do início."); return; }
```

com `duracao_min: duracao,` no corpo do `Api.put`.

- [ ] **Step 2: Verify in the browser**

Suba o servidor (CLAUDE.md seção 4, com banco recriado pelo `seed.py`), entre como gestor e confira com o Playwright: abrir "+ Agendar" → Fim = Início + 50; trocar Início para 10:00 → Fim 10:50; Fim 10:30 → agendar → o bloco na grade vai de 10:00 a 10:30. Editar a consulta → Início/Fim certos.

- [ ] **Step 3: Run front tests**

Run: `node --test frontend/tests/*.test.js` — Expected: todos passam.

- [ ] **Step 4: Commit**

```bash
git add frontend/js/views/agenda.js
git commit -m "Agenda: início e fim livres nos pop-ups de consulta"
```

---

### Task 8: Pop-up de Ausência e seletor "Consulta | Ausência"

**Files:**
- Create: `frontend/js/views/agenda_ausencia_modal.js`
- Modify: `frontend/js/views/agenda.js` (`abrirModalNovaConsulta`: seletor no topo)
- Modify: `frontend/index.html` (script novo antes de `views/agenda.js`)

**Interfaces:**
- Consumes: `diasSemanaPadrao`, `calcularFim` (Task 6); rotas da Task 3; `duracaoPadraoClinica` (Task 7).
- Produces:
  - `abrirModalAusencia({profissionalId, data, hora, ocorrencia}, aoAtualizar)` — sem `ocorrencia` cria; com `ocorrencia` (item do GET) edita (se `pode_editar`) ou só mostra.
  - `renderSeletorTipoAgendamento(tipoAtivo) -> string` (HTML dos dois botões `.btn-tipo-agendamento[data-tipo="consulta"|"ausencia"]`).

- [ ] **Step 1: Implement `agenda_ausencia_modal.js`**

```js
// ============================================================================
// views/agenda_ausencia_modal.js — pop-up de Ausência (spec 07/10/2026)
// ============================================================================

const DIAS_AUSENCIA = [["1", "Seg"], ["2", "Ter"], ["3", "Qua"], ["4", "Qui"], ["5", "Sex"], ["6", "Sáb"], ["0", "Dom"]];

function renderSeletorTipoAgendamento(tipoAtivo) {
    return `
    <div class="linha gap-2" style="margin-bottom:14px;">
      <button type="button" class="botao botao-sm ${tipoAtivo === "consulta" ? "botao-primario" : "botao-secundario"} btn-tipo-agendamento" data-tipo="consulta">📅 Consulta</button>
      <button type="button" class="botao botao-sm ${tipoAtivo === "ausencia" ? "botao-primario" : "botao-secundario"} btn-tipo-agendamento" data-tipo="ausencia">⛔ Ausência</button>
    </div>`;
}

function _textoPeriodoAusencia(o) {
    const periodo = o.data_fim
        ? (o.data_fim === o.data_inicio ? formatarData(o.data_inicio) : `${formatarData(o.data_inicio)} a ${formatarData(o.data_fim)}`)
        : `a partir de ${formatarData(o.data_inicio)}, sem fim`;
    const horario = o.dia_inteiro ? "dia inteiro" : `${o.hora_inicio}–${o.hora_fim}`;
    const dias = DIAS_AUSENCIA.filter(([v]) => String(o.dias_semana || "").includes(v)).map(([, n]) => n).join(", ");
    return `${periodo} · ${horario} · ${dias}`;
}

function _mostrarConsultasNoPeriodo(lista) {
    if (!lista || !lista.length) return;
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:8px;">Há ${lista.length} ${lista.length === 1 ? "consulta" : "consultas"} nesse período</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:12px;">A ausência foi salva. Remarque ou cancele estas consultas na agenda:</p>
        <ul class="texto-sm" style="margin:0 0 16px 18px;">
          ${lista.map(c => `<li>${escapeHtml(formatarDataHoraLocal(c.data_hora))} — ${escapeHtml(c.paciente_nome || "")}</li>`).join("")}
        </ul>
        <button type="button" class="botao botao-primario" id="btn-ok-consultas-periodo" style="width:100%;">Entendi</button>
      </div>
    </div>`);
    document.body.appendChild(modal);
    document.getElementById("btn-ok-consultas-periodo").addEventListener("click", () => modal.remove());
}

async function abrirModalAusencia(pre, aoAtualizar) {
    const atualizar = aoAtualizar || despachar;
    const u = Sessao.usuario;
    const o = pre.ocorrencia || null;
    const editando = !!o;
    const somenteVer = editando && !o.pode_editar;

    if (somenteVer) {
        const modal = el(`
        <div class="modal-fundo"><div class="modal-caixa">
          <h3 style="margin-bottom:6px;">⛔ ${escapeHtml(o.profissional_nome || "Profissional")} ausente</h3>
          <p class="texto-sm" style="margin-bottom:6px;">${escapeHtml(o.motivo || "Sem motivo informado")}</p>
          <p class="texto-xs texto-suave" style="margin-bottom:16px;">${escapeHtml(_textoPeriodoAusencia(o))}</p>
          <button type="button" class="botao botao-secundario" id="btn-fechar-ausencia" style="width:100%;">Fechar</button>
        </div></div>`);
        document.body.appendChild(modal);
        document.getElementById("btn-fechar-ausencia").addEventListener("click", () => modal.remove());
        return;
    }

    const ehProfissionalComum = u.papel === "profissional";
    const profissionais = ehProfissionalComum ? [{ id: u.id, nome: u.nome, especialidade: u.especialidade }]
        : await Api.get("/pessoas/profissionais?incluir_gestor=1");
    const profId = o ? o.profissional_id : (pre.profissionalId || (ehProfissionalComum ? u.id : profissionais[0] && profissionais[0].id));
    const dataIni = o ? o.data_inicio : (pre.data || paraChaveDia(new Date()));
    const dataFim = o ? (o.data_fim || "") : (pre.data || "");
    const diaInteiro = o ? !!o.dia_inteiro : false;
    const horaIni = o ? (o.hora_inicio || "12:00") : (pre.hora || "12:00");
    const horaFim = o ? (o.hora_fim || "13:00") : calcularFim(horaIni, 60);
    const dias = o ? String(o.dias_semana || "") : diasSemanaPadrao(dataIni, dataFim);

    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:14px;">${editando ? "Editar ausência" : "Agendar"}</h3>
        ${editando ? "" : renderSeletorTipoAgendamento("ausencia")}
        <form id="form-ausencia">
          <div class="campo"><label>Profissional ${ASTERISCO_OBRIGATORIO}</label>
            <select id="au-profissional" ${ehProfissionalComum || editando ? "disabled" : ""}>
              ${profissionais.map(p => `<option value="${p.id}" ${p.id === profId ? "selected" : ""}>${escapeHtml(p.nome)}${p.especialidade ? ` (${escapeHtml(p.especialidade)})` : ""}</option>`).join("")}
            </select>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>De ${ASTERISCO_OBRIGATORIO}</label><input type="date" id="au-data-inicio" required value="${escapeHtml(dataIni)}" /></div>
            <div class="campo" style="flex:1;"><label>Até <span class="texto-xs texto-suave">(vazio = sem fim)</span></label><input type="date" id="au-data-fim" value="${escapeHtml(dataFim)}" /></div>
          </div>
          <label class="linha gap-2" style="align-items:center; cursor:pointer; margin-bottom:10px;">
            <input type="checkbox" id="au-dia-inteiro" ${diaInteiro ? "checked" : ""} /> <span class="texto-sm">Dia inteiro</span>
          </label>
          <div class="linha gap-4" id="au-wrap-horas" style="${diaInteiro ? "display:none;" : ""}">
            <div class="campo" style="flex:1;"><label>Das</label><input type="time" id="au-hora-inicio" value="${escapeHtml(horaIni)}" /></div>
            <div class="campo" style="flex:1;"><label>Até</label><input type="time" id="au-hora-fim" value="${escapeHtml(horaFim)}" /></div>
          </div>
          <div class="campo"><label>Dias da semana</label>
            <div class="linha gap-2" style="flex-wrap:wrap;" id="au-dias">
              ${DIAS_AUSENCIA.map(([v, n]) => `<label class="linha gap-1" style="align-items:center; cursor:pointer;"><input type="checkbox" value="${v}" ${dias.includes(v) ? "checked" : ""} /><span class="texto-sm">${n}</span></label>`).join("")}
            </div>
          </div>
          <div class="campo"><label>Motivo</label><input type="text" id="au-motivo" maxlength="120" placeholder="Ex.: Almoço, Férias, Curso" value="${escapeHtml(o ? (o.motivo || "") : "")}" /></div>
          <div class="linha gap-3" style="margin-top:16px; flex-wrap:wrap;">
            <button type="submit" class="botao botao-primario">${editando ? "Salvar alterações" : "Salvar ausência"}</button>
            ${editando ? `<button type="button" class="botao botao-secundario" id="btn-apagar-ausencia">🗑️ Apagar ausência</button>` : ""}
            <button type="button" class="botao botao-secundario" id="btn-cancelar-ausencia">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    const fechar = () => modal.remove();
    document.getElementById("btn-cancelar-ausencia").addEventListener("click", fechar);
    document.getElementById("au-dia-inteiro").addEventListener("change", (e) => {
        document.getElementById("au-wrap-horas").style.display = e.target.checked ? "none" : "";
    });
    // Sem dias marcados à mão, as datas sugerem os dias (um dia só → o dia dele).
    let diasTocados = editando;
    document.querySelectorAll("#au-dias input").forEach(cb => cb.addEventListener("change", () => { diasTocados = true; }));
    const sugerirDias = () => {
        if (diasTocados) return;
        const sug = diasSemanaPadrao(document.getElementById("au-data-inicio").value, document.getElementById("au-data-fim").value);
        document.querySelectorAll("#au-dias input").forEach(cb => { cb.checked = sug.includes(cb.value); });
    };
    document.getElementById("au-data-inicio").addEventListener("change", sugerirDias);
    document.getElementById("au-data-fim").addEventListener("change", sugerirDias);

    modal.querySelectorAll(".btn-tipo-agendamento").forEach(btn => btn.addEventListener("click", () => {
        if (btn.dataset.tipo !== "consulta") return;
        const prof = parseInt(document.getElementById("au-profissional").value, 10);
        fechar();
        abrirModalNovaConsulta({ profissionalId: prof, data: document.getElementById("au-data-inicio").value, hora: document.getElementById("au-hora-inicio").value }, atualizar);
    }));

    if (editando) {
        document.getElementById("btn-apagar-ausencia").addEventListener("click", async () => {
            if (!confirm("Apagar esta ausência inteira (todas as datas dela)?")) return;
            try {
                await Api.del(`/agenda/ausencias/${o.ausencia_id}`);
                Toast.sucesso("Ausência apagada.");
                fechar();
                atualizar();
            } catch (err) { Toast.erro(err.message); }
        });
    }

    document.getElementById("form-ausencia").addEventListener("submit", async (e) => {
        e.preventDefault();
        const corpo = {
            profissional_id: parseInt(document.getElementById("au-profissional").value, 10),
            data_inicio: document.getElementById("au-data-inicio").value,
            data_fim: document.getElementById("au-data-fim").value,
            dia_inteiro: document.getElementById("au-dia-inteiro").checked,
            hora_inicio: document.getElementById("au-hora-inicio").value,
            hora_fim: document.getElementById("au-hora-fim").value,
            dias_semana: Array.from(document.querySelectorAll("#au-dias input:checked")).map(cb => cb.value).join(""),
            motivo: document.getElementById("au-motivo").value.trim(),
        };
        try {
            const r = editando ? await Api.put(`/agenda/ausencias/${o.ausencia_id}`, corpo) : await Api.post("/agenda/ausencias", corpo);
            Toast.sucesso(editando ? "Ausência atualizada!" : "Ausência salva!");
            fechar();
            atualizar();
            _mostrarConsultasNoPeriodo(r.consultas_no_periodo);
        } catch (err) { Toast.erro(err.message); }
    });
}
```

(`Api.del` é o método de DELETE em `frontend/js/api.js`.)

- [ ] **Step 2: Implement — seletor no pop-up de consulta**

Em `abrirModalNovaConsulta`, logo depois do `<h3>`: `${renderSeletorTipoAgendamento("consulta")}`. Depois do `appendChild`:

```js
    modal.querySelectorAll(".btn-tipo-agendamento").forEach(btn => btn.addEventListener("click", () => {
        if (btn.dataset.tipo !== "ausencia") return;
        const pre = {
            profissionalId: parseInt(document.getElementById("ag-profissional").value, 10),
            data: document.getElementById("ag-data").value,
            hora: document.getElementById("ag-hora").value,
        };
        modal.remove();
        abrirModalAusencia(pre, atualizar);
    }));
```

`frontend/index.html`: `<script src="/js/views/agenda_ausencia_modal.js"></script>` antes de `<script src="/js/views/agenda.js"></script>`.

- [ ] **Step 3: Verify in the browser**

Como gestor: "+ Agendar" → "⛔ Ausência" → profissional Camila, de hoje sem fim, 12:00–13:00, seg–sex, "Almoço" → salvar (toast). Como Camila (`camila@clinicaencantar.com.br`/`prof123`): o seletor de profissional vem travado nela. Confirme no DevTools/Network que o POST devolve 201.

- [ ] **Step 4: Commit**

```bash
git add frontend/js/views/agenda_ausencia_modal.js frontend/js/views/agenda.js frontend/index.html
git commit -m "Agenda: pop-up de Ausência e seletor Consulta | Ausência"
```

---

### Task 9: Grade genérica com ausências + visão Dia "Por Profissional"

**Files:**
- Modify: `frontend/js/views/agenda.js` (`viewAgenda`: estado, `renderNavSemana`, `renderVisaoPorProfissional`, `conectarEventos`)
- Modify: `frontend/css/components.css` (depois de `.agenda-bloco-nome`, ~linha 290)

**Interfaces:**
- Consumes: `ocorrenciasDaColuna`, `intervaloBloqueado` (Task 6), `abrirModalAusencia` (Task 8), `GET /agenda/ausencias`.
- Produces (dentro de `viewAgenda`): estado `escalaProf` (`"semana"|"dia"`), `ausencias` (lista de ocorrências), `async function carregarAusencias()`, `function renderGradeHoraria({titulo, colunas})` onde `colunas = [{chave: "YYYY-MM-DD", profissionalId: number, cabecalho: html, hoje: bool}]`. Cada coluna do DOM tem `data-dia` e `data-prof`.

- [ ] **Step 1: Estado e carregamento das ausências**

Depois de `let faixaAtual = null;`:

```js
    let escalaProf = "semana";          // "semana" | "dia" (modo Por Profissional)
    let ausencias = [];                  // ocorrências da semana exibida (GET /agenda/ausencias)
    let ausenciasChave = null;           // "inicio|fim" carregado — evita refazer o GET

    // Ausências da semana de dataReferencia (domingo a sábado). Responsável não vê.
    async function carregarAusencias(forcar = false) {
        if (base === "responsavel") return;
        const ini = inicioDaSemana(dataReferencia);
        const fim = new Date(ini); fim.setDate(fim.getDate() + 6);
        const chave = `${paraChaveDia(ini)}|${paraChaveDia(fim)}`;
        if (!forcar && chave === ausenciasChave) return;
        try {
            ausencias = await Api.get(`/agenda/ausencias?inicio=${paraChaveDia(ini)}&fim=${paraChaveDia(fim)}`);
            ausenciasChave = chave;
        } catch (e) { ausencias = []; ausenciasChave = null; }
    }

    async function renderizarComAusencias() {
        await carregarAusencias();
        renderizarTudo();
    }
```

Troque `recarregarConsultas` por:

```js
    async function recarregarConsultas() {
        const [lista] = await Promise.all([Api.get("/agenda"), carregarAusencias(true)]);
        consultas = lista;
        renderizarTudo();
    }
```

No fim de `viewAgenda`, troque `renderizarTudo();` por `await renderizarComAusencias();`. Em `conectarEventos`, todo handler que muda `dataReferencia` (btn-hoje, semana anterior/próxima, mês anterior/próximo e os novos do Step 2) chama `renderizarComAusencias()` em vez de `renderizarTudo()`.

- [ ] **Step 2: Navegação Dia | Semana**

Substitua `renderNavSemana` por:

```js
    // Navegação da grade (Por Profissional, e Geral na visão Dia): passo de 1
    // dia na visão Dia, de 7 na Semana.
    function renderNavPeriodo(ehDia, comBotoesEscala) {
        let rotulo;
        if (ehDia) {
            rotulo = `${DIAS_SEMANA_ABREV[dataReferencia.getDay()]}, ${formatarData(paraChaveDia(dataReferencia))}`;
        } else {
            const inicio = inicioDaSemana(dataReferencia);
            const fim = new Date(inicio); fim.setDate(fim.getDate() + 6);
            rotulo = `${formatarData(paraChaveDia(inicio))} – ${formatarData(paraChaveDia(fim))}`;
        }
        const escala = comBotoesEscala ? `
          <button type="button" class="botao botao-sm ${ehDia ? "botao-primario" : "botao-secundario"} btn-escala-prof" data-escala="dia">Dia</button>
          <button type="button" class="botao botao-sm ${ehDia ? "botao-secundario" : "botao-primario"} btn-escala-prof" data-escala="semana">Semana</button>` : "";
        return `
        <div class="linha gap-1" style="align-items:center;">
          ${escala}
          <button type="button" class="botao-icone" id="btn-periodo-anterior" data-passo="${ehDia ? -1 : -7}" title="${ehDia ? "Dia anterior" : "Semana anterior"}">←</button>
          <button type="button" class="botao botao-sm botao-secundario" id="btn-hoje">Hoje</button>
          <button type="button" class="botao-icone" id="btn-periodo-proximo" data-passo="${ehDia ? 1 : 7}" title="${ehDia ? "Próximo dia" : "Próxima semana"}">→</button>
          <strong class="texto-sm" style="margin-left:6px; white-space:nowrap;">${rotulo}</strong>
        </div>`;
    }
```

Em `renderizarTudo`, troque `renderNavSemana()` por `renderNavPeriodo(escalaProf === "dia", true)`. Em `conectarEventos`:

```js
        document.querySelectorAll(".btn-escala-prof").forEach(btn => btn.addEventListener("click", () => {
            escalaProf = btn.dataset.escala;
            renderizarComAusencias();
        }));
        ["btn-periodo-anterior", "btn-periodo-proximo"].forEach(id => {
            const b = document.getElementById(id);
            if (b) b.addEventListener("click", () => {
                dataReferencia.setDate(dataReferencia.getDate() + parseInt(b.dataset.passo, 10));
                renderizarComAusencias();
            });
        });
```

- [ ] **Step 3: Grade genérica**

Substitua `renderVisaoPorProfissional` por duas funções — o desenhista genérico e a visão do profissional:

```js
    // Grade horária genérica (spec 07/10/2026): cada coluna é um dia de um
    // profissional (Semana/Dia "Por Profissional") ou um profissional num dia
    // (Dia do modo Geral). Posição em % da faixa — ver agenda_faixa.js.
    function renderGradeHoraria({ titulo, colunas, larga }) {
        const daGrade = consultas.filter(c => colunas.some(col => col.profissionalId === c.profissional_id && col.chave === c.data_hora.slice(0, 10)));
        const ausDaGrade = colunas.flatMap(col => ocorrenciasDaColuna(ausencias, col.profissionalId, col.chave));
        const org = Sessao.usuario.organizacao || {};
        faixaAtual = calcularFaixaAgenda(daGrade, org.agenda_hora_inicio, org.agenda_hora_fim, ausDaGrade);
        const total = faixaAtual.fim - faixaAtual.ini;
        const pct = m => ((m - faixaAtual.ini) / total) * 100;

        const linhas = [];
        for (let m = Math.ceil(faixaAtual.ini / 30) * 30; m < faixaAtual.fim; m += 30) {
            linhas.push(`<div class="agenda-linha-hora ${m % 60 ? "meia" : ""}" style="top:${pct(m)}%;"></div>`);
        }
        const rotulos = [];
        for (let m = Math.ceil(faixaAtual.ini / 60) * 60; m < faixaAtual.fim; m += 60) {
            rotulos.push(`<div class="agenda-rotulo-hora" style="top:${pct(m)}%; ${m === faixaAtual.ini ? "transform:none;" : ""}">${minutosParaHHMM(m)}</div>`);
        }

        function renderBloco(c) {
            const inicioMin = minutoDoDia(c.data_hora);
            if (inicioMin === null) return "";
            const duracao = c.duracao_min || AGENDA_DURACAO_PADRAO;
            const info = STATUS_CONSULTA_INFO[c.status] || STATUS_CONSULTA_INFO.agendada;
            const desmarcada = c.status === "cancelada";
            return `
            <div class="agenda-bloco-consulta btn-abrir-editar-consulta ${desmarcada ? "status-desmarcada" : ""}" data-id="${c.id}"
                 draggable="${podeEditarAgendaDe(c.profissional_id) ? "true" : "false"}"
                 style="top:${pct(inicioMin)}%; height:calc(${(duracao / total) * 100}% - 2px); ${desmarcada ? "" : `border-color:${info.cor};`}"
                 title="${escapeHtml(`${info.label} · ${c.paciente_nome || ""}`)}">
              <div class="agenda-bloco-hora">${info.icone}${minutosParaHHMM(inicioMin)} – ${minutosParaHHMM(inicioMin + duracao)}</div>
              <div class="agenda-bloco-nome">${escapeHtml(c.paciente_nome || "")}</div>
            </div>`;
        }

        function renderAusencia(o, idx) {
            const ini = o.dia_inteiro ? faixaAtual.ini : hhmmParaMinutos(o.hora_inicio);
            const fim = o.dia_inteiro ? faixaAtual.fim : hhmmParaMinutos(o.hora_fim);
            if (ini === null || fim === null) return "";
            return `
            <div class="agenda-bloco-ausencia btn-abrir-ausencia" data-idx="${idx}"
                 style="top:${pct(ini)}%; height:${((fim - ini) / total) * 100}%;"
                 title="${escapeHtml(`Ausente${o.motivo ? " · " + o.motivo : ""}`)}">
              ⛔ Ausente${o.motivo ? ` · ${escapeHtml(o.motivo)}` : ""}
            </div>`;
        }

        return `
        <section class="agenda-cartao-grade">
          ${titulo}
          <div class="agenda-grade-rolagem">
            <div class="agenda-grade-cab ${larga ? "agenda-grade-larga" : ""}" style="--agenda-dias:${colunas.length};">
              <div></div>
              ${colunas.map(col => `<div class="agenda-grade-dia ${col.hoje ? "hoje" : ""}">${col.cabecalho}</div>`).join("")}
            </div>
            <div class="agenda-grade-corpo ${larga ? "agenda-grade-larga" : ""}" style="--agenda-dias:${colunas.length};">
              <div class="agenda-coluna-horas">${rotulos.join("")}</div>
              ${colunas.map(col => {
                  const editavel = podeEditarAgendaDe(col.profissionalId);
                  return `
                  <div class="agenda-coluna-grade droppable-dia ${editavel ? "btn-slot-vazio editavel" : ""} ${col.hoje ? "hoje" : ""}" data-dia="${col.chave}" data-prof="${col.profissionalId}">
                    ${linhas.join("")}
                    ${ocorrenciasDaColuna(ausencias, col.profissionalId, col.chave).map(o => renderAusencia(o, ausencias.indexOf(o))).join("")}
                    ${daGrade.filter(c => c.profissional_id === col.profissionalId && c.data_hora.slice(0, 10) === col.chave).map(renderBloco).join("")}
                  </div>`;
              }).join("")}
            </div>
          </div>
          <div style="margin-top:8px;">${renderLegendaStatus()}</div>
        </section>`;
    }

    function renderVisaoPorProfissional() {
        if (!profissionaisTodos.length) {
            return `<div class="cartao estado-vazio"><p>Nenhum profissional cadastrado ainda.</p></div>`;
        }
        const profSelecionado = profissionaisTodos.find(p => p.id === profissionalSelecionadoId) || profissionaisTodos[0];
        const consultasDoProf = consultas.filter(c => c.profissional_id === profSelecionado.id);
        const dias = escalaProf === "dia" ? [new Date(dataReferencia)] : diasDaGradeSemana(inicioDaSemana(dataReferencia), consultasDoProf);
        const hojeChave = paraChaveDia(new Date());
        const editavel = podeEditarAgendaDe(profSelecionado.id);
        const titulo = `
          <div class="linha gap-2" style="align-items:baseline; flex-wrap:wrap; margin-bottom:6px;">
            <span class="agenda-ponto-cor" style="background:${corSegura(profSelecionado.cor_agenda, "var(--cor-marca)")}; width:12px; height:12px;"></span>
            <strong>${escapeHtml(profSelecionado.nome)}</strong>
            <span class="texto-xs texto-suave">${escapeHtml(profSelecionado.especialidade || "")}</span>
            <span class="texto-xs texto-suave">· ${editavel ? "clique num horário livre para agendar, ou arraste uma consulta para remarcar" : "somente visualização — só o Gestor ou quem atende pode editar esta agenda"}</span>
          </div>`;
        return renderGradeHoraria({
            titulo,
            colunas: dias.map(d => ({
                chave: paraChaveDia(d), profissionalId: profSelecionado.id, hoje: paraChaveDia(d) === hojeChave,
                cabecalho: `${DIAS_SEMANA_ABREV[d.getDay()]} <strong>${d.getDate()}</strong>`,
            })),
        });
    }
```

Atenção: `diasDaGradeSemana` recebe `consultasDoProf` só para decidir o domingo — mantenha. Na visão Dia, se a data for domingo, a coluna aparece normalmente.

- [ ] **Step 4: Eventos — clique, ausência e arrastar entre colunas**

Em `conectarEventos`, substitua o handler de `.btn-slot-vazio` e o de `drop` por:

```js
        document.querySelectorAll(".btn-abrir-ausencia").forEach(bloco => bloco.addEventListener("click", (e) => {
            e.stopPropagation();
            const o = ausencias[parseInt(bloco.dataset.idx, 10)];
            if (o) abrirModalAusencia({ ocorrencia: o }, recarregarConsultas);
        }));

        // Clique num horário livre — abre "Agendar" já preenchido (dia e profissional da coluna).
        document.querySelectorAll(".btn-slot-vazio").forEach(coluna => coluna.addEventListener("click", (e) => {
            if (e.target.closest(".agenda-bloco-consulta, .agenda-bloco-ausencia") || !faixaAtual) return;
            const profId = parseInt(coluna.dataset.prof, 10);
            if (!podeEditarAgendaDe(profId)) return;
            const rect = coluna.getBoundingClientRect();
            const minuto = minutoNaFaixa(e.clientY - rect.top, rect.height, faixaAtual);
            if (intervaloBloqueado(ausencias, profId, coluna.dataset.dia, minuto, minuto + AGENDA_PASSO_MIN)) {
                Toast.erro("Profissional ausente nesse horário."); return;
            }
            abrirModalNovaConsulta({ profissionalId: profId, data: coluna.dataset.dia, hora: minutosParaHHMM(minuto) }, recarregarConsultas);
        }));
```

e o `drop`:

```js
            coluna.addEventListener("drop", async (e) => {
                e.preventDefault();
                if (!idArrastando || !faixaAtual) return;
                const consulta = consultas.find(c => String(c.id) === String(idArrastando));
                idArrastando = null;
                if (!consulta) return;
                const rect = coluna.getBoundingClientRect();
                const minuto = minutoNaFaixa(e.clientY - rect.top, rect.height, faixaAtual);
                const hhmm = minutosParaHHMM(minuto);
                const profDestino = parseInt(coluna.dataset.prof, 10);
                const duracao = consulta.duracao_min || AGENDA_DURACAO_PADRAO;
                if (intervaloBloqueado(ausencias, profDestino, coluna.dataset.dia, minuto, minuto + duracao)) {
                    Toast.erro("Profissional ausente nesse horário."); return;
                }
                const corpo = { data_hora: `${coluna.dataset.dia} ${hhmm}:00` };
                if (profDestino !== consulta.profissional_id) corpo.profissional_id = profDestino;
                try {
                    await Api.put(`/agenda/${consulta.id}`, corpo);
                    const prof = profissionaisTodos.find(p => p.id === profDestino);
                    Toast.sucesso(`Consulta remarcada para ${formatarData(coluna.dataset.dia)} às ${hhmm}${corpo.profissional_id && prof ? ` com ${prof.nome}` : ""}.`);
                    recarregarConsultas();
                } catch (err) { Toast.erro(err.message); }
            });
```

- [ ] **Step 5: CSS** (depois de `.agenda-bloco-nome` em `components.css`)

```css
/* Agenda — ausência (spec 07/10/2026): bloco listrado atrás das consultas */
.agenda-bloco-ausencia {
    position: absolute; left: 0; right: 0; z-index: 1; overflow: hidden; padding: 2px 6px;
    font-size: 11px; font-weight: 600; color: var(--cor-tinta-suave); cursor: pointer;
    background: repeating-linear-gradient(135deg, rgba(120, 120, 130, .20) 0 6px, rgba(120, 120, 130, .08) 6px 12px);
    border-top: 1px solid rgba(120, 120, 130, .35); border-bottom: 1px solid rgba(120, 120, 130, .35);
}
.agenda-grade-rolagem { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow-x: auto; }
.agenda-grade-cab.agenda-grade-larga, .agenda-grade-corpo.agenda-grade-larga {
    grid-template-columns: 48px repeat(var(--agenda-dias, 6), minmax(140px, 1fr));
}
.agenda-grade-larga .agenda-coluna-horas, .agenda-grade-cab.agenda-grade-larga > div:first-child {
    position: sticky; left: 0; z-index: 4; background: var(--cor-superficie);
}
```

Confira se `.agenda-cartao-grade` precisa de `min-width: 0` para a rolagem funcionar dentro do flex; acrescente se a grade larga empurrar a página para o lado.

- [ ] **Step 6: Verify in the browser**

Com o almoço da Task 8 lançado: modo Por Profissional da Camila → bloco listrado 12–13h de seg a sex; clicar no bloco abre a edição da ausência (não o "Agendar"); arrastar uma consulta para 12:15 → toast de ausente e nada muda; "Dia" → uma coluna larga; setas andam 1 dia; "Hoje" volta.

- [ ] **Step 7: Run front tests and commit**

Run: `node --test frontend/tests/*.test.js` — Expected: todos passam.

```bash
git add frontend/js/views/agenda.js frontend/css/components.css
git commit -m "Agenda: ausências na grade e visão Dia por profissional"
```

---

### Task 10: Visão Dia do modo Geral (todos os profissionais lado a lado)

**Files:**
- Modify: `frontend/js/views/agenda.js` (`renderBotoesVisao`, `renderListaProfissionais`, `renderizarTudo`, `conectarEventos`)

**Interfaces:**
- Consumes: `renderGradeHoraria`, `renderNavPeriodo`, `carregarAusencias` (Task 9).
- Produces: `visaoAtual` aceita `"dia"`; estado `profsOcultosDia` (`Set` de ids).

- [ ] **Step 1: Implement**

Estado (junto dos outros `let`): `const profsOcultosDia = new Set();`

`renderBotoesVisao`: `const opcoes = [["dia", "🕘 Dia"], ["lista", "📋 Lista"], ["semana", "🗓️ Semana"], ["mes", "📆 Mês"]];`

Profissionais que o usuário enxerga na visão Dia:

```js
    function profissionaisVisiveisNoDia() {
        const daAgenda = (u.papel === "profissional" && !u.agenda_permissao_total)
            ? profissionaisTodos.filter(p => p.id === u.id)
            : profissionaisTodos;
        return daAgenda.filter(p => !profsOcultosDia.has(p.id));
    }

    function renderVisaoDiaGeral() {
        const lista = profissionaisVisiveisNoDia();
        if (!lista.length) return `<div class="cartao estado-vazio"><p>Nenhum profissional selecionado — escolha na lista ao lado.</p></div>`;
        const chave = paraChaveDia(dataReferencia);
        const hoje = chave === paraChaveDia(new Date());
        return renderGradeHoraria({
            titulo: `<p class="texto-xs texto-suave" style="margin-bottom:6px;">Clique num horário livre para agendar, ou arraste uma consulta para outro horário ou profissional.</p>`,
            larga: true,
            colunas: lista.map(p => ({
                chave, profissionalId: p.id, hoje,
                cabecalho: `<span class="agenda-ponto-cor" style="background:${corSegura(p.cor_agenda, "var(--cor-marca)")};"></span> <strong>${escapeHtml((p.nome || "").split(" ")[0])}</strong><br><span class="texto-xs texto-suave">${escapeHtml(p.especialidade || "")}</span>`,
            })),
        });
    }
```

`renderListaProfissionais`: no modo Geral com `visaoAtual === "dia"`, o item fica ativo quando visível e o "Todos" fica ativo quando nada está oculto:

```js
        const ehDiaGeral = modoVisao === "geral" && visaoAtual === "dia";
        const itemTodos = modoVisao === "geral" ? `
          <li><button type="button" class="agenda-item-prof ${!ehDiaGeral || !profsOcultosDia.size ? "ativo" : ""}" data-todos="1">
          ...` : "";
```

e, no `map`, `const ativo = ehDiaGeral ? !profsOcultosDia.has(p.id) : (modoVisao === "porProfissional" && p.id === profissionalSelecionadoId);`. Acrescente `title="${ehDiaGeral ? "Mostrar/esconder a coluna" : ""}"` no botão.

`renderizarTudo`, no ramo do modo Geral:

```js
                : `<div style="margin-bottom:12px;">${visaoAtual !== "lista" && visaoAtual !== "dia" ? renderLegendaProfissionais() : ""}</div>`
                  + (visaoAtual === "dia" ? renderVisaoDiaGeral() : visaoAtual === "lista" ? renderListaView() : visaoAtual === "semana" ? renderSemanaView() : renderMesView());
```

e nas ações: `+ (modoVisao === "porProfissional" ? renderNavPeriodo(escalaProf === "dia", true) : renderBotoesVisao() + (visaoAtual === "dia" ? renderNavPeriodo(true, false) : ""))`.

`conectarEventos` — clique na lista lateral:

```js
        document.querySelectorAll(".btn-selecionar-profissional").forEach(btn => btn.addEventListener("click", () => {
            const id = parseInt(btn.dataset.id, 10);
            if (modoVisao === "geral" && visaoAtual === "dia") {
                if (profsOcultosDia.has(id)) profsOcultosDia.delete(id); else profsOcultosDia.add(id);
                renderizarTudo();
                return;
            }
            profissionalSelecionadoId = id;
            modoVisao = "porProfissional"; // nas outras visões do modo Geral, abre a agenda dele
            renderizarComAusencias();
        }));
        const btnTodos = document.querySelector(".agenda-item-prof[data-todos]");
        if (btnTodos) btnTodos.addEventListener("click", () => {
            if (modoVisao === "geral" && visaoAtual === "dia") { profsOcultosDia.clear(); renderizarTudo(); }
        });
```

O handler de `.btn-visao-agenda` passa a chamar `renderizarComAusencias()`.

- [ ] **Step 2: Verify in the browser**

Como gestor: "Geral da Clínica" → "Dia" → uma coluna por profissional (Camila, Rafael, Juliana…), cada uma com suas consultas e ausências; clicar num nome na lista esconde/mostra a coluna; "Todos" mostra todas; clicar num horário livre da coluna do Rafael abre "Agendar" com Rafael e a hora; arrastar uma consulta da Camila para a coluna do Rafael troca o profissional (toast "… com Rafael …"); arrastar para a Camila no almoço → toast de ausente. Reduza a janela para ~900 px: as colunas rolam para o lado e a coluna de horas fica parada. Como Camila (sem permissão total): Geral → Dia mostra só a coluna dela.

- [ ] **Step 3: Run front tests and commit**

Run: `node --test frontend/tests/*.test.js` — Expected: todos passam.

```bash
git add frontend/js/views/agenda.js
git commit -m "Agenda: visão Dia do modo Geral, um profissional por coluna"
```

---

### Task 11: Fechamento — suíte completa, CLAUDE.md, fumaça e PR

**Files:**
- Modify: `CLAUDE.md` (seção 5 item novo `y)`, seção 7 e tabela da seção 8)

- [ ] **Step 1: Suítes completas**

Run: `cd backend && PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q` e `node --test frontend/tests/*.test.js` (na raiz).
Expected: tudo passa; anote os totais.

- [ ] **Step 2: Fumaça com Playwright** (servidor local com banco recriado pelo `seed.py`)

Roteiro único: gestor → Configurações → duração padrão 45 → Agenda → "+ Agendar" (Fim = início + 45) → lançar almoço da Camila seg–sex → grade da Camila mostra o bloco → tentar agendar por cima (409, toast) → série semanal de 3 cruzando férias de uma semana (toast com a data pulada) → Geral → Dia com colunas. Apague a pasta `.playwright-mcp/` no fim (não versionar).

- [ ] **Step 3: CLAUDE.md**

Seção 5, item `y) Agenda: hora de fim, Ausência e visão Dia (07/10/2026)` resumindo: tabela `ausencias_profissional` (regra com período/horário/dias), bloqueio 409 nas rotas de consulta, `datas_puladas` na série, `consultas_no_periodo` ao lançar ausência, `agenda_duracao_padrao` (5–240, Configurações), `duracao_min` validada (5–480), visão Dia (Por Profissional = 1 coluna; Geral = um profissional por coluna, lista lateral como filtro), arquivos novos (`ausencias_service.py`, `agenda_ausencias.js`, `views/agenda_ausencia_modal.js`), migração (`migracoes/migracao_ausencias_agenda.sql` ou `migrar_ausencias_agenda.py`) e os totais de testes. Seção 7: marcar a parte (2) como feita e lembrar a migração pendente em produção. Seção 8: linhas para ausências (backend e front).

- [ ] **Step 4: Commit, push e PR**

```bash
git add CLAUDE.md
git commit -m "CLAUDE.md: agenda com Ausência, hora de fim e visão Dia"
git push -u origin agenda-ausencia-fim-dia
"/c/Program Files/GitHub CLI/gh.exe" pr create --base main --title "Agenda: hora de fim, Ausência e visão Dia" --body "<resumo + testes + passo manual da migração + 🤖 Generated with [Claude Code](https://claude.com/claude-code)>"
```

Este PR tem **mudança de schema**: não usar o merge automático — esperar o CI (`gh pr checks`) e **perguntar ao usuário** antes de mesclar, avisando que a migração precisa rodar no Supabase antes do `git pull` em produção.
