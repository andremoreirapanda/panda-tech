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
import pytest

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


# ================================================================== Checkout Pro (fallback do cartão, 26/08/2026)
#
# O Card Payment Brick embutido acima (testado ao vivo) trava na
# inicialização nesta conta de Mercado Pago mesmo com CSP/chave pública
# corretos — ver o comentário em criar_checkout_cartao. Checkout Pro troca o
# Brick por um link hospedado pela própria Mercado Pago, aberto em nova aba.

class _SDKPreferenceFalso:
    """Só o suficiente pra sdk.preference().create(...) — não mistura com
    _SDKFalso acima (que é só payment().create()) pra não arriscar quebrar
    os testes existentes do Brick."""

    def __init__(self, resposta):
        self._resposta = resposta

    def preference(self):
        return self

    def create(self, preference_data):
        return self._resposta


class _SDKWebhookFalso:
    """Só o suficiente pra sdk.payment().get(id, opcoes) — usado nos testes
    de processar_webhook abaixo."""

    def __init__(self, resposta):
        self._resposta = resposta

    def payment(self):
        return self

    def get(self, payment_id, request_options=None):
        return self._resposta


def test_checkout_cartao_cria_link_de_pagamento(client, db_ctx, monkeypatch):
    org = nova_organizacao("Clínica Checkout Pro")
    gestor = novo_usuario(org, "Gestora", "gestora@checkout.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_id = _cobranca_pendente(org)
    monkeypatch.setenv("URL_APP", "https://pandatech.exemplo.com.br")

    monkeypatch.setattr(pps, "_sdk", lambda: _SDKPreferenceFalso(
        {"status": 201, "response": {"id": "pref-123", "init_point": "https://www.mercadopago.com/checkout/v1/pref-123"}}
    ))

    r = autenticado(client, gestor).post(f"/api/admin/assinatura/{cobranca_id}/checkout-cartao")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["checkout_url"] == "https://www.mercadopago.com/checkout/v1/pref-123"


def test_checkout_cartao_sem_url_app_e_recusado(client, db_ctx, monkeypatch):
    org = nova_organizacao("Clínica Sem URL_APP")
    gestor = novo_usuario(org, "Gestora", "gestora@semurlapp.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_id = _cobranca_pendente(org)
    monkeypatch.delenv("URL_APP", raising=False)
    monkeypatch.setattr(pps, "_sdk", lambda: _SDKPreferenceFalso({"status": 201, "response": {"init_point": "https://x"}}))

    r = autenticado(client, gestor).post(f"/api/admin/assinatura/{cobranca_id}/checkout-cartao")
    assert r.status_code == 400
    assert "URL_APP" in r.get_json()["erro"]


def test_checkout_cartao_cobranca_ja_paga_e_recusado(client, db_ctx, monkeypatch):
    org = nova_organizacao("Clínica Checkout Já Paga")
    gestor = novo_usuario(org, "Gestora", "gestora@checkoutpaga.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_id = _cobranca_pendente(org)
    db.execute("UPDATE cobrancas_planos SET status = 'pago' WHERE id = ?", (cobranca_id,))
    monkeypatch.setenv("URL_APP", "https://pandatech.exemplo.com.br")

    r = autenticado(client, gestor).post(f"/api/admin/assinatura/{cobranca_id}/checkout-cartao")
    assert r.status_code == 400


def test_checkout_cartao_outra_clinica_nao_consegue_criar_link_alheio(client, db_ctx):
    """Mesmo IDOR do pagar-cartao (Brick): a rota checa organizacao_id antes
    de qualquer coisa, então nem chega a chamar o Mercado Pago."""
    org_a = nova_organizacao("Clínica A Checkout")
    org_b = nova_organizacao("Clínica B Checkout")
    gestor_b = novo_usuario(org_b, "Gestora B", "gestorab@checkout.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_a = _cobranca_pendente(org_a)

    r = autenticado(client, gestor_b).post(f"/api/admin/assinatura/{cobranca_a}/checkout-cartao")
    assert r.status_code == 404


# ---------------------------------------------------------------- processar_webhook — fallback por external_reference

def test_webhook_confirma_pagamento_do_checkout_pro_por_external_reference(client, db_ctx, monkeypatch):
    """Diferente do PIX/Brick, o Checkout Pro não tem `mp_payment_id` salvo
    de antemão (só existe uma "preferência" até o Gestor pagar de verdade) —
    o webhook precisa achar a cobrança pelo external_reference do próprio
    pagamento e gravar o mp_payment_id na primeira notificação."""
    org = nova_organizacao("Clínica Webhook Checkout")
    novo_usuario(org, "Gestora", "gestora@webhookcheckout.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_id = _cobranca_pendente(org)
    # Sem mp_payment_id salvo — é exatamente o estado após criar_checkout_cartao.
    assert db_ctx.query_one("SELECT mp_payment_id FROM cobrancas_planos WHERE id = ?", (cobranca_id,))["mp_payment_id"] is None

    monkeypatch.setattr(pps, "_sdk", lambda: _SDKWebhookFalso({
        "status": 200,
        "response": {"id": 777, "status": "approved", "payment_method_id": "master",
                      "external_reference": f"cobranca-plano-{cobranca_id}"},
    }))

    resultado = pps.processar_webhook("777")
    assert resultado == {"ok": True, "status": "pago"}

    cobranca = db_ctx.query_one("SELECT * FROM cobrancas_planos WHERE id = ?", (cobranca_id,))
    assert cobranca["status"] == "pago"
    assert cobranca["forma_confirmacao"] == "mercadopago_cartao"
    assert cobranca["mp_payment_id"] == "777"


def test_webhook_checkout_pro_pendente_guarda_payment_id_sem_confirmar(client, db_ctx, monkeypatch):
    org = nova_organizacao("Clínica Webhook Checkout Pendente")
    novo_usuario(org, "Gestora", "gestora@webhookpendente.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_id = _cobranca_pendente(org)

    monkeypatch.setattr(pps, "_sdk", lambda: _SDKWebhookFalso({
        "status": 200,
        "response": {"id": 888, "status": "pending", "payment_method_id": "master",
                      "external_reference": f"cobranca-plano-{cobranca_id}"},
    }))

    resultado = pps.processar_webhook("888")
    assert resultado == {"ok": True, "status": "pending"}

    cobranca = db_ctx.query_one("SELECT * FROM cobrancas_planos WHERE id = ?", (cobranca_id,))
    assert cobranca["status"] == "pendente"
    assert cobranca["mp_payment_id"] == "888"  # já linkado — a próxima notificação acha direto por aqui


def test_webhook_sem_referencia_conhecida_e_ignorado(client, db_ctx, monkeypatch):
    """external_reference que não bate com nenhuma cobrança (ex: pagamento
    de outro produto na mesma conta de Mercado Pago) — ignora sem erro."""
    _configurar_mercadopago_plataforma()
    monkeypatch.setattr(pps, "_sdk", lambda: _SDKWebhookFalso({
        "status": 200,
        "response": {"id": 999, "status": "approved", "external_reference": "algo-que-nao-existe"},
    }))

    resultado = pps.processar_webhook("999")
    assert resultado["ignorado"] is True


def test_webhook_pix_continua_rotulado_corretamente(client, db_ctx, monkeypatch):
    """Regressão: o webhook do PIX (que já chega com mp_payment_id salvo por
    criar_pagamento_pix) precisa continuar gravando forma_confirmacao como
    mercadopago_pix, não mercadopago_cartao, depois da mudança que passou a
    olhar o payment_method_id em vez de um valor fixo."""
    org = nova_organizacao("Clínica Webhook Pix")
    novo_usuario(org, "Gestora", "gestora@webhookpix.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_id = _cobranca_pendente(org)
    db.execute("UPDATE cobrancas_planos SET mp_payment_id = ? WHERE id = ?", ("321", cobranca_id))

    monkeypatch.setattr(pps, "_sdk", lambda: _SDKWebhookFalso({
        "status": 200,
        "response": {"id": 321, "status": "approved", "payment_method_id": "pix",
                      "external_reference": f"cobranca-plano-{cobranca_id}"},
    }))

    resultado = pps.processar_webhook("321")
    assert resultado == {"ok": True, "status": "pago"}

    cobranca = db_ctx.query_one("SELECT * FROM cobrancas_planos WHERE id = ?", (cobranca_id,))
    assert cobranca["forma_confirmacao"] == "mercadopago_pix"


# ---------------------------------------------------------------------------
# Correção de segurança 04/09/2026: o CodeQL apontou "information exposure
# through an exception" nas rotas /assinatura/<id>/gerar-pix e
# /assinatura/<id>/pagar-cartao — elas faziam `except RuntimeError as exc:
# jsonify({"erro": str(exc)})`, capturando QUALQUER RuntimeError, inclusive
# um totalmente inesperado (bug, falha de biblioteca) cujo texto poderia
# vazar detalhe interno do servidor pro cliente. A correção introduziu
# `ErroPagamentoUsuario` (subclasse de RuntimeError só para as mensagens de
# negócio deliberadas, como "Cobrança não encontrada.") e estreitou o
# `except` dos dois endpoints pra capturar só essa subclasse.
#
# Os testes acima (ex: test_cobranca_ja_paga_e_recusada) já cobrem que uma
# mensagem de negócio real continua chegando normalmente ao cliente. Este
# teste cobre o lado que a auditoria pediu: um erro que NÃO é
# ErroPagamentoUsuario tem que escapar do try/except do blueprint em vez de
# virar uma resposta 400 com o texto exposto (nesta app de teste,
# `testing=True` faz uma exceção não tratada se propagar pra quem chamou o
# client, em vez de virar 500 silencioso — é exatamente esse escape que
# comprova que ela não foi capturada pelo except errado).
# ---------------------------------------------------------------------------

def test_erro_inesperado_no_gerar_pix_nao_vira_mensagem_pro_cliente(client, db_ctx, monkeypatch):
    org = nova_organizacao("Clínica Erro Inesperado Pix")
    gestor = novo_usuario(org, "Gestora", "gestora@erroinesperado.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_id = _cobranca_pendente(org)

    def _sdk_quebrado():
        raise RuntimeError("detalhe interno sensível que não deveria ir pro cliente")

    monkeypatch.setattr(pps, "_sdk", _sdk_quebrado)

    with pytest.raises(RuntimeError, match="detalhe interno sensível"):
        autenticado(client, gestor).post(f"/api/admin/assinatura/{cobranca_id}/gerar-pix")


def test_erro_inesperado_no_pagar_cartao_nao_vira_mensagem_pro_cliente(client, db_ctx, monkeypatch):
    org = nova_organizacao("Clínica Erro Inesperado Cartão")
    gestor = novo_usuario(org, "Gestora", "gestora@erroinesperadocartao.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_id = _cobranca_pendente(org)

    def _sdk_quebrado():
        raise RuntimeError("detalhe interno sensível que não deveria ir pro cliente")

    monkeypatch.setattr(pps, "_sdk", _sdk_quebrado)

    with pytest.raises(RuntimeError, match="detalhe interno sensível"):
        autenticado(client, gestor).post(
            f"/api/admin/assinatura/{cobranca_id}/pagar-cartao", json=_corpo_cartao("gestora@erroinesperadocartao.com"),
        )


def test_erro_de_negocio_continua_com_mensagem_amigavel_gerar_pix(client, db_ctx):
    """Contraprova da correção acima: um ErroPagamentoUsuario de verdade
    (mensagem de negócio deliberada) continua sendo capturado e devolvido
    normalmente ao cliente — a correção estreitou o except, não o quebrou."""
    org = nova_organizacao("Clínica Cobrança Paga Pix")
    gestor = novo_usuario(org, "Gestora", "gestora@japagapix.com", "gestor")
    _configurar_mercadopago_plataforma()
    cobranca_id = _cobranca_pendente(org)
    db.execute("UPDATE cobrancas_planos SET status = 'pago' WHERE id = ?", (cobranca_id,))

    r = autenticado(client, gestor).post(f"/api/admin/assinatura/{cobranca_id}/gerar-pix")
    assert r.status_code == 400, r.get_data(as_text=True)
    assert "já está paga" in r.get_json()["erro"]
