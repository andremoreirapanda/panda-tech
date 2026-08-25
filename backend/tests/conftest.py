"""
Configuração compartilhada da suíte de testes (pytest).

Cada teste que usa o fixture `flask_app` ganha um banco SQLite novo e vazio
(criado a partir de schema.sql, num arquivo temporário) e uma instância Flask
nova — testes não compartilham estado entre si, então a ordem de execução
não importa e um teste não pode "vazar" dados para o próximo.

Por que isso existe (contexto): esta suíte nasceu da auditoria de segurança
de 25/08/2026, que encontrou 6 falhas de vazamento de dados entre clínicas
(IDOR) através de revisão manual de código. Sem uma suíte automatizada, uma
regressão futura em qualquer uma dessas rotas só seria descoberta na próxima
auditoria manual — o objetivo desta suíte é detectar isso automaticamente,
a cada commit (ver .github/workflows/tests.yml).
"""
import os
import sqlite3
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Precisam existir ANTES de importar auth.py/crypto_utils.py (eles leem a
# env var no import do módulo e falham "fail-hard" se não estiver definida —
# ver auth.py e crypto_utils.py). Os valores aqui são só para teste.
os.environ.setdefault("ENCANTO_SECRET", "chave-de-teste-nao-usar-em-producao")
os.environ.setdefault("ENCANTO_CRYPTO_KEY", "tXk_jawA-xaVDvpOfgcrao05C3ZQ-lsDr2gmQQ9Eq-k=")
os.environ.pop("FLASK_DEBUG", None)
os.environ.pop("DATABASE_URL", None)  # garante SQLite, nunca Postgres, nos testes

import app as app_module  # noqa: E402
import auth  # noqa: E402
import db as db_module  # noqa: E402
import rate_limit  # noqa: E402


@pytest.fixture(autouse=True)
def _rate_limit_isolado():
    """O limitador de tentativas (rate_limit.py) guarda seu estado num dict em
    memória, no nível do módulo — sem isso, chamadas de um teste anterior às
    MESMAS rotas contariam para o limite deste teste, e a suíte ficaria
    dependente da ordem de execução. Reseta antes de cada teste."""
    rate_limit._tentativas.clear()
    rate_limit._ULTIMA_LIMPEZA[0] = 0.0
    yield


@pytest.fixture()
def flask_app(tmp_path):
    """Flask app com um banco SQLite novo (schema aplicado, sem dados)."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(open(os.path.join(BACKEND_DIR, "schema.sql")).read())
    conn.commit()
    conn.close()

    db_module.DB_PATH = str(db_path)
    db_module._standalone_conn = None  # descarta qualquer conexão reaproveitada de outro teste

    application = app_module.create_app()
    application.testing = True
    return application


@pytest.fixture()
def db_ctx(flask_app):
    """Contexto de aplicação Flask ativo — necessário pra chamar db.query/execute
    diretamente (fora de uma requisição HTTP), por ex. pra popular dados de teste."""
    with flask_app.app_context():
        yield db_module


@pytest.fixture()
def client(flask_app):
    return flask_app.test_client()


def token_de(usuario):
    """Gera um JWT válido para o dict de usuário informado, sem passar pelo
    endpoint de login — mais rápido e mais direto para preparar cenários de teste."""
    return auth.gerar_token(usuario)


def autenticado(client, usuario):
    """Devolve o mesmo test_client, mas com o header Authorization já configurado
    para o usuário informado."""
    client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token_de(usuario)}"
    return client
