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

A chave vem de ENCANTO_CRYPTO_KEY (variável de ambiente). Se não estiver
definida, uma chave é gerada e usada em memória só para o processo atual —
funciona para rodar localmente, mas os dados cifrados não sobrevivem a um
restart do processo (por design: força quem for para produção a definir a
variável de verdade, em vez de silenciosamente usar uma chave previsível).
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

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
else:
    _KEY = Fernet.generate_key()

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
