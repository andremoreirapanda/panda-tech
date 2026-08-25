"""
Domínio 10 — Integrações (Documento 09 / Módulo 10).

ATUALIZAÇÃO DESTA RODADA: sai da Fase 2 ("andaime" — só o toggle
liga/desliga) e entra na integração REAL com os 3 provedores prioritários
do piloto — Google Agenda (OAuth2), Mercado Pago (PIX) e WhatsApp Cloud API.
O ERP continua como toggle-only (é honesto: sem saber qual ERP a
clínica-piloto usa, não dá para escolher um adapter específico — ver
GAP_ANALYSIS.md).

Cada integração agora tem seu próprio fluxo de configuração (ver funções
abaixo); `alternar()` (o toggle genérico antigo) só continua servindo para
o ERP.
"""
from urllib.parse import quote

from flask import Blueprint, request, jsonify, g, redirect

from db import query, query_one, execute, log_auditoria, obter_config_integracao
from auth import login_required, papel_required
import calendar_sync_service
import pagamento_service
import whatsapp_service

bp = Blueprint("integracoes", __name__, url_prefix="/api/integracoes")

# Códigos de erro OAuth2 padrão (RFC 6749 §4.1.2.1) que o Google pode
# devolver nesse redirect. Qualquer coisa fora dessa lista é tratada como
# "erro_desconhecido" — não refletimos o parâmetro `error` bruto no
# redirect, porque esse endpoint é público (sem @login_required) e
# `?error=...` é 100% controlado por quem monta a URL, não só pelo Google.
ERROS_OAUTH_CONHECIDOS = {
    "access_denied", "invalid_request", "unauthorized_client",
    "unsupported_response_type", "invalid_scope", "server_error",
    "temporarily_unavailable",
}

TIPOS_PADRAO = [
    ("whatsapp", "WhatsApp Business", "💬", "Envia lembretes de missão e consulta direto no WhatsApp da família."),
    ("google_calendar", "Google Agenda", "📅", "Sincroniza a agenda da clínica com o Google Calendar da equipe."),
    ("erp", "ERP / Sistema financeiro", "🧾", "Sincroniza cobranças e notas fiscais com o ERP já usado pela clínica."),
    ("pagamento", "Gateway de pagamento", "💳", "Habilita cobrança automática via PIX/cartão direto no app da família."),
]

TIPOS_COM_TOGGLE_MANUAL = ("erp",)  # os outros 3 têm fluxo de conexão próprio


def _garantir_linhas(organizacao_id):
    existentes = {i["tipo"] for i in query("SELECT tipo FROM integracoes WHERE organizacao_id = ?", (organizacao_id,))}
    for tipo, *_ in TIPOS_PADRAO:
        if tipo not in existentes:
            execute("INSERT INTO integracoes (organizacao_id, tipo, status) VALUES (?, ?, 'desconectado')", (organizacao_id, tipo))


@bp.get("")
@login_required
@papel_required("gestor", "admin_master")
def listar():
    org_id = g.usuario["organizacao_id"]
    _garantir_linhas(org_id)
    rows = query("SELECT * FROM integracoes WHERE organizacao_id = ?", (org_id,))
    por_tipo = {r["tipo"]: r for r in rows}
    resultado = []
    for tipo, nome, icone, descricao in TIPOS_PADRAO:
        r = por_tipo.get(tipo, {})
        item = {
            "tipo": tipo, "nome": nome, "icone": icone, "descricao": descricao,
            "status": r.get("status", "desconectado"), "id": r.get("id"),
            "toggle_manual": tipo in TIPOS_COM_TOGGLE_MANUAL,
        }
        if tipo == "google_calendar":
            item["disponivel_no_saas"] = calendar_sync_service.credenciais_configuradas()
        resultado.append(item)
    return jsonify(resultado)


@bp.post("/<tipo>/toggle")
@login_required
@papel_required("gestor", "admin_master")
def alternar(tipo):
    """Toggle genérico — hoje só faz sentido para o ERP (as outras 3
    integrações têm fluxo de conexão dedicado com credenciais reais)."""
    if tipo not in TIPOS_COM_TOGGLE_MANUAL:
        return jsonify({"erro": f"Use o fluxo de conexão dedicado para '{tipo}' (ver Central de Integrações)."}), 400
    u = g.usuario
    _garantir_linhas(u["organizacao_id"])
    row = query_one("SELECT * FROM integracoes WHERE organizacao_id = ? AND tipo = ?", (u["organizacao_id"], tipo))
    if not row:
        return jsonify({"erro": "Integração desconhecida."}), 404
    novo_status = "desconectado" if row["status"] == "conectado" else "conectado"
    execute("UPDATE integracoes SET status = ? WHERE id = ?", (novo_status, row["id"]))
    log_auditoria(u["organizacao_id"], u["id"], "alternar_integracao", "integracao", row["id"], f"{tipo} -> {novo_status}")
    return jsonify({"status": novo_status})


# ------------------------- Google Agenda (OAuth2) -------------------------

@bp.get("/google_calendar/autorizar")
@login_required
@papel_required("gestor", "admin_master")
def google_autorizar():
    if not calendar_sync_service.credenciais_configuradas():
        return jsonify({"erro": "O SaaS ainda não configurou as credenciais OAuth do Google (GOOGLE_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI)."}), 503
    url = calendar_sync_service.gerar_url_autorizacao(g.usuario["organizacao_id"])
    return jsonify({"url": url})


@bp.get("/google_calendar/callback")
def google_callback():
    """Chamado pelo próprio Google (navegação de navegador, sem Bearer token
    — por isso não usa @login_required; a segurança vem do `state` assinado).

    IMPORTANTE: como este endpoint não exige login, `?error=...` pode ser
    montado por qualquer pessoa (não só pelo Google) — por isso nunca
    refletimos esse valor bruto no redirect (era um XSS refletido não
    autenticado: ver ERROS_OAUTH_CONHECIDOS acima). O motivo devolvido
    também é sempre URL-encoded como defesa em profundidade, mesmo já
    validado/truncado."""
    erro = request.args.get("error")
    if erro:
        motivo = erro if erro in ERROS_OAUTH_CONHECIDOS else "erro_desconhecido"
        return redirect(f"/#/gestor/integracoes?google_calendar=erro&motivo={quote(motivo)}")
    code = request.args.get("code")
    state = request.args.get("state")
    try:
        organizacao_id = calendar_sync_service.finalizar_autorizacao(code, state)
        log_auditoria(organizacao_id, None, "conectar_integracao", "integracao", None, "google_calendar conectado via OAuth2")
        return redirect("/#/gestor/integracoes?google_calendar=conectado")
    except Exception as exc:
        return redirect(f"/#/gestor/integracoes?google_calendar=erro&motivo={quote(str(exc)[:120])}")


@bp.post("/google_calendar/desconectar")
@login_required
@papel_required("gestor", "admin_master")
def google_desconectar():
    calendar_sync_service.desconectar(g.usuario["organizacao_id"])
    log_auditoria(g.usuario["organizacao_id"], g.usuario["id"], "desconectar_integracao", "integracao", None, "google_calendar")
    return jsonify({"status": "desconectado"})


# ------------------------- Pagamento (Mercado Pago) -------------------------

@bp.post("/pagamento/config")
@login_required
@papel_required("gestor", "admin_master")
def pagamento_config():
    body = request.get_json(force=True, silent=True) or {}
    access_token = (body.get("access_token") or "").strip()
    if not access_token:
        return jsonify({"erro": "Informe o Access Token do Mercado Pago (painel > Suas integrações > Credenciais)."}), 400
    webhook_secret = (body.get("webhook_secret") or "").strip() or None
    pagamento_service.salvar_access_token(g.usuario["organizacao_id"], access_token, body.get("public_key"), webhook_secret)
    log_auditoria(g.usuario["organizacao_id"], g.usuario["id"], "conectar_integracao", "integracao", None, "pagamento configurado")
    return jsonify({"status": "conectado"})


@bp.post("/pagamento/webhook")
def pagamento_webhook():
    """Endpoint público — o Mercado Pago chama isso quando o status de um
    pagamento muda. Não usa @login_required (a chamada não vem do
    navegador de ninguém autenticado no app, vem do servidor do Mercado
    Pago).

    Cada clínica tem a própria conta de Mercado Pago (e portanto a própria
    chave secreta de webhook) — por isso, antes de validar a assinatura,
    primeiro descobrimos a QUE clínica esse payment_id pertence, para saber
    qual chave usar. Se não encontrarmos nenhuma cobrança com esse
    payment_id, não há nada a confirmar mesmo, então respondemos 200 sem
    checar assinatura (não vaza nenhuma informação sensível)."""
    x_signature = request.headers.get("x-signature")
    x_request_id = request.headers.get("x-request-id")
    payment_id = request.args.get("data.id") or (request.get_json(silent=True) or {}).get("data", {}).get("id")
    if not payment_id:
        return jsonify({"ignorado": True}), 200

    organizacao_id = pagamento_service.organizacao_id_por_payment_id(str(payment_id))
    if not organizacao_id:
        return jsonify({"ignorado": True, "motivo": "cobrança não encontrada para este payment_id"}), 200

    secret = pagamento_service.webhook_secret_configurado(organizacao_id)
    if not pagamento_service.validar_assinatura_webhook(x_signature, x_request_id, str(payment_id), secret):
        return jsonify({"erro": "assinatura inválida"}), 401

    resultado = pagamento_service.processar_webhook(payment_id)
    return jsonify(resultado), 200


# ------------------------- WhatsApp (Cloud API) -------------------------

@bp.post("/whatsapp/config")
@login_required
@papel_required("gestor", "admin_master")
def whatsapp_config():
    body = request.get_json(force=True, silent=True) or {}
    access_token = (body.get("access_token") or "").strip()
    phone_number_id = (body.get("phone_number_id") or "").strip()
    if not access_token or not phone_number_id:
        return jsonify({"erro": "Informe o Access Token e o Phone Number ID (painel Meta for Developers > WhatsApp > Introdução)."}), 400
    whatsapp_service.salvar_configuracao(g.usuario["organizacao_id"], access_token, phone_number_id)
    log_auditoria(g.usuario["organizacao_id"], g.usuario["id"], "conectar_integracao", "integracao", None, "whatsapp configurado")
    return jsonify({"status": "conectado"})


@bp.post("/whatsapp/testar")
@login_required
@papel_required("gestor", "admin_master")
def whatsapp_testar():
    body = request.get_json(force=True, silent=True) or {}
    telefone = (body.get("telefone") or "").strip()
    if not telefone:
        return jsonify({"erro": "Informe um telefone (com DDD) para o teste."}), 400
    try:
        whatsapp_service.enviar_texto_livre(
            g.usuario["organizacao_id"], telefone,
            body.get("mensagem") or "Mensagem de teste da Panda Tech 🌟 — se você recebeu isso, a integração está funcionando!",
        )
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"erro": str(exc)}), 400
