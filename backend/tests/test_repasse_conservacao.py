"""Financeiro etapa 3, revisão final (16/11/2026): o repasse nunca passa do que a família pagou,
mesmo quando a numeração do pacote ou as sessões do mês mudam depois de um fechamento."""
import db
import repasse_service
from test_repasse_relatorio import (DE, ATE, HOJE, _cenario, _regra, _acordo, _consulta, _sync, _rel, _prof,
                                    _org, _mensalidade_de)
from test_repasse_fechamento import _pagar, _fechar


def _pacote(cen, valor=40000, total=4, pago=None):
    """Pacote de `total` sessões por `valor`, com uma parcela de metade do valor (só ela é paga)."""
    acordo = _acordo(cen, "pacote", valor_centavos=valor, sessoes_total=total, parcelas=1,
                     primeiro_vencimento="2026-10-05")
    p1 = db.execute("""INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status,
                       organizacao_id, acordo_id, tipo) VALUES (?, 'P', ?, '2026-10-05', 'pendente', ?, ?, 'pacote')""",
                    (cen.paciente_a1, pago if pago is not None else valor // 2, cen.org_a, acordo))
    return acordo, p1


def _ids(cen):
    p = _prof(_rel(cen), cen.prof_a1)
    return [s["consulta_id"] for s in p["sessoes"]] if p else []


def test_pacote_sessao_registrada_atrasada_nao_entra_de_novo(client, db_ctx):
    """4 sessões por R$ 400, R$ 200 pagos: 2 liberadas e repassadas. Uma sessão anterior registrada
    depois vira a nº 2 na renumeração, mas o pago continua liberando só 2 — nada novo entra."""
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    _org(cen, fin_repasse_base="rateado")
    acordo, p1 = _pacote(cen)
    a = _consulta(cen, "2026-10-02")
    atrasada = _consulta(cen, "2026-10-09", status="agendada")
    b = _consulta(cen, "2026-10-16")
    _sync(cen.org_a)
    _pagar(p1)
    assert _ids(cen) == [a, b]
    _fechar(cen, [a, b])
    itens = db.query("SELECT consulta_id, acordo_id, mes FROM repasse_itens ORDER BY consulta_id")
    assert [(i["consulta_id"], i["acordo_id"], i["mes"]) for i in itens] == [(a, acordo, None), (b, acordo, None)]

    db.execute("UPDATE consultas SET status = 'realizada' WHERE id = ?", (atrasada,))
    rel = _rel(cen)
    assert _prof(rel, cen.prof_a1) is None
    assert [x["consulta_id"] for x in rel["aguardando"]] == [atrasada]


def test_pacote_realizada_que_vira_falta_libera_a_seguinte(client, db_ctx):
    """Decisão 3 (22/11/2026): a repassada que vira falta sem repasse sai do "já repassado" (a
    vaga vai para a seguinte) e ganha o −valor do profissional (ajuste `status`)."""
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    _org(cen, fin_repasse_base="rateado")
    acordo, p1 = _pacote(cen)
    a = _consulta(cen, "2026-10-02")
    b = _consulta(cen, "2026-10-09")
    c = _consulta(cen, "2026-10-16")
    _sync(cen.org_a)
    _pagar(p1)
    assert _ids(cen) == [a, b]
    _fechar(cen, [a, b])
    db.execute("UPDATE consultas SET status = 'faltou' WHERE id = ?", (a,))
    _sync(cen.org_a)
    assert _ids(cen) == [c]
    assert [(x["consulta_id"], x["origem"], x["valor_centavos"]) for x in db.query(
        "SELECT consulta_id, origem, valor_centavos FROM repasse_ajustes")] == [(a, "status", -5000)]
    # pagar o resto: c continua com a base da 2ª vaga (a falta não conta mais)
    p2 = db.execute("""INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status,
                       organizacao_id, acordo_id, tipo) VALUES (?, 'P2', 20000, '2026-10-05', 'pendente', ?, ?, 'pacote')""",
                    (cen.paciente_a1, cen.org_a, acordo))
    _pagar(p2)
    p = _prof(_rel(cen), cen.prof_a1)
    assert [s["consulta_id"] for s in p["sessoes"]] == [c]
    assert p["sessoes"][0]["base_centavos"] == 10000


def test_mensalidade_rateada_com_falta_depois_do_fechamento_nao_passa_do_mes(client, db_ctx):
    """R$ 800 no mês, 2 sessões repassadas (R$ 400 cada). Uma vira falta (sem repasse) e outra é
    finalizada depois: a falta sai do "já repassado" (decisão 3) e ganha o −R$ 200 dela, então a
    finalizada leva os R$ 400 que sobram — no total, o mês continua em R$ 800."""
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    _org(cen, fin_repasse_base="rateado")
    acordo = _acordo(cen, "mensalidade", valor_centavos=80000, dia_vencimento=10)
    a = _consulta(cen, "2026-10-06")
    b = _consulta(cen, "2026-10-13")
    atrasada = _consulta(cen, "2026-10-20", status="agendada")
    _sync(cen.org_a)
    _pagar(_mensalidade_de(acordo, "2026-10-01")["id"])
    assert _ids(cen) == [a, b]
    _fechar(cen, [a, b])
    itens = db.query("SELECT acordo_id, mes, base_centavos FROM repasse_itens ORDER BY consulta_id")
    assert [(i["acordo_id"], i["mes"], i["base_centavos"]) for i in itens] == [
        (acordo, "2026-10-01", 40000), (acordo, "2026-10-01", 40000)]

    db.execute("UPDATE consultas SET status = 'faltou' WHERE id = ?", (a,))
    db.execute("UPDATE consultas SET status = 'realizada' WHERE id = ?", (atrasada,))
    p = _prof(_rel(cen), cen.prof_a1)
    assert [(s["consulta_id"], s["base_centavos"]) for s in p["sessoes"]] == [(atrasada, 40000)]
    assert [(x["origem"], x["valor_centavos"]) for x in p["ajustes"]] == [("status", -20000)]
    assert db.query_one("SELECT consulta_id FROM repasse_ajustes")["consulta_id"] == a


def test_pacote_base_nunca_passa_do_valor_liquido(client, db_ctx):
    """Base 'procedimento': 3 sessões de R$ 230 num pacote de R$ 400 pago — a soma para em R$ 400."""
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    acordo, p1 = _pacote(cen, valor=40000, total=3, pago=40000)
    cs = [_consulta(cen, f"2026-10-{d:02d}") for d in (2, 9, 16)]
    _sync(cen.org_a)
    _pagar(p1)
    p = _prof(_rel(cen), cen.prof_a1)
    assert [s["consulta_id"] for s in p["sessoes"]] == cs
    assert [s["base_centavos"] for s in p["sessoes"]] == [23000, 17000, 0]


def test_pacote_desconto_depois_de_repassar_limita_o_resto(client, db_ctx):
    """Rateado: R$ 400 / 4 = R$ 100 cada; 2 repassadas. Um desconto de R$ 150 depois deixa o
    pacote em R$ 250: as duas que faltam dividem só os R$ 50 que sobram."""
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    _org(cen, fin_repasse_base="rateado")
    acordo, p1 = _pacote(cen, pago=40000)
    cs = [_consulta(cen, f"2026-10-{d:02d}") for d in (2, 9)]
    _sync(cen.org_a)
    _pagar(p1)
    _fechar(cen, cs)
    cs += [_consulta(cen, f"2026-10-{d:02d}") for d in (16, 23)]
    _sync(cen.org_a)
    db.execute("UPDATE cobrancas SET desconto_centavos = 15000 WHERE id = ?", (p1,))
    p = _prof(_rel(cen), cen.prof_a1)
    assert [s["consulta_id"] for s in p["sessoes"]] == cs[2:]
    assert sum(s["base_centavos"] for s in p["sessoes"]) == 5000


def test_estorno_do_pacote_renumerado_tira_as_ultimas_repassadas(client, db_ctx):
    """Depois da renumeração, a sessão repassada perde o "pago" só se o pago libera menos
    sessões do que as repassadas — e saem as mais recentes."""
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    _org(cen, fin_repasse_base="rateado")
    acordo, p1 = _pacote(cen)
    a = _consulta(cen, "2026-10-02")
    atrasada = _consulta(cen, "2026-10-09", status="agendada")
    b = _consulta(cen, "2026-10-16")
    _sync(cen.org_a)
    _pagar(p1)
    _fechar(cen, [a, b])
    db.execute("UPDATE consultas SET status = 'realizada' WHERE id = ?", (atrasada,))
    _sync(cen.org_a)
    # a renumeração sozinha não é estorno
    assert repasse_service.avisar_estorno(p1) == 0
    # o pago cai para R$ 100 (libera 1): sai a repassada mais recente (b)
    db.execute("UPDATE pagamentos SET valor_centavos = 10000 WHERE cobranca_id = ?", (p1,))
    assert repasse_service.avisar_estorno(p1) == 1
    assert [x["consulta_id"] for x in db.query("SELECT consulta_id FROM repasse_ajustes")] == [b]
