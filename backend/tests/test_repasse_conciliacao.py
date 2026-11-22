"""Repasse — conciliação automática das sessões já repassadas (decisões do usuário de 22/11/2026):
recrédito quando a família paga de novo, ajuste quando a sessão deixa de contar (e volta) e o
teto da mensalidade com base "valor do procedimento"."""
import db
import repasse_service
from conftest import autenticado
from test_repasse_relatorio import (DE, ATE, HOJE, _cenario, _regra, _acordo, _consulta, _sync, _rel, _prof,
                                    _org, _cobranca_da, _mensalidade_de, _todas_sessoes)
from test_repasse_fechamento import _pagar, _fechar, _duas_avulsas_pagas, _notificacoes_do
from test_repasse_conservacao import _pacote

V = 14950   # 65% de R$ 230 (avulsa)


def _ajustes(consulta_id=None):
    sql = "SELECT * FROM repasse_ajustes"
    params = ()
    if consulta_id is not None:
        sql += " WHERE consulta_id = ?"
        params = (consulta_id,)
    return [dict(a) for a in db.query(sql + " ORDER BY id", params)]


def _resumo(consulta_id=None):
    return [(a["origem"], a["valor_centavos"], a["repasse_id"] is not None, bool(a["dispensado_em"]))
            for a in _ajustes(consulta_id)]


def _estornar(client, cen, pagamento_id):
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/pagamento/{pagamento_id}/estornar",
                                               json={"motivo": "Família pediu de volta"})
    assert r.status_code == 200, r.get_data(as_text=True)


def _pagar_pela_tela(client, cen, cobranca_id):
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/cobranca/{cobranca_id}/pagar",
                                               json={"forma": "dinheiro"})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["pagamento_id"]


def _status(client, cen, consulta_id, status):
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{consulta_id}/status", json={"status": status})
    assert r.status_code == 200, r.get_data(as_text=True)


# ------------------------------------------------------------------ Review Focus 1 e 2

def test_estorno_e_pago_de_novo_antes_do_fechamento_apaga_o_ajuste(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])
    _estornar(client, cen, pagamentos[c1])
    assert _resumo() == [("estorno", -V, False, False)]
    assert len(_notificacoes_do(cen.gestor_a)) == 1

    _pagar_pela_tela(client, cen, _cobranca_da(c1)["id"])
    assert _ajustes() == []
    assert len(_notificacoes_do(cen.gestor_a)) == 1   # apagar não notifica
    assert _prof(_rel(cen), cen.prof_a1) is None


def test_estorno_ja_descontado_e_pago_de_novo_vira_recredito(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])
    _estornar(client, cen, pagamentos[c1])
    _fechar(cen, [])   # desconta os −R$ 149,50
    assert _resumo() == [("estorno", -V, True, False)]

    _pagar_pela_tela(client, cen, _cobranca_da(c1)["id"])
    assert _resumo() == [("estorno", -V, True, False), ("recredito", V, False, False)]
    rec = _ajustes()[1]
    assert rec["consulta_id"] == c1 and rec["profissional_id"] == cen.prof_a1["id"]
    assert rec["descricao"].startswith("Recrédito: Paciente A1 em 05/10")
    notas = _notificacoes_do(cen.gestor_a)
    assert len(notas) == 2 and "Recrédito" in notas[-1]["mensagem"] and "R$ 149,50" in notas[-1]["mensagem"]
    p = _prof(_rel(cen), cen.prof_a1)
    assert p["sessoes"] == [] and p["a_pagar_centavos"] == V

    # estornado de novo antes de fechar: o recrédito pendente some
    pg2 = db.query_one("SELECT id FROM pagamentos WHERE cobranca_id = ? AND estornado_em IS NULL",
                       (_cobranca_da(c1)["id"],))["id"]
    _estornar(client, cen, pg2)
    assert _resumo() == [("estorno", -V, True, False)]


def test_estorno_fechamento_pago_estornado_de_novo_cria_outro_negativo(client, db_ctx):
    """Sem o índice único: o segundo estorno da mesma sessão gera outro −v."""
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])
    _estornar(client, cen, pagamentos[c1])
    _fechar(cen, [])
    pg2 = _pagar_pela_tela(client, cen, _cobranca_da(c1)["id"])
    _fechar(cen, [])   # paga o recrédito
    _estornar(client, cen, pg2)
    assert _resumo(c1) == [("estorno", -V, True, False), ("recredito", V, True, False),
                           ("estorno", -V, False, False)]
    assert _prof(_rel(cen), cen.prof_a1)["a_pagar_centavos"] == -V


# ------------------------------------------------------------------ Review Focus 3

def test_pacote_repassada_vira_falta_libera_a_vaga_e_volta(client, db_ctx):
    """Rateado: R$ 400 / 4 sessões, R$ 200 pagos (libera 2). a e b repassadas (R$ 100 de base,
    R$ 50 ao profissional). a vira falta sem repasse → −R$ 50 (status) e c ocupa a vaga;
    a volta a ser finalizada → o −R$ 50 pendente some e c volta a aguardar."""
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    _org(cen, fin_repasse_base="rateado")
    acordo, p1 = _pacote(cen)
    a, b, c = (_consulta(cen, f"2026-10-{d:02d}") for d in (2, 9, 16))
    _sync(cen.org_a)
    _pagar(p1)
    _fechar(cen, [a, b])
    assert [x["consulta_id"] for x in _rel(cen)["aguardando"]] == [c]

    _status(client, cen, a, "faltou")
    assert _resumo() == [("status", -5000, False, False)]
    assert _ajustes()[0]["consulta_id"] == a
    assert len(_notificacoes_do(cen.gestor_a)) == 1
    p = _prof(_rel(cen), cen.prof_a1)
    assert [(s["consulta_id"], s["base_centavos"]) for s in p["sessoes"]] == [(c, 10000)]
    assert p["a_pagar_centavos"] == 5000 - 5000

    _status(client, cen, a, "realizada")
    assert _ajustes() == []
    rel = _rel(cen)
    assert _prof(rel, cen.prof_a1) is None
    assert [x["consulta_id"] for x in rel["aguardando"]] == [c]


def test_avulsa_cancelada_depois_do_repasse_e_reativada(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, _ = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])
    _status(client, cen, c1, "cancelada")
    a = _ajustes()
    assert [(x["origem"], x["consulta_id"], x["valor_centavos"]) for x in a] == [("status", c1, -V)]
    assert a[0]["descricao"].startswith("Sessão cancelada: Paciente A1 em 05/10 — já repassado em ")
    _status(client, cen, c1, "realizada")
    assert _ajustes() == []


# ------------------------------------------------------------------ Review Focus 4

def test_conciliar_duas_vezes_nao_cria_nada_na_segunda(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])
    db.execute("UPDATE pagamentos SET estornado_em = '2026-11-12 09:00:00' WHERE id = ?", (pagamentos[c1],))
    db.execute("UPDATE cobrancas SET status = 'pendente' WHERE id = ?", (_cobranca_da(c1)["id"],))
    assert repasse_service.conciliar(cen.org_a) == 1
    assert repasse_service.conciliar(cen.org_a) == 0
    aviso = _ajustes()[0]
    repasse_service.excluir_ajuste(cen.org_a, aviso["id"], cen.gestor_a)
    assert _resumo() == [("estorno", -V, False, True)]
    assert repasse_service.conciliar(cen.org_a) == 0
    assert repasse_service.conciliar(cen.org_a, [c1, c2]) == 0
    _rel(cen)   # o relatório também concilia
    assert _resumo() == [("estorno", -V, False, True)]
    assert len(_notificacoes_do(cen.gestor_a)) == 1


def test_dispensado_e_familia_paga_de_novo_apaga_o_dispensado(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])
    _estornar(client, cen, pagamentos[c1])
    repasse_service.excluir_ajuste(cen.org_a, _ajustes()[0]["id"], cen.gestor_a)
    _pagar_pela_tela(client, cen, _cobranca_da(c1)["id"])
    assert _ajustes() == []
    assert len(_notificacoes_do(cen.gestor_a)) == 1


def test_excluir_ajuste_automatico_dispensa_e_manual_apaga(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, _ = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])
    _status(client, cen, c1, "cancelada")
    aid = _ajustes()[0]["id"]
    repasse_service.excluir_ajuste(cen.org_a, aid, cen.gestor_a)
    assert _resumo() == [("status", -V, False, True)]
    assert repasse_service.conciliar(cen.org_a) == 0


# ------------------------------------------------------------------ Review Focus 5: teto da mensalidade

def test_mensalidade_por_procedimento_nunca_passa_do_liquido(client, db_ctx):
    """8 sessões de R$ 150 num mês de R$ 600 pago: a soma das bases é R$ 600."""
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    acordo = _acordo(cen, "mensalidade", valor_centavos=60000, dia_vencimento=10)
    cs = [_consulta(cen, f"2026-10-{d:02d}", proc=cen.proc_150, valor=15000) for d in (1, 5, 8, 12, 15, 19, 22, 26)]
    _sync(cen.org_a)
    _pagar(_mensalidade_de(acordo, "2026-10-01")["id"])
    p = _prof(_rel(cen), cen.prof_a1)
    assert [s["consulta_id"] for s in p["sessoes"]] == cs
    assert [s["base_centavos"] for s in p["sessoes"]] == [15000] * 4 + [0] * 4
    assert p["total_sessoes_centavos"] == 60000


def test_mensalidade_por_procedimento_desconta_o_ja_repassado(client, db_ctx):
    cen = _cenario(db_ctx)
    _regra(cen, cen.prof_a1, pct=5000)
    acordo = _acordo(cen, "mensalidade", valor_centavos=60000, dia_vencimento=10)
    primeiras = [_consulta(cen, f"2026-10-{d:02d}", proc=cen.proc_150, valor=15000) for d in (1, 5, 8)]
    _sync(cen.org_a)
    _pagar(_mensalidade_de(acordo, "2026-10-01")["id"])
    _fechar(cen, primeiras)
    depois = [_consulta(cen, f"2026-10-{d:02d}", proc=cen.proc_150, valor=15000) for d in (12, 15, 19)]
    _sync(cen.org_a)
    p = _prof(_rel(cen), cen.prof_a1)
    assert [(s["consulta_id"], s["base_centavos"]) for s in p["sessoes"]] == list(zip(depois, [15000, 0, 0]))


# ------------------------------------------------------------------ ganchos

def test_mudanca_de_status_pela_agenda_concilia(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    c1, c2, _ = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])
    chamadas = []
    original = repasse_service.conciliar

    def espia(org_id, consulta_ids=None, *a, **k):
        chamadas.append((org_id, list(consulta_ids or [])))
        return original(org_id, consulta_ids, *a, **k)
    monkeypatch.setattr(repasse_service, "conciliar", espia)
    gestor = autenticado(client, cen.gestor_a)

    assert gestor.put(f"/api/agenda/{c1}/status", json={"status": "desmarcada_profissional"}).status_code == 200
    assert chamadas[-1] == (cen.org_a, [c1])
    assert _resumo() == [("status", -V, False, False)]

    r = gestor.put(f"/api/agenda/{c1}/atendimento", json={"status": "realizada", "descricao": "Sessão ok"})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert chamadas[-1] == (cen.org_a, [c1])
    assert _ajustes() == []

    gestor.put(f"/api/agenda/{c2}/status", json={"status": "faltou"})
    assert chamadas[-1] == (cen.org_a, [c2])
    r = gestor.put(f"/api/agenda/{c2}", json={"observacoes": "remarcar"})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert chamadas[-1] == (cen.org_a, [c2])


def test_falha_na_conciliacao_nao_derruba_baixa_nem_status(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])
    db.execute("UPDATE pagamentos SET estornado_em = '2026-11-12 09:00:00' WHERE id = ?", (pagamentos[c1],))
    db.execute("UPDATE cobrancas SET status = 'pendente' WHERE id = ?", (_cobranca_da(c1)["id"],))

    def quebra(*a, **k):
        raise RuntimeError("fora do ar")
    monkeypatch.setattr(repasse_service, "_carregar", quebra)
    _pagar_pela_tela(client, cen, _cobranca_da(c1)["id"])
    assert db.query_one("SELECT status FROM cobrancas WHERE id = ?", (_cobranca_da(c1)["id"],))["status"] == "pago"
    _status(client, cen, c2, "cancelada")
    assert db.query_one("SELECT status FROM consultas WHERE id = ?", (c2,))["status"] == "cancelada"
    assert repasse_service.conciliar(cen.org_a) == 0
    assert len(db.query("SELECT 1 FROM eventos WHERE tipo = 'aviso_repasse_falhou'")) >= 2
    assert _ajustes() == []


def test_falha_numa_sessao_nao_impede_as_outras(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    rid = _fechar(cen, [c1, c2])["id"]
    for c in (c1, c2):
        db.execute("UPDATE pagamentos SET estornado_em = '2026-11-12 09:00:00' WHERE id = ?", (pagamentos[c],))
        db.execute("UPDATE cobrancas SET status = 'pendente' WHERE id = ?", (_cobranca_da(c)["id"],))
    original = repasse_service._travar_sessao

    def trava_quebrada(consulta_id):
        if consulta_id == c1:
            raise RuntimeError("x")
        return original(consulta_id)
    monkeypatch.setattr(repasse_service, "_travar_sessao", trava_quebrada)
    assert repasse_service.avisar_estorno_das_sessoes(cen.org_a, [c1, c2], rid) == 1
    assert [a["consulta_id"] for a in _ajustes()] == [c2]
    assert db.query_one("SELECT 1 FROM eventos WHERE tipo = 'aviso_repasse_falhou'")


def test_ajuste_gravado_por_outra_rodada_no_meio_nao_duplica(client, db_ctx, monkeypatch):
    """Outra rodada gravou o −v de c1 entre a leitura e a trava: sob a trava a soma é relida,
    então c1 não ganha outro e c2 continua sendo criado."""
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    rid = _fechar(cen, [c1, c2])["id"]
    for c in (c1, c2):
        db.execute("UPDATE pagamentos SET estornado_em = '2026-11-12 09:00:00' WHERE id = ?", (pagamentos[c],))
        db.execute("UPDATE cobrancas SET status = 'pendente' WHERE id = ?", (_cobranca_da(c)["id"],))
    db.execute("""INSERT INTO repasse_ajustes (organizacao_id, profissional_id, descricao, valor_centavos, origem,
                                               consulta_id) VALUES (?, ?, 'outra rodada', ?, 'estorno', ?)""",
               (cen.org_a, cen.prof_a1["id"], -V, c1))
    monkeypatch.setattr(repasse_service, "_somas_automaticas", lambda *a, **k: {})   # leitura antiga
    assert repasse_service.avisar_estorno_das_sessoes(cen.org_a, [c1, c2], rid) == 1
    ajustes = _ajustes()
    assert [(a["consulta_id"], a["descricao"] == "outra rodada") for a in ajustes] == [(c1, True), (c2, False)]
    assert len(_notificacoes_do(cen.gestor_a)) == 1
    assert not db.query_one("SELECT 1 FROM eventos WHERE tipo = 'aviso_repasse_falhou'")


def test_outra_clinica_nunca_e_tocada(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])
    db.execute("UPDATE pagamentos SET estornado_em = '2026-11-12 09:00:00' WHERE id = ?", (pagamentos[c1],))
    db.execute("UPDATE cobrancas SET status = 'pendente' WHERE id = ?", (_cobranca_da(c1)["id"],))
    assert repasse_service.conciliar(cen.org_b) == 0
    assert repasse_service.conciliar(cen.org_b, [c1, c2]) == 0
    assert _ajustes() == [] and _notificacoes_do(cen.gestor_b) == []
    assert repasse_service.conciliar(cen.org_a) == 1
    assert _notificacoes_do(cen.gestor_b) == []
    assert db.query_one("SELECT organizacao_id FROM repasse_ajustes")["organizacao_id"] == cen.org_a


def test_desfazer_apaga_os_automaticos_pendentes_e_mantem_o_409(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    rid = _fechar(cen, [c1, c2])["id"]
    _status(client, cen, c2, "cancelada")
    _estornar(client, cen, pagamentos[c1])
    repasse_service.excluir_ajuste(cen.org_a, _ajustes(c1)[0]["id"], cen.gestor_a)   # dispensado
    assert len(_ajustes()) == 2
    rid2 = _fechar(cen, [])["id"]   # usa o "status" de c2
    try:
        repasse_service.desfazer(cen.org_a, rid, "refazer", cen.gestor_a)
        assert False, "devia dar 409"
    except repasse_service.Conflito:
        pass
    repasse_service.desfazer(cen.org_a, rid2, "refazer", cen.gestor_a)
    repasse_service.desfazer(cen.org_a, rid, "refazer", cen.gestor_a)
    assert _ajustes() == []
    rel = _rel(cen)
    assert [s["consulta_id"] for s in _todas_sessoes(rel)] == []
    assert sorted(x["consulta_id"] for x in rel["aguardando"]) == [c1]


# ------------------------------------------------------------------ correções da revisão (rodada 1)

def _mensalidade_repassada(cen, valor=60000):
    _regra(cen, cen.prof_a1, pct=5000)
    acordo = _acordo(cen, "mensalidade", valor_centavos=valor, dia_vencimento=10)
    c = _consulta(cen, "2026-10-05")
    _sync(cen.org_a)
    _pagar(_mensalidade_de(acordo, "2026-10-01")["id"])
    _fechar(cen, [c])
    return acordo, c


def test_corte_movido_depois_do_repasse_nao_vira_estorno(client, db_ctx):
    """Mensalidade de R$ 600 paga, sessão de 05/10 repassada; o gestor move o "cobrar desde"
    para 20/10: a sessão não se classifica mais, mas o item gravado diz que o mês está pago."""
    cen = _cenario(db_ctx)
    _mensalidade_repassada(cen)
    _org(cen, fin_cobrar_desde="2026-10-20")
    _rel(cen)
    assert repasse_service.conciliar(cen.org_a) == 0
    assert _ajustes() == [] and _notificacoes_do(cen.gestor_a) == []


def test_acordo_que_deixa_de_valer_nao_vira_estorno(client, db_ctx):
    cen = _cenario(db_ctx)
    acordo, _ = _mensalidade_repassada(cen)
    db.execute("UPDATE acordos_pagamento SET especialidade = 'Psicologia' WHERE id = ?", (acordo,))
    _rel(cen)
    assert repasse_service.conciliar(cen.org_a) == 0
    assert _ajustes() == [] and _notificacoes_do(cen.gestor_a) == []


def test_falta_repassada_com_cobrar_falta_desligado_nao_vira_ajuste(client, db_ctx):
    from test_repasse_fechamento import _falta_de_mensalidade_repassada
    cen = _cenario(db_ctx)
    _falta_de_mensalidade_repassada(cen)
    _org(cen, fin_cobrar_falta=0)
    _rel(cen)
    assert _ajustes() == [] and _notificacoes_do(cen.gestor_a) == []


def test_mensalidade_repassada_estornada_ainda_vira_estorno(client, db_ctx):
    """O vínculo gravado também vale no sentido contrário: o mês deixou de estar pago."""
    cen = _cenario(db_ctx)
    acordo, c = _mensalidade_repassada(cen)
    _org(cen, fin_cobrar_desde="2026-10-20")
    cob = _mensalidade_de(acordo, "2026-10-01")
    db.execute("UPDATE pagamentos SET estornado_em = '2026-11-12 09:00:00' WHERE cobranca_id = ?", (cob["id"],))
    db.execute("UPDATE cobrancas SET status = 'pendente' WHERE id = ?", (cob["id"],))
    assert repasse_service.avisar_estorno(cob["id"]) == 1
    assert _resumo(c) == [("estorno", -11500, False, False)]


def test_baixa_entre_a_leitura_e_a_trava_nao_recria_o_negativo(client, db_ctx, monkeypatch):
    """A conciliação leu "não paga"; antes da trava, a baixa foi gravada e a conciliação dela
    apagou o −v. Sob a trava o pago é relido: nada é criado."""
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])
    _estornar(client, cen, pagamentos[c1])
    assert _resumo() == [("estorno", -V, False, False)]
    cob = _cobranca_da(c1)["id"]
    original = repasse_service._somas_automaticas

    def baixa_no_meio(org_id):
        _pagar(cob)
        db.execute("DELETE FROM repasse_ajustes WHERE consulta_id = ?", (c1,))
        return original(org_id)
    monkeypatch.setattr(repasse_service, "_somas_automaticas", baixa_no_meio)
    assert repasse_service.conciliar(cen.org_a) == 0
    assert _ajustes() == []
    assert len(_notificacoes_do(cen.gestor_a)) == 1


def test_estorno_pendente_vira_status_quando_a_sessao_deixa_de_contar(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])
    _estornar(client, cen, pagamentos[c1])
    aid = _ajustes()[0]["id"]
    _status(client, cen, c1, "cancelada")
    a = _ajustes()
    assert [(x["id"], x["origem"], x["valor_centavos"]) for x in a] == [(aid, "status", -V)]
    assert a[0]["descricao"].startswith("Sessão cancelada: Paciente A1 em 05/10")
    assert len(_notificacoes_do(cen.gestor_a)) == 1   # trocar o rótulo não notifica
    assert repasse_service.conciliar(cen.org_a) == 0
    _status(client, cen, c1, "realizada")   # volta a contar, ainda sem pagar
    assert [(x["id"], x["origem"], x["valor_centavos"]) for x in _ajustes()] == [(aid, "estorno", -V)]


class _SDKAprovado:
    def __init__(self, referencia, valor):
        self.referencia, self.valor = referencia, valor

    def payment(self):
        return self

    def get(self, payment_id, opcoes=None):
        return {"response": {"status": "approved", "transaction_amount": self.valor,
                             "external_reference": self.referencia,
                             "date_approved": "2026-11-10T10:00:00.000-03:00"}}


def test_webhook_aprovado_concilia_e_o_repetido_nao(client, db_ctx, monkeypatch):
    import pagamento_service
    cen = _cenario(db_ctx)
    c1, c2, pagamentos = _duas_avulsas_pagas(cen)
    _fechar(cen, [c1, c2])
    _estornar(client, cen, pagamentos[c1])
    assert _resumo() == [("estorno", -V, False, False)]
    cob = _cobranca_da(c1)["id"]
    db.execute("UPDATE cobrancas SET mp_payment_id = 'MP-1' WHERE id = ?", (cob,))
    monkeypatch.setattr(pagamento_service, "_sdk", lambda org: _SDKAprovado(f"cobranca-{cob}", 230.0))
    chamadas = []
    original = repasse_service.avisar_estorno
    monkeypatch.setattr(repasse_service, "avisar_estorno", lambda cid: chamadas.append(cid) or original(cid))

    r = pagamento_service.processar_webhook("MP-1")
    assert r.get("status") == "pago", r
    assert chamadas == [cob]
    assert _ajustes() == []

    r = pagamento_service.processar_webhook("MP-1")   # o Mercado Pago repete o aviso
    assert r.get("ignorado") is True, r
    assert chamadas == [cob]
