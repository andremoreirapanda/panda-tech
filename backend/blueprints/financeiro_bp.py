"""
Domínio 7 — Financeiro (Documento 09 / Módulo 07)

Posicionamento estratégico (Documento 10):
"Não pretende substituir um ERP no MVP. Complementa a operação da clínica."
"""
from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute, log_evento, hoje_sql
from auth import login_required, papel_required, paciente_acessivel
from modulos_service import modulo_ativo_para_clinica, financeiro_visivel_para_usuario
import pagamento_service

bp = Blueprint("financeiro", __name__, url_prefix="/api/financeiro")


def _financeiro_habilitado_para(usuario, organizacao_id):
    """Cruza as 3 camadas de Feature Flag para o módulo Financeiro."""
    org = query_one("SELECT plano FROM organizacoes WHERE id = ?", (organizacao_id,))
    if not org or not modulo_ativo_para_clinica(organizacao_id, org["plano"], "financeiro"):
        return False
    if usuario["papel"] == "responsavel":
        return financeiro_visivel_para_usuario(usuario)
    return True  # gestor/profissional/admin: só depende da camada clínica


@bp.get("/paciente/<int:paciente_id>")
@login_required
def listar_cobrancas(paciente_id):
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Sem acesso."}), 403
    paciente = query_one("SELECT organizacao_id FROM pacientes WHERE id = ?", (paciente_id,))
    if not _financeiro_habilitado_para(g.usuario, paciente["organizacao_id"]):
        return jsonify({"erro": "O módulo Financeiro não está disponível para você no momento."}), 403
    rows = query(
        """SELECT c.*, (SELECT forma FROM pagamentos WHERE cobranca_id = c.id ORDER BY id DESC LIMIT 1) as forma_pagamento,
                  (SELECT pago_em FROM pagamentos WHERE cobranca_id = c.id ORDER BY id DESC LIMIT 1) as pago_em
           FROM cobrancas c WHERE c.paciente_id = ? ORDER BY c.vencimento DESC""",
        (paciente_id,),
    )
    return jsonify(rows)


@bp.get("/clinica/resumo")
@login_required
@papel_required("gestor", "admin_master")
def resumo_financeiro_clinica():
    u = g.usuario
    if not _financeiro_habilitado_para(u, u["organizacao_id"]):
        return jsonify({"erro": "O módulo Financeiro não está habilitado para esta clínica."}), 403
    total_mes = query_one(
        """SELECT COALESCE(SUM(valor_centavos),0) as total FROM cobrancas c
           JOIN pacientes p ON p.id = c.paciente_id
           WHERE p.organizacao_id = ? AND c.status='pago' AND substr(c.vencimento, 1, 7) = substr(?, 1, 7)""",
        (u["organizacao_id"], hoje_sql()),
    )["total"]
    pendentes = query_one(
        """SELECT COUNT(*) as c, COALESCE(SUM(valor_centavos),0) as total FROM cobrancas c
           JOIN pacientes p ON p.id = c.paciente_id
           WHERE p.organizacao_id = ? AND c.status='pendente'""",
        (u["organizacao_id"],),
    )
    vencidos = query_one(
        """SELECT COUNT(*) as c FROM cobrancas c
           JOIN pacientes p ON p.id = c.paciente_id
           WHERE p.organizacao_id = ? AND c.status='vencido'""",
        (u["organizacao_id"],),
    )["c"]
    return jsonify({
        "receita_mes_centavos": total_mes,
        "pendentes_qtd": pendentes["c"],
        "pendentes_total_centavos": pendentes["total"],
        "vencidos_qtd": vencidos,
    })


@bp.post("/cobranca")
@login_required
@papel_required("gestor", "admin_master")
def criar_cobranca():
    body = request.get_json(force=True, silent=True) or {}
    paciente_id = body.get("paciente_id")
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Sem acesso."}), 403
    cid = execute(
        "INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento) VALUES (?, ?, ?, ?)",
        (paciente_id, body.get("descricao", "Mensalidade"), body.get("valor_centavos", 0), body["vencimento"]),
    )
    log_evento(g.usuario["organizacao_id"], "cobranca_criada", "cobranca", cid, paciente_id)
    return jsonify({"id": cid}), 201


@bp.post("/cobranca/<int:cobranca_id>/gerar-pix")
@login_required
def gerar_pix(cobranca_id):
    """Gera uma cobrança PIX real no Mercado Pago (QR code + copia-e-cola).
    Requer que a clínica já tenha configurado o Access Token em
    Central de Integrações > Gateway de pagamento. A confirmação do
    pagamento chega sozinha via `POST /api/integracoes/pagamento/webhook`
    — não é preciso chamar `/pagar` manualmente depois de gerar o PIX."""
    cobranca = query_one("SELECT * FROM cobrancas WHERE id = ?", (cobranca_id,))
    if not cobranca:
        return jsonify({"erro": "Cobrança não encontrada."}), 404
    if not paciente_acessivel(cobranca["paciente_id"]):
        return jsonify({"erro": "Sem acesso."}), 403
    if cobranca["status"] == "pago":
        return jsonify({"erro": "Esta cobrança já está paga."}), 409
    try:
        resultado = pagamento_service.criar_pagamento_pix(cobranca_id)
        return jsonify(resultado)
    except RuntimeError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.post("/cobranca/<int:cobranca_id>/pagar")
@login_required
@papel_required("gestor", "admin_master")
def registrar_pagamento(cobranca_id):
    """Confirmação MANUAL de pagamento — para quando a família paga fora do
    app (dinheiro, transferência, PIX direto sem gerar QR pelo app), feita
    pela CLÍNICA depois de conferir que o dinheiro entrou. Quando o
    pagamento é feito via `/gerar-pix`, a confirmação é automática pelo
    webhook do Mercado Pago.

    CORREÇÃO DE SEGURANÇA desta rodada: antes este endpoint só exigia estar
    logado (`@login_required`), sem checar o papel — na prática, a própria
    família (responsável) conseguia se auto-confirmar como "pago" sem pagar
    nada, porque `paciente_acessivel()` também libera responsável. Isso era
    aceitável numa demo sem dinheiro real; deixa de ser aceitável assim que
    a integração de pagamento vira real. Agora só Gestor/Admin confirmam
    manualmente — a família só consegue "pagar" de fato via `/gerar-pix`
    (PIX real) + webhook, que ela não tem como forjar."""
    cobranca = query_one("SELECT * FROM cobrancas WHERE id = ?", (cobranca_id,))
    if not cobranca:
        return jsonify({"erro": "Cobrança não encontrada."}), 404
    if not paciente_acessivel(cobranca["paciente_id"]):
        return jsonify({"erro": "Sem acesso."}), 403
    body = request.get_json(force=True, silent=True) or {}
    execute(
        "INSERT INTO pagamentos (cobranca_id, valor_centavos, forma) VALUES (?, ?, ?)",
        (cobranca_id, cobranca["valor_centavos"], body.get("forma", "pix")),
    )
    execute("UPDATE cobrancas SET status = 'pago' WHERE id = ?", (cobranca_id,))
    org_id = g.usuario["organizacao_id"] or query_one(
        "SELECT organizacao_id FROM pacientes WHERE id=?", (cobranca["paciente_id"],)
    )["organizacao_id"]
    log_evento(org_id, "pagamento_confirmado", "cobranca", cobranca_id, cobranca["paciente_id"])
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Acordos de pagamento (financeiro etapa 1, 07/11/2026)
# ---------------------------------------------------------------------------
import acordos_service
import ausencias_service
from db import log_auditoria  # noqa: F401  (auditoria feita no serviço)


def _paciente_do_acordo_ou_erro(paciente_id):
    """(paciente, None) se o usuário pode mexer; senão (None, resposta de erro)."""
    u = g.usuario
    p = query_one("SELECT id, organizacao_id FROM pacientes WHERE id = ?", (paciente_id,))
    if not p or (u["papel"] != "admin_master" and p["organizacao_id"] != u["organizacao_id"]):
        return None, (jsonify({"erro": "Paciente não encontrado."}), 404)
    if not _financeiro_habilitado_para(u, p["organizacao_id"]):
        return None, (jsonify({"erro": "O módulo Financeiro não está habilitado para esta clínica."}), 403)
    return p, None


def _acordo_ou_erro(acordo_id):
    u = g.usuario
    a = query_one("SELECT * FROM acordos_pagamento WHERE id = ?", (acordo_id,))
    if not a or (u["papel"] != "admin_master" and a["organizacao_id"] != u["organizacao_id"]):
        return None, (jsonify({"erro": "Acordo não encontrado."}), 404)
    if not _financeiro_habilitado_para(u, a["organizacao_id"]):
        return None, (jsonify({"erro": "O módulo Financeiro não está habilitado para esta clínica."}), 403)
    return a, None


@bp.get("/paciente/<int:paciente_id>/acordos")
@login_required
@papel_required("gestor", "secretaria", "admin_master")
def listar_acordos(paciente_id):
    p, erro = _paciente_do_acordo_ou_erro(paciente_id)
    if erro:
        return erro
    rows = query("SELECT * FROM acordos_pagamento WHERE paciente_id = ? ORDER BY status, id DESC", (paciente_id,))
    for r in rows:
        if r["tipo"] == "pacote":
            r["sessoes_usadas"] = query_one(
                "SELECT COUNT(*) AS n FROM acordo_pacote_consumo WHERE acordo_id = ?", (r["id"],))["n"]
        else:
            r["sessoes_usadas"] = None
    return jsonify(rows)


@bp.post("/paciente/<int:paciente_id>/acordos")
@login_required
@papel_required("gestor", "secretaria", "admin_master")
def criar_acordo(paciente_id):
    p, erro = _paciente_do_acordo_ou_erro(paciente_id)
    if erro:
        return erro
    corpo = request.get_json(force=True, silent=True) or {}
    hoje = ausencias_service.hoje_brasilia().isoformat()
    dados, msg = acordos_service.validar(corpo, hoje)
    if msg:
        return jsonify({"erro": msg}), 400
    incluir = corpo.get("incluir_consultas") or []
    if not isinstance(incluir, list) or any(isinstance(i, bool) or not isinstance(i, int) for i in incluir):
        return jsonify({"erro": "Lista de sessões inválida."}), 400
    try:
        acordo_id = acordos_service.criar(p["organizacao_id"], paciente_id, dados, g.usuario, incluir)
    except acordos_service.ConflitoAcordo as e:
        return jsonify({"erro": str(e)}), 409
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400
    return jsonify({"id": acordo_id}), 201


@bp.put("/acordos/<int:acordo_id>")
@login_required
@papel_required("gestor", "secretaria", "admin_master")
def atualizar_acordo(acordo_id):
    a, erro = _acordo_ou_erro(acordo_id)
    if erro:
        return erro
    corpo = request.get_json(force=True, silent=True) or {}
    try:
        acordos_service.atualizar(acordo_id, corpo, g.usuario)
    except acordos_service.ConflitoAcordo as e:
        return jsonify({"erro": str(e)}), 409
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400
    return jsonify({"ok": True})


@bp.post("/acordos/<int:acordo_id>/encerrar")
@login_required
@papel_required("gestor", "secretaria", "admin_master")
def encerrar_acordo(acordo_id):
    a, erro = _acordo_ou_erro(acordo_id)
    if erro:
        return erro
    corpo = request.get_json(force=True, silent=True) or {}
    fim = corpo.get("fim") or ausencias_service.hoje_brasilia().isoformat()
    try:
        acordos_service.encerrar(acordo_id, fim, g.usuario)
    except acordos_service.ConflitoAcordo as e:
        return jsonify({"erro": str(e)}), 409
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400
    return jsonify({"ok": True})


@bp.get("/paciente/<int:paciente_id>/sem-acordo")
@login_required
@papel_required("gestor", "secretaria", "admin_master")
def sessoes_sem_acordo_paciente(paciente_id):
    p, erro = _paciente_do_acordo_ou_erro(paciente_id)
    if erro:
        return erro
    hoje = ausencias_service.hoje_brasilia().isoformat()
    esp = (request.args.get("especialidade") or "").strip() or None
    if esp == "*":
        esp = None
    return jsonify(acordos_service.sessoes_sem_acordo(p["organizacao_id"], paciente_id, esp, hoje))
