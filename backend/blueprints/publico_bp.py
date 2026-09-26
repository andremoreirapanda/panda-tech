"""
White Label completo (spec 25/09/2026): rotas SEM login para a tela de login
própria da clínica (#/entrar/<endereco>) e para as imagens da identidade
(ícone do app, mascote, cenário). As imagens vão por URL porque a CSP não
deixa usar blob: e o manifest precisa de URL.

Só respondem para clínica ativa, não cancelada e com o módulo white_label —
fora isso, 404 (o front cai no login normal). Nunca devolvem dado comercial,
de pacientes ou o id da clínica.
"""
import json

from flask import Blueprint, jsonify, Response, abort

from db import query_one
from identidade_service import identidade_efetiva, mime_imagem, IMAGENS_RESUMIDAS_SQL
from modulos_service import modulo_ativo_para_clinica
from validacao_arquivo import _decodificar_binario

bp = Blueprint("publico", __name__, url_prefix="/api/publico")

# As imagens vêm resumidas; cada rota de imagem pede só a coluna dela.
_CAMPOS = """id, nome, plano, ativo, status_comercial, logo_emoji, logo_base64, cor_primaria, cor_secundaria,
             nome_ia, nome_moeda_gamificacao, nome_medalha_generico, app_nome, login_mensagem,
             mundo_fonte, mundo_fundo, mundo_mascote, mundo_comemoracao, endereco_login,
             pandoo_cenario_padrao, pandoo_cenario_tom, """ + IMAGENS_RESUMIDAS_SQL
_CAMPOS_PUBLICOS = ("nome", "logo_emoji", "logo_base64", "cor_primaria", "cor_secundaria", "app_nome",
                    "login_mensagem", "mundo_mascote", "tem_mascote_imagem", "tem_icone", "versao_imagens",
                    "endereco_login")


def _clinica(endereco, imagem=None):
    extra = f", {imagem} AS imagem_bruta" if imagem else ""
    org = query_one(f"SELECT {_CAMPOS}{extra} FROM organizacoes WHERE endereco_login = ?", ((endereco or "").lower(),))
    if not org or not org["ativo"] or org["status_comercial"] == "cancelada":
        abort(404)
    if not modulo_ativo_para_clinica(org["id"], org["plano"], "white_label"):
        abort(404)
    return org


@bp.get("/clinica/<endereco>")
def dados_login(endereco):
    e = identidade_efetiva(_clinica(endereco), True)
    return jsonify({k: e[k] for k in _CAMPOS_PUBLICOS})


def _imagem(b64):
    mime = mime_imagem(b64) if b64 else None
    if not mime:
        abort(404)
    resp = Response(_decodificar_binario(b64), mimetype=mime)
    # A URL leva ?v=<versao_imagens>, que muda quando a imagem muda.
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@bp.get("/clinica/<endereco>/icone")
def icone(endereco):
    return _imagem(_clinica(endereco, "app_icone_base64")["imagem_bruta"])


@bp.get("/clinica/<endereco>/mascote")
def mascote(endereco):
    return _imagem(_clinica(endereco, "mundo_mascote_imagem")["imagem_bruta"])


@bp.get("/clinica/<endereco>/cenario")
def cenario(endereco):
    return _imagem(_clinica(endereco, "pandoo_cenario_imagem")["imagem_bruta"])


@bp.get("/clinica/<endereco>/manifest.webmanifest")
def manifest(endereco):
    """Nome e ícone do app na tela inicial do celular (Android/Chrome)."""
    org = _clinica(endereco, "app_icone_base64")
    e = identidade_efetiva(org, True)
    icones = []
    if e["tem_icone"]:
        icones.append({"src": f"/api/publico/clinica/{org['endereco_login']}/icone?v={e['versao_imagens']}",
                       "sizes": "512x512", "type": mime_imagem(org["imagem_bruta"])})
    nome = e["app_nome"]
    corpo = {"name": nome, "short_name": nome if len(nome) <= 12 else nome[:12].rstrip(),
             "start_url": f"/#/entrar/{org['endereco_login']}", "display": "standalone",
             "background_color": "#FFFFFF", "theme_color": e["cor_primaria"], "icons": icones}
    return Response(json.dumps(corpo, ensure_ascii=False), mimetype="application/manifest+json")
