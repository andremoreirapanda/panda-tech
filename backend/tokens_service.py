"""
Tokens de uso único — usados tanto para convite de ativação de conta quanto
para redefinição de senha (Doc 35/36). Mesma mecânica de fundo: gerar um
token com validade, guardar, e mais tarde validar/consumir uma única vez.
"""
import secrets
from datetime import datetime, timedelta

from db import execute, query_one

VALIDADE_CONVITE_MINUTOS = 60 * 24 * 3  # convite dura 3 dias
VALIDADE_REDEFINICAO_MINUTOS = 60        # redefinição de senha dura 1h


def gerar_token(usuario_id: int, tipo: str = "redefinicao") -> str:
    validade = VALIDADE_CONVITE_MINUTOS if tipo == "convite" else VALIDADE_REDEFINICAO_MINUTOS
    token = secrets.token_urlsafe(24)
    expira_em = (datetime.now() + timedelta(minutes=validade)).strftime("%Y-%m-%d %H:%M:%S")
    execute(
        "INSERT INTO tokens_redefinicao_senha (usuario_id, token, tipo, expira_em) VALUES (?, ?, ?, ?)",
        (usuario_id, token, tipo, expira_em),
    )
    return token


def link_para(token: str) -> str:
    return f"#/redefinir-senha?token={token}"


def gerar_senha_bloqueada() -> str:
    """
    Usada ao criar uma conta por convite: a senha inicial é um valor
    aleatório impossível de adivinhar — a pessoa só ganha acesso de verdade
    depois de abrir o link de convite e definir a própria senha.
    """
    return secrets.token_urlsafe(24)


def token_valido(token: str):
    linha = query_one("SELECT * FROM tokens_redefinicao_senha WHERE token = ?", (token,))
    if not linha or linha["usado"] or linha["expira_em"] < datetime.now().strftime("%Y-%m-%d %H:%M:%S"):
        return None
    return linha
