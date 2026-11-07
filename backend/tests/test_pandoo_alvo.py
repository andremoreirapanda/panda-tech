"""Pandoo (05/11/2026): "Toque só no alvo" — regras, validação, resultado e medidas."""
import base64

import pytest

import pandoo_service as ps

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def _c(itens):
    return {"versao": 1, "itens": itens}


def _it(i, texto=None, imagem=PNG, audio=None):
    texto = f"Palavra {i}" if texto is None else texto
    return {"id": f"i{i}", "pergunta": {"texto": texto, "imagem": imagem, "audio": audio}}


# --- Task 1: regras e validação -------------------------------------------

def test_regras_padrao_e_normalizacao():
    _, r = ps.validar_jogo("alvo", _c([_it(1), _it(2)]), {"alvo_item_id": "i1"}, None)
    assert r == {"alvo_item_id": "i1", "frase_inicio": "Toque só no", "fase_inicio": 1, "fase_fim": 3,
                 "subir_sozinho": True, "figuras_por_fase": 20, "velocidade": "media", "som": True,
                 "frase_audio": None}
    _, r = ps.validar_jogo("alvo", _c([_it(1), _it(2)]),
                           {"alvo_item_id": "i2", "frase_inicio": "  ", "fase_inicio": 3, "fase_fim": 1,
                            "figuras_por_fase": 999, "velocidade": "turbo", "som": 0, "voz": True,
                            "subir_sozinho": 0}, None)
    assert r["frase_inicio"] == "Toque só no" and (r["fase_inicio"], r["fase_fim"]) == (3, 3)
    assert r["figuras_por_fase"] == 60 and r["velocidade"] == "media"
    assert r["som"] is False and r["subir_sozinho"] is False and "voz" not in r
    _, r = ps.validar_jogo("alvo", _c([_it(1), _it(2)]),
                           {"alvo_item_id": "i1", "frase_inicio": "Toque só na " + "x" * 60}, None)
    assert len(r["frase_inicio"]) == 40
    _, r = ps.validar_jogo("alvo", _c([_it(1), _it(2)]),
                           {"alvo_item_id": "i1", "fase_inicio": 2, "fase_fim": 3, "figuras_por_fase": 3,
                            "velocidade": "rapida"}, None)
    assert (r["fase_inicio"], r["fase_fim"], r["figuras_por_fase"], r["velocidade"]) == (2, 3, 10, "rapida")


def test_alvo_obrigatorio_e_existente():
    for regras in ({}, {"alvo_item_id": "nao-existe"}):
        with pytest.raises(ps.ErroPandoo, match="Escolha qual figura é o alvo"):
            ps.validar_jogo("alvo", _c([_it(1), _it(2)]), regras, None)


def test_imagem_obrigatoria():
    with pytest.raises(ps.ErroPandoo, match="precisa de uma imagem"):
        ps.validar_jogo("alvo", _c([_it(1), _it(2, imagem=None)]), {"alvo_item_id": "i1"}, None)


def test_alvo_precisa_palavra_ou_voz_pegadinha_nao():
    with pytest.raises(ps.ErroPandoo, match="palavra ou a voz"):
        ps.validar_jogo("alvo", _c([_it(1, texto=""), _it(2)]), {"alvo_item_id": "i1"}, None)
    ps.validar_jogo("alvo", _c([_it(1), _it(2, texto="")]), {"alvo_item_id": "i1"}, None)


# --- Task 2: resultado da partida e medidas -------------------------------

def D(item, alvo, tocou, fase=1, tempo=None):
    d = {"item_id": item, "texto": "", "alvo": alvo, "tocou": tocou, "fase": fase,
         "resultado": "conseguiu" if alvo == tocou else "treinar"}
    if tempo is not None:
        d["tempo_ms"] = tempo
    return d


REG = {"alvo_item_id": "i0"}


def test_calcular_resultado_alvo_conta_so_toques():
    det = [D("i0", True, True, 1, 500), D("i1", False, False), D("i0", True, False), D("i1", False, True, 2)]
    r = ps.calcular_resultado(det, "alvo", REG)
    assert (r["total_rodadas"], r["acertos"], r["a_treinar"]) == (2, 2, 2)
    assert r["detalhes"][0] == {"item_id": "i0", "texto": "", "resultado": "conseguiu", "alvo": True,
                                "tocou": True, "fase": 1, "tempo_ms": 500}
    assert "tempo_ms" not in r["detalhes"][1]


def test_calcular_resultado_alvo_sem_toque_zero_rodadas():
    assert ps.calcular_resultado([D("i0", True, False), D("i1", False, False)], "alvo", REG)["total_rodadas"] == 0


def test_servidor_confere_alvo_e_resultado():
    with pytest.raises(ps.ErroPandoo):  # pegadinha dizendo ser alvo
        ps.calcular_resultado([D("i1", True, True)], "alvo", REG)
    with pytest.raises(ps.ErroPandoo):  # resultado incoerente
        ps.calcular_resultado([{**D("i0", True, True), "resultado": "treinar"}], "alvo", REG)
    with pytest.raises(ps.ErroPandoo):  # fase fora de 1..3
        ps.calcular_resultado([D("i0", True, True, 4)], "alvo", REG)
    with pytest.raises(ps.ErroPandoo):  # tocou não booleano
        ps.calcular_resultado([{**D("i0", True, True), "tocou": "sim"}], "alvo", REG)


def test_tempo_so_em_alvo_tocado_e_limitado():
    r = ps.calcular_resultado([D("i1", False, True, 1, 300), D("i0", True, True, 1, 99999)], "alvo", REG)
    assert "tempo_ms" not in r["detalhes"][0] and r["detalhes"][1]["tempo_ms"] == 10000


def test_outros_modelos_continuam_iguais():
    r = ps.calcular_resultado([{"item_id": "a", "texto": "x", "resultado": "conseguiu", "fase": 9}])
    assert r["detalhes"] == [{"item_id": "a", "texto": "x", "resultado": "conseguiu"}] and r["total_rodadas"] == 1


def test_medidas_alvo():
    det = [D("i0", True, True, 1, 400), D("i0", True, True, 2, 800), D("i0", True, False, 2),
           D("i1", False, True, 2), D("i1", False, False)]
    assert ps.medidas_alvo(det) == {"alvos_tocados": 2, "alvos_total": 3, "alvos_perdidos": 1,
                                    "toques_errados": 1, "tempo_medio_ms": 600, "fase_alcancada": 2}
    assert ps.medidas_alvo([D("i1", False, False)])["tempo_medio_ms"] is None


# --- integração (rotas) ---------------------------------------------------

import db  # noqa: E402
from conftest import autenticado  # noqa: E402
from factories import DuasClinicas, vincular_responsavel  # noqa: E402
from modulos_service import definir_liberacao_admin  # noqa: E402

CORPO_JOGO = {"titulo": "Ache o cachorro", "modelo": "alvo", "regras": {"alvo_item_id": "i0"},
              "conteudo": _c([_it(0, "cachorro"), _it(1, "gato"), _it(2, "")])}


def _jogo(client, cen):
    definir_liberacao_admin(cen.org_a, "pandoo", True)
    r = autenticado(client, cen.prof_a1).post("/api/pandoo/jogos", json=CORPO_JOGO)
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["id"]


def _missao(client, cen, jogo_id):
    jornada = db.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)", (cen.paciente_a1, "Obj"))
    plano = db.execute("INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
                       (jornada, cen.prof_a1["id"], "Plano"))
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano}/criar-missao",
                                              json={"titulo": "M", "tipo": "diaria", "frequencia_dias": 3, "exercicios_ids": [jogo_id]})
    missao_id = r.get_json()["id"]
    return missao_id, db.query_one("SELECT id FROM atividades WHERE missao_id = ?", (missao_id,))["id"]


def test_partida_sem_toque_nao_libera_missao_nem_trava_dia(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    missao, atividade = _missao(client, cen, jogo)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    c = autenticado(client, cen.resp_a1)
    corpo = {"paciente_id": cen.paciente_a1, "exercicio_id": jogo, "missao_id": missao, "atividade_id": atividade}

    r = c.post("/api/pandoo/resultados", json={**corpo, "detalhes": [D("i1", False, False), D("i0", True, False)]})
    assert r.status_code == 201 and r.get_json()["total_rodadas"] == 0
    ativ = c.get(f"/api/jornada/missao/{missao}").get_json()["atividades"][0]
    assert ativ["jogo_jogado"] is False and ativ["jogou_hoje"] is False

    r = c.post("/api/pandoo/resultados", json={**corpo, "detalhes": [D("i1", False, False), D("i0", True, True, 1, 700)]})
    assert r.status_code == 201 and r.get_json()["total_rodadas"] == 1
    ativ = c.get(f"/api/jornada/missao/{missao}").get_json()["atividades"][0]
    assert ativ["jogo_jogado"] is True and ativ["jogou_hoje"] is True


def test_detalhe_forjado_400(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    r = autenticado(client, cen.prof_a1).post("/api/pandoo/resultados", json={
        "paciente_id": cen.paciente_a1, "exercicio_id": jogo, "detalhes": [D("i1", True, True, 1, 100)]})
    assert r.status_code == 400


def test_listagem_traz_medidas_e_ignora_jogo_editado(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    c = autenticado(client, cen.prof_a1)
    det = [D("i0", True, True, 1, 400), D("i1", False, True, 1), D("i0", True, False, 2)]
    assert c.post("/api/pandoo/resultados", json={"paciente_id": cen.paciente_a1, "exercicio_id": jogo,
                                                  "detalhes": det}).status_code == 201
    r = c.put(f"/api/pandoo/jogos/{jogo}", json={**CORPO_JOGO, "regras": {"alvo_item_id": "i1"}})
    assert r.status_code == 200, r.get_data(as_text=True)
    dados = c.get(f"/api/pandoo/resultados?paciente_id={cen.paciente_a1}").get_json()
    assert dados["partidas"][0]["medidas"] == {"alvos_tocados": 1, "alvos_total": 2, "alvos_perdidos": 1,
                                               "toques_errados": 1, "tempo_medio_ms": 400, "fase_alcancada": 2}
    assert dados["por_jogo"] == []


# --- Ajustes de 07/11/2026: voz gravada da frase do comando -----------------

WEBM = base64.b64encode(bytes([0x1A, 0x45, 0xDF, 0xA3]) + bytes(64)).decode()


def test_frase_audio_guardada_no_alvo():
    _, r = ps.validar_jogo("alvo", _c([_it(1), _it(2)]), {"alvo_item_id": "i1", "frase_audio": WEBM}, None)
    assert r["frase_audio"] == WEBM
    _, r = ps.validar_jogo("alvo", _c([_it(1), _it(2)]), {"alvo_item_id": "i1", "frase_audio": ""}, None)
    assert r["frase_audio"] is None


def test_frase_audio_invalida_ou_grande():
    with pytest.raises(ps.ErroPandoo, match="Frase do comando"):
        ps.validar_jogo("alvo", _c([_it(1), _it(2)]), {"alvo_item_id": "i1", "frase_audio": PNG}, None)
    grande = base64.b64encode(bytes([0x1A, 0x45, 0xDF, 0xA3]) + bytes(601 * 1024)).decode()
    with pytest.raises(ps.ErroPandoo, match="Frase do comando.*600 KB"):
        ps.validar_jogo("alvo", _c([_it(1), _it(2)]), {"alvo_item_id": "i1", "frase_audio": grande}, None)
    with pytest.raises(ps.ErroPandoo, match="Frase do comando"):
        ps.validar_jogo("alvo", _c([_it(1), _it(2)]), {"alvo_item_id": "i1", "frase_audio": 123}, None)


def test_frase_audio_ignorada_fora_do_alvo():
    _, r = ps.validar_jogo("roleta", _c([_it(1), _it(2)]), {"frase_audio": WEBM}, None)
    assert "frase_audio" not in r
