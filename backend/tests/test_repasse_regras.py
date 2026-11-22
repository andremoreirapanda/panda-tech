import repasse_regras as rr


def _r(proc=None, tipo=None, modo="percentual", pct=0, valor=0):
    return {"procedimento_id": proc, "tipo_acordo": tipo, "modo": modo,
            "percentual_centesimos": pct, "valor_centavos": valor}


REGRAS = [_r(pct=6000), _r(tipo="pacote", pct=5000), _r(proc=7, pct=6500),
          _r(proc=7, tipo="pacote", pct=7000)]


def test_escolher_regra_ordem():
    assert rr.escolher_regra(REGRAS, 7, "pacote")["percentual_centesimos"] == 7000
    assert rr.escolher_regra(REGRAS, 7, "avulsa")["percentual_centesimos"] == 6500
    assert rr.escolher_regra(REGRAS, 8, "pacote")["percentual_centesimos"] == 5000
    assert rr.escolher_regra(REGRAS, 8, "avulsa")["percentual_centesimos"] == 6000


def test_escolher_regra_vazia_ou_sem_padrao():
    assert rr.escolher_regra([], 1, "avulsa") is None
    assert rr.escolher_regra([_r(proc=7, pct=6500)], 8, "avulsa") is None


def test_valor_profissional():
    assert rr.valor_profissional(_r(pct=6500), 23000) == 14950
    assert rr.valor_profissional(_r(pct=6550), 10001) == 6551
    assert rr.valor_profissional(_r(modo="fixo", valor=8000), 23000) == 8000
    assert rr.valor_profissional(_r(pct=0), 23000) == 0


def test_bases_avulsa():
    r = rr.bases_avulsa([15000, 15000, 5000], 3500)
    assert sum(r) == 31500
    assert r[0] == r[1] and r[0] > r[2]
    assert rr.bases_avulsa([15000, 5000], 0) == [15000, 5000]


def test_rateio_igual():
    assert rr.rateio_igual(100000, 3) == [33333, 33333, 33334]
    assert rr.rateio_igual(0, 2) == [0, 0]


def test_pacote_liberadas():
    assert rr.pacote_liberadas(100000, 10, 35000) == 3
    assert rr.pacote_liberadas(100000, 10, 0) == 0
    assert rr.pacote_liberadas(100000, 10, 100000) == 10
    assert rr.pacote_liberadas(100000, 3, 33334) == 1
    assert rr.pacote_liberadas(100000, 3, 33333) == 0
    assert rr.pacote_liberadas(100000, 10, 500000) == 10


def test_rotulo_regra():
    assert rr.rotulo_regra(_r(pct=6500)) == "65%"
    assert rr.rotulo_regra(_r(pct=6550)) == "65,5%"
    assert rr.rotulo_regra(_r(pct=6525)) == "65,25%"
    assert rr.rotulo_regra(_r(modo="fixo", valor=8000)) == "R$ 80,00 fixo"
    assert rr.rotulo_regra(_r(modo="fixo", valor=125000)) == "R$ 1.250,00 fixo"
    assert rr.rotulo_regra(None) == "a definir"
