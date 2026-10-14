"""
Logo da plataforma (14/10/2026): enviado pelo Admin em Perfil da Plataforma
(tabela `plataforma_identidade`, linha id = 1). Dois tipos:

- "principal" (`logo_base64`): fundos claros — menu do Admin, e-mails e telas
  de recuperar acesso; também o login, quando não há o logo do login.
- "login" (`logo_login_base64`, 15/10/2026): versão com letras claras, só para
  o fundo roxo da tela de login.

A tela de login própria de cada clínica (White Label) continua com o logo da
clínica. O `index.html` leva a versão de cada logo numa meta, e a imagem sai
por `/api/publico/plataforma/logo[-login]?v=<versao>`: trocar o logo muda o
endereço, então nenhum celular fica preso no logo antigo pelo cache.
"""
import hashlib

from db import query_one, execute, agora_sql, get_db
from identidade_service import mime_imagem

MAX_LOGO_BYTES = 2 * 1024 * 1024  # o navegador já reduz para até 1024 px / ~1,5 MB
COLUNAS = {"principal": "logo_base64", "login": "logo_login_base64"}


def _linha(tipo="principal"):
    """O logo do tipo, ou None — também se a tabela ou a coluna ainda não
    existirem (deploy antes da migração): aí tudo segue como sem logo.
    Uma consulta por coluna, para um logo não depender da migração do outro."""
    coluna = COLUNAS[tipo]
    try:
        return query_one(
            f"SELECT {coluna} AS logo, atualizado_em FROM plataforma_identidade "
            f"WHERE id = 1 AND {coluna} IS NOT NULL AND {coluna} <> ''"
        )
    except Exception:
        try:
            get_db().rollback()  # no Postgres a transação fica abortada depois do erro
        except Exception:
            pass
        return None


def logo_base64(tipo="principal"):
    linha = _linha(tipo)
    return linha["logo"] if linha else None


def versao_logo(tipo="principal"):
    """Texto curto que muda quando o logo muda; "" sem logo."""
    linha = _linha(tipo)
    if not linha:
        return ""
    base = f"{tipo}:{linha['atualizado_em']}:{len(linha['logo'])}:{linha['logo'][-64:]}"
    return hashlib.sha256(base.encode()).hexdigest()[:10]


def salvar_logo(b64, tipo="principal"):
    """Grava o logo (PNG, JPEG ou WebP). Devolve a mensagem de erro, ou None."""
    coluna = COLUNAS[tipo]
    if not isinstance(b64, str) or not b64.strip():
        return "Envie uma imagem."
    b64 = b64.strip()
    if mime_imagem(b64) is None:
        return "Formato não aceito: envie PNG, JPG ou WebP."
    if len(b64) * 3 // 4 > MAX_LOGO_BYTES:
        return "Imagem grande demais (máximo 2 MB). Reduza e envie de novo."
    execute(
        f"""INSERT INTO plataforma_identidade (id, {coluna}, atualizado_em) VALUES (1, ?, ?)
            ON CONFLICT (id) DO UPDATE SET {coluna} = excluded.{coluna}, atualizado_em = excluded.atualizado_em""",
        (b64, agora_sql()),
    )
    return None


def remover_logo(tipo="principal"):
    coluna = COLUNAS[tipo]
    execute(f"UPDATE plataforma_identidade SET {coluna} = NULL, atualizado_em = ? WHERE id = 1", (agora_sql(),))
