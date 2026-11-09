"""Financeiro etapa 1, task 5: baixa, estorno, liberar, conferência, cancelar e decisões."""
from datetime import timedelta

import db
import planos_padrao
import pagamento_service
import ausencias_service
import cobranca_service
from factories import DuasClinicas, novo_usuario, vincular_responsavel

from conftest import autenticado


def _hoje():
    return ausencias_service.hoje_brasilia()


def _cenario(db_ctx):
    cen = DuasClinicas()
    planos_padrao.criar_planos_padrao_para_teste()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id IN (?, ?)", (cen.org_a, cen.org_b))
    cen.sec_a = novo_usuario(cen.org_a, "Secretaria A", "sec@a.com", "secretaria")
    cen.proc_a = db.execute("INSERT INTO procedimentos (organizacao_id, nome, valor_centavos) VALUES (?, 'Sessão', 15000)",
                            (cen.org_a,))
    return cen


def _cobranca(cen, valor=23000, status="pendente", venc=None, tipo="manual", desconto=0, org=None, **extra):
    venc = venc or (_hoje() + timedelta(days=10)).isoformat()
    campos = {"paciente_id": cen.paciente_a1, "descricao": "Mensalidade", "valor_centavos": valor,
              "vencimento": venc, "status": status, "organizacao_id": org or cen.org_a, "tipo": tipo,
              "desconto_centavos": desconto}
    campos.update(extra)
    cols = ", ".join(campos)
    return db.execute(f"INSERT INTO cobrancas ({cols}) VALUES ({', '.join('?' for _ in campos)})",
                      tuple(campos.values()))


def _sessao(cen, dias_atras=3, status="realizada", valor=15000):
    dia = (_hoje() - timedelta(days=dias_atras)).isoformat()
    return db.execute(
        """INSERT INTO consultas (paciente_id, profissional_id, data_hora, status, especialidade,
                                  procedimento_id, procedimento_valor_centavos)
           VALUES (?, ?, ?, ?, 'Fonoaudiologia', ?, ?)""",
        (cen.paciente_a1, cen.prof_a1["id"], f"{dia} 09:00:00", status, cen.proc_a, valor))


def _item(cobranca_id, consulta_id, valor=15000):
    return db.execute("INSERT INTO cobranca_itens (cobranca_id, consulta_id, data_hora, valor_centavos) VALUES (?, ?, '2026-01-01 09:00:00', ?)",
                      (cobranca_id, consulta_id, valor))


def _cob(cid):
    return db.query_one("SELECT * FROM cobrancas WHERE id = ?", (cid,))


def _pagar(client, usuario, cid, **corpo):
    corpo.setdefault("forma", "dinheiro")
    return autenticado(client, usuario).post(f"/api/financeiro/cobranca/{cid}/pagar", json=corpo)


def _auditoria(acao, cid):
    return db.query("SELECT * FROM auditoria WHERE entidade = 'cobranca' AND entidade_id = ? AND acao = ?", (cid, acao))


# ------------------------------------------------------------------ baixa

def test_baixa_total_e_parcial(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, 23000)
    r = _pagar(client, cen.gestor_a, cid, valor_centavos=10000)
    assert r.status_code == 200 and r.get_json()["status"] == "parcial"
    assert _cob(cid)["status"] == "parcial"
    r = _pagar(client, cen.gestor_a, cid, valor_centavos=13000, forma="pix")
    assert r.status_code == 200 and r.get_json()["status"] == "pago"
    assert _cob(cid)["status"] == "pago"
    pgs = db.query("SELECT * FROM pagamentos WHERE cobranca_id = ? ORDER BY id", (cid,))
    assert [p["valor_centavos"] for p in pgs] == [10000, 13000]
    assert pgs[0]["recebido_por_usuario_id"] == cen.gestor_a["id"]
    assert pgs[0]["recebido_por_nome"] == cen.gestor_a["nome"]


def test_baixa_sem_valor_paga_o_saldo_com_desconto(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, 23000, desconto=3000)
    r = _pagar(client, cen.gestor_a, cid)
    assert r.status_code == 200 and r.get_json()["status"] == "pago"
    assert db.query_one("SELECT valor_centavos FROM pagamentos WHERE cobranca_id = ?", (cid,))["valor_centavos"] == 20000
    assert _pagar(client, cen.gestor_a, cid).status_code == 409   # já paga


def test_baixa_maior_que_saldo_400(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, 23000)
    assert _pagar(client, cen.gestor_a, cid, valor_centavos=23001).status_code == 400
    assert _pagar(client, cen.gestor_a, cid, valor_centavos=0).status_code == 400
    assert _pagar(client, cen.gestor_a, cid, valor_centavos="100").status_code == 400
    assert _pagar(client, cen.gestor_a, cid, forma="cartao").status_code == 400
    assert db.query("SELECT * FROM pagamentos WHERE cobranca_id = ?", (cid,)) == []
    assert _cob(cid)["status"] == "pendente"


def test_baixa_rascunho_e_cancelada_409(client, db_ctx):
    cen = _cenario(db_ctx)
    assert _pagar(client, cen.gestor_a, _cobranca(cen, status="rascunho")).status_code == 409
    assert _pagar(client, cen.gestor_a, _cobranca(cen, status="cancelado")).status_code == 409


def test_baixa_corpo_que_nao_e_objeto_400(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/cobranca/{cid}/pagar", json=[1, 2])
    assert r.status_code == 400


def test_baixa_com_data_passada_e_futura(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    ontem = (_hoje() - timedelta(days=1)).isoformat()
    amanha = (_hoje() + timedelta(days=1)).isoformat()
    assert _pagar(client, cen.gestor_a, cid, valor_centavos=1000, data=amanha).status_code == 400
    assert _pagar(client, cen.gestor_a, cid, valor_centavos=1000, data="2026-13-40").status_code == 400
    assert _pagar(client, cen.gestor_a, cid, valor_centavos=1000, data=ontem).status_code == 200
    assert db.query_one("SELECT pago_em FROM pagamentos WHERE cobranca_id = ?", (cid,))["pago_em"].startswith(ontem)


def test_secretaria_da_baixa(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    assert _pagar(client, cen.sec_a, cid).status_code == 200
    pg = db.query_one("SELECT * FROM pagamentos WHERE cobranca_id = ?", (cid,))
    assert pg["recebido_por_usuario_id"] == cen.sec_a["id"]


def test_profissional_nao_da_baixa_403(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    assert _pagar(client, cen.prof_a1, cid).status_code == 403
    assert _cob(cid)["status"] == "pendente"


def test_responsavel_nao_da_baixa_403(client, db_ctx):
    cen = _cenario(db_ctx)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    cid = _cobranca(cen)
    assert _pagar(client, cen.resp_a1, cid).status_code == 403
    assert db.query("SELECT * FROM pagamentos WHERE cobranca_id = ?", (cid,)) == []


# ------------------------------------------------------------------ estorno

def _paga(client, cen, cid, **corpo):
    return _pagar(client, cen.gestor_a, cid, **corpo).get_json()["pagamento_id"]


def test_estorno_so_gestor(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    pid = _paga(client, cen, cid)
    for u in (cen.sec_a, cen.prof_a1):
        r = autenticado(client, u).post(f"/api/financeiro/pagamento/{pid}/estornar", json={"motivo": "erro"})
        assert r.status_code == 403
    assert _cob(cid)["status"] == "pago"
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/pagamento/{pid}/estornar", json={"motivo": "erro"})
    assert r.status_code == 200


def test_estorno_exige_motivo_e_nao_repete(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    pid = _paga(client, cen, cid)
    c = autenticado(client, cen.gestor_a)
    assert c.post(f"/api/financeiro/pagamento/{pid}/estornar", json={}).status_code == 400
    assert c.post(f"/api/financeiro/pagamento/{pid}/estornar", json={"motivo": "  "}).status_code == 400
    assert c.post(f"/api/financeiro/pagamento/{pid}/estornar", json={"motivo": "lançado errado"}).status_code == 200
    assert c.post(f"/api/financeiro/pagamento/{pid}/estornar", json={"motivo": "de novo"}).status_code == 409
    pg = db.query_one("SELECT * FROM pagamentos WHERE id = ?", (pid,))
    assert pg["estornado_em"] and pg["estorno_motivo"] == "lançado errado" and pg["estornado_por"] == cen.gestor_a["id"]


def test_estorno_volta_status(client, db_ctx):
    cen = _cenario(db_ctx)
    futuro = _cobranca(cen, 20000)
    p1 = _paga(client, cen, futuro, valor_centavos=5000)
    p2 = _paga(client, cen, futuro, valor_centavos=15000)
    assert _cob(futuro)["status"] == "pago"
    c = autenticado(client, cen.gestor_a)
    assert c.post(f"/api/financeiro/pagamento/{p2}/estornar", json={"motivo": "x"}).get_json()["status"] == "parcial"
    assert c.post(f"/api/financeiro/pagamento/{p1}/estornar", json={"motivo": "x"}).get_json()["status"] == "pendente"
    # sem nada pago e com vencimento no passado: vencido
    passado = _cobranca(cen, 20000, venc=(_hoje() - timedelta(days=2)).isoformat(), status="vencido")
    p3 = _paga(client, cen, passado)
    assert _cob(passado)["status"] == "pago"
    assert c.post(f"/api/financeiro/pagamento/{p3}/estornar", json={"motivo": "x"}).get_json()["status"] == "vencido"
    assert _cob(passado)["status"] == "vencido"


# ------------------------------------------------------------------ liberar

def test_liberar_so_periodo_encerrado(client, db_ctx):
    cen = _cenario(db_ctx)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    c = autenticado(client, cen.sec_a)
    ontem = (_hoje() - timedelta(days=1)).isoformat()
    aberto = _cobranca(cen, status="rascunho", tipo="periodo", periodo_inicio=ontem, periodo_fim=_hoje().isoformat())
    assert c.post(f"/api/financeiro/cobranca/{aberto}/liberar").status_code == 409
    encerrado = _cobranca(cen, status="rascunho", tipo="periodo", periodo_inicio=ontem, periodo_fim=ontem)
    assert c.post(f"/api/financeiro/cobranca/{encerrado}/liberar").status_code == 200
    cob = _cob(encerrado)
    assert cob["status"] == "pendente" and cob["liberada_em"]
    notif = db.query("SELECT titulo, mensagem FROM notificacoes WHERE usuario_id = ?", (cen.resp_a1["id"],))
    assert [n["titulo"] for n in notif] == ["Nova cobrança disponível"]
    assert "R$" not in notif[0]["mensagem"]
    assert c.post(f"/api/financeiro/cobranca/{encerrado}/liberar").status_code == 409   # já liberada
    assert autenticado(client, cen.prof_a1).post(f"/api/financeiro/cobranca/{aberto}/liberar").status_code == 403


# ------------------------------------------------------------------ conferir

def test_conferir_desconto_e_remover_item(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, 30000, status="rascunho", tipo="periodo")
    s1, s2 = _sessao(cen, 5), _sessao(cen, 4)
    i1, i2 = _item(cid, s1), _item(cid, s2)
    r = autenticado(client, cen.sec_a).put(f"/api/financeiro/cobranca/{cid}/conferir", json={
        "desconto_centavos": 2000, "desconto_motivo": "Cortesia", "remover_itens": [i2]})
    assert r.status_code == 200, r.get_data(as_text=True)
    cob = _cob(cid)
    assert (cob["valor_centavos"], cob["desconto_centavos"], cob["desconto_motivo"]) == (15000, 2000, "Cortesia")
    assert [x["id"] for x in db.query("SELECT id FROM cobranca_itens WHERE cobranca_id = ?", (cid,))] == [i1]
    d = db.query_one("SELECT * FROM consulta_decisao_cobranca WHERE consulta_id = ?", (s2,))
    assert (d["decisao"], d["motivo"]) == ("nao_cobrar", "Retirado na conferência")
    # a sessão retirada não volta na sincronização
    cobranca_service.sincronizar(cen.org_a, _hoje().isoformat())
    assert db.query_one("SELECT 1 AS x FROM cobranca_itens WHERE consulta_id = ?", (s2,)) is None


def test_desconto_sem_motivo_400(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, 15000, status="rascunho", tipo="periodo")
    _item(cid, _sessao(cen, 5))
    c = autenticado(client, cen.gestor_a)
    assert c.put(f"/api/financeiro/cobranca/{cid}/conferir", json={"desconto_centavos": 1000}).status_code == 400
    assert c.put(f"/api/financeiro/cobranca/{cid}/conferir", json={"desconto_centavos": 15001, "desconto_motivo": "x"}).status_code == 400
    assert c.put(f"/api/financeiro/cobranca/{cid}/conferir", json={"desconto_centavos": -1, "desconto_motivo": "x"}).status_code == 400
    assert c.put(f"/api/financeiro/cobranca/{cid}/conferir", json={"remover_itens": [999999]}).status_code == 400
    assert _cob(cid)["desconto_centavos"] == 0


def test_conferir_so_rascunho_409(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, 15000, status="pendente")
    r = autenticado(client, cen.gestor_a).put(f"/api/financeiro/cobranca/{cid}/conferir",
                                              json={"desconto_centavos": 100, "desconto_motivo": "x"})
    assert r.status_code == 409


# ------------------------------------------------------------------ cancelar / revisão

def test_cancelar_com_pagamento_409(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    pid = _paga(client, cen, cid, valor_centavos=1000)
    c = autenticado(client, cen.gestor_a)
    assert c.post(f"/api/financeiro/cobranca/{cid}/cancelar", json={"motivo": "x"}).status_code == 409
    assert _cob(cid)["status"] == "parcial"
    c.post(f"/api/financeiro/pagamento/{pid}/estornar", json={"motivo": "x"})
    assert c.post(f"/api/financeiro/cobranca/{cid}/cancelar", json={}).status_code == 400   # motivo
    assert c.post(f"/api/financeiro/cobranca/{cid}/cancelar", json={"motivo": "duplicada"}).status_code == 200
    assert _cob(cid)["status"] == "cancelado"
    assert autenticado(client, cen.sec_a).post(f"/api/financeiro/cobranca/{cid}/cancelar", json={"motivo": "x"}).status_code == 403


def test_cancelar_vira_nao_cobrar_nos_itens(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, 15000, tipo="avulsa")
    s = _sessao(cen, 5)
    _item(cid, s)
    assert autenticado(client, cen.gestor_a).post(f"/api/financeiro/cobranca/{cid}/cancelar", json={"motivo": "engano"}).status_code == 200
    assert db.query_one("SELECT decisao FROM consulta_decisao_cobranca WHERE consulta_id = ?", (s,))["decisao"] == "nao_cobrar"
    cobranca_service.sincronizar(cen.org_a, _hoje().isoformat())
    assert [x["id"] for x in db.query("SELECT id FROM cobrancas WHERE paciente_id = ? AND status != 'cancelado'", (cen.paciente_a1,))] == []


def test_resolver_revisao_mantem_motivo(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, revisar=1, revisar_motivo="Sessão de 05/11 virou Falta justificada")
    assert autenticado(client, cen.sec_a).post(f"/api/financeiro/cobranca/{cid}/resolver-revisao").status_code == 403
    assert autenticado(client, cen.gestor_a).post(f"/api/financeiro/cobranca/{cid}/resolver-revisao").status_code == 200
    cob = _cob(cid)
    assert cob["revisar"] == 0 and cob["revisar_motivo"]


# ------------------------------------------------------------------ decisão e avulsas

def test_decisao_valor_gera_cobranca_na_proxima_sincronizacao(client, db_ctx):
    cen = _cenario(db_ctx)
    db.execute("""INSERT INTO acordos_pagamento (organizacao_id, paciente_id, especialidade, tipo, ciclo, inicio, vence_dias)
                  VALUES (?, ?, 'Fonoaudiologia', 'avulsa', 'consulta', '2026-01-01', 5)""", (cen.org_a, cen.paciente_a1))
    s = _sessao(cen, 3, valor=0)
    hoje = _hoje().isoformat()
    cobranca_service.sincronizar(cen.org_a, hoje)
    assert db.query("SELECT * FROM cobranca_itens WHERE consulta_id = ?", (s,)) == []
    c = autenticado(client, cen.sec_a)
    assert c.post(f"/api/financeiro/sessoes/{s}/decisao", json={"decisao": "valor"}).status_code == 400
    assert c.post(f"/api/financeiro/sessoes/{s}/decisao", json={"decisao": "valor", "valor_centavos": 0}).status_code == 400
    assert c.post(f"/api/financeiro/sessoes/{s}/decisao", json={"decisao": "valor", "valor_centavos": 100_000_001}).status_code == 400
    assert c.post(f"/api/financeiro/sessoes/{s}/decisao", json={"decisao": "valor", "valor_centavos": 9000}).status_code == 200
    cobranca_service.sincronizar(cen.org_a, hoje)
    item = db.query_one("SELECT * FROM cobranca_itens WHERE consulta_id = ?", (s,))
    assert item and item["valor_centavos"] == 9000
    g = autenticado(client, cen.gestor_a)
    assert g.post(f"/api/financeiro/sessoes/{s}/decisao", json={"decisao": "nao_cobrar", "motivo": "x"}).status_code == 409


def test_secretaria_nao_decide_nao_cobrar(client, db_ctx):
    cen = _cenario(db_ctx)
    s = _sessao(cen, 3)
    c = autenticado(client, cen.sec_a)
    assert c.post(f"/api/financeiro/sessoes/{s}/decisao", json={"decisao": "nao_cobrar", "motivo": "x"}).status_code == 403
    assert db.query("SELECT * FROM consulta_decisao_cobranca") == []
    assert c.post(f"/api/financeiro/sessoes/{s}/decisao", json={"decisao": "valor", "valor_centavos": 5000}).status_code == 200


def test_decisao_nao_cobrar_exige_motivo(client, db_ctx):
    cen = _cenario(db_ctx)
    s = _sessao(cen, 3)
    c = autenticado(client, cen.gestor_a)
    assert c.post(f"/api/financeiro/sessoes/{s}/decisao", json={"decisao": "nao_cobrar"}).status_code == 400
    assert c.post(f"/api/financeiro/sessoes/{s}/decisao", json={"decisao": "nao_cobrar", "motivo": "Cortesia"}).status_code == 200
    assert c.post(f"/api/financeiro/sessoes/{s}/decisao", json={"decisao": "talvez"}).status_code == 400
    assert c.post(f"/api/financeiro/sessoes/{s}/decisao", json="x").status_code == 400
    assert autenticado(client, cen.prof_a1).post(f"/api/financeiro/sessoes/{s}/decisao",
                                                 json={"decisao": "nao_cobrar", "motivo": "x"}).status_code == 403


def test_cobrar_avulsas(client, db_ctx):
    cen = _cenario(db_ctx)
    s1, s2 = _sessao(cen, 5), _sessao(cen, 4)
    c = autenticado(client, cen.sec_a)
    url = f"/api/financeiro/paciente/{cen.paciente_a1}/cobrar-avulsas"
    assert c.post(url, json={"consulta_ids": []}).status_code == 400
    assert c.post(url, json={"consulta_ids": [s1, 999999]}).status_code == 400
    assert c.post(url, json={"consulta_ids": "x"}).status_code == 400
    r = c.post(url, json={"consulta_ids": [s1, s2]})
    assert r.status_code == 201, r.get_data(as_text=True)
    cob = _cob(r.get_json()["id"])
    assert (cob["tipo"], cob["status"], cob["valor_centavos"], cob["organizacao_id"]) == ("avulsa", "pendente", 30000, cen.org_a)
    assert cob["vencimento"] == (_hoje() + timedelta(days=5)).isoformat()
    assert len(db.query("SELECT 1 FROM cobranca_itens WHERE cobranca_id = ?", (cob["id"],))) == 2
    # já cobradas: não entram de novo
    assert c.post(url, json={"consulta_ids": [s1]}).status_code == 400
    assert _auditoria("criar", cob["id"])


def test_cobrar_avulsas_sessao_com_acordo_400(client, db_ctx):
    cen = _cenario(db_ctx)
    db.execute("""INSERT INTO acordos_pagamento (organizacao_id, paciente_id, especialidade, tipo, valor_centavos,
                  dia_vencimento, inicio, vence_dias) VALUES (?, ?, 'Fonoaudiologia', 'mensalidade', 50000, 10, '2026-01-01', 5)""",
               (cen.org_a, cen.paciente_a1))
    s = _sessao(cen, 3)
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/paciente/{cen.paciente_a1}/cobrar-avulsas", json={"consulta_ids": [s]})
    assert r.status_code == 400


def test_cobranca_manual(client, db_ctx):
    cen = _cenario(db_ctx)
    c = autenticado(client, cen.sec_a)
    corpo = {"paciente_id": cen.paciente_a1, "descricao": "Material", "valor_centavos": 5000, "vencimento": "2026-12-10"}
    r = c.post("/api/financeiro/cobranca", json=corpo)
    assert r.status_code == 201
    cob = _cob(r.get_json()["id"])
    assert (cob["tipo"], cob["organizacao_id"], cob["status"]) == ("manual", cen.org_a, "pendente")
    assert c.post("/api/financeiro/cobranca", json={**corpo, "valor_centavos": 0}).status_code == 400
    assert c.post("/api/financeiro/cobranca", json={**corpo, "vencimento": "10/12/2026"}).status_code == 400
    assert c.post("/api/financeiro/cobranca", json={k: v for k, v in corpo.items() if k != "vencimento"}).status_code == 400
    assert c.post("/api/financeiro/cobranca", json=[1]).status_code == 400
    assert autenticado(client, cen.prof_a1).post("/api/financeiro/cobranca", json=corpo).status_code == 403


# ------------------------------------------------------------------ webhook

class _SDKFalso:
    def __init__(self, status="approved", valor=None):
        self._status = status
        self._valor = valor

    def payment(self):
        return self

    def get(self, payment_id, opcoes=None):
        resposta = {"status": self._status}
        if self._valor is not None:
            resposta["transaction_amount"] = self._valor
        return {"response": resposta}


def test_webhook_grava_mercado_pago(db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, 20000, desconto=2000, mp_payment_id="MP-1")
    monkeypatch.setattr(pagamento_service, "_sdk", lambda org: _SDKFalso(valor=180.00))
    assert pagamento_service.processar_webhook("MP-1")["status"] == "pago"
    pgs = db.query("SELECT * FROM pagamentos WHERE cobranca_id = ?", (cid,))
    assert len(pgs) == 1
    assert (pgs[0]["forma"], pgs[0]["recebido_por_nome"], pgs[0]["valor_centavos"], pgs[0]["mp_payment_id"]) == \
        ("pix", "Mercado Pago", 18000, "MP-1")
    assert _cob(cid)["status"] == "pago"
    # idempotente
    pagamento_service.processar_webhook("MP-1")
    assert len(db.query("SELECT * FROM pagamentos WHERE cobranca_id = ?", (cid,))) == 1


def test_webhook_depois_de_estorno_nao_paga_de_novo(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, 20000, mp_payment_id="MP-2")
    monkeypatch.setattr(pagamento_service, "_sdk", lambda org: _SDKFalso())
    pagamento_service.processar_webhook("MP-2")
    pid = db.query_one("SELECT id FROM pagamentos WHERE cobranca_id = ?", (cid,))["id"]
    assert autenticado(client, cen.gestor_a).post(f"/api/financeiro/pagamento/{pid}/estornar", json={"motivo": "devolvido"}).status_code == 200
    pagamento_service.processar_webhook("MP-2")
    assert _cob(cid)["status"] != "pago"
    assert len(db.query("SELECT * FROM pagamentos WHERE cobranca_id = ?", (cid,))) == 1


# ------------------------------------------------------------------ isolamento e auditoria

def test_idor_cobranca_outra_clinica(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, 20000)
    rasc = _cobranca(cen, 20000, status="rascunho", tipo="periodo", periodo_fim="2026-01-01")
    pid = _paga(client, cen, cid, valor_centavos=1000)
    sessao = _sessao(cen, 3)
    c = autenticado(client, cen.gestor_b)
    pre = "/api/financeiro"
    respostas = [
        c.post(f"{pre}/cobranca/{cid}/pagar", json={"forma": "pix"}),
        c.post(f"{pre}/pagamento/{pid}/estornar", json={"motivo": "x"}),
        c.post(f"{pre}/cobranca/{rasc}/liberar"),
        c.put(f"{pre}/cobranca/{rasc}/conferir", json={}),
        c.post(f"{pre}/cobranca/{cid}/cancelar", json={"motivo": "x"}),
        c.post(f"{pre}/cobranca/{cid}/resolver-revisao"),
        c.post(f"{pre}/sessoes/{sessao}/decisao", json={"decisao": "nao_cobrar", "motivo": "x"}),
        c.post(f"{pre}/paciente/{cen.paciente_a1}/cobrar-avulsas", json={"consulta_ids": [sessao]}),
    ]
    assert [r.status_code for r in respostas] == [404] * 8
    assert _cob(cid)["status"] == "parcial" and _cob(rasc)["status"] == "rascunho"
    assert db.query_one("SELECT estornado_em FROM pagamentos WHERE id = ?", (pid,))["estornado_em"] is None
    assert db.query("SELECT * FROM consulta_decisao_cobranca") == []


def test_auditoria(client, db_ctx):
    cen = _cenario(db_ctx)
    ontem = (_hoje() - timedelta(days=1)).isoformat()
    cid = _cobranca(cen, 20000)
    pid = _paga(client, cen, cid, valor_centavos=5000)
    g = autenticado(client, cen.gestor_a)
    g.post(f"/api/financeiro/pagamento/{pid}/estornar", json={"motivo": "teste"})
    g.post(f"/api/financeiro/cobranca/{cid}/cancelar", json={"motivo": "teste"})
    rasc = _cobranca(cen, 15000, status="rascunho", tipo="periodo", periodo_fim=ontem)
    _item(rasc, _sessao(cen, 6))
    g.put(f"/api/financeiro/cobranca/{rasc}/conferir", json={})
    g.post(f"/api/financeiro/cobranca/{rasc}/liberar")
    g.post(f"/api/financeiro/cobranca/{rasc}/resolver-revisao")
    s = _sessao(cen, 3)
    g.post(f"/api/financeiro/sessoes/{s}/decisao", json={"decisao": "nao_cobrar", "motivo": "x"})
    for acao, ent in (("baixa", cid), ("estornar", cid), ("cancelar", cid), ("conferir", rasc), ("liberar", rasc),
                      ("resolver_revisao", rasc)):
        [a] = _auditoria(acao, ent)
        assert a["usuario_id"] == cen.gestor_a["id"] and a["organizacao_id"] == cen.org_a
    assert db.query("SELECT 1 FROM auditoria WHERE entidade = 'consulta' AND entidade_id = ? AND acao = 'decisao'", (s,))


# ------------------------------------------------------------------ rodada de correções 1

def test_webhook_registra_o_valor_realmente_recebido_parcial(db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, 20000, mp_payment_id="MP-3")
    monkeypatch.setattr(pagamento_service, "_sdk", lambda org: _SDKFalso(valor=50.10))
    assert pagamento_service.processar_webhook("MP-3")["status"] == "parcial"
    assert db.query_one("SELECT valor_centavos FROM pagamentos WHERE cobranca_id = ?", (cid,))["valor_centavos"] == 5010
    assert _cob(cid)["status"] == "parcial"


def test_webhook_novo_id_depois_de_estorno_registra(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, 20000, mp_payment_id="MP-4")
    monkeypatch.setattr(pagamento_service, "_sdk", lambda org: _SDKFalso(valor=200.00))
    pagamento_service.processar_webhook("MP-4")
    pagamento_service.processar_webhook("MP-4")   # mesmo id: ignora
    assert len(db.query("SELECT * FROM pagamentos WHERE cobranca_id = ?", (cid,))) == 1
    pid = db.query_one("SELECT id FROM pagamentos WHERE cobranca_id = ?", (cid,))["id"]
    assert autenticado(client, cen.gestor_a).post(f"/api/financeiro/pagamento/{pid}/estornar", json={"motivo": "x"}).status_code == 200
    assert _cob(cid)["status"] != "pago"
    pagamento_service.processar_webhook("MP-4")   # o id estornado não volta
    assert len(db.query("SELECT * FROM pagamentos WHERE cobranca_id = ?", (cid,))) == 1
    # a família paga de novo: outro pagamento do MP na mesma cobrança
    db.execute("UPDATE cobrancas SET mp_payment_id = 'MP-5' WHERE id = ?", (cid,))
    pagamento_service.processar_webhook("MP-5")
    assert [p["mp_payment_id"] for p in db.query("SELECT * FROM pagamentos WHERE cobranca_id = ? ORDER BY id", (cid,))] == ["MP-4", "MP-5"]
    assert _cob(cid)["status"] == "pago"


def test_webhook_em_cobranca_cancelada_registra_e_pede_revisao(db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, 20000, status="cancelado", mp_payment_id="MP-6")
    monkeypatch.setattr(pagamento_service, "_sdk", lambda org: _SDKFalso(valor=200.00))
    assert pagamento_service.processar_webhook("MP-6")["status"] == "cancelado"
    cob = _cob(cid)
    assert (cob["status"], cob["revisar"]) == ("cancelado", 1)
    assert cob["revisar_motivo"] == "Pagamento recebido pelo Mercado Pago em cobrança cancelada"
    assert db.query_one("SELECT valor_centavos FROM pagamentos WHERE cobranca_id = ?", (cid,))["valor_centavos"] == 20000


def test_liberar_e_resolver_corpo_que_nao_e_objeto_400(client, db_ctx):
    cen = _cenario(db_ctx)
    ontem = (_hoje() - timedelta(days=1)).isoformat()
    rasc = _cobranca(cen, status="rascunho", tipo="periodo", periodo_fim=ontem)
    c = autenticado(client, cen.gestor_a)
    assert c.post(f"/api/financeiro/cobranca/{rasc}/liberar", json=[1]).status_code == 400
    assert c.post(f"/api/financeiro/cobranca/{rasc}/resolver-revisao", json="x").status_code == 400
    assert _cob(rasc)["status"] == "rascunho"


def test_desconto_total_libera_como_paga(client, db_ctx):
    cen = _cenario(db_ctx)
    ontem = (_hoje() - timedelta(days=1)).isoformat()
    cid = _cobranca(cen, 15000, status="rascunho", tipo="periodo", periodo_fim=ontem)
    _item(cid, _sessao(cen, 5))
    c = autenticado(client, cen.gestor_a)
    assert c.put(f"/api/financeiro/cobranca/{cid}/conferir",
                 json={"desconto_centavos": 15000, "desconto_motivo": "Cortesia"}).status_code == 200
    r = c.post(f"/api/financeiro/cobranca/{cid}/liberar")
    assert r.status_code == 200 and r.get_json()["status"] == "pago"
    assert _cob(cid)["status"] == "pago"


def test_baixa_exige_forma(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/cobranca/{cid}/pagar", json={"valor_centavos": 1000})
    assert r.status_code == 400
    assert db.query("SELECT * FROM pagamentos WHERE cobranca_id = ?", (cid,)) == []


def test_baixa_manual_grava_meio_dia(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    ontem = (_hoje() - timedelta(days=1)).isoformat()
    assert _pagar(client, cen.gestor_a, cid, valor_centavos=1000, data=ontem).status_code == 200
    assert db.query_one("SELECT pago_em FROM pagamentos WHERE cobranca_id = ?", (cid,))["pago_em"] == f"{ontem} 12:00:00"


def test_reconferir_sem_motivo_mantem_o_motivo_guardado(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, 30000, status="rascunho", tipo="periodo")
    i1, i2 = _item(cid, _sessao(cen, 5)), _item(cid, _sessao(cen, 4))
    c = autenticado(client, cen.gestor_a)
    assert c.put(f"/api/financeiro/cobranca/{cid}/conferir",
                 json={"desconto_centavos": 2000, "desconto_motivo": "Cortesia"}).status_code == 200
    r = c.put(f"/api/financeiro/cobranca/{cid}/conferir", json={"desconto_centavos": 2000, "remover_itens": [i2]})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert _cob(cid)["desconto_motivo"] == "Cortesia"
    # sem motivo guardado e sem enviar: continua exigindo
    outro = _cobranca(cen, 15000, status="rascunho", tipo="periodo")
    _item(outro, _sessao(cen, 7))
    assert c.put(f"/api/financeiro/cobranca/{outro}/conferir", json={"desconto_centavos": 100}).status_code == 400
