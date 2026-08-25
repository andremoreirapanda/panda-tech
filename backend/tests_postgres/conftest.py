"""
Configuração da suíte de smoke test que roda contra Postgres REAL — não o
SQLite usado pelo resto da suíte em `tests/`.

Por que existe (contexto): toda a suíte em `tests/` roda contra SQLite (ver
`tests/conftest.py`, que inclusive remove DATABASE_URL do ambiente de
propósito, pra garantir isso). Isso é ótimo pra velocidade e isolamento, mas
significa que a suíte inteira nunca detectaria uma diferença de dialeto SQL
entre SQLite e o Postgres real usado em produção (`db.py` traduz `?` -> `%s`
e usa `RETURNING id` só no Postgres — ver `db.py::_preparar_sql`/`execute`).
Este diretório é separado de `tests/` de propósito, pra nunca rodar por
engano dentro do `pytest` padrão (que usa `testpaths = tests`, ver
`pytest.ini`) — só roda quando alguém invoca `pytest tests_postgres`
explicitamente, com DATABASE_URL já apontando pra um Postgres com o schema
aplicado (ver o cabeçalho de test_smoke_fluxo_principal.py para como rodar
localmente, e `.github/workflows/tests.yml`, job "smoke-postgres", para
como isso roda no CI, contra um Postgres efêmero — nunca o Supabase real).

IMPORTANTE: `db.py` decide SQLite vs Postgres (`db.USANDO_POSTGRES`) uma
única vez, na primeira vez que o módulo é importado, olhando a env var
DATABASE_URL naquele instante — por isso esta suíte SEMPRE precisa rodar num
processo `pytest` separado da suíte em SQLite (nunca no mesmo processo),
mesmo quando pulada (ver `pytestmark` abaixo): os imports de app/db/auth
acontecem incondicionalmente para a coleta de testes nunca quebrar com
ImportError quando DATABASE_URL não está definida — só a EXECUÇÃO dos
testes é pulada nesse caso.
"""
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("ENCANTO_SECRET", "chave-de-teste-ci-nao-usar-em-producao")
os.environ.setdefault("ENCANTO_CRYPTO_KEY", "tXk_jawA-xaVDvpOfgcrao05C3ZQ-lsDr2gmQQ9Eq-k=")
os.environ.pop("FLASK_DEBUG", None)

_TEM_DATABASE_URL = bool(os.environ.get("DATABASE_URL"))

# Pula a suíte inteira com uma mensagem clara em vez de deixar cada teste
# quebrar com um erro de conexão confuso (ex: rodar `pytest tests_postgres`
# sem querer numa máquina sem Postgres disponível).
#
# IMPORTANTE: `pytestmark` só é respeitado pelo pytest quando definido DENTRO
# de um módulo de teste (ver docs do pytest) -- defini-lo aqui em
# conftest.py não pula nada sozinho (ficou comprovado na prática: sem isso
# exportado e aplicado em cada arquivo de teste, os testes rodavam mesmo sem
# DATABASE_URL, contra o SQLite padrão de db.py, e quebravam com um erro
# confuso de "no such table"). Por isso é exportado aqui e cada módulo de
# teste precisa fazer `pytestmark = REQUER_POSTGRES` explicitamente.
REQUER_POSTGRES = pytest.mark.skipif(
    not _TEM_DATABASE_URL,
    reason=(
        "Suíte de smoke test contra Postgres real -- defina DATABASE_URL "
        "apontando para um Postgres (efêmero, com schema_postgres.sql + "
        "migracao_integracoes_plataforma.sql já aplicados) para rodar. "
        "Ver o cabeçalho de test_smoke_fluxo_principal.py."
    ),
)

# Importados incondicionalmente (mesmo sem DATABASE_URL) para a COLETA dos
# testes nunca falhar com ImportError -- só a execução é pulada, via
# pytestmark acima. Sem DATABASE_URL, db.py simplesmente inicializa em modo
# SQLite (comportamento padrão do módulo); como os testes nunca chegam a
# rodar, isso não importa na prática.
import app as app_module  # noqa: E402
import auth  # noqa: E402
import db as db_module  # noqa: E402
import rate_limit  # noqa: E402

if _TEM_DATABASE_URL:
    assert db_module.USANDO_POSTGRES, (
        "DATABASE_URL está definida mas db.USANDO_POSTGRES ficou False -- "
        "db.py só decide isso na primeira importação do módulo (ver seu "
        "cabeçalho). Alguma coisa neste processo importou db.py antes desta "
        "env var estar definida -- confira a ordem no workflow do CI."
    )


@pytest.fixture(autouse=True)
def _rate_limit_isolado():
    """Mesmo motivo do fixture homônimo em tests/conftest.py: o limitador de
    tentativas guarda estado num dict em memória, no nível do módulo."""
    rate_limit._tentativas.clear()
    rate_limit._ULTIMA_LIMPEZA[0] = 0.0
    yield


@pytest.fixture()
def flask_app():
    """Ao contrário de tests/conftest.py, NÃO criamos um banco novo por teste
    (Postgres não é um arquivo) -- todos os testes desta suíte compartilham
    o mesmo banco efêmero da execução do CI. Isso é aceitável aqui porque
    cada teste cria sua própria clínica/paciente do zero (não há dado
    pré-existente pra colidir)."""
    application = app_module.create_app()
    application.testing = True
    return application


@pytest.fixture()
def db_ctx(flask_app):
    with flask_app.app_context():
        yield db_module


@pytest.fixture()
def client(flask_app):
    return flask_app.test_client()


def token_de(usuario):
    return auth.gerar_token(usuario)


def autenticado(client, usuario):
    client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token_de(usuario)}"
    return client
