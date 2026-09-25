"""Pandoo (25/09/2026): salvar e consultar resultados de partidas."""
import base64
from datetime import date

import db
from factories import DuasClinicas, vincular_responsavel
from conftest import autenticado
from modulos_service import definir_liberacao_admin

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
DET = [{"item_id": "i0", "texto": "Rato", "resultado": "conseguiu"}, {"item_id": "i1", "texto": "Rosa", "resultado": "treinar"}]


def _jogo(client, cen):
    definir_liberacao_admin(cen.org_a, "pandoo", True)
    corpo = {"titulo": "Roleta", "modelo": "roleta",
             "conteudo": {"versao": 1, "itens": [{"id": f"i{i}", "pergunta": {"texto": f"P{i}", "imagem": PNG}} for i in range(3)]}}
    return autenticado(client, cen.prof_a1).post("/api/pandoo/jogos", json=corpo).get_json()["id"]


def _missao(client, cen, jogo_id, tipo="diaria", paciente=None):
    paciente = paciente or cen.paciente_a1
    jornada = db.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)", (paciente, "Obj"))
    plano = db.execute("INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
                       (jornada, cen.prof_a1["id"], "Plano"))
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano}/criar-missao",
                                              json={"titulo": "M", "tipo": tipo, "frequencia_dias": 3, "exercicios_ids": [jogo_id]})
    missao_id = r.get_json()["id"]
    atividade_id = db.query_one("SELECT id FROM atividades WHERE missao_id = ?", (missao_id,))["id"]
    return missao_id, atividade_id


def test_responsavel_salva_partida_da_missao(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    missao, atividade = _missao(client, cen, jogo)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    r = autenticado(client, cen.resp_a1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": jogo, "missao_id": missao, "atividade_id": atividade,
        "encerrado_antes": True, "detalhes": DET})
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["acertos"] == 1 and r.get_json()["a_treinar"] == 1
    linha = db.query_one("SELECT * FROM pandoo_resultados WHERE id = ?", (r.get_json()["id"],))
    assert linha["encerrado_antes"] == 1 and linha["data_local"] == date.today().isoformat()
    assert linha["usuario_id"] == cen.resp_a1["id"] and linha["modelo"] == "roleta"


def test_numeros_recalculados_no_servidor(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    r = autenticado(client, cen.prof_a1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": jogo, "acertos": 99, "detalhes": DET})
    assert r.status_code == 201 and r.get_json()["acertos"] == 1


def test_responsavel_sem_vinculo_nao_salva(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    r = autenticado(client, cen.resp_a1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": jogo, "detalhes": DET})
    assert r.status_code == 403


def test_outra_clinica_nao_salva(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    r = autenticado(client, cen.prof_b1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": jogo, "detalhes": DET})
    assert r.status_code == 403


def test_missao_e_atividade_incoerentes_400(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    m1, a1 = _missao(client, cen, jogo)
    m2, a2 = _missao(client, cen, jogo, paciente=cen.paciente_a2)
    c = autenticado(client, cen.prof_a1)
    base = {"paciente_id": cen.paciente_a1, "exercicio_id": jogo, "detalhes": DET}
    assert c.post("/api/pandoo/resultados", json={**base, "missao_id": m1, "atividade_id": a2}).status_code == 400
    assert c.post("/api/pandoo/resultados", json={**base, "missao_id": m2, "atividade_id": a2}).status_code == 400
    assert c.post("/api/pandoo/resultados", json={**base, "missao_id": m1}).status_code == 400
    assert db.query_one("SELECT COUNT(*) AS n FROM pandoo_resultados")["n"] == 0


def test_atividade_de_outro_exercicio_400(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    outro = db.execute("INSERT INTO exercicios (organizacao_id, titulo, tipo) VALUES (?, ?, 'jogo')", (cen.org_a, "Outro"))
    db.execute("INSERT INTO pandoo_jogos (exercicio_id, modelo, conteudo_json, regras_json, total_itens) VALUES (?, 'roleta', '{}', '{}', 0)", (outro,))
    m, a = _missao(client, cen, jogo)
    r = autenticado(client, cen.prof_a1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": outro, "missao_id": m, "atividade_id": a, "detalhes": DET})
    assert r.status_code == 400


def test_detalhes_invalidos_400(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    r = autenticado(client, cen.prof_a1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": jogo, "detalhes": [{"item_id": "i0", "resultado": "talvez"}]})
    assert r.status_code == 400


def test_profissional_ve_partidas_e_resumo_por_figura(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    c = autenticado(client, cen.prof_a1)
    for det in (DET, [{"item_id": "i0", "texto": "Rato", "resultado": "conseguiu"}]):
        c.post("/api/pandoo/resultados", json={"paciente_id": cen.paciente_a1, "exercicio_id": jogo, "detalhes": det})
    r = c.get(f"/api/pandoo/resultados?paciente_id={cen.paciente_a1}").get_json()
    assert len(r["partidas"]) == 2 and r["partidas"][0]["titulo"] == "Roleta"
    itens = {i["texto"]: i for i in r["por_jogo"][0]["itens"]}
    assert (itens["Rato"]["conseguiu"], itens["Rato"]["total"]) == (2, 2)
    assert (itens["Rosa"]["conseguiu"], itens["Rosa"]["total"]) == (0, 1)
    assert autenticado(client, cen.prof_b1).get(f"/api/pandoo/resultados?paciente_id={cen.paciente_a1}").status_code == 403
    assert autenticado(client, cen.resp_a1).get(f"/api/pandoo/resultados?paciente_id={cen.paciente_a1}").status_code == 403
