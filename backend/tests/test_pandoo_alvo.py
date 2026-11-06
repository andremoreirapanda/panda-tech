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
                 "subir_sozinho": True, "figuras_por_fase": 20, "velocidade": "media", "som": True}
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
