"""Pandoo (25/09/2026): validação do conteúdo único, das regras da roleta e
do resultado de uma partida."""
import base64
import json

import pytest

import pandoo_service as ps

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
MP3 = base64.b64encode(b"ID3" + b"\x00" * 64).decode()
WEBM = base64.b64encode(b"\x1a\x45\xdf\xa3" + b"\x00" * 64).decode()
TEXTO_FALSO = base64.b64encode(b"<script>alert(1)</script>").decode()


def _item(i, **p):
    return {"id": f"i{i}", "pergunta": {"texto": f"Palavra {i}", "imagem": PNG, **p}}


def _conteudo(n=3, **p):
    return {"versao": 1, "itens": [_item(i, **p) for i in range(n)]}


def test_roleta_valida_e_normaliza():
    conteudo, regras = ps.validar_jogo("roleta", _conteudo(), {}, None)
    item = conteudo["itens"][0]
    assert item["resposta"] == {"texto": "", "imagem": None, "audio": None}
    assert item["distratores"] == [] and item["grupo"] is None
    assert regras == {"fim": "todas", "giros": 10, "mostrar_palavra": True, "som": True, "voz": True}


def test_regras_por_giros_limitadas():
    _, regras = ps.validar_jogo("roleta", _conteudo(), {"fim": "giros", "giros": 500, "voz": False}, "mar")
    assert regras["fim"] == "giros" and regras["giros"] == 100 and regras["voz"] is False


@pytest.mark.parametrize("modelo,conteudo,cenario,trecho", [
    ("quiz", _conteudo(), None, "modelo"),
    ("roleta", {"versao": 2, "itens": []}, None, "versão"),
    ("roleta", _conteudo(1), None, "2 a 24"),
    ("roleta", _conteudo(25), None, "2 a 24"),
    ("roleta", _conteudo(), "praia", "(?i)cenário"),
])
def test_recusas_basicas(modelo, conteudo, cenario, trecho):
    with pytest.raises(ps.ErroPandoo, match=trecho):
        ps.validar_jogo(modelo, conteudo, {}, cenario)


def test_roleta_exige_imagem_em_cada_item():
    c = _conteudo()
    c["itens"][1]["pergunta"]["imagem"] = None
    with pytest.raises(ps.ErroPandoo, match="imagem"):
        ps.validar_jogo("roleta", c, {}, None)


def test_imagem_falsa_ou_grande_recusada():
    with pytest.raises(ps.ErroPandoo, match="imagem"):
        ps.validar_jogo("roleta", _conteudo(imagem=TEXTO_FALSO), {}, None)
    grande = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * (310 * 1024)).decode()
    with pytest.raises(ps.ErroPandoo, match="300 KB"):
        ps.validar_jogo("roleta", _conteudo(imagem=grande), {}, None)


def test_audio_mp3_e_webm_aceitos_texto_nao():
    ps.validar_jogo("roleta", _conteudo(audio=MP3), {}, None)
    ps.validar_jogo("roleta", _conteudo(audio=WEBM), {}, None)
    with pytest.raises(ps.ErroPandoo, match="áudio"):
        ps.validar_jogo("roleta", _conteudo(audio=TEXTO_FALSO), {}, None)


def test_texto_cortado_e_ids_unicos():
    c = _conteudo()
    c["itens"][0]["pergunta"]["texto"] = "  " + "x" * 200 + "  "
    conteudo, _ = ps.validar_jogo("roleta", c, {}, None)
    assert len(conteudo["itens"][0]["pergunta"]["texto"]) == 80
    c = _conteudo()
    c["itens"][1]["id"] = "i0"
    with pytest.raises(ps.ErroPandoo, match="repetid"):
        ps.validar_jogo("roleta", c, {}, None)


def test_conteudo_total_acima_de_10_mb():
    imagem = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * (290 * 1024)).decode()
    c = {"versao": 1, "itens": [_item(i, imagem=imagem, audio=base64.b64encode(b"ID3" + b"\x00" * (590 * 1024)).decode()) for i in range(24)]}
    with pytest.raises(ps.ErroPandoo, match="10 MB"):
        ps.validar_jogo("roleta", c, {}, None)


def test_calcular_resultado():
    r = ps.calcular_resultado([
        {"item_id": "i1", "texto": "Rato", "resultado": "conseguiu"},
        {"item_id": "i2", "texto": "Rosa", "resultado": "treinar"},
        {"item_id": "i3", "texto": "Rei", "resultado": "conseguiu"},
    ])
    assert (r["total_rodadas"], r["acertos"], r["a_treinar"]) == (3, 2, 1)
    assert r["detalhes"][0] == {"item_id": "i1", "texto": "Rato", "resultado": "conseguiu"}


def test_resultado_invalido():
    with pytest.raises(ps.ErroPandoo):
        ps.calcular_resultado([{"item_id": "i1", "resultado": "talvez"}])
    with pytest.raises(ps.ErroPandoo):
        ps.calcular_resultado("não é lista")
    with pytest.raises(ps.ErroPandoo):
        ps.calcular_resultado([{"item_id": "i", "resultado": "conseguiu"}] * 501)


def test_partida_encerrada_sem_rodadas_e_valida():
    assert ps.calcular_resultado([])["total_rodadas"] == 0


def test_imagem_cenario():
    assert ps.imagem_cenario_valida(PNG)
    assert not ps.imagem_cenario_valida(TEXTO_FALSO)
    grande = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * (810 * 1024)).decode()
    assert not ps.imagem_cenario_valida(grande)
