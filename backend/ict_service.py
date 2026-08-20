"""
Índice de Continuidade Terapêutica (ICT) — Documento 04 / Documento 27.

"O maior KPI da empresa." Mede se a plataforma está mantendo a criança e a
família conectadas ao tratamento entre uma consulta e outra — não é uma
métrica clínica (não avalia eficácia do tratamento), é uma métrica de
ENGAJAMENTO COM A CONTINUIDADE, composta por 4 sinais dos últimos 7 dias:

  40% — Adesão às missões (missões concluídas / missões com prazo na janela)
  25% — Sequência de prática (sequência atual normalizada até 7 dias)
  20% — Família engajada (deu algum feedback ou mandou mensagem)
  15% — Profissional acompanhou (registrou diário ou evolução)

⚠️ Fórmula provisória, como os próprios documentos pedem cautela: precisa
ser validada empiricamente antes de virar promessa de eficácia terapêutica
(Doc 27, ADR-027-004). Aqui ela já nasce declarada como não-clínica.
"""
from datetime import datetime, timedelta

from db import query, query_one

JANELA_DIAS = 7
PESOS = {"adesao": 0.40, "sequencia": 0.25, "familia": 0.20, "profissional": 0.15}


def calcular_ict_paciente(paciente_id):
    limite = (datetime.now() - timedelta(days=JANELA_DIAS)).strftime("%Y-%m-%d %H:%M:%S")

    jornada = query_one("SELECT id FROM jornadas WHERE paciente_id = ? AND status='ativa'", (paciente_id,))
    if not jornada:
        return {"ict_pct": None, "motivo": "Sem jornada ativa.", "componentes": {}}

    plano = query_one(
        "SELECT id FROM planos_terapeuticos WHERE jornada_id = ? AND status='ativo'", (jornada["id"],)
    )

    # --- Adesão às missões (últimos 7 dias)
    if plano:
        missoes_janela = query(
            "SELECT status FROM missoes WHERE plano_id = ? AND criado_em >= ? AND status != 'rascunho'", (plano["id"], limite)
        )
    else:
        missoes_janela = []
    if missoes_janela:
        concluidas = len([m for m in missoes_janela if m["status"] == "concluida"])
        adesao = concluidas / len(missoes_janela)
    else:
        adesao = 0.0

    # --- Sequência de prática
    gam = query_one("SELECT sequencia_dias FROM gamificacao_paciente WHERE paciente_id = ?", (paciente_id,))
    sequencia = min((gam["sequencia_dias"] if gam else 0) / JANELA_DIAS, 1.0)

    # --- Família engajada (feedback ou mensagem na janela)
    feedback_recente = query_one(
        """SELECT COUNT(*) as c FROM feedbacks_familia f JOIN missoes m ON m.id = f.missao_id
           WHERE m.plano_id = ? AND f.criado_em >= ?""",
        (plano["id"] if plano else -1, limite),
    )["c"] if plano else 0
    conversa = query_one("SELECT id FROM conversas WHERE paciente_id = ?", (paciente_id,))
    mensagem_recente = 0
    if conversa:
        mensagem_recente = query_one(
            """SELECT COUNT(*) as c FROM mensagens msg JOIN usuarios u ON u.id = msg.autor_id
               WHERE msg.conversa_id = ? AND u.papel = 'responsavel' AND msg.criado_em >= ?""",
            (conversa["id"], limite),
        )["c"]
    familia = 1.0 if (feedback_recente > 0 or mensagem_recente > 0) else 0.0

    # --- Profissional acompanhou (diário na janela)
    diario_recente = query_one(
        "SELECT COUNT(*) as c FROM diarios_terapeuticos WHERE jornada_id = ? AND criado_em >= ?",
        (jornada["id"], limite),
    )["c"]
    profissional = 1.0 if diario_recente > 0 else 0.0

    ict = (
        PESOS["adesao"] * adesao + PESOS["sequencia"] * sequencia
        + PESOS["familia"] * familia + PESOS["profissional"] * profissional
    )

    return {
        "ict_pct": round(ict * 100),
        "componentes": {
            "adesao_missoes_pct": round(adesao * 100),
            "sequencia_pct": round(sequencia * 100),
            "familia_engajada": bool(familia),
            "profissional_acompanhou": bool(profissional),
        },
        "janela_dias": JANELA_DIAS,
    }


def calcular_ict_medio_clinica(organizacao_id):
    pacientes = query("SELECT id FROM pacientes WHERE organizacao_id = ? AND ativo = 1", (organizacao_id,))
    valores = []
    for p in pacientes:
        r = calcular_ict_paciente(p["id"])
        if r["ict_pct"] is not None:
            valores.append(r["ict_pct"])
    if not valores:
        return None
    return round(sum(valores) / len(valores))
