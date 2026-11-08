"""
Domínio 7 — Financeiro (Documento 09 / Módulo 07)

Posicionamento estratégico (Documento 10):
"Não pretende substituir um ERP no MVP. Complementa a operação da clínica."
"""
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute, em_lote, log_evento, log_auditoria, criar_notificacao
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


def _montar_cobrancas(org_id, where="", params=(), familia=False):
    """Cobranças da clínica no formato das telas (itens e pagamentos juntos, sem N+1)."""
    hoje = _hoje_iso()
    rows = query(
        f"""SELECT cb.*, p.nome AS paciente_nome, ac.especialidade AS acordo_especialidade
            FROM cobrancas cb JOIN pacientes p ON p.id = cb.paciente_id
            LEFT JOIN acordos_pagamento ac ON ac.id = cb.acordo_id
            WHERE COALESCE(cb.organizacao_id, p.organizacao_id) = ? {where}
            ORDER BY cb.vencimento DESC, cb.id DESC""", (org_id, *params))
    ids = [r["id"] for r in rows]
    itens, pagtos = {}, {}
    if ids:
        marc = ", ".join("?" for _ in ids)
        for it in query(
                f"""SELECT i.cobranca_id, i.id, i.consulta_id, i.data_hora, i.procedimento_nome, i.valor_centavos,
                           c.especialidade
                    FROM cobranca_itens i JOIN consultas c ON c.id = i.consulta_id
                    WHERE i.cobranca_id IN ({marc}) ORDER BY i.data_hora, i.id""", tuple(ids)):
            itens.setdefault(it["cobranca_id"], []).append(it)
        for pg in query(f"SELECT * FROM pagamentos WHERE cobranca_id IN ({marc}) ORDER BY pago_em, id", tuple(ids)):
            pagtos.setdefault(pg["cobranca_id"], []).append(pg)
    saida = []
    for r in rows:
        todos = pagtos.get(r["id"], [])
        validos = [x for x in todos if not x["estornado_em"]]
        pago = sum(x["valor_centavos"] for x in validos)
        a_pagar = r["valor_centavos"] - (r["desconto_centavos"] or 0)
        esp = r["acordo_especialidade"] if r["acordo_especialidade"] not in (None, "*") else None
        lista_itens = []
        for it in itens.get(r["id"], []):
            esp = esp or it["especialidade"]
            lista_itens.append({k: it[k] for k in ("id", "consulta_id", "data_hora", "procedimento_nome", "valor_centavos")})
        lista_pg = []
        for x in (validos if familia else todos):
            d = {k: x[k] for k in ("id", "valor_centavos", "forma", "pago_em")}
            if not familia:
                d.update({k: x[k] for k in ("recebido_por_usuario_id", "recebido_por_nome", "mp_payment_id",
                                            "estornado_em", "estorno_motivo", "estornado_por")})
            lista_pg.append(d)
        ultimo = validos[-1] if validos else None
        d = {
            "id": r["id"], "paciente_id": r["paciente_id"], "paciente_nome": r["paciente_nome"], "tipo": r["tipo"],
            "descricao": r["descricao"], "especialidade": esp, "periodo_inicio": r["periodo_inicio"],
            "periodo_fim": r["periodo_fim"], "vencimento": r["vencimento"], "status": r["status"],
            "aberta": bool(r["status"] == "rascunho" and r["periodo_fim"] and str(r["periodo_fim"])[:10] >= hoje),
            "valor_centavos": r["valor_centavos"], "desconto_centavos": r["desconto_centavos"] or 0,
            "desconto_motivo": r["desconto_motivo"], "a_pagar_centavos": a_pagar, "pago_centavos": pago,
            "saldo_centavos": a_pagar - pago,
            "forma_pagamento": ultimo["forma"] if ultimo else None, "pago_em": ultimo["pago_em"] if ultimo else None,
            "itens": lista_itens, "pagamentos": lista_pg,
        }
        if not familia:
            d["revisar"] = bool(r["revisar"])
            d["revisar_motivo"] = r["revisar_motivo"]
        saida.append(d)
    return saida


@bp.get("/paciente/<int:paciente_id>")
@login_required
def listar_cobrancas(paciente_id):
    u = g.usuario
    if u["papel"] == "secretaria":
        # paciente_acessivel não tem ramo da secretária (o Diário segue fechado para ela):
        # aqui basta o paciente ser da mesma clínica.
        ok = query_one("SELECT 1 FROM pacientes WHERE id = ? AND organizacao_id = ?",
                       (paciente_id, u["organizacao_id"]))
        if not ok:
            return jsonify({"erro": "Sem acesso."}), 403
    elif not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Sem acesso."}), 403
    paciente = query_one("SELECT organizacao_id FROM pacientes WHERE id = ?", (paciente_id,))
    if not _financeiro_habilitado_para(g.usuario, paciente["organizacao_id"]):
        return jsonify({"erro": "O módulo Financeiro não está disponível para você no momento."}), 403
    familia = g.usuario["papel"] == "responsavel"
    if not familia and g.usuario["papel"] not in PAPEIS_BAIXA:
        return jsonify({"erro": "Sem acesso."}), 403
    cobranca_service.sincronizar(paciente["organizacao_id"])
    where = " AND cb.paciente_id = ?"
    if familia:
        where += " AND cb.status NOT IN ('rascunho', 'cancelado')"
    return jsonify(_montar_cobrancas(paciente["organizacao_id"], where, (paciente_id,), familia))


def _org_financeiro_ou_erro():
    """(org_id, None) ou (None, erro) para as rotas da clínica (gestor/secretária/admin)."""
    u = g.usuario
    org_id = u["organizacao_id"]
    if not org_id or not _financeiro_habilitado_para(u, org_id):
        return None, (jsonify({"erro": "O módulo Financeiro não está habilitado para esta clínica."}), 403)
    return org_id, None


@bp.get("/cobrancas")
@login_required
@papel_required("gestor", "secretaria", "admin_master")
def listar_cobrancas_clinica():
    org_id, erro = _org_financeiro_ou_erro()
    if erro:
        return erro
    de = request.args.get("de") or None
    ate = request.args.get("ate") or None
    if (de and not _data_iso(de)) or (ate and not _data_iso(ate)):
        return jsonify({"erro": "Datas inválidas (AAAA-MM-DD)."}), 400
    paciente_id = request.args.get("paciente_id") or None
    if paciente_id is not None:
        try:
            paciente_id = int(paciente_id)
        except ValueError:
            return jsonify({"erro": "Paciente inválido."}), 400
    status = request.args.get("status") or None
    if status and status not in ("rascunho", "pendente", "parcial", "pago", "vencido", "cancelado"):
        return jsonify({"erro": "Status inválido."}), 400
    esp = (request.args.get("especialidade") or "").strip().lower()

    cobranca_service.sincronizar(org_id)
    abertas = ("pendente", "parcial", "vencido")
    # Período: de/ate/status valem para o que vence no período; com `de`, as dívidas
    # abertas de antes dele também entram (não somem só porque o mês virou).
    per, params = "", []
    if de:
        per += " AND substr(cb.vencimento, 1, 10) >= ?"
        params.append(de)
    if ate:
        per += " AND substr(cb.vencimento, 1, 10) <= ?"
        params.append(ate)
    if status:
        per += " AND cb.status = ?"
        params.append(status)
    where = per
    if de and (not status or status in abertas):
        antigas = " AND substr(cb.vencimento, 1, 10) < ? AND cb.status IN ('pendente', 'parcial', 'vencido')"
        ps_antigas = [de]
        if status:
            antigas += " AND cb.status = ?"
            ps_antigas.append(status)
        where = f" AND (({per[5:]}) OR ({antigas[5:]}))"
        params = params + ps_antigas
    if paciente_id is not None:
        where += " AND cb.paciente_id = ?"
        params.append(paciente_id)
    lista = _montar_cobrancas(org_id, where, tuple(params))
    if esp:
        lista = [c for c in lista if (c["especialidade"] or "").strip().lower() == esp]

    vivas = [c for c in lista if c["status"] in ("pendente", "parcial", "vencido")]
    # A especialidade é a mesma de `_montar_cobrancas`: a do acordo ou, no "todas", a da 1ª sessão.
    sql = """SELECT pg.valor_centavos, COALESCE(NULLIF(ac.especialidade, '*'),
                 (SELECT c.especialidade FROM cobranca_itens i JOIN consultas c ON c.id = i.consulta_id
                  WHERE i.cobranca_id = cb.id ORDER BY i.data_hora, i.id LIMIT 1)) AS especialidade
             FROM pagamentos pg
             JOIN cobrancas cb ON cb.id = pg.cobranca_id JOIN pacientes p ON p.id = cb.paciente_id
             LEFT JOIN acordos_pagamento ac ON ac.id = cb.acordo_id
             WHERE COALESCE(cb.organizacao_id, p.organizacao_id) = ? AND pg.estornado_em IS NULL"""
    ps = [org_id]
    if de:
        sql += " AND substr(pg.pago_em, 1, 10) >= ?"
        ps.append(de)
    if ate:
        sql += " AND substr(pg.pago_em, 1, 10) <= ?"
        ps.append(ate)
    if paciente_id is not None:
        sql += " AND cb.paciente_id = ?"
        ps.append(paciente_id)
    recebido = sum(r["valor_centavos"] for r in query(sql, tuple(ps))
                   if not esp or (r["especialidade"] or "").strip().lower() == esp)
    para_conferir = query_one(
        """SELECT COUNT(*) AS n FROM cobrancas cb JOIN pacientes p ON p.id = cb.paciente_id
           WHERE COALESCE(cb.organizacao_id, p.organizacao_id) = ? AND cb.status = 'rascunho'
             AND cb.periodo_fim IS NOT NULL AND substr(cb.periodo_fim, 1, 10) < ?""", (org_id, _hoje_iso()))["n"]
    return jsonify({
        "cobrancas": lista,
        "totais": {
            "recebido_centavos": recebido,
            "em_aberto_centavos": sum(c["saldo_centavos"] for c in vivas),
            "vencido_centavos": sum(c["saldo_centavos"] for c in vivas if c["status"] == "vencido"),
        },
        "para_conferir": para_conferir,
    })


@bp.get("/pendencias")
@login_required
@papel_required("gestor", "admin_master")
def listar_pendencias():
    org_id, erro = _org_financeiro_ou_erro()
    if erro:
        return erro
    cobranca_service.sincronizar(org_id)
    return jsonify(cobranca_service.pendencias(org_id))


@bp.get("/config")
@login_required
@papel_required("gestor", "admin_master")
def obter_config():
    org_id, erro = _org_financeiro_ou_erro()
    if erro:
        return erro
    o = query_one("SELECT fin_cobrar_falta, fin_repasse_falta FROM organizacoes WHERE id = ?", (org_id,))
    return jsonify({"cobrar_falta": bool(o["fin_cobrar_falta"]), "repasse_falta": bool(o["fin_repasse_falta"])})


@bp.put("/config")
@login_required
@papel_required("gestor", "admin_master")
def salvar_config():
    org_id, erro = _org_financeiro_ou_erro()
    if erro:
        return erro
    body, erro = _corpo_json()
    if erro:
        return erro
    o = query_one("SELECT fin_cobrar_falta, fin_repasse_falta FROM organizacoes WHERE id = ?", (org_id,))
    novo = {}
    for chave, coluna in (("cobrar_falta", "fin_cobrar_falta"), ("repasse_falta", "fin_repasse_falta")):
        if chave in body:
            if not isinstance(body[chave], bool):
                return jsonify({"erro": f"Valor inválido para {chave}."}), 400
            novo[coluna] = 1 if body[chave] else 0
        else:
            novo[coluna] = o[coluna]
    execute("UPDATE organizacoes SET fin_cobrar_falta = ?, fin_repasse_falta = ? WHERE id = ?",
            (novo["fin_cobrar_falta"], novo["fin_repasse_falta"], org_id))
    log_auditoria(org_id, g.usuario["id"], "editar", "financeiro_config", org_id,
                  f"cobrar_falta={novo['fin_cobrar_falta']} · repasse_falta={novo['fin_repasse_falta']}")
    return jsonify({"cobrar_falta": bool(novo["fin_cobrar_falta"]), "repasse_falta": bool(novo["fin_repasse_falta"])})


@bp.get("/clinica/resumo")
@login_required
@papel_required("gestor", "admin_master")
def resumo_financeiro_clinica():
    u = g.usuario
    if not _financeiro_habilitado_para(u, u["organizacao_id"]):
        return jsonify({"erro": "O módulo Financeiro não está habilitado para esta clínica."}), 403
    org = u["organizacao_id"]
    hoje = _hoje_iso()
    total_mes = query_one(
        """SELECT COALESCE(SUM(pg.valor_centavos), 0) AS total FROM pagamentos pg
           JOIN cobrancas c ON c.id = pg.cobranca_id JOIN pacientes p ON p.id = c.paciente_id
           WHERE COALESCE(c.organizacao_id, p.organizacao_id) = ? AND pg.estornado_em IS NULL
             AND substr(pg.pago_em, 1, 7) = substr(?, 1, 7)""", (org, hoje))["total"]
    abertas = query(
        """SELECT c.status, c.valor_centavos - COALESCE(c.desconto_centavos, 0)
                  - (SELECT COALESCE(SUM(pg.valor_centavos), 0) FROM pagamentos pg
                     WHERE pg.cobranca_id = c.id AND pg.estornado_em IS NULL) AS saldo
           FROM cobrancas c JOIN pacientes p ON p.id = c.paciente_id
           WHERE COALESCE(c.organizacao_id, p.organizacao_id) = ? AND c.status IN ('pendente', 'parcial', 'vencido')""",
        (org,))
    return jsonify({
        "receita_mes_centavos": total_mes,
        "pendentes_qtd": sum(1 for a in abertas if a["status"] in ("pendente", "parcial")),
        "pendentes_total_centavos": sum(a["saldo"] for a in abertas if a["status"] in ("pendente", "parcial")),
        "vencidos_qtd": sum(1 for a in abertas if a["status"] == "vencido"),
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
    u = g.usuario
    if u["papel"] in PAPEIS_BAIXA:
        cobranca, erro = _cobranca_ou_erro(cobranca_id)
        if erro:
            return erro
    elif u["papel"] == "responsavel":
        cobranca = query_one("SELECT * FROM cobrancas WHERE id = ?", (cobranca_id,))
        if not cobranca:
            return jsonify({"erro": "Cobrança não encontrada."}), 404
        if not paciente_acessivel(cobranca["paciente_id"]):
            return jsonify({"erro": "Sem acesso."}), 403
        paciente = query_one("SELECT organizacao_id FROM pacientes WHERE id = ?", (cobranca["paciente_id"],))
        if not _financeiro_habilitado_para(u, paciente["organizacao_id"]):
            return jsonify({"erro": "O módulo Financeiro não está disponível para você no momento."}), 403
    else:
        return jsonify({"erro": "Sem acesso."}), 403
    if cobranca["status"] == "pago":
        return jsonify({"erro": "Esta cobrança já está paga."}), 409
    if cobranca["status"] in ("rascunho", "cancelado"):
        return jsonify({"erro": "Esta cobrança ainda não está disponível para pagamento."}), 409
    if pagamento_service.saldo_centavos(cobranca_id) <= 0:
        return jsonify({"erro": "Esta cobrança não tem saldo a pagar."}), 409
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
        # conferida com atraso não nasce vencida (hoje + 5, se a data já passou)
        vencimento = cobranca_service._vencimento_minimo(str(c["vencimento"])[:10], hoje)
        execute("UPDATE cobrancas SET status = 'pendente', liberada_em = ?, vencimento = ? WHERE id = ?",
                (_agora_iso(), vencimento, cobranca_id))
        status = pagamento_service.recalcular_status(cobranca_id, hoje)   # 100% de desconto já nasce paga
        log_auditoria(c["org_id"], u["id"], "liberar", "cobranca", cobranca_id, f"{c['descricao']} · {status}")
    for r in query("""SELECT u.* FROM responsaveis_pacientes rp JOIN usuarios u ON u.id = rp.usuario_id
                      WHERE rp.paciente_id = ?""", (c["paciente_id"],)):
        if financeiro_visivel_para_usuario(r):   # quem não vê o financeiro não recebe aviso dele
            criar_notificacao(r["id"], "Nova cobrança disponível",
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
    u = g.usuario
    with em_lote():
        _travar_cobranca(cobranca_id)
        if query_one("SELECT status FROM cobrancas WHERE id = ?", (cobranca_id,))["status"] != "rascunho":
            return jsonify({"erro": "Só um rascunho pode ser conferido."}), 409
        itens = {i["id"]: i for i in query("SELECT * FROM cobranca_itens WHERE cobranca_id = ?", (cobranca_id,))}
        if any(i not in itens for i in remover):
            return jsonify({"erro": "Sessão não pertence a esta cobrança."}), 400
        restante = sum(i["valor_centavos"] for k, i in itens.items() if k not in remover)
        if desconto > restante:
            return jsonify({"erro": "O desconto não pode passar do valor da cobrança."}), 400
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


@bp.post("/cobranca/<int:cobranca_id>/desconto")
@login_required
@papel_required(*PAPEIS_GESTAO)
def dar_desconto(cobranca_id):
    """Desconto numa cobrança já liberada ainda em aberto (o rascunho usa `conferir`)."""
    c, erro = _cobranca_ou_erro(cobranca_id)
    if erro:
        return erro
    body, erro = _corpo_json()
    if erro:
        return erro
    desconto = body.get("desconto_centavos")
    if isinstance(desconto, bool) or not isinstance(desconto, int) or desconto < 0:
        return jsonify({"erro": "Desconto inválido."}), 400
    motivo, msg = _motivo(body.get("desconto_motivo"), True)
    if msg:
        return jsonify({"erro": "Informe o motivo do desconto." if msg == "Informe o motivo." else msg}), 400
    u = g.usuario
    with em_lote():
        _travar_cobranca(cobranca_id)
        atual = query_one("SELECT status, valor_centavos, desconto_centavos FROM cobrancas WHERE id = ?", (cobranca_id,))
        if atual["status"] not in ("pendente", "parcial", "vencido"):
            return jsonify({"erro": "Só dá para dar desconto numa cobrança em aberto."}), 409
        if desconto > atual["valor_centavos"]:
            return jsonify({"erro": "O desconto não pode passar do valor da cobrança."}), 400
        if atual["valor_centavos"] - desconto < pagamento_service.pago_centavos(cobranca_id):
            return jsonify({"erro": "Com esse desconto, a cobrança ficaria abaixo do que já foi pago."}), 400
        execute("UPDATE cobrancas SET desconto_centavos = ?, desconto_motivo = ? WHERE id = ?",
                (desconto, motivo if desconto > 0 else None, cobranca_id))
        status = pagamento_service.recalcular_status(cobranca_id, _hoje_iso())
        log_auditoria(c["org_id"], u["id"], "desconto", "cobranca", cobranca_id,
                      f"{atual['desconto_centavos'] or 0} → {desconto} centavos · {motivo} · {status}")
    return jsonify({"ok": True, "status": status, "desconto_centavos": desconto})


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
    s = query_one("""SELECT c.id, c.data_hora, p.organizacao_id AS org_id FROM consultas c
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
    if query_one("SELECT 1 AS x FROM acordo_pacote_consumo WHERE consulta_id = ?", (consulta_id,)):
        return jsonify({"erro": "Esta sessão já foi usada de um pacote."}), 409
    if str(s["data_hora"])[:10] > _hoje_iso():
        return jsonify({"erro": "Esta sessão ainda não aconteceu."}), 409
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
    if (not isinstance(ids, list) or not ids
            or any(isinstance(i, bool) or not isinstance(i, int) for i in ids)
            or len(set(ids)) != len(ids)):
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
                execute("""INSERT INTO cobranca_itens (cobranca_id, consulta_id, data_hora, procedimento_nome, valor_centavos, status_origem)
                           VALUES (?, ?, ?, ?, ?, ?)""", (cid, i, s["data_hora"], s["procedimento_nome"], valores[i], s["status"]))
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
    corpo, erro = _corpo_json()
    if erro:
        return erro
    hoje = ausencias_service.hoje_brasilia().isoformat()
    dados, msg = acordos_service.validar(corpo, hoje)
    if msg:
        return jsonify({"erro": msg}), 400
    incluir = corpo.get("incluir_consultas")   # None = não decidiu nada; [] = nenhuma entra
    if incluir is not None and (not isinstance(incluir, list)
                                or any(isinstance(i, bool) or not isinstance(i, int) for i in incluir)):
        return jsonify({"erro": "Lista de sessões inválida."}), 400
    cobranca_service.sincronizar(p["organizacao_id"])   # saldo do pacote e sessões em dia
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
    corpo, erro = _corpo_json()
    if erro:
        return erro
    cobranca_service.sincronizar(a["organizacao_id"])   # os meses até hoje já existem para acompanhar o fim
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
    corpo, erro = _corpo_json()
    if erro:
        return erro
    cobranca_service.sincronizar(a["organizacao_id"])   # os meses até hoje já existem para acompanhar o fim
    try:
        acordos_service.encerrar(acordo_id, corpo.get("fim") or None, g.usuario)
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
