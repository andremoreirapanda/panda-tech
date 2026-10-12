"""O produto se chama PandaUp em tudo o que o usuário vê (spec 12/10/2026, item A).

Comentários, docstrings, nomes de arquivo e variáveis não mudam; só os textos
(strings) do backend que podem chegar a uma tela, a um e-mail ou ao PDF."""
import ast
from pathlib import Path

import identidade_service as ids

BACKEND = Path(__file__).resolve().parent.parent


def _arquivos():
    for p in BACKEND.rglob("*.py"):
        rel = p.relative_to(BACKEND).as_posix()
        if rel.startswith(("tests/", "tests_postgres/", "venv/")) or p.name.startswith(("seed", "migrar_")):
            continue
        yield p


def _docstrings(arvore):
    ids_doc = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and no.body:
            primeiro = no.body[0]
            if isinstance(primeiro, ast.Expr) and isinstance(primeiro.value, ast.Constant):
                ids_doc.add(id(primeiro.value))
    return ids_doc


def test_nenhum_texto_do_backend_diz_panda_tech():
    achados = []
    for p in _arquivos():
        arvore = ast.parse(p.read_text(encoding="utf-8"))
        docs = _docstrings(arvore)
        for no in ast.walk(arvore):
            if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in docs:
                if "Panda Tech" in no.value:
                    achados.append(f"{p.relative_to(BACKEND).as_posix()}:{no.lineno}")
    assert achados == []


def test_nome_padrao_do_app_e_pandaup_e_o_da_clinica_continua():
    org = {"nome": "Clínica Sol", "app_nome": None}
    assert ids.identidade_efetiva(dict(org), True)["app_nome"] == "PandaUp"
    assert ids.identidade_efetiva(dict(org, app_nome="Clínica Sol"), True)["app_nome"] == "Clínica Sol"


def test_health_diz_pandaup(client):
    assert client.get("/api/health").get_json()["produto"] == "PandaUp"
