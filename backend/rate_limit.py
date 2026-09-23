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
import os
import time
import threading
from functools import wraps

from flask import request, jsonify

_lock = threading.Lock()
_tentativas = {}  # chave -> [timestamps de tentativa, dentro da janela]
_ULTIMA_LIMPEZA = [0.0]
_INTERVALO_LIMPEZA_SEGUNDOS = 600  # varre e descarta chaves mortas a cada 10 min


# Quantos proxies confiáveis ficam na frente do app e acrescentam o IP do
# cliente no fim do X-Forwarded-For. Padrão 0: a produção (LiteSpeed no
# cPanel) entrega o IP real do cliente direto em remote_addr.
#
# Correção de auditoria (23/09/2026): antes, o primeiro IP do
# X-Forwarded-For era usado sempre — mas esse cabeçalho é enviado pelo
# próprio cliente, então bastava trocar o valor a cada tentativa para
# nunca ser bloqueado (força bruta de senha ilimitada). Agora o cabeçalho
# só é considerado quando ENCANTO_PROXIES_CONFIAVEIS > 0, e mesmo assim
# lido pela direita (a parte escrita pelos proxies, não pelo cliente).
_PROXIES_CONFIAVEIS = int(os.environ.get("ENCANTO_PROXIES_CONFIAVEIS", "0") or 0)


def _ip_cliente():
    if _PROXIES_CONFIAVEIS > 0:
        cadeia = [ip.strip() for ip in request.headers.get("X-Forwarded-For", "").split(",") if ip.strip()]
        if len(cadeia) >= _PROXIES_CONFIAVEIS:
            return cadeia[-_PROXIES_CONFIAVEIS]
    return request.remote_addr or "desconhecido"


def _chave(prefixo):
    return f"{prefixo}:{_ip_cliente()}"


def _email_do_corpo():
    body = request.get_json(force=True, silent=True) or {}
    email = body.get("email") if isinstance(body, dict) else None
    return email.strip().lower() if isinstance(email, str) and email.strip() else None


def _excedeu(chave, max_tentativas, janela_segundos, agora):
    """Registra uma tentativa em `chave` e diz se o limite já tinha sido
    atingido (nesse caso a tentativa não é registrada). Chamar com _lock."""
    timestamps = [t for t in _tentativas.get(chave, []) if agora - t < janela_segundos]
    if len(timestamps) >= max_tentativas:
        _tentativas[chave] = timestamps
        return True
    timestamps.append(agora)
    _tentativas[chave] = timestamps
    return False


def _limpar_chaves_mortas(agora, janela_segundos):
    """Evita crescimento ilimitado de memória em processo de longa duração:
    descarta por completo chaves cuja última tentativa já saiu da janela."""
    if agora - _ULTIMA_LIMPEZA[0] < _INTERVALO_LIMPEZA_SEGUNDOS:
        return
    mortas = [k for k, ts in _tentativas.items() if not ts or agora - max(ts) > janela_segundos]
    for k in mortas:
        _tentativas.pop(k, None)
    _ULTIMA_LIMPEZA[0] = agora


def limitar(prefixo, max_tentativas=10, janela_segundos=300, max_por_email=None):
    """
    Decorator de rota Flask: permite no máximo `max_tentativas` chamadas por
    IP a cada `janela_segundos`. Responde 429 quando o limite é excedido.

    `max_por_email` (opcional) soma um segundo limite, por e-mail do corpo
    da requisição, na mesma janela — segura força bruta contra UMA conta
    vinda de muitos IPs diferentes.

    Uso: @limitar("login", max_tentativas=10, janela_segundos=300, max_por_email=20)
    """
    def decorador(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            agora = time.time()
            email = _email_do_corpo() if max_por_email else None
            with _lock:
                _limpar_chaves_mortas(agora, janela_segundos)
                bloqueado = _excedeu(_chave(prefixo), max_tentativas, janela_segundos, agora)
                if not bloqueado and email:
                    bloqueado = _excedeu(f"{prefixo}:email:{email}", max_por_email, janela_segundos, agora)
            if bloqueado:
                return jsonify({
                    "erro": "Muitas tentativas em pouco tempo. Aguarde alguns minutos e tente novamente."
                }), 429
            return func(*args, **kwargs)
        return wrapper
    return decorador
