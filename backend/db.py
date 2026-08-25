"""
Camada de acesso ao banco de dados.

Funciona com dois backends, escolhidos automaticamente pela variável de
ambiente DATABASE_URL:

  - **Sem DATABASE_URL** (padrão local/desenvolvimento): SQLite, arquivo único
    `encanto.db`, exatamente como antes desta rodada.
  - **Com DATABASE_URL** (produção/piloto): PostgreSQL (ex: Supabase),
    conexão via psycopg2.

Todo o resto do backend (blueprints, serviços) continua chamando só
`query()`, `query_one()` e `execute()` com placeholders `?` — a tradução
para o dialeto certo (`?` → `%s`, `cursor.lastrowid` → `RETURNING id`)
acontece só aqui, então nenhum outro arquivo precisa saber qual banco está
rodando por baixo.
"""
import json
import os
import re
import sqlite3
from datetime import datetime as _datetime, timezone as _timezone

from flask import g, has_app_context

from crypto_utils import cifrar, decifrar

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "encanto.db")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USANDO_POSTGRES = bool(DATABASE_URL)

# Tabelas cuja chave primária não se chama "id" (ou não é gerada pelo banco) —
# para essas, não faz sentido pedir `RETURNING id` no Postgres.
_TABELAS_SEM_ID_AUTO = {"gamificacao_paciente"}

_RE_INSERT_TABELA = re.compile(r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)

_standalone_conn = None  # usada por scripts (seed.py, migrar_postgres.py) fora do contexto Flask

if USANDO_POSTGRES:
    import psycopg2
    import psycopg2.extras


def dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}


def _nova_conexao_sqlite():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _nova_conexao_postgres():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def get_db():
    global _standalone_conn
    if not has_app_context():
        # Permite que db.py seja usado por scripts utilitários (ex: seed.py)
        if _standalone_conn is None:
            _standalone_conn = _nova_conexao_postgres() if USANDO_POSTGRES else _nova_conexao_sqlite()
        return _standalone_conn
    if "db" not in g:
        g.db = _nova_conexao_postgres() if USANDO_POSTGRES else _nova_conexao_sqlite()
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def _preparar_sql(sql):
    """Traduz placeholders `?` (estilo SQLite) para `%s` (estilo psycopg2).
    Sem efeito nenhum quando rodando em SQLite."""
    if not USANDO_POSTGRES:
        return sql
    return sql.replace("?", "%s")


def query(sql, params=()):
    db = get_db()
    cur = db.cursor()
    cur.execute(_preparar_sql(sql), params)
    rows = cur.fetchall()
    if USANDO_POSTGRES:
        rows = [dict(r) for r in rows]
        cur.close()
    return rows


def query_one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    """INSERT/UPDATE/DELETE — retorna o id da linha inserida (quando aplicável) e faz commit."""
    db = get_db()

    if not USANDO_POSTGRES:
        cur = db.execute(sql, params)
        db.commit()
        return cur.lastrowid

    sql_preparado = _preparar_sql(sql)
    eh_insert = sql.lstrip()[:6].upper() == "INSERT"
    tabela_match = _RE_INSERT_TABELA.search(sql) if eh_insert else None
    tabela = tabela_match.group(1) if tabela_match else None
    deve_retornar_id = (
        eh_insert
        and tabela
        and tabela not in _TABELAS_SEM_ID_AUTO
        and "returning" not in sql.lower()
    )
    if deve_retornar_id:
        sql_preparado = sql_preparado.rstrip().rstrip(";") + " RETURNING id"

    cur = db.cursor()
    cur.execute(sql_preparado, params)
    novo_id = None
    if deve_retornar_id:
        linha = cur.fetchone()
        novo_id = linha["id"] if linha else None
    db.commit()
    cur.close()
    return novo_id


def agora_sql() -> str:
    """Timestamp atual em UTC, no formato `YYYY-MM-DD HH:MM:SS` — mesmo
    formato que o `datetime('now')` do SQLite produzia. Usado para popular
    colunas de data/hora a partir do Python (portável entre SQLite e
    Postgres) em vez de depender de uma função específica de cada banco."""
    return _datetime.now(_timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def hoje_sql() -> str:
    """Data atual em UTC no formato `YYYY-MM-DD` — equivalente ao antigo
    `date('now')` do SQLite."""
    return _datetime.now(_timezone.utc).strftime("%Y-%m-%d")


def log_evento(organizacao_id, tipo, entidade, entidade_id, paciente_id=None, payload=None):
    """
    Publica um evento na tabela `eventos`.

    Implementa o princípio do Documento 08: 'Plataforma orientada por eventos'.
    Ex: missao concluída → evento → gamificação → indicadores → notificação.
    """
    execute(
        """INSERT INTO eventos (organizacao_id, tipo, entidade, entidade_id, paciente_id, payload_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (organizacao_id, tipo, entidade, entidade_id, paciente_id, json.dumps(payload or {})),
    )


def log_auditoria(organizacao_id, usuario_id, acao, entidade, entidade_id, detalhes=""):
    """'Quem alterou, quando, o que mudou' — Documento 07, Core > Auditoria."""
    execute(
        """INSERT INTO auditoria (organizacao_id, usuario_id, acao, entidade, entidade_id, detalhes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (organizacao_id, usuario_id, acao, entidade, entidade_id, detalhes),
    )


def criar_notificacao(usuario_id, titulo, mensagem, tipo="info", entidade=None, entidade_id=None):
    """Notificação do sininho para um usuário (Core > Notificações, Doc 07).

    `entidade`/`entidade_id` (agosto/2026) identificam do que a notificação
    trata — hoje 'paciente' (para missao/conquista/diario/mensagem, todas
    escopadas a um paciente) ou 'assinatura' (financeiro) — usados só pelo
    frontend, pra levar o clique no sininho direto pra tela certa em vez de
    só abrir o painel. Central única: todo INSERT em `notificacoes` deveria
    passar por aqui, em vez de montar o SQL na mão em cada blueprint/service."""
    execute(
        "INSERT INTO notificacoes (usuario_id, titulo, mensagem, tipo, entidade, entidade_id) VALUES (?, ?, ?, ?, ?, ?)",
        (usuario_id, titulo, mensagem, tipo, entidade, entidade_id),
    )


# ------------------------- Config de integrações (cifrada) -------------------------
#
# `integracoes.configuracao_json` guarda credenciais sensíveis (refresh token
# do Google, access token do Mercado Pago, token do WhatsApp Cloud API) —
# sempre cifradas em repouso via crypto_utils (ver ENCANTO_CRYPTO_KEY).

def obter_config_integracao(organizacao_id, tipo) -> dict:
    row = query_one(
        "SELECT configuracao_json FROM integracoes WHERE organizacao_id = ? AND tipo = ?",
        (organizacao_id, tipo),
    )
    if not row or not row.get("configuracao_json"):
        return {}
    texto = decifrar(row["configuracao_json"])
    if not texto:
        return {}
    try:
        return json.loads(texto)
    except ValueError:
        return {}


def salvar_config_integracao(organizacao_id, tipo, config: dict, status: str = None):
    """Faz upsert da configuração cifrada. Se `status` for informado, também
    atualiza o estado conectado/desconectado (ex: após OAuth bem-sucedido)."""
    existente = query_one(
        "SELECT id FROM integracoes WHERE organizacao_id = ? AND tipo = ?",
        (organizacao_id, tipo),
    )
    texto_cifrado = cifrar(json.dumps(config))
    if existente:
        if status:
            execute(
                "UPDATE integracoes SET configuracao_json = ?, status = ? WHERE id = ?",
                (texto_cifrado, status, existente["id"]),
            )
        else:
            execute(
                "UPDATE integracoes SET configuracao_json = ? WHERE id = ?",
                (texto_cifrado, existente["id"]),
            )
    else:
        execute(
            "INSERT INTO integracoes (organizacao_id, tipo, status, configuracao_json) VALUES (?, ?, ?, ?)",
            (organizacao_id, tipo, status or "desconectado", texto_cifrado),
        )


# ------------------- Config de integrações da PLATAFORMA (Panda Tech) -------------------
#
# Igual à seção acima, mas para as credenciais da própria Panda Tech (não de
# uma clínica) — ex: o Mercado Pago que cobra as clínicas pelo plano
# (`pagamento_plataforma_service.py`). Tabela própria (`integracoes_plataforma`,
# sem organizacao_id) porque não faz sentido amarrar isso a uma clínica.

def obter_config_integracao_plataforma(tipo) -> dict:
    row = query_one("SELECT configuracao_json FROM integracoes_plataforma WHERE tipo = ?", (tipo,))
    if not row or not row.get("configuracao_json"):
        return {}
    texto = decifrar(row["configuracao_json"])
    if not texto:
        return {}
    try:
        return json.loads(texto)
    except ValueError:
        return {}


def salvar_config_integracao_plataforma(tipo, config: dict, status: str = None):
    existente = query_one("SELECT id FROM integracoes_plataforma WHERE tipo = ?", (tipo,))
    texto_cifrado = cifrar(json.dumps(config))
    if existente:
        if status:
            execute(
                "UPDATE integracoes_plataforma SET configuracao_json = ?, status = ? WHERE id = ?",
                (texto_cifrado, status, existente["id"]),
            )
        else:
            execute(
                "UPDATE integracoes_plataforma SET configuracao_json = ? WHERE id = ?",
                (texto_cifrado, existente["id"]),
            )
    else:
        execute(
            "INSERT INTO integracoes_plataforma (tipo, status, configuracao_json) VALUES (?, ?, ?)",
            (tipo, status or "desconectado", texto_cifrado),
        )
