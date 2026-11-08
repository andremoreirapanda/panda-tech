"""
Domínio 7 — Financeiro (Documento 09 / Módulo 07)

Posicionamento estratégico (Documento 10):
"Não pretende substituir um ERP no MVP. Complementa a operação da clínica."
"""
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute, em_lote, log_evento, log_auditoria, criar_notificacao, hoje_sql
from auth import login_required, papel_required, paciente_acessivel
from modulos_service import modulo_ativo_para_clinica, financeiro_visivel_para_usuario
import pagamento_service
import cobranca_service

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
@papel_required("gestor", "secretaria", "admin_master")
def criar_cobranca():
    """Cobrança manual (fora do ciclo automático): tipo 'manual', já pendente."""
    body, erro = _corpo_json()
    if erro:
        return erro
    paciente_id = body.get("paciente_id")
    if isinstance(paciente_id, bool) or not isinstance(paciente_id, int):
        return jsonify({"erro": "Paciente inválido."}), 400
    u = g.usuario
    p = query_one("SELECT id, organizacao_id FROM pacientes WHERE id = ?", (paciente_id,))
    if not p or (u["papel"] != "admin_master" and p["organizacao_id"] != u["organizacao_id"]):
        return jsonify({"erro": "Sem acesso."}), 403
    if not _financeiro_habilitado_para(u, p["organizacao_id"]):
        return jsonify({"erro": "O módulo Financeiro não está habilitado para esta clínica."}), 403
    valor = body.get("valor_centavos")
    if isinstance(valor, bool) or not isinstance(valor, int) or not (0 < valor <= LIMITE_CENTAVOS):
        return jsonify({"erro": "Informe um valor maior que zero."}), 400
    vencimento = _data_iso(body.get("vencimento"))
    if not vencimento:
        return jsonify({"erro": "Informe o vencimento (AAAA-MM-DD)."}), 400
    descricao = body.get("descricao", "Mensalidade")
    if not isinstance(descricao, str) or not descricao.strip() or len(descricao) > 200:
        return jsonify({"erro": "Descrição inválida (até 200 caracteres)."}), 400
    cid = execute(
        """INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status, organizacao_id, tipo)
           VALUES (?, ?, ?, ?, 'pendente', ?, 'manual')""",
        (paciente_id, descricao.strip(), valor, vencimento, p["organizacao_id"]),
    )
    log_evento(p["organizacao_id"], "cobranca_criada", "cobranca", cid, paciente_id)
    log_auditoria(p["organizacao_id"], u["id"], "criar", "cobranca", cid, f"manual · {valor} centavos · {descricao.strip()}")
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
    if cobranca["status"] in ("rascunho", "cancelado"):
        return jsonify({"erro": "Esta cobrança ainda não está disponível para pagamento."}), 409
    try:
        resultado = pagamento_service.criar_pagamento_pix(cobranca_id)
        return jsonify(resultado)
    except RuntimeError as exc:
        return jsonify({"erro": str(exc)}), 400


# ---------------------------------------------------------------------------
# Baixa, estorno, conferência e pendências (financeiro etapa 1, 07/11/2026)
# ---------------------------------------------------------------------------
LIMITE_CENTAVOS = 100_000_000
FORMAS_BAIXA = ("pix", "dinheiro", "cartao_credito", "cartao_debito", "transferencia")
PAPEIS_BAIXA = ("gestor", "secretaria", "admin_master")
PAPEIS_GESTAO = ("gestor", "admin_master")


def _corpo_json():
    """(dict, None) ou (None, resposta 400): o corpo precisa ser um objeto JSON (vazio vale {})."""
    bruto = request.get_json(force=True, silent=True)
    if bruto is None:
        if request.get_data():
            return None, (jsonify({"erro": "Corpo da requisição inválido."}), 400)
        return {}, None
    if not isinstance(bruto, dict):
        return None, (jsonify({"erro": "Corpo da requisição inválido."}), 400)
    return bruto, None


def _data_iso(valor):
    if not isinstance(valor, str) or len(valor) != 10:
        return None
    try:
        return date.fromisoformat(valor).isoformat()
    except ValueError:
        return None


def _agora_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _hoje_iso():
    return ausencias_service.hoje_brasilia().isoformat()


def _cobranca_ou_erro(cobranca_id):
    """(cobranca com `org_id`, None) ou (None, erro). Outra clínica → 404."""
    u = g.usuario
    c = query_one(
        """SELECT c.*, COALESCE(c.organizacao_id, p.organizacao_id) AS org_id
           FROM cobrancas c JOIN pacientes p ON p.id = c.paciente_id WHERE c.id = ?""", (cobranca_id,))
    if not c or (u["papel"] != "admin_master" and c["org_id"] != u["organizacao_id"]):
        return None, (jsonify({"erro": "Cobrança não encontrada."}), 404)
    if not _financeiro_habilitado_para(u, c["org_id"]):
        return None, (jsonify({"erro": "O módulo Financeiro não está habilitado para esta clínica."}), 403)
    return c, None


def _motivo(valor, obrigatorio):
    """(texto, None) ou (None, mensagem)."""
    if valor is None or valor == "":
        return (None, "Informe o motivo.") if obrigatorio else ("", None)
    if not isinstance(valor, str) or len(valor.strip()) > 200:
        return None, "Motivo inválido (até 200 caracteres)."
    texto = valor.strip()
    if obrigatorio and not texto:
        return None, "Informe o motivo."
    return texto, None


def _travar_cobranca(cobranca_id):
    """Primeira instrução de toda gravação sobre uma cobrança: trava a linha (Postgres) ou
    a base (SQLite) até o commit, para que duas baixas/cancelamentos simultâneos se enfileirem."""
    execute("UPDATE cobrancas SET status = status WHERE id = ?", (cobranca_id,))


def _nao_cobrar(consulta_id, motivo, usuario_id):
    execute("DELETE FROM consulta_decisao_cobranca WHERE consulta_id = ?", (consulta_id,))
    execute("""INSERT INTO consulta_decisao_cobranca (consulta_id, decisao, motivo, decidido_por)
               VALUES (?, 'nao_cobrar', ?, ?)""", (consulta_id, motivo, usuario_id))


@bp.post("/cobranca/<int:cobranca_id>/pagar")
@login_required
@papel_required(*PAPEIS_BAIXA)
def registrar_pagamento(cobranca_id):
    """Baixa MANUAL (total ou parcial) feita pela clínica depois de conferir que o
    dinheiro entrou. A família nunca dá baixa (correção de segurança antiga): ela só
    paga pelo PIX do app, confirmado pelo webhook do Mercado Pago."""
    c, erro = _cobranca_ou_erro(cobranca_id)
    if erro:
        return erro
    body, erro = _corpo_json()
    if erro:
        return erro
    if c["status"] in ("rascunho", "cancelado"):
        return jsonify({"erro": "Esta cobrança não aceita pagamento (rascunho ou cancelada)."}), 409
    forma = body.get("forma")
    if forma not in FORMAS_BAIXA:
        return jsonify({"erro": "Informe a forma de pagamento."}), 400
    valor = body.get("valor_centavos")
    if valor is not None and (isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0):
        return jsonify({"erro": "Informe um valor maior que zero."}), 400
    hoje = _hoje_iso()
    data = body.get("data")
    pago_em = None
    if data not in (None, ""):
        data = _data_iso(data)
        if not data or data > hoje:
            return jsonify({"erro": "Data do pagamento inválida (não pode ser futura)."}), 400
        pago_em = f"{data} 12:00:00"
    u = g.usuario
    with em_lote():
        _travar_cobranca(cobranca_id)
        atual = query_one("SELECT status FROM cobrancas WHERE id = ?", (cobranca_id,))
        if atual["status"] in ("rascunho", "cancelado"):
            return jsonify({"erro": "Esta cobrança não aceita pagamento (rascunho ou cancelada)."}), 409
        saldo = pagamento_service.saldo_centavos(cobranca_id)
        if saldo <= 0:
            return jsonify({"erro": "Esta cobrança já está paga."}), 409
        if valor is None:
            valor = saldo
        if valor > saldo:
            return jsonify({"erro": "O valor é maior que o saldo da cobrança."}), 400
        if pago_em:
            pid = execute(
                """INSERT INTO pagamentos (cobranca_id, valor_centavos, forma, pago_em, recebido_por_usuario_id, recebido_por_nome)
                   VALUES (?, ?, ?, ?, ?, ?)""", (cobranca_id, valor, forma, pago_em, u["id"], u["nome"]))
        else:
            pid = execute(
                """INSERT INTO pagamentos (cobranca_id, valor_centavos, forma, recebido_por_usuario_id, recebido_por_nome)
                   VALUES (?, ?, ?, ?, ?)""", (cobranca_id, valor, forma, u["id"], u["nome"]))
        status = pagamento_service.recalcular_status(cobranca_id, hoje)
        log_auditoria(c["org_id"], u["id"], "baixa", "cobranca", cobranca_id,
                      f"{valor} centavos · {forma} · pagamento {pid} · {status}")
    log_evento(c["org_id"], "pagamento_confirmado", "cobranca", cobranca_id, c["paciente_id"])
    return jsonify({"ok": True, "pagamento_id": pid, "status": status})


@bp.post("/pagamento/<int:pagamento_id>/estornar")
@login_required
@papel_required(*PAPEIS_GESTAO)
def estornar_pagamento(pagamento_id):
    pg = query_one("SELECT * FROM pagamentos WHERE id = ?", (pagamento_id,))
    if not pg:
        return jsonify({"erro": "Pagamento não encontrado."}), 404
    c, erro = _cobranca_ou_erro(pg["cobranca_id"])
    if erro:
        if erro[1] == 404:
            return jsonify({"erro": "Pagamento não encontrado."}), 404
        return erro
    body, erro = _corpo_json()
    if erro:
        return erro
    motivo, msg = _motivo(body.get("motivo"), True)
    if msg:
        return jsonify({"erro": msg}), 400
    u = g.usuario
    with em_lote():
        _travar_cobranca(c["id"])
        if query_one("SELECT estornado_em FROM pagamentos WHERE id = ?", (pagamento_id,))["estornado_em"]:
            return jsonify({"erro": "Este pagamento já foi estornado."}), 409
        execute("UPDATE pagamentos SET estornado_em = ?, estorno_motivo = ?, estornado_por = ? WHERE id = ?",
                (_agora_iso(), motivo, u["id"], pagamento_id))
        status = pagamento_service.recalcular_status(c["id"], _hoje_iso())
        log_auditoria(c["org_id"], u["id"], "estornar", "cobranca", c["id"],
                      f"pagamento {pagamento_id} · {pg['valor_centavos']} centavos · {motivo} · {status}")
    return jsonify({"ok": True, "status": status})


@bp.post("/cobranca/<int:cobranca_id>/liberar")
@login_required
@papel_required(*PAPEIS_BAIXA)
def liberar_cobranca(cobranca_id):
    c, erro = _cobranca_ou_erro(cobranca_id)
    if erro:
        return erro
    _, erro = _corpo_json()
    if erro:
        return erro
    hoje = _hoje_iso()
    if c["status"] != "rascunho":
        return jsonify({"erro": "Só um rascunho pode ser liberado."}), 409
    if not c["periodo_fim"] or str(c["periodo_fim"])[:10] >= hoje:
        return jsonify({"erro": "O período ainda não terminou."}), 409
    u = g.usuario
    with em_lote():
        _travar_cobranca(cobranca_id)
        if query_one("SELECT status FROM cobrancas WHERE id = ?", (cobranca_id,))["status"] != "rascunho":
            return jsonify({"erro": "Só um rascunho pode ser liberado."}), 409
        execute("UPDATE cobrancas SET status = 'pendente', liberada_em = ? WHERE id = ?", (_agora_iso(), cobranca_id))
        status = pagamento_service.recalcular_status(cobranca_id, hoje)   # 100% de desconto já nasce paga
        log_auditoria(c["org_id"], u["id"], "liberar", "cobranca", cobranca_id, f"{c['descricao']} · {status}")
    for r in query("SELECT usuario_id FROM responsaveis_pacientes WHERE paciente_id = ?", (c["paciente_id"],)):
        criar_notificacao(r["usuario_id"], "Nova cobrança disponível",
                          "A clínica liberou uma nova cobrança. Veja em Financeiro.",
                          "info", "paciente", c["paciente_id"])
    return jsonify({"ok": True, "status": status})


@bp.put("/cobranca/<int:cobranca_id>/conferir")
@login_required
@papel_required(*PAPEIS_BAIXA)
def conferir_cobranca(cobranca_id):
    c, erro = _cobranca_ou_erro(cobranca_id)
    if erro:
        return erro
    body, erro = _corpo_json()
    if erro:
        return erro
    if c["status"] != "rascunho":
        return jsonify({"erro": "Só um rascunho pode ser conferido."}), 409
    desconto = body.get("desconto_centavos", c["desconto_centavos"] or 0)
    if isinstance(desconto, bool) or not isinstance(desconto, int) or desconto < 0:
        return jsonify({"erro": "Desconto inválido."}), 400
    motivo, msg = _motivo(body["desconto_motivo"] if "desconto_motivo" in body else c["desconto_motivo"], desconto > 0)
    if msg:
        return jsonify({"erro": "Informe o motivo do desconto." if msg == "Informe o motivo." else msg}), 400
    remover = body.get("remover_itens", [])
    if not isinstance(remover, list) or any(isinstance(i, bool) or not isinstance(i, int) for i in remover):
        return jsonify({"erro": "Lista de sessões inválida."}), 400
    remover = set(remover)
    itens = {i["id"]: i for i in query("SELECT * FROM cobranca_itens WHERE cobranca_id = ?", (cobranca_id,))}
    if any(i not in itens for i in remover):
        return jsonify({"erro": "Sessão não pertence a esta cobrança."}), 400
    restante = sum(i["valor_centavos"] for k, i in itens.items() if k not in remover)
    if desconto > restante:
        return jsonify({"erro": "O desconto não pode passar do valor da cobrança."}), 400
    u = g.usuario
    with em_lote():
        for item_id in remover:
            _nao_cobrar(itens[item_id]["consulta_id"], "Retirado na conferência", u["id"])
            execute("DELETE FROM cobranca_itens WHERE id = ?", (item_id,))
        cobranca_service._recalcular(cobranca_id)
        atual = query_one("SELECT status FROM cobrancas WHERE id = ?", (cobranca_id,))
        if atual["status"] != "cancelado":
            execute("UPDATE cobrancas SET desconto_centavos = ?, desconto_motivo = ? WHERE id = ?",
                    (desconto, motivo if desconto > 0 else None, cobranca_id))
        log_auditoria(c["org_id"], u["id"], "conferir", "cobranca", cobranca_id,
                      f"desconto {desconto} centavos · {len(remover)} sessão(ões) retirada(s)"
                      + (f" · {motivo}" if desconto > 0 else ""))
    nova = query_one("SELECT status, valor_centavos, desconto_centavos FROM cobrancas WHERE id = ?", (cobranca_id,))
    return jsonify({"ok": True, **nova})


@bp.post("/cobranca/<int:cobranca_id>/cancelar")
@login_required
@papel_required(*PAPEIS_GESTAO)
def cancelar_cobranca(cobranca_id):
    c, erro = _cobranca_ou_erro(cobranca_id)
    if erro:
        return erro
    body, erro = _corpo_json()
    if erro:
        return erro
    motivo, msg = _motivo(body.get("motivo"), True)
    if msg:
        return jsonify({"erro": msg}), 400
    u = g.usuario
    with em_lote():
        _travar_cobranca(cobranca_id)
        if query_one("SELECT status FROM cobrancas WHERE id = ?", (cobranca_id,))["status"] == "cancelado":
            return jsonify({"erro": "Esta cobrança já está cancelada."}), 409
        if query_one("SELECT 1 AS x FROM pagamentos WHERE cobranca_id = ? AND estornado_em IS NULL", (cobranca_id,)):
            return jsonify({"erro": "Há pagamento nesta cobrança: estorne antes de cancelar."}), 409
        for it in query("SELECT consulta_id FROM cobranca_itens WHERE cobranca_id = ?", (cobranca_id,)):
            _nao_cobrar(it["consulta_id"], f"Cobrança cancelada: {motivo}", u["id"])
        execute("DELETE FROM cobranca_itens WHERE cobranca_id = ?", (cobranca_id,))
        execute("UPDATE cobrancas SET status = 'cancelado', revisar = 0 WHERE id = ?", (cobranca_id,))
        log_auditoria(c["org_id"], u["id"], "cancelar", "cobranca", cobranca_id,
                      f"{c['valor_centavos']} centavos · {motivo}")
    return jsonify({"ok": True})


@bp.post("/cobranca/<int:cobranca_id>/resolver-revisao")
@login_required
@papel_required(*PAPEIS_GESTAO)
def resolver_revisao(cobranca_id):
    c, erro = _cobranca_ou_erro(cobranca_id)
    if erro:
        return erro
    _, erro = _corpo_json()
    if erro:
        return erro
    u = g.usuario
    with em_lote():
        # o motivo fica guardado: a próxima sincronização não deve avisar de novo
        execute("UPDATE cobrancas SET revisar = 0 WHERE id = ?", (cobranca_id,))
        log_auditoria(c["org_id"], u["id"], "resolver_revisao", "cobranca", cobranca_id, c["revisar_motivo"] or "")
    return jsonify({"ok": True})


@bp.post("/sessoes/<int:consulta_id>/decisao")
@login_required
@papel_required(*PAPEIS_BAIXA)
def decidir_sessao(consulta_id):
    u = g.usuario
    s = query_one("""SELECT c.id, p.organizacao_id AS org_id FROM consultas c
                     JOIN pacientes p ON p.id = c.paciente_id WHERE c.id = ?""", (consulta_id,))
    if not s or (u["papel"] != "admin_master" and s["org_id"] != u["organizacao_id"]):
        return jsonify({"erro": "Sessão não encontrada."}), 404
    if not _financeiro_habilitado_para(u, s["org_id"]):
        return jsonify({"erro": "O módulo Financeiro não está habilitado para esta clínica."}), 403
    body, erro = _corpo_json()
    if erro:
        return erro
    decisao = body.get("decisao")
    if decisao not in ("nao_cobrar", "valor"):
        return jsonify({"erro": "Decisão inválida."}), 400
    if decisao == "nao_cobrar" and u["papel"] not in PAPEIS_GESTAO:
        return jsonify({"erro": "Só o gestor decide não cobrar uma sessão."}), 403
    motivo, msg = _motivo(body.get("motivo"), decisao == "nao_cobrar")
    if msg:
        return jsonify({"erro": msg}), 400
    valor = None
    if decisao == "valor":
        valor = body.get("valor_centavos")
        if isinstance(valor, bool) or not isinstance(valor, int) or not (1 <= valor <= LIMITE_CENTAVOS):
            return jsonify({"erro": "Informe um valor maior que zero."}), 400
    if query_one("SELECT 1 AS x FROM cobranca_itens WHERE consulta_id = ?", (consulta_id,)):
        return jsonify({"erro": "Esta sessão já está numa cobrança."}), 409
    with em_lote():
        execute("DELETE FROM consulta_decisao_cobranca WHERE consulta_id = ?", (consulta_id,))
        execute("""INSERT INTO consulta_decisao_cobranca (consulta_id, decisao, valor_centavos, motivo, decidido_por)
                   VALUES (?, ?, ?, ?, ?)""", (consulta_id, decisao, valor, motivo or None, u["id"]))
        log_auditoria(s["org_id"], u["id"], "decisao", "consulta", consulta_id,
                      decisao + (f" · {valor} centavos" if valor else "") + (f" · {motivo}" if motivo else ""))
    return jsonify({"ok": True})


@bp.post("/paciente/<int:paciente_id>/cobrar-avulsas")
@login_required
@papel_required(*PAPEIS_BAIXA)
def cobrar_avulsas(paciente_id):
    p, erro = _paciente_do_acordo_ou_erro(paciente_id)
    if erro:
        return erro
    body, erro = _corpo_json()
    if erro:
        return erro
    ids = body.get("consulta_ids")
    if (not isinstance(ids, list) or not ids or len(set(ids)) != len(ids)
            or any(isinstance(i, bool) or not isinstance(i, int) for i in ids)):
        return jsonify({"erro": "Escolha as sessões a cobrar."}), 400
    hoje = _hoje_iso()
    org_id = p["organizacao_id"]
    u = g.usuario
    disponiveis = {s["consulta_id"]: s for s in acordos_service.sessoes_sem_acordo(org_id, paciente_id, None, hoje)}
    if any(i not in disponiveis for i in ids):
        return jsonify({"erro": "Alguma sessão não está disponível para cobrança avulsa."}), 400
    valores = {}
    for i in ids:
        d = query_one("SELECT valor_centavos FROM consulta_decisao_cobranca WHERE consulta_id = ? AND decisao = 'valor'", (i,))
        v = (d["valor_centavos"] if d else None) or disponiveis[i]["procedimento_valor_centavos"] or 0
        if v <= 0:
            return jsonify({"erro": "Há sessão sem valor: defina o valor antes de cobrar."}), 400
        valores[i] = v
    total = sum(valores.values())
    vencimento = (date.fromisoformat(hoje) + timedelta(days=5)).isoformat()
    descricao = "Sessões avulsas" if len(ids) > 1 else "Sessão avulsa"
    try:
        with em_lote():
            cid = execute(
                """INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status, organizacao_id, tipo)
                   VALUES (?, ?, ?, ?, 'pendente', ?, 'avulsa')""",
                (paciente_id, descricao, total, vencimento, org_id))
            for i in ids:
                s = disponiveis[i]
                execute("""INSERT INTO cobranca_itens (cobranca_id, consulta_id, data_hora, procedimento_nome, valor_centavos)
                           VALUES (?, ?, ?, ?, ?)""", (cid, i, s["data_hora"], s["procedimento_nome"], valores[i]))
            log_auditoria(org_id, u["id"], "criar", "cobranca", cid, f"avulsa · {len(ids)} sessão(ões) · {total} centavos")
    except Exception as e:
        if cobranca_service._violacao_unica(e):   # outra cobrança pegou a sessão no meio
            return jsonify({"erro": "Alguma sessão já entrou em outra cobrança."}), 409
        raise
    return jsonify({"id": cid, "valor_centavos": total, "vencimento": vencimento}), 201


# ---------------------------------------------------------------------------
# Acordos de pagamento (financeiro etapa 1, 07/11/2026)
# ---------------------------------------------------------------------------
import acordos_service
import ausencias_service


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
