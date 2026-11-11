"""Financeiro etapa 2: fechamento de caixa (serviço, horário de Brasília nos pagamentos, rotas e PDF)."""
import base64
import io
from datetime import datetime

import db
import ausencias_service
import caixa_service
from factories import novo_paciente, novo_usuario, vincular_responsavel

from conftest import autenticado
from test_cobranca_baixa import _cenario, _cobranca, _pagar


DIA = "2026-11-09"


def _pag(cid, valor, forma="pix", pago_em=f"{DIA} 10:00:00", quem="Ana", estornado_em=None, motivo=None):
    return db.execute(
        """INSERT INTO pagamentos (cobranca_id, valor_centavos, forma, pago_em, recebido_por_nome,
                                   estornado_em, estorno_motivo) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (cid, valor, forma, pago_em, quem, estornado_em, motivo))


def _fechar(cen, de=DIA, ate=DIA, **filtros):
    return caixa_service.fechamento(cen.org_a, de, ate, **filtros)


def _brasilia_22h30(monkeypatch):
    monkeypatch.setattr(ausencias_service, "_agora_utc", lambda: datetime(2026, 11, 10, 1, 30))


# ------------------------------------------------------------------ horário de Brasília

def test_agora_brasilia_iso_tres_horas_antes_do_utc(monkeypatch):
    _brasilia_22h30(monkeypatch)
    assert ausencias_service.agora_brasilia_iso() == "2026-11-09 22:30:00"


def test_baixa_manual_sem_data_grava_hora_de_brasilia(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    _brasilia_22h30(monkeypatch)
    r = _pagar(client, cen.gestor_a, cid)
    assert r.status_code == 200, r.get_json()
    pg = db.query_one("SELECT pago_em FROM pagamentos WHERE cobranca_id = ?", (cid,))
    assert pg["pago_em"] == "2026-11-09 22:30:00"


def test_estorno_grava_hora_de_brasilia(client, db_ctx, monkeypatch):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    pid = _pagar(client, cen.gestor_a, cid).get_json()["pagamento_id"]
    _brasilia_22h30(monkeypatch)
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/pagamento/{pid}/estornar", json={"motivo": "erro"})
    assert r.status_code == 200, r.get_json()
    assert db.query_one("SELECT estornado_em FROM pagamentos WHERE id = ?", (pid,))["estornado_em"] == "2026-11-09 22:30:00"


# ------------------------------------------------------------------ serviço

def test_totais_por_forma_e_por_quem(db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, valor=50000)
    _pag(cid, 10000, "pix", quem="Ana")
    _pag(cid, 5000, "dinheiro", quem="Ana")
    _pag(cid, 2500, "pix", quem="Mercado Pago")
    d = _fechar(cen)
    assert d["totais"] == {"recebido_centavos": 17500, "estornado_centavos": 0, "liquido_centavos": 17500, "quantidade": 3}
    assert d["por_forma"][0] == {"forma": "pix", "recebido_centavos": 12500, "estornado_centavos": 0, "liquido_centavos": 12500}
    assert d["por_forma"][1]["forma"] == "dinheiro"
    ana = next(x for x in d["por_quem"] if x["recebido_por"] == "Ana")
    assert ana["recebido_centavos"] == 15000 and ana["liquido_centavos"] == 15000
    assert len(d["recebimentos"]) == 3 and d["estornos"] == []
    r = d["recebimentos"][0]
    assert r["paciente_nome"] == "Paciente A1" and r["cobranca_id"] == cid and r["estornado"] is False


def test_estornado_no_mesmo_dia_entra_e_sai(db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    _pag(cid, 10000, estornado_em=f"{DIA} 15:00:00", motivo="duplicado")
    d = _fechar(cen)
    assert len(d["recebimentos"]) == 1 and d["recebimentos"][0]["estornado"] is True
    assert len(d["estornos"]) == 1 and d["estornos"][0]["motivo"] == "duplicado"
    assert d["totais"]["recebido_centavos"] == 10000
    assert d["totais"]["estornado_centavos"] == 10000
    assert d["totais"]["liquido_centavos"] == 0


def test_estorno_de_pagamento_antigo_so_sai(db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    _pag(cid, 10000, pago_em="2026-11-01 10:00:00", estornado_em=f"{DIA} 09:00:00", motivo="erro")
    d = _fechar(cen)
    assert d["recebimentos"] == [] and len(d["estornos"]) == 1
    assert d["totais"]["liquido_centavos"] == -10000
    assert d["por_forma"] == [{"forma": "pix", "recebido_centavos": 0, "estornado_centavos": 10000, "liquido_centavos": -10000}]
    antes = _fechar(cen, "2026-11-01", "2026-11-01")
    assert antes["totais"]["recebido_centavos"] == 10000 and antes["totais"]["estornado_centavos"] == 0
    assert antes["recebimentos"][0]["estornado"] is True


def test_filtros_quem_e_forma(db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen, valor=50000)
    _pag(cid, 10000, "pix", quem="Ana")
    _pag(cid, 5000, "dinheiro", quem="Ana")
    _pag(cid, 2500, "pix", quem="Mercado Pago")
    d = _fechar(cen, recebido_por="Ana", forma="pix")
    assert [x["valor_centavos"] for x in d["recebimentos"]] == [10000]
    assert d["totais"]["recebido_centavos"] == 10000
    assert d["opcoes"]["quem"] == ["Ana", "Mercado Pago"]
    assert set(d["opcoes"]["formas"]) == {"pix", "dinheiro"}


def test_sem_nome_vira_nao_informado(db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    _pag(cid, 3000, quem=None)
    d = _fechar(cen)
    assert d["recebimentos"][0]["recebido_por"] == "Não informado"
    assert len(_fechar(cen, recebido_por="Não informado")["recebimentos"]) == 1


def test_outra_clinica_nao_aparece(db_ctx):
    cen = _cenario(db_ctx)
    cid_b = db.execute(
        """INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status, organizacao_id, tipo)
           VALUES (?, 'B', 1000, ?, 'pendente', ?, 'manual')""", (novo_paciente(cen.org_b, "Paciente B"), DIA, cen.org_b))
    _pag(cid_b, 1000)
    assert _fechar(cen)["recebimentos"] == []


def test_paciente_arquivado_aparece(db_ctx):
    cen = _cenario(db_ctx)
    cid = _cobranca(cen)
    _pag(cid, 1000)
    db.execute("UPDATE pacientes SET ativo = 0 WHERE id = ?", (cen.paciente_a1,))
    assert len(_fechar(cen)["recebimentos"]) == 1


def test_validar_periodo():
    v = caixa_service.validar_periodo
    assert v("", "", "2026-11-09") == ("2026-11-09", "2026-11-09")
    assert v(None, None, "2026-11-09") == ("2026-11-09", "2026-11-09")
    assert v("2026-11-01", "", "2026-11-09") == ("2026-11-01", "2026-11-09")
    assert v("2026-11-10", "2026-11-09", "2026-11-09") == "A data inicial é depois da final."
    assert v("2025-01-01", "2026-11-09", "2026-11-09") == "Escolha um período de até 1 ano."
    assert v("09/11/2026", "", "2026-11-09") == "Data inválida."
    assert v("2026-02-30", "", "2026-11-09") == "Data inválida."
