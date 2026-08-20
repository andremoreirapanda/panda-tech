"""
Sincronização de consultas com o Google Calendar (Doc 26 — Integration Layer).

ATUALIZAÇÃO DESTA RODADA: esta é agora a integração REAL (OAuth2 + Google
Calendar API), não mais só o "encaixe". A versão anterior deste arquivo só
simulava (gerava um `google_event_id` fake) porque foi construída num
ambiente sem acesso à internet — este ambiente tem, então a troca foi feita
como o comentário antigo já previa.

Como funciona:
  1. O gestor clica em "Conectar" na Central de Integrações → o frontend
     chama `GET /api/integracoes/google_calendar/autorizar` (ver
     integracoes_bp.py), que devolve a URL de consentimento do Google.
  2. O navegador é redirecionado pro Google, o gestor autoriza, o Google
     redireciona de volta pro `GOOGLE_OAUTH_REDIRECT_URI` configurado.
  3. `finalizar_autorizacao()` troca o `code` por um token de acesso +
     refresh token, e guarda isso cifrado em `integracoes.configuracao_json`
     (uma linha por clínica — `organizacao_id` isola cada uma).
  4. A partir daí, toda vez que uma consulta é criada/editada/cancelada,
     `agenda_bp.py` chama `sincronizar_consulta_google()` como já fazia — o
     resto do sistema não precisou mudar, exatamente como o comentário
     original previa.

Se a clínica nunca conectou (sem token salvo), a função cai de volta pro
modo simulado — nunca quebra o fluxo de agenda por causa da integração.

Variáveis de ambiente necessárias (ver `.env.example`):
  GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI
"""
import os
from datetime import datetime, timedelta

from db import query_one, execute, log_evento, obter_config_integracao, salvar_config_integracao

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI")


def credenciais_configuradas() -> bool:
    """Confere se o SaaS (não a clínica) já tem um app OAuth do Google criado.
    Sem isso, nem adianta mostrar o botão 'Conectar' pra nenhuma clínica."""
    return bool(CLIENT_ID and CLIENT_SECRET and REDIRECT_URI)


def _client_config():
    return {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    }


def integracao_google_ativa(organizacao_id: int) -> bool:
    """Confere se a clínica já concluiu o OAuth (tem refresh_token salvo)."""
    linha = query_one(
        "SELECT status FROM integracoes WHERE organizacao_id = ? AND tipo = 'google_calendar'",
        (organizacao_id,),
    )
    return bool(linha and linha["status"] == "conectado")


def gerar_url_autorizacao(organizacao_id: int) -> str:
    """Monta a URL de consentimento do Google, com o organizacao_id embutido
    de forma assinada no `state` (assim o callback sabe pra qual clínica
    salvar o token, sem depender de sessão/cookie do navegador)."""
    from google_oauth_state import assinar_state
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=REDIRECT_URI)
    url, _ = flow.authorization_url(
        access_type="offline",       # necessário para ganhar refresh_token
        include_granted_scopes="true",
        prompt="consent",            # força reemissão do refresh_token mesmo se já autorizou antes
        state=assinar_state(organizacao_id),
    )
    return url


def finalizar_autorizacao(code: str, state: str):
    """Chamado pelo callback OAuth. Troca o `code` pelo token e salva.
    Retorna o organizacao_id em caso de sucesso, ou levanta ValueError."""
    from google_oauth_state import verificar_state
    from google_auth_oauthlib.flow import Flow

    organizacao_id = verificar_state(state)  # levanta ValueError se inválido/expirado

    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=REDIRECT_URI)
    flow.fetch_token(code=code)
    creds = flow.credentials

    salvar_config_integracao(
        organizacao_id,
        "google_calendar",
        {
            "refresh_token": creds.refresh_token,
            "token": creds.token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
            "conectado_em": datetime.utcnow().isoformat(),
        },
        status="conectado",
    )
    return organizacao_id


def desconectar(organizacao_id: int):
    """Revoga localmente (apaga o token salvo). Não chama o endpoint de
    revoke do Google automaticamente para não exigir escopo extra — o
    gestor também pode revogar em myaccount.google.com/permissions."""
    salvar_config_integracao(organizacao_id, "google_calendar", {}, status="desconectado")


def _obter_credenciais(organizacao_id: int):
    """Reconstrói um objeto Credentials do google-auth a partir do que está
    salvo no banco, renovando o access_token automaticamente se necessário."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GoogleRequest

    config = obter_config_integracao(organizacao_id, "google_calendar")
    refresh_token = config.get("refresh_token")
    if not refresh_token:
        return None

    creds = Credentials(
        token=config.get("token"),
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES,
    )
    if not creds.valid:
        creds.refresh(GoogleRequest())
        config["token"] = creds.token
        config["expiry"] = creds.expiry.isoformat() if creds.expiry else None
        salvar_config_integracao(organizacao_id, "google_calendar", config, status="conectado")
    return creds


def sincronizar_consulta_google(consulta_id: int, organizacao_id: int, acao: str = "criar"):
    """
    Ponto único de sincronização — chamado pelo agenda_bp.py sempre que uma
    consulta é criada, editada ou tem o status alterado.

    - Sem integração conectada: não faz nada (custo zero), como sempre.
    - Com integração conectada e credenciais do app OAuth configuradas: cria
      / atualiza / apaga o evento de verdade no Google Calendar do
      profissional responsável (usando o token da clínica).
    - Com integração 'conectada' no banco mas sem `credenciais_configuradas()`
      (ex: ambiente de desenvolvimento sem as env vars do Google): cai pro
      modo simulado antigo, para não quebrar a demo.
    """
    if not integracao_google_ativa(organizacao_id):
        return

    consulta = query_one("SELECT * FROM consultas WHERE id = ?", (consulta_id,))
    if not consulta:
        return

    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not credenciais_configuradas():
        # Modo simulado (comportamento original, preservado como fallback).
        if acao == "excluir":
            execute("UPDATE consultas SET google_event_id = NULL, google_sincronizado_em = ? WHERE id = ?", (agora, consulta_id))
        else:
            event_id_simulado = consulta["google_event_id"] or f"simulado-{consulta_id}"
            execute("UPDATE consultas SET google_event_id = ?, google_sincronizado_em = ? WHERE id = ?", (event_id_simulado, agora, consulta_id))
        log_evento(organizacao_id, "consulta_sincronizada_google_simulado", "consulta", consulta_id)
        return

    try:
        creds = _obter_credenciais(organizacao_id)
        if not creds:
            return
        from googleapiclient.discovery import build

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        if acao == "excluir":
            if consulta["google_event_id"]:
                try:
                    service.events().delete(calendarId="primary", eventId=consulta["google_event_id"]).execute()
                except Exception:
                    pass  # evento já pode ter sido apagado manualmente no Google
            execute("UPDATE consultas SET google_event_id = NULL, google_sincronizado_em = ? WHERE id = ?", (agora, consulta_id))
        else:
            paciente = query_one("SELECT nome FROM pacientes WHERE id = ?", (consulta["paciente_id"],))
            inicio = datetime.strptime(consulta["data_hora"], "%Y-%m-%d %H:%M:%S")
            fim = inicio + timedelta(minutes=consulta["duracao_min"] or 50)
            corpo_evento = {
                "summary": f"Consulta — {paciente['nome'] if paciente else 'Paciente'}",
                "description": consulta.get("observacoes") or "Consulta agendada via Panda Tech.",
                "start": {"dateTime": inicio.isoformat(), "timeZone": "America/Sao_Paulo"},
                "end": {"dateTime": fim.isoformat(), "timeZone": "America/Sao_Paulo"},
            }
            if consulta["google_event_id"]:
                evento = service.events().update(
                    calendarId="primary", eventId=consulta["google_event_id"], body=corpo_evento
                ).execute()
            else:
                evento = service.events().insert(calendarId="primary", body=corpo_evento).execute()
            execute(
                "UPDATE consultas SET google_event_id = ?, google_sincronizado_em = ? WHERE id = ?",
                (evento["id"], agora, consulta_id),
            )
        log_evento(organizacao_id, "consulta_sincronizada_google", "consulta", consulta_id)
    except Exception as exc:
        # Nunca deixa a integração quebrar o fluxo principal de agenda —
        # registra o erro como evento de auditoria e segue.
        log_evento(organizacao_id, "consulta_sincronizacao_google_falhou", "consulta", consulta_id, payload={"erro": str(exc)})
