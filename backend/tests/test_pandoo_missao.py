"""Pandoo (25/09/2026): missão com jogo só conclui depois de jogar
(diária: uma partida na missão; semanal: uma partida no dia)."""
import base64
from datetime import date, timedelta

import db
from factories import DuasClinicas, vincular_responsavel, novo_exercicio
from conftest import autenticado
from modulos_service import definir_liberacao_admin

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
DET = [{"item_id": "i0", "texto": "Rato", "resultado": "conseguiu"}]


def _jogo(client, cen):
    definir_liberacao_admin(cen.org_a, "pandoo", True)
    corpo = {"titulo": "Roleta", "modelo": "roleta",
             "conteudo": {"versao": 1, "itens": [{"id": f"i{i}", "pergunta": {"texto": f"P{i}", "imagem": PNG}} for i in range(3)]}}
    return autenticado(client, cen.prof_a1).post("/api/pandoo/jogos", json=corpo).get_json()["id"]


def _missao(client, cen, exercicios, tipo="diaria"):
    jornada = db.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)", (cen.paciente_a1, "Obj"))
    plano = db.execute("INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
                       (jornada, cen.prof_a1["id"], "Plano"))
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano}/criar-missao",
                                              json={"titulo": "M", "tipo": tipo, "frequencia_dias": 3, "exercicios_ids": exercicios})
    return r.get_json()["id"]


def _jogar(client, cen, missao_id, jogo_id, data_local=None):
    atividade = db.query_one("SELECT id FROM atividades WHERE missao_id = ? AND exercicio_id = ?", (missao_id, jogo_id))["id"]
    r = autenticado(client, cen.resp_a1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": jogo_id, "missao_id": missao_id, "atividade_id": atividade, "detalhes": DET})
    assert r.status_code == 201, r.get_data(as_text=True)
    if data_local:
        db.execute("UPDATE pandoo_resultados SET data_local = ? WHERE id = ?", (data_local, r.get_json()["id"]))
    return atividade


def _prep(client, cen, tipo="diaria"):
    jogo = _jogo(client, cen)
    comum = novo_exercicio(cen.org_a, "Vídeo")["id"]
    missao = _missao(client, cen, [jogo, comum], tipo)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    return jogo, missao


def test_diaria_bloqueada_sem_jogar_e_liberada_depois(client, db_ctx):
    cen = DuasClinicas()
    jogo, missao = _prep(client, cen)
    c = autenticado(client, cen.resp_a1)
    r = c.post(f"/api/jornada/missao/{missao}/concluir")
    assert r.status_code == 409 and "Jogue" in r.get_json()["erro"]
    assert len(r.get_json()["jogos_pendentes"]) == 1
    assert db.query_one("SELECT status FROM missoes WHERE id = ?", (missao,))["status"] != "concluida"
    _jogar(client, cen, missao, jogo)
    assert c.post(f"/api/jornada/missao/{missao}/concluir").status_code == 200


def test_semanal_exige_partida_no_dia(client, db_ctx):
    cen = DuasClinicas()
    jogo, missao = _prep(client, cen, "semanal")
    c = autenticado(client, cen.resp_a1)
    ontem = (date.today() - timedelta(days=1)).isoformat()
    _jogar(client, cen, missao, jogo, data_local=ontem)
    assert c.post(f"/api/jornada/missao/{missao}/concluir-dia").status_code == 409
    _jogar(client, cen, missao, jogo)
    assert c.post(f"/api/jornada/missao/{missao}/concluir-dia").status_code == 200


def test_missao_sem_jogo_segue_como_antes(client, db_ctx):
    cen = DuasClinicas()
    comum = novo_exercicio(cen.org_a, "Vídeo")["id"]
    missao = _missao(client, cen, [comum])
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    assert autenticado(client, cen.resp_a1).post(f"/api/jornada/missao/{missao}/concluir").status_code == 200


def test_bundle_informa_tipo_e_se_jogou(client, db_ctx):
    cen = DuasClinicas()
    jogo, missao = _prep(client, cen)
    c = autenticado(client, cen.resp_a1)

    def atividades():
        m = c.get(f"/api/jornada/missao/{missao}").get_json()
        return {a["exercicio_id"]: a for a in m["atividades"]}

    a = atividades()
    assert a[jogo]["exercicio_tipo"] == "jogo" and a[jogo]["jogo_jogado"] is False
    _jogar(client, cen, missao, jogo)
    assert atividades()[jogo]["jogo_jogado"] is True


def test_partida_sem_giro_nao_libera_a_missao(client, db_ctx):
    """Pedido do usuário (26/09/2026): 'Finalizar jogo' antes de girar não
    conta como ter jogado — a missão exige pelo menos um giro."""
    cen = DuasClinicas()
    jogo, missao = _prep(client, cen)
    atividade = db.query_one("SELECT id FROM atividades WHERE missao_id = ? AND exercicio_id = ?", (missao, jogo))["id"]
    c = autenticado(client, cen.resp_a1)
    r = c.post("/api/pandoo/resultados", json={"paciente_id": cen.paciente_a1, "exercicio_id": jogo, "missao_id": missao,
                                             "atividade_id": atividade, "encerrado_antes": True, "detalhes": []})
    assert r.status_code == 201
    assert autenticado(client, cen.resp_a1).post(f"/api/jornada/missao/{missao}/concluir").status_code == 409
    ativs = autenticado(client, cen.resp_a1).get(f"/api/jornada/paciente/{cen.paciente_a1}").get_json()["missoes"]
    a = next(x for m in ativs if m["id"] == missao for x in m["atividades"] if x["exercicio_id"] == jogo)
    assert a["jogo_jogado"] is False
    _jogar(client, cen, missao, jogo)
    assert autenticado(client, cen.resp_a1).post(f"/api/jornada/missao/{missao}/concluir").status_code == 200
