"""
Gateway de pagamento da PLATAFORMA (Panda Tech cobrando as clínicas pela
assinatura do plano) — irmão de `pagamento_service.py` (que é a clínica
cobrando as famílias), mas com escopo, credencial e tabela próprios:

  - Credencial: a da própria Panda Tech, salva em `integracoes_plataforma`
    (tipo "mercadopago") via Admin > Integrações — uma conta só, não uma por
    clínica (aqui faz sentido, é a Panda Tech recebendo).
  - Cobranças: tabela `cobrancas_planos` (organizacao_id + plano_codigo +
    valor_centavos), separada de `cobrancas`/`pagamentos` (que são a clínica
    cobrando as famílias).

Cobrança automática tem um interruptor mestre (`cobranca_automatica_ativa`,
guardado dentro da própria config do Mercado Pago da plataforma): enquanto
estiver desligado — o padrão —, `gerar_cobrancas_mensais()` não cria cobrança
nenhuma, nem pelo cron nem pelo botão "Gerar cobranças agora" do Admin. Isso
é proposital: nenhuma clínica deve começar a ser cobrada de verdade sem uma
decisão explícita do administrador da plataforma.

Fluxo (quando ligado):
  1. `gerar_cobrancas_mensais()` roda (via cron mensal ou botão manual no
     Admin) — para cada clínica com status comercial "ativa" ou
     "inadimplente", cria (se ainda não existir uma para o mês corrente) uma
     linha em `cobrancas_planos` com o preço atual do plano dela, e já tenta
     gerar o PIX correspondente na hora (best-effort — se a geração do PIX
     falhar, a cobrança fica registrada mesmo assim, só sem QR code ainda;
     dá pra gerar depois pelo botão).
  2. O Mercado Pago chama de volta `POST /api/admin/integracoes/pagamento/webhook`
     quando o PIX é pago — a cobrança muda pra "pago" sozinha. Se a clínica
     estava "inadimplente", volta pra "ativa" automaticamente.
  3. Confirmação manual (`marcar_pago_manual`) continua existindo como
     fallback, para quando o pagamento chegou fora do app.
"""
import os

from db import (
    query, query_one, execute, log_evento, log_auditoria, hoje_sql,
    obter_config_integracao_plataforma, salvar_config_integracao_plataforma,
)


def _config():
    return obter_config_integracao_plataforma("mercadopago")


def access_token_configurado():
    return _config().get("access_token")


def cobranca_automatica_ativa() -> bool:
    return bool(_config().get("cobranca_automatica_ativa", False))


def definir_cobranca_automatica(ativa: bool):
    """Liga/desliga o interruptor mestre. Não deixa ligar sem credencial
    configurada — não faz sentido "ativar cobrança" sem ter como cobrar."""
    cfg = _config()
    if ativa and not cfg.get("access_token"):
        raise ValueError("Configure o Access Token do Mercado Pago da Panda Tech antes de ativar a cobrança automática.")
    cfg["cobranca_automatica_ativa"] = bool(ativa)
    salvar_config_integracao_plataforma("mercadopago", cfg, status="conectado" if cfg.get("access_token") else "desconectado")


def _sdk():
    import mercadopago

    token = access_token_configurado()
    if not token:
        return None
    return mercadopago.SDK(token)


def _plano_por_codigo(codigo):
    return query_one("SELECT * FROM planos WHERE codigo = ?", (codigo,))


def _email_cobranca(org):
    """E-mail usado no campo obrigatório `payer.email` do Mercado Pago — o
    contato comercial da clínica, senão o e-mail de login do Gestor, senão
    um genérico (nunca deixa a geração do PIX falhar por falta de e-mail)."""
    if org.get("contato_email"):
        return org["contato_email"]
    gestor = query_one(
        "SELECT email FROM usuarios WHERE organizacao_id = ? AND papel = 'gestor' ORDER BY id LIMIT 1",
        (org["id"],),
    )
    return (gestor or {}).get("email") or "financeiro@pandacriacao.com.br"


def _ja_gerada_no_mes(organizacao_id):
    """Evita duplicar cobrança: já existe uma (pendente ou paga — cancelada
    não conta) pra essa clínica dentro do mês corrente?"""
    return query_one(
        """SELECT id FROM cobrancas_planos
           WHERE organizacao_id = ? AND status != 'cancelada' AND substr(criado_em, 1, 7) = substr(?, 1, 7)""",
        (organizacao_id, hoje_sql()),
    )


def gerar_cobrancas_mensais():
    """Ponto de entrada único, chamado tanto pelo cron mensal
    (`gerar_cobrancas_planos_mensal.py`) quanto pelo botão "Gerar cobranças
    agora" no Admin — de propósito o mesmo caminho, sem atalho que ignore o
    interruptor mestre: enquanto ele estiver desligado, nada é cobrado."""
    if not cobranca_automatica_ativa():
        return {"executado": False, "motivo": "Cobrança automática está desativada em Admin > Integrações.", "geradas": 0, "puladas": 0, "erros": []}

    clinicas = query("SELECT * FROM organizacoes WHERE status_comercial IN ('ativa', 'inadimplente')")
    geradas, puladas, erros = 0, 0, []

    for org in clinicas:
        if _ja_gerada_no_mes(org["id"]):
            puladas += 1
            continue
        plano = _plano_por_codigo(org["plano"])
        if not plano or not plano.get("preco_mensal_centavos"):
            puladas += 1
            continue

        cobranca_id = execute(
            "INSERT INTO cobrancas_planos (organizacao_id, plano_codigo, valor_centavos) VALUES (?, ?, ?)",
            (org["id"], org["plano"], plano["preco_mensal_centavos"]),
        )
        log_evento(org["id"], "cobranca_plano_gerada", "cobranca_plano", cobranca_id, payload={"valor_centavos": plano["preco_mensal_centavos"]})
        geradas += 1

        try:
            criar_pagamento_pix(cobranca_id)
        except RuntimeError as exc:
            # A cobrança já foi criada e fica registrada mesmo se o PIX
            # falhar agora — dá pra gerar depois pelo botão "Gerar PIX".
            erros.append({"organizacao_id": org["id"], "organizacao_nome": org["nome"], "erro": str(exc)})

    return {"executado": True, "geradas": geradas, "puladas": puladas, "erros": erros}


def criar_pagamento_pix(cobranca_id: int):
    """Cria o PIX real no Mercado Pago (conta da própria Panda Tech) para a
    `cobranca_id` (linha de `cobrancas_planos`) informada."""
    cobranca = query_one(
        """SELECT cp.*, o.nome as organizacao_nome, o.contato_email, o.id as org_id
           FROM cobrancas_planos cp JOIN organizacoes o ON o.id = cp.organizacao_id WHERE cp.id = ?""",
        (cobranca_id,),
    )
    if not cobranca:
        raise RuntimeError("Cobrança não encontrada.")
    if cobranca["status"] == "pago":
        raise RuntimeError("Esta cobrança já está paga.")

    sdk = _sdk()
    if not sdk:
        raise RuntimeError("A Panda Tech ainda não configurou o gateway de pagamento (Mercado Pago) em Admin > Integrações.")

    org = query_one("SELECT * FROM organizacoes WHERE id = ?", (cobranca["org_id"],))
    payer_email = _email_cobranca(org)
    plano = _plano_por_codigo(cobranca["plano_codigo"])
    nome_plano = plano["nome"] if plano else cobranca["plano_codigo"]

    payment_data = {
        "transaction_amount": round(cobranca["valor_centavos"] / 100, 2),
        "description": f"Assinatura Panda Tech — Plano {nome_plano} — {cobranca['organizacao_nome']}",
        "payment_method_id": "pix",
        "payer": {"email": payer_email},
        "external_reference": f"cobranca-plano-{cobranca_id}",
        "notification_url": os.environ.get("MP_PLATAFORMA_NOTIFICATION_URL") or os.environ.get("MP_NOTIFICATION_URL") or None,
    }
    request_options = None
    try:
        from mercadopago.config import RequestOptions
        request_options = RequestOptions(
            custom_headers={"X-Idempotency-Key": f"cobranca-plano-{cobranca_id}-pix"},
            connection_timeout=15.0, max_retries=1,
        )
    except ImportError:
        pass

    try:
        resultado = sdk.payment().create(payment_data, request_options) if request_options else sdk.payment().create(payment_data)
    except Exception as exc:
        raise RuntimeError(f"Não foi possível falar com o Mercado Pago agora ({exc.__class__.__name__}). Tente novamente em instantes.") from exc

    resposta = resultado.get("response", {})
    if resultado.get("status") not in (200, 201):
        raise RuntimeError(f"Mercado Pago recusou a cobrança: {resposta.get('message', 'erro desconhecido')}")

    poi = resposta.get("point_of_interaction", {}).get("transaction_data", {})
    execute(
        """UPDATE cobrancas_planos SET mp_payment_id = ?, pix_qr_code = ?, pix_qr_code_base64 = ?, pix_copia_cola = ?
           WHERE id = ?""",
        (str(resposta.get("id")), poi.get("qr_code"), poi.get("qr_code_base64"), poi.get("qr_code"), cobranca_id),
    )
    log_evento(cobranca["org_id"], "pix_gerado_plano", "cobranca_plano", cobranca_id)
    return {
        "mp_payment_id": resposta.get("id"),
        "qr_code": poi.get("qr_code"),
        "qr_code_base64": poi.get("qr_code_base64"),
        "status": resposta.get("status"),
    }


def processar_webhook(payment_id: str):
    """Idempotente — chamar duas vezes para o mesmo pagamento aprovado não
    tem efeito colateral extra na segunda vez."""
    cobranca = query_one("SELECT * FROM cobrancas_planos WHERE mp_payment_id = ?", (str(payment_id),))
    if not cobranca:
        return {"ignorado": True, "motivo": "cobrança de plano não encontrada para este payment_id"}

    sdk = _sdk()
    if not sdk:
        return {"ignorado": True, "motivo": "integração desconectada"}

    try:
        from mercadopago.config import RequestOptions
        opcoes = RequestOptions(connection_timeout=15.0, max_retries=1)
        resultado = sdk.payment().get(payment_id, opcoes)
    except Exception as exc:
        log_evento(cobranca["organizacao_id"], "webhook_mercadopago_plano_falhou", "cobranca_plano", cobranca["id"], payload={"erro": str(exc)})
        return {"ignorado": True, "motivo": f"erro ao consultar o Mercado Pago: {exc.__class__.__name__}"}

    pagamento = resultado.get("response", {})
    status = pagamento.get("status")

    if status == "approved" and cobranca["status"] != "pago":
        execute(
            "UPDATE cobrancas_planos SET status = 'pago', forma_confirmacao = 'mercadopago_pix', pago_em = ? WHERE id = ?",
            (hoje_sql(), cobranca["id"]),
        )
        org = query_one("SELECT status_comercial FROM organizacoes WHERE id = ?", (cobranca["organizacao_id"],))
        if org and org["status_comercial"] == "inadimplente":
            execute("UPDATE organizacoes SET status_comercial = 'ativa' WHERE id = ?", (cobranca["organizacao_id"],))
        log_evento(cobranca["organizacao_id"], "cobranca_plano_paga", "cobranca_plano", cobranca["id"], payload={"origem": "mercadopago_webhook"})
        return {"ok": True, "status": "pago"}

    return {"ok": True, "status": status}


def marcar_pago_manual(cobranca_id: int, usuario_id: int):
    cobranca = query_one("SELECT * FROM cobrancas_planos WHERE id = ?", (cobranca_id,))
    if not cobranca:
        raise RuntimeError("Cobrança não encontrada.")
    if cobranca["status"] == "pago":
        raise RuntimeError("Esta cobrança já está paga.")
    execute(
        "UPDATE cobrancas_planos SET status = 'pago', forma_confirmacao = 'manual', pago_em = ? WHERE id = ?",
        (hoje_sql(), cobranca_id),
    )
    org = query_one("SELECT status_comercial FROM organizacoes WHERE id = ?", (cobranca["organizacao_id"],))
    if org and org["status_comercial"] == "inadimplente":
        execute("UPDATE organizacoes SET status_comercial = 'ativa' WHERE id = ?", (cobranca["organizacao_id"],))
    log_auditoria(cobranca["organizacao_id"], usuario_id, "confirmar_pagamento_manual", "cobranca_plano", cobranca_id, "Pagamento manual (fora do app)")
    log_evento(cobranca["organizacao_id"], "cobranca_plano_paga", "cobranca_plano", cobranca_id, payload={"origem": "manual"})
