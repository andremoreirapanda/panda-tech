"""Pandoo fase 2 (01/10/2026): Memória — regras e validação."""
import base64

import pytest

import pandoo_service as ps

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def _c(itens):
    return {"versao": 1, "itens": itens}


def _it(i, texto=None, imagem=PNG, distratores=None):
    texto = f"Palavra {i}" if texto is None else texto
    return {"id": f"i{i}", "pergunta": {"texto": texto, "imagem": imagem, "audio": None},
            "distratores": distratores or []}


def test_regras_padrao_e_normalizacao():
    _, r = ps.validar_jogo("memoria", _c([_it(1), _it(2)]), {}, None)
    assert r == {"pares": "figura", "quantidade": 6, "som": True, "voz": True}
    _, r = ps.validar_jogo("memoria", _c([_it(1), _it(2)]),
                           {"pares": "xx", "quantidade": 7, "voz": 0, "giros": 3}, None)
    assert r == {"pares": "figura", "quantidade": 6, "som": True, "voz": False}
    _, r = ps.validar_jogo("memoria", _c([_it(1), _it(2)]), {"pares": "palavra", "quantidade": "10"}, None)
    assert (r["pares"], r["quantidade"]) == ("palavra", 10)


def test_imagem_obrigatoria():
    with pytest.raises(ps.ErroPandoo, match="a memória precisa de uma imagem"):
        ps.validar_jogo("memoria", _c([_it(1, imagem=None), _it(2)]), {}, None)


def test_tipo_figura_aceita_sem_palavra_e_repetida():
    ps.validar_jogo("memoria", _c([_it(1, texto=""), _it(2, texto="")]), {"pares": "figura"}, None)
    ps.validar_jogo("memoria", _c([_it(1, "Gato"), _it(2, "gato")]), {"pares": "figura"}, None)


def test_tipo_palavra_exige_palavra_diferente():
    with pytest.raises(ps.ErroPandoo, match="precisa da palavra de cada figura"):
        ps.validar_jogo("memoria", _c([_it(1, texto=""), _it(2)]), {"pares": "palavra"}, None)
    with pytest.raises(ps.ErroPandoo, match="Item 2: a palavra repete"):
        ps.validar_jogo("memoria", _c([_it(1, "Robô"), _it(2, " robo ")]), {"pares": "palavra"}, None)


def test_memoria_nao_guarda_distratores():
    c, _ = ps.validar_jogo("memoria", _c([_it(1, distratores=["Pato"]), _it(2)]), {}, None)
    assert c["itens"][0]["distratores"] == []
