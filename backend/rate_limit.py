"""
Limitador de taxa simples, em memória, por processo — sem dependência nova.

Correção de auditoria (item 4.5): login e recuperação de senha não tinham
nenhuma proteção contra força bruta — tentativas ilimitadas, sem atraso,
sem bloqueio de conta, sem CAPTCHA. Isto fecha essa lacuna com custo zero de
nova dependência, o que importa aqui porque o processo de deploy atual é
`git pull` + restart, sem um passo de `pip install` automático — adicionar
uma biblioteca como flask-limiter exigiria um passo manual extra no cPanel
que é fácil de esquecer e derrubaria o processo se esquecido.

Limitação conhecida (documentada, não escondida): com múltiplos workers
Gunicorn (o Dockerfile deste projeto usa --workers 2), cada worker mantém a
própria contagem em memória — o limite efetivo real é (limite x número de
workers), não um limite global exato entre processos. Ainda assim, é uma
redução real e imediata da superfície de força bruta em relação ao estado
anterior (zero limite). Se o tráfego/escala crescerem a ponto de isso não
ser suficiente, a recomendação da auditoria (seção 19) é migrar para um
limitador compartilhado (Redis, por exemplo) — não antes de precisar.
"""
import time
import threading
from functools import wraps

from flask import request, jsonify

_lock = threading.Lock()
_tentativas = {}  # chave -> [timestamps de tentativa, dentro da janela]
_ULTIMA_LIMPEZA = [0.0]
_INTERVALO_LIMPEZA_SEGUNDOS = 600  # varre e descarta chaves mortas a cada 10 min


def _chave(prefixo):
    # X-Forwarded-For é usado quando o app roda atrás de um proxy (comum em
    # cPanel/Passenger); pega só o primeiro IP da cadeia (o do cliente real).
    origem = request.headers.get("X-Forwarded-For", request.remote_addr or "desconhecido")
    ip = origem.split(",")[0].strip()
    return f"{prefixo}:{ip}"


def _limpar_chaves_mortas(agora, janela_segundos):
    """Evita crescimento ilimitado de memória em processo de longa duração:
    descarta por completo chaves cuja última tentativa já saiu da janela."""
    if agora - _ULTIMA_LIMPEZA[0] < _INTERVALO_LIMPEZA_SEGUNDOS:
        return
    mortas = [k for k, ts in _tentativas.items() if not ts or agora - max(ts) > janela_segundos]
    for k in mortas:
        _tentativas.pop(k, None)
    _ULTIMA_LIMPEZA[0] = agora


def limitar(prefixo, max_tentativas=10, janela_segundos=300):
    """
    Decorator de rota Flask: permite no máximo `max_tentativas` chamadas por
    IP a cada `janela_segundos`. Responde 429 quando o limite é excedido.

    Uso: @limitar("login", max_tentativas=10, janela_segundos=300)
    """
    def decorador(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            chave = _chave(prefixo)
            agora = time.time()
            with _lock:
                _limpar_chaves_mortas(agora, janela_segundos)
                timestamps = [t for t in _tentativas.get(chave, []) if agora - t < janela_segundos]
                if len(timestamps) >= max_tentativas:
                    _tentativas[chave] = timestamps
                    return jsonify({
                        "erro": "Muitas tentativas em pouco tempo. Aguarde alguns minutos e tente novamente."
                    }), 429
                timestamps.append(agora)
                _tentativas[chave] = timestamps
            return func(*args, **kwargs)
        return wrapper
    return decorador
