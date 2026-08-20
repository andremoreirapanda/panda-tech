"""
Domínio: Core > Autenticação (Documento 07)
Endpoints: login, dados do usuário logado, troca de perfil (modo criança),
recuperação de senha com token de uso único (Doc 35/36).
"""
import json

from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute
from auth import verificar_senha, gerar_token as gerar_jwt, login_required, hash_senha
from modulos_service import modulos_habilitados_clinica, financeiro_visivel_para_usuario
from tokens_service import gerar_token, link_para, token_valido, VALIDADE_REDEFINICAO_MINUTOS

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

CAMPOS_ORG = """id, nome, cor_primaria, cor_secundaria, logo_emoji, logo_base64, plano,
                nome_ia, nome_moeda_gamificacao, nome_medalha_generico, especialidades_json,
                agenda_permissao_total_padrao"""


def _org_com_modulos(organizacao_id):
    org = query_one(f"SELECT {CAMPOS_ORG} FROM organizacoes WHERE id = ?", (organizacao_id,))
    if org:
        org["modulos_habilitados"] = sorted(modulos_habilitados_clinica(organizacao_id, org["plano"]))
        org["especialidades"] = json.loads(org.pop("especialidades_json") or "[]")
    return org


@bp.post("/login")
def login():
    body = request.get_json(force=True, silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    senha = body.get("senha") or ""

    if not email or not senha:
        return jsonify({"erro": "Informe e-mail e senha."}), 400

    usuario = query_one("SELECT * FROM usuarios WHERE lower(email) = ? AND ativo = 1", (email,))
    if not usuario or not verificar_senha(senha, usuario["senha_hash"], usuario["senha_salt"]):
        return jsonify({"erro": "E-mail ou senha inválidos."}), 401

    token = gerar_jwt(usuario)
    org = _org_com_modulos(usuario["organizacao_id"]) if usuario["organizacao_id"] else None
    financeiro_visivel = financeiro_visivel_para_usuario(usuario) if usuario["papel"] == "responsavel" else None

    return jsonify({
        "token": token,
        "usuario": {
            "id": usuario["id"],
            "nome": usuario["nome"],
            "email": usuario["email"],
            "papel": usuario["papel"],
            "telefone": usuario["telefone"],
            "avatar_emoji": usuario["avatar_emoji"],
            "avatar_base64": usuario["avatar_base64"],
            "especialidade": usuario["especialidade"],
            "cor_agenda": usuario["cor_agenda"],
            "agenda_permissao_total": bool(usuario["agenda_permissao_total"]),
            "organizacao_id": usuario["organizacao_id"],
            "organizacao": org,
            "financeiro_visivel": financeiro_visivel,
        },
    })


@bp.get("/me")
@login_required
def me():
    u = g.usuario
    org = _org_com_modulos(u["organizacao_id"]) if u["organizacao_id"] else None
    filhos = []
    if u["papel"] == "responsavel":
        filhos = query(
            """SELECT p.id, p.nome, p.avatar_mascote, p.foto_base64, p.data_nascimento
               FROM pacientes p
               JOIN responsaveis_pacientes rp ON rp.paciente_id = p.id
               WHERE rp.usuario_id = ? AND p.ativo = 1""",
            (u["id"],),
        )
    financeiro_visivel = financeiro_visivel_para_usuario(u) if u["papel"] == "responsavel" else None
    return jsonify({
        "id": u["id"], "nome": u["nome"], "email": u["email"], "papel": u["papel"], "telefone": u["telefone"],
        "avatar_emoji": u["avatar_emoji"], "avatar_base64": u["avatar_base64"], "especialidade": u["especialidade"],
        "cor_agenda": u["cor_agenda"], "agenda_permissao_total": bool(u["agenda_permissao_total"]),
        "organizacao_id": u["organizacao_id"],
        "organizacao": org, "filhos": filhos, "financeiro_visivel": financeiro_visivel,
    })


@bp.post("/esqueci-senha")
def esqueci_senha():
    """
    Gera um token de uso único com validade de 1h (Doc 35/36). Como este
    ambiente não tem servidor de e-mail configurado, o link é devolvido
    diretamente na resposta (rotulado como 'modo demonstração') em vez de
    ser enviado por e-mail — em produção, aqui entraria o disparo real via
    serviço de Notificações (Core).
    """
    body = request.get_json(force=True, silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    usuario = query_one("SELECT * FROM usuarios WHERE lower(email) = ? AND ativo = 1", (email,))

    resposta = {"mensagem": f"Se {email} estiver cadastrado, enviaremos instruções de recuperação."}
    if usuario:
        token = gerar_token(usuario["id"], tipo="redefinicao")
        resposta["modo_demonstracao"] = True
        resposta["link_redefinicao"] = link_para(token)
        resposta["validade_minutos"] = VALIDADE_REDEFINICAO_MINUTOS
    return jsonify(resposta)


@bp.get("/validar-token-redefinicao/<token>")
def validar_token_redefinicao(token):
    linha = token_valido(token)
    if not linha:
        return jsonify({"valido": False}), 200
    usuario = query_one("SELECT nome, email FROM usuarios WHERE id = ?", (linha["usuario_id"],))
    return jsonify({"valido": True, "nome": usuario["nome"], "email": usuario["email"], "tipo": linha["tipo"]})


@bp.post("/redefinir-senha")
def redefinir_senha():
    body = request.get_json(force=True, silent=True) or {}
    token = body.get("token", "")
    nova_senha = body.get("nova_senha", "")
    if not token or not nova_senha:
        return jsonify({"erro": "Token e nova senha são obrigatórios."}), 400
    if len(nova_senha) < 6:
        return jsonify({"erro": "A senha precisa ter pelo menos 6 caracteres."}), 400

    linha = token_valido(token)
    if not linha:
        linha_bruta = query_one("SELECT * FROM tokens_redefinicao_senha WHERE token = ?", (token,))
        if linha_bruta and linha_bruta["usado"]:
            return jsonify({"erro": "Este link já foi usado. Solicite um novo."}), 400
        return jsonify({"erro": "Este link é inválido ou expirou. Solicite um novo."}), 400

    senha_hash, salt = hash_senha(nova_senha)
    execute("UPDATE usuarios SET senha_hash = ?, senha_salt = ? WHERE id = ?", (senha_hash, salt, linha["usuario_id"]))
    execute("UPDATE tokens_redefinicao_senha SET usado = 1 WHERE id = ?", (linha["id"],))
    return jsonify({"ok": True})
