"""
Domínio 6 — Gamificação (Documento 09 / Módulo 06)

"Ela nunca é criada manualmente. Sempre nasce de eventos." (Documento 08)

Este serviço é o consumidor do evento 'missao_concluida' (publicado pela
Jornada Terapêutica) e é o único responsável por escrever nas tabelas de
gamificação — respeitando o princípio de que cada domínio tem um único dono.
"""
from datetime import date, timedelta

from db import query_one, execute, log_evento, agora_sql

MEDALHAS_PADRAO = [
    ("Primeira Missão", "Concluiu a primeira missão da jornada", "🥇", "1 missão concluída"),
    ("Sequência de 3 dias", "Realizou atividades por 3 dias seguidos", "🔥", "3 dias consecutivos"),
    ("Sequência de 7 dias", "Uma semana inteira sem parar!", "⭐", "7 dias consecutivos"),
    ("Sequência de 30 dias", "Trinta dias consecutivos de dedicação", "🏆", "30 dias consecutivos"),
    ("Semana Completa", "Concluiu todas as missões da semana", "🎯", "100% das missões da semana"),
    ("Explorador", "Concluiu 10 missões", "🧭", "10 missões concluídas"),
    ("Mestre da Jornada", "Concluiu 50 missões", "👑", "50 missões concluídas"),
]


def garantir_medalhas_padrao():
    existentes = query_one("SELECT COUNT(*) as c FROM medalhas")
    if existentes and existentes["c"] > 0:
        return
    for nome, desc, icone, criterio in MEDALHAS_PADRAO:
        execute("INSERT INTO medalhas (nome, descricao, icone_emoji, criterio) VALUES (?, ?, ?, ?)",
                (nome, desc, icone, criterio))


def _conceder_medalha(paciente_id, nome_medalha):
    medalha = query_one("SELECT id FROM medalhas WHERE nome = ?", (nome_medalha,))
    if not medalha:
        return None
    ja_tem = query_one(
        "SELECT 1 FROM medalhas_paciente WHERE paciente_id = ? AND medalha_id = ?",
        (paciente_id, medalha["id"]),
    )
    if ja_tem:
        return None
    execute("INSERT INTO medalhas_paciente (paciente_id, medalha_id) VALUES (?, ?)", (paciente_id, medalha["id"]))
    return medalha["id"]


def processar_missao_concluida(paciente_id: int, missao: dict) -> dict:
    """
    Consome o evento de missão concluída e atualiza:
    XP, nível, estrelas, sequência de dias, medalhas, baú de recompensas.
    Retorna um resumo usado pela UI para animar a conquista (confetes, etc.)
    """
    garantir_medalhas_padrao()

    gam = query_one("SELECT * FROM gamificacao_paciente WHERE paciente_id = ?", (paciente_id,))
    if not gam:
        execute("INSERT INTO gamificacao_paciente (paciente_id) VALUES (?)", (paciente_id,))
        gam = query_one("SELECT * FROM gamificacao_paciente WHERE paciente_id = ?", (paciente_id,))

    hoje = date.today()
    ultima = gam["ultima_atividade_em"]
    nova_sequencia = 1
    if ultima:
        ultima_data = date.fromisoformat(ultima[:10])
        if ultima_data == hoje:
            nova_sequencia = gam["sequencia_dias"]
        elif ultima_data == hoje - timedelta(days=1):
            nova_sequencia = gam["sequencia_dias"] + 1
        else:
            nova_sequencia = 1  # sequência quebrada

    novo_xp = gam["xp_total"] + missao["recompensa_xp"]
    novas_estrelas = gam["estrelas"] + 1
    novo_nivel = 1 + novo_xp // 100
    novo_mascote_estagio = min(5, 1 + novo_nivel // 3)

    execute(
        """UPDATE gamificacao_paciente
           SET xp_total = ?, nivel = ?, estrelas = ?, sequencia_dias = ?,
               ultima_atividade_em = ?, mascote_estagio = ?
           WHERE paciente_id = ?""",
        (novo_xp, novo_nivel, novas_estrelas, nova_sequencia, agora_sql(), novo_mascote_estagio, paciente_id),
    )

    total_missoes_concluidas = query_one(
        """SELECT COUNT(*) as c FROM missoes m
           JOIN planos_terapeuticos pt ON pt.id = m.plano_id
           JOIN jornadas j ON j.id = pt.jornada_id
           WHERE j.paciente_id = ? AND m.status = 'concluida'""",
        (paciente_id,),
    )["c"]

    medalhas_novas = []
    if total_missoes_concluidas == 1:
        m = _conceder_medalha(paciente_id, "Primeira Missão")
        if m:
            medalhas_novas.append("Primeira Missão")
    if nova_sequencia == 3:
        if _conceder_medalha(paciente_id, "Sequência de 3 dias"):
            medalhas_novas.append("Sequência de 3 dias")
    if nova_sequencia == 7:
        if _conceder_medalha(paciente_id, "Sequência de 7 dias"):
            medalhas_novas.append("Sequência de 7 dias")
    if nova_sequencia == 30:
        if _conceder_medalha(paciente_id, "Sequência de 30 dias"):
            medalhas_novas.append("Sequência de 30 dias")
    if total_missoes_concluidas == 10:
        if _conceder_medalha(paciente_id, "Explorador"):
            medalhas_novas.append("Explorador")
    if total_missoes_concluidas == 50:
        if _conceder_medalha(paciente_id, "Mestre da Jornada"):
            medalhas_novas.append("Mestre da Jornada")

    # Semana completa: todas as missões do plano ativo concluídas
    plano = query_one(
        """SELECT pt.id FROM planos_terapeuticos pt
           JOIN jornadas j ON j.id = pt.jornada_id
           WHERE j.paciente_id = ? AND pt.status = 'ativo'""",
        (paciente_id,),
    )
    if plano:
        pendentes = query_one(
            "SELECT COUNT(*) as c FROM missoes WHERE plano_id = ? AND status != 'concluida'", (plano["id"],)
        )["c"]
        if pendentes == 0:
            if _conceder_medalha(paciente_id, "Semana Completa"):
                medalhas_novas.append("Semana Completa")
                execute(
                    "INSERT INTO recompensas_bau (paciente_id, nome, icone_emoji, desbloqueado) VALUES (?, ?, ?, 1)",
                    (paciente_id, "Baú da Semana Completa", "🎁"),
                )

    for nome in medalhas_novas:
        log_evento(None, "medalha_conquistada", "medalha", None, paciente_id, {"medalha": nome})

    return {
        "xp_ganho": missao["recompensa_xp"],
        "xp_total": novo_xp,
        "nivel": novo_nivel,
        "estrelas": novas_estrelas,
        "sequencia_dias": nova_sequencia,
        "mascote_estagio": novo_mascote_estagio,
        "medalhas_novas": medalhas_novas,
    }
