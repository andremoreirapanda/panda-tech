"""
WhatsApp (Doc 26 — Integration Layer / Módulo 10) — lembretes de missão e
consulta direto no WhatsApp da família.

ATUALIZAÇÃO DESTA RODADA: integração REAL com a WhatsApp Cloud API oficial
da Meta (não Twilio) — pesquisei as duas opções antes de decidir: o sandbox
gratuito da Twilio é rotulado pela própria documentação como "só para
desenvolvimento", com um único número compartilhado e sem suporte a
mensagens de template fora da janela de 24h — não é adequado para validar
com clientes reais. A Cloud API direto da Meta, por outro lado, já nasce
pronta pra isso: dá pra cadastrar um "número de teste" gratuito que manda
mensagens de verdade para até 5 números verificados sem precisar de
verificação completa de empresa — perfeito para o piloto com uma clínica e
famílias reais antes de migrar para um número comercial de produção.

Como funciona:
  1. Clínica (ou o SaaS, no piloto) cria um app Meta for Developers, adiciona
     o produto "WhatsApp", pega o `phone_number_id` e o token de acesso
     temporário (ou permanente, via System User) do painel.
  2. Gestor salva isso em `POST /api/integracoes/whatsapp/config`.
  3. `enviar_lembrete_consulta()` / `enviar_lembrete_missao()` são chamados
     nos pontos certos (agenda_bp.py ao confirmar consulta, jornada_bp.py ao
     publicar missão) e disparam a mensagem via Graph API.

Dentro da janela de 24h após a família mandar qualquer mensagem pro número
da clínica, dá pra mandar texto livre. Fora dela (caso mais comum de
lembrete pró-ativo), é obrigatório usar um Message Template pré-aprovado
pela Meta — por isso `enviar_template()` existe separado de
`enviar_texto_livre()`. Ver SETUP_INTEGRACOES.md para como criar o
template "lembrete_consulta" e "lembrete_missao" no Gerenciador do
WhatsApp Business.
"""
import os
import re

import requests

from db import query_one, log_evento, obter_config_integracao, salvar_config_integracao, obter_config_integracao_plataforma

GRAPH_API_VERSION = "v20.0"
GRAPH_API_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def configurado(organizacao_id: int) -> bool:
    config = obter_config_integracao(organizacao_id, "whatsapp")
    return bool(config.get("access_token") and config.get("phone_number_id"))


def salvar_configuracao(organizacao_id: int, access_token: str, phone_number_id: str):
    salvar_config_integracao(
        organizacao_id, "whatsapp",
        {"access_token": access_token, "phone_number_id": phone_number_id},
        status="conectado" if (access_token and phone_number_id) else "desconectado",
    )


def _link_absoluto(link_relativo: str) -> str:
    """`tokens_service.link_para()` devolve só a rota relativa da SPA (ex:
    "#/redefinir-senha?token=..."), porque quem sempre montou a URL completa
    até agora foi o próprio navegador (`location.origin + location.pathname`
    em util.js::mostrarModalConvite). Uma mensagem de WhatsApp não tem esse
    contexto — precisa de uma URL absoluta pronta. Exige a variável de
    ambiente URL_APP (ver .env.example); sem ela, retorna "" de propósito
    (nunca manda um link quebrado, sem domínio, por WhatsApp)."""
    base = os.environ.get("URL_APP", "").strip().rstrip("/")
    if not base or not link_relativo:
        return ""
    return f"{base}/{link_relativo}"


def formatar_telefone_e164(telefone: str, pais_padrao: str = "55") -> str:
    """Normaliza um telefone brasileiro solto (com ou sem DDI/máscara) para
    o formato E.164 que a Graph API exige (ex: '11987654321' -> '5511987654321')."""
    digitos = re.sub(r"\D", "", telefone or "")
    if not digitos:
        return ""
    if digitos.startswith(pais_padrao) and len(digitos) >= 12:
        return digitos
    return f"{pais_padrao}{digitos}"


def _enviar(access_token: str, phone_number_id: str, payload: dict):
    if not access_token or not phone_number_id:
        raise RuntimeError("WhatsApp não configurado.")
    resp = requests.post(
        f"{GRAPH_API_URL}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=payload,
        timeout=10,
    )
    corpo = resp.json()
    if resp.status_code >= 400:
        erro = corpo.get("error", {}).get("message", "erro desconhecido")
        raise RuntimeError(f"WhatsApp recusou o envio: {erro}")
    return corpo


def _post(organizacao_id: int, payload: dict):
    config = obter_config_integracao(organizacao_id, "whatsapp")
    if not config.get("access_token") or not config.get("phone_number_id"):
        raise RuntimeError("Esta clínica ainda não configurou o WhatsApp na Central de Integrações.")
    return _enviar(config["access_token"], config["phone_number_id"], payload)


def configurado_plataforma() -> bool:
    """Mesma checagem de `configurado()`, mas pra credencial da PRÓPRIA
    Panda Tech (Admin > Integrações), não de uma clínica."""
    config = obter_config_integracao_plataforma("whatsapp")
    return bool(config.get("access_token") and config.get("phone_number_id"))


def _post_plataforma(payload: dict):
    config = obter_config_integracao_plataforma("whatsapp")
    if not config.get("access_token") or not config.get("phone_number_id"):
        raise RuntimeError("A Panda Tech ainda não configurou o WhatsApp da plataforma (Admin > Integrações).")
    return _enviar(config["access_token"], config["phone_number_id"], payload)


def enviar_texto_livre(organizacao_id: int, telefone: str, texto: str):
    """Só funciona dentro da janela de 24h após a família ter mandado
    mensagem pro número da clínica. Fora disso, use `enviar_template`."""
    destino = formatar_telefone_e164(telefone)
    payload = {
        "messaging_product": "whatsapp",
        "to": destino,
        "type": "text",
        "text": {"body": texto},
    }
    return _post(organizacao_id, payload)


def enviar_texto_livre_plataforma(telefone: str, texto: str):
    """Igual `enviar_texto_livre`, mas mandado do número da própria Panda
    Tech (não de uma clínica) — usado pros avisos administrativos (ex:
    cobrança de plano gerada). Mesma limitação: só entrega se o destinatário
    tiver mandado mensagem pro WhatsApp da Panda Tech nas últimas 24h; fora
    dessa janela a Meta recusa texto livre (precisaria de um Template
    aprovado, que este fluxo não usa por simplicidade)."""
    destino = formatar_telefone_e164(telefone)
    payload = {
        "messaging_product": "whatsapp",
        "to": destino,
        "type": "text",
        "text": {"body": texto},
    }
    return _post_plataforma(payload)


def enviar_template(organizacao_id: int, telefone: str, nome_template: str, idioma: str = "pt_BR", parametros: list = None):
    """Envia uma mensagem de template pré-aprovada (necessário para iniciar
    conversa fora da janela de 24h — caso típico de lembrete pró-ativo)."""
    destino = formatar_telefone_e164(telefone)
    componentes = []
    if parametros:
        componentes.append({"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in parametros]})
    payload = {
        "messaging_product": "whatsapp",
        "to": destino,
        "type": "template",
        "template": {"name": nome_template, "language": {"code": idioma}, "components": componentes},
    }
    return _post(organizacao_id, payload)


# ------------------------- Pontos de disparo -------------------------

def enviar_lembrete_consulta(consulta_id: int):
    """Chamado pelo agenda_bp.py ao criar/confirmar uma consulta. Nunca
    levanta exceção para não derrubar o fluxo de agenda — qualquer falha
    (integração desconectada, telefone ausente, template não aprovado
    ainda) vira só um evento de auditoria."""
    consulta = query_one("SELECT * FROM consultas WHERE id = ?", (consulta_id,))
    if not consulta:
        return
    paciente = query_one("SELECT organizacao_id, nome FROM pacientes WHERE id = ?", (consulta["paciente_id"],))
    if not paciente or not configurado(paciente["organizacao_id"]):
        return
    responsavel = query_one(
        """SELECT u.telefone FROM responsaveis_pacientes rp JOIN usuarios u ON u.id = rp.usuario_id
           WHERE rp.paciente_id = ? AND u.telefone IS NOT NULL AND u.telefone != '' LIMIT 1""",
        (consulta["paciente_id"],),
    )
    if not responsavel:
        return
    try:
        enviar_template(
            paciente["organizacao_id"], responsavel["telefone"], "lembrete_consulta",
            parametros=[paciente["nome"], consulta["data_hora"]],
        )
        log_evento(paciente["organizacao_id"], "whatsapp_lembrete_consulta_enviado", "consulta", consulta_id)
    except Exception as exc:
        log_evento(paciente["organizacao_id"], "whatsapp_lembrete_consulta_falhou", "consulta", consulta_id, payload={"erro": str(exc)})


def enviar_convite_responsavel(usuario_id: int, link: str) -> bool:
    """Achado de UAT (26/08/2026): quando quem cadastra o responsável não
    copia o link de ativação, hoje só dá pra gerar um novo (ver
    pessoas_bp.py::reenviar_convite_responsavel) e reenviar manualmente —
    não existe envio automático por e-mail (o projeto nunca teve integração
    de e-mail). Como o WhatsApp real já está integrado, oferece essa opção
    aqui em vez disso.

    Chamado ao vincular um responsável novo e ao reenviar o convite. Mesma
    postura defensiva das demais notificações (enviar_lembrete_*): nunca
    levanta exceção — se a clínica não tiver o WhatsApp configurado, se o
    responsável não tiver telefone cadastrado, ou se o envio falhar por
    qualquer motivo, quem chamou continua tendo o link pra copiar e mandar
    manualmente. Retorna True/False só para a tela poder avisar se o envio
    automático rolou ou não.

    Requer um Message Template aprovado no Gerenciador do WhatsApp Business
    chamado "convite_responsavel" (idioma pt_BR), com exatamente dois
    parâmetros de corpo na ordem usada abaixo: {{1}} = nome do responsável,
    {{2}} = link de ativação. Ver tutorial de configuração na biblioteca.
    """
    usuario = query_one("SELECT nome, telefone, organizacao_id FROM usuarios WHERE id = ?", (usuario_id,))
    if not usuario or not usuario["telefone"] or not configurado(usuario["organizacao_id"]):
        return False
    link_absoluto = _link_absoluto(link)
    if not link_absoluto:
        # URL_APP não configurada no servidor — mandar o link relativo
        # (ex: "#/redefinir-senha?token=...") quebraria no WhatsApp, que não
        # tem o domínio implícito que o navegador teria. Melhor não mandar
        # nada automático do que mandar um link inútil.
        return False
    try:
        enviar_template(
            usuario["organizacao_id"], usuario["telefone"], "convite_responsavel",
            parametros=[usuario["nome"], link_absoluto],
        )
        log_evento(usuario["organizacao_id"], "whatsapp_convite_responsavel_enviado", "usuario", usuario_id)
        return True
    except Exception as exc:
        log_evento(usuario["organizacao_id"], "whatsapp_convite_responsavel_falhou", "usuario", usuario_id, payload={"erro": str(exc)})
        return False


def enviar_lembrete_missao(missao_id: int):
    """Chamado ao publicar uma missão nova (jornada_bp.py). Mesma postura
    defensiva de `enviar_lembrete_consulta`: nunca quebra o fluxo principal."""
    contexto = query_one(
        """SELECT m.titulo, p.id as paciente_id, p.organizacao_id, p.nome as paciente_nome
           FROM missoes m
           JOIN planos_terapeuticos pt ON pt.id = m.plano_id
           JOIN jornadas j ON j.id = pt.jornada_id
           JOIN pacientes p ON p.id = j.paciente_id
           WHERE m.id = ?""",
        (missao_id,),
    )
    if not contexto or not configurado(contexto["organizacao_id"]):
        return
    responsavel = query_one(
        """SELECT u.telefone FROM responsaveis_pacientes rp JOIN usuarios u ON u.id = rp.usuario_id
           WHERE rp.paciente_id = ? AND u.telefone IS NOT NULL AND u.telefone != '' LIMIT 1""",
        (contexto["paciente_id"],),
    )
    if not responsavel:
        return
    try:
        enviar_template(
            contexto["organizacao_id"], responsavel["telefone"], "lembrete_missao",
            parametros=[contexto["paciente_nome"], contexto["titulo"]],
        )
        log_evento(contexto["organizacao_id"], "whatsapp_lembrete_missao_enviado", "missao", missao_id)
    except Exception as exc:
        log_evento(contexto["organizacao_id"], "whatsapp_lembrete_missao_falhou", "missao", missao_id, payload={"erro": str(exc)})
