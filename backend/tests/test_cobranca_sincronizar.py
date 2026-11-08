"""Financeiro etapa 1, task 4: sincronização agenda → cobranças e pendências."""
import db
import planos_padrao
import acordos_service
import cobranca_service
from factories import DuasClinicas, novo_paciente

from conftest import autenticado


def _cenario(db_ctx):
    cen = DuasClinicas()
    planos_padrao.criar_planos_padrao_para_teste()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id IN (?, ?)", (cen.org_a, cen.org_b))
    db_ctx.execute("UPDATE usuarios SET especialidade = 'Fonoaudiologia' WHERE id = ?", (cen.prof_a1["id"],))
    db_ctx.execute("UPDATE usuarios SET especialidade = 'Terapia Ocupacional' WHERE id = ?", (cen.prof_a2["id"],))
    cen.proc_a = db.execute("INSERT INTO procedimentos (organizacao_id, nome, valor_centavos) VALUES (?, 'Sessão', 15000)",
                            (cen.org_a,))
    cen.proc_b = db.execute("INSERT INTO procedimentos (organizacao_id, nome, valor_centavos) VALUES (?, 'Sessão', 15000)",
                            (cen.org_b,))
    return cen


def _sessao(cen, data, status="realizada", esp="Fonoaudiologia", prof=None, valor=15000, paciente=None,
            proc="a"):
    proc_id = {"a": cen.proc_a, "b": cen.proc_b, None: None}[proc]
    return db.execute(
        """INSERT INTO consultas (paciente_id, profissional_id, data_hora, status, especialidade,
                                  procedimento_id, procedimento_valor_centavos)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (paciente or cen.paciente_a1, (prof or cen.prof_a1)["id"], data, status, esp, proc_id, valor))


def _acordo(cen, tipo, org=None, paciente=None, especialidade="Fonoaudiologia", inicio="2026-01-01", **campos):
    dados = {"organizacao_id": org or cen.org_a, "paciente_id": paciente or cen.paciente_a1,
             "especialidade": especialidade, "tipo": tipo, "inicio": inicio, "vence_dias": 5}
    dados.update(campos)
    cols = ", ".join(dados)
    return db.execute(f"INSERT INTO acordos_pagamento ({cols}) VALUES ({', '.join('?' for _ in dados)})",
                      tuple(dados.values()))


def _status(cid, status):
    db.execute("UPDATE consultas SET status = ? WHERE id = ?", (status, cid))


def _cobrancas(org=None, **filtro):
    sql = "SELECT * FROM cobrancas WHERE 1=1"
    params = []
    if org is not None:
        sql += " AND organizacao_id = ?"
        params.append(org)
    for k, v in filtro.items():
        sql += f" AND {k} = ?"
        params.append(v)
    return db.query(sql + " ORDER BY id", tuple(params))


def _itens(cobranca_id):
    return db.query("SELECT * FROM cobranca_itens WHERE cobranca_id = ? ORDER BY id", (cobranca_id,))


def _ids(lista):
    return [s["consulta_id"] for s in lista]


# ------------------------------------------------------------------ avulsa por consulta

def test_avulsa_por_consulta_cria_cobranca_ao_finalizar(db_ctx):
    cen = _cenario(db_ctx)
    aid = _acordo(cen, "avulsa", ciclo="consulta")
    c = _sessao(cen, "2026-11-10 09:00:00", status="agendada")
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-10") == {"criadas": 0, "itens": 0, "revisar": 0}
    _status(c, "realizada")
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-10") == {"criadas": 1, "itens": 1, "revisar": 0}
    [cob] = _cobrancas(cen.org_a)
    assert (cob["tipo"], cob["status"], cob["valor_centavos"], cob["vencimento"]) == \
        ("avulsa", "pendente", 15000, "2026-11-15")
    assert (cob["acordo_id"], cob["paciente_id"]) == (aid, cen.paciente_a1)
    [item] = _itens(cob["id"])
    assert (item["consulta_id"], item["valor_centavos"], item["procedimento_nome"]) == (c, 15000, "Sessão")


def test_falta_so_cobra_com_configuracao(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="consulta")
    _sessao(cen, "2026-11-10 09:00:00", status="faltou")
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-12")["criadas"] == 0
    db.execute("UPDATE organizacoes SET fin_cobrar_falta = 1 WHERE id = ?", (cen.org_a,))
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-12")["criadas"] == 1


def test_falta_justificada_nunca_cobra(db_ctx):
    cen = _cenario(db_ctx)
    db.execute("UPDATE organizacoes SET fin_cobrar_falta = 1 WHERE id = ?", (cen.org_a,))
    _acordo(cen, "avulsa", ciclo="consulta")
    for st in ("falta_justificada", "desmarcada_profissional", "cancelada", "agendada", "confirmada"):
        _sessao(cen, "2026-11-10 09:00:00", status=st)
        _sessao(cen, "2026-11-10 10:00:00", status=st, esp="Psicologia")  # sem acordo
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-12")["criadas"] == 0
    assert cobranca_service.pendencias(cen.org_a, "2026-11-12")["sem_acordo"] == []


# ------------------------------------------------------------------ períodos

def test_quinzenal_agrupa_em_rascunho(db_ctx):
    cen = _cenario(db_ctx)
    aid = _acordo(cen, "avulsa", ciclo="quinzenal")
    s = [_sessao(cen, "2026-11-03 09:00:00"), _sessao(cen, "2026-11-10T9:00:00"), _sessao(cen, "2026-11-14 9:00:00")]
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-14") == {"criadas": 1, "itens": 3, "revisar": 0}
    [cob] = _cobrancas(cen.org_a)
    assert (cob["tipo"], cob["status"], cob["acordo_id"]) == ("periodo", "rascunho", aid)
    assert (cob["periodo_inicio"], cob["periodo_fim"], cob["vencimento"]) == ("2026-11-01", "2026-11-15", "2026-11-20")
    assert cob["valor_centavos"] == 45000
    assert [i["consulta_id"] for i in _itens(cob["id"])] == s
    # rascunho não vira vencido
    cobranca_service.sincronizar(cen.org_a, "2026-11-25")
    assert _cobrancas(cen.org_a)[0]["status"] == "rascunho"


def test_mensal_agrupa_no_mes(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="mensal", vence_dias=10)
    _sessao(cen, "2026-11-03 09:00:00")
    _sessao(cen, "2026-11-25 09:00:00")
    cobranca_service.sincronizar(cen.org_a, "2026-11-30")
    [cob] = _cobrancas(cen.org_a)
    assert (cob["periodo_inicio"], cob["periodo_fim"], cob["vencimento"]) == ("2026-11-01", "2026-11-30", "2026-12-10")
    assert len(_itens(cob["id"])) == 2


def test_sessao_atrasada_vai_para_proximo_periodo(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="quinzenal")
    _sessao(cen, "2026-11-03 09:00:00")
    cobranca_service.sincronizar(cen.org_a, "2026-11-16")
    [p1] = _cobrancas(cen.org_a)
    db.execute("UPDATE cobrancas SET status = 'pendente', liberada_em = '2026-11-16 10:00:00' WHERE id = ?", (p1["id"],))
    atrasada = _sessao(cen, "2026-11-14 09:00:00", status="agendada")
    _status(atrasada, "realizada")
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-20") == {"criadas": 1, "itens": 1, "revisar": 0}
    p2 = _cobrancas(cen.org_a)[1]
    assert (p2["periodo_inicio"], p2["periodo_fim"], p2["status"]) == ("2026-11-16", "2026-11-30", "rascunho")
    assert [i["consulta_id"] for i in _itens(p2["id"])] == [atrasada]
    assert len(_itens(p1["id"])) == 1


def test_rascunho_cancelado_sem_liberar_nao_empurra_periodo(db_ctx):
    """Rascunho que esvaziou (cancelado sem nunca ter sido liberado) não fecha o período."""
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="quinzenal")
    c1 = _sessao(cen, "2026-11-03 09:00:00")
    cobranca_service.sincronizar(cen.org_a, "2026-11-05")
    _status(c1, "falta_justificada")
    cobranca_service.sincronizar(cen.org_a, "2026-11-06")
    assert _cobrancas(cen.org_a)[0]["status"] == "cancelado"
    c2 = _sessao(cen, "2026-11-07 09:00:00")
    cobranca_service.sincronizar(cen.org_a, "2026-11-08")
    nova = _cobrancas(cen.org_a, status="rascunho")
    assert len(nova) == 1 and nova[0]["periodo_inicio"] == "2026-11-01"
    assert [i["consulta_id"] for i in _itens(nova[0]["id"])] == [c2]


# ------------------------------------------------------------------ mensalidade

def test_mensalidade_proporcional_e_sem_itens(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "mensalidade", inicio="2026-11-16", valor_centavos=30000, dia_vencimento=25)
    _sessao(cen, "2026-11-17 09:00:00")
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-20") == {"criadas": 1, "itens": 0, "revisar": 0}
    [cob] = _cobrancas(cen.org_a)
    assert (cob["tipo"], cob["status"], cob["valor_centavos"], cob["vencimento"]) == \
        ("mensalidade", "pendente", 15000, "2026-11-25")
    assert (cob["periodo_inicio"], cob["periodo_fim"]) == ("2026-11-01", "2026-11-30")
    assert _itens(cob["id"]) == []
    assert cobranca_service.pendencias(cen.org_a, "2026-11-20")["sem_acordo"] == []


def test_mensalidade_cria_meses_ate_hoje_sem_repetir(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "mensalidade", inicio="2026-09-01", valor_centavos=20000, dia_vencimento=10)
    _acordo(cen, "mensalidade", especialidade="Terapia Ocupacional", inicio="2026-09-01", fim="2026-10-15",
            valor_centavos=20000, dia_vencimento=10)
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-05")["criadas"] == 5
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-05")["criadas"] == 0
    fono = [(c["periodo_inicio"], c["valor_centavos"], c["vencimento"], c["status"])
            for c in _cobrancas(cen.org_a) if "Fono" in c["descricao"]]
    # meses criados depois do dia de vencimento não nascem vencidos: vencem em hoje + 5
    assert fono == [("2026-09-01", 20000, "2026-11-10", "pendente"), ("2026-10-01", 20000, "2026-11-10", "pendente"),
                    ("2026-11-01", 20000, "2026-11-10", "pendente")]
    to = [(c["periodo_inicio"], c["valor_centavos"]) for c in _cobrancas(cen.org_a) if "Terapia" in c["descricao"]]
    assert to == [("2026-09-01", 20000), ("2026-10-01", 9677)]
    assert cobranca_service.sincronizar(cen.org_a, "2026-12-01")["criadas"] == 1


def test_acordo_encerrado_ainda_cobre_sessoes_da_vigencia(db_ctx):
    """Encerrar a mensalidade não transforma as sessões já cobertas em "sem acordo"."""
    cen = _cenario(db_ctx)
    _acordo(cen, "mensalidade", inicio="2026-10-01", fim="2026-10-31", status="encerrado",
            valor_centavos=20000, dia_vencimento=10)
    dentro = _sessao(cen, "2026-10-20 09:00:00")
    fora = _sessao(cen, "2026-11-03 09:00:00")
    cobranca_service.sincronizar(cen.org_a, "2026-11-05")
    assert _ids(cobranca_service.pendencias(cen.org_a, "2026-11-05")["sem_acordo"]) == [fora]
    assert dentro not in _ids(acordos_service.sessoes_sem_acordo(cen.org_a, None, None, "2026-11-05"))


# ------------------------------------------------------------------ pacote

def test_pacote_consome_em_ordem(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "pacote", sessoes_total=10, valor_centavos=100000, parcelas=1, primeiro_vencimento="2026-11-10")
    s = [_sessao(cen, d) for d in ("2026-11-10 09:00:00", "2026-11-03 09:00:00", "2026-11-05 9:00:00")]
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-12") == {"criadas": 0, "itens": 0, "revisar": 0}
    assert cobranca_service.sessao_do_pacote(s[0]) == {"numero": 3, "total": 10}
    assert cobranca_service.sessao_do_pacote(s[1]) == {"numero": 1, "total": 10}
    assert cobranca_service.sessao_do_pacote(s[2]) == {"numero": 2, "total": 10}
    assert cobranca_service.sessao_do_pacote(999999) is None
    assert _cobrancas(cen.org_a) == []


def test_pacote_esgotado_vira_pendencia(db_ctx):
    cen = _cenario(db_ctx)
    aid = _acordo(cen, "pacote", sessoes_total=2, valor_centavos=30000, parcelas=1, primeiro_vencimento="2026-11-10")
    s1, s2, s3 = (_sessao(cen, f"2026-11-0{d} 09:00:00") for d in (3, 4, 5))
    cobranca_service.sincronizar(cen.org_a, "2026-11-12")
    assert cobranca_service.sessao_do_pacote(s2) == {"numero": 2, "total": 2}
    assert cobranca_service.sessao_do_pacote(s3) is None
    assert db.query("SELECT * FROM cobranca_itens") == []
    pend = cobranca_service.pendencias(cen.org_a, "2026-11-12")
    assert _ids(pend["sem_acordo"]) == [s3]
    assert _ids(acordos_service.sessoes_sem_acordo(cen.org_a, cen.paciente_a1, None, "2026-11-12")) == [s3]
    [pac] = pend["pacotes_acabando"]
    assert (pac["acordo_id"], pac["sessoes_total"], pac["sessoes_usadas"], pac["restantes"]) == (aid, 2, 2, 0)
    # sincronizar de novo não consome nem duplica
    cobranca_service.sincronizar(cen.org_a, "2026-11-12")
    assert db.query_one("SELECT COUNT(*) AS n FROM acordo_pacote_consumo")["n"] == 2


def test_volta_atras_devolve_sessao_ao_pacote(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "pacote", sessoes_total=2, valor_centavos=30000, parcelas=1, primeiro_vencimento="2026-11-10")
    s1, s2, s3 = (_sessao(cen, f"2026-11-0{d} 09:00:00") for d in (3, 4, 5))
    cobranca_service.sincronizar(cen.org_a, "2026-11-12")
    _status(s1, "falta_justificada")
    cobranca_service.sincronizar(cen.org_a, "2026-11-12")
    assert cobranca_service.sessao_do_pacote(s1) is None
    assert cobranca_service.sessao_do_pacote(s2) == {"numero": 1, "total": 2}
    assert cobranca_service.sessao_do_pacote(s3) == {"numero": 2, "total": 2}
    assert cobranca_service.pendencias(cen.org_a, "2026-11-12")["sem_acordo"] == []


# ------------------------------------------------------------------ escolha do acordo e pendências

def test_acordo_especifico_vence_todas(db_ctx):
    cen = _cenario(db_ctx)
    todas = _acordo(cen, "avulsa", especialidade="*", ciclo="consulta")
    fono = _acordo(cen, "avulsa", especialidade=" fonoaudiologia ", ciclo="quinzenal")
    c_fono = _sessao(cen, "2026-11-03 09:00:00")
    c_to = _sessao(cen, "2026-11-04 09:00:00", esp="Terapia Ocupacional", prof=cen.prof_a2)
    cobranca_service.sincronizar(cen.org_a, "2026-11-05")
    dono = {i["consulta_id"]: db.query_one("SELECT acordo_id, tipo FROM cobrancas WHERE id = ?", (i["cobranca_id"],))
            for i in db.query("SELECT * FROM cobranca_itens")}
    assert (dono[c_fono]["acordo_id"], dono[c_fono]["tipo"]) == (fono, "periodo")
    assert (dono[c_to]["acordo_id"], dono[c_to]["tipo"]) == (todas, "avulsa")


def test_sem_acordo_vira_pendencia(db_ctx):
    cen = _cenario(db_ctx)
    c = _sessao(cen, "2026-11-03 09:00:00")
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-05")["criadas"] == 0
    [p] = cobranca_service.pendencias(cen.org_a, "2026-11-05")["sem_acordo"]
    assert p["consulta_id"] == c
    assert (p["paciente_id"], p["paciente_nome"], p["profissional_nome"], p["especialidade"], p["procedimento_nome"]) == \
        (cen.paciente_a1, "Paciente A1", "Prof A1", "Fonoaudiologia", "Sessão")
    assert p["data_hora"] == "2026-11-03 09:00:00"
    assert _cobrancas(cen.org_a) == []


def test_sem_valor_vira_pendencia(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="consulta")
    sem_proc = _sessao(cen, "2026-11-03 09:00:00", proc=None, valor=None)
    zero = _sessao(cen, "2026-11-04 09:00:00", valor=0)
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-05")["criadas"] == 0
    pend = cobranca_service.pendencias(cen.org_a, "2026-11-05")
    assert _ids(pend["sem_valor"]) == [sem_proc, zero]
    assert pend["sem_valor"][0]["procedimento_nome"] is None
    assert pend["sem_acordo"] == []
    db.execute("INSERT INTO consulta_decisao_cobranca (consulta_id, decisao, valor_centavos) VALUES (?, 'valor', 12000)",
               (sem_proc,))
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-05")["criadas"] == 1
    [item] = db.query("SELECT * FROM cobranca_itens")
    assert (item["consulta_id"], item["valor_centavos"]) == (sem_proc, 12000)
    assert _ids(cobranca_service.pendencias(cen.org_a, "2026-11-05")["sem_valor"]) == [zero]


def test_decisao_nao_cobrar_some_da_pendencia(db_ctx):
    cen = _cenario(db_ctx)
    sem_acordo = _sessao(cen, "2026-11-03 09:00:00", esp="Psicologia")
    _acordo(cen, "avulsa", ciclo="consulta")
    sem_valor = _sessao(cen, "2026-11-04 09:00:00", valor=None)
    pend = cobranca_service.pendencias(cen.org_a, "2026-11-05")
    assert (_ids(pend["sem_acordo"]), _ids(pend["sem_valor"])) == ([sem_acordo], [sem_valor])
    for cid in (sem_acordo, sem_valor):
        db.execute("INSERT INTO consulta_decisao_cobranca (consulta_id, decisao, motivo) VALUES (?, 'nao_cobrar', 'x')",
                   (cid,))
    cobranca_service.sincronizar(cen.org_a, "2026-11-05")
    pend = cobranca_service.pendencias(cen.org_a, "2026-11-05")
    assert (pend["sem_acordo"], pend["sem_valor"]) == ([], [])
    assert _cobrancas(cen.org_a) == []


def test_mensalidade_terminando_no_mes(db_ctx):
    cen = _cenario(db_ctx)
    aid = _acordo(cen, "mensalidade", inicio="2026-09-01", fim="2026-11-30", valor_centavos=20000, dia_vencimento=10)
    _acordo(cen, "mensalidade", especialidade="Psicologia", inicio="2026-09-01", fim="2026-12-31",
            valor_centavos=20000, dia_vencimento=10)
    _acordo(cen, "mensalidade", especialidade="Terapia Ocupacional", inicio="2026-09-01",
            valor_centavos=20000, dia_vencimento=10)
    [m] = cobranca_service.pendencias(cen.org_a, "2026-11-05")["mensalidades_terminando"]
    assert (m["acordo_id"], m["fim"], m["paciente_nome"]) == (aid, "2026-11-30", "Paciente A1")


# ------------------------------------------------------------------ volta atrás

def test_status_volta_atras_remove_item_de_cobranca_aberta(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="quinzenal")
    _acordo(cen, "avulsa", ciclo="consulta", especialidade="Terapia Ocupacional")
    a, b = _sessao(cen, "2026-11-03 09:00:00"), _sessao(cen, "2026-11-04 09:00:00", valor=20000)
    to = _sessao(cen, "2026-11-04 10:00:00", esp="Terapia Ocupacional", prof=cen.prof_a2)
    cobranca_service.sincronizar(cen.org_a, "2026-11-05")
    periodo = _cobrancas(cen.org_a, tipo="periodo")[0]
    avulsa = _cobrancas(cen.org_a, tipo="avulsa")[0]
    assert periodo["valor_centavos"] == 35000
    _status(b, "falta_justificada")
    _status(to, "desmarcada_profissional")
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-05")["revisar"] == 0
    periodo = db.query_one("SELECT * FROM cobrancas WHERE id = ?", (periodo["id"],))
    assert (periodo["status"], periodo["valor_centavos"]) == ("rascunho", 15000)
    assert [i["consulta_id"] for i in _itens(periodo["id"])] == [a]
    avulsa = db.query_one("SELECT * FROM cobrancas WHERE id = ?", (avulsa["id"],))
    assert avulsa["status"] == "cancelado" and _itens(avulsa["id"]) == []
    _status(a, "cancelada")
    cobranca_service.sincronizar(cen.org_a, "2026-11-05")
    assert db.query_one("SELECT status FROM cobrancas WHERE id = ?", (periodo["id"],))["status"] == "cancelado"
    # voltar a valer cria cobrança nova (a cancelada não reabre)
    _status(to, "realizada")
    cobranca_service.sincronizar(cen.org_a, "2026-11-05")
    assert len(_cobrancas(cen.org_a, tipo="avulsa", status="pendente")) == 1


def test_status_volta_atras_em_cobranca_paga_marca_revisar(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="consulta")
    c = _sessao(cen, "2026-11-10 09:00:00")
    parcial = _sessao(cen, "2026-11-11 09:00:00")
    cobranca_service.sincronizar(cen.org_a, "2026-11-12")
    cob_pago, cob_parcial = _cobrancas(cen.org_a)
    db.execute("INSERT INTO pagamentos (cobranca_id, valor_centavos, forma) VALUES (?, 15000, 'dinheiro')", (cob_pago["id"],))
    db.execute("UPDATE cobrancas SET status = 'pago' WHERE id = ?", (cob_pago["id"],))
    db.execute("INSERT INTO pagamentos (cobranca_id, valor_centavos, forma) VALUES (?, 5000, 'pix')", (cob_parcial["id"],))
    db.execute("UPDATE cobrancas SET status = 'parcial' WHERE id = ?", (cob_parcial["id"],))
    _status(c, "falta_justificada")
    _status(parcial, "cancelada")
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-12") == {"criadas": 0, "itens": 0, "revisar": 2}
    pago = db.query_one("SELECT * FROM cobrancas WHERE id = ?", (cob_pago["id"],))
    assert (pago["status"], pago["valor_centavos"], pago["revisar"]) == ("pago", 15000, 1)
    assert pago["revisar_motivo"] == "Sessão de 10/11 virou Falta justificada"
    assert len(_itens(pago["id"])) == 1
    p2 = db.query_one("SELECT * FROM cobrancas WHERE id = ?", (cob_parcial["id"],))
    assert (p2["status"], p2["revisar"]) == ("parcial", 1)
    # não conta de novo, nem depois de o gestor resolver
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-12")["revisar"] == 0
    db.execute("UPDATE cobrancas SET revisar = 0 WHERE id = ?", (cob_pago["id"],))
    cobranca_service.sincronizar(cen.org_a, "2026-11-12")
    assert db.query_one("SELECT revisar FROM cobrancas WHERE id = ?", (cob_pago["id"],))["revisar"] == 0
    assert [r["id"] for r in cobranca_service.pendencias(cen.org_a, "2026-11-12")["revisar"]] == [cob_parcial["id"]]


def test_pagamento_estornado_nao_impede_cancelar(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="consulta")
    c = _sessao(cen, "2026-11-10 09:00:00")
    cobranca_service.sincronizar(cen.org_a, "2026-11-12")
    [cob] = _cobrancas(cen.org_a)
    db.execute("INSERT INTO pagamentos (cobranca_id, valor_centavos, forma, estornado_em) VALUES (?, 15000, 'pix', '2026-11-11')",
               (cob["id"],))
    _status(c, "falta_justificada")
    cobranca_service.sincronizar(cen.org_a, "2026-11-12")
    assert db.query_one("SELECT status FROM cobrancas WHERE id = ?", (cob["id"],))["status"] == "cancelado"


# ------------------------------------------------------------------ vencidas, idempotência, isolamento

def test_vencida_muda_status(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="consulta")
    _sessao(cen, "2026-11-10 09:00:00")
    cobranca_service.sincronizar(cen.org_a, "2026-11-10")
    _sessao(cen, "2026-11-11 09:00:00")
    cobranca_service.sincronizar(cen.org_a, "2026-11-11")
    c1, c2 = _cobrancas(cen.org_a)
    assert (c1["vencimento"], c2["vencimento"]) == ("2026-11-15", "2026-11-16")
    db.execute("UPDATE cobrancas SET status = 'parcial' WHERE id = ?", (c2["id"],))
    cobranca_service.sincronizar(cen.org_a, "2026-11-15")
    assert [c["status"] for c in _cobrancas(cen.org_a)] == ["pendente", "parcial"]   # vence hoje: ainda não
    cobranca_service.sincronizar(cen.org_a, "2026-11-17")
    assert [c["status"] for c in _cobrancas(cen.org_a)] == ["vencido", "vencido"]
    venc = cobranca_service.pendencias(cen.org_a, "2026-11-17")["vencidas"]
    assert [v["id"] for v in venc] == [c1["id"], c2["id"]]
    assert venc[0]["paciente_nome"] == "Paciente A1" and venc[0]["saldo_centavos"] == 15000


def test_sincronizar_duas_vezes_nao_duplica(db_ctx):
    cen = _cenario(db_ctx)
    db.execute("UPDATE organizacoes SET fin_cobrar_falta = 1 WHERE id = ?", (cen.org_a,))
    _acordo(cen, "avulsa", ciclo="consulta")
    _acordo(cen, "avulsa", ciclo="quinzenal", especialidade="Terapia Ocupacional")
    _acordo(cen, "mensalidade", especialidade="Psicologia", inicio="2026-10-01", valor_centavos=10000, dia_vencimento=5)
    _acordo(cen, "pacote", paciente=cen.paciente_a2, especialidade="*", sessoes_total=5, valor_centavos=5000,
            parcelas=1, primeiro_vencimento="2026-11-01")
    _sessao(cen, "2026-11-03 09:00:00")
    _sessao(cen, "2026-11-04 09:00:00", status="faltou")
    _sessao(cen, "2026-11-04 10:00:00", esp="Terapia Ocupacional", prof=cen.prof_a2)
    _sessao(cen, "2026-11-05 10:00:00", esp="Terapia Ocupacional", prof=cen.prof_a2)
    _sessao(cen, "2026-11-05 11:00:00", paciente=cen.paciente_a2)
    primeira = cobranca_service.sincronizar(cen.org_a, "2026-11-06")
    assert primeira == {"criadas": 5, "itens": 4, "revisar": 0}
    antes = (len(_cobrancas()), len(db.query("SELECT * FROM cobranca_itens")),
             len(db.query("SELECT * FROM acordo_pacote_consumo")))
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-06") == {"criadas": 0, "itens": 0, "revisar": 0}
    assert (len(_cobrancas()), len(db.query("SELECT * FROM cobranca_itens")),
            len(db.query("SELECT * FROM acordo_pacote_consumo"))) == antes == (5, 4, 1)


def test_consulta_futura_nao_cobra(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="consulta")
    _acordo(cen, "pacote", especialidade="Terapia Ocupacional", sessoes_total=5, valor_centavos=5000, parcelas=1,
            primeiro_vencimento="2026-11-01")
    _sessao(cen, "2026-11-21 09:00:00")
    _sessao(cen, "2026-11-21 10:00:00", esp="Terapia Ocupacional", prof=cen.prof_a2)
    _sessao(cen, "2026-11-21 11:00:00", esp="Psicologia")
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-20") == {"criadas": 0, "itens": 0, "revisar": 0}
    assert db.query("SELECT * FROM acordo_pacote_consumo") == []
    assert cobranca_service.pendencias(cen.org_a, "2026-11-20")["sem_acordo"] == []


def test_isolamento_entre_clinicas(db_ctx):
    cen = _cenario(db_ctx)
    pid_b = novo_paciente(cen.org_b, "Paciente B1")
    _acordo(cen, "avulsa", org=cen.org_b, paciente=pid_b, especialidade="*", ciclo="consulta")
    _sessao(cen, "2026-11-03 09:00:00", prof=cen.prof_b1, paciente=pid_b, proc="b")
    _sessao(cen, "2026-11-03 10:00:00", prof=cen.prof_b1, paciente=pid_b, proc="b", esp="X", valor=None)
    _sessao(cen, "2026-11-03 11:00:00")   # da clínica A, sem acordo
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-05")["criadas"] == 0
    assert _cobrancas() == []
    pend_a = cobranca_service.pendencias(cen.org_a, "2026-11-05")
    assert all(s["paciente_id"] == cen.paciente_a1 for s in pend_a["sem_acordo"] + pend_a["sem_valor"])
    assert cobranca_service.sincronizar(cen.org_b, "2026-11-05")["criadas"] == 1   # a sem valor fica pendente
    assert all(c["organizacao_id"] == cen.org_b for c in _cobrancas())
    assert cobranca_service.pendencias(cen.org_a, "2026-11-05")["vencidas"] == []


def test_script_cron_roda(db_ctx, capsys):
    import gerar_cobrancas_clinicas
    cen = _cenario(db_ctx)
    db.execute("UPDATE organizacoes SET plano = 'starter' WHERE id = ?", (cen.org_b,))
    _acordo(cen, "avulsa", ciclo="consulta")
    _sessao(cen, "2026-11-03 09:00:00")
    pid_b = novo_paciente(cen.org_b, "PB")
    _acordo(cen, "avulsa", org=cen.org_b, paciente=pid_b, ciclo="consulta", especialidade="*")
    _sessao(cen, "2026-11-03 09:00:00", prof=cen.prof_b1, paciente=pid_b, proc="b")
    gerar_cobrancas_clinicas.main(hoje="2026-11-05")
    saida = capsys.readouterr().out
    assert "Clínica A" in saida and "Clínica B" not in saida
    assert saida.strip().endswith("(SQLite)")
    assert [c["organizacao_id"] for c in _cobrancas()] == [cen.org_a]


# ------------------------------------------------------------------ agenda: histórico cobrado não muda sozinho

def _faltou_cobrada(client, cen):
    db.execute("UPDATE organizacoes SET fin_cobrar_falta = 1 WHERE id = ?", (cen.org_a,))
    _acordo(cen, "avulsa", ciclo="consulta")
    c = _sessao(cen, "2026-11-03 09:00:00", status="faltou")
    cobranca_service.sincronizar(cen.org_a, "2026-11-05")
    assert db.query_one("SELECT 1 FROM cobranca_itens WHERE consulta_id = ?", (c,))
    return c


def test_reatribuir_sessao_cobrada_nao_muda_especialidade(client, db_ctx):
    cen = _cenario(db_ctx)
    c = _faltou_cobrada(client, cen)
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{c}", json={"profissional_id": cen.prof_a2["id"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    row = db.query_one("SELECT profissional_id, especialidade FROM consultas WHERE id = ?", (c,))
    assert (row["profissional_id"], row["especialidade"]) == (cen.prof_a2["id"], "Fonoaudiologia")


def test_reatribuir_sessao_do_pacote_nao_muda_especialidade(client, db_ctx):
    cen = _cenario(db_ctx)
    db.execute("UPDATE organizacoes SET fin_cobrar_falta = 1 WHERE id = ?", (cen.org_a,))
    _acordo(cen, "pacote", sessoes_total=5, valor_centavos=5000, parcelas=1, primeiro_vencimento="2026-11-01")
    c = _sessao(cen, "2026-11-03 09:00:00", status="faltou")
    cobranca_service.sincronizar(cen.org_a, "2026-11-05")
    assert cobranca_service.sessao_do_pacote(c) == {"numero": 1, "total": 5}
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{c}", json={"profissional_id": cen.prof_a2["id"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert db.query_one("SELECT especialidade FROM consultas WHERE id = ?", (c,))["especialidade"] == "Fonoaudiologia"


def test_excluir_sessao_cobrada_409(client, db_ctx):
    cen = _cenario(db_ctx)
    c = _faltou_cobrada(client, cen)
    r = autenticado(client, cen.gestor_a).delete(f"/api/agenda/{c}")
    assert r.status_code == 409
    assert db.query_one("SELECT 1 FROM consultas WHERE id = ?", (c,))


# ------------------------------------------------------------------ rodada de correções (revisão da task 4)

def test_avulsa_criada_com_atraso_nao_nasce_vencida(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="consulta")
    _sessao(cen, "2026-10-01 09:00:00")
    cobranca_service.sincronizar(cen.org_a, "2026-11-12")
    [cob] = _cobrancas(cen.org_a)
    assert (cob["vencimento"], cob["status"]) == ("2026-11-17", "pendente")


def test_mensalidade_primeiro_mes_depois_do_vencimento_nao_nasce_vencida(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "mensalidade", inicio="2026-11-01", valor_centavos=20000, dia_vencimento=5)
    cobranca_service.sincronizar(cen.org_a, "2026-11-20")
    [cob] = _cobrancas(cen.org_a)
    assert (cob["vencimento"], cob["status"], cob["valor_centavos"]) == ("2026-11-25", "pendente", 20000)


def test_mensalidade_mes_repetido_por_sincronizacao_simultanea(db_ctx, monkeypatch):
    """Índice único (acordo, mês): a outra sincronização gravou o mês primeiro."""
    cen = _cenario(db_ctx)
    aid = _acordo(cen, "mensalidade", inicio="2026-11-01", valor_centavos=20000, dia_vencimento=10)
    _acordo(cen, "avulsa", ciclo="consulta", especialidade="Terapia Ocupacional")
    _sessao(cen, "2026-11-03 09:00:00", esp="Terapia Ocupacional", prof=cen.prof_a2)
    db.execute("""INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status, organizacao_id,
                                        acordo_id, tipo, periodo_inicio, periodo_fim)
                  VALUES (?, 'Mensalidade 11/2026', 20000, '2026-11-10', 'pendente', ?, ?, 'mensalidade',
                          '2026-11-01', '2026-11-30')""", (cen.paciente_a1, cen.org_a, aid))
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-05")["criadas"] == 1   # a avulsa; o mês já existe
    assert len(_cobrancas(cen.org_a, tipo="mensalidade")) == 1
    # simula a corrida: a leitura dos meses existentes não vê o mês gravado pela outra
    original = cobranca_service.query

    def query_sem_meses(sql, params=()):
        if "SELECT acordo_id, periodo_inicio FROM cobrancas" in sql:
            return []
        return original(sql, params)

    monkeypatch.setattr(cobranca_service, "query", query_sem_meses)
    _sessao(cen, "2026-11-04 09:00:00", esp="Terapia Ocupacional", prof=cen.prof_a2)
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-05") == {"criadas": 0, "itens": 0, "revisar": 0}
    assert len(_cobrancas(cen.org_a, tipo="mensalidade")) == 1
    assert len(_cobrancas(cen.org_a, tipo="avulsa")) == 1   # a rodada foi desfeita inteira
    monkeypatch.setattr(cobranca_service, "query", original)
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-05")["criadas"] == 1


def test_periodo_liberado_nao_reabre_marca_revisar(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="quinzenal")
    a, b = _sessao(cen, "2026-11-03 09:00:00"), _sessao(cen, "2026-11-04 09:00:00")
    cobranca_service.sincronizar(cen.org_a, "2026-11-16")
    [cob] = _cobrancas(cen.org_a)
    db.execute("UPDATE cobrancas SET status = 'pendente', liberada_em = '2026-11-16 10:00:00' WHERE id = ?", (cob["id"],))
    _status(b, "falta_justificada")
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-17")["revisar"] == 1
    cob = db.query_one("SELECT * FROM cobrancas WHERE id = ?", (cob["id"],))
    assert (cob["status"], cob["valor_centavos"], cob["revisar"]) == ("pendente", 30000, 1)
    assert cob["revisar_motivo"] == "Sessão de 04/11 virou Falta justificada"
    assert [i["consulta_id"] for i in _itens(cob["id"])] == [a, b]


def test_revisar_duas_sessoes_no_mesmo_dia(db_ctx):
    cen = _cenario(db_ctx)
    _acordo(cen, "avulsa", ciclo="quinzenal")
    c1, c2 = _sessao(cen, "2026-11-03 09:00:00"), _sessao(cen, "2026-11-03 10:00:00")
    cobranca_service.sincronizar(cen.org_a, "2026-11-16")
    [cob] = _cobrancas(cen.org_a)
    db.execute("UPDATE cobrancas SET status = 'pago', liberada_em = '2026-11-16' WHERE id = ?", (cob["id"],))
    db.execute("INSERT INTO pagamentos (cobranca_id, valor_centavos, forma) VALUES (?, 30000, 'pix')", (cob["id"],))
    _status(c1, "falta_justificada")
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-17")["revisar"] == 1
    db.execute("UPDATE cobrancas SET revisar = 0 WHERE id = ?", (cob["id"],))   # gestor resolveu (motivo fica)
    _status(c2, "falta_justificada")
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-17")["revisar"] == 1
    cob = db.query_one("SELECT * FROM cobrancas WHERE id = ?", (cob["id"],))
    assert cob["revisar"] == 1
    assert cob["revisar_motivo"] == ("Sessão de 03/11 virou Falta justificada; "
                                     "Sessão de 03/11 virou Falta justificada")
    assert cobranca_service.sincronizar(cen.org_a, "2026-11-17")["revisar"] == 0


def test_excluir_consulta_com_decisao_de_cobranca(client, db_ctx):
    cen = _cenario(db_ctx)
    c = _sessao(cen, "2026-11-03 09:00:00", status="faltou")
    db.execute("INSERT INTO consulta_decisao_cobranca (consulta_id, decisao, motivo) VALUES (?, 'nao_cobrar', 'x')", (c,))
    r = autenticado(client, cen.gestor_a).delete(f"/api/agenda/{c}")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert db.query_one("SELECT 1 FROM consultas WHERE id = ?", (c,)) is None
    assert db.query_one("SELECT 1 FROM consulta_decisao_cobranca WHERE consulta_id = ?", (c,)) is None
