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
