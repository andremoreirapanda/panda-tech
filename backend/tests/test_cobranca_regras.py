import cobranca_regras as cr


def _acordo(esp, inicio="2026-01-01", fim=None, status="ativo", **kw):
    d = {"especialidade": esp, "inicio": inicio, "fim": fim, "status": status}
    d.update(kw)
    return d


def test_normalizar_especialidade():
    assert cr.normalizar_especialidade("  ") == "Geral"
    assert cr.normalizar_especialidade(None) == "Geral"
    assert cr.normalizar_especialidade("  Fono ") == "Fono"


def test_mesma_especialidade():
    assert cr.mesma_especialidade(" Fono", "fono  ")
    assert not cr.mesma_especialidade("Fono", "TO")


def test_acordo_especifico_vence_todas():
    todas = _acordo("*", id=1)
    fono = _acordo("Fono", id=2)
    assert cr.escolher_acordo([todas, fono], "fono", "2026-11-10")["id"] == 2
    assert cr.escolher_acordo([todas, fono], "TO", "2026-11-10")["id"] == 1


def test_acordo_fora_da_vigencia_ignorado():
    assert cr.escolher_acordo([_acordo("Fono", inicio="2026-12-01")], "Fono", "2026-11-10") is None
    assert cr.escolher_acordo([_acordo("Fono", fim="2026-11-09")], "Fono", "2026-11-10") is None
    assert cr.escolher_acordo([_acordo("Fono", fim="2026-11-10")], "Fono", "2026-11-10") is not None
    assert cr.escolher_acordo([_acordo("Fono", status="encerrado")], "Fono", "2026-11-10") is None


def test_status_gera_cobranca():
    assert cr.status_gera_cobranca("realizada", False) is True
    assert cr.status_gera_cobranca("faltou", False) is False
    assert cr.status_gera_cobranca("faltou", True) is True
    assert cr.status_gera_cobranca("falta_justificada", True) is False
    assert cr.status_gera_cobranca("cancelada", True) is False
    assert cr.status_gera_cobranca("desmarcada_profissional", True) is False


def test_periodo_da_data():
    assert cr.periodo_da_data("2026-11-15", "quinzenal") == ("2026-11-01", "2026-11-15")
    assert cr.periodo_da_data("2026-11-16", "quinzenal") == ("2026-11-16", "2026-11-30")
    assert cr.periodo_da_data("2026-02-20", "mensal") == ("2026-02-01", "2026-02-28")
    assert cr.periodo_da_data("2026-11-20", "consulta") == ("2026-11-20", "2026-11-20")


def test_vencimento_do_periodo():
    assert cr.vencimento_do_periodo("2026-11-30", 5) == "2026-12-05"


def test_mensalidade_do_mes():
    assert cr.mensalidade_do_mes(60000, 2026, 11, "2026-11-16", None) == 30000
    assert cr.mensalidade_do_mes(60000, 2026, 11, "2026-10-01", "2026-11-10") == 20000
    assert cr.mensalidade_do_mes(60000, 2026, 12, "2026-10-01", "2026-11-10") == 0
    assert cr.mensalidade_do_mes(60000, 2026, 11, "2026-10-01", None) == 60000
    assert cr.mensalidade_do_mes(60000, 2026, 10, "2026-11-16", None) == 0


def test_ratear_desconto():
    r = cr.ratear_desconto([23000, 23000, 20500], 6650)
    assert r == [20700, 20700, 18450]
    assert sum(r) == 66500 - 6650 == 59850


def test_ratear_desconto_sobra_vai_para_o_maior():
    r = cr.ratear_desconto([10000, 10000, 10001], 100)
    assert sum(r) == 30001 - 100
    assert cr.ratear_desconto([5000], 0) == [5000]


def test_parcelas_do_pacote():
    assert cr.parcelas_do_pacote(100000, 3, "2026-01-31") == [
        ("2026-01-31", 33334), ("2026-02-28", 33333), ("2026-03-31", 33333)]
