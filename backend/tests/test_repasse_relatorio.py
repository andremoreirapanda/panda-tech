"""Financeiro etapa 3, task 3: relatório de atendimentos do repasse (cálculo, sem gravar)."""
import db
import planos_padrao
import cobranca_service
import repasse_service
from factories import DuasClinicas, novo_paciente

HOJE = "2026-11-12"
DE, ATE = "2026-10-01", "2026-10-31"


def _cenario(db_ctx):
    cen = DuasClinicas()
    planos_padrao.criar_planos_padrao_para_teste()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id IN (?, ?)", (cen.org_a, cen.org_b))
    db_ctx.execute("UPDATE usuarios SET tipo_registro = 'CRFa', numero_registro = '2-12345' WHERE id = ?",
                   (cen.prof_a1["id"],))
    cen.proc_230 = db.execute("INSERT INTO procedimentos (organizacao_id, nome, valor_centavos) "
                              "VALUES (?, 'Avaliação', 23000)", (cen.org_a,))
    cen.proc_150 = db.execute("INSERT INTO procedimentos (organizacao_id, nome, valor_centavos) "
                              "VALUES (?, 'Sessão', 15000)", (cen.org_a,))
    return cen


def _org(cen, **campos):
    sets = ", ".join(f"{k} = ?" for k in campos)
    db.execute(f"UPDATE organizacoes SET {sets} WHERE id = ?", (*campos.values(), cen.org_a))


def _regra(cen, prof, modo="percentual", pct=None, valor=None, proc=None, tipo=None, org=None):
    return db.execute(
        """INSERT INTO regras_repasse (organizacao_id, profissional_id, procedimento_id, tipo_acordo, modo,
                                       percentual_centesimos, valor_centavos) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (org or cen.org_a, prof["id"], proc, tipo, modo, pct, valor))


def _acordo(cen, tipo, paciente=None, especialidade="*", inicio="2026-10-01", org=None, **extra):
    campos = {"organizacao_id": org or cen.org_a, "paciente_id": paciente or cen.paciente_a1,
              "especialidade": especialidade, "tipo": tipo, "inicio": inicio}
    if tipo == "avulsa":
        campos["ciclo"] = "consulta"
    campos.update(extra)
    cols = ", ".join(campos)
    return db.execute(f"INSERT INTO acordos_pagamento ({cols}) VALUES ({', '.join('?' for _ in campos)})",
                      tuple(campos.values()))


_PADRAO = object()


def _consulta(cen, dia, prof=None, proc=_PADRAO, valor=23000, status="realizada", esp="Fonoaudiologia",
              paciente=None, hora="09:00:00"):
    return db.execute(
        """INSERT INTO consultas (paciente_id, profissional_id, data_hora, status, especialidade,
                                  procedimento_id, procedimento_valor_centavos)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (paciente or cen.paciente_a1, (prof or cen.prof_a1)["id"], f"{dia} {hora}", status, esp,
         cen.proc_230 if proc is _PADRAO else proc, valor))


def _sync(org):
    cobranca_service.sincronizar(org, HOJE)


def _cobranca_da(consulta_id):
    return db.query_one("""SELECT cb.* FROM cobrancas cb JOIN cobranca_itens i ON i.cobranca_id = cb.id
                           WHERE i.consulta_id = ?""", (consulta_id,))


def _pagar(cobranca_id, valor=None, status="pago"):
    cb = db.query_one("SELECT * FROM cobrancas WHERE id = ?", (cobranca_id,))
    if valor is None:
        valor = cb["valor_centavos"] - cb["desconto_centavos"]
    db.execute("INSERT INTO pagamentos (cobranca_id, valor_centavos, forma, pago_em) "
               "VALUES (?, ?, 'dinheiro', '2026-11-10 10:00:00')", (cobranca_id, valor))
    db.execute("UPDATE cobrancas SET status = ? WHERE id = ?", (status, cobranca_id))


def _rel(cen, de=DE, ate=ATE, org=None, **kw):
    return repasse_service.relatorio(org or cen.org_a, de, ate, hoje=HOJE, **kw)


def _prof(rel, prof):
    for p in rel["profissionais"]:
        if p["profissional_id"] == prof["id"]:
            return p
    return None


def _todas_sessoes(rel):
    return [s for p in rel["profissionais"] for s in p["sessoes"]]


# ------------------------------------------------------------------ avulsa

def test_avulsa_paga_entra_com_percentual(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=6500)
    _acordo(cen, "avulsa")
    c1 = _consulta(cen, "2026-10-05")
    c2 = _consulta(cen, "2026-10-12")
    _sync(cen.org_a)
    _pagar(_cobranca_da(c1)["id"])
    _pagar(_cobranca_da(c2)["id"])
    rel = _rel(cen)
    assert rel["de"] == DE and rel["ate"] == ATE and rel["base"] == "procedimento"
    p = _prof(rel, cen.prof_a1)
    assert p["nome"] == "Prof A1" and p["registro"] == "CRFa 2-12345"
    assert [s["consulta_id"] for s in p["sessoes"]] == [c1, c2]
    for s in p["sessoes"]:
        assert s["tipo_acordo"] == "avulsa"
        assert s["base_centavos"] == 23000
        assert s["profissional_centavos"] == 14950
        assert s["clinica_centavos"] == 8050
        assert s["regra_rotulo"] == "65%"
        assert s["especialidade"] == "Fonoaudiologia"
        assert s["paciente_nome"] == "Paciente A1"
    assert p["total_sessoes_centavos"] == 46000
    assert p["total_profissional_centavos"] == 29900
    assert p["a_pagar_centavos"] == 29900
    assert p["sem_regra"] is False
    assert p["por_especialidade"] == [{"especialidade": "Fonoaudiologia", "quantidade": 2,
                                       "base_centavos": 46000, "profissional_centavos": 29900}]
    assert rel["aguardando"] == [] and rel["ja_pagas"] == []


def test_avulsa_paga_em_parte_aguarda(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=6500)
    _acordo(cen, "avulsa")
    c1 = _consulta(cen, "2026-10-05")
    _sync(cen.org_a)
    _pagar(_cobranca_da(c1)["id"], valor=10000, status="parcial")
    rel = _rel(cen)
    assert _todas_sessoes(rel) == []
    assert len(rel["aguardando"]) == 1
    ag = rel["aguardando"][0]
    assert ag["consulta_id"] == c1 and ag["motivo"] == "Pago em parte"
    assert ag["paciente_nome"] == "Paciente A1" and ag["profissional_nome"] == "Prof A1"


def test_avulsa_em_aberto_aguarda(client, db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa")
    c1 = _consulta(cen, "2026-10-05")
    rel = _rel(cen)
    assert [(a["consulta_id"], a["motivo"]) for a in rel["aguardando"]] == [(c1, "Cobrança em aberto")]


def test_desconto_reduz_a_base(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    _acordo(cen, "avulsa", ciclo="mensal")
    c1 = _consulta(cen, "2026-10-05", proc=cen.proc_230, valor=23000)
    c2 = _consulta(cen, "2026-10-12", proc=cen.proc_230, valor=23000)
    c3 = _consulta(cen, "2026-10-19", proc=cen.proc_150, valor=15000)
    _sync(cen.org_a)
    cid = _cobranca_da(c1)["id"]
    assert _cobranca_da(c3)["id"] == cid
    db.execute("UPDATE cobrancas SET desconto_centavos = 6100 WHERE id = ?", (cid,))
    _pagar(cid)
    p = _prof(_rel(cen), cen.prof_a1)
    bases = {s["consulta_id"]: s["base_centavos"] for s in p["sessoes"]}
    assert sum(bases.values()) == 54900
    assert bases == {c1: 20700, c2: 20700, c3: 13500}
    assert [s["profissional_centavos"] for s in p["sessoes"]] == [10350, 10350, 6750]


def test_item_retirado_da_cobranca_nao_aparece(client, db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="mensal")
    c1 = _consulta(cen, "2026-10-05")
    c2 = _consulta(cen, "2026-10-12")
    _sync(cen.org_a)
    db.execute("DELETE FROM cobranca_itens WHERE consulta_id = ?", (c2,))
    db.execute("INSERT INTO consulta_decisao_cobranca (consulta_id, decisao) VALUES (?, 'nao_cobrar')", (c2,))
    _pagar(_cobranca_da(c1)["id"])
    rel = _rel(cen)
    assert [s["consulta_id"] for s in _todas_sessoes(rel)] == [c1]
    assert rel["aguardando"] == []


# ------------------------------------------------------------------ pacote

def test_pacote_libera_na_ordem(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    acordo = _acordo(cen, "pacote", valor_centavos=100000, sessoes_total=10, parcelas=2,
                     primeiro_vencimento="2026-10-05")
    parcela = db.execute("""INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status,
                                                   organizacao_id, acordo_id, tipo)
                            VALUES (?, 'Pacote 1/2', 50000, '2026-10-05', 'pendente', ?, ?, 'pacote')""",
                         (cen.paciente_a1, cen.org_a, acordo))
    db.execute("""INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status,
                                         organizacao_id, acordo_id, tipo)
                  VALUES (?, 'Pacote 2/2', 50000, '2026-11-05', 'pendente', ?, ?, 'pacote')""",
               (cen.paciente_a1, cen.org_a, acordo))
    consultas = [_consulta(cen, f"2026-10-{d:02d}") for d in (2, 9, 16, 23, 30)]
    _sync(cen.org_a)
    _pagar(parcela, valor=35000, status="parcial")
    # um pagamento estornado não conta
    db.execute("INSERT INTO pagamentos (cobranca_id, valor_centavos, forma, estornado_em) "
               "VALUES (?, 15000, 'dinheiro', '2026-11-11 10:00:00')", (parcela,))

    _org(cen, fin_repasse_base="rateado")
    rel = _rel(cen)
    p = _prof(rel, cen.prof_a1)
    assert [s["consulta_id"] for s in p["sessoes"]] == consultas[:3]
    assert [s["sessao_numero"] for s in p["sessoes"]] == [1, 2, 3]
    assert all(s["sessao_total"] == 10 and s["tipo_acordo"] == "pacote" for s in p["sessoes"])
    assert [s["base_centavos"] for s in p["sessoes"]] == [10000, 10000, 10000]
    assert [(a["consulta_id"], a["motivo"]) for a in rel["aguardando"]] == [
        (consultas[3], "Pacote: pago até a sessão 3"), (consultas[4], "Pacote: pago até a sessão 3")]

    _org(cen, fin_repasse_base="procedimento")
    rel = _rel(cen)
    assert rel["base"] == "procedimento"
    assert [s["base_centavos"] for s in _prof(rel, cen.prof_a1)["sessoes"]] == [23000, 23000, 23000]


# ------------------------------------------------------------------ mensalidade

def test_mensalidade_paga_rateada(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    _org(cen, fin_repasse_base="rateado")
    acordo = _acordo(cen, "mensalidade", valor_centavos=80000, dia_vencimento=10)
    consultas = [_consulta(cen, f"2026-10-{d:02d}") for d in (6, 13, 20, 27)]
    _sync(cen.org_a)
    rel = _rel(cen)
    assert _todas_sessoes(rel) == []
    assert [(a["consulta_id"], a["motivo"]) for a in rel["aguardando"]] == [
        (c, "Mensalidade de 10/2026 em aberto") for c in consultas]

    out = db.query_one("SELECT id FROM cobrancas WHERE acordo_id = ? AND tipo = 'mensalidade' "
                       "AND periodo_inicio = '2026-10-01'", (acordo,))
    _pagar(out["id"])
    rel = _rel(cen)
    p = _prof(rel, cen.prof_a1)
    assert [s["consulta_id"] for s in p["sessoes"]] == consultas
    assert [s["base_centavos"] for s in p["sessoes"]] == [20000] * 4
    assert all(s["tipo_acordo"] == "mensalidade" for s in p["sessoes"])
    assert rel["aguardando"] == []

    _org(cen, fin_repasse_base="procedimento")
    db.execute("UPDATE cobrancas SET desconto_centavos = 8000 WHERE id = ?", (out["id"],))
    p = _prof(_rel(cen), cen.prof_a1)
    assert [s["base_centavos"] for s in p["sessoes"]] == [20700] * 4   # 23000 × (1 − 8000/80000)


def _mensalidade_de(acordo, mes):
    return db.query_one("SELECT * FROM cobrancas WHERE acordo_id = ? AND tipo = 'mensalidade' "
                        "AND periodo_inicio = ?", (acordo, mes))


def test_mensalidade_rateada_mes_em_andamento_aguarda(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    _org(cen, fin_repasse_base="rateado")
    acordo = _acordo(cen, "mensalidade", valor_centavos=80000, dia_vencimento=10, inicio="2026-11-01")
    c1 = _consulta(cen, "2026-11-03")
    _sync(cen.org_a)
    _pagar(_mensalidade_de(acordo, "2026-11-01")["id"])
    rel = _rel(cen, de="2026-11-01", ate="2026-11-30")
    assert _todas_sessoes(rel) == []
    assert [(a["consulta_id"], a["motivo"]) for a in rel["aguardando"]] == [
        (c1, "Mensalidade do mês em andamento")]
    # base 'procedimento' não espera o fim do mês
    _org(cen, fin_repasse_base="procedimento")
    rel = _rel(cen, de="2026-11-01", ate="2026-11-30")
    assert [s["consulta_id"] for s in _todas_sessoes(rel)] == [c1]


def test_mensalidade_rateada_depois_de_repasse_parcial_divide_so_o_resto(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    _org(cen, fin_repasse_base="rateado")
    acordo = _acordo(cen, "mensalidade", valor_centavos=80000, dia_vencimento=10)
    c1 = _consulta(cen, "2026-10-06")
    _sync(cen.org_a)
    _pagar(_mensalidade_de(acordo, "2026-10-01")["id"])
    rid = db.execute("""INSERT INTO repasses (organizacao_id, profissional_id, periodo_de, periodo_ate, pago_em)
                        VALUES (?, ?, '2026-10-01', '2026-10-15', '2026-10-16 10:00:00')""",
                     (cen.org_a, cen.prof_a1["id"]))
    db.execute("""INSERT INTO repasse_itens (repasse_id, consulta_id, especialidade, base_centavos)
                  VALUES (?, ?, 'Fonoaudiologia', 50000)""", (rid, c1))
    # sessões finalizadas depois do primeiro fechamento
    c2 = _consulta(cen, "2026-10-13")
    c3 = _consulta(cen, "2026-10-20")
    sessoes = _todas_sessoes(_rel(cen))
    assert [s["consulta_id"] for s in sessoes] == [c2, c3]
    assert [s["base_centavos"] for s in sessoes] == [15000, 15000]
    assert 50000 + sum(s["base_centavos"] for s in sessoes) <= 80000


def test_mensalidade_rateada_repasse_acima_do_cobrado_zera_o_resto(client, db_ctx):
    cen = _cenario(db_ctx)
    _org(cen, fin_repasse_base="rateado")
    acordo = _acordo(cen, "mensalidade", valor_centavos=80000, dia_vencimento=10)
    c1 = _consulta(cen, "2026-10-06")
    _sync(cen.org_a)
    _pagar(_mensalidade_de(acordo, "2026-10-01")["id"])
    rid = db.execute("""INSERT INTO repasses (organizacao_id, profissional_id, periodo_de, periodo_ate, pago_em)
                        VALUES (?, ?, '2026-10-01', '2026-10-15', '2026-10-16 10:00:00')""",
                     (cen.org_a, cen.prof_a1["id"]))
    db.execute("INSERT INTO repasse_itens (repasse_id, consulta_id, base_centavos) VALUES (?, ?, 90000)", (rid, c1))
    c2 = _consulta(cen, "2026-10-13")
    assert [(s["consulta_id"], s["base_centavos"]) for s in _todas_sessoes(_rel(cen))] == [(c2, 0)]


def test_sessao_incluida_antes_do_inicio_vai_para_o_primeiro_mes(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    _org(cen, fin_repasse_base="rateado")
    antes = _consulta(cen, "2026-09-20")
    acordo = _acordo(cen, "mensalidade", valor_centavos=80000, dia_vencimento=10, inicio="2026-10-15")
    db.execute("INSERT INTO consulta_acordo_incluida (consulta_id, acordo_id, incluida) VALUES (?, ?, 1)",
               (antes, acordo))
    depois = _consulta(cen, "2026-10-20")
    _sync(cen.org_a)
    rel = _rel(cen, de="2026-09-01", ate="2026-10-31")
    assert [(a["consulta_id"], a["motivo"]) for a in rel["aguardando"]] == [
        (antes, "Mensalidade de 10/2026 em aberto"), (depois, "Mensalidade de 10/2026 em aberto")]
    cob = _mensalidade_de(acordo, "2026-10-01")
    _pagar(cob["id"])
    rel = _rel(cen, de="2026-09-01", ate="2026-10-31")
    sessoes = _todas_sessoes(rel)
    assert [s["consulta_id"] for s in sessoes] == [antes, depois]
    assert sum(s["base_centavos"] for s in sessoes) == cob["valor_centavos"]
    assert rel["aguardando"] == []


def test_falta_cobrada_conta_no_divisor_sem_repasse(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    _org(cen, fin_repasse_base="rateado", fin_cobrar_falta=1, fin_repasse_falta=0)
    acordo = _acordo(cen, "mensalidade", valor_centavos=80000, dia_vencimento=10)
    feitas = [_consulta(cen, f"2026-10-{d:02d}") for d in (6, 13, 20)]
    _consulta(cen, "2026-10-27", status="faltou")
    _sync(cen.org_a)
    _pagar(_mensalidade_de(acordo, "2026-10-01")["id"])
    rel = _rel(cen)
    sessoes = _todas_sessoes(rel)
    assert [s["consulta_id"] for s in sessoes] == feitas
    assert [s["base_centavos"] for s in sessoes] == [20000] * 3
    assert rel["aguardando"] == []


def test_mensalidade_nao_gerada_aguarda(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    _acordo(cen, "mensalidade", valor_centavos=80000, dia_vencimento=10)
    c1 = _consulta(cen, "2026-10-06")
    _sync(cen.org_a)
    db.execute("DELETE FROM cobrancas WHERE tipo = 'mensalidade' AND periodo_inicio = '2026-10-01'")
    # sem sincronizar de novo: simula o mês ainda sem cobrança
    monkeypatch.setattr(repasse_service.cobranca_service, "sincronizar", lambda *a, **k: None)
    rel = _rel(cen)
    assert [(a["consulta_id"], a["motivo"]) for a in rel["aguardando"]] == [
        (c1, "Mensalidade do mês ainda não gerada")]


# ------------------------------------------------------------------ faltas

def test_falta_so_com_as_duas_chaves(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=6500)
    _acordo(cen, "avulsa")
    _org(cen, fin_cobrar_falta=1)
    cobrada = _consulta(cen, "2026-10-05", status="faltou")
    _sync(cen.org_a)
    _pagar(_cobranca_da(cobrada)["id"])
    _org(cen, fin_cobrar_falta=0)
    nao_cobrada = _consulta(cen, "2026-10-12", status="faltou")
    _sync(cen.org_a)
    assert _cobranca_da(nao_cobrada) is None

    _org(cen, fin_repasse_falta=0)
    rel = _rel(cen)
    assert _todas_sessoes(rel) == [] and rel["aguardando"] == []

    _org(cen, fin_repasse_falta=1)
    rel = _rel(cen)
    assert [s["consulta_id"] for s in _todas_sessoes(rel)] == [cobrada]
    assert rel["aguardando"] == []


# ------------------------------------------------------------------ regras

def test_excecao_por_procedimento_vence_padrao(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=6500)
    _regra(cen, cen.prof_a1, pct=6000, proc=cen.proc_150)
    _acordo(cen, "avulsa")
    c1 = _consulta(cen, "2026-10-05", proc=cen.proc_230, valor=23000)
    c2 = _consulta(cen, "2026-10-12", proc=cen.proc_150, valor=15000)
    _sync(cen.org_a)
    _pagar(_cobranca_da(c1)["id"])
    _pagar(_cobranca_da(c2)["id"])
    p = _prof(_rel(cen), cen.prof_a1)
    por = {s["consulta_id"]: s for s in p["sessoes"]}
    assert por[c1]["profissional_centavos"] == 14950 and por[c1]["regra_rotulo"] == "65%"
    assert por[c2]["profissional_centavos"] == 9000 and por[c2]["regra_rotulo"] == "60%"
    assert por[c2]["regra"]["procedimento_id"] == cen.proc_150


def test_sem_regra_a_definir(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a2, modo="fixo", valor=5000, proc=cen.proc_150)
    _acordo(cen, "avulsa")
    c1 = _consulta(cen, "2026-10-05", prof=cen.prof_a2, proc=cen.proc_230, valor=23000)
    c2 = _consulta(cen, "2026-10-12", prof=cen.prof_a2, proc=cen.proc_150, valor=15000)
    _sync(cen.org_a)
    _pagar(_cobranca_da(c1)["id"])
    _pagar(_cobranca_da(c2)["id"])
    p = _prof(_rel(cen), cen.prof_a2)
    por = {s["consulta_id"]: s for s in p["sessoes"]}
    assert por[c1]["regra"] is None and por[c1]["regra_rotulo"] == "a definir"
    assert por[c1]["profissional_centavos"] is None and por[c1]["clinica_centavos"] is None
    assert por[c2]["profissional_centavos"] == 5000 and por[c2]["clinica_centavos"] == 10000
    assert por[c2]["regra_rotulo"] == "R$ 50,00 fixo"
    assert p["sem_regra"] is True
    assert p["total_profissional_centavos"] == 5000
    assert p["a_pagar_centavos"] == 5000
    assert p["registro"] == ""


# ------------------------------------------------------------------ período

def test_pago_antes_do_periodo_entra_ate_o_fim(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=6500)
    _acordo(cen, "avulsa", inicio="2026-08-01")
    antiga = _consulta(cen, "2026-08-20")
    depois = _consulta(cen, "2026-11-03")
    _sync(cen.org_a)
    _pagar(_cobranca_da(antiga)["id"])
    _pagar(_cobranca_da(depois)["id"])
    rel = _rel(cen)
    assert [s["consulta_id"] for s in _todas_sessoes(rel)] == [antiga]
    assert rel["aguardando"] == []


def test_aguardando_so_do_periodo(client, db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", inicio="2026-08-01")
    _consulta(cen, "2026-08-20")
    c2 = _consulta(cen, "2026-10-20")
    rel = _rel(cen)
    assert [a["consulta_id"] for a in rel["aguardando"]] == [c2]


def test_sem_acordo_aguarda(client, db_ctx):
    cen = _cenario(db_ctx)
    c1 = _consulta(cen, "2026-10-20")
    rel = _rel(cen)
    assert [(a["consulta_id"], a["motivo"]) for a in rel["aguardando"]] == [(c1, "Sessão sem acordo")]


def test_ja_pagas_e_ajustes(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=6500)
    _acordo(cen, "avulsa")
    c1 = _consulta(cen, "2026-10-05")
    c2 = _consulta(cen, "2026-10-12")
    _sync(cen.org_a)
    _pagar(_cobranca_da(c1)["id"])
    _pagar(_cobranca_da(c2)["id"])
    rid = db.execute("""INSERT INTO repasses (organizacao_id, profissional_id, periodo_de, periodo_ate, pago_em)
                        VALUES (?, ?, '2026-10-01', '2026-10-10', '2026-10-11 10:00:00')""",
                     (cen.org_a, cen.prof_a1["id"]))
    db.execute("""INSERT INTO repasse_itens (repasse_id, consulta_id, especialidade, base_centavos)
                  VALUES (?, ?, 'Fonoaudiologia', 23000)""", (rid, c1))
    db.execute("""INSERT INTO repasse_ajustes (organizacao_id, profissional_id, descricao, valor_centavos, origem)
                  VALUES (?, ?, 'Vale', -5000, 'manual')""", (cen.org_a, cen.prof_a1["id"]))
    db.execute("""INSERT INTO repasse_ajustes (organizacao_id, profissional_id, repasse_id, descricao,
                                               valor_centavos, origem)
                  VALUES (?, ?, ?, 'Antigo', -999, 'manual')""", (cen.org_a, cen.prof_a1["id"], rid))
    rel = _rel(cen)
    p = _prof(rel, cen.prof_a1)
    assert [s["consulta_id"] for s in p["sessoes"]] == [c2]
    assert rel["ja_pagas"] == [{"consulta_id": c1, "pago_em": "2026-10-11 10:00:00", "repasse_id": rid}]
    assert [(a["descricao"], a["valor_centavos"], a["origem"]) for a in p["ajustes"]] == [("Vale", -5000, "manual")]
    assert p["total_ajustes_centavos"] == -5000
    assert p["a_pagar_centavos"] == 14950 - 5000


def test_profissional_so_com_ajuste_aparece(client, db_ctx):
    cen = _cenario(db_ctx)
    db.execute("""INSERT INTO repasse_ajustes (organizacao_id, profissional_id, descricao, valor_centavos, origem)
                  VALUES (?, ?, 'Estorno', -3000, 'estorno')""", (cen.org_a, cen.prof_a2["id"]))
    p = _prof(_rel(cen), cen.prof_a2)
    assert p["sessoes"] == [] and p["a_pagar_centavos"] == -3000


# ------------------------------------------------------------------ filtros e isolamento

def test_filtros_profissional_e_especialidade(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=6500)
    _regra(cen, cen.prof_a2, pct=6000)
    _acordo(cen, "avulsa")
    c1 = _consulta(cen, "2026-10-05", prof=cen.prof_a1, esp="Fonoaudiologia")
    c2 = _consulta(cen, "2026-10-06", prof=cen.prof_a2, esp="Terapia Ocupacional")
    a1 = _consulta(cen, "2026-10-07", prof=cen.prof_a1, esp="Fonoaudiologia")
    a2 = _consulta(cen, "2026-10-08", prof=cen.prof_a2, esp="Terapia Ocupacional")
    _sync(cen.org_a)
    _pagar(_cobranca_da(c1)["id"])
    _pagar(_cobranca_da(c2)["id"])

    rel = _rel(cen, profissional_id=cen.prof_a2["id"])
    assert [p["profissional_id"] for p in rel["profissionais"]] == [cen.prof_a2["id"]]
    assert [s["consulta_id"] for s in _todas_sessoes(rel)] == [c2]
    assert [a["consulta_id"] for a in rel["aguardando"]] == [a2]

    rel = _rel(cen, especialidade=" terapia ocupacional ")
    assert [s["consulta_id"] for s in _todas_sessoes(rel)] == [c2]
    assert [a["consulta_id"] for a in rel["aguardando"]] == [a2]

    rel = _rel(cen)
    assert sorted(s["consulta_id"] for s in _todas_sessoes(rel)) == [c1, c2]
    assert sorted(a["consulta_id"] for a in rel["aguardando"]) == [a1, a2]


def test_outra_clinica_nunca_aparece(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=6500)
    _regra(cen, cen.prof_b1, pct=6500, org=cen.org_b)
    pac_b = novo_paciente(cen.org_b, "Paciente B1")
    _acordo(cen, "avulsa", paciente=pac_b, org=cen.org_b)
    cb1 = _consulta(cen, "2026-10-05", prof=cen.prof_b1, paciente=pac_b, proc=None, valor=20000)
    _consulta(cen, "2026-10-06", prof=cen.prof_b1, paciente=pac_b, proc=None, valor=20000)
    db.execute("INSERT INTO repasse_ajustes (organizacao_id, profissional_id, descricao, valor_centavos, origem) "
               "VALUES (?, ?, 'B', 100, 'manual')", (cen.org_b, cen.prof_b1["id"]))
    _sync(cen.org_b)
    _pagar(_cobranca_da(cb1)["id"])
    rel = _rel(cen)
    assert rel["profissionais"] == [] and rel["aguardando"] == [] and rel["ja_pagas"] == []
    rel_b = _rel(cen, org=cen.org_b)
    assert [s["consulta_id"] for s in _todas_sessoes(rel_b)] == [cb1]


# ------------------------------------------------------------------ período padrão

def test_validar_periodo_padrao_mes_anterior():
    assert repasse_service.validar_periodo("", "", "2026-11-12") == ("2026-10-01", "2026-10-31")
    assert repasse_service.validar_periodo(None, None, "2026-01-05") == ("2025-12-01", "2025-12-31")
    assert repasse_service.validar_periodo("2026-03-01", "2026-03-15", "2026-11-12") == ("2026-03-01", "2026-03-15")
    assert repasse_service.validar_periodo("2026-13-01", "", "2026-11-12") == "Data inválida."
    assert repasse_service.validar_periodo("2026-03-02", "2026-03-01", "2026-11-12") == "A data inicial é depois da final."
    assert repasse_service.validar_periodo("2024-01-01", "2026-01-01", "2026-11-12") == "Escolha um período de até 1 ano."
