"""Pandoo fase 2 (30/09/2026): Quiz — regras e validação."""
import base64

import pytest

import pandoo_service as ps

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
MP3 = base64.b64encode(b"ID3" + b"\x00" * 64).decode()


def _c(itens):
    return {"versao": 1, "itens": itens}


def _it(i, texto=None, imagem=PNG, audio=None, distratores=None):
    texto = f"Palavra {i}" if texto is None else texto
    return {"id": f"i{i}", "pergunta": {"texto": texto, "imagem": imagem, "audio": audio},
            "distratores": distratores or []}


def test_quiz_ouvir_valido_e_regras_padrao():
    c, r = ps.validar_jogo("quiz", _c([_it(1), _it(2, "Rosa")]), {}, None)
    assert r == {"modo": "ouvir", "opcoes": 3, "fim": "todas", "perguntas": 10, "som": True, "voz": True}
    assert len(c["itens"]) == 2


def test_quiz_ouvir_aceita_audio_sem_texto():
    ps.validar_jogo("quiz", _c([_it(1, texto="", audio=MP3), _it(2)]), {"modo": "ouvir"}, None)


def test_quiz_recusas():
    with pytest.raises(ps.ErroPandoo, match="o quiz precisa de uma imagem"):
        ps.validar_jogo("quiz", _c([_it(1, imagem=None), _it(2)]), {}, None)
    with pytest.raises(ps.ErroPandoo, match="precisa da palavra de cada figura"):
        ps.validar_jogo("quiz", _c([_it(1, texto=""), _it(2)]), {"modo": "ver"}, None)
    with pytest.raises(ps.ErroPandoo, match="palavra ou a voz"):
        ps.validar_jogo("quiz", _c([_it(1, texto=""), _it(2)]), {"modo": "ouvir"}, None)


def test_quiz_regras_normalizadas():
    _, r = ps.validar_jogo("quiz", _c([_it(1), _it(2)]),
                           {"modo": "xx", "opcoes": 7, "fim": "perguntas", "perguntas": 999, "som": 0}, None)
    assert r == {"modo": "ouvir", "opcoes": 3, "fim": "perguntas", "perguntas": 100, "som": False, "voz": True}
    _, r = ps.validar_jogo("quiz", _c([_it(1), _it(2)]), {"modo": "ver", "opcoes": "2", "giros": 5}, None)
    assert (r["modo"], r["opcoes"]) == ("ver", 2)
    assert "giros" not in r


def test_quiz_distratores_ate_3():
    c, _ = ps.validar_jogo("quiz", _c([_it(1, distratores=["Pato", "Gato", "Mato", "Fato"]), _it(2)]),
                           {"modo": "ver"}, None)
    assert c["itens"][0]["distratores"] == ["Pato", "Gato", "Mato"]


def test_quiz_precisa_de_2_palavras_diferentes():
    # Revisão final (30/09/2026): "Rato"/"rato" deixaria a pergunta com 1 opção.
    iguais = _c([_it(1, "Rato"), _it(2, "rato")])
    for modo in ("ver", "ouvir"):
        with pytest.raises(ps.ErroPandoo, match="2 palavras diferentes"):
            ps.validar_jogo("quiz", iguais, {"modo": modo}, None)
    # as opções erradas de uma figura não servem para a outra
    with pytest.raises(ps.ErroPandoo, match="Item 2.*2 palavras diferentes"):
        ps.validar_jogo("quiz", _c([_it(1, "Rato", distratores=["Pato"]), _it(2, "rato")]), {"modo": "ver"}, None)
    ps.validar_jogo("quiz", _c([_it(1, "Rato", distratores=["Pato"]), _it(2, "rato", distratores=["Gato"])]),
                    {"modo": "ver"}, None)
    ps.validar_jogo("quiz", _c([_it(1, "Robô"), _it(2, "", audio=MP3)]), {"modo": "ouvir"}, None)


def test_quiz_ouvir_sem_voz_exige_palavra():
    with pytest.raises(ps.ErroPandoo, match="precisa da palavra"):
        ps.validar_jogo("quiz", _c([_it(1, texto="", audio=MP3), _it(2)]), {"modo": "ouvir", "voz": False}, None)


def test_roleta_sem_mudanca():
    _, r = ps.validar_jogo("roleta", _c([_it(1), _it(2)]), {"modo": "ver"}, None)
    assert r == {"fim": "todas", "giros": 10, "mostrar_palavra": True, "som": True, "voz": True}
    with pytest.raises(ps.ErroPandoo, match="a roleta precisa de uma imagem"):
        ps.validar_jogo("roleta", _c([_it(1, imagem=None), _it(2)]), {}, None)
