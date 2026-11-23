"""Financeiro 6.5: extrato do paciente (sessões uma a uma, cobranças, pagamentos) em JSON e PDF."""
from datetime import timedelta

import db
import ausencias_service
import relatorios_service
from factories import novo_paciente, vincular_responsavel

from conftest import autenticado
from test_cobranca_baixa import _cenario, _cobranca


def _hoje():
    return ausencias_service.hoje_brasilia()


def _dia(n):
    return (_hoje() - timedelta(days=n)).isoformat()


def _consulta(cen, dias, esp="Fonoaudiologia", status="realizada", valor=15000, paciente=None):
    return db.execute(
        """INSERT INTO consultas (paciente_id, profissional_id, data_hora, status, especialidade,
                                  procedimento_id, procedimento_valor_centavos)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (paciente or cen.paciente_a1, cen.prof_a1["id"], f"{_dia(dias)} 09:00:00", status, esp, cen.proc_a, valor))


def _item(cid, consulta, valor=15000):
    db.execute("""INSERT INTO cobranca_itens (cobranca_id, consulta_id, data_hora, procedimento_nome, valor_centavos,
                                               status_origem) VALUES (?, ?, ?, 'Sessão', ?, 'realizada')""",
               (cid, consulta, db.query_one("SELECT data_hora FROM consultas WHERE id = ?", (consulta,))["data_hora"],
                valor))


def _acordo(cen, tipo, esp, **campos):
    dados = {"organizacao_id": cen.org_a, "paciente_id": cen.paciente_a1, "especialidade": esp, "tipo": tipo,
             "inicio": _dia(60), "status": "ativo"}
    dados.update(campos)
    return db.execute(f"INSERT INTO acordos_pagamento ({', '.join(dados)}) VALUES ({', '.join('?' for _ in dados)})",
                      tuple(dados.values()))


def _pagar(cid, valor, dias=2, estornado=False):
    return db.execute("""INSERT INTO pagamentos (cobranca_id, valor_centavos, forma, pago_em, recebido_por_nome,
                                                 estornado_em, estorno_motivo) VALUES (?, ?, 'pix', ?, 'Ana', ?, ?)""",
                      (cid, valor, f"{_dia(dias)} 10:00:00", f"{_dia(1)} 10:00:00" if estornado else None,
                       "erro" if estornado else None))


def _cenario_completo(db_ctx):
    """Avulsa (2 sessões em cobranças), pacote (3 sessões consumidas), mensalidade (2 sessões),
    falta não cobrada, sessão de outro paciente e uma cobrança vencida antes do período."""
    cen = _cenario(db_ctx)
    s1, s2 = _consulta(cen, 20), _consulta(cen, 18)
    c1 = _cobranca(cen, valor=15000, status="pago", venc=_dia(15), descricao="Sessão 1")
    c2 = _cobranca(cen, valor=15000, status="pendente", venc=_dia(10), descricao="Sessão 2")
    _item(c1, s1)
    _item(c2, s2)
    _pagar(c1, 15000)
    _pagar(c2, 5000, estornado=True)

    pac = _acordo(cen, "pacote", "Psicopedagogia", valor_centavos=100000, sessoes_total=10, parcelas=2)
    for n, d in enumerate((16, 14, 12), start=1):
        s = _consulta(cen, d, esp="Psicopedagogia", valor=12000)
        db.execute("INSERT INTO acordo_pacote_consumo (consulta_id, acordo_id, numero, status_origem) VALUES (?, ?, ?, 'realizada')",
                   (s, pac, n))
    _cobranca(cen, valor=50000, status="pendente", venc=_dia(8), tipo="pacote", acordo_id=pac, descricao="Pacote 1/2")

    men = _acordo(cen, "mensalidade", "Terapia Ocupacional", valor_centavos=60000, dia_vencimento=10)
    _consulta(cen, 6, esp="Terapia Ocupacional", valor=13000)
    _consulta(cen, 4, esp="Terapia Ocupacional", valor=13000)
    mes = _dia(6)[:8] + "01"
    _cobranca(cen, valor=60000, status="pendente", venc=_dia(3), tipo="mensalidade", acordo_id=men,
              periodo_inicio=mes, descricao="Mensalidade")

    _consulta(cen, 2, status="faltou")                       # falta sem cobrança: fora do extrato
    _consulta(cen, 5, paciente=cen.paciente_a2)              # outro paciente: fora
    _cobranca(cen, valor=20000, status="vencido", venc=_dia(120), descricao="Antiga")   # antes do período
    return cen


def test_extrato_sessao_por_sessao_e_totais(db_ctx):
    cen = _cenario_completo(db_ctx)
    d = relatorios_service.extrato_paciente(cen.org_a, cen.paciente_a1, _dia(30), _dia(0), hoje=_dia(0))
    assert d["paciente"]["id"] == cen.paciente_a1
    assert len(d["sessoes"]) == 7
    situacoes = [s["situacao"] for s in d["sessoes"]]
    assert situacoes[0].startswith("Cobrança: Sessão 1")
    assert situacoes[1].startswith("Cobrança: Sessão 2")
    assert situacoes[2:5] == ["Pacote: sessão 1 de 10", "Pacote: sessão 2 de 10", "Pacote: sessão 3 de 10"]
    assert all(s.startswith("Mensalidade ") for s in situacoes[5:7])
    assert d["sessoes"][0]["valor_centavos"] == 15000 and d["sessoes"][2]["valor_centavos"] == 12000
    assert [c["descricao"] for c in d["cobrancas"]] == ["Sessão 1", "Sessão 2", "Pacote 1/2", "Mensalidade"]
    t = d["totais"]
    assert t["cobrado_centavos"] == 15000 + 15000 + 50000 + 60000        # pelas cobranças, sem dobrar as sessões
    assert t["pago_centavos"] == 15000                                    # o estornado não soma
    assert t["saldo_aberto_centavos"] == 15000 + 50000 + 60000 + 20000    # inclui a vencida antiga
    estornado = [p for p in d["pagamentos"] if p["estornado"]]
    assert len(estornado) == 1 and estornado[0]["valor_centavos"] == 5000


def test_extrato_nao_traz_repasse_nem_anotacao_interna(db_ctx):
    cen = _cenario_completo(db_ctx)
    db.execute("UPDATE cobrancas SET revisar = 1, revisar_motivo = 'SEGREDO' WHERE paciente_id = ?", (cen.paciente_a1,))
    d = relatorios_service.extrato_paciente(cen.org_a, cen.paciente_a1, _dia(30), _dia(0), hoje=_dia(0))
    texto = repr(d)
    assert "SEGREDO" not in texto and "revisar" not in texto and "repasse" not in texto


def test_sessao_nao_cobrada_e_sem_acordo(db_ctx):
    cen = _cenario(db_ctx)
    s = _consulta(cen, 5)
    db.execute("INSERT INTO consulta_decisao_cobranca (consulta_id, decisao) VALUES (?, 'nao_cobrar')", (s,))
    _consulta(cen, 3)
    d = relatorios_service.extrato_paciente(cen.org_a, cen.paciente_a1, _dia(30), _dia(0), hoje=_dia(0))
    assert [x["situacao"] for x in d["sessoes"]] == ["Não cobrada", "Sem acordo"]


def test_periodo_vazio(db_ctx):
    cen = _cenario(db_ctx)
    d = relatorios_service.extrato_paciente(cen.org_a, cen.paciente_a1, "2025-01-01", "2025-01-31", hoje=_dia(0))
    assert d["sessoes"] == [] and d["cobrancas"] == [] and d["pagamentos"] == []
    assert d["totais"] == {"cobrado_centavos": 0, "pago_centavos": 0, "saldo_aberto_centavos": 0}


# ------------------------------------------------------------------ rotas

def test_permissoes_do_extrato(client, db_ctx):
    cen = _cenario(db_ctx)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    url = f"/api/financeiro/paciente/{cen.paciente_a1}/extrato"
    for u in (cen.gestor_a, cen.sec_a):
        assert autenticado(client, u).get(url).status_code == 200
        assert autenticado(client, u).get(url + "/pdf").status_code == 200
    for u in (cen.prof_a1, cen.resp_a1):
        assert autenticado(client, u).get(url).status_code == 403
        assert autenticado(client, u).get(url + "/pdf").status_code == 403


def test_extrato_de_outra_clinica_404(client, db_ctx):
    cen = _cenario(db_ctx)
    outro = novo_paciente(cen.org_b, "Paciente B")
    for u in (cen.gestor_a, cen.sec_a):
        assert autenticado(client, u).get(f"/api/financeiro/paciente/{outro}/extrato").status_code == 404
        assert autenticado(client, u).get(f"/api/financeiro/paciente/{outro}/extrato/pdf").status_code == 404


def test_extrato_sem_modulo_e_periodo_invalido(client, db_ctx):
    cen = _cenario(db_ctx)
    g = autenticado(client, cen.gestor_a)
    r = g.get(f"/api/financeiro/paciente/{cen.paciente_a1}/extrato?de=2026-11-10&ate=2026-11-01")
    assert r.status_code == 400
    db.execute("UPDATE organizacoes SET plano = 'starter' WHERE id = ?", (cen.org_a,))
    assert g.get(f"/api/financeiro/paciente/{cen.paciente_a1}/extrato").status_code == 403


def test_extrato_padrao_ultimos_3_meses(client, db_ctx):
    cen = _cenario(db_ctx)
    d = autenticado(client, cen.gestor_a).get(f"/api/financeiro/paciente/{cen.paciente_a1}/extrato").get_json()
    assert d["ate"] == _dia(0)
    assert d["de"] < _dia(85) and d["de"] >= _dia(93)


def test_extrato_pdf(client, db_ctx):
    import base64
    import io
    from PIL import Image
    cen = _cenario_completo(db_ctx)
    db.execute("UPDATE pacientes SET nome = ? WHERE id = ?", ("Ana <b>& Cia", cen.paciente_a1))
    g = autenticado(client, cen.gestor_a)
    url = f"/api/financeiro/paciente/{cen.paciente_a1}/extrato/pdf?de={_dia(30)}&ate={_dia(0)}"
    r = g.get(url)
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")
    assert f"-{_dia(30)}-a-{_dia(0)}.pdf" in r.headers["Content-Disposition"]
    assert g.get(f"/api/financeiro/paciente/{cen.paciente_a1}/extrato/pdf?de=2025-01-01&ate=2025-01-31").data.startswith(b"%PDF")
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), (91, 79, 233)).save(buf, format="PNG")
    db.execute("UPDATE organizacoes SET logo_base64 = ? WHERE id = ?", (base64.b64encode(buf.getvalue()).decode(), cen.org_a))
    assert g.get(url).data.startswith(b"%PDF")
