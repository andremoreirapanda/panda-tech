"""
Gateway de pagamento (PIX / cartão) — Doc 26 (Integration Layer) + Módulo 07
(Financeiro, "complementa, não substitui o ERP").

ATUALIZAÇÃO DESTA RODADA: integração REAL com o Mercado Pago (SDK oficial),
no lugar do botão "Marcar como pago" 100% manual que existia antes. Cada
clínica configura o próprio Access Token do Mercado Pago (obtido no painel
dela: https://www.mercadopago.com.br/developers/panel) — não é uma conta
única do SaaS recebendo por todas, é a clínica que recebe direto na conta
dela. Isso evita qualquer discussão de intermediação financeira/split.

Fluxo:
  1. Gestor cola o Access Token na Central de Integrações
     (`POST /api/integracoes/pagamento/config`).
  2. Ao criar uma cobrança, o Gestor/Responsável pode gerar um PIX real
     (`POST /api/financeiro/cobranca/<id>/gerar-pix`) — devolve QR code +
     "copia e cola".
  3. O Mercado Pago chama de volta `POST /api/integracoes/pagamento/webhook`
     quando o PIX é pago — a cobrança muda pra "pago" sozinha, sem ação
     manual de ninguém (isso é o ganho real sobre o botão manual antigo).
  4. Pagamento manual (dinheiro/transferência fora do app) continua existindo
     como opção — nem toda clínica vai quiser cobrar pelo app no piloto.

Chave secreta do webhook (gerada no painel do Mercado Pago, DE CADA CONTA,
em Suas integrações > [app] > Webhooks > Chave secreta) — usada para validar
a assinatura `x-signature` e ter certeza de que a notificação é mesmo do
Mercado Pago.

CORREÇÃO (agosto/2026): essa chave costumava vir de uma única variável de
ambiente global (MP_WEBHOOK_SECRET) — o que quebra assim que existe mais de
uma conta de Mercado Pago em jogo, porque o Mercado Pago gera uma chave
secreta DIFERENTE por aplicação/conta. Como cada clínica conecta a própria
conta (ver cabeçalho do módulo), uma única chave global só conseguia validar
os webhooks de UMA clínica — todas as outras eram recusadas (401,
fail-closed) e o pagamento nunca confirmava sozinho. Agora a chave secreta
é guardada junto com o access_token de cada clínica, na própria config
cifrada da integração (`integrações.configuracao_json`), e passada
explicitamente para `validar_assinatura_webhook`.
"""
import hashlib
import hmac
import os

from db import query_one, execute, log_evento, obter_config_integracao, salvar_config_integracao


def access_token_configurado(organizacao_id: int):
    config = obter_config_integracao(organizacao_id, "pagamento")
    return config.get("access_token")


def webhook_secret_configurado(organizacao_id: int):
    config = obter_config_integracao(organizacao_id, "pagamento")
    return config.get("webhook_secret")


def organizacao_id_por_payment_id(payment_id: str):
    """Descobre a organizacao_id (clínica) dona da cobrança a partir do
    payment_id que veio no webhook do Mercado Pago — precisa disso ANTES de
    validar a assinatura, porque cada clínica tem sua própria chave secreta
    (contas diferentes de Mercado Pago). Retorna None se não encontrar
    nenhuma cobrança com esse payment_id (nesse caso não há o que confirmar
    mesmo, então o webhook pode ser ignorado sem risco de segurança)."""
    cobranca = query_one("SELECT paciente_id FROM cobrancas WHERE mp_payment_id = ?", (str(payment_id),))
    if not cobranca:
        return None
    paciente = query_one("SELECT organizacao_id FROM pacientes WHERE id = ?", (cobranca["paciente_id"],))
    return paciente["organizacao_id"] if paciente else None


def salvar_access_token(organizacao_id: int, access_token: str, public_key: str = None, webhook_secret: str = None):
    config = {"access_token": access_token, "public_key": public_key}
    if webhook_secret:
        config["webhook_secret"] = webhook_secret
    else:
        # Campo deixado em branco no formulário: preserva uma chave de
        # webhook já salva antes, em vez de apagá-la sempre que o Gestor só
        # quiser atualizar o Access Token.
        anterior = obter_config_integracao(organizacao_id, "pagamento")
        if anterior.get("webhook_secret"):
            config["webhook_secret"] = anterior["webhook_secret"]
    salvar_config_integracao(
        organizacao_id, "pagamento", config,
        status="conectado" if access_token else "desconectado",
    )


def _sdk(organizacao_id: int):
    import mercadopago

    token = access_token_configurado(organizacao_id)
    if not token:
        return None
    return mercadopago.SDK(token)


def criar_pagamento_pix(cobranca_id: int):
    """Cria uma cobrança PIX real no Mercado Pago para a `cobranca_id` informada.
    Retorna dict com qr_code / qr_code_base64 / ticket_url, ou levanta
    RuntimeError com uma mensagem segura para mostrar ao usuário."""
    cobranca = query_one(
        """SELECT c.*, p.organizacao_id, p.nome as paciente_nome
           FROM cobrancas c JOIN pacientes p ON p.id = c.paciente_id WHERE c.id = ?""",
        (cobranca_id,),
    )
    if not cobranca:
        raise RuntimeError("Cobrança não encontrada.")

    sdk = _sdk(cobranca["organizacao_id"])
    if not sdk:
        raise RuntimeError("Esta clínica ainda não configurou o gateway de pagamento (Mercado Pago).")

    # Responsável financeiro (para o campo obrigatório `payer.email`) — usa o
    # e-mail de qualquer responsável vinculado ao paciente; cai para um
    # e-mail genérico se por algum motivo não existir (não deveria acontecer,
    # cadastro de paciente exige responsável).
    responsavel = query_one(
        """SELECT u.email FROM responsaveis_pacientes rp JOIN usuarios u ON u.id = rp.usuario_id
           WHERE rp.paciente_id = ? LIMIT 1""",
        (cobranca["paciente_id"],),
    )
    payer_email = (responsavel or {}).get("email") or "familia@encantoemcasa.com"

    payment_data = {
        "transaction_amount": round(cobranca["valor_centavos"] / 100, 2),
        "description": f"{cobranca['descricao']} — {cobranca['paciente_nome']}",
        "payment_method_id": "pix",
        "payer": {"email": payer_email},
        "external_reference": f"cobranca-{cobranca_id}",
        "notification_url": os.environ.get("MP_NOTIFICATION_URL") or None,
    }
    request_options = None
    try:
        from mercadopago.config import RequestOptions
        # connection_timeout/max_retries baixos: preferimos falhar rápido e
        # mostrar um erro claro ao gestor a deixar a requisição pendurada
        # (o padrão do SDK é 60s x 3 tentativas = até 3 minutos).
        request_options = RequestOptions(
            custom_headers={"X-Idempotency-Key": f"cobranca-{cobranca_id}-pix"},
            connection_timeout=15.0, max_retries=1,
        )
    except ImportError:
        pass  # versões mais antigas do SDK não têm RequestOptions — segue sem idempotency key

    try:
        resultado = sdk.payment().create(payment_data, request_options) if request_options else sdk.payment().create(payment_data)
    except RuntimeError:
        raise
    except Exception as exc:
        # Falha de rede/timeout/erro inesperado do SDK — nunca deixa vazar
        # como 500 cru pro frontend; vira uma mensagem que dá pra mostrar
        # ao gestor (e fica registrada no evento abaixo teria ido, mas aqui
        # nem chegamos a criar o pagamento).
        raise RuntimeError(f"Não foi possível falar com o Mercado Pago agora ({exc.__class__.__name__}). Tente novamente em instantes.") from exc

    resposta = resultado.get("response", {})
    if resultado.get("status") not in (200, 201):
        raise RuntimeError(f"Mercado Pago recusou a cobrança: {resposta.get('message', 'erro desconhecido')}")

    poi = resposta.get("point_of_interaction", {}).get("transaction_data", {})
    execute(
        """UPDATE cobrancas SET mp_payment_id = ?, pix_qr_code = ?, pix_qr_code_base64 = ?, pix_copia_cola = ?
           WHERE id = ?""",
        (str(resposta.get("id")), poi.get("qr_code"), poi.get("qr_code_base64"), poi.get("qr_code"), cobranca_id),
    )
    log_evento(cobranca["organizacao_id"], "pix_gerado", "cobranca", cobranca_id, cobranca["paciente_id"])
    return {
        "mp_payment_id": resposta.get("id"),
        "qr_code": poi.get("qr_code"),
        "qr_code_base64": poi.get("qr_code_base64"),
        "ticket_url": resposta.get("point_of_interaction", {}).get("transaction_data", {}).get("ticket_url"),
        "status": resposta.get("status"),
    }


def validar_assinatura_webhook(x_signature: str, x_request_id: str, data_id: str, secret: str) -> bool:
    """Valida a assinatura HMAC-SHA256 do webhook (docs Mercado Pago:
    'Como validar notificações webhook').

    `secret` é a chave secreta ESPECÍFICA da conta de Mercado Pago que deve
    ter gerado essa notificação (de uma clínica, ou da própria plataforma)
    — quem chama esta função é responsável por descobrir qual chave usar
    antes (ver `organizacao_id_por_payment_id` / `webhook_secret_configurado`
    aqui, e `pagamento_plataforma_service.webhook_secret_configurado` para o
    lado da plataforma).

    Correção de auditoria (item 4.9): antes, se a chave não estivesse
    configurada, a validação era pulada por completo (retornava True
    incondicionalmente) — qualquer POST não autenticado era aceito como se
    fosse do Mercado Pago. O dano real já era limitado, porque
    `processar_webhook` (deste módulo e de pagamento_plataforma_service.py)
    sempre reconfirma o status direto na API do Mercado Pago antes de dar
    baixa — mas essa camada de defesa não deveria ser opcional. Agora, sem a
    chave configurada, o webhook é recusado (fail-closed) em vez de aceito.

    Correção (agosto/2026): a chave costumava vir de uma única variável de
    ambiente global — o que quebra assim que existe mais de uma conta de
    Mercado Pago (cada clínica + a própria Panda Tech). Agora ela é sempre
    passada como parâmetro, resolvida por conta antes da chamada.
    """
    if not secret:
        return False
    if not x_signature:
        return False
    partes = dict(p.split("=", 1) for p in x_signature.split(",") if "=" in p)
    ts, v1 = partes.get("ts"), partes.get("v1")
    if not ts or not v1:
        return False
    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
    assinatura_calculada = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(assinatura_calculada, v1)


def processar_webhook(payment_id: str, organizacao_id: int = None):
    """Busca o pagamento no Mercado Pago pelo id recebido no webhook e, se
    aprovado, confirma a cobrança correspondente. Idempotente: chamar duas
    vezes para o mesmo pagamento aprovado não duplica a linha em `pagamentos`."""
    cobranca = query_one("SELECT * FROM cobrancas WHERE mp_payment_id = ?", (str(payment_id),))
    if not cobranca:
        return {"ignorado": True, "motivo": "cobrança não encontrada para este payment_id"}

    paciente = query_one("SELECT organizacao_id FROM pacientes WHERE id = ?", (cobranca["paciente_id"],))
    sdk = _sdk(paciente["organizacao_id"])
    if not sdk:
        return {"ignorado": True, "motivo": "integração desconectada"}

    try:
        from mercadopago.config import RequestOptions
        opcoes = RequestOptions(connection_timeout=15.0, max_retries=1)
        resultado = sdk.payment().get(payment_id, opcoes)
    except Exception as exc:
        log_evento(paciente["organizacao_id"], "webhook_mercadopago_falhou", "cobranca", cobranca["id"], cobranca["paciente_id"], {"erro": str(exc)})
        return {"ignorado": True, "motivo": f"erro ao consultar o Mercado Pago: {exc.__class__.__name__}"}
    pagamento = resultado.get("response", {})
    status = pagamento.get("status")

    if status == "approved" and cobranca["status"] != "pago":
        ja_registrado = query_one("SELECT 1 FROM pagamentos WHERE cobranca_id = ? AND forma = 'pix'", (cobranca["id"],))
        if not ja_registrado:
            execute(
                "INSERT INTO pagamentos (cobranca_id, valor_centavos, forma) VALUES (?, ?, 'pix')",
                (cobranca["id"], cobranca["valor_centavos"]),
            )
        execute("UPDATE cobrancas SET status = 'pago' WHERE id = ?", (cobranca["id"],))
        log_evento(paciente["organizacao_id"], "pagamento_confirmado", "cobranca", cobranca["id"], cobranca["paciente_id"], {"origem": "mercadopago_webhook"})
        return {"ok": True, "status": "pago"}

    return {"ok": True, "status": status}
