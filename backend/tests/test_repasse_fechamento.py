"""Financeiro etapa 3, task 4: fechar repasse, ajustes, desfazer e aviso de estorno."""
import pytest

import db
import repasse_service
from conftest import autenticado
from test_repasse_relatorio import (DE, ATE, HOJE, _cenario, _regra, _acordo, _consulta, _sync,
                                    _cobranca_da, _rel, _prof, _todas_sessoes, _mensalidade_de, _org)


def _pagar(cobranca_id):
    cb = db.query_one("SELECT * FROM cobrancas WHERE id = ?", (cobranca_id,))
    pid = db.execute("INSERT INTO pagamentos (cobranca_id, valor_centavos, forma, pago_em) "
                     "VALUES (?, ?, 'dinheiro', '2026-11-10 10:00:00')",
                     (cobranca_id, cb["valor_centavos"] - cb["desconto_centavos"]))
    db.execute("UPDATE cobrancas SET status = 'pago' WHERE id = ?", (cobranca_id,))
    return pid


def _duas_avulsas_pagas(cen, pct=6500):
    _regra(cen, cen.prof_a1, pct=pct)
    _acordo(cen, "avulsa")
    c1 = _consulta(cen, "2026-10-05")
    c2 = _consulta(cen, "2026-10-12")
    _sync(cen.org_a)
    pagamentos = {c1: _pagar(_cobranca_da(c1)["id"]), c2: _pagar(_cobranca_da(c2)["id"])}
    return c1, c2, pagamentos


def _fechar(cen, ids, prof=None, de=DE, ate=ATE):
    return repasse_service.fechar(cen.org_a, (prof or cen.prof_a1)["id"], de, ate, ids, cen.gestor_a, hoje=HOJE)


def _contagens():
    return (db.query_one("SELECT COUNT(*) AS n FROM repasses")["n"],
            db.query_one("SELECT COUNT(*) AS n FROM repasse_itens")["n"])


def _ajuste(cen, valor=-5000, descricao="Vale", prof=None):
    return repasse_service.criar_ajuste(cen.org_a, (prof or cen.prof_a1)["id"], descricao, valor, cen.gestor_a)


# ------------------------------------------------------------------ fechar

def test_fechar_grava_valores_e_tira_do_relatorio(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, _ = _duas_avulsas_pagas(cen)
    _ajuste(cen, -5000)
    fech = _fechar(cen, [c2, c1])
    rid = fech["id"]
    r = db.query_one("SELECT * FROM repasses WHERE id = ?", (rid,))
    assert r["organizacao_id"] == cen.org_a and r["profissional_id"] == cen.prof_a1["id"]
    assert (r["periodo_de"], r["periodo_ate"]) == (DE, ATE)
    assert r["quantidade"] == 2
    assert r["total_sessoes_centavos"] == 46000
    assert r["total_profissional_centavos"] == 29900
    assert r["total_ajustes_centavos"] == -5000
    assert r["a_pagar_centavos"] == 24900
    assert r["pago_por"] == cen.gestor_a["id"] and r["pago_em"]
    itens = db.query("SELECT * FROM repasse_itens WHERE repasse_id = ? ORDER BY consulta_id", (rid,))
    assert [i["consulta_id"] for i in itens] == sorted([c1, c2])
    i = itens[0]
    assert i["paciente_nome"] == "Paciente A1" and i["especialidade"] == "Fonoaudiologia"
    assert i["tipo_acordo"] == "avulsa" and i["base_centavos"] == 23000
    assert i["regra_modo"] == "percentual" and i["regra_percentual_centesimos"] == 6500
    assert i["profissional_centavos"] == 14950 and i["clinica_centavos"] == 8050
    assert db.query_one("SELECT repasse_id FROM repasse_ajustes")["repasse_id"] == rid
    assert db.query_one("SELECT 1 FROM auditoria WHERE acao = 'repasse_pago' AND entidade_id = ?", (rid,))

    rel = _rel(cen)
    assert _todas_sessoes(rel) == [] and _prof(rel, cen.prof_a1) is None
    assert sorted(j["consulta_id"] for j in rel["ja_pagas"]) == sorted([c1, c2])
    assert all(j["repasse_id"] == rid for j in rel["ja_pagas"])

    assert [f["id"] for f in repasse_service.listar_fechamentos(cen.org_a)] == [rid]
    assert repasse_service.listar_fechamentos(cen.org_a, profissional_id=cen.prof_a2["id"]) == []
    assert repasse_service.listar_fechamentos(cen.org_b) == []
    det = repasse_service.detalhe_fechamento(cen.org_a, rid)
    assert det["profissional_nome"] == "Prof A1"
    assert len(det["itens"]) == 2 and [a["valor_centavos"] for a in det["ajustes"]] == [-5000]
    assert repasse_service.detalhe_fechamento(cen.org_b, rid) is None


def test_mudar_regra_nao_muda_fechamento(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, _ = _duas_avulsas_pagas(cen)
    rid = _fechar(cen, [c1, c2])["id"]
    db.execute("UPDATE regras_repasse SET percentual_centesimos = 7000")
    det = repasse_service.detalhe_fechamento(cen.org_a, rid)
    assert [i["regra_percentual_centesimos"] for i in det["itens"]] == [6500, 6500]
    assert [i["profissional_centavos"] for i in det["itens"]] == [14950, 14950]
    assert det["a_pagar_centavos"] == 29900


def test_relatorio_mudou_409(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, _ = _duas_avulsas_pagas(cen)
    _ajuste(cen)
    for ids in ([c1], [c1, c2, 999999], [c1, c1, c2], []):
        with pytest.raises(repasse_service.Conflito, match="O relatório mudou"):
            _fechar(cen, ids)
    assert _contagens() == (0, 0)
    assert db.query_one("SELECT repasse_id FROM repasse_ajustes")["repasse_id"] is None


def test_sessao_sem_regra_bloqueia(client, db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa")
    c1 = _consulta(cen, "2026-10-05")
    _sync(cen.org_a)
    _pagar(_cobranca_da(c1)["id"])
    with pytest.raises(ValueError, match="Defina a regra de repasse de Prof A1 antes de marcar como pago."):
        _fechar(cen, [c1])
    assert _contagens() == (0, 0)


def test_dois_fechamentos_da_mesma_sessao(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    c1, c2, _ = _duas_avulsas_pagas(cen)
    _ajuste(cen)
    velho = repasse_service.relatorio(cen.org_a, DE, ATE, profissional_id=cen.prof_a1["id"], hoje=HOJE)
    # outra aba fechou c1 enquanto esta conferia
    outro = db.execute("""INSERT INTO repasses (organizacao_id, profissional_id, periodo_de, periodo_ate, pago_em)
                          VALUES (?, ?, ?, ?, '2026-11-12 10:00:00')""", (cen.org_a, cen.prof_a1["id"], DE, ATE))
    db.execute("INSERT INTO repasse_itens (repasse_id, consulta_id, base_centavos) VALUES (?, ?, 23000)", (outro, c1))
    monkeypatch.setattr(repasse_service, "relatorio", lambda *a, **k: velho)
    with pytest.raises(repasse_service.Conflito, match="já foi incluída em outro repasse"):
        _fechar(cen, [c1, c2])
    assert _contagens() == (1, 1)
    assert db.query_one("SELECT repasse_id FROM repasse_ajustes")["repasse_id"] is None


def test_fechar_valida_periodo_e_profissional(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, _ = _duas_avulsas_pagas(cen)
    with pytest.raises(ValueError, match="A data inicial é depois da final."):
        _fechar(cen, [c1, c2], de=ATE, ate=DE)
    with pytest.raises(LookupError):
        _fechar(cen, [c1, c2], prof=cen.prof_b1)
    with pytest.raises(repasse_service.Conflito):
        _fechar(cen, [], prof=cen.prof_a2)   # nada a pagar
    assert _contagens() == (0, 0)


# ------------------------------------------------------------------ ajustes

def test_ajuste_entra_no_proximo_fechamento(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, _ = _duas_avulsas_pagas(cen)
    a1 = _ajuste(cen, 2500, "Bônus")
    assert a1["valor_centavos"] == 2500 and a1["repasse_id"] is None and a1["origem"] == "manual"
    rid =_fechar(cen, [c1, c2])["id"]
    a2 = _ajuste(cen, -1000, "Material")
    p = _prof(_rel(cen), cen.prof_a1)
    assert [a["id"] for a in p["ajustes"]] == [a2["id"]] and p["a_pagar_centavos"] == -1000
    assert db.query_one("SELECT repasse_id FROM repasse_ajustes WHERE id = ?", (a1["id"],))["repasse_id"] == rid
    # só ajuste: fecha também
    rid2 = _fechar(cen, [])["id"]
    r2 = db.query_one("SELECT * FROM repasses WHERE id = ?", (rid2,))
    assert r2["quantidade"] == 0 and r2["a_pagar_centavos"] == -1000 and r2["total_ajustes_centavos"] == -1000


def test_criar_ajuste_valida(client, db_ctx):
    cen = _cenario(db_ctx)
    for desc, valor in (("", 100), ("   ", 100), ("x" * 201, 100), ("Ok", 0), ("Ok", True), ("Ok", "100"),
                        ("Ok", 10.5), ("Ok", 10_000_001), ("Ok", -10_000_001)):
        with pytest.raises(ValueError):
            _ajuste(cen, valor, desc)
    with pytest.raises(LookupError):
        _ajuste(cen, 100, "Ok", prof=cen.prof_b1)
    assert _ajuste(cen, -10_000_000, "  Limite  ")["descricao"] == "Limite"
    assert db.query_one("SELECT COUNT(*) AS n FROM repasse_ajustes")["n"] == 1


def test_excluir_ajuste_ja_fechado_409(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, _ = _duas_avulsas_pagas(cen)
    fechado = _ajuste(cen, -5000)
    _fechar(cen, [c1, c2])
    pendente = _ajuste(cen, 300)
    with pytest.raises(repasse_service.Conflito):
        repasse_service.excluir_ajuste(cen.org_a, fechado["id"], cen.gestor_a)
    with pytest.raises(LookupError):
        repasse_service.excluir_ajuste(cen.org_b, pendente["id"], cen.gestor_b)
    repasse_service.excluir_ajuste(cen.org_a, pendente["id"], cen.gestor_a)
    assert [a["id"] for a in db.query("SELECT id FROM repasse_ajustes")] == [fechado["id"]]


# ------------------------------------------------------------------ desfazer

def test_desfazer_devolve_sessoes_e_ajustes(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, _ = _duas_avulsas_pagas(cen)
    aj = _ajuste(cen, -5000)
    rid = _fechar(cen, [c1, c2])["id"]
    for motivo in ("", "   ", None):
        with pytest.raises(ValueError):
            repasse_service.desfazer(cen.org_a, rid, motivo, cen.gestor_a)
    with pytest.raises(LookupError):
        repasse_service.desfazer(cen.org_b, rid, "erro", cen.gestor_b)
    repasse_service.desfazer(cen.org_a, rid, "Pago na conta errada", cen.gestor_a)
    assert _contagens() == (0, 0)
    assert db.query_one("SELECT repasse_id FROM repasse_ajustes WHERE id = ?", (aj["id"],))["repasse_id"] is None
    aud = db.query_one("SELECT * FROM auditoria WHERE acao = 'repasse_desfeito' AND entidade_id = ?", (rid,))
    assert aud and "Pago na conta errada" in aud["detalhes"] and aud["usuario_id"] == cen.gestor_a["id"]
    p = _prof(_rel(cen), cen.prof_a1)
    assert sorted(s["consulta_id"] for s in p["sessoes"]) == sorted([c1, c2])
    assert p["a_pagar_centavos"] == 29900 - 5000
    # e fecha de novo
    _fechar(cen, [c1, c2])


# ------------------------------------------------------------------ estorno

def _notificacoes_do(usuario):
    return db.query("SELECT * FROM notificacoes WHERE usuario_id = ? AND tipo = 'cobranca_familia'",
                    (usuario["id"],))


def test_estorno_depois_do_repasse_vira_ajuste_negativo_uma_vez(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/pagamento/{pagamentos[c1]}/estornar",
                                               json={"motivo": "Família pediu de volta"})
    assert r.status_code == 200
    assert repasse_service.avisar_estorno(_cobranca_da(c1)["id"]) == 0   # de novo: nada novo
    ajustes = db.query("SELECT * FROM repasse_ajustes")
    assert len(ajustes) == 1
    a = ajustes[0]
    assert a["origem"] == "estorno" and a["consulta_id"] == c1 and a["valor_centavos"] == -14950
    assert a["profissional_id"] == cen.prof_a1["id"] and a["repasse_id"] is None
    assert a["descricao"].startswith("Estorno: Paciente A1 em 05/10 — já repassado em ")
    assert len(_notificacoes_do(cen.gestor_a)) == 1
    p = _prof(_rel(cen), cen.prof_a1)
    assert p["sessoes"] == [] and p["a_pagar_centavos"] == -14950


def test_estorno_de_parcela_de_pacote_so_tira_as_ultimas(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    _org(cen, fin_repasse_base="rateado")
    acordo = _acordo(cen, "pacote", valor_centavos=40000, sessoes_total=4, parcelas=2,
                     primeiro_vencimento="2026-10-05")
    p1 = db.execute("""INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status,
                                              organizacao_id, acordo_id, tipo)
                       VALUES (?, 'Pacote 1/2', 20000, '2026-10-05', 'pendente', ?, ?, 'pacote')""",
                    (cen.paciente_a1, cen.org_a, acordo))
    p2 = db.execute("""INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status,
                                              organizacao_id, acordo_id, tipo)
                       VALUES (?, 'Pacote 2/2', 20000, '2026-11-05', 'pendente', ?, ?, 'pacote')""",
                    (cen.paciente_a1, cen.org_a, acordo))
    cs = [_consulta(cen, f"2026-10-{d:02d}") for d in (2, 9, 16, 23)]
    _sync(cen.org_a)
    _pagar(p1)
    pg2 = _pagar(p2)
    _fechar(cen, cs)
    db.execute("UPDATE pagamentos SET estornado_em = '2026-11-12 09:00:00' WHERE id = ?", (pg2,))
    db.execute("UPDATE cobrancas SET status = 'pendente' WHERE id = ?", (p2,))
    assert repasse_service.avisar_estorno(p2) == 2
    ajustes = db.query("SELECT consulta_id, valor_centavos FROM repasse_ajustes ORDER BY consulta_id")
    assert [(a["consulta_id"], a["valor_centavos"]) for a in ajustes] == [(cs[2], -5000), (cs[3], -5000)]


def test_estorno_de_mensalidade_tira_o_mes(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    acordo = _acordo(cen, "mensalidade", valor_centavos=80000, dia_vencimento=10)
    cs = [_consulta(cen, f"2026-10-{d:02d}") for d in (6, 13)]
    _sync(cen.org_a)
    cob = _mensalidade_de(acordo, "2026-10-01")
    pg = _pagar(cob["id"])
    _fechar(cen, cs)
    db.execute("UPDATE pagamentos SET estornado_em = '2026-11-12 09:00:00' WHERE id = ?", (pg,))
    db.execute("UPDATE cobrancas SET status = 'pendente' WHERE id = ?", (cob["id"],))
    assert repasse_service.avisar_estorno(cob["id"]) == 2
    assert sorted(a["valor_centavos"] for a in db.query("SELECT valor_centavos FROM repasse_ajustes")) == [-11500,
                                                                                                         -11500]


def test_estorno_antes_do_repasse_nao_gera_ajuste(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/pagamento/{pagamentos[c1]}/estornar",
                                               json={"motivo": "erro"})
    assert r.status_code == 200
    assert db.query("SELECT * FROM repasse_ajustes") == []
    assert _notificacoes_do(cen.gestor_a) == []
    # e a sessão volta a aguardar
    rel = _rel(cen)
    assert [s["consulta_id"] for s in _todas_sessoes(rel)] == [c2]
    assert [a["consulta_id"] for a in rel["aguardando"]] == [c1]


def test_desfazer_apaga_aviso_de_estorno_pendente(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    rid = _fechar(cen, [c1, c2])["id"]
    autenticado(client, cen.gestor_a).post(f"/api/financeiro/pagamento/{pagamentos[c1]}/estornar",
                                           json={"motivo": "erro"})
    assert len(db.query("SELECT * FROM repasse_ajustes")) == 1
    repasse_service.desfazer(cen.org_a, rid, "refazer", cen.gestor_a)
    assert db.query("SELECT * FROM repasse_ajustes") == []
    rel = _rel(cen)
    assert [s["consulta_id"] for s in _todas_sessoes(rel)] == [c2]


def test_falha_no_aviso_nao_desfaz_estorno(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])

    def quebra(*a, **k):
        raise RuntimeError("sino fora do ar")
    monkeypatch.setattr(repasse_service, "criar_notificacao", quebra)
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/pagamento/{pagamentos[c1]}/estornar",
                                               json={"motivo": "erro"})
    assert r.status_code == 200
    assert db.query_one("SELECT estornado_em FROM pagamentos WHERE id = ?", (pagamentos[c1],))["estornado_em"]
    assert db.query_one("SELECT 1 FROM eventos WHERE tipo = 'aviso_repasse_falhou'")

    # falha antes de gravar o ajuste também não quebra a rota
    monkeypatch.setattr(repasse_service, "_sessoes_repassadas_da_cobranca",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/pagamento/{pagamentos[c2]}/estornar",
                                               json={"motivo": "erro"})
    assert r.status_code == 200
    assert db.query_one("SELECT estornado_em FROM pagamentos WHERE id = ?", (pagamentos[c2],))["estornado_em"]


def test_reversao_do_mercado_pago_chama_o_aviso(client, db_ctx, monkeypatch):
    import pagamento_service
    chamadas = []
    monkeypatch.setattr(repasse_service, "avisar_estorno", lambda cid: chamadas.append(cid) or 0)
    monkeypatch.setattr(pagamento_service, "_avisar_reversao", lambda *a, **k: True)
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa")
    c1 = _consulta(cen, "2026-10-05")
    _sync(cen.org_a)
    cob = _cobranca_da(c1)
    assert pagamento_service._alertar_reversao(cob, cen.org_a, "123", {"status": "refunded"}) is True
    assert chamadas == [cob["id"]]
