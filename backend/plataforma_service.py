"""
Logo da plataforma (14/10/2026): uma imagem só, enviada pelo Admin em Perfil da
Plataforma (tabela `plataforma_identidade`, linha id = 1). Aparece no menu do
Admin, na tela de login comum e nas telas de recuperar acesso — a tela de login
própria de cada clínica (White Label) continua com o logo da clínica.

O `index.html` leva a versão do logo numa meta (`versao_logo`), e a imagem sai
por `/api/publico/plataforma/logo?v=<versao>`: trocar o logo muda o endereço,
então nenhum celular fica preso no logo antigo pelo cache.
"""
import hashlib

from db import query_one, execute, agora_sql, get_db
from identidade_service import mime_imagem

MAX_LOGO_BYTES = 2 * 1024 * 1024  # o navegador já reduz para até 1024 px / ~1,5 MB


def _linha():
    """A linha do logo, ou None — também se a tabela ainda não existir (deploy
    antes da migração): aí tudo segue como sem logo."""
    try:
        return query_one(
            "SELECT logo_base64, atualizado_em FROM plataforma_identidade "
            "WHERE id = 1 AND logo_base64 IS NOT NULL AND logo_base64 <> ''"
        )
    except Exception:
        try:
            get_db().rollback()  # no Postgres a transação fica abortada depois do erro
        except Exception:
            pass
        return None


def logo_base64():
    linha = _linha()
    return linha["logo_base64"] if linha else None


def versao_logo():
    """Texto curto que muda quando o logo muda; "" sem logo."""
    linha = _linha()
    if not linha:
        return ""
    base = f"{linha['atualizado_em']}:{len(linha['logo_base64'])}:{linha['logo_base64'][-64:]}"
    return hashlib.sha256(base.encode()).hexdigest()[:10]


def salvar_logo(b64):
    """Grava o logo (PNG, JPEG ou WebP). Devolve a mensagem de erro, ou None."""
    if not isinstance(b64, str) or not b64.strip():
        return "Envie uma imagem."
    b64 = b64.strip()
    if mime_imagem(b64) is None:
        return "Formato não aceito: envie PNG, JPG ou WebP."
    if len(b64) * 3 // 4 > MAX_LOGO_BYTES:
        return "Imagem grande demais (máximo 2 MB). Reduza e envie de novo."
    execute(
        """INSERT INTO plataforma_identidade (id, logo_base64, atualizado_em) VALUES (1, ?, ?)
           ON CONFLICT (id) DO UPDATE SET logo_base64 = excluded.logo_base64, atualizado_em = excluded.atualizado_em""",
        (b64, agora_sql()),
    )
    return None


def remover_logo():
    execute("UPDATE plataforma_identidade SET logo_base64 = NULL, atualizado_em = ? WHERE id = 1", (agora_sql(),))
