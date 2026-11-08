"""Financeiro etapa 1, task 6: listagens, configuração, extrato da família e pacote no Atender."""
from datetime import timedelta

import db
import planos_padrao
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
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    cen.paciente_b1 = db.execute("INSERT INTO pacientes (organizacao_id, nome, data_nascimento) VALUES (?, 'Paciente B1', '2018-01-01')", (cen.org_b,))
    return cen


def _cobranca(cen, valor=23000, status="pendente", venc=None, desconto=0, paciente=None, org=None, **extra):
    venc = venc or (_hoje() + timedelta(days=10)).isoformat()
    campos = {"paciente_id": paciente or cen.paciente_a1, "descricao": "Mensalidade", "valor_centavos": valor,
              "vencimento": venc, "status": status, "organizacao_id": org or cen.org_a, "tipo": "manual",
              "desconto_centavos": desconto}
    campos.update(extra)
    cols = ", ".join(campos)
    return db.execute(f"INSERT INTO cobrancas ({cols}) VALUES ({', '.join('?' for _ in campos)})",
                      tuple(campos.values()))


def _pagamento(cid, valor, pago_em=None, estornado=False):
    pago_em = pago_em or _hoje().isoformat() + " 10:00:00"
    return db.execute(
        """INSERT INTO pagamentos (cobranca_id, valor_centavos, forma, pago_em, recebido_por_usuario_id,
                                   recebido_por_nome, estornado_em, estorno_motivo, estornado_por)
           VALUES (?, ?, 'dinheiro', ?, 1, 'Fulano', ?, ?, ?)""",
        (cid, valor, pago_em, "2026-01-01 00:00:00" if estornado else None, "erro" if estornado else None,
         1 if estornado else None))


def _get(client, usuario, url):
    return autenticado(client, usuario).get(url)


def test_lista_chama_sincronizar(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    chamadas = []
    monkeypatch.setattr(cobranca_service, "sincronizar", lambda org, hoje=None: chamadas.append(org) or {})
    r = _get(client, cen.gestor_a, "/api/financeiro/cobrancas")
    assert r.status_code == 200
    assert chamadas == [cen.org_a]
    _get(client, cen.gestor_a, f"/api/financeiro/paciente/{cen.paciente_a1}")
    _get(client, cen.gestor_a, "/api/financeiro/pendencias")
    assert chamadas == [cen.org_a] * 3


def test_forma_da_cobranca(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, valor=20000, desconto=5000)
    _pagamento(cid, 6000)
    c = _get(client, cen.gestor_a, "/api/financeiro/cobrancas").get_json()["cobrancas"][0]
    assert c["id"] == cid and c["paciente_nome"]
    assert (c["a_pagar_centavos"], c["pago_centavos"], c["saldo_centavos"]) == (15000, 6000, 9000)
    assert c["aberta"] is False and c["itens"] == [] and len(c["pagamentos"]) == 1


def test_filtros(client, db_ctx):
    cen = _cenario(db_ctx)
    h = _hoje()
    a = _cobranca(cen, venc=(h + timedelta(days=1)).isoformat())
    b = _cobranca(cen, venc=(h + timedelta(days=20)).isoformat(), status="pago", paciente=cen.paciente_a2)
    c = _cobranca(cen, venc=(h + timedelta(days=30)).isoformat(), org=cen.org_a)
    base = "/api/financeiro/cobrancas"

    def ids(q):
        return {x["id"] for x in _get(client, cen.gestor_a, base + q).get_json()["cobrancas"]}
    assert ids("") == {a, b, c}
    assert ids("?status=pago") == {b}
    assert ids(f"?paciente_id={cen.paciente_a2}") == {b}
    assert ids(f"?de={(h + timedelta(days=15)).isoformat()}") == {a, b, c}   # `a` é dívida aberta anterior
    assert ids(f"?ate={(h + timedelta(days=25)).isoformat()}") == {a, b}
    assert _get(client, cen.gestor_a, base + "?status=xx").status_code == 400
    assert _get(client, cen.gestor_a, base + "?de=lixo").status_code == 400


def test_filtro_especialidade(client, db_ctx):
    cen = _cenario(db_ctx)
    ac = db.execute(
        """INSERT INTO acordos_pagamento (organizacao_id, paciente_id, especialidade, tipo, valor_centavos, dia_vencimento, inicio)
           VALUES (?, ?, 'Fonoaudiologia', 'mensalidade', 1000, 5, '2026-01-01')""", (cen.org_a, cen.paciente_a1))
    a = _cobranca(cen, acordo_id=ac)
    b = _cobranca(cen)
    r = _get(client, cen.gestor_a, "/api/financeiro/cobrancas?especialidade=fonoaudiologia").get_json()
    ids = {x["id"] for x in r["cobrancas"]}
    assert a in ids and b not in ids
    assert all(x["especialidade"] == "Fonoaudiologia" for x in r["cobrancas"])


def test_totais_ignoram_estorno(client, db_ctx):
    cen = _cenario(db_ctx)
    h = _hoje()
    cid = _cobranca(cen, valor=10000, status="parcial")
    _pagamento(cid, 4000)
    _pagamento(cid, 3000, estornado=True)
    v = _cobranca(cen, valor=5000, status="vencido", venc=(h - timedelta(days=2)).isoformat())
    _cobranca(cen, valor=9999, status="cancelado")
    t = _get(client, cen.gestor_a, "/api/financeiro/cobrancas").get_json()["totais"]
    assert t["recebido_centavos"] == 4000
    assert t["em_aberto_centavos"] == 6000 + 5000
    assert t["vencido_centavos"] == 5000
    antigo = (h - timedelta(days=40)).isoformat() + " 10:00:00"
    _pagamento(v, 500, pago_em=antigo)
    t = _get(client, cen.gestor_a, f"/api/financeiro/cobrancas?de={h.isoformat()}").get_json()["totais"]
    assert t["recebido_centavos"] == 4000


def test_para_conferir_conta_so_periodos_encerrados(client, db_ctx):
    cen = _cenario(db_ctx)
    h = _hoje()
    _cobranca(cen, status="rascunho", periodo_inicio=(h - timedelta(days=10)).isoformat(),
              periodo_fim=(h - timedelta(days=1)).isoformat())
    aberta = _cobranca(cen, status="rascunho", periodo_inicio=h.isoformat(), periodo_fim=h.isoformat())
    r = _get(client, cen.gestor_a, "/api/financeiro/cobrancas").get_json()
    assert r["para_conferir"] == 1
    por_id = {c["id"]: c for c in r["cobrancas"]}
    assert por_id[aberta]["aberta"] is True
    assert sum(1 for c in r["cobrancas"] if c["aberta"]) == 1


def test_lista_outra_clinica_nao_aparece(client, db_ctx):
    cen = _cenario(db_ctx)
    _cobranca(cen)
    r = _get(client, cen.gestor_b, "/api/financeiro/cobrancas").get_json()
    assert r["cobrancas"] == []


def test_profissional_e_responsavel_nao_listam(client, db_ctx):
    cen = _cenario(db_ctx)
    assert _get(client, cen.prof_a1, "/api/financeiro/cobrancas").status_code == 403
    assert _get(client, cen.resp_a1, "/api/financeiro/cobrancas").status_code == 403


def test_secretaria_lista(client, db_ctx):
    cen = _cenario(db_ctx)
    assert _get(client, cen.sec_a, "/api/financeiro/cobrancas").status_code == 200


def test_pendencias_so_gestor(client, db_ctx):
    cen = _cenario(db_ctx)
    assert _get(client, cen.sec_a, "/api/financeiro/pendencias").status_code == 403
    r = _get(client, cen.gestor_a, "/api/financeiro/pendencias")
    assert r.status_code == 200 and "sem_acordo" in r.get_json()


def test_config_so_gestor(client, db_ctx):
    cen = _cenario(db_ctx)
    assert _get(client, cen.sec_a, "/api/financeiro/config").status_code == 403
    assert autenticado(client, cen.sec_a).put("/api/financeiro/config", json={"cobrar_falta": True}).status_code == 403
    g = autenticado(client, cen.gestor_a)
    assert g.get("/api/financeiro/config").get_json() == {"cobrar_falta": False, "repasse_falta": False}
    r = g.put("/api/financeiro/config", json={"cobrar_falta": True, "repasse_falta": True})
    assert r.status_code == 200 and r.get_json() == {"cobrar_falta": True, "repasse_falta": True}
    assert g.get("/api/financeiro/config").get_json()["cobrar_falta"] is True
    # só uma chave: a outra se mantém
    g.put("/api/financeiro/config", json={"repasse_falta": False})
    assert g.get("/api/financeiro/config").get_json() == {"cobrar_falta": True, "repasse_falta": False}
    assert g.put("/api/financeiro/config", json={"cobrar_falta": "sim"}).status_code == 400
    assert g.put("/api/financeiro/config", json=[1]).status_code == 400
    # a outra clínica não mudou
    assert autenticado(client, cen.gestor_b).get("/api/financeiro/config").get_json()["cobrar_falta"] is False


def test_familia_nao_ve_rascunho(client, db_ctx):
    cen = _cenario(db_ctx)
    ok = _cobranca(cen, status="pendente")
    _cobranca(cen, status="rascunho")
    _cobranca(cen, status="cancelado")
    r = _get(client, cen.resp_a1, f"/api/financeiro/paciente/{cen.paciente_a1}")
    assert r.status_code == 200
    assert [c["id"] for c in r.get_json()] == [ok]
    # a equipe vê tudo
    r = _get(client, cen.gestor_a, f"/api/financeiro/paciente/{cen.paciente_a1}")
    assert len(r.get_json()) == 3


def test_familia_nao_ve_quem_recebeu(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, desconto=1000, desconto_motivo="amigo", revisar=1, revisar_motivo="mudou")
    _pagamento(cid, 5000)
    _pagamento(cid, 2000, estornado=True)
    r = _get(client, cen.resp_a1, f"/api/financeiro/paciente/{cen.paciente_a1}").get_json()[0]
    assert "revisar" not in r and "revisar_motivo" not in r
    assert r["desconto_motivo"] == "amigo"
    assert len(r["pagamentos"]) == 1
    pg = r["pagamentos"][0]
    for k in ("recebido_por_usuario_id", "recebido_por_nome", "estornado_por", "estorno_motivo", "mp_payment_id"):
        assert k not in pg
    assert r["pago_centavos"] == 5000
    eq = _get(client, cen.gestor_a, f"/api/financeiro/paciente/{cen.paciente_a1}").get_json()[0]
    assert eq["revisar"] is True and len(eq["pagamentos"]) == 2
    assert eq["pagamentos"][0]["recebido_por_nome"] == "Fulano"


def test_familia_de_outro_paciente_403(client, db_ctx):
    cen = _cenario(db_ctx)
    assert _get(client, cen.resp_a1, f"/api/financeiro/paciente/{cen.paciente_b1}").status_code == 403


def test_resumo_com_status_novos(client, db_ctx):
    cen = _cenario(db_ctx)
    h = _hoje()
    a = _cobranca(cen, valor=10000, status="parcial")
    _pagamento(a, 4000)
    _pagamento(a, 1000, estornado=True)
    _cobranca(cen, valor=3000, status="pendente")
    _cobranca(cen, valor=7000, status="vencido", venc=(h - timedelta(days=3)).isoformat())
    _cobranca(cen, valor=9000, status="rascunho")
    r = _get(client, cen.gestor_a, "/api/financeiro/clinica/resumo").get_json()
    assert r["receita_mes_centavos"] == 4000
    assert r["pendentes_qtd"] == 2
    assert r["pendentes_total_centavos"] == 6000 + 3000
    assert r["vencidos_qtd"] == 1


def test_atendimento_mostra_sessao_do_pacote(client, db_ctx):
    cen = _cenario(db_ctx)
    dia = _hoje().isoformat()
    cid = db.execute(
        """INSERT INTO consultas (paciente_id, profissional_id, data_hora, status, especialidade)
           VALUES (?, ?, ?, 'agendada', 'Fonoaudiologia')""", (cen.paciente_a1, cen.prof_a1["id"], f"{dia} 09:00:00"))
    r = _get(client, cen.prof_a1, f"/api/agenda/{cid}/atendimento").get_json()
    assert r["pacote"] is None
    ac = db.execute(
        """INSERT INTO acordos_pagamento (organizacao_id, paciente_id, especialidade, tipo, valor_centavos, sessoes_total, inicio)
           VALUES (?, ?, 'Fonoaudiologia', 'pacote', 100000, 10, '2026-01-01')""", (cen.org_a, cen.paciente_a1))
    db.execute("INSERT INTO acordo_pacote_consumo (consulta_id, acordo_id, numero) VALUES (?, ?, 3)", (cid, ac))
    r = _get(client, cen.prof_a1, f"/api/agenda/{cid}/atendimento").get_json()
    assert r["pacote"] == {"numero": 3, "total": 10}


def test_profissional_nao_ve_extrato_nem_sincroniza(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    chamadas = []
    monkeypatch.setattr(cobranca_service, "sincronizar", lambda org, hoje=None: chamadas.append(org) or {})
    r = _get(client, cen.prof_a1, f"/api/financeiro/paciente/{cen.paciente_a1}")
    assert r.status_code == 403
    assert chamadas == []


def test_gestor_nao_ve_extrato_de_paciente_de_outra_clinica(client, db_ctx):
    cen = _cenario(db_ctx)
    assert _get(client, cen.gestor_a, f"/api/financeiro/paciente/{cen.paciente_b1}").status_code in (403, 404)


def test_paciente_id_zero_filtra(client, db_ctx):
    cen = _cenario(db_ctx)
    _cobranca(cen)
    r = _get(client, cen.gestor_a, "/api/financeiro/cobrancas?paciente_id=0").get_json()
    assert r["cobrancas"] == []


def test_secretaria_ve_extrato_da_propria_clinica(client, db_ctx):
    cen = _cenario(db_ctx)
    _cobranca(cen, status="rascunho", revisar=1)
    r = _get(client, cen.sec_a, f"/api/financeiro/paciente/{cen.paciente_a1}")
    assert r.status_code == 200
    c = r.get_json()[0]
    assert c["status"] == "rascunho" and c["revisar"] is True


def test_secretaria_nao_ve_extrato_de_outra_clinica(client, db_ctx):
    cen = _cenario(db_ctx)
    assert _get(client, cen.sec_a, f"/api/financeiro/paciente/{cen.paciente_b1}").status_code in (403, 404)


def test_divida_antiga_aparece_com_filtro_do_mes(client, db_ctx):
    cen = _cenario(db_ctx)
    h = _hoje()
    velha = _cobranca(cen, valor=7000, status="vencido", venc=(h - timedelta(days=45)).isoformat())
    paga = _cobranca(cen, valor=7000, status="pago", venc=(h - timedelta(days=45)).isoformat())
    atual = _cobranca(cen, valor=3000, status="pendente", venc=(h + timedelta(days=3)).isoformat())
    de = (h - timedelta(days=10)).isoformat()
    r = _get(client, cen.gestor_a, f"/api/financeiro/cobrancas?de={de}").get_json()
    ids = {x["id"] for x in r["cobrancas"]}
    assert velha in ids and atual in ids and paga not in ids
    assert r["totais"]["vencido_centavos"] == 7000
    assert r["totais"]["em_aberto_centavos"] == 10000
    # status explícito que não é "em aberto" não traz a dívida antiga
    ids = {x["id"] for x in _get(client, cen.gestor_a, f"/api/financeiro/cobrancas?de={de}&status=pago").get_json()["cobrancas"]}
    assert ids == set()
    ids = {x["id"] for x in _get(client, cen.gestor_a, f"/api/financeiro/cobrancas?de={de}&status=vencido").get_json()["cobrancas"]}
    assert ids == {velha}
