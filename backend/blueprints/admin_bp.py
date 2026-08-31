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
    salvar_config_integracao_plataforma, obter_config_integracao_plataforma,
)
from auth import login_required, papel_required, hash_senha
from tokens_service import gerar_token as gerar_token_convite, link_para as link_para_token, gerar_senha_bloqueada
import calendar_sync_service
import pagamento_service
import pagamento_plataforma_service

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _plano_por_codigo(codigo):
    p = query_one("SELECT * FROM planos WHERE codigo = ?", (codigo,))
    if p and p.get("recursos_json"):
        p["recursos"] = json.loads(p["recursos_json"])
    return p


def _plano_valido(codigo):
    """Confere se `codigo` é um plano comercial real e ativo — usado sempre
    que uma clínica escolhe/troca de plano, pra nunca deixar `organizacoes.plano`
    apontar pra um código que não existe (ou que foi desativado) em `planos`."""
    return query_one("SELECT 1 FROM planos WHERE codigo = ? AND ativo = 1", (codigo,)) is not None


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
    plano_escolhido = body.get("plano", "starter")
    if not _plano_valido(plano_escolhido):
        return jsonify({"erro": "Plano inválido — escolha um dos planos comerciais cadastrados em Admin > Planos."}), 400

    # Achado de UAT (26/08/2026): o e-mail do gestor só é único DENTRO da
    # clínica nova que está nascendo (UNIQUE(organizacao_id, email) no
    # schema) — como a organização é sempre nova aqui, isso nunca colidia
    # sozinho, mesmo que o e-mail já pertencesse a uma conta de OUTRA
    # clínica (ou ao admin_master). O login busca só por e-mail, sem
    # filtrar organização (ver auth_bp.py::login), então a conta cujo
    # e-mail colide fica com o login quebrado sem nenhum aviso. Checa ANTES
    # de criar a organização, pra nunca sobrar uma clínica órfã sem gestor.
    gestor_email_checagem = (body.get("gestor_email") or "").strip().lower()
    if gestor_email_checagem and query_one("SELECT 1 FROM usuarios WHERE lower(email) = ?", (gestor_email_checagem,)):
        return jsonify({"erro": "Este e-mail já está em uso em outra conta da plataforma."}), 409

    especialidades = body.get("especialidades") or []
    org_id = execute(
        """INSERT INTO organizacoes (nome, plano, logo_emoji, status_comercial, data_inicio_trial, dias_trial,
                                      contato_nome, contato_email, contato_telefone, origem_lead, observacoes_comerciais,
                                      cnpj, telefone, endereco_cep, endereco_logradouro, endereco_numero,
                                      endereco_bairro, endereco_cidade, endereco_uf, especialidades_json)
           VALUES (?, ?, ?, 'trial', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (nome, plano_escolhido, body.get("logo_emoji", "🌟"), hoje_sql(), body.get("dias_trial", 14),
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
    org = query_one("SELECT id FROM organizacoes WHERE id = ?", (org_id,))
    if not org:
        return jsonify({"erro": "Clínica não encontrada."}), 404
    plano_escolhido = body.get("plano", "starter")
    if not _plano_valido(plano_escolhido):
        return jsonify({"erro": "Plano inválido — escolha um dos planos comerciais cadastrados em Admin > Planos."}), 400
    execute("UPDATE organizacoes SET plano = ? WHERE id = ?", (plano_escolhido, org_id))
    log_auditoria(None, g.usuario["id"], "atualizar_plano", "organizacao", org_id, plano_escolhido)
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

    nome = body.get("nome", plano["nome"])
    if isinstance(nome, str):
        nome = nome.strip()
    if not nome:
        return jsonify({"erro": "Nome do plano é obrigatório."}), 400

    preco = body.get("preco_mensal_centavos", plano["preco_mensal_centavos"])
    if not isinstance(preco, (int, float)) or isinstance(preco, bool) or preco < 0:
        return jsonify({"erro": "Preço mensal inválido — informe um valor maior ou igual a zero."}), 400
    preco = int(round(preco))

    limite_pac = body.get("limite_pacientes", plano["limite_pacientes"])
    if limite_pac is not None and (not isinstance(limite_pac, (int, float)) or isinstance(limite_pac, bool) or limite_pac <= 0):
        return jsonify({"erro": "Limite de pacientes inválido — deixe em branco para ilimitado ou informe um número maior que zero."}), 400
    limite_pac = int(limite_pac) if limite_pac is not None else None

    limite_prof = body.get("limite_profissionais", plano["limite_profissionais"])
    if limite_prof is not None and (not isinstance(limite_prof, (int, float)) or isinstance(limite_prof, bool) or limite_prof <= 0):
        return jsonify({"erro": "Limite de profissionais inválido — deixe em branco para ilimitado ou informe um número maior que zero."}), 400
    limite_prof = int(limite_prof) if limite_prof is not None else None

    # Perfil opcional "Secretária" (insight do usuário, 31/08/2026): diferente
    # dos limites acima, 0 é um valor válido aqui (plano que não inclui o
    # recurso) — por isso a validação aceita >= 0, não só > 0.
    limite_sec = body.get("limite_secretarias", plano.get("limite_secretarias"))
    if limite_sec is not None and (not isinstance(limite_sec, (int, float)) or isinstance(limite_sec, bool) or limite_sec < 0):
        return jsonify({"erro": "Limite de secretárias inválido — deixe em branco para ilimitado ou informe um número maior ou igual a zero."}), 400
    limite_sec = int(limite_sec) if limite_sec is not None else None

    recursos = body.get("recursos")
    execute(
        """UPDATE planos SET nome = ?, preco_mensal_centavos = ?, limite_pacientes = ?, limite_profissionais = ?,
           limite_secretarias = ?, recursos_json = ?, cor = ? WHERE codigo = ?""",
        (nome, preco, limite_pac, limite_prof, limite_sec,
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
        if tipo == "mercadopago":
            item["cobranca_automatica_ativa"] = pagamento_plataforma_service.cobranca_automatica_ativa()
            item["notificacoes"] = pagamento_plataforma_service.notificacoes_ativas()
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
    webhook_secret = (body.get("webhook_secret") or "").strip()
    cfg = {"access_token": access_token, "public_key": (body.get("public_key") or "").strip()}
    if webhook_secret:
        cfg["webhook_secret"] = webhook_secret
    else:
        # Campo deixado em branco: preserva uma chave de webhook já salva
        # antes, em vez de apagá-la sempre que o Admin só atualizar o token.
        anterior = obter_config_integracao_plataforma("mercadopago")
        if anterior.get("webhook_secret"):
            cfg["webhook_secret"] = anterior["webhook_secret"]
    salvar_config_integracao_plataforma(
        "mercadopago",
        cfg,
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


@bp.post("/integracoes/mercadopago/cobranca-automatica")
@login_required
@papel_required("admin_master")
def alternar_cobranca_automatica():
    """Interruptor mestre da cobrança automática das clínicas pelo plano.
    Desligado é o padrão — nenhuma clínica é cobrada até o Admin decidir
    ligar aqui, explicitamente, com o Mercado Pago da Panda Tech já
    configurado."""
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    ativa = bool(body.get("ativa"))
    try:
        pagamento_plataforma_service.definir_cobranca_automatica(ativa)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    log_auditoria(None, u["id"], "alternar_cobranca_automatica_plataforma", "integracao_plataforma", None,
                  f"cobrança automática -> {'ativada' if ativa else 'desativada'}")
    return jsonify({"cobranca_automatica_ativa": ativa})


@bp.post("/integracoes/mercadopago/notificacoes")
@login_required
@papel_required("admin_master")
def alternar_notificacoes_cobranca():
    """Como o Gestor fica sabendo de uma cobrança de plano gerada (ou paga):
    sininho (notificação interna) e/ou WhatsApp da plataforma. O Admin
    escolhe aqui — nenhum dos dois depende do outro."""
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    sininho = bool(body.get("sininho"))
    whatsapp = bool(body.get("whatsapp"))
    pagamento_plataforma_service.definir_notificacoes(sininho, whatsapp)
    log_auditoria(None, u["id"], "alternar_notificacoes_cobranca_plataforma", "integracao_plataforma", None,
                  f"sininho={sininho} whatsapp={whatsapp}")
    return jsonify({"notificar_sininho": sininho, "notificar_whatsapp": whatsapp})


# ---------------------------------------------------------------- Cobrança das clínicas pelo plano

@bp.get("/cobrancas-planos")
@login_required
@papel_required("admin_master")
def listar_cobrancas_planos():
    rows = query(
        """SELECT cp.*, o.nome as organizacao_nome, o.logo_emoji,
                  (SELECT nome FROM planos WHERE codigo = cp.plano_codigo) as plano_nome
           FROM cobrancas_planos cp JOIN organizacoes o ON o.id = cp.organizacao_id
           ORDER BY cp.criado_em DESC LIMIT 200"""
    )
    return jsonify(rows)


@bp.post("/cobrancas-planos/gerar")
@login_required
@papel_required("admin_master")
def gerar_cobrancas_planos():
    """Gera as cobranças do mês corrente pra todas as clínicas ativas/inadimplentes
    que ainda não têm uma — usado pelo botão "Gerar cobranças agora" do Admin
    e, com o mesmo caminho, pelo cron mensal (ver gerar_cobrancas_planos_mensal.py).
    Respeita o interruptor mestre: se a cobrança automática estiver desligada,
    não gera nada (mesmo chamado manualmente)."""
    resultado = pagamento_plataforma_service.gerar_cobrancas_mensais()
    if resultado["executado"]:
        log_auditoria(None, g.usuario["id"], "gerar_cobrancas_planos", "cobranca_plano", None,
                      f"{resultado['geradas']} cobrança(s) gerada(s), {resultado['puladas']} pulada(s)")
    return jsonify(resultado)


@bp.post("/cobrancas-planos/avulsa")
@login_required
@papel_required("admin_master")
def criar_cobranca_plano_avulsa():
    """Cobrança pontual da Panda Tech para uma clínica específica, fora do
    ciclo mensal (ver docstring de criar_cobranca_avulsa em
    pagamento_plataforma_service.py) — usado pelo formulário "Cobrança
    avulsa" em Admin > Cobranças das Clínicas."""
    body = request.get_json(force=True, silent=True) or {}
    organizacao_id = body.get("organizacao_id")
    valor_centavos = body.get("valor_centavos")
    descricao = body.get("descricao")
    gerar_pix_agora = body.get("gerar_pix_agora", True)
    if not organizacao_id or not isinstance(valor_centavos, int):
        return jsonify({"erro": "Informe organizacao_id e valor_centavos (inteiro)."}), 400
    try:
        resultado = pagamento_plataforma_service.criar_cobranca_avulsa(organizacao_id, valor_centavos, descricao, gerar_pix_agora=bool(gerar_pix_agora))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"erro": str(exc)}), 404
    log_auditoria(None, g.usuario["id"], "criar_cobranca_plano_avulsa", "cobranca_plano", resultado["id"],
                  f"organizacao_id={organizacao_id} valor_centavos={valor_centavos} descricao={descricao!r}")
    return jsonify(resultado), 201


@bp.post("/cobrancas-planos/<int:cobranca_id>/gerar-pix")
@login_required
@papel_required("admin_master")
def gerar_pix_plano(cobranca_id):
    try:
        resultado = pagamento_plataforma_service.criar_pagamento_pix(cobranca_id)
        return jsonify(resultado)
    except RuntimeError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.post("/cobrancas-planos/<int:cobranca_id>/marcar-pago")
@login_required
@papel_required("admin_master")
def marcar_pago_plano(cobranca_id):
    try:
        pagamento_plataforma_service.marcar_pago_manual(cobranca_id, g.usuario["id"])
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.post("/integracoes/pagamento/webhook")
def pagamento_plataforma_webhook():
    """Endpoint público — o Mercado Pago (conta da própria Panda Tech) chama
    isso quando o status de uma cobrança de PLANO muda. Sem @login_required
    de propósito: quem chama é o servidor do Mercado Pago, não um navegador
    autenticado no app. A segurança vem da validação de assinatura abaixo,
    usando a chave secreta de webhook da PRÓPRIA Panda Tech (distinta da
    chave de cada clínica — ver pagamento_service.py)."""
    x_signature = request.headers.get("x-signature")
    x_request_id = request.headers.get("x-request-id")
    payment_id = request.args.get("data.id") or (request.get_json(silent=True) or {}).get("data", {}).get("id")
    if not payment_id:
        return jsonify({"ignorado": True}), 200

    secret = pagamento_plataforma_service.webhook_secret_configurado()
    if not pagamento_service.validar_assinatura_webhook(x_signature, x_request_id, str(payment_id), secret):
        return jsonify({"erro": "assinatura inválida"}), 401

    resultado = pagamento_plataforma_service.processar_webhook(payment_id)
    return jsonify(resultado), 200


# ---------------------------------------------------------------- "Sua Assinatura" (visão do Gestor)
#
# Diferente de /admin/cobrancas-planos (visão global do Admin, todas as
# clínicas), esta seção é o que o próprio Gestor vê sobre a assinatura da
# SUA clínica — plano atual, status e o PIX de qualquer cobrança pendente.

@bp.get("/assinatura")
@login_required
@papel_required("gestor")
def minha_assinatura():
    u = g.usuario
    org = query_one("SELECT * FROM organizacoes WHERE id = ?", (u["organizacao_id"],))
    if not org:
        return jsonify({"erro": "Clínica não encontrada."}), 404
    plano = _plano_por_codigo(org["plano"]) or {}

    dias_restantes_trial = None
    if org["status_comercial"] == "trial" and org.get("data_inicio_trial"):
        inicio = datetime.strptime(org["data_inicio_trial"], "%Y-%m-%d")
        fim = inicio + timedelta(days=org.get("dias_trial") or 14)
        dias_restantes_trial = (fim - datetime.now()).days

    cobrancas = query(
        "SELECT * FROM cobrancas_planos WHERE organizacao_id = ? ORDER BY criado_em DESC LIMIT 12",
        (u["organizacao_id"],),
    )
    return jsonify({
        "plano": plano,
        "status_comercial": org["status_comercial"],
        "dias_restantes_trial": dias_restantes_trial,
        "cobrancas": cobrancas,
        # Public Key não é secreta (roda no navegador) — o frontend usa ela
        # pra inicializar o Card Payment Brick nesta mesma tela (Fase 1 do
        # plano de cobrança por cartão). Vem null se a plataforma ainda não
        # configurou (aí o botão "Pagar com cartão" simplesmente não aparece).
        "mercadopago_public_key": pagamento_plataforma_service.public_key_configurado(),
    })


@bp.post("/assinatura/<int:cobranca_id>/gerar-pix")
@login_required
@papel_required("gestor")
def minha_assinatura_gerar_pix(cobranca_id):
    """Deixa o próprio Gestor gerar o PIX de uma cobrança da assinatura dele
    (ex: se a geração automática falhou na hora) — sem depender do Admin.
    Continua usando a credencial da PLATAFORMA (não a do Gestor), então não
    precisa de nada configurado do lado da clínica."""
    cobranca = query_one("SELECT * FROM cobrancas_planos WHERE id = ?", (cobranca_id,))
    if not cobranca or cobranca["organizacao_id"] != g.usuario["organizacao_id"]:
        return jsonify({"erro": "Cobrança não encontrada."}), 404
    try:
        resultado = pagamento_plataforma_service.criar_pagamento_pix(cobranca_id)
        return jsonify(resultado)
    except RuntimeError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.post("/assinatura/<int:cobranca_id>/pagar-cartao")
@login_required
@papel_required("gestor")
def minha_assinatura_pagar_cartao(cobranca_id):
    """Paga uma cobrança da assinatura no cartão de crédito — o próprio
    Gestor é quem digita os dados do cartão no Card Payment Brick (é o dono
    do cartão, então é ele quem deve preenchê-lo, nunca o Admin em nome
    dele); o Brick tokeniza tudo no navegador antes de chegar aqui, então o
    que recebemos já vem sem o número do cartão. Fase 1 do plano de cobrança
    por cartão (26/08/2026) — só Plataforma → Clínicas por enquanto."""
    cobranca = query_one("SELECT * FROM cobrancas_planos WHERE id = ?", (cobranca_id,))
    if not cobranca or cobranca["organizacao_id"] != g.usuario["organizacao_id"]:
        return jsonify({"erro": "Cobrança não encontrada."}), 404

    body = request.get_json(force=True, silent=True) or {}
    token = (body.get("token") or "").strip()
    payment_method_id = (body.get("payment_method_id") or "").strip()
    payer = body.get("payer") or {}
    payer_email = (payer.get("email") or "").strip()
    if not token or not payment_method_id or not payer_email:
        return jsonify({"erro": "Dados do cartão incompletos."}), 400

    try:
        resultado = pagamento_plataforma_service.criar_pagamento_cartao(
            cobranca_id, token, payment_method_id, body.get("installments") or 1,
            payer_email, payer.get("identification"), body.get("issuer_id"),
        )
        return jsonify(resultado)
    except RuntimeError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.post("/assinatura/<int:cobranca_id>/checkout-cartao")
@login_required
@papel_required("gestor")
def minha_assinatura_checkout_cartao(cobranca_id):
    """Fallback do pagamento no cartão via Checkout Pro (link hospedado pela
    própria Mercado Pago, aberto em nova aba) — criado depois de confirmar
    ao vivo que o Card Payment Brick embutido (rota acima) trava na
    inicialização nesta conta, mesmo com CSP e chave pública corretos (ver
    o comentário em criar_checkout_cartao, em pagamento_plataforma_service).
    Devolve só a URL; quem abre a nova aba é o frontend."""
    cobranca = query_one("SELECT * FROM cobrancas_planos WHERE id = ?", (cobranca_id,))
    if not cobranca or cobranca["organizacao_id"] != g.usuario["organizacao_id"]:
        return jsonify({"erro": "Cobrança não encontrada."}), 404

    try:
        resultado = pagamento_plataforma_service.criar_checkout_cartao(cobranca_id)
        return jsonify(resultado)
    except RuntimeError as exc:
        return jsonify({"erro": str(exc)}), 400

