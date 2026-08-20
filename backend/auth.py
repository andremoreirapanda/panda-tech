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

SECRET_KEY = os.environ.get("ENCANTO_SECRET", "encanto-em-casa-dev-secret-nao-usar-em-producao")
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
