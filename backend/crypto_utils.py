"""
Criptografia em repouso para credenciais de integrações (Doc 26 — Integration
Layer / boas práticas de segurança para OAuth tokens e chaves de API).

Antes desta rodada, `integracoes.configuracao_json` era só um andaime vazio.
Agora ele guarda de verdade tokens do Google, access token do Mercado Pago e
token do WhatsApp Cloud API — dado sensível que nunca deve ficar em texto
puro no banco (mesmo o SQLite local de demonstração).

Uso:
    from crypto_utils import cifrar, decifrar
    configuracao_json = cifrar(json.dumps({"refresh_token": "..."}))
    dados = json.loads(decifrar(configuracao_json))

A chave vem de ENCANTO_CRYPTO_KEY (variável de ambiente).

Correção de auditoria (seção 19/recomendação de arquitetura): antes, se a
variável não estivesse definida, o processo gerava uma chave aleatória em
memória e seguia normalmente — o que parece seguro, mas na prática é uma
armadilha operacional silenciosa: com múltiplos workers Gunicorn (este
projeto roda com --workers 2), cada worker gera a PRÓPRIA chave, então dado
cifrado por um worker pode não ser decifrável por outro, e nada sobrevive a
um restart. Isso mascarava credenciais de integração "sumindo" sem nenhum
erro visível. Agora o processo recusa iniciar fora do modo de
desenvolvimento (FLASK_DEBUG=1) sem essa variável definida.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_DEV_MODE = os.environ.get("FLASK_DEBUG", "0") == "1"
_ENV_KEY = os.environ.get("ENCANTO_CRYPTO_KEY")

if _ENV_KEY:
    # Aceita tanto uma chave Fernet válida (44 chars, base64 urlsafe) quanto
    # qualquer string secreta arbitrária (derivamos uma chave Fernet válida
    # a partir dela via SHA-256 — mais prático para configurar em painéis de
    # hospedagem que só aceitam uma variável de texto simples).
    try:
        Fernet(_ENV_KEY.encode())
        _KEY = _ENV_KEY.encode()
    except (ValueError, TypeError):
        _KEY = base64.urlsafe_b64encode(hashlib.sha256(_ENV_KEY.encode()).digest())
elif _DEV_MODE:
    _KEY = Fernet.generate_key()
    print("⚠️  ENCANTO_CRYPTO_KEY não definida — usando chave temporária de DESENVOLVIMENTO "
          "(FLASK_DEBUG=1). Dados cifrados não sobrevivem a um restart neste modo.")
else:
    raise RuntimeError(
        "ENCANTO_CRYPTO_KEY não está definida. Gere uma chave estável antes de iniciar o "
        "servidor (ex.: `python3 -c \"from cryptography.fernet import Fernet; "
        "print(Fernet.generate_key().decode())\"`) e configure essa variável de ambiente no "
        "seu provedor de hospedagem — sem isso, credenciais de integração cifradas (Mercado "
        "Pago, WhatsApp, Google) podem se tornar ilegíveis entre reinícios/processos. "
        "Para rodar localmente em modo de desenvolvimento sem essa variável, defina FLASK_DEBUG=1."
    )

_fernet = Fernet(_KEY)


def cifrar(texto_plano: str) -> str:
    if texto_plano is None:
        return None
    return _fernet.encrypt(texto_plano.encode()).decode()


def decifrar(texto_cifrado: str):
    if not texto_cifrado:
        return None
    try:
        return _fernet.decrypt(texto_cifrado.encode()).decode()
    except (InvalidToken, ValueError):
        # Dado antigo não cifrado (ex: linha criada antes desta migração) ou
        # chave trocada — trata como "sem configuração" em vez de derrubar a
        # requisição.
        return None
