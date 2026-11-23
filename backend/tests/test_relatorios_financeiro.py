"""Financeiro 6.5: relatórios da clínica (em aberto e vencidas, pacotes/mensalidades acabando, sem acordo)."""
import db
import relatorios_service
from factories import novo_paciente, vincular_responsavel

from conftest import autenticado
from test_cobranca_baixa import _cenario, _cobranca
from test_extrato_paciente import _acordo, _consulta, _dia, _pagar


# ------------------------------------------------------------------ em aberto e vencidas

def test_em_aberto_com_saldo_e_dias_de_atraso(db_ctx):
    cen = _cenario(db_ctx)
    v = _cobranca(cen, valor=20000, status="vencido", venc=_dia(10), descricao="Vencida")
    p = _cobranca(cen, valor=30000, status="parcial", venc=_dia(-5), descricao="Parcial")
    _pagar(p, 10000)
    _cobranca(cen, valor=9999, status="rascunho", venc=_dia(1))
    _cobranca(cen, valor=9999, status="pago", venc=_dia(1))
    _cobranca(cen, valor=9999, status="cancelado", venc=_dia(1))
    d = relatorios_service.em_aberto(cen.org_a, hoje=_dia(0))
    assert [c["descricao"] for c in d["cobrancas"]] == ["Vencida", "Parcial"]
    venc, parc = d["cobrancas"]
    assert venc["dias_atraso"] == 10 and venc["saldo_centavos"] == 20000 and venc["paciente_nome"] == "Paciente A1"
    assert parc["dias_atraso"] == 0 and parc["saldo_centavos"] == 20000 and parc["pago_centavos"] == 10000
    assert d["totais"] == {"em_aberto_centavos": 40000, "vencido_centavos": 20000, "quantidade": 2}


def test_em_aberto_filtros(db_ctx):
    cen = _cenario(db_ctx)
    _cobranca(cen, valor=10000, status="pendente", venc=_dia(-3))
    _cobranca(cen, valor=20000, status="pendente", venc=_dia(-3), paciente_id=cen.paciente_a2)
    pac = _acordo(cen, "pacote", "Psicopedagogia", valor_centavos=50000, sessoes_total=5, parcelas=1)
    _cobranca(cen, valor=50000, status="pendente", venc=_dia(-3), tipo="pacote", acordo_id=pac)
    assert relatorios_service.em_aberto(cen.org_a, paciente_id=cen.paciente_a2, hoje=_dia(0))["totais"]["em_aberto_centavos"] == 20000
    d = relatorios_service.em_aberto(cen.org_a, especialidade="psicopedagogia", hoje=_dia(0))
    assert [c["a_pagar_centavos"] for c in d["cobrancas"]] == [50000]


# ------------------------------------------------------------------ acabando

def test_pacotes_acabando_e_mensalidades_terminando(db_ctx):
    cen = _cenario(db_ctx)
    quase = _acordo(cen, "pacote", "Fonoaudiologia", valor_centavos=40000, sessoes_total=4)
    for n in (1, 2, 3):
        s = _consulta(cen, 10 + n)
        db.execute("INSERT INTO acordo_pacote_consumo (consulta_id, acordo_id, numero) VALUES (?, ?, ?)", (s, quase, n))
    _acordo(cen, "pacote", "Psicopedagogia", valor_centavos=100000, sessoes_total=10)        # 10 restantes: fora
    _acordo(cen, "mensalidade", "Terapia Ocupacional", valor_centavos=60000, fim=_dia(-10), dia_vencimento=5)
    _acordo(cen, "mensalidade", "Psicologia", valor_centavos=60000, fim=_dia(-200), dia_vencimento=5)  # longe: fora
    _acordo(cen, "mensalidade", "Musicoterapia", valor_centavos=60000, dia_vencimento=5)               # sem fim: fora
    d = relatorios_service.acabando(cen.org_a, restantes=2, de=_dia(0), ate=_dia(-60))
    assert [(p["acordo_id"], p["restantes"], p["sessoes_usadas"]) for p in d["pacotes"]] == [(quase, 1, 3)]
    assert [m["especialidade"] for m in d["mensalidades"]] == ["Terapia Ocupacional"]
    assert relatorios_service.acabando(cen.org_a, restantes=0, de=_dia(0), ate=_dia(-60))["pacotes"] == []


# ------------------------------------------------------------------ sem acordo

def test_sem_acordo_no_periodo_com_filtros(db_ctx):
    cen = _cenario(db_ctx)
    _consulta(cen, 5, valor=15000)
    _consulta(cen, 6, esp="Psicopedagogia", valor=12000)
    _consulta(cen, 90, valor=99999)                       # fora do período
    _acordo(cen, "mensalidade", "Terapia Ocupacional", valor_centavos=60000, dia_vencimento=5)
    _consulta(cen, 4, esp="Terapia Ocupacional")          # coberta por mensalidade: fora
    d = relatorios_service.sem_acordo(cen.org_a, _dia(30), _dia(0), hoje=_dia(0))
    assert sorted(s["valor_centavos"] for s in d["sessoes"]) == [12000, 15000]
    assert d["totais"] == {"quantidade": 2, "valor_centavos": 27000}
    assert len(relatorios_service.sem_acordo(cen.org_a, _dia(30), _dia(0), especialidade="Psicopedagogia",
                                             hoje=_dia(0))["sessoes"]) == 1
    assert relatorios_service.sem_acordo(cen.org_a, _dia(30), _dia(0), profissional_id=cen.prof_a2["id"],
                                         hoje=_dia(0))["sessoes"] == []


# ------------------------------------------------------------------ rotas

ROTAS = ("/api/financeiro/relatorios/em-aberto", "/api/financeiro/relatorios/acabando",
         "/api/financeiro/relatorios/sem-acordo")


def test_relatorios_so_gestor(client, db_ctx):
    cen = _cenario(db_ctx)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    for rota in ROTAS:
        assert autenticado(client, cen.gestor_a).get(rota).status_code == 200, rota
        for u in (cen.sec_a, cen.prof_a1, cen.resp_a1):
            assert autenticado(client, u).get(rota).status_code == 403, (rota, u["papel"])


def test_relatorios_sem_modulo_e_periodo_invalido(client, db_ctx):
    cen = _cenario(db_ctx)
    g = autenticado(client, cen.gestor_a)
    assert g.get("/api/financeiro/relatorios/sem-acordo?de=2026-11-10&ate=2026-11-01").status_code == 400
    assert g.get("/api/financeiro/relatorios/acabando?restantes=9").status_code == 400
    db.execute("UPDATE organizacoes SET plano = 'starter' WHERE id = ?", (cen.org_a,))
    for rota in ROTAS:
        assert g.get(rota).status_code == 403


def test_outra_clinica_nunca_aparece(client, db_ctx):
    cen = _cenario(db_ctx)
    outro = novo_paciente(cen.org_b, "Paciente B")
    _cobranca(cen, valor=10000, status="vencido", venc=_dia(5), paciente_id=outro, org=cen.org_b)
    db.execute("""INSERT INTO consultas (paciente_id, profissional_id, data_hora, status, especialidade,
                                         procedimento_valor_centavos) VALUES (?, ?, ?, 'realizada', 'Geral', 5000)""",
               (outro, cen.prof_b1["id"], f"{_dia(3)} 09:00:00"))
    g = autenticado(client, cen.gestor_a)
    assert g.get("/api/financeiro/relatorios/em-aberto").get_json()["cobrancas"] == []
    assert g.get("/api/financeiro/relatorios/sem-acordo").get_json()["sessoes"] == []
