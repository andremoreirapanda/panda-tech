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
    criar_notificacao,
)
import whatsapp_service


def _config():
    return obter_config_integracao_plataforma("mercadopago")


def access_token_configurado():
    return _config().get("access_token")


def webhook_secret_configurado():
    """Chave secreta do webhook da conta de Mercado Pago da PRÓPRIA Panda
    Tech — separada da chave de cada clínica (ver pagamento_service.py),
    porque é uma conta de Mercado Pago diferente."""
    return _config().get("webhook_secret")


def public_key_configurado():
    """Public Key da conta de Mercado Pago da própria Panda Tech — ao
    contrário do Access Token, não é secreta (é feita pra rodar no
    navegador): o frontend usa ela pra inicializar o Card Payment Brick na
    tela "Sua Assinatura" do Gestor (ver `minha_assinatura` em admin_bp.py)."""
    return _config().get("public_key")


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


def notificacoes_ativas() -> dict:
    """Preferências de como o Gestor é avisado quando uma cobrança de plano
    é gerada (ou paga) — o Admin escolhe em Admin > Integrações. Sininho
    (notificação interna) vem ligado por padrão, assim que a cobrança
    automática é usada, porque não depende de nada externo; WhatsApp vem
    desligado por padrão porque só entrega de fato se a clínica tiver
    trocado mensagem com o WhatsApp da Panda Tech nas últimas 24h."""
    cfg = _config()
    return {
        "sininho": bool(cfg.get("notificar_sininho", True)),
        "whatsapp": bool(cfg.get("notificar_whatsapp", False)),
    }


def definir_notificacoes(sininho: bool, whatsapp: bool):
    cfg = _config()
    cfg["notificar_sininho"] = bool(sininho)
    cfg["notificar_whatsapp"] = bool(whatsapp)
    salvar_config_integracao_plataforma("mercadopago", cfg, status="conectado" if cfg.get("access_token") else "desconectado")


def _telefone_contato(org):
    return org.get("contato_telefone") or org.get("telefone") or ""


def _notificar_gestores(org_id, titulo, mensagem, tipo="financeiro"):
    """Insere uma notificação (sininho) para todo usuário com papel Gestor
    da clínica — normalmente é um só, mas nada impede mais de um.

    `entidade="assinatura"` (sem entidade_id — não há uma tela por-cobrança
    pra levar o clique, só a Central de Configurações > Sua Assinatura,
    onde ficam TODAS as cobranças pendentes) é o que o frontend usa pra
    saber pra onde levar o clique nessa notificação."""
    gestores = query("SELECT id FROM usuarios WHERE organizacao_id = ? AND papel = 'gestor'", (org_id,))
    for gestor in gestores:
        criar_notificacao(gestor["id"], titulo, mensagem, tipo=tipo, entidade="assinatura")


def _notificar_whatsapp(org, mensagem):
    """Melhor esforço — nunca levanta exceção (mesma postura defensiva de
    whatsapp_service.enviar_lembrete_*): se o WhatsApp da plataforma não
    estiver configurado, se o telefone da clínica estiver vazio, ou se a
    Meta recusar (fora da janela de 24h, por exemplo), só fica registrado
    como evento — não pode derrubar a geração da cobrança."""
    if not whatsapp_service.configurado_plataforma():
        return
    telefone = _telefone_contato(org)
    if not telefone:
        return
    try:
        whatsapp_service.enviar_texto_livre_plataforma(telefone, mensagem)
        log_evento(org["id"], "whatsapp_cobranca_plano_enviado", "organizacao", org["id"])
    except Exception as exc:
        log_evento(org["id"], "whatsapp_cobranca_plano_falhou", "organizacao", org["id"], payload={"erro": str(exc)})


def _notificar_cobranca_gerada(org, valor_centavos, plano_nome, descricao=None):
    """`descricao` só vem preenchida para cobrança avulsa (criar_cobranca_avulsa)
    — nesse caso a mensagem fala da descrição digitada pelo Admin em vez de
    tratar como se fosse a mensalidade do plano."""
    prefs = notificacoes_ativas()
    valor_fmt = f"R$ {valor_centavos / 100:.2f}".replace(".", ",")
    if descricao:
        titulo = "Nova cobrança da Panda Tech"
        msg_sininho = f"{descricao} ({valor_fmt}) — veja o PIX em Configurações > Sua Assinatura."
        msg_whatsapp = f"Panda Tech: uma nova cobrança — {descricao} ({valor_fmt}) — foi gerada. Acesse o app em Configurações > Sua Assinatura pra ver o PIX e pagar."
    else:
        titulo = "Nova cobrança da sua assinatura"
        msg_sininho = f"O plano {plano_nome} ({valor_fmt}/mês) gerou uma cobrança. Veja o PIX em Configurações > Sua Assinatura."
        msg_whatsapp = f"Panda Tech: uma nova cobrança de {valor_fmt} da sua assinatura (plano {plano_nome}) foi gerada. Acesse o app em Configurações > Sua Assinatura pra ver o PIX e pagar."
    if prefs["sininho"]:
        _notificar_gestores(org["id"], titulo, msg_sininho)
    if prefs["whatsapp"]:
        _notificar_whatsapp(org, msg_whatsapp)


def _notificar_pagamento_confirmado(org_id):
    prefs = notificacoes_ativas()
    if not prefs["sininho"]:
        return
    _notificar_gestores(org_id, "Pagamento confirmado", "Recebemos o pagamento da sua assinatura — obrigado! Sua clínica está em dia.")


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
        _notificar_cobranca_gerada(org, plano["preco_mensal_centavos"], plano["nome"])
        geradas += 1

        try:
            criar_pagamento_pix(cobranca_id)
        except RuntimeError as exc:
            # A cobrança já foi criada e fica registrada mesmo se o PIX
            # falhar agora — dá pra gerar depois pelo botão "Gerar PIX".
            erros.append({"organizacao_id": org["id"], "organizacao_nome": org["nome"], "erro": str(exc)})

    return {"executado": True, "geradas": geradas, "puladas": puladas, "erros": erros}


def criar_cobranca_avulsa(organizacao_id: int, valor_centavos: int, descricao: str, gerar_pix_agora: bool = True):
    """Cobrança pontual da Panda Tech para UMA clínica específica, fora do
    ciclo mensal — ex: taxa de setup, ajuste retroativo, cobrança combinada
    à parte da mensalidade. Diferente de `gerar_cobrancas_mensais()`:

      - Não passa pelo interruptor "Cobrança automática" (Admin >
        Integrações) — é uma ação explícita do Admin, não um job automático.
      - Não é bloqueada por `_ja_gerada_no_mes` — nada impede uma clínica
        de ter, no mesmo mês, a mensalidade normal E uma cobrança avulsa.
      - `valor_centavos` é o valor digitado pelo Admin, não o preço do
        plano; `plano_codigo` é gravado só como referência (é NOT NULL na
        tabela), sem afetar o valor cobrado.

    Levanta ValueError em validações de entrada (repassado pela rota como
    400) e RuntimeError se a clínica não existir (repassado como 404)."""
    if not isinstance(valor_centavos, int) or valor_centavos <= 0:
        raise ValueError("Informe um valor em centavos maior que zero.")
    descricao = (descricao or "").strip()
    if not descricao:
        raise ValueError("Informe uma descrição para a cobrança avulsa.")

    org = query_one("SELECT * FROM organizacoes WHERE id = ?", (organizacao_id,))
    if not org:
        raise RuntimeError("Clínica não encontrada.")

    cobranca_id = execute(
        "INSERT INTO cobrancas_planos (organizacao_id, plano_codigo, valor_centavos, descricao) VALUES (?, ?, ?, ?)",
        (org["id"], org["plano"], valor_centavos, descricao),
    )
    log_evento(org["id"], "cobranca_plano_avulsa_gerada", "cobranca_plano", cobranca_id,
               payload={"valor_centavos": valor_centavos, "descricao": descricao})
    _notificar_cobranca_gerada(org, valor_centavos, None, descricao=descricao)

    resultado = {"id": cobranca_id, "pix": None, "erro_pix": None}
    if gerar_pix_agora:
        try:
            resultado["pix"] = criar_pagamento_pix(cobranca_id)
        except RuntimeError as exc:
            # A cobrança fica registrada mesmo se o PIX falhar agora — dá
            # pra gerar depois pelo botão "Gerar PIX" já existente na lista.
            resultado["erro_pix"] = str(exc)
    return resultado


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
    # Cobrança avulsa (tem `descricao` preenchida) usa o texto digitado pelo
    # Admin no PIX, em vez de descrevê-la como se fosse a mensalidade do plano.
    descricao_pix = cobranca.get("descricao") or f"Assinatura Panda Tech — Plano {nome_plano}"

    payment_data = {
        "transaction_amount": round(cobranca["valor_centavos"] / 100, 2),
        "description": f"{descricao_pix} — {cobranca['organizacao_nome']}",
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


def criar_pagamento_cartao(cobranca_id: int, token: str, payment_method_id: str, installments: int,
                            payer_email: str, payer_identification: dict = None, issuer_id: str = None):
    """Cobra uma cobrança de plano no cartão de crédito (Fase 1 do plano de
    cobrança por cartão) — irmã de `criar_pagamento_pix`, mas com o cartão
    tokenizado no navegador do próprio Gestor pelo Card Payment Brick (ver
    frontend/js/views/financeiro.js). O número do cartão nunca passa pelo
    nosso servidor — só o `token` de uso único que o Brick já entrega.

    Diferente do PIX (que fica "pendente" até a família escanear o QR code),
    o cartão aprova (ou recusa) de forma síncrona na própria resposta desta
    chamada — por isso, ao contrário de `criar_pagamento_pix`, esta função já
    confirma o pagamento na hora quando aprovado, sem depender só do webhook
    (o webhook continua batendo depois, como confirmação redundante e
    idempotente — não tem problema nenhum ele chegar de qualquer forma)."""
    cobranca = query_one(
        """SELECT cp.*, o.nome as organizacao_nome, o.id as org_id
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

    plano = _plano_por_codigo(cobranca["plano_codigo"])
    nome_plano = plano["nome"] if plano else cobranca["plano_codigo"]
    descricao_pagamento = cobranca.get("descricao") or f"Assinatura Panda Tech — Plano {nome_plano}"

    payer = {"email": payer_email}
    if payer_identification and payer_identification.get("type") and payer_identification.get("number"):
        payer["identification"] = {
            "type": payer_identification["type"],
            "number": payer_identification["number"],
        }

    payment_data = {
        "transaction_amount": round(cobranca["valor_centavos"] / 100, 2),
        "description": f"{descricao_pagamento} — {cobranca['organizacao_nome']}",
        "token": token,
        "payment_method_id": payment_method_id,
        "installments": int(installments) if installments else 1,
        "payer": payer,
        "external_reference": f"cobranca-plano-{cobranca_id}",
        "notification_url": os.environ.get("MP_PLATAFORMA_NOTIFICATION_URL") or os.environ.get("MP_NOTIFICATION_URL") or None,
    }
    if issuer_id:
        payment_data["issuer_id"] = issuer_id

    request_options = None
    try:
        from mercadopago.config import RequestOptions
        request_options = RequestOptions(
            custom_headers={"X-Idempotency-Key": f"cobranca-plano-{cobranca_id}-cartao"},
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
        raise RuntimeError(f"Mercado Pago recusou o cartão: {resposta.get('message', 'erro desconhecido')}")

    status_pagamento = resposta.get("status")
    mp_payment_id = str(resposta.get("id")) if resposta.get("id") else None

    if status_pagamento == "rejected":
        motivo = resposta.get("status_detail", "cartão recusado")
        log_evento(cobranca["org_id"], "cobranca_plano_cartao_recusado", "cobranca_plano", cobranca_id, payload={"status_detail": motivo})
        raise RuntimeError("O cartão foi recusado pela operadora. Confira os dados ou tente outro cartão.")

    execute("UPDATE cobrancas_planos SET mp_payment_id = ? WHERE id = ?", (mp_payment_id, cobranca_id))

    if status_pagamento == "approved":
        execute(
            "UPDATE cobrancas_planos SET status = 'pago', forma_confirmacao = 'mercadopago_cartao', pago_em = ? WHERE id = ?",
            (hoje_sql(), cobranca_id),
        )
        org = query_one("SELECT status_comercial FROM organizacoes WHERE id = ?", (cobranca["org_id"],))
        if org and org["status_comercial"] == "inadimplente":
            execute("UPDATE organizacoes SET status_comercial = 'ativa' WHERE id = ?", (cobranca["org_id"],))
        log_evento(cobranca["org_id"], "cobranca_plano_paga", "cobranca_plano", cobranca_id, payload={"origem": "mercadopago_cartao"})
        _notificar_pagamento_confirmado(cobranca["org_id"])
        return {"status": "aprovado", "mp_payment_id": mp_payment_id}

    # "in_process"/"pending" — cartão em análise (antifraude). Fica registrado
    # com o mp_payment_id salvo; o webhook confirma sozinho quando a Mercado
    # Pago decidir (aprovado ou recusado), do mesmo jeito que já acontece
    # hoje com o PIX.
    log_evento(cobranca["org_id"], "cobranca_plano_cartao_em_analise", "cobranca_plano", cobranca_id, payload={"status": status_pagamento})
    return {"status": "em_analise", "mp_payment_id": mp_payment_id}


def _url_app():
    """Base pública do próprio app (ver .env.example) — usada nos back_urls
    do Checkout Pro (pra onde a Mercado Pago manda o Gestor de volta depois
    de pagar). Sem isso configurado no servidor não dá pra montar um
    back_url válido, então o checkout no cartão fica indisponível (mas o
    PIX e o resto do app continuam funcionando normalmente)."""
    return os.environ.get("URL_APP", "").strip().rstrip("/")


def criar_checkout_cartao(cobranca_id: int):
    """Fallback do cartão via Checkout Pro (link hospedado pela própria
    Mercado Pago, aberto em nova aba) — criado depois de confirmar, testando
    ao vivo, que o Card Payment Brick embutido (`criar_pagamento_cartao`
    acima) trava na inicialização em algumas contas/navegadores mesmo com
    CSP e chave pública corretos (erro "Bricks.create: Bricks component
    initialization failed", reproduzido mesmo em janela anônima sem
    extensões — não é bloqueador de anúncio, aparenta ser uma restrição do
    lado da conta/typo de integração "Bricks" na própria Mercado Pago).
    Checkout Pro é o fluxo mais simples e maduro da Mercado Pago: em vez de
    montar o formulário de cartão dentro do nosso site, a gente só cria uma
    "preferência" de cobrança e manda o Gestor pra uma página hospedada pela
    própria Mercado Pago pra pagar — nenhum JS deles precisa rodar aqui.

    Diferente do PIX/Brick, aqui NÃO temos o `mp_payment_id` na hora (só
    depois que o Gestor efetivamente pagar na página da Mercado Pago) — por
    isso `processar_webhook` abaixo sabe procurar pelo `external_reference`
    quando não encontra a cobrança pelo `mp_payment_id`."""
    cobranca = query_one(
        """SELECT cp.*, o.nome as organizacao_nome, o.id as org_id
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

    url_app = _url_app()
    if not url_app:
        raise RuntimeError("URL_APP não está configurada no servidor — fale com o suporte da Panda Tech.")

    org = query_one("SELECT * FROM organizacoes WHERE id = ?", (cobranca["org_id"],))
    payer_email = _email_cobranca(org)
    plano = _plano_por_codigo(cobranca["plano_codigo"])
    nome_plano = plano["nome"] if plano else cobranca["plano_codigo"]
    descricao_pagamento = cobranca.get("descricao") or f"Assinatura Panda Tech — Plano {nome_plano}"
    voltar = f"{url_app}/#/gestor/configuracoes"

    preference_data = {
        "items": [{
            "title": descricao_pagamento,
            "quantity": 1,
            "unit_price": round(cobranca["valor_centavos"] / 100, 2),
            "currency_id": "BRL",
        }],
        "payer": {"email": payer_email},
        "external_reference": f"cobranca-plano-{cobranca_id}",
        "notification_url": os.environ.get("MP_PLATAFORMA_NOTIFICATION_URL") or os.environ.get("MP_NOTIFICATION_URL") or None,
        "back_urls": {"success": voltar, "pending": voltar, "failure": voltar},
        "auto_return": "approved",
        # Só cartão — PIX/boleto já têm o fluxo próprio nesta mesma tela, não
        # faz sentido oferecer os dois caminhos pro mesmo valor ao mesmo tempo.
        "payment_methods": {"excluded_payment_types": [{"id": "ticket"}, {"id": "bank_transfer"}]},
    }

    try:
        resultado = sdk.preference().create(preference_data)
    except Exception as exc:
        raise RuntimeError(f"Não foi possível falar com o Mercado Pago agora ({exc.__class__.__name__}). Tente novamente em instantes.") from exc

    resposta = resultado.get("response", {})
    if resultado.get("status") not in (200, 201):
        raise RuntimeError(f"Mercado Pago recusou a criação do checkout: {resposta.get('message', 'erro desconhecido')}")

    checkout_url = resposta.get("init_point")
    if not checkout_url:
        raise RuntimeError("Mercado Pago não retornou o link de pagamento. Tente novamente em instantes.")

    log_evento(cobranca["org_id"], "cobranca_plano_checkout_cartao_criado", "cobranca_plano", cobranca_id)
    return {"checkout_url": checkout_url}


def processar_webhook(payment_id: str):
    """Idempotente — chamar duas vezes para o mesmo pagamento aprovado não
    tem efeito colateral extra na segunda vez.

    Procura primeiro por `mp_payment_id` (caso do PIX e do Card Payment
    Brick, onde a gente já salva o id assim que cria o pagamento). Se não
    achar, cai pro `external_reference` do próprio pagamento — caso do
    Checkout Pro (`criar_checkout_cartao`), onde só existe uma "preferência"
    até o Gestor pagar de verdade na página da Mercado Pago; é só aqui, na
    primeira notificação do webhook, que a gente descobre o payment_id de
    verdade e grava ele na cobrança."""
    sdk = _sdk()
    if not sdk:
        return {"ignorado": True, "motivo": "integração desconectada"}

    cobranca = query_one("SELECT * FROM cobrancas_planos WHERE mp_payment_id = ?", (str(payment_id),))

    try:
        from mercadopago.config import RequestOptions
        opcoes = RequestOptions(connection_timeout=15.0, max_retries=1)
        resultado = sdk.payment().get(payment_id, opcoes)
    except Exception as exc:
        motivo = f"erro ao consultar o Mercado Pago: {exc.__class__.__name__}"
        if cobranca:
            log_evento(cobranca["organizacao_id"], "webhook_mercadopago_plano_falhou", "cobranca_plano", cobranca["id"], payload={"erro": str(exc)})
        return {"ignorado": True, "motivo": motivo}

    pagamento = resultado.get("response", {})
    status = pagamento.get("status")

    if not cobranca:
        # Não achou pelo mp_payment_id — caso do Checkout Pro
        # (`criar_checkout_cartao`), onde só existe uma "preferência" até o
        # Gestor pagar de verdade na página da Mercado Pago; é só aqui, na
        # primeira notificação do webhook, que a gente descobre o
        # payment_id de verdade e grava ele na cobrança.
        referencia = pagamento.get("external_reference", "") or ""
        if referencia.startswith("cobranca-plano-"):
            cobranca_id_ref = referencia.replace("cobranca-plano-", "", 1)
            cobranca = query_one("SELECT * FROM cobrancas_planos WHERE id = ?", (cobranca_id_ref,))
            if cobranca:
                execute("UPDATE cobrancas_planos SET mp_payment_id = ? WHERE id = ?", (str(payment_id), cobranca["id"]))
    if not cobranca:
        return {"ignorado": True, "motivo": "cobrança de plano não encontrada para este payment_id"}

    if status == "approved" and cobranca["status"] != "pago":
        # forma_confirmacao pelo payment_method_id real da Mercado Pago, não
        # fixo em "pix" — desde o Checkout Pro (Fase 1, cartão), este mesmo
        # webhook também confirma pagamentos no cartão, e rotular errado
        # atrapalharia relatório/auditoria mais pra frente.
        forma = "mercadopago_pix" if pagamento.get("payment_method_id") == "pix" else "mercadopago_cartao"
        execute(
            "UPDATE cobrancas_planos SET status = 'pago', forma_confirmacao = ?, pago_em = ? WHERE id = ?",
            (forma, hoje_sql(), cobranca["id"]),
        )
        org = query_one("SELECT status_comercial FROM organizacoes WHERE id = ?", (cobranca["organizacao_id"],))
        if org and org["status_comercial"] == "inadimplente":
            execute("UPDATE organizacoes SET status_comercial = 'ativa' WHERE id = ?", (cobranca["organizacao_id"],))
        log_evento(cobranca["organizacao_id"], "cobranca_plano_paga", "cobranca_plano", cobranca["id"], payload={"origem": "mercadopago_webhook"})
        _notificar_pagamento_confirmado(cobranca["organizacao_id"])
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
    _notificar_pagamento_confirmado(cobranca["organizacao_id"])
