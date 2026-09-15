"""
Testes da Fase 2 da cobrança por cartão (Plataforma → Clínicas, 15/09/2026):

  1. Correção do bug em `_ja_gerada_no_mes` — uma cobrança AVULSA no mês não
     pode mais "esconder" a mensalidade de verdade (e vice-versa).
  2. Assinatura recorrente no cartão (`assinaturas_cartao_recorrentes`):
     ativar, autorizar (webhook subscription_preapproval), cobrar (webhook
     subscription_authorized_payment — sucesso, falha e idempotência),
     cancelar, e o ciclo mensal comum pulando quem está com assinatura ativa.

Mesmo padrão de teste de unidade do resto da suíte de pagamento — mocka o
SDK da Mercado Pago inteiro (substituindo `pagamento_plataforma_service._sdk`
por um objeto falso) e, para o webhook de cobrança recorrente, o `requests`
usado internamente — sem bater na API real e sem depender dos pacotes
`mercadopago`/`requests` fazendo chamada de rede nenhuma.
"""
import pytest

import db
import pagamento_plataforma_service as pps
from factories import nova_organizacao, novo_usuario


class _SDKFalso:
    """Substitui `_sdk()` inteiro. `resposta_preapproval` é usada tanto por
    `.create()` quanto por `.get()`/`.update()` (chega o cenário mais comum:
    mesma resposta em qualquer chamada) — testes que precisam de respostas
    diferentes por chamada passam uma função em vez de dict."""

    def __init__(self, resposta_payment=None, resposta_preapproval=None):
        self._resposta_payment = resposta_payment
        self._resposta_preapproval = resposta_preapproval

    def payment(self):
        return _RecursoFalso(self._resposta_payment)

    def preapproval(self):
        return _RecursoFalso(self._resposta_preapproval)


class _RecursoFalso:
    def __init__(self, resposta):
        self._resposta = resposta

    def _resolver(self, *args, **kwargs):
        if callable(self._resposta):
            return self._resposta(*args, **kwargs)
        return self._resposta

    def create(self, data, request_options=None):
        return self._resolver("create", data)

    def get(self, id_, request_options=None):
        return self._resolver("get", id_)

    def update(self, id_, data, request_options=None):
        return self._resolver("update", id_, data)


class _RespostaHttpFalsa:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self.ok = ok

    def json(self):
        return self._payload


def _configurar_mercadopago_plataforma():
    db.salvar_config_integracao_plataforma(
        "mercadopago", {"access_token": "TOKEN-TESTE", "public_key": "PUBLIC-TESTE", "cobranca_automatica_ativa": True},
        status="conectado",
    )


def _novo_plano(codigo="starter", preco_centavos=14970):
    db.execute(
        "INSERT INTO planos (codigo, nome, preco_mensal_centavos) VALUES (?, ?, ?)",
        (codigo, codigo.capitalize(), preco_centavos),
    )


def _nova_org_ativa(nome, plano="starter"):
    org_id = nova_organizacao(nome, plano)
    db.execute("UPDATE organizacoes SET status_comercial = 'ativa' WHERE id = ?", (org_id,))
    return org_id


# ---------------------------------------------------------------- Correção do dedup (avulsa não esconde mensalidade)

def test_avulsa_no_mes_nao_impede_gerar_mensalidade(client, db_ctx, monkeypatch):
    _configurar_mercadopago_plataforma()
    org_id = _nova_org_ativa("Clínica Avulsa Antes")
    _novo_plano()

    # Cobrança avulsa já lançada este mês (ex: taxa de setup) — ANTES da
    # correção, isso fazia _ja_gerada_no_mes achar que a clínica já tinha
    # sido cobrada no mês, e a mensalidade nunca era gerada.
    pps.criar_cobranca_avulsa(org_id, 500, "Taxa de setup", gerar_pix_agora=False)

    monkeypatch.setattr(pps, "_sdk", lambda: _SDKFalso(
        resposta_payment={"status": 201, "response": {"id": 1, "status": "pending", "point_of_interaction": {"transaction_data": {}}}}
    ))

    resultado = pps.gerar_cobrancas_mensais()
    assert resultado["executado"] is True
    assert resultado["geradas"] == 1, resultado
    assert resultado["puladas"] == 0

    mensalidades = db.query(
        "SELECT * FROM cobrancas_planos WHERE organizacao_id = ? AND (descricao IS NULL OR descricao = '')",
        (org_id,),
    )
    assert len(mensalidades) == 1


def test_mensalidade_no_mes_nao_impede_avulsa(db_ctx):
    org_id = _nova_org_ativa("Clínica Mensalidade Antes")
    db.execute(
        "INSERT INTO cobrancas_planos (organizacao_id, plano_codigo, valor_centavos) VALUES (?, ?, ?)",
        (org_id, "starter", 14970),
    )
    # `_ja_gerada_no_mes` (usada só para a mensalidade) deve enxergar a
    # mensalidade normalmente...
    assert pps._ja_gerada_no_mes(org_id) is not None
    # ...mas criar uma avulsa no mesmo mês continua permitido (nunca foi
    # bloqueado por isso — só confirmando que a correção não mudou essa parte).
    resultado = pps.criar_cobranca_avulsa(org_id, 500, "Ajuste retroativo", gerar_pix_agora=False)
    assert resultado["id"]


def test_gerar_cobrancas_ainda_pula_clinica_ja_cobrada_no_mes(db_ctx, monkeypatch):
    """Continua funcionando: mensalidade já gerada este mês -> pula (o
    comportamento original de dedup, que não foi tocado pela correção)."""
    _configurar_mercadopago_plataforma()
    org_id = _nova_org_ativa("Clínica Já Cobrada")
    _novo_plano()
    db.execute(
        "INSERT INTO cobrancas_planos (organizacao_id, plano_codigo, valor_centavos) VALUES (?, ?, ?)",
        (org_id, "starter", 14970),
    )
    resultado = pps.gerar_cobrancas_mensais()
    assert resultado["geradas"] == 0
    assert resultado["puladas"] == 1


# ---------------------------------------------------------------- Ativar assinatura recorrente

def test_criar_assinatura_recorrente_sucesso(client, db_ctx, monkeypatch):
    org_id = _nova_org_ativa("Clínica Recorrente")
    gestor = novo_usuario(org_id, "Gestora", "gestora@recorrente.com", "gestor")
    _configurar_mercadopago_plataforma()
    _novo_plano()
    monkeypatch.setenv("URL_APP", "https://pandatech.pandacriacao.com.br")

    monkeypatch.setattr(pps, "_sdk", lambda: _SDKFalso(
        resposta_preapproval={"status": 201, "response": {"id": "PA-123", "init_point": "https://mercadopago.com/subscriptions/PA-123"}}
    ))

    resultado = pps.criar_assinatura_recorrente(org_id)
    assert resultado["checkout_url"] == "https://mercadopago.com/subscriptions/PA-123"

    assinatura = pps.assinatura_recorrente(org_id)
    assert assinatura["status"] == "pendente"
    assert assinatura["mp_preapproval_id"] == "PA-123"


def test_criar_assinatura_recorrente_sem_plano_pago_falha(db_ctx, monkeypatch):
    org_id = _nova_org_ativa("Clínica Sem Plano", plano="inexistente")
    _configurar_mercadopago_plataforma()
    monkeypatch.setenv("URL_APP", "https://pandatech.pandacriacao.com.br")

    with pytest.raises(pps.ErroPagamentoUsuario, match="plano pago"):
        pps.criar_assinatura_recorrente(org_id)


def test_criar_assinatura_recorrente_pendente_pode_ser_retomada(db_ctx, monkeypatch):
    """CORREÇÃO (15/09/2026, ver pagamento_plataforma_service.py): uma
    assinatura "pendente" (autorização iniciada e nunca concluída no
    Mercado Pago) não trava mais a clínica pra sempre — chamar de novo
    (o botão "Continuar autorização") gera uma nova pré-aprovação em vez
    de falhar. Substitui o antigo test_criar_assinatura_recorrente_duplicada_falha,
    que esperava o comportamento contrário (o bug que essa correção resolveu)."""
    org_id = _nova_org_ativa("Clínica Pendente Retomada")
    _configurar_mercadopago_plataforma()
    _novo_plano()
    monkeypatch.setenv("URL_APP", "https://pandatech.pandacriacao.com.br")
    monkeypatch.setattr(pps, "_sdk", lambda: _SDKFalso(
        resposta_preapproval={"status": 201, "response": {"id": "PA-1", "init_point": "https://x"}}
    ))
    pps.criar_assinatura_recorrente(org_id)

    monkeypatch.setattr(pps, "_sdk", lambda: _SDKFalso(
        resposta_preapproval={"status": 201, "response": {"id": "PA-2", "init_point": "https://y"}}
    ))
    resultado = pps.criar_assinatura_recorrente(org_id)
    assert resultado["checkout_url"] == "https://y"

    assinatura = pps.assinatura_recorrente(org_id)
    assert assinatura["status"] == "pendente"
    assert assinatura["mp_preapproval_id"] == "PA-2"


def test_criar_assinatura_recorrente_ativa_duplicada_falha(db_ctx, monkeypatch):
    """A trava continua valendo pra reativação de verdade: com assinatura
    já "ativa", criar_assinatura_recorrente ainda recusa."""
    org_id = _nova_org_ativa("Clínica Duplicada")
    _configurar_mercadopago_plataforma()
    _novo_plano()
    _preparar_assinatura_ativa(org_id)
    monkeypatch.setenv("URL_APP", "https://pandatech.pandacriacao.com.br")

    with pytest.raises(pps.ErroPagamentoUsuario, match="ativa"):
        pps.criar_assinatura_recorrente(org_id)


def test_rota_ativar_recorrente_gestor(client, db_ctx, monkeypatch):
    from conftest import autenticado

    org_id = _nova_org_ativa("Clínica Rota Ativar")
    gestor = novo_usuario(org_id, "Gestora", "gestora@rota.com", "gestor")
    _configurar_mercadopago_plataforma()
    _novo_plano()
    monkeypatch.setenv("URL_APP", "https://pandatech.pandacriacao.com.br")
    monkeypatch.setattr(pps, "_sdk", lambda: _SDKFalso(
        resposta_preapproval={"status": 201, "response": {"id": "PA-9", "init_point": "https://mercadopago.com/x"}}
    ))

    r = autenticado(client, gestor).post("/api/admin/assinatura/recorrente/ativar")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["checkout_url"] == "https://mercadopago.com/x"


# ---------------------------------------------------------------- Webhook: status da assinatura muda

def test_webhook_preapproval_autorizada_ativa_assinatura(db_ctx, monkeypatch):
    org_id = _nova_org_ativa("Clínica Webhook Preapproval")
    db.execute("UPDATE organizacoes SET status_comercial = 'inadimplente' WHERE id = ?", (org_id,))
    _configurar_mercadopago_plataforma()
    db.execute(
        "INSERT INTO assinaturas_cartao_recorrentes (organizacao_id, mp_preapproval_id, status, valor_centavos) VALUES (?, ?, 'pendente', ?)",
        (org_id, "PA-777", 14970),
    )
    monkeypatch.setattr(pps, "_sdk", lambda: _SDKFalso(
        resposta_preapproval={"status": 200, "response": {"status": "authorized"}}
    ))

    resultado = pps.processar_webhook_preapproval("PA-777")
    assert resultado["status"] == "ativa"

    assinatura = pps.assinatura_recorrente(org_id)
    assert assinatura["status"] == "ativa"
    org = db.query_one("SELECT status_comercial FROM organizacoes WHERE id = ?", (org_id,))
    assert org["status_comercial"] == "ativa"


def test_webhook_preapproval_desconhecido_ignora(db_ctx):
    resultado = pps.processar_webhook_preapproval("PA-NAO-EXISTE")
    assert resultado["ignorado"] is True


# ---------------------------------------------------------------- Webhook: cobrança recorrente de verdade

def _preparar_assinatura_ativa(org_id, preapproval_id="PA-1", valor_centavos=14970):
    db.execute(
        "INSERT INTO assinaturas_cartao_recorrentes (organizacao_id, mp_preapproval_id, status, valor_centavos) VALUES (?, ?, 'ativa', ?)",
        (org_id, preapproval_id, valor_centavos),
    )


def test_webhook_pagamento_recorrente_processado_cria_cobranca_paga(db_ctx, monkeypatch):
    org_id = _nova_org_ativa("Clínica Cobrança Recorrente")
    db.execute("UPDATE organizacoes SET status_comercial = 'inadimplente' WHERE id = ?", (org_id,))
    _configurar_mercadopago_plataforma()
    _preparar_assinatura_ativa(org_id)

    monkeypatch.setattr(pps.requests, "get", lambda *a, **k: _RespostaHttpFalsa(
        {"preapproval_id": "PA-1", "status": "processed", "transaction_amount": 149.70}
    ))

    resultado = pps.processar_webhook_pagamento_recorrente("AP-500")
    assert resultado["status"] == "pago"

    cobranca = db.query_one("SELECT * FROM cobrancas_planos WHERE mp_payment_id = ?", ("AP-500",))
    assert cobranca is not None
    assert cobranca["status"] == "pago"
    assert cobranca["forma_confirmacao"] == "mercadopago_cartao"
    assert cobranca["valor_centavos"] == 14970

    org = db.query_one("SELECT status_comercial FROM organizacoes WHERE id = ?", (org_id,))
    assert org["status_comercial"] == "ativa"


def test_webhook_pagamento_recorrente_e_idempotente(db_ctx, monkeypatch):
    org_id = _nova_org_ativa("Clínica Idempotente")
    _configurar_mercadopago_plataforma()
    _preparar_assinatura_ativa(org_id)
    monkeypatch.setattr(pps.requests, "get", lambda *a, **k: _RespostaHttpFalsa(
        {"preapproval_id": "PA-1", "status": "processed", "transaction_amount": 149.70}
    ))

    pps.processar_webhook_pagamento_recorrente("AP-DUP")
    resultado = pps.processar_webhook_pagamento_recorrente("AP-DUP")
    assert resultado.get("duplicado") is True

    cobrancas = db.query("SELECT * FROM cobrancas_planos WHERE mp_payment_id = ?", ("AP-DUP",))
    assert len(cobrancas) == 1


def test_webhook_pagamento_recorrente_recusado_cria_pix_fallback(db_ctx, monkeypatch):
    org_id = _nova_org_ativa("Clínica Cartão Recusado Recorrente")
    _configurar_mercadopago_plataforma()
    _novo_plano()
    _preparar_assinatura_ativa(org_id)

    monkeypatch.setattr(pps.requests, "get", lambda *a, **k: _RespostaHttpFalsa(
        {"preapproval_id": "PA-1", "status": "rejected"}
    ))
    # _criar_cobranca_fallback_recorrente_recusada também chama
    # criar_pagamento_pix (best-effort) pra já deixar o QR pronto no PIX de
    # fallback — mesmo SDK falso do resto do arquivo, agora respondendo a
    # sdk.payment().create().
    monkeypatch.setattr(pps, "_sdk", lambda: _SDKFalso(
        resposta_payment={"status": 201, "response": {"id": 42, "point_of_interaction": {"transaction_data": {}}}}
    ))

    resultado = pps.processar_webhook_pagamento_recorrente("AP-RECUSADO")
    assert resultado["status"] == "rejected"

    pendente = db.query_one(
        "SELECT * FROM cobrancas_planos WHERE organizacao_id = ? AND status = 'pendente'", (org_id,),
    )
    assert pendente is not None


def test_webhook_pagamento_recorrente_pending_nao_cria_cobranca(db_ctx, monkeypatch):
    org_id = _nova_org_ativa("Clínica Pending Recorrente")
    _configurar_mercadopago_plataforma()
    _preparar_assinatura_ativa(org_id)
    monkeypatch.setattr(pps.requests, "get", lambda *a, **k: _RespostaHttpFalsa(
        {"preapproval_id": "PA-1", "status": "pending"}
    ))

    pps.processar_webhook_pagamento_recorrente("AP-PENDING")
    cobrancas = db.query("SELECT * FROM cobrancas_planos WHERE organizacao_id = ?", (org_id,))
    assert len(cobrancas) == 0


# ---------------------------------------------------------------- Ciclo mensal pula quem tem assinatura ativa

def test_gerar_cobrancas_pula_clinica_com_assinatura_recorrente_ativa(db_ctx):
    _configurar_mercadopago_plataforma()
    org_id = _nova_org_ativa("Clínica Já em Recorrência")
    _novo_plano()
    _preparar_assinatura_ativa(org_id)

    resultado = pps.gerar_cobrancas_mensais()
    assert resultado["geradas"] == 0
    assert resultado["puladas"] == 1

    cobrancas = db.query("SELECT * FROM cobrancas_planos WHERE organizacao_id = ?", (org_id,))
    assert len(cobrancas) == 0  # nenhum PIX duplicado foi criado por cima da recorrência


def test_gerar_cobrancas_nao_pula_clinica_com_recorrencia_pendente(db_ctx, monkeypatch):
    """Só 'ativa' pula — 'pendente' (ainda não autorizada pelo Gestor) não
    conta como cobrança garantida, então o ciclo comum continua normal."""
    _configurar_mercadopago_plataforma()
    org_id = _nova_org_ativa("Clínica Recorrência Pendente")
    _novo_plano()
    db.execute(
        "INSERT INTO assinaturas_cartao_recorrentes (organizacao_id, mp_preapproval_id, status, valor_centavos) VALUES (?, NULL, 'pendente', ?)",
        (org_id, 14970),
    )
    monkeypatch.setattr(pps, "_sdk", lambda: _SDKFalso(
        resposta_payment={"status": 201, "response": {"id": 1, "status": "pending", "point_of_interaction": {"transaction_data": {}}}}
    ))

    resultado = pps.gerar_cobrancas_mensais()
    assert resultado["geradas"] == 1


# ---------------------------------------------------------------- Cancelar

def test_cancelar_assinatura_recorrente(db_ctx, monkeypatch):
    org_id = _nova_org_ativa("Clínica Cancelar Recorrente")
    _configurar_mercadopago_plataforma()
    _preparar_assinatura_ativa(org_id)
    chamada = {}

    def _update_falso(id_, data):
        chamada["id"] = id_
        chamada["data"] = data
        return {"status": 200, "response": {"status": "cancelled"}}

    monkeypatch.setattr(pps, "_sdk", lambda: _SDKFalso(resposta_preapproval=lambda op, *a: _update_falso(*a) if op == "update" else None))

    pps.cancelar_assinatura_recorrente(org_id)
    assert chamada["id"] == "PA-1"
    assert chamada["data"] == {"status": "cancelled"}

    assinatura = pps.assinatura_recorrente(org_id)
    assert assinatura["status"] == "cancelada"


def test_cancelar_sem_assinatura_ativa_falha(db_ctx):
    org_id = _nova_org_ativa("Clínica Sem Recorrência")
    with pytest.raises(pps.ErroPagamentoUsuario, match="Não há assinatura"):
        pps.cancelar_assinatura_recorrente(org_id)
