"""Cadastro de procedimentos (spec 09/10/2026, parte A)."""
import pytest

import procedimentos_service as ps
from factories import DuasClinicas, novo_usuario
from conftest import autenticado


@pytest.mark.parametrize("entrada,esperado", [
    ("230,00", 23000), ("1.230,50", 123050), (230.5, 23050), (230, 23000), ("R$ 15", 1500), ("0", 0),
    ("-1", None), ("abc", None), ("", None), (None, None), (100000.01, None), ("100.000,00", 10000000), (True, None),
])
def test_reais_para_centavos(entrada, esperado):
    assert ps.reais_para_centavos(entrada) == esperado


LISTA = [{"codigo": "", "nome": "Sessão Divinópolis", "valor": "230,00", "ativo": True},
         {"codigo": "AV", "nome": "Avaliação", "valor": "260,00", "ativo": True},
         {"codigo": "", "nome": "Sessão Equipe", "valor": "205,00", "ativo": True}]


def _salvar(client, quem, itens):
    return autenticado(client, quem).put("/api/procedimentos", json={"procedimentos": itens})


def _lista_gestor(client, cen):
    return autenticado(client, cen.gestor_a).get("/api/procedimentos").get_json()


def test_gestor_cria_e_ve_valores(client, db_ctx):
    cen = DuasClinicas()
    r = _salvar(client, cen.gestor_a, LISTA)
    assert r.status_code == 200, r.get_data(as_text=True)
    lista = _lista_gestor(client, cen)
    assert [(p["nome"], p["valor_centavos"], p["codigo"], p["ativo"], p["em_uso"]) for p in lista] == [
        ("Sessão Divinópolis", 23000, None, 1, 0), ("Avaliação", 26000, "AV", 1, 0), ("Sessão Equipe", 20500, None, 1, 0)]
    assert db_ctx.query_one("SELECT 1 FROM auditoria WHERE entidade = 'procedimentos'")


def test_profissional_e_secretaria_veem_so_ativos_sem_valor(client, db_ctx):
    cen = DuasClinicas()
    _salvar(client, cen.gestor_a, [*LISTA[:2], {**LISTA[2], "ativo": False}])
    sec = novo_usuario(cen.org_a, "Sec", "sec@a.com", "secretaria")
    for quem in (cen.prof_a1, sec):
        lista = autenticado(client, quem).get("/api/procedimentos").get_json()
        assert [p["nome"] for p in lista] == ["Sessão Divinópolis", "Avaliação"]
        assert all("valor_centavos" not in p and "em_uso" not in p for p in lista)
    assert autenticado(client, cen.resp_a1).get("/api/procedimentos").status_code == 403
    for quem in (cen.prof_a1, sec):
        assert _salvar(client, quem, LISTA).status_code == 403


def test_editar_reordenar_e_desativar(client, db_ctx):
    cen = DuasClinicas()
    _salvar(client, cen.gestor_a, LISTA)
    atual = _lista_gestor(client, cen)
    novos = [{"id": atual[2]["id"], "nome": "Sessão Equipe 2X", "valor": "200,00", "ativo": True},
             {"id": atual[0]["id"], "nome": "Sessão Divinópolis", "valor": "240,00", "ativo": False},
             {"id": atual[1]["id"], "nome": "Avaliação", "valor": 260, "ativo": True}]
    assert _salvar(client, cen.gestor_a, novos).status_code == 200
    lista = _lista_gestor(client, cen)
    assert [(p["nome"], p["valor_centavos"], p["ativo"]) for p in lista] == [
        ("Sessão Equipe 2X", 20000, 1), ("Sessão Divinópolis", 24000, 0), ("Avaliação", 26000, 1)]


def test_trocar_nomes_entre_linhas(client, db_ctx):
    cen = DuasClinicas()
    _salvar(client, cen.gestor_a, LISTA[:2])
    a, b = _lista_gestor(client, cen)
    r = _salvar(client, cen.gestor_a, [{"id": a["id"], "nome": "Avaliação", "valor": 1}, {"id": b["id"], "nome": "Sessão Divinópolis", "valor": 2}])
    assert r.status_code == 200, r.get_data(as_text=True)
    assert [p["nome"] for p in _lista_gestor(client, cen)] == ["Avaliação", "Sessão Divinópolis"]


@pytest.mark.parametrize("ruim", [
    [{"nome": "Sessão", "valor": 1}, {"nome": " sessão ", "valor": 2}],
    [{"nome": "  ", "valor": 1}],
    [{"nome": "X", "codigo": "C" * 31, "valor": 1}],
    [{"nome": "X" * 121, "valor": 1}],
    [{"nome": "Ok", "valor": 1}, {"nome": "Ruim", "valor": "abc"}],
    [{"nome": "Ok", "valor": -5}],
])
def test_validacao_nao_grava_nada(client, db_ctx, ruim):
    cen = DuasClinicas()
    _salvar(client, cen.gestor_a, LISTA[:1])
    r = _salvar(client, cen.gestor_a, ruim)
    assert r.status_code == 400
    assert r.get_json()["erro"]
    assert [p["nome"] for p in _lista_gestor(client, cen)] == ["Sessão Divinópolis"]


def test_remover_usado_da_409_e_nao_grava_nada(client, db_ctx):
    cen = DuasClinicas()
    _salvar(client, cen.gestor_a, LISTA[:2])
    a, b = _lista_gestor(client, cen)
    db_ctx.execute("INSERT INTO consultas (paciente_id, profissional_id, data_hora, procedimento_id) VALUES (?, ?, '2026-10-20 09:00:00', ?)",
                   (cen.paciente_a1, cen.prof_a1["id"], a["id"]))
    r = _salvar(client, cen.gestor_a, [{"id": b["id"], "nome": "Avaliação", "valor": "999,00"}])
    assert r.status_code == 409
    assert "Sessão Divinópolis" in r.get_json()["erro"]
    lista = _lista_gestor(client, cen)
    assert [(p["nome"], p["valor_centavos"]) for p in lista] == [("Sessão Divinópolis", 23000), ("Avaliação", 26000)]
    assert lista[0]["em_uso"] == 1


def test_remover_nao_usado_apaga(client, db_ctx):
    cen = DuasClinicas()
    _salvar(client, cen.gestor_a, LISTA[:2])
    a, b = _lista_gestor(client, cen)
    assert _salvar(client, cen.gestor_a, [{"id": b["id"], "nome": "Avaliação", "valor": 1}]).status_code == 200
    assert [p["nome"] for p in _lista_gestor(client, cen)] == ["Avaliação"]


def test_id_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    _salvar(client, cen.gestor_b, LISTA[:1])
    outro = autenticado(client, cen.gestor_b).get("/api/procedimentos").get_json()[0]
    r = _salvar(client, cen.gestor_a, [{"id": outro["id"], "nome": "Roubado", "valor": 1}])
    assert r.status_code == 400
    assert autenticado(client, cen.gestor_b).get("/api/procedimentos").get_json()[0]["nome"] == "Sessão Divinópolis"
