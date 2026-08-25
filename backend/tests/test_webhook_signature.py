"""
Regressão para a assinatura de webhook do Mercado Pago (correção de
auditoria, item 4.9 + correção de agosto/2026 sobre segredo por conta).

Teste puro de unidade — não precisa de Flask nem de banco de dados, só da
função de validação em si (backend/pagamento_service.py).
"""
import hashlib
import hmac

from pagamento_service import validar_assinatura_webhook


def _assinar(secret, data_id, request_id, ts):
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    return hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()


def test_assinatura_valida_e_aceita():
    ts = "1700000000"
    v1 = _assinar("segredo-da-clinica-a", "12345", "req-1", ts)
    x_signature = f"ts={ts},v1={v1}"
    assert validar_assinatura_webhook(x_signature, "req-1", "12345", "segredo-da-clinica-a") is True


def test_assinatura_de_outra_conta_e_rejeitada():
    """O achado original: um segredo global único não conseguia validar mais
    de uma conta de Mercado Pago. Aqui, uma assinatura gerada com o segredo
    da Clínica B nunca deve validar contra o segredo da Clínica A."""
    ts = "1700000000"
    v1_da_clinica_b = _assinar("segredo-da-clinica-b", "12345", "req-1", ts)
    x_signature = f"ts={ts},v1={v1_da_clinica_b}"
    assert validar_assinatura_webhook(x_signature, "req-1", "12345", "segredo-da-clinica-a") is False


def test_sem_segredo_configurado_falha_fechado():
    """Item 4.9: sem segredo configurado, o webhook deve ser RECUSADO
    (fail-closed), nunca aceito por padrão."""
    assert validar_assinatura_webhook("ts=1700000000,v1=qualquercoisa", "req-1", "12345", None) is False
    assert validar_assinatura_webhook("ts=1700000000,v1=qualquercoisa", "req-1", "12345", "") is False


def test_sem_header_de_assinatura_e_rejeitado():
    assert validar_assinatura_webhook(None, "req-1", "12345", "segredo-qualquer") is False
    assert validar_assinatura_webhook("", "req-1", "12345", "segredo-qualquer") is False


def test_header_malformado_e_rejeitado():
    assert validar_assinatura_webhook("formato-errado-sem-ts-nem-v1", "req-1", "12345", "segredo-qualquer") is False


def test_data_id_diferente_invalida_assinatura():
    """A assinatura é calculada sobre o data_id — reutilizar uma assinatura
    válida de OUTRO pagamento não deve colar."""
    ts = "1700000000"
    v1 = _assinar("segredo-da-clinica-a", "12345", "req-1", ts)
    x_signature = f"ts={ts},v1={v1}"
    assert validar_assinatura_webhook(x_signature, "req-1", "99999", "segredo-da-clinica-a") is False
