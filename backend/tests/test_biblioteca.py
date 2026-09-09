"""
Regressão pro Domínio 3 — Biblioteca Terapêutica (biblioteca_bp.py), que até
09/09/2026 não tinha nenhum teste automatizado próprio. Cobre o isolamento
multi-tenant (Biblioteca da Clínica x Biblioteca da Plataforma), CRUD de
exercícios, e o arquivamento — em especial o achado do usuário de que
"Arquivar" escondia o exercício pra sempre, sem nenhuma tela pra revê-lo
(a listagem nunca pedia os inativos, embora o backend já suportasse
incluir_inativos=1).
"""
from factories import DuasClinicas, novo_exercicio

from conftest import autenticado


def test_listagem_traz_biblioteca_da_clinica_mais_a_da_plataforma(client, db_ctx):
    cen = DuasClinicas()
    ex_a = novo_exercicio(cen.org_a, "Exercício da Clínica A")
    ex_b = novo_exercicio(cen.org_b, "Exercício da Clínica B")
    ex_plataforma = novo_exercicio(None, "Exercício da Plataforma")

    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/exercicios")
    assert r.status_code == 200
    ids = {e["id"] for e in r.get_json()}
    assert ex_a["id"] in ids
    assert ex_plataforma["id"] in ids
    assert ex_b["id"] not in ids  # isolamento entre clínicas


def test_admin_master_so_ve_biblioteca_da_plataforma(client, db_ctx):
    from factories import novo_usuario
    admin = novo_usuario(None, "Admin", "admin.biblioteca@plataforma.com", "admin_master")
    cen = DuasClinicas()
    ex_a = novo_exercicio(cen.org_a, "Exercício da Clínica A")
    ex_plataforma = novo_exercicio(None, "Exercício da Plataforma")

    r = autenticado(client, admin).get("/api/biblioteca/exercicios?apenas_plataforma=1")
    assert r.status_code == 200
    ids = {e["id"] for e in r.get_json()}
    assert ex_plataforma["id"] in ids
    assert ex_a["id"] not in ids


def test_gestor_cria_exercicio_na_biblioteca_da_propria_clinica(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/exercicios", json={
        "titulo": "Novo exercício", "tipo": "video", "conteudo_url": "https://youtube.com/watch?v=abc",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    ex_id = r.get_json()["id"]

    r = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{ex_id}")
    assert r.status_code == 200
    assert r.get_json()["organizacao_id"] == cen.org_a


def test_gestor_nao_edita_exercicio_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    ex_b = novo_exercicio(cen.org_b, "Exercício da Clínica B")
    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex_b['id']}", json={"titulo": "Hackeado"})
    assert r.status_code == 403, r.get_data(as_text=True)


def test_gestor_nao_edita_biblioteca_da_plataforma(client, db_ctx):
    cen = DuasClinicas()
    ex_plataforma = novo_exercicio(None, "Exercício da Plataforma")
    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex_plataforma['id']}", json={"titulo": "Hackeado"})
    assert r.status_code == 403, r.get_data(as_text=True)


def test_listagem_esconde_arquivados_por_padrao(client, db_ctx):
    cen = DuasClinicas()
    ex = novo_exercicio(cen.org_a, "Exercício Arquivado", ativo=0)

    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/exercicios")
    ids = {e["id"] for e in r.get_json()}
    assert ex["id"] not in ids


def test_incluir_inativos_traz_ativos_e_arquivados_juntos(client, db_ctx):
    """Achado do usuário (09/09/2026): o parâmetro já existia no backend, mas
    nenhuma tela pedia — sem isso, um exercício arquivado ficava invisível
    pra sempre, mesmo sem ter sido de fato excluído."""
    cen = DuasClinicas()
    ex_ativo = novo_exercicio(cen.org_a, "Exercício Ativo")
    ex_arquivado = novo_exercicio(cen.org_a, "Exercício Arquivado", ativo=0)

    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/exercicios?incluir_inativos=1")
    assert r.status_code == 200
    por_id = {e["id"]: e for e in r.get_json()}
    assert por_id[ex_ativo["id"]]["ativo"] == 1
    assert por_id[ex_arquivado["id"]]["ativo"] == 0


def test_arquivar_e_reativar_exercicio(client, db_ctx):
    cen = DuasClinicas()
    ex = novo_exercicio(cen.org_a, "Exercício")

    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex['id']}/arquivar")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["ativo"] is False

    # Some da listagem padrão...
    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/exercicios")
    assert ex["id"] not in {e["id"] for e in r.get_json()}

    # ...mas continua acessível diretamente por ID (missões que já o usam
    # continuam funcionando, como o próprio texto de confirmação do botão diz).
    r = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{ex['id']}")
    assert r.status_code == 200

    # E dá pra reativar.
    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex['id']}/arquivar")
    assert r.status_code == 200
    assert r.get_json()["ativo"] is True
    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/exercicios")
    assert ex["id"] in {e["id"] for e in r.get_json()}


def test_gestor_nao_arquiva_exercicio_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    ex_b = novo_exercicio(cen.org_b, "Exercício da Clínica B")
    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex_b['id']}/arquivar")
    assert r.status_code == 403, r.get_data(as_text=True)


def test_duplicar_exercicio_da_plataforma_para_a_clinica(client, db_ctx):
    cen = DuasClinicas()
    ex_plataforma = novo_exercicio(None, "Exercício da Plataforma", tipo="pdf", conteudo_url="https://exemplo.com/a.pdf")
    r = autenticado(client, cen.gestor_a).post(f"/api/biblioteca/exercicios/{ex_plataforma['id']}/duplicar")
    assert r.status_code == 201, r.get_data(as_text=True)
    novo_id = r.get_json()["id"]

    r = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{novo_id}")
    dados = r.get_json()
    assert dados["organizacao_id"] == cen.org_a
    assert dados["titulo"] == "Exercício da Plataforma (cópia)"
