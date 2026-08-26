"""
Regressão para a Fase 1 da cobrança por cartão de crédito (Plataforma →
Clínicas, 26/08/2026): o próprio Gestor paga a cobrança da assinatura da
clínica no cartão, via Card Payment Brick, na tela "Sua Assinatura" —
ver pagamento_plataforma_service.py::criar_pagamento_cartao e a rota
POST /api/admin/assinatura/<id>/pagar-cartao em admin_bp.py.

Mesmo padrão de teste de unidade do resto da suíte de pagamento — mocka o
SDK da Mercado Pago inteiro (substituindo `pagamento_plataforma_service._sdk`
por um objeto falso), sem bater na API real e sem depender do pacote
`mercadopago` estar instalado no ambiente de teste.
"""
import db
import pagamento_plataforma_service as pps
from factories import nova_organizacao, novo_usuario
from conftest import autenticado


class _SDKFalso:
    """Substitui `_sdk()` inteiro — mais simples e mais robusto do que tentar
    mockar o pacote `mercadopago` de verdade."""

    def __init__(self, resposta):
        self._resposta = resposta

    def payment(self):
        return self

    def create(self, payment_data, request_options=None):
        return self._resposta


def _cobranca_pendente(org_id, valor_centavos=14970):
    return db.execute(
        "INSERT INTO cobrancas_planos (organizacao_id, plano_codigo, valor_centavos) VALUES (?, ?, ?)",
        (org_id, "starter", valor_centavos),
    )


def _configurar_mercadopago_plataforma():
    db.salvar_config_integracao_plataforma(
        "mercadopago", {"access_token": "TOKEN-TESTE", "public_key": "PUBLIC-TESTE"}, status="conectado",
    )


def _corpo_cartao(email):
    return {
        "token": "tok-abc",
        "payment_method_id": "visa",
        "installments": 1,
        "payer": {"email": email},
    }


# ---------------------------------------------------------------- Public Key exposta pra tela

def test_public_key_e_exposta_na_tela_sua_assinatura(client, db_ctx):
    org = nova_organizacao("Clínica Cartão")
    gestor = novo_usuario(org, "Gestora", "gestora@cartao.com", "gestor")
    _configurar_mercadopago_plataforma()

    r = autenticado(client, gestor).get("/api/admin/assinatura")
    assert r.status_code == 200
    assert r.get_json()["mercadopago_public_key"] == "PUBLIC-TESTE"


def test_sem_mercadopago_configurado_public_key_e_nula(client, db_ctx):
    org = nova_organizacao("Clínica Sem MP")
    gestor = novo_usuario(org, "Gestora", "gestora@semmp.com", "gestor")

    r = autenticado(client, gestor).get("/api/admin/assinatura")
    assert r.status_code == 200
    assert r.get_json()["mercadopago_public_key"] is None


# ---------------------------------------------------------------- Pagamento no cartão

def test_pagamento_aprovado_confirma_cobranca_na_hora(client, db_ctx, monkeypatch):
    org = nova_organizacao("Clínica Cartão Aprovado")
    gestor = novo_usuario(org, "Gestora", "gestora@aprovado.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_id = _cobranca_pendente(org)

    monkeypatch.setattr(pps, "_sdk", lambda: _SDKFalso({"status": 201, "response": {"id": 999888, "status": "approved"}}))

    r = autenticado(client, gestor).post(
        f"/api/admin/assinatura/{cobranca_id}/pagar-cartao", json=_corpo_cartao("gestora@aprovado.com"),
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == "aprovado"

    cobranca = db_ctx.query_one("SELECT * FROM cobrancas_planos WHERE id = ?", (cobranca_id,))
    assert cobranca["status"] == "pago"
    assert cobranca["forma_confirmacao"] == "mercadopago_cartao"
    assert cobranca["mp_payment_id"] == "999888"


def test_cartao_recusado_mantem_cobranca_pendente(client, db_ctx, monkeypatch):
    org = nova_organizacao("Clínica Cartão Recusado")
    gestor = novo_usuario(org, "Gestora", "gestora@recusado.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_id = _cobranca_pendente(org)

    monkeypatch.setattr(pps, "_sdk", lambda: _SDKFalso(
        {"status": 201, "response": {"id": 111, "status": "rejected", "status_detail": "cc_rejected_insufficient_amount"}}
    ))

    r = autenticado(client, gestor).post(
        f"/api/admin/assinatura/{cobranca_id}/pagar-cartao", json=_corpo_cartao("gestora@recusado.com"),
    )
    assert r.status_code == 400
    assert "recusado" in r.get_json()["erro"].lower()

    cobranca = db_ctx.query_one("SELECT * FROM cobrancas_planos WHERE id = ?", (cobranca_id,))
    assert cobranca["status"] == "pendente"


def test_cartao_em_analise_fica_pendente_mas_guarda_payment_id(client, db_ctx, monkeypatch):
    """Antifraude da Mercado Pago pode segurar um cartão pra análise em vez
    de aprovar/recusar na hora — a cobrança fica pendente, mas já guardamos o
    mp_payment_id pra o webhook confirmar sozinho quando a decisão sair
    (mesmo comportamento que o PIX já tem hoje)."""
    org = nova_organizacao("Clínica Cartão Análise")
    gestor = novo_usuario(org, "Gestora", "gestora@analise.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_id = _cobranca_pendente(org)

    monkeypatch.setattr(pps, "_sdk", lambda: _SDKFalso({"status": 201, "response": {"id": 222, "status": "in_process"}}))

    r = autenticado(client, gestor).post(
        f"/api/admin/assinatura/{cobranca_id}/pagar-cartao", json=_corpo_cartao("gestora@analise.com"),
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "em_analise"

    cobranca = db_ctx.query_one("SELECT * FROM cobrancas_planos WHERE id = ?", (cobranca_id,))
    assert cobranca["status"] == "pendente"
    assert cobranca["mp_payment_id"] == "222"


def test_cobranca_ja_paga_e_recusada(client, db_ctx):
    org = nova_organizacao("Clínica Já Paga")
    gestor = novo_usuario(org, "Gestora", "gestora@japaga.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_id = _cobranca_pendente(org)
    db.execute("UPDATE cobrancas_planos SET status = 'pago' WHERE id = ?", (cobranca_id,))

    r = autenticado(client, gestor).post(
        f"/api/admin/assinatura/{cobranca_id}/pagar-cartao", json=_corpo_cartao("gestora@japaga.com"),
    )
    assert r.status_code == 400


def test_sem_dados_do_cartao_e_recusado_com_400(client, db_ctx):
    org = nova_organizacao("Clínica Dados Incompletos")
    gestor = novo_usuario(org, "Gestora", "gestora@incompleto.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_id = _cobranca_pendente(org)

    r = autenticado(client, gestor).post(f"/api/admin/assinatura/{cobranca_id}/pagar-cartao", json={})
    assert r.status_code == 400


def test_outra_clinica_nao_consegue_pagar_cobranca_alheia(client, db_ctx):
    """IDOR: o Gestor da clínica B não pode pagar (nem ver) uma cobrança da
    clínica A só sabendo o id — mesmo padrão de isolamento entre clínicas
    testado no resto da suíte."""
    org_a = nova_organizacao("Clínica A Cartão")
    org_b = nova_organizacao("Clínica B Cartão")
    gestor_b = novo_usuario(org_b, "Gestora B", "gestorab@cartao.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_a = _cobranca_pendente(org_a)

    r = autenticado(client, gestor_b).post(
        f"/api/admin/assinatura/{cobranca_a}/pagar-cartao", json=_corpo_cartao("gestorab@cartao.com"),
    )
    assert r.status_code == 404

    cobranca = db_ctx.query_one("SELECT * FROM cobrancas_planos WHERE id = ?", (cobranca_a,))
    assert cobranca["status"] == "pendente"
