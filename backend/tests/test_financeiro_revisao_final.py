"""Financeiro etapa 1: correções da revisão final (08/11/2026). Dinheiro de verdade:
cada teste reproduz um defeito encontrado na revisão do branch inteiro."""
import calendar
import hashlib
import hmac
from datetime import date, timedelta

import pytest

import acordos_service
import ausencias_service
import cobranca_regras
import cobranca_service
import db
import pagamento_service
from factories import novo_usuario, vincular_responsavel
from test_cobranca_sincronizar import _acordo, _cenario as _cenario_base, _cobrancas, _itens, _sessao, _status

from conftest import autenticado

HOJE = ausencias_service.hoje_brasilia()
URL_ACORDOS = "/api/financeiro/paciente/{}/acordos"
FONO = "Fonoaudiologia"


def _cenario(db_ctx):
    cen = _cenario_base(db_ctx)
    cen.sec_a = novo_usuario(cen.org_a, "Secretaria A", "sec@a.com", "secretaria")
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    return cen


def _d(dias_atras):
    return (HOJE - timedelta(days=dias_atras)).isoformat()


def _s(cen, dias_atras, status="realizada", **k):
    return _sessao(cen, f"{_d(dias_atras)} 09:00:00", status=status, **k)


def _chave_falta(cen, ligada):
    db.execute("UPDATE organizacoes SET fin_cobrar_falta = ? WHERE id = ?", (1 if ligada else 0, cen.org_a))


def _cob(cid):
    return db.query_one("SELECT * FROM cobrancas WHERE id = ?", (cid,))


def _nova_cobranca(cen, valor=10000, status="pendente", tipo="manual", venc=None, paciente=None, **extra):
    campos = {"paciente_id": paciente or cen.paciente_a1, "descricao": "Teste", "valor_centavos": valor,
              "vencimento": venc or (HOJE + timedelta(days=10)).isoformat(), "status": status,
              "organizacao_id": cen.org_a, "tipo": tipo}
    campos.update(extra)
    return db.execute(f"INSERT INTO cobrancas ({', '.join(campos)}) VALUES ({', '.join('?' for _ in campos)})",
                      tuple(campos.values()))


def _pagar(cid, valor, estornado=None, forma="dinheiro"):
    return db.execute("INSERT INTO pagamentos (cobranca_id, valor_centavos, forma, estornado_em) VALUES (?, ?, ?, ?)",
                      (cid, valor, forma, estornado))


def _auditoria(entidade, entidade_id):
    return [(a["acao"], a["detalhes"]) for a in db.query(
        "SELECT acao, detalhes FROM auditoria WHERE entidade = ? AND entidade_id = ? ORDER BY id", (entidade, entidade_id))]


class _SDK:
    """Mercado Pago falso: guarda a criação do PIX e responde à consulta do pagamento."""
    def __init__(self, status="approved", valor=None, referencia=None, aprovado_em=None):
        self.resposta = {"status": status}
        if valor is not None:
            self.resposta["transaction_amount"] = valor
        if referencia is not None:
            self.resposta["external_reference"] = referencia
        if aprovado_em is not None:
            self.resposta["date_approved"] = aprovado_em
        self.criados = []

    def payment(self):
        return self

    def get(self, payment_id, opcoes=None):
        return {"response": self.resposta}

    def create(self, dados, opcoes=None):
        self.criados.append((dados, opcoes))
        return {"status": 201, "response": {"id": 1000 + len(self.criados), "status": "pending",
                                            "point_of_interaction": {"transaction_data": {"qr_code": "qr"}}}}


# ------------------------------------------------------------------ C1: incluir sessões no acordo novo

def test_c1_mensalidade_com_sessao_antiga_gera_so_o_mes_corrente(client, db_ctx):
    cen = _cenario(db_ctx)
    s1 = _s(cen, 300)
    c = autenticado(client, cen.gestor_a)
    r = c.post(URL_ACORDOS.format(cen.paciente_a1), json={
        "tipo": "mensalidade", "especialidade": FONO, "valor_centavos": 80000, "dia_vencimento": 10,
        "incluir_consultas": [s1]})
    assert r.status_code == 201, r.get_data(as_text=True)
    a = db.query_one("SELECT * FROM acordos_pagamento WHERE id = ?", (r.get_json()["id"],))
    assert a["inicio"] == HOJE.isoformat()   # não recua
    cobranca_service.sincronizar(cen.org_a)
    cobs = _cobrancas(cen.org_a)
    assert len(cobs) == 1 and cobs[0]["periodo_inicio"] == HOJE.replace(day=1).isoformat()
    assert cobs[0]["valor_centavos"] == cobranca_regras.mensalidade_do_mes(80000, HOJE.year, HOJE.month, HOJE.isoformat(), None)
    # a sessão incluída fica coberta: não é mais pendência
    assert acordos_service.sessoes_sem_acordo(cen.org_a, cen.paciente_a1, None, HOJE.isoformat()) == []
    assert cobranca_service.sincronizar(cen.org_a) == {"criadas": 0, "itens": 0, "revisar": 0}


def test_c1_avulsa_so_a_marcada_vira_item(client, db_ctx):
    cen = _cenario(db_ctx)
    s1, s2 = _s(cen, 60), _s(cen, 30)
    c = autenticado(client, cen.gestor_a)
    assert c.post(URL_ACORDOS.format(cen.paciente_a1), json={
        "tipo": "avulsa", "ciclo": "consulta", "especialidade": FONO, "incluir_consultas": [s1]}).status_code == 201
    cobranca_service.sincronizar(cen.org_a)
    assert [i["consulta_id"] for i in db.query("SELECT consulta_id FROM cobranca_itens")] == [s1]
    r = c.get(f"/api/financeiro/paciente/{cen.paciente_a1}/sem-acordo")
    assert [x["consulta_id"] for x in r.get_json()] == [s2]


def test_c1_desmarcada_dentro_da_vigencia_continua_sem_acordo(client, db_ctx):
    cen = _cenario(db_ctx)
    s1, s2 = _s(cen, 60), _s(cen, 30)
    c = autenticado(client, cen.gestor_a)
    assert c.post(URL_ACORDOS.format(cen.paciente_a1), json={
        "tipo": "avulsa", "ciclo": "consulta", "especialidade": FONO, "inicio": _d(90),
        "incluir_consultas": [s1]}).status_code == 201
    cobranca_service.sincronizar(cen.org_a)
    assert [i["consulta_id"] for i in db.query("SELECT consulta_id FROM cobranca_itens")] == [s1]
    assert [x["consulta_id"] for x in acordos_service.sessoes_sem_acordo(cen.org_a, None, None, HOJE.isoformat())] == [s2]
    # sessão finalizada depois de criar o acordo, na vigência: entra normalmente
    s3 = _s(cen, 20)
    cobranca_service.sincronizar(cen.org_a)
    assert sorted(i["consulta_id"] for i in db.query("SELECT consulta_id FROM cobranca_itens")) == [s1, s3]


def test_c1_sem_a_lista_vale_a_vigencia(client, db_ctx):
    cen = _cenario(db_ctx)
    s1 = _s(cen, 30)
    c = autenticado(client, cen.gestor_a)
    assert c.post(URL_ACORDOS.format(cen.paciente_a1), json={
        "tipo": "avulsa", "ciclo": "consulta", "especialidade": FONO, "inicio": _d(90)}).status_code == 201
    cobranca_service.sincronizar(cen.org_a)
    assert [i["consulta_id"] for i in db.query("SELECT consulta_id FROM cobranca_itens")] == [s1]


def test_c1_pacote_consome_a_sessao_incluida(client, db_ctx):
    cen = _cenario(db_ctx)
    s1, s2 = _s(cen, 200), _s(cen, 100)
    c = autenticado(client, cen.gestor_a)
    r = c.post(URL_ACORDOS.format(cen.paciente_a1), json={
        "tipo": "pacote", "especialidade": FONO, "sessoes_total": 4, "valor_centavos": 40000, "parcelas": 1,
        "primeiro_vencimento": (HOJE + timedelta(days=5)).isoformat(), "incluir_consultas": [s1]})
    assert r.status_code == 201
    cobranca_service.sincronizar(cen.org_a)
    assert [p["consulta_id"] for p in db.query("SELECT consulta_id FROM acordo_pacote_consumo")] == [s1]
    assert [x["consulta_id"] for x in acordos_service.sessoes_sem_acordo(cen.org_a, None, None, HOJE.isoformat())] == [s2]


def test_c1_sessao_deixada_de_fora_entra_em_outro_acordo_depois(client, db_ctx):
    cen = _cenario(db_ctx)
    s1 = _s(cen, 30)
    c = autenticado(client, cen.gestor_a)
    aid = c.post(URL_ACORDOS.format(cen.paciente_a1), json={
        "tipo": "avulsa", "ciclo": "consulta", "especialidade": FONO, "inicio": _d(90),
        "incluir_consultas": []}).get_json()["id"]
    cobranca_service.sincronizar(cen.org_a)
    assert db.query("SELECT 1 AS x FROM cobranca_itens") == []
    assert c.post(f"/api/financeiro/acordos/{aid}/encerrar", json={}).status_code == 200
    r = c.post(URL_ACORDOS.format(cen.paciente_a1), json={
        "tipo": "avulsa", "ciclo": "consulta", "especialidade": FONO, "incluir_consultas": [s1]})
    assert r.status_code == 201, r.get_data(as_text=True)
    cobranca_service.sincronizar(cen.org_a)
    assert [i["consulta_id"] for i in db.query("SELECT consulta_id FROM cobranca_itens")] == [s1]


def test_c1_excluir_consulta_incluida_nao_quebra(client, db_ctx):
    cen = _cenario(db_ctx)
    s1 = _s(cen, 30)
    c = autenticado(client, cen.gestor_a)
    assert c.post(URL_ACORDOS.format(cen.paciente_a1), json={
        "tipo": "mensalidade", "especialidade": FONO, "valor_centavos": 80000, "dia_vencimento": 10,
        "incluir_consultas": [s1]}).status_code == 201
    _status(s1, "cancelada")
    assert c.delete(f"/api/agenda/{s1}").status_code == 200
    assert db.query("SELECT 1 AS x FROM consulta_acordo_incluida") == []


def test_c1_sem_acordo_traz_o_valor_efetivo(client, db_ctx):
    cen = _cenario(db_ctx)
    s1 = _s(cen, 30, valor=0)
    c = autenticado(client, cen.gestor_a)
    assert c.post(f"/api/financeiro/sessoes/{s1}/decisao", json={"decisao": "valor", "valor_centavos": 7000}).status_code == 200
    [x] = c.get(f"/api/financeiro/paciente/{cen.paciente_a1}/sem-acordo").get_json()
    assert x["valor_centavos"] == 7000


# ------------------------------------------------------------------ C2: status_origem

def test_c2_item_grava_status_de_origem(client, db_ctx):
    cen = _cenario(db_ctx)
    _chave_falta(cen, True)
    _acordo(cen, "avulsa", ciclo="consulta")
    s1, s2 = _s(cen, 5), _s(cen, 4, status="faltou")
    cobranca_service.sincronizar(cen.org_a)
    origem = {i["consulta_id"]: i["status_origem"] for i in db.query("SELECT consulta_id, status_origem FROM cobranca_itens")}
    assert origem == {s1: "realizada", s2: "faltou"}


def test_c2_cobrar_avulsas_grava_status_de_origem(client, db_ctx):
    cen = _cenario(db_ctx)
    s1 = _s(cen, 5)
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/paciente/{cen.paciente_a1}/cobrar-avulsas",
                                               json={"consulta_ids": [s1]})
    assert r.status_code == 201
    assert db.query_one("SELECT status_origem FROM cobranca_itens WHERE consulta_id = ?", (s1,))["status_origem"] == "realizada"


def test_c2_realizada_que_virou_falta_sem_chave_sai_da_avulsa(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="consulta")
    s = _s(cen, 2)
    cobranca_service.sincronizar(cen.org_a)
    _status(s, "faltou")
    cobranca_service.sincronizar(cen.org_a)
    [cob] = _cobrancas(cen.org_a)
    assert (cob["status"], cob["valor_centavos"], cob["revisar"]) == ("cancelado", 0, 0)
    assert db.query("SELECT 1 AS x FROM cobranca_itens") == []
    assert cobranca_service.sincronizar(cen.org_a) == {"criadas": 0, "itens": 0, "revisar": 0}


def test_c2_realizada_que_virou_falta_sem_chave_sai_do_rascunho(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="mensal")
    s1, s2 = _s(cen, 2), _s(cen, 1)
    cobranca_service.sincronizar(cen.org_a)
    _status(s1, "faltou")
    cobranca_service.sincronizar(cen.org_a)
    [cob] = _cobrancas(cen.org_a)
    assert [i["consulta_id"] for i in _itens(cob["id"])] == [s2] and cob["valor_centavos"] == 15000


def test_c2_paga_vira_revisar_sem_mudar_valor(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="consulta")
    s = _s(cen, 2)
    cobranca_service.sincronizar(cen.org_a)
    [cob] = _cobrancas(cen.org_a)
    _pagar(cob["id"], 15000)
    db.execute("UPDATE cobrancas SET status = 'pago' WHERE id = ?", (cob["id"],))
    _status(s, "faltou")
    res = cobranca_service.sincronizar(cen.org_a)
    assert res["revisar"] == 1
    c = _cob(cob["id"])
    assert (c["status"], c["valor_centavos"], c["revisar"]) == ("pago", 15000, 1)
    assert "Não compareceu" in c["revisar_motivo"]
    assert cobranca_service.sincronizar(cen.org_a)["revisar"] == 0


def test_c2_desligar_a_chave_nao_desfaz_falta_cobrada(db_ctx):
    cen = _cenario(db_ctx)
    _chave_falta(cen, True)
    _acordo(cen, "avulsa", ciclo="consulta")
    _s(cen, 2, status="faltou")
    cobranca_service.sincronizar(cen.org_a)
    _chave_falta(cen, False)
    assert cobranca_service.sincronizar(cen.org_a)["revisar"] == 0
    [cob] = _cobrancas(cen.org_a)
    assert (cob["status"], cob["valor_centavos"], cob["revisar"]) == ("pendente", 15000, 0)
    assert len(_itens(cob["id"])) == 1


def test_c2_virou_falta_com_a_chave_ligada_fica_cobrada_mesmo_desligando_depois(db_ctx):
    cen = _cenario(db_ctx)
    _chave_falta(cen, True)
    _acordo(cen, "avulsa", ciclo="consulta")
    s = _s(cen, 2)
    cobranca_service.sincronizar(cen.org_a)
    _status(s, "faltou")
    cobranca_service.sincronizar(cen.org_a)   # falta cobrada: a origem acompanha
    assert db.query_one("SELECT status_origem FROM cobranca_itens")["status_origem"] == "faltou"
    _chave_falta(cen, False)
    cobranca_service.sincronizar(cen.org_a)
    assert len(db.query("SELECT 1 AS x FROM cobranca_itens")) == 1


def test_c2_falta_cobrada_que_virou_realizada_e_depois_falta_sem_chave_sai(db_ctx):
    cen = _cenario(db_ctx)
    _chave_falta(cen, True)
    _acordo(cen, "avulsa", ciclo="consulta")
    s = _s(cen, 2, status="faltou")
    cobranca_service.sincronizar(cen.org_a)
    _status(s, "realizada")
    cobranca_service.sincronizar(cen.org_a)
    _chave_falta(cen, False)
    _status(s, "faltou")
    cobranca_service.sincronizar(cen.org_a)
    assert db.query("SELECT 1 AS x FROM cobranca_itens") == []


def test_c2_pacote_devolve_realizada_que_virou_falta_sem_chave(db_ctx):
    cen = _cenario(db_ctx)
    aid = _acordo(cen, "pacote", sessoes_total=3, valor_centavos=30000, parcelas=1, primeiro_vencimento=_d(-5))
    s1, s2 = _s(cen, 5), _s(cen, 4)
    cobranca_service.sincronizar(cen.org_a)
    _status(s1, "faltou")
    cobranca_service.sincronizar(cen.org_a)
    rows = db.query("SELECT consulta_id, numero FROM acordo_pacote_consumo WHERE acordo_id = ?", (aid,))
    assert [(r["consulta_id"], r["numero"]) for r in rows] == [(s2, 1)]


def test_c2_pacote_desligar_a_chave_nao_devolve_falta_consumida(db_ctx):
    cen = _cenario(db_ctx)
    _chave_falta(cen, True)
    aid = _acordo(cen, "pacote", sessoes_total=3, valor_centavos=30000, parcelas=1, primeiro_vencimento=_d(-5))
    s = _s(cen, 5, status="faltou")
    cobranca_service.sincronizar(cen.org_a)
    _chave_falta(cen, False)
    cobranca_service.sincronizar(cen.org_a)
    assert [r["consulta_id"] for r in db.query("SELECT consulta_id FROM acordo_pacote_consumo WHERE acordo_id = ?", (aid,))] == [s]


# ------------------------------------------------------------------ I1: liberar aplica o vencimento mínimo

def test_i1_liberar_rascunho_antigo_nao_nasce_vencido(client, db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="mensal")
    _s(cen, 70)
    cobranca_service.sincronizar(cen.org_a)
    [cob] = _cobrancas(cen.org_a)
    assert cob["status"] == "rascunho" and cob["vencimento"] < HOJE.isoformat()
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/cobranca/{cob['id']}/liberar")
    assert r.status_code == 200 and r.get_json()["status"] == "pendente"
    assert _cob(cob["id"])["vencimento"] == (HOJE + timedelta(days=5)).isoformat()


def test_i1_liberar_mantem_vencimento_que_ainda_nao_passou(client, db_ctx):
    cen = _cenario(db_ctx)
    venc = (HOJE + timedelta(days=2)).isoformat()
    cid = _nova_cobranca(cen, status="rascunho", tipo="periodo", periodo_fim=_d(1), venc=venc)
    assert autenticado(client, cen.gestor_a).post(f"/api/financeiro/cobranca/{cid}/liberar").status_code == 200
    assert _cob(cid)["vencimento"] == venc


# ------------------------------------------------------------------ I2: fim da mensalidade + desconto

def _mensalidade(client, cen, inicio, valor=80000):
    c = autenticado(client, cen.gestor_a)
    r = c.post(URL_ACORDOS.format(cen.paciente_a1), json={
        "tipo": "mensalidade", "especialidade": FONO, "valor_centavos": valor, "dia_vencimento": 10, "inicio": inicio})
    assert r.status_code == 201, r.get_data(as_text=True)
    cobranca_service.sincronizar(cen.org_a)
    return c, r.get_json()["id"]


def _primeiro_do_mes(meses_atras):
    m = HOJE.month - 1 - meses_atras
    return date(HOJE.year + m // 12, m % 12 + 1, 1)


def _ultimo_dia(d):
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def test_i2_encerrar_recalcula_o_mes_sem_pagamento(client, db_ctx):
    cen = _cenario(db_ctx)
    inicio = HOJE.replace(day=1).isoformat()
    c, aid = _mensalidade(client, cen, inicio)
    [cob] = _cobrancas(cen.org_a)
    assert cob["valor_centavos"] == 80000
    assert c.post(f"/api/financeiro/acordos/{aid}/encerrar", json={"fim": HOJE.isoformat()}).status_code == 200
    esperado = cobranca_regras.mensalidade_do_mes(80000, HOJE.year, HOJE.month, inicio, HOJE.isoformat())
    assert _cob(cob["id"])["valor_centavos"] == esperado
    if esperado != 80000:   # (no último dia do mês o valor não muda)
        assert any(a == "recalcular" for a, _ in _auditoria("cobranca", cob["id"]))


def test_i2_mes_inteiro_depois_do_fim_e_cancelado(client, db_ctx):
    cen = _cenario(db_ctx)
    mes_passado = _primeiro_do_mes(1)
    c, aid = _mensalidade(client, cen, _primeiro_do_mes(2).isoformat())
    cobs = _cobrancas(cen.org_a)
    assert len(cobs) == 3
    fim = _ultimo_dia(_primeiro_do_mes(2)).isoformat()
    assert c.post(f"/api/financeiro/acordos/{aid}/encerrar", json={"fim": fim}).status_code == 200
    por_mes = {x["periodo_inicio"]: x for x in _cobrancas(cen.org_a)}
    assert por_mes[_primeiro_do_mes(2).isoformat()]["status"] != "cancelado"
    assert por_mes[_primeiro_do_mes(2).isoformat()]["valor_centavos"] == 80000
    for m in (mes_passado.isoformat(), HOJE.replace(day=1).isoformat()):
        assert (por_mes[m]["status"], por_mes[m]["valor_centavos"]) == ("cancelado", 0)
        assert any(a == "recalcular" for a, _ in _auditoria("cobranca", por_mes[m]["id"]))


def test_i2_com_pagamento_vira_revisar_e_nao_muda_valor(client, db_ctx):
    cen = _cenario(db_ctx)
    c, aid = _mensalidade(client, cen, _primeiro_do_mes(1).isoformat())
    atual = [x for x in _cobrancas(cen.org_a) if x["periodo_inicio"] == HOJE.replace(day=1).isoformat()][0]
    assert c.post(f"/api/financeiro/cobranca/{atual['id']}/pagar", json={"forma": "pix", "valor_centavos": 1000}).status_code == 200
    fim = _ultimo_dia(_primeiro_do_mes(1)).isoformat()
    assert c.post(f"/api/financeiro/acordos/{aid}/encerrar", json={"fim": fim}).status_code == 200
    x = _cob(atual["id"])
    assert (x["valor_centavos"], x["revisar"]) == (80000, 1)
    assert "Mensalidade" in x["revisar_motivo"] and x["status"] != "cancelado"


def test_i2_put_fim_recalcula_e_estender_reabre(client, db_ctx):
    cen = _cenario(db_ctx)
    c, aid = _mensalidade(client, cen, _primeiro_do_mes(1).isoformat())
    atual = [x for x in _cobrancas(cen.org_a) if x["periodo_inicio"] == HOJE.replace(day=1).isoformat()][0]
    fim = _ultimo_dia(_primeiro_do_mes(1)).isoformat()
    assert c.put(f"/api/financeiro/acordos/{aid}", json={"fim": fim}).status_code == 200
    assert (_cob(atual["id"])["status"], _cob(atual["id"])["valor_centavos"]) == ("cancelado", 0)
    # estendeu de novo: a cobrança cancelada pelo fim volta (o índice só deixa uma por mês)
    assert c.put(f"/api/financeiro/acordos/{aid}", json={"fim": None}).status_code == 200
    assert (_cob(atual["id"])["status"], _cob(atual["id"])["valor_centavos"]) == (
        "pendente" if _cob(atual["id"])["vencimento"] >= HOJE.isoformat() else "vencido", 80000)


def test_i2_cancelada_pelo_gestor_nao_volta(client, db_ctx):
    cen = _cenario(db_ctx)
    c, aid = _mensalidade(client, cen, HOJE.replace(day=1).isoformat())
    [cob] = _cobrancas(cen.org_a)
    assert c.post(f"/api/financeiro/cobranca/{cob['id']}/cancelar", json={"motivo": "Combinado"}).status_code == 200
    assert c.put(f"/api/financeiro/acordos/{aid}", json={"fim": HOJE.isoformat()}).status_code == 200
    assert c.put(f"/api/financeiro/acordos/{aid}", json={"fim": None}).status_code == 200
    assert _cob(cob["id"])["status"] == "cancelado"


def test_i2_put_fim_sem_mudanca_no_mes_nao_mexe(client, db_ctx):
    cen = _cenario(db_ctx)
    c, aid = _mensalidade(client, cen, HOJE.replace(day=1).isoformat())
    [cob] = _cobrancas(cen.org_a)
    fim = (_ultimo_dia(HOJE) + timedelta(days=40)).isoformat()
    assert c.put(f"/api/financeiro/acordos/{aid}", json={"fim": fim}).status_code == 200
    assert _cob(cob["id"])["valor_centavos"] == 80000
    assert not any(a == "recalcular" for a, _ in _auditoria("cobranca", cob["id"]))


def test_i2_desconto_maior_que_o_novo_valor_e_limitado(client, db_ctx):
    cen = _cenario(db_ctx)
    inicio = _primeiro_do_mes(1)
    c, aid = _mensalidade(client, cen, inicio.isoformat())
    passada = [x for x in _cobrancas(cen.org_a) if x["periodo_inicio"] == inicio.isoformat()][0]
    db.execute("UPDATE cobrancas SET desconto_centavos = 79000, desconto_motivo = 'x' WHERE id = ?", (passada["id"],))
    fim = inicio.isoformat()   # só 1 dia do mês passado
    assert c.post(f"/api/financeiro/acordos/{aid}/encerrar", json={"fim": fim}).status_code == 200
    x = _cob(passada["id"])
    assert x["valor_centavos"] == cobranca_regras.mensalidade_do_mes(80000, inicio.year, inicio.month, fim, fim)
    assert x["desconto_centavos"] <= x["valor_centavos"]


def _url_desconto(cid):
    return f"/api/financeiro/cobranca/{cid}/desconto"


def test_i2_rota_desconto(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen, 10000)
    c = autenticado(client, cen.gestor_a)
    assert c.post(_url_desconto(cid), json={"desconto_centavos": 1000}).status_code == 400   # sem motivo
    assert c.post(_url_desconto(cid), json={"desconto_centavos": 10001, "desconto_motivo": "x"}).status_code == 400
    assert c.post(_url_desconto(cid), json={"desconto_centavos": True, "desconto_motivo": "x"}).status_code == 400
    assert c.post(_url_desconto(cid), json=[1]).status_code == 400
    r = c.post(_url_desconto(cid), json={"desconto_centavos": 1000, "desconto_motivo": "Combinado"})
    assert r.status_code == 200 and r.get_json()["status"] == "pendente"
    x = _cob(cid)
    assert (x["desconto_centavos"], x["desconto_motivo"]) == (1000, "Combinado")
    assert any(a == "desconto" and "Combinado" in d for a, d in _auditoria("cobranca", cid))
    assert pagamento_service.saldo_centavos(cid) == 9000


def test_i2_rota_desconto_total_vira_paga(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen, 10000)
    r = autenticado(client, cen.gestor_a).post(_url_desconto(cid), json={"desconto_centavos": 10000, "desconto_motivo": "Cortesia"})
    assert r.status_code == 200 and r.get_json()["status"] == "pago"


def test_i2_rota_desconto_nao_fica_abaixo_do_que_foi_pago(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen, 10000, status="parcial")
    _pagar(cid, 6000)
    c = autenticado(client, cen.gestor_a)
    assert c.post(_url_desconto(cid), json={"desconto_centavos": 5000, "desconto_motivo": "x"}).status_code == 400
    assert _cob(cid)["desconto_centavos"] == 0
    r = c.post(_url_desconto(cid), json={"desconto_centavos": 4000, "desconto_motivo": "x"})
    assert r.status_code == 200 and r.get_json()["status"] == "pago"


@pytest.mark.parametrize("status", ["rascunho", "pago", "cancelado"])
def test_i2_rota_desconto_so_em_aberto(client, db_ctx, status):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen, 10000, status=status)
    r = autenticado(client, cen.gestor_a).post(_url_desconto(cid), json={"desconto_centavos": 100, "desconto_motivo": "x"})
    assert r.status_code == 409


def test_i2_rota_desconto_permissoes(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen, 10000)
    corpo = {"desconto_centavos": 100, "desconto_motivo": "x"}
    assert autenticado(client, cen.sec_a).post(_url_desconto(cid), json=corpo).status_code == 403
    assert autenticado(client, cen.prof_a1).post(_url_desconto(cid), json=corpo).status_code == 403
    assert autenticado(client, cen.resp_a1).post(_url_desconto(cid), json=corpo).status_code == 403
    assert autenticado(client, cen.gestor_b).post(_url_desconto(cid), json=corpo).status_code == 404


# ------------------------------------------------------------------ I3: encerrar não aceita data futura

def test_i3_encerrar_recusa_data_futura(client, db_ctx):
    cen = _cenario(db_ctx)
    c, aid = _mensalidade(client, cen, HOJE.replace(day=1).isoformat())
    r = c.post(f"/api/financeiro/acordos/{aid}/encerrar", json={"fim": (HOJE + timedelta(days=1)).isoformat()})
    assert r.status_code == 400 and "Editar" in r.get_json()["erro"]
    assert db.query_one("SELECT status FROM acordos_pagamento WHERE id = ?", (aid,))["status"] == "ativo"


def test_i3_encerrar_recusa_data_depois_do_fim_atual(client, db_ctx):
    cen = _cenario(db_ctx)
    c, aid = _mensalidade(client, cen, _primeiro_do_mes(2).isoformat())
    fim = _ultimo_dia(_primeiro_do_mes(2)).isoformat()
    assert c.put(f"/api/financeiro/acordos/{aid}", json={"fim": fim}).status_code == 200
    r = c.post(f"/api/financeiro/acordos/{aid}/encerrar", json={"fim": HOJE.isoformat()})
    assert r.status_code == 400 and "Editar" in r.get_json()["erro"]
    # sem data: encerra no fim que já existia, não em hoje
    assert c.post(f"/api/financeiro/acordos/{aid}/encerrar", json={}).status_code == 200
    assert db.query_one("SELECT fim FROM acordos_pagamento WHERE id = ?", (aid,))["fim"] == fim


# ------------------------------------------------------------------ I4: gerar PIX

def _pix(client, usuario, cid):
    return autenticado(client, usuario).post(f"/api/financeiro/cobranca/{cid}/gerar-pix")


@pytest.fixture
def pix_falso(monkeypatch):
    monkeypatch.setattr(pagamento_service, "criar_pagamento_pix", lambda i: {"ok": 1})


def test_i4_gestor_secretaria_e_admin_geram(client, db_ctx, pix_falso):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen)
    assert _pix(client, cen.gestor_a, cid).status_code == 200
    assert _pix(client, cen.sec_a, cid).status_code == 200
    admin = novo_usuario(cen.org_a, "Admin", "adm@a.com", "admin_master")
    assert _pix(client, admin, cid).status_code == 200


def test_i4_profissional_nao_gera(client, db_ctx, pix_falso):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen)
    assert _pix(client, cen.prof_a1, cid).status_code == 403


def test_i4_responsavel_so_do_proprio_filho_e_com_financeiro_visivel(client, db_ctx, pix_falso):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen)
    assert _pix(client, cen.resp_a1, cid).status_code == 200
    outro = novo_usuario(cen.org_a, "Outro", "outro@a.com", "responsavel")
    assert _pix(client, outro, cid).status_code == 403
    db.execute("UPDATE usuarios SET financeiro_habilitado_override = 0 WHERE id = ?", (cen.resp_a1["id"],))
    assert _pix(client, cen.resp_a1, cid).status_code == 403


def test_i4_outra_clinica_404_e_inexistente_404(client, db_ctx, pix_falso):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen)
    assert _pix(client, cen.gestor_b, cid).status_code == 404
    assert _pix(client, cen.gestor_a, 999999).status_code == 404


def test_i4_saldo_zero_409(client, db_ctx, pix_falso):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen, 10000, status="vencido", desconto_centavos=10000)
    assert _pix(client, cen.gestor_a, cid).status_code == 409
    assert _pix(client, cen.resp_a1, cid).status_code == 409


# ------------------------------------------------------------------ I5: QR anterior e valor acima do saldo

def _assinatura(secret, payment_id, request_id="req-1", ts="1700000000"):
    v1 = hmac.new(secret.encode(), f"id:{payment_id};request-id:{request_id};ts:{ts};".encode(), hashlib.sha256).hexdigest()
    return {"x-signature": f"ts={ts},v1={v1}", "x-request-id": request_id}


def test_i5_chave_de_idempotencia_muda_com_o_saldo(db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen, 10000)
    sdk = _SDK()
    monkeypatch.setattr(pagamento_service, "_sdk", lambda org: sdk)
    pagamento_service.criar_pagamento_pix(cid)
    _pagar(cid, 4000)
    pagamento_service.criar_pagamento_pix(cid)
    chaves = [o.custom_headers["X-Idempotency-Key"] for _, o in sdk.criados]
    assert chaves == [f"cobranca-{cid}-pix-10000", f"cobranca-{cid}-pix-6000"]
    assert sdk.criados[1][0]["transaction_amount"] == 60.0


def test_i5_webhook_do_qr_anterior_acha_pela_referencia(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    pagamento_service.salvar_access_token(cen.org_a, "APP_USR-a", None, "segredo-a")
    pagamento_service.salvar_access_token(cen.org_b, "APP_USR-b", None, "segredo-b")
    cid = _nova_cobranca(cen, 10000, mp_payment_id="QR-NOVO")
    monkeypatch.setattr(pagamento_service, "_sdk", lambda org: _SDK(valor=100.0, referencia=f"cobranca-{cid}"))
    r = client.post("/api/integracoes/pagamento/webhook?data.id=QR-VELHO", headers=_assinatura("segredo-a", "QR-VELHO"))
    assert r.status_code == 200 and r.get_json()["status"] == "pago", r.get_data(as_text=True)
    pg = db.query_one("SELECT * FROM pagamentos WHERE cobranca_id = ?", (cid,))
    assert (pg["mp_payment_id"], pg["valor_centavos"]) == ("QR-VELHO", 10000)
    # repetido: não duplica
    assert client.post("/api/integracoes/pagamento/webhook?data.id=QR-VELHO",
                       headers=_assinatura("segredo-a", "QR-VELHO")).status_code == 200
    assert len(db.query("SELECT 1 AS x FROM pagamentos WHERE cobranca_id = ?", (cid,))) == 1


def test_i5_webhook_sem_assinatura_valida_nao_baixa(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    pagamento_service.salvar_access_token(cen.org_a, "APP_USR-a", None, "segredo-a")
    cid = _nova_cobranca(cen, 10000, mp_payment_id="QR-NOVO")
    monkeypatch.setattr(pagamento_service, "_sdk", lambda org: _SDK(valor=100.0, referencia=f"cobranca-{cid}"))
    r = client.post("/api/integracoes/pagamento/webhook?data.id=QR-VELHO", headers=_assinatura("errado", "QR-VELHO"))
    assert r.status_code == 200 and r.get_json().get("ignorado")
    assert db.query("SELECT 1 AS x FROM pagamentos") == []


def test_i5_referencia_de_outra_clinica_e_ignorada(db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen, 10000)   # da clínica A
    monkeypatch.setattr(pagamento_service, "_sdk", lambda org: _SDK(valor=100.0, referencia=f"cobranca-{cid}"))
    r = pagamento_service.processar_webhook("QR-X", cen.org_b)
    assert r.get("ignorado")
    assert db.query("SELECT 1 AS x FROM pagamentos") == []


@pytest.mark.parametrize("referencia", [None, "outra-coisa", "cobranca-abc", "cobranca-999999"])
def test_i5_referencia_invalida_e_ignorada(db_ctx, monkeypatch, referencia):
    cen = _cenario(db_ctx)
    monkeypatch.setattr(pagamento_service, "_sdk", lambda org: _SDK(valor=100.0, referencia=referencia))
    assert pagamento_service.processar_webhook("QR-X", cen.org_a).get("ignorado")
    assert db.query("SELECT 1 AS x FROM pagamentos") == []


def test_i5_recebido_acima_do_saldo_registra_e_marca_revisar(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen, 10000, mp_payment_id="777")
    assert autenticado(client, cen.gestor_a).post(f"/api/financeiro/cobranca/{cid}/pagar",
                                                  json={"forma": "dinheiro"}).status_code == 200
    monkeypatch.setattr(pagamento_service, "_sdk", lambda org: _SDK(valor=100.0))
    assert pagamento_service.processar_webhook("777")["status"] == "pago"
    assert pagamento_service.pago_centavos(cid) == 20000
    c = _cob(cid)
    assert c["revisar"] == 1 and "acima do saldo" in c["revisar_motivo"]


def test_i5_recebido_igual_ao_saldo_nao_marca_revisar(db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen, 10000, mp_payment_id="778")
    monkeypatch.setattr(pagamento_service, "_sdk", lambda org: _SDK(valor=100.0))
    pagamento_service.processar_webhook("778")
    assert _cob(cid)["revisar"] == 0


# ------------------------------------------------------------------ I7: pacote esgotado não trava acordo novo

def _pacote_corpo(sessoes=1):
    return {"tipo": "pacote", "especialidade": FONO, "sessoes_total": sessoes, "valor_centavos": 10000, "parcelas": 1,
            "primeiro_vencimento": (HOJE + timedelta(days=5)).isoformat(), "inicio": _d(30)}


def test_i7_pacote_esgotado_e_encerrado_e_o_novo_criado(client, db_ctx):
    cen = _cenario(db_ctx)
    c = autenticado(client, cen.gestor_a)
    velho = c.post(URL_ACORDOS.format(cen.paciente_a1), json=_pacote_corpo()).get_json()["id"]
    _s(cen, 10)
    extra = _s(cen, 5)
    cobranca_service.sincronizar(cen.org_a)
    r = c.post(URL_ACORDOS.format(cen.paciente_a1), json={
        "tipo": "avulsa", "ciclo": "consulta", "especialidade": FONO, "incluir_consultas": [extra]})
    assert r.status_code == 201, r.get_data(as_text=True)
    a = db.query_one("SELECT * FROM acordos_pagamento WHERE id = ?", (velho,))
    assert (a["status"], a["fim"]) == ("encerrado", HOJE.isoformat())
    assert any(ac == "encerrar" for ac, _ in _auditoria("acordo_pagamento", velho))
    cobranca_service.sincronizar(cen.org_a)
    assert [i["consulta_id"] for i in db.query("SELECT consulta_id FROM cobranca_itens")] == [extra]


def test_i7_outro_conflito_409_com_a_mensagem(client, db_ctx):
    cen = _cenario(db_ctx)
    c = autenticado(client, cen.gestor_a)
    assert c.post(URL_ACORDOS.format(cen.paciente_a1), json=_pacote_corpo(sessoes=2)).status_code == 201
    _s(cen, 10)
    cobranca_service.sincronizar(cen.org_a)
    r = c.post(URL_ACORDOS.format(cen.paciente_a1), json={"tipo": "avulsa", "ciclo": "consulta", "especialidade": FONO})
    assert r.status_code == 409
    assert r.get_json()["erro"] == ("Já existe um acordo ativo para essa especialidade. "
                                    "Encerre-o na ficha do paciente antes de criar outro.")


# ------------------------------------------------------------------ M1: editar sessão já cobrada

def _proc(cen, nome, valor):
    return db.execute("INSERT INTO procedimentos (organizacao_id, nome, valor_centavos) VALUES (?, ?, ?)", (cen.org_a, nome, valor))


def test_m1_mudar_data_atualiza_o_item(client, db_ctx):
    cen = _cenario(db_ctx)
    _chave_falta(cen, True)
    _acordo(cen, "avulsa", ciclo="consulta")
    s = _s(cen, 5, status="faltou")
    cobranca_service.sincronizar(cen.org_a)
    nova = f"{_d(6)} 14:00:00"
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{s}", json={"data_hora": nova})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert db.query_one("SELECT data_hora FROM cobranca_itens WHERE consulta_id = ?", (s,))["data_hora"] == nova


def test_m1_mudar_data_renumera_o_pacote(client, db_ctx):
    cen = _cenario(db_ctx)
    _chave_falta(cen, True)
    aid = _acordo(cen, "pacote", sessoes_total=5, valor_centavos=50000, parcelas=1, primeiro_vencimento=_d(-5))
    s1, s2 = _s(cen, 5, status="faltou"), _s(cen, 4, status="faltou")
    cobranca_service.sincronizar(cen.org_a)
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{s2}", json={"data_hora": f"{_d(6)} 09:00:00"})
    assert r.status_code == 200, r.get_data(as_text=True)
    num = {x["consulta_id"]: x["numero"] for x in db.query(
        "SELECT consulta_id, numero FROM acordo_pacote_consumo WHERE acordo_id = ?", (aid,))}
    assert num == {s2: 1, s1: 2}


def test_m1_trocar_procedimento_no_rascunho(client, db_ctx):
    cen = _cenario(db_ctx)
    _chave_falta(cen, True)
    _acordo(cen, "avulsa", ciclo="mensal")
    s = _s(cen, 2, status="faltou")
    cobranca_service.sincronizar(cen.org_a)
    novo = _proc(cen, "Avaliação", 25000)
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{s}", json={"procedimento_id": novo})
    assert r.status_code == 200, r.get_data(as_text=True)
    [cob] = _cobrancas(cen.org_a)
    [it] = _itens(cob["id"])
    assert (it["valor_centavos"], it["procedimento_nome"], cob["valor_centavos"]) == (25000, "Avaliação", 25000)


def test_m1_trocar_procedimento_avulsa_sem_pagamento(client, db_ctx):
    cen = _cenario(db_ctx)
    _chave_falta(cen, True)
    _acordo(cen, "avulsa", ciclo="consulta")
    s = _s(cen, 2, status="faltou")
    cobranca_service.sincronizar(cen.org_a)
    novo = _proc(cen, "Avaliação", 25000)
    assert autenticado(client, cen.gestor_a).put(f"/api/agenda/{s}", json={"procedimento_id": novo}).status_code == 200
    [cob] = _cobrancas(cen.org_a)
    assert (cob["valor_centavos"], cob["revisar"]) == (25000, 0)


def test_m1_trocar_procedimento_com_pagamento_vira_revisar(client, db_ctx):
    cen = _cenario(db_ctx)
    _chave_falta(cen, True)
    _acordo(cen, "avulsa", ciclo="consulta")
    s = _s(cen, 2, status="faltou")
    cobranca_service.sincronizar(cen.org_a)
    [cob] = _cobrancas(cen.org_a)
    _pagar(cob["id"], 1000)
    novo = _proc(cen, "Avaliação", 25000)
    assert autenticado(client, cen.gestor_a).put(f"/api/agenda/{s}", json={"procedimento_id": novo}).status_code == 200
    x = _cob(cob["id"])
    [it] = _itens(cob["id"])
    assert (x["valor_centavos"], it["valor_centavos"], x["revisar"]) == (15000, 15000, 1)
    assert "Avaliação" in x["revisar_motivo"]


def test_m1_periodo_liberado_nao_reabre_vira_revisar(client, db_ctx):
    cen = _cenario(db_ctx)
    _chave_falta(cen, True)
    _acordo(cen, "avulsa", ciclo="mensal")
    s = _s(cen, 70, status="faltou")
    cobranca_service.sincronizar(cen.org_a)
    [cob] = _cobrancas(cen.org_a)
    c = autenticado(client, cen.gestor_a)
    assert c.post(f"/api/financeiro/cobranca/{cob['id']}/liberar").status_code == 200
    novo = _proc(cen, "Avaliação", 25000)
    assert c.put(f"/api/agenda/{s}", json={"procedimento_id": novo}).status_code == 200
    x = _cob(cob["id"])
    assert (x["valor_centavos"], x["revisar"]) == (15000, 1)


def test_m1_manter_o_mesmo_procedimento_nao_mexe(client, db_ctx):
    cen = _cenario(db_ctx)
    _chave_falta(cen, True)
    _acordo(cen, "avulsa", ciclo="consulta")
    s = _s(cen, 2, status="faltou")
    cobranca_service.sincronizar(cen.org_a)
    assert autenticado(client, cen.gestor_a).put(f"/api/agenda/{s}", json={
        "procedimento_id": cen.proc_a, "observacoes": "x"}).status_code == 200
    [cob] = _cobrancas(cen.org_a)
    assert (cob["valor_centavos"], cob["revisar"]) == (15000, 0)


# ------------------------------------------------------------------ M2: corpo não-objeto

def test_m2_rotas_de_acordo_recusam_corpo_que_nao_e_objeto(client, db_ctx):
    cen = _cenario(db_ctx)
    c, aid = _mensalidade(client, cen, HOJE.replace(day=1).isoformat())
    assert c.post(URL_ACORDOS.format(cen.paciente_a1), json=[1]).status_code == 400
    assert c.put(f"/api/financeiro/acordos/{aid}", json=[1]).status_code == 400
    assert c.post(f"/api/financeiro/acordos/{aid}/encerrar", json="x").status_code == 400
    assert db.query_one("SELECT status FROM acordos_pagamento WHERE id = ?", (aid,))["status"] == "ativo"


# ------------------------------------------------------------------ M3: recebido por especialidade

def test_m3_recebido_respeita_especialidade(client, db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="consulta", especialidade=FONO)
    _acordo(cen, "avulsa", ciclo="consulta", especialidade="Terapia Ocupacional")
    _acordo(cen, "avulsa", ciclo="consulta", especialidade="*", paciente=cen.paciente_a2)
    _s(cen, 3)
    _s(cen, 2, esp="Terapia Ocupacional", prof=cen.prof_a2)
    _s(cen, 1, paciente=cen.paciente_a2)   # acordo '*': a especialidade vem da sessão
    cobranca_service.sincronizar(cen.org_a)
    cobs = _cobrancas(cen.org_a)
    assert len(cobs) == 3
    c = autenticado(client, cen.gestor_a)
    for valor, cob in zip((1000, 2000, 4000), cobs):
        assert c.post(f"/api/financeiro/cobranca/{cob['id']}/pagar", json={"forma": "pix", "valor_centavos": valor}).status_code == 200
    total = lambda q="": c.get(f"/api/financeiro/cobrancas{q}").get_json()["totais"]["recebido_centavos"]
    assert total() == 7000
    assert total("?especialidade=fonoaudiologia") == 5000
    assert total("?especialidade=Terapia%20Ocupacional") == 2000
    assert total("?especialidade=Psicologia") == 0


# ------------------------------------------------------------------ M5: conferir trava e relê

def test_m5_conferir_trava_e_rele_o_status(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen, 10000, status="rascunho", tipo="periodo", periodo_fim=_d(1))
    import blueprints.financeiro_bp as fin
    original = fin._travar_cobranca
    chamadas = []

    def travar_e_liberar(i):   # outra pessoa liberou a cobrança entre a 1ª leitura e a trava
        chamadas.append(i)
        original(i)
        db.execute("UPDATE cobrancas SET status = 'pendente' WHERE id = ?", (i,))

    monkeypatch.setattr(fin, "_travar_cobranca", travar_e_liberar)
    r = autenticado(client, cen.gestor_a).put(f"/api/financeiro/cobranca/{cid}/conferir",
                                              json={"desconto_centavos": 500, "desconto_motivo": "x"})
    assert chamadas == [cid] and r.status_code == 409
    assert _cob(cid)["desconto_centavos"] == 0


# ------------------------------------------------------------------ M6: cobrar_avulsas com lixo

@pytest.mark.parametrize("ids", [[{"a": 1}], [[1]], ["1"], [1.5], [True]])
def test_m6_cobrar_avulsas_lista_invalida_400(client, db_ctx, ids):
    cen = _cenario(db_ctx)
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/paciente/{cen.paciente_a1}/cobrar-avulsas",
                                               json={"consulta_ids": ids})
    assert r.status_code == 400


# ------------------------------------------------------------------ M7: decisão em sessão futura ou consumida

def test_m7_decisao_recusa_sessao_futura(client, db_ctx):
    cen = _cenario(db_ctx)
    s = _sessao(cen, f"{(HOJE + timedelta(days=3)).isoformat()} 09:00:00", status="agendada")
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/sessoes/{s}/decisao", json={"decisao": "nao_cobrar", "motivo": "x"})
    assert r.status_code == 409


def test_m7_decisao_recusa_sessao_consumida_de_pacote(client, db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "pacote", sessoes_total=5, valor_centavos=50000, parcelas=1, primeiro_vencimento=_d(-5))
    s = _s(cen, 3)
    cobranca_service.sincronizar(cen.org_a)
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/sessoes/{s}/decisao", json={"decisao": "nao_cobrar", "motivo": "x"})
    assert r.status_code == 409


# ------------------------------------------------------------------ M8: pago_em do webhook

def test_m8_webhook_grava_data_de_brasilia(db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen, 10000, mp_payment_id="M8-1")
    monkeypatch.setattr(pagamento_service, "_sdk", lambda org: _SDK(valor=100.0))
    pagamento_service.processar_webhook("M8-1")
    pg = db.query_one("SELECT pago_em FROM pagamentos WHERE cobranca_id = ?", (cid,))
    assert pg["pago_em"] == f"{HOJE.isoformat()} 12:00:00"


def test_m8_webhook_usa_a_data_da_aprovacao_em_brasilia(db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen, 10000, mp_payment_id="M8-2")
    # 01:30 UTC do dia 2 ainda é dia 1 em Brasília
    monkeypatch.setattr(pagamento_service, "_sdk",
                        lambda org: _SDK(valor=100.0, aprovado_em="2026-10-02T01:30:00.000Z"))
    pagamento_service.processar_webhook("M8-2")
    assert db.query_one("SELECT pago_em FROM pagamentos WHERE cobranca_id = ?", (cid,))["pago_em"] == "2026-10-01 12:00:00"


# ------------------------------------------------------------------ M9: indicadores

def test_m9_indicadores_ignoram_pagamento_estornado(client, db_ctx):
    from datetime import datetime
    cen = _cenario(db_ctx)
    cid = _nova_cobranca(cen, 10000)
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("INSERT INTO pagamentos (cobranca_id, valor_centavos, forma, pago_em) VALUES (?, 100, 'pix', ?)", (cid, agora))
    db.execute("INSERT INTO pagamentos (cobranca_id, valor_centavos, forma, pago_em, estornado_em) VALUES (?, 100, 'pix', ?, ?)",
               (cid, agora, agora))
    r = autenticado(client, cen.gestor_a).get("/api/indicadores/gestor")
    assert r.status_code == 200 and r.get_json()["pagamentos_hoje"] == 1


# ------------------------------------------------------------------ M10: notificação ao liberar

def test_m10_liberar_so_notifica_quem_ve_o_financeiro(client, db_ctx):
    cen = _cenario(db_ctx)
    outro = novo_usuario(cen.org_a, "Familia 2", "familia2@a.com", "responsavel")
    vincular_responsavel(outro["id"], cen.paciente_a1)
    db.execute("UPDATE usuarios SET financeiro_habilitado_override = 0 WHERE id = ?", (outro["id"],))
    cid = _nova_cobranca(cen, status="rascunho", tipo="periodo", periodo_fim=_d(1))
    assert autenticado(client, cen.gestor_a).post(f"/api/financeiro/cobranca/{cid}/liberar").status_code == 200
    para = {n["usuario_id"] for n in db.query("SELECT usuario_id FROM notificacoes WHERE titulo = 'Nova cobrança disponível'")}
    assert para == {cen.resp_a1["id"]}


# ------------------------------------------------------------------ schema / migração

def test_tabela_sem_id_esta_no_conjunto_sem_returning():
    assert "consulta_acordo_incluida" in db._TABELAS_SEM_ID_AUTO
