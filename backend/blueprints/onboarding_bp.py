"""
Onboarding guiado da clínica (Documento 32 — Clinic Onboarding, Documento 31A,
Documento 33 — UX/UI Flows).

Fluxo: boas-vindas → identidade da clínica → convidar equipe →
cadastrar primeiro paciente → revisar módulos → conclusão.

Em vez de rastrear "qual etapa a pessoa está" com um campo de progresso à
parte (que facilmente fica dessincronizado da realidade), cada etapa é
computada AO VIVO a partir dos dados reais (tem profissional cadastrado?
tem paciente cadastrado?). Isso torna o wizard naturalmente retomável: se o
gestor sair no meio e voltar depois, cada passo já aparece marcado conforme
o que ele realmente fez — sem duplicar estado.
"""
from datetime import datetime

from flask import Blueprint, jsonify, g, request

from db import query_one, execute
from auth import login_required, papel_required

bp = Blueprint("onboarding", __name__, url_prefix="/api/onboarding")


@bp.get("/status")
@login_required
@papel_required("gestor", "admin_master")
def status():
    org_id = g.usuario["organizacao_id"]
    org = query_one("SELECT * FROM organizacoes WHERE id = ?", (org_id,))

    total_profissionais = query_one(
        "SELECT COUNT(*) as c FROM usuarios WHERE organizacao_id = ? AND papel = 'profissional' AND ativo = 1",
        (org_id,),
    )["c"]
    total_pacientes = query_one(
        "SELECT COUNT(*) as c FROM pacientes WHERE organizacao_id = ? AND ativo = 1", (org_id,)
    )["c"]
    total_responsaveis = query_one(
        """SELECT COUNT(DISTINCT rp.usuario_id) as c FROM responsaveis_pacientes rp
           JOIN pacientes p ON p.id = rp.paciente_id WHERE p.organizacao_id = ?""",
        (org_id,),
    )["c"]
    total_missoes_publicadas = query_one(
        """SELECT COUNT(*) as c FROM missoes m
           JOIN planos_terapeuticos pt ON pt.id = m.plano_id
           JOIN jornadas j ON j.id = pt.jornada_id
           JOIN pacientes p ON p.id = j.paciente_id
           WHERE p.organizacao_id = ? AND m.status != 'rascunho'""",
        (org_id,),
    )["c"]

    etapas = {
        "identidade": bool(org["especialidades_json"] and org["especialidades_json"] != "[]"),
        "equipe": total_profissionais > 0,
        "paciente": total_pacientes > 0,
        "responsavel": total_responsaveis > 0,
        "primeira_missao": total_missoes_publicadas > 0,
    }

    # "Clínica nova" o suficiente pra valer a pena oferecer o wizard: sem
    # equipe e sem pacientes ainda. Uma clínica com dados reais não deve
    # ser interrompida por um wizard de primeiros passos.
    parece_nova = total_profissionais == 0 and total_pacientes == 0

    return jsonify({
        "concluido": bool(org["onboarding_concluido"]),
        "concluido_em": org["onboarding_concluido_em"],
        "mostrar_wizard": parece_nova and not org["onboarding_concluido"],
        "etapas": etapas,
        "contadores": {
            "profissionais": total_profissionais, "pacientes": total_pacientes,
            "responsaveis": total_responsaveis, "missoes_publicadas": total_missoes_publicadas,
        },
    })


@bp.post("/concluir")
@login_required
@papel_required("gestor", "admin_master")
def concluir():
    """Chamado tanto ao terminar o wizard quanto ao pular ('mais tarde')."""
    org_id = g.usuario["organizacao_id"]
    execute(
        "UPDATE organizacoes SET onboarding_concluido = 1, onboarding_concluido_em = ? WHERE id = ?",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), org_id),
    )
    return jsonify({"ok": True})
