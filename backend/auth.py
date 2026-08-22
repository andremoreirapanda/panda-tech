"""
Core > Autenticação e Permissões (Documento 07, seção 2).

- Login / Sessão via JWT (stateless).
- Recuperação de senha (endpoint simulado, sem envio real de e-mail).
- Perfis: admin_master | gestor | profissional | responsavel
- Isolamento entre organizações (cada clínica só enxerga seus próprios dados).
"""
import hashlib
import hmac
import os
import time
from functools import wraps

import jwt
from flask import request, jsonify, g

from db import query_one

# Correção de auditoria (item 4.1 — crítico): antes, se ENCANTO_SECRET não
# estivesse definida, o processo subia normalmente usando uma chave fixa e
# hardcoded neste arquivo (visível a qualquer pessoa com acesso ao
# código-fonte) como segredo de assinatura JWT — permitindo forjar um token
# válido para qualquer usuário, inclusive admin_master, sem credencial
# nenhuma. Agora o processo recusa iniciar fora do modo de desenvolvimento
# (FLASK_DEBUG=1) sem essa variável definida.
_DEV_MODE = os.environ.get("FLASK_DEBUG", "0") == "1"
_SECRET_ENV = os.environ.get("ENCANTO_SECRET")

if _SECRET_ENV:
    SECRET_KEY = _SECRET_ENV
elif _DEV_MODE:
    SECRET_KEY = "encanto-em-casa-dev-secret-nao-usar-em-producao"
    print("⚠️  ENCANTO_SECRET não definida — usando a chave padrão de DESENVOLVIMENTO "
          "(FLASK_DEBUG=1). Isso só é aceitável rodando localmente.")
else:
    raise RuntimeError(
        "ENCANTO_SECRET não está definida. Defina uma chave forte antes de iniciar o servidor "
        "(ex.: gere com `python3 -c \"import secrets; print(secrets.token_hex(32))\"` e "
        "configure essa variável de ambiente no seu provedor de hospedagem). Para rodar "
        "localmente em modo de desenvolvimento sem essa variável, defina FLASK_DEBUG=1."
    )

TOKEN_TTL_SECONDS = 60 * 60 * 12  # 12h


# ------------------------- Senhas -------------------------

def hash_senha(senha: str, salt: str = None):
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), 100_000).hex()
    return digest, salt


def verificar_senha(senha: str, hash_armazenado: str, salt: str) -> bool:
    digest, _ = hash_senha(senha, salt)
    return hmac.compare_digest(digest, hash_armazenado)


# ------------------------- Token -------------------------

def gerar_token(usuario: dict) -> str:
    payload = {
        "sub": usuario["id"],
        "papel": usuario["papel"],
        "organizacao_id": usuario["organizacao_id"],
        "nome": usuario["nome"],
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decodificar_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


# ------------------------- Decorators -------------------------

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"erro": "Não autenticado. Faça login novamente."}), 401
        token = auth_header.split(" ", 1)[1]
        payload = decodificar_token(token)
        if not payload:
            return jsonify({"erro": "Sessão expirada. Faça login novamente."}), 401
        usuario = query_one("SELECT * FROM usuarios WHERE id = ? AND ativo = 1", (payload["sub"],))
        if not usuario:
            return jsonify({"erro": "Usuário não encontrado ou inativo."}), 401
        g.usuario = usuario
        return fn(*args, **kwargs)

    return wrapper


def papel_required(*papeis_permitidos):
    """Restringe o endpoint a determinados papéis (RBAC)."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if g.usuario["papel"] not in papeis_permitidos:
                return jsonify({"erro": "Você não tem permissão para acessar este recurso."}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def paciente_acessivel(paciente_id: int) -> bool:
    """
    Verifica se g.usuario pode VER dados do paciente informado (Doc 013,
    seção 8, atualizado — insight do usuário): qualquer profissional da
    clínica pode visualizar qualquer paciente, não só os que atende
    diretamente — só a EDIÇÃO é restrita (ver `paciente_editavel`).
    """
    u = g.usuario
    if u["papel"] in ("admin_master", "gestor"):
        row = query_one(
            "SELECT 1 FROM pacientes WHERE id = ? AND organizacao_id = ?",
            (paciente_id, u["organizacao_id"]),
        )
        return bool(row)
    if u["papel"] == "profissional":
        row = query_one(
            "SELECT 1 FROM pacientes WHERE id = ? AND organizacao_id = ?",
            (paciente_id, u["organizacao_id"]),
        )
        return bool(row)
    if u["papel"] == "responsavel":
        row = query_one(
            "SELECT 1 FROM responsaveis_pacientes WHERE usuario_id = ? AND paciente_id = ?",
            (u["id"], paciente_id),
        )
        return bool(row)
    return False


def paciente_editavel(paciente_id: int) -> bool:
    """
    Verifica se g.usuario pode EDITAR o paciente (criar/editar jornada,
    plano, missões, diário, ficha clínica, dados de identidade): Gestor
    sempre pode; Profissional só se estiver de fato vinculado como parte
    da equipe que atende esse paciente.
    """
    u = g.usuario
    if u["papel"] in ("admin_master", "gestor"):
        row = query_one(
            "SELECT 1 FROM pacientes WHERE id = ? AND organizacao_id = ?",
            (paciente_id, u["organizacao_id"]),
        )
        return bool(row)
    if u["papel"] == "profissional":
        row = query_one(
            "SELECT 1 FROM profissionais_pacientes WHERE usuario_id = ? AND paciente_id = ?",
            (u["id"], paciente_id),
        )
        return bool(row)
    return False
