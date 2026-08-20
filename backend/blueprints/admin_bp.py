"""
Módulo 11 — Administração da Plataforma (Documento 10) + camada comercial.

"Esse módulo será utilizado apenas por quem administra o SaaS
(e não pela clínica)." Gestão de clínicas, planos, White Label, auditoria
global — e, nesta fase, também o painel que o time comercial usa para
acompanhar MRR, trials vencendo, inadimplência e churn.
"""
import json
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, g

from db import (
    query, query_one, execute, log_auditoria, hoje_sql,
    salvar_config_integracao_plataforma,
)
from auth import login_required, papel_required, hash_senha
from tokens_service import gerar_token as gerar_token_convite, link_para as link_para_token, gerar_senha_bloqueada
import calendar_sync_service

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _plano_por_codigo(codigo):
    p = query_one("SELECT * FROM planos WHERE codigo = ?", (codigo,))
    if p and p.get("recursos_json"):
        p["recursos"] = json.loads(p["recursos_json"])
    return p


def _enriquecer_clinica(o):
    plano = _plano_por_codigo(o["plano"]) or {}
    o["especialidades"] = json.loads(o.get("especialidades_json") or "[]")
    total_pacientes = query_one("SELECT COUNT(*) as c FROM pacientes WHERE organizacao_id = ? AND ativo=1", (o["id"],))["c"]
    total_profissionais = query_one("SELECT COUNT(*) as c FROM usuarios WHERE organizacao_id = ? AND papel='profissional'", (o["id"],))["c"]

    dias_restantes_trial = None
    if o["status_comercial"] == "trial" and o.get("data_inicio_trial"):
        inicio = datetime.strptime(o["data_inicio_trial"], "%Y-%m-%d")
        fim = inicio + timedelta(days=o.get("dias_trial") or 14)
        dias_restantes_trial = (fim - datetime.now()).days

    limite_pac = plano.get("limite_pacientes")
    uso_pacientes_pct = round((total_pacientes / limite_pac) * 100) if limite_pac else None

    o["plano_nome"] = plano.get("nome", o["plano"])
    o["plano_cor"] = plano.get("cor", "#6A6280")
    o["mrr_centavos"] = plano.get("preco_mensal_centavos", 0) if o["status_comercial"] in ("ativa", "inadimplente") else 0
    o["total_pacientes"] = total_pacientes
    o["total_profissionais"] = total_profissionais
    o["limite_pacientes"] = limite_pac
    o["uso_pacientes_pct"] = uso_pacientes_pct
    o["dias_restantes_trial"] = dias_restantes_trial
    return o


# ---------------------------------------------------------------- Clínicas

@bp.get("/clinicas")
@login_required
@papel_required("admin_master")
def listar_clinicas():
    rows = query("SELECT * FROM organizacoes ORDER BY criado_em DESC")
    return jsonify([_enriquecer_clinica(o) for o in rows])


@bp.post("/clinicas")
@login_required
@papel_required("admin_master")
def criar_clinica():
    body = request.get_json(force=True, silent=True) or {}
    nome = (body.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "Nome da clínica é obrigatório."}), 400
    especialidades = body.get("especialidades") or []
    org_id = execute(
        """INSERT INTO organizacoes (nome, plano, logo_emoji, status_comercial, data_inicio_trial, dias_trial,
                                      contato_nome, contato_email, contato_telefone, origem_lead, observacoes_comerciais,
                                      cnpj, telefone, endereco_cep, endereco_logradouro, endereco_numero,
                                      endereco_bairro, endereco_cidade, endereco_uf, especialidades_json)
           VALUES (?, ?, ?, 'trial', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (nome, body.get("plano", "starter"), body.get("logo_emoji", "🌟"), hoje_sql(), body.get("dias_trial", 14),
         body.get("contato_nome", ""), body.get("gestor_email", ""), body.get("contato_telefone", ""),
         body.get("origem_lead", "outbound"), body.get("observacoes_comerciais", ""),
         body.get("cnpj", ""), body.get("telefone", ""), body.get("endereco_cep", ""),
         body.get("endereco_logradouro", ""), body.get("endereco_numero", ""), body.get("endereco_bairro", ""),
         body.get("endereco_cidade", ""), body.get("endereco_uf", ""), json.dumps(especialidades, ensure_ascii=False)),
    )
    gestor_nome = body.get("gestor_nome", "Gestor(a)")
    gestor_email = (body.get("gestor_email") or f"gestor@{nome.lower().replace(' ', '')}.com").strip().lower()
    senha_hash, salt = hash_senha(gerar_senha_bloqueada())
    gestor_id = execute(
        """INSERT INTO usuarios (organizacao_id, nome, email, senha_hash, senha_salt, papel)
           VALUES (?, ?, ?, ?, ?, 'gestor')""",
        (org_id, gestor_nome, gestor_email, senha_hash, salt),
    )
    token = gerar_token_convite(gestor_id, tipo="convite")
    log_auditoria(None, g.usuario["id"], "criar", "organizacao", org_id, nome)
    return jsonify({"id": org_id, "gestor_email": gestor_email, "link_convite": link_para_token(token)}), 201


@bp.put("/clinicas/<int:org_id>/plano")
@login_required
@papel_required("admin_master")
def atualizar_plano(org_id):
    body = request.get_json(force=True, silent=True) or {}
    execute("UPDATE organizacoes SET plano = ? WHERE id = ?", (body.get("plano", "starter"), org_id))
    log_auditoria(None, g.usuario["id"], "atualizar_plano", "organizacao", org_id, body.get("plano"))
    return jsonify({"ok": True})


@bp.put("/clinicas/<int:org_id>/status")
@login_required
@papel_required("admin_master")
def atualizar_status_clinica(org_id):
    body = request.get_json(force=True, silent=True) or {}
    execute("UPDATE organizacoes SET ativo = ? WHERE id = ?", (1 if body.get("ativo") else 0, org_id))
    return jsonify({"ok": True})


@bp.put("/clinicas/<int:org_id>/comercial")
@login_required
@papel_required("admin_master")
def atualizar_dados_comerciais(org_id):
    """Edita status comercial, contato e observações — usado pelo time de vendas/CS."""
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    org = query_one("SELECT * FROM organizacoes WHERE id = ?", (org_id,))
    if not org:
        return jsonify({"erro": "Clínica não encontrada."}), 404

    novo_status = body.get("status_comercial", org["status_comercial"])
    campos_extra = ""
    params_extra = []
    if novo_status in ("ativa",) and org["status_comercial"] == "trial":
        # Conversão de trial para pagante: registra a data da assinatura
        campos_extra = ", assinatura_inicio = ?"
        params_extra = [hoje_sql()]

    execute(
        f"""UPDATE organizacoes SET status_comercial = ?, contato_nome = ?, contato_email = ?,
            contato_telefone = ?, origem_lead = ?, observacoes_comerciais = ?, ativo = ?
            {campos_extra}
            WHERE id = ?""",
        (novo_status, body.get("contato_nome", org["contato_nome"]), body.get("contato_email", org["contato_email"]),
         body.get("contato_telefone", org["contato_telefone"]), body.get("origem_lead", org["origem_lead"]),
         body.get("observacoes_comerciais", org["observacoes_comerciais"]),
         0 if novo_status == "cancelada" else 1, *params_extra, org_id),
    )
    log_auditoria(None, u["id"], "atualizar_dados_comerciais", "organizacao", org_id,
                  f"status -> {novo_status}")
    return jsonify({"ok": True})


@bp.put("/clinicas/<int:org_id>/institucional")
@login_required
@papel_required("admin_master")
def atualizar_dados_institucionais(org_id):
    """
    Edita CNPJ, telefone, endereço e área de atuação de qualquer clínica —
    o mesmo conjunto de campos que o gestor edita em Configurações, mas
    acessível ao Admin do SaaS (ex: pra completar um cadastro que o gestor
    ainda não preencheu, ou corrigir um dado incorreto).
    """
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    org = query_one("SELECT * FROM organizacoes WHERE id = ?", (org_id,))
    if not org:
        return jsonify({"erro": "Clínica não encontrada."}), 404
    especialidades = body.get("especialidades")
    execute(
        """UPDATE organizacoes SET cnpj = ?, telefone = ?, endereco_cep = ?, endereco_logradouro = ?,
           endereco_numero = ?, endereco_bairro = ?, endereco_cidade = ?, endereco_uf = ?, especialidades_json = ?
           WHERE id = ?""",
        (body.get("cnpj", org["cnpj"]), body.get("telefone", org["telefone"]),
         body.get("endereco_cep", org["endereco_cep"]), body.get("endereco_logradouro", org["endereco_logradouro"]),
         body.get("endereco_numero", org["endereco_numero"]), body.get("endereco_bairro", org["endereco_bairro"]),
         body.get("endereco_cidade", org["endereco_cidade"]), body.get("endereco_uf", org["endereco_uf"]),
         json.dumps(especialidades, ensure_ascii=False) if especialidades is not None else org["especialidades_json"],
         org_id),
    )
    log_auditoria(None, u["id"], "atualizar_dados_institucionais", "organizacao", org_id, "Dados institucionais")
    return jsonify({"ok": True})


# ---------------------------------------------------------------- Planos

@bp.get("/planos")
@login_required
@papel_required("admin_master", "gestor")
def listar_planos():
    rows = query("SELECT * FROM planos WHERE ativo = 1 ORDER BY ordem")
    for p in rows:
        p["recursos"] = json.loads(p["recursos_json"]) if p.get("recursos_json") else []
    return jsonify(rows)


@bp.put("/planos/<codigo>")
@login_required
@papel_required("admin_master")
def atualizar_plano_definicao(codigo):
    """Permite ao Admin do SaaS ajustar preço/limites/recursos de um plano comercial."""
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    plano = query_one("SELECT * FROM planos WHERE codigo = ?", (codigo,))
    if not plano:
        return jsonify({"erro": "Plano não encontrado."}), 404
    recursos = body.get("recursos")
    execute(
        """UPDATE planos SET nome = ?, preco_mensal_centavos = ?, limite_pacientes = ?, limite_profissionais = ?,
           recursos_json = ?, cor = ? WHERE codigo = ?""",
        (body.get("nome", plano["nome"]), body.get("preco_mensal_centavos", plano["preco_mensal_centavos"]),
         body.get("limite_pacientes", plano["limite_pacientes"]), body.get("limite_profissionais", plano["limite_profissionais"]),
         json.dumps(recursos, ensure_ascii=False) if recursos is not None else plano["recursos_json"],
         body.get("cor", plano["cor"]), codigo),
    )
    log_auditoria(None, u["id"], "atualizar_plano_definicao", "plano", None, codigo)
    return jsonify({"ok": True})


# ---------------------------------------------------------------- Auditoria

@bp.get("/auditoria")
@login_required
@papel_required("admin_master")
def auditoria_global():
    rows = query("SELECT * FROM auditoria ORDER BY criado_em DESC LIMIT 100")
    return jsonify(rows)


# ---------------------------------------------------------------- Painel comercial / Monitoramento

@bp.get("/monitoramento")
@login_required
@papel_required("admin_master")
def monitoramento():
    clinicas = [_enriquecer_clinica(o) for o in query("SELECT * FROM organizacoes")]

    total_clinicas = len(clinicas)
    ativas = [c for c in clinicas if c["status_comercial"] == "ativa"]
    trial = [c for c in clinicas if c["status_comercial"] == "trial"]
    inadimplentes = [c for c in clinicas if c["status_comercial"] == "inadimplente"]
    canceladas = [c for c in clinicas if c["status_comercial"] == "cancelada"]

    mrr_total_centavos = sum(c["mrr_centavos"] for c in clinicas)
    mrr_em_risco_centavos = sum(c["mrr_centavos"] for c in inadimplentes)

    trials_vencendo = sorted(
        [c for c in trial if c["dias_restantes_trial"] is not None and c["dias_restantes_trial"] <= 5],
        key=lambda c: c["dias_restantes_trial"],
    )
    proximas_upsell = sorted(
        [c for c in clinicas if c["uso_pacientes_pct"] is not None and c["uso_pacientes_pct"] >= 80 and c["status_comercial"] == "ativa"],
        key=lambda c: -c["uso_pacientes_pct"],
    )

    por_plano = {}
    for c in clinicas:
        if c["status_comercial"] in ("ativa", "inadimplente"):
            por_plano.setdefault(c["plano"], {"plano": c["plano"], "plano_nome": c["plano_nome"], "total": 0, "mrr_centavos": 0})
            por_plano[c["plano"]]["total"] += 1
            por_plano[c["plano"]]["mrr_centavos"] += c["mrr_centavos"]

    return jsonify({
        "total_clinicas": total_clinicas,
        "total_usuarios": query_one("SELECT COUNT(*) as c FROM usuarios")["c"],
        "total_pacientes": query_one("SELECT COUNT(*) as c FROM pacientes WHERE ativo=1")["c"],
        "total_missoes_concluidas": query_one("SELECT COUNT(*) as c FROM missoes WHERE status='concluida'")["c"],
        "mrr_total_centavos": mrr_total_centavos,
        "mrr_em_risco_centavos": mrr_em_risco_centavos,
        "qtd_ativas": len(ativas), "qtd_trial": len(trial),
        "qtd_inadimplentes": len(inadimplentes), "qtd_canceladas": len(canceladas),
        "clinicas_por_plano": list(por_plano.values()),
        "trials_vencendo": trials_vencendo,
        "oportunidades_upsell": proximas_upsell,
    })


# ---------------------------------------------------------------- Integrações da plataforma
#
# Diferente de /api/integracoes (Módulo 10, escopo por clínica), esta seção
# guarda as credenciais da PRÓPRIA Panda Tech — hoje usadas para cobrar as
# clínicas pelo plano (Mercado Pago). Google Agenda e WhatsApp entram aqui
# por paridade com a Central de Integrações da clínica, mas cada um com o
# nível de integração que já existe de fato (ver descrições abaixo — nenhuma
# aqui finge estar pronta se não estiver).

TIPOS_PLATAFORMA = [
    ("mercadopago", "Gateway de pagamento", "💳",
     "Credencial da própria Panda Tech no Mercado Pago — usada para gerar o PIX que cobra a assinatura de cada clínica nova."),
    ("whatsapp", "WhatsApp Business", "💬",
     "Número da Panda Tech para avisos administrativos (ex: cobrança gerada, clínica inadimplente). Guardado, mas ainda não disparado automaticamente por nenhum fluxo."),
    ("google_calendar", "Google Agenda", "📅",
     "Client ID/Secret do app OAuth da Panda Tech no Google — uma vez configurado aqui, cada clínica conecta a própria agenda sozinha (botão \"Conectar\" na Central de Integrações dela), sem precisar de mais nada de código ou servidor."),
]


@bp.get("/integracoes")
@login_required
@papel_required("admin_master")
def listar_integracoes_plataforma():
    rows = query("SELECT tipo, status FROM integracoes_plataforma")
    por_tipo = {r["tipo"]: r["status"] for r in rows}
    resultado = []
    for tipo, nome, icone, descricao in TIPOS_PLATAFORMA:
        item = {
            "tipo": tipo, "nome": nome, "icone": icone, "descricao": descricao,
            "status": por_tipo.get(tipo, "desconectado"),
        }
        if tipo == "google_calendar":
            item["status"] = "conectado" if calendar_sync_service.credenciais_configuradas() else "desconectado"
            item["redirect_uri_esperado"] = calendar_sync_service.config_oauth_app()["redirect_uri"]
        resultado.append(item)
    return jsonify(resultado)


@bp.post("/integracoes/mercadopago")
@login_required
@papel_required("admin_master")
def configurar_mercadopago_plataforma():
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    access_token = (body.get("access_token") or "").strip()
    if not access_token:
        return jsonify({"erro": "Informe o Access Token do Mercado Pago da Panda Tech (painel Mercado Pago > Suas integrações > Credenciais)."}), 400
    salvar_config_integracao_plataforma(
        "mercadopago",
        {"access_token": access_token, "public_key": (body.get("public_key") or "").strip()},
        status="conectado",
    )
    log_auditoria(None, u["id"], "conectar_integracao_plataforma", "integracao_plataforma", None, "mercadopago configurado")
    return jsonify({"status": "conectado"})


@bp.post("/integracoes/whatsapp")
@login_required
@papel_required("admin_master")
def configurar_whatsapp_plataforma():
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    access_token = (body.get("access_token") or "").strip()
    phone_number_id = (body.get("phone_number_id") or "").strip()
    if not access_token or not phone_number_id:
        return jsonify({"erro": "Informe o Access Token e o Phone Number ID (painel Meta for Developers > WhatsApp > Introdução)."}), 400
    salvar_config_integracao_plataforma(
        "whatsapp",
        {"access_token": access_token, "phone_number_id": phone_number_id},
        status="conectado",
    )
    log_auditoria(None, u["id"], "conectar_integracao_plataforma", "integracao_plataforma", None, "whatsapp configurado")
    return jsonify({"status": "conectado"})


@bp.post("/integracoes/google_calendar")
@login_required
@papel_required("admin_master")
def configurar_google_calendar_plataforma():
    """Guarda o Client ID/Secret do app OAuth da Panda Tech no Google — não é
    credencial de clínica nenhuma, é o que identifica a Panda Tech perante o
    Google (criado uma vez em console.cloud.google.com/apis/credentials).
    Depois disso salvo, cada clínica conecta a própria agenda sozinha (fluxo
    já existente em integracoes_bp.py, sem precisar de nada aqui)."""
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    client_id = (body.get("client_id") or "").strip()
    client_secret = (body.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        return jsonify({"erro": "Informe o Client ID e o Client Secret (Google Cloud Console > APIs e serviços > Credenciais)."}), 400
    redirect_uri = calendar_sync_service.config_oauth_app()["redirect_uri"]
    if not redirect_uri:
        return jsonify({"erro": "Configure a variável ALLOWED_ORIGIN no servidor antes de salvar (é usada para calcular a URL de redirecionamento do Google)."}), 400
    salvar_config_integracao_plataforma(
        "google_calendar",
        {"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri},
        status="conectado",
    )
    log_auditoria(None, u["id"], "conectar_integracao_plataforma", "integracao_plataforma", None, "google_calendar configurado")
    return jsonify({"status": "conectado", "redirect_uri": redirect_uri})

