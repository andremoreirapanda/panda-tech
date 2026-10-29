"""Pandoo (29/10/2026): Cruzadinha — regras, palavras e a arrumação guardada."""
import base64
import copy

import pytest

import pandoo_service as ps
from conftest import autenticado
from factories import DuasClinicas
from modulos_service import definir_liberacao_admin

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()

# A cruzadinha da prévia aprovada (6 linhas × 4 colunas).
PALAVRAS = [("casa", 0, 1, "v"), ("gato", 1, 0, "h"), ("ovo", 1, 3, "v"),
            ("sapo", 3, 0, "h"), ("sol", 3, 0, "v"), ("lua", 5, 0, "h")]
GRADE = {"linhas": 6, "colunas": 4,
         "palavras": [{"item_id": p, "linha": l, "coluna": c, "direcao": d} for p, l, c, d in PALAVRAS]}


def _c(itens):
    return {"versao": 1, "itens": itens}


def _it(item_id, texto=None, imagem=PNG, distratores=None):
    return {"id": item_id, "pergunta": {"texto": item_id.upper() if texto is None else texto, "imagem": imagem, "audio": None},
            "distratores": distratores or []}


ITENS = [_it(p) for p, *_ in PALAVRAS]


def _grade(*palavras, linhas=15, colunas=15):
    return {"linhas": linhas, "colunas": colunas,
            "palavras": [{"item_id": i, "linha": l, "coluna": c, "direcao": d} for i, l, c, d in palavras]}


def _validar(itens=None, regras=None):
    regras = {"grade": GRADE} if regras is None else regras
    return ps.validar_jogo("cruzadinha", _c(ITENS if itens is None else itens), regras, None)


def test_regras_padrao_e_formas():
    _, r = _validar()
    assert r == {"formas": ["teclado", "letras"], "primeira_letra": False, "som": True,
                 "voz": True, "voz_acertar": True, "grade": GRADE}
    for ruim in ([], ["xx"], "teclado", None):
        _, r = _validar(regras={"formas": ruim, "grade": GRADE})
        assert r["formas"] == ["teclado", "letras"]
    _, r = _validar(regras={"formas": ["figuras", "teclado", "figuras"], "grade": GRADE, "voz_acertar": 0,
                            "primeira_letra": 1})
    assert r["formas"] == ["teclado", "figuras"]
    assert r["voz_acertar"] is False and r["primeira_letra"] is True


def test_limite_de_figuras():
    with pytest.raises(ps.ErroPandoo, match="A cruzadinha precisa ter de 2 a 10 figuras."):
        _validar(itens=[_it("gato")], regras={"grade": _grade(("gato", 0, 0, "h"))})
    onze = [_it(f"p{i}", "ab" + "cdefghijklm"[i]) for i in range(11)]
    with pytest.raises(ps.ErroPandoo, match="2 a 10 figuras"):
        _validar(itens=onze, regras={"grade": None})


def test_roleta_continua_ate_24():
    ps.validar_jogo("roleta", _c([_it(f"p{i}") for i in range(24)]), {}, None)


def test_imagem_e_palavra_obrigatorias():
    with pytest.raises(ps.ErroPandoo, match="Item 1: a cruzadinha precisa de uma imagem em cada figura."):
        _validar(itens=[_it("casa", imagem=None)] + ITENS[1:])
    with pytest.raises(ps.ErroPandoo, match="Item 1: a cruzadinha precisa da palavra de cada figura."):
        _validar(itens=[_it("casa", texto="  ")] + ITENS[1:])


@pytest.mark.parametrize("texto", ["Gato1", "ga.to", "-gato", "gato-", "ga--to", "ga- to"])
def test_caracteres_proibidos(texto):
    with pytest.raises(ps.ErroPandoo, match="Item 1: use só letras, hífen e espaço na palavra da cruzadinha."):
        _validar(itens=[_it("x", texto=texto), _it("y", texto="Uva")], regras={"grade": None})


@pytest.mark.parametrize("texto", ["A", "BORBOLETINHAS"])
def test_tamanho_da_palavra(texto):
    with pytest.raises(ps.ErroPandoo, match="Item 1: a palavra da cruzadinha precisa ter de 2 a 12 letras."):
        _validar(itens=[_it("x", texto=texto), _it("y", texto="Uva")], regras={"grade": None})


def test_hifen_e_espaco_valem_e_espacos_repetidos_viram_um():
    itens = [_it("g", texto="guarda-chuva"), _it("a", texto=" arco   íris ")]
    grade = _grade(("g", 0, 0, "h"), ("a", 2, 0, "h"))
    conteudo, _ = _validar(itens=itens, regras={"grade": grade})
    assert conteudo["itens"][1]["pergunta"]["texto"] == "arco íris"


def test_palavra_repetida():
    with pytest.raises(ps.ErroPandoo, match="Item 2: a palavra repete a de outra figura."):
        _validar(itens=[_it("x", texto="Robô"), _it("y", texto=" robo ")], regras={"grade": None})


def test_nao_guarda_distratores():
    itens = [_it("casa", distratores=["Pato"])] + ITENS[1:]
    conteudo, _ = _validar(itens=itens)
    assert conteudo["itens"][0]["distratores"] == []


def _quebrar(alterar):
    grade = copy.deepcopy(GRADE)
    alterar(grade)
    return grade


@pytest.mark.parametrize("grade", [
    None,
    "gato",
    _quebrar(lambda g: g["palavras"].pop()),                                    # item faltando
    _quebrar(lambda g: g["palavras"].append(dict(g["palavras"][0]))),           # item repetido
    _quebrar(lambda g: g["palavras"][0].update(item_id="zzz")),                 # item desconhecido
    _quebrar(lambda g: g["palavras"][0].update(direcao="d")),                   # direção inválida
    _quebrar(lambda g: g.update(colunas=3)),                                    # fora dos limites
    _quebrar(lambda g: g["palavras"][0].update(linha=-1)),                      # fora dos limites
    _quebrar(lambda g: g.update(linhas=16)),                                    # passa de 15
    _quebrar(lambda g: g["palavras"][2].update(coluna=2)),                      # cruzamento com letra diferente
])
def test_grade_invalida(grade):
    with pytest.raises(ps.ErroPandoo, match="A arrumação da cruzadinha está desatualizada."):
        _validar(regras={"grade": grade})


def test_cruzamento_no_hifen_recusado():
    itens = [_it("g", texto="pe-de-moleque"[:12]), _it("a", texto="ave")]
    # "PE-DE-MOLEQU" deitada; "AVE" em pé passando pelo hífen da coluna 2
    grade = _grade(("g", 1, 0, "h"), ("a", 0, 2, "v"))
    with pytest.raises(ps.ErroPandoo, match="desatualizada"):
        _validar(itens=itens, regras={"grade": grade})


def test_mesma_direcao_nao_divide_casa():
    itens = [_it("s", texto="sol"), _it("o", texto="sola")]
    grade = _grade(("s", 0, 0, "h"), ("o", 0, 0, "h"))
    with pytest.raises(ps.ErroPandoo, match="desatualizada"):
        _validar(itens=itens, regras={"grade": grade})


def test_acento_no_cruzamento_vale():
    itens = [_it("e", texto="ÉGUA"), _it("l", texto="ela")]
    ps.validar_jogo("cruzadinha", _c(itens), {"grade": _grade(("e", 0, 0, "h"), ("l", 0, 0, "v"))}, None)


def test_casas_da_palavra():
    assert ps.casas_da_palavra("Pé-de moça") == [
        ("P", False), ("E", False), ("-", True), ("D", False), ("E", False), (" ", True),
        ("M", False), ("O", False), ("C", False), ("A", False)]


def test_rota_salva_e_le_a_cruzadinha(client, db_ctx):
    cen = DuasClinicas()
    definir_liberacao_admin(cen.org_a, "pandoo", True)
    corpo = {"titulo": "Bichos e coisas", "modelo": "cruzadinha", "conteudo": _c(ITENS),
             "regras": {"formas": ["teclado", "figuras"], "grade": GRADE}}
    r = autenticado(client, cen.prof_a1).post("/api/pandoo/jogos", json=corpo)
    assert r.status_code == 201, r.get_data(as_text=True)
    jogo = autenticado(client, cen.prof_a1).get(f"/api/pandoo/jogos/{r.get_json()['id']}").get_json()
    assert jogo["modelo"] == "cruzadinha"
    assert jogo["regras"]["grade"] == GRADE and jogo["regras"]["formas"] == ["teclado", "figuras"]
    corpo["regras"]["grade"] = None
    assert autenticado(client, cen.prof_a1).post("/api/pandoo/jogos", json=corpo).status_code == 400
