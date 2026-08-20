"""
Assinatura do parâmetro `state` usado no fluxo OAuth2 do Google Calendar.

O callback do Google (`/api/integracoes/google_calendar/callback`) é uma
navegação de navegador comum — não chega com o header `Authorization:
Bearer ...` que o resto da API exige. Por isso o `organizacao_id` viaja
embutido e assinado dentro do `state` (protege contra CSRF e contra alguém
forjar uma clínica diferente da que iniciou o fluxo), com expiração curta
(10 minutos — tempo de sobra para o gestor autorizar no Google).
"""
import os

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

_SECRET = os.environ.get("ENCANTO_SECRET", "encanto-em-casa-dev-secret-nao-usar-em-producao")
_SALT = "google-oauth-state"
_MAX_IDADE_SEGUNDOS = 600

_serializer = URLSafeTimedSerializer(_SECRET, salt=_SALT)


def assinar_state(organizacao_id: int) -> str:
    return _serializer.dumps({"organizacao_id": organizacao_id})


def verificar_state(state: str) -> int:
    try:
        dados = _serializer.loads(state, max_age=_MAX_IDADE_SEGUNDOS)
    except (BadSignature, SignatureExpired) as exc:
        raise ValueError("state inválido ou expirado — tente conectar novamente.") from exc
    return dados["organizacao_id"]
