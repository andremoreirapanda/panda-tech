"""
Domínio 8 — Indicadores (Documento 09 / Módulo 08)

"Não cria dados. Apenas interpreta eventos." — todas as queries aqui são
somente leitura, agregando dados de outros domínios.

Implementa literalmente os dashboards descritos no Documento 11 (Jornada 01
e Jornada 02) e no Documento 12 (UX Blueprint).
"""
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, g

from db import query, query_one, hoje_sql
from auth import login_required, papel_required, paciente_acessivel
from ict_service import calcular_ict_paciente, calcular_ict_medio_clinica
from modulos_service import modulo_ativo_para_clinica

bp = Blueprint("indicadores", __name__, url_prefix="/api/indicadores")


@bp.get("/gestor")
@login_required
@papel_required("gestor", "admin_master")
def dashboard_gestor():
    """
    Documento 11, Jornada 01: 'quatro perguntas em menos de 30 segundos'
    Como está minha clínica? Quem precisa de atenção? Financeiro? Engajamento?
    """
    org_id = g.usuario["organizacao_id"]
    hoje = datetime.now().strftime("%Y-%m-%d")

    criancas_ativas_hoje = query_one(
        """SELECT COUNT(DISTINCT j.paciente_id) as c FROM eventos e
           JOIN jornadas j ON 1=1
           WHERE e.organizacao_id = ? AND e.tipo = 'missao_concluida' AND date(e.criado_em) = ?
             AND e.paciente_id = j.paciente_id""",
        (org_id, hoje),
    )["c"]

    consultas_hoje = query_one(
        """SELECT COUNT(*) as c FROM consultas c JOIN pacientes p ON p.id = c.paciente_id
           WHERE p.organizacao_id = ? AND date(c.data_hora) = ?""",
        (org_id, hoje),
    )["c"]

    pagamentos_hoje = query_one(
        """SELECT COUNT(*) as c FROM pagamentos pg
           JOIN cobrancas cb ON cb.id = pg.cobranca_id
           JOIN pacientes p ON p.id = cb.paciente_id
           WHERE p.organizacao_id = ? AND date(pg.pago_em) = ?""",
        (org_id, hoje),
    )["c"]

    total_pacientes = query_one("SELECT COUNT(*) as c FROM pacientes WHERE organizacao_id = ? AND ativo=1", (org_id,))["c"]

    # Famílias há mais de 5 dias sem atividade concluída
    limite = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    familias_inativas = query_one(
        """SELECT COUNT(*) as c FROM pacientes p WHERE p.organizacao_id = ? AND p.ativo = 1
           AND p.id NOT IN (
               SELECT paciente_id FROM eventos WHERE tipo='missao_concluida' AND criado_em >= ?
           )""",
        (org_id, limite),
    )["c"]

    engajamento_pct = round((criancas_ativas_hoje / total_pacientes) * 100) if total_pacientes else 0

    equipe = query(
        """SELECT u.id, u.nome, u.especialidade,
                  (SELECT COUNT(*) FROM profissionais_pacientes pp WHERE pp.usuario_id = u.id) as total_pacientes
           FROM usuarios u WHERE u.organizacao_id = ? AND u.papel='profissional' AND u.ativo=1""",
        (org_id,),
    )

    org = query_one("SELECT plano FROM organizacoes WHERE id = ?", (org_id,))
    ict_medio = None
    if org and modulo_ativo_para_clinica(org_id, org["plano"], "analytics_avancado"):
        ict_medio = calcular_ict_medio_clinica(org_id)

    return jsonify({
        "criancas_ativas_hoje": criancas_ativas_hoje,
        "consultas_hoje": consultas_hoje,
        "pagamentos_hoje": pagamentos_hoje,
        "familias_inativas_5dias": familias_inativas,
        "engajamento_pct": engajamento_pct,
        "total_pacientes": total_pacientes,
        "total_profissionais": len(equipe),
        "equipe": equipe,
        "ict_medio_pct": ict_medio,
    })


@bp.get("/paciente/<int:paciente_id>/ict")
@login_required
def obter_ict_paciente(paciente_id):
    """Índice de Continuidade Terapêutica de um paciente (Doc 04 / Doc 27)."""
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Sem acesso a este paciente."}), 403
    return jsonify(calcular_ict_paciente(paciente_id))


@bp.get("/profissional")
@login_required
@papel_required("profissional")
def dashboard_profissional():
    """
    Documento 11, Jornada 02: 'crianças dentro do planejado / baixa adesão / precisam atenção'
    Critério: proporção de missões concluídas no prazo dentro do plano ativo.
    """
    u = g.usuario
    pacientes = query(
        """SELECT p.id, p.nome, p.avatar_mascote FROM pacientes p
           JOIN profissionais_pacientes pp ON pp.paciente_id = p.id
           WHERE pp.usuario_id = ? AND p.ativo = 1""",
        (u["id"],),
    )

    dentro_planejado, baixa_adesao, precisa_atencao = [], [], []
    for p in pacientes:
        plano = query_one(
            """SELECT pt.id FROM planos_terapeuticos pt JOIN jornadas j ON j.id = pt.jornada_id
               WHERE j.paciente_id = ? AND pt.status = 'ativo'""",
            (p["id"],),
        )
        if not plano:
            continue
        total = query_one("SELECT COUNT(*) as c FROM missoes WHERE plano_id = ? AND status != 'rascunho'", (plano["id"],))["c"]
        concluidas = query_one(
            "SELECT COUNT(*) as c FROM missoes WHERE plano_id = ? AND status='concluida'", (plano["id"],)
        )["c"]
        atrasadas = query_one(
            "SELECT COUNT(*) as c FROM missoes WHERE plano_id = ? AND status IN ('pendente','iniciada') AND prazo < ?",
            (plano["id"], hoje_sql()),
        )["c"]
        pct = (concluidas / total * 100) if total else 100
        p["progresso_pct"] = round(pct)
        p["missoes_atrasadas"] = atrasadas
        if atrasadas >= 2:
            precisa_atencao.append(p)
        elif pct < 60:
            baixa_adesao.append(p)
        else:
            dentro_planejado.append(p)

    return jsonify({
        "dentro_planejado": dentro_planejado,
        "baixa_adesao": baixa_adesao,
        "precisa_atencao": precisa_atencao,
        "total_pacientes": len(pacientes),
    })


@bp.get("/clinica/engajamento-semanal")
@login_required
@papel_required("gestor", "admin_master")
def engajamento_semanal():
    """Série temporal simples para o gráfico de Indicadores (Módulo 08)."""
    org_id = g.usuario["organizacao_id"]
    dias = []
    for i in range(6, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        c = query_one(
            "SELECT COUNT(*) as c FROM eventos WHERE organizacao_id = ? AND tipo='missao_concluida' AND date(criado_em) = ?",
            (org_id, d),
        )["c"]
        dias.append({"data": d, "missoes_concluidas": c})
    return jsonify(dias)
