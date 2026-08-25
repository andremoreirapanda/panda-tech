"""
Domínio 2 — Jornada Terapêutica (Documento 09 / Módulo 02)

"O coração da plataforma" — entidade central do ecossistema (PD-009-001).
Paciente → Jornada → Plano Terapêutico → Objetivos → Missões → Atividades → Evolução

Ao concluir uma missão, publica o evento 'missao_concluida', que:
 - atualiza a Gamificação (XP, sequência, medalhas)
 - gera uma Notificação para o responsável
 - alimenta os Indicadores
Esse fluxo implementa literalmente o exemplo do Documento 08 ("Fluxo da Informação").
"""
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute, log_evento, log_auditoria, agora_sql, hoje_sql, criar_notificacao
from auth import login_required, papel_required, paciente_acessivel, paciente_editavel
from gamificacao_service import processar_missao_concluida

bp = Blueprint("jornada", __name__, url_prefix="/api/jornada")


def _checar_acesso(paciente_id):
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Você não tem acesso à jornada deste paciente."}), 403
    return None


@bp.get("/paciente/<int:paciente_id>")
@login_required
def obter_jornada_completa(paciente_id):
    """
    Retorna a 'Home' do paciente (UX Pattern 06, Documento 13):
    objetivo principal, progresso, missões da semana, feedbacks, timeline, marcos.
    """
    erro = _checar_acesso(paciente_id)
    if erro:
        return erro
    return jsonify(_montar_bundle_jornada(paciente_id))


def _montar_bundle_jornada(paciente_id):
    """
    Monta o mesmo dicionário retornado por GET /jornada/paciente/<id> — extraído
    à parte pra também ser reaproveitado na geração do relatório em PDF, sem
    duplicar as consultas. Assume que o acesso já foi checado por quem chama.
    """
    paciente = query_one("SELECT * FROM pacientes WHERE id = ?", (paciente_id,))
    paciente["pode_editar"] = paciente_editavel(paciente_id)
    paciente["responsaveis"] = query(
        """SELECT u.id, u.nome, u.email, u.telefone, rp.parentesco
           FROM usuarios u JOIN responsaveis_pacientes rp ON rp.usuario_id = u.id
           WHERE rp.paciente_id = ?""",
        (paciente_id,),
    )
    paciente["profissionais"] = query(
        """SELECT u.id, u.nome, u.especialidade, pp.principal
           FROM usuarios u JOIN profissionais_pacientes pp ON pp.usuario_id = u.id
           WHERE pp.paciente_id = ?""",
        (paciente_id,),
    )
    jornada = query_one(
        "SELECT * FROM jornadas WHERE paciente_id = ? AND status = 'ativa' ORDER BY id DESC LIMIT 1",
        (paciente_id,),
    )
    if not jornada:
        return {"paciente": paciente, "jornada": None, "planos": []}

    plano = query_one(
        "SELECT * FROM planos_terapeuticos WHERE jornada_id = ? AND status = 'ativo' ORDER BY id DESC LIMIT 1",
        (jornada["id"],),
    )
    objetivos, missoes = [], []
    if plano:
        objetivos = query("SELECT * FROM objetivos_terapeuticos WHERE plano_id = ?", (plano["id"],))
        sql_missoes = """SELECT m.*,
                      (SELECT COUNT(*) FROM atividades a WHERE a.missao_id = m.id) AS total_atividades,
                      (SELECT COUNT(*) FROM atividades a WHERE a.missao_id = m.id AND a.concluida = 1) AS atividades_concluidas,
                      (SELECT COUNT(*) FROM feedbacks_familia f WHERE f.missao_id = m.id) AS tem_feedback
               FROM missoes m WHERE m.plano_id = ?"""
        # Rascunhos são visíveis só para quem pode editar a jornada (US-017/019);
        # a família nunca deve ver uma missão que ainda não foi publicada.
        if g.usuario["papel"] in ("responsavel",):
            sql_missoes += " AND m.status != 'rascunho'"
        sql_missoes += " ORDER BY m.criado_em"
        missoes = query(sql_missoes, (plano["id"],))
        for m in missoes:
            m["atividades"] = query(
                """SELECT a.id, a.ordem, a.concluida, e.id as exercicio_id, e.titulo, e.tipo, e.conteudo_url,
                          (e.arquivo_base64 IS NOT NULL AND e.arquivo_base64 != '') as tem_arquivo
                   FROM atividades a JOIN exercicios e ON e.id = a.exercicio_id
                   WHERE a.missao_id = ? ORDER BY a.ordem""",
                (m["id"],),
            )
            if m["tipo"] == "semanal":
                dias = query("SELECT data FROM missao_dias_concluidos WHERE missao_id = ? ORDER BY data", (m["id"],))
                m["dias_concluidos"] = [d["data"] for d in dias]
                m["dias_concluidos_total"] = len(dias)

    marcos = query("SELECT * FROM marcos_terapeuticos WHERE jornada_id = ? ORDER BY criado_em DESC", (jornada["id"],))
    diarios_recentes = query(
        """SELECT d.id, d.data_atendimento, d.evolucao_clinica, d.mensagem_familia, d.objetivo_semana, d.compartilhado_familia,
                  d.criado_em, u.nome as profissional_nome
           FROM diarios_terapeuticos d JOIN usuarios u ON u.id = d.profissional_id
           WHERE d.jornada_id = ? ORDER BY d.data_atendimento DESC, d.criado_em DESC LIMIT 5""",
        (jornada["id"],),
    )
    if g.usuario["papel"] == "responsavel":
        # Só chegam ao resumo os registros já marcados como compartilhados
        # com a família — e mesmo esses nunca trazem a evolução clínica.
        diarios_recentes = [d for d in diarios_recentes if d["compartilhado_familia"]]
        for d in diarios_recentes:
            d["evolucao_clinica"] = None
    feedbacks = query(
        """SELECT f.*, m.titulo as missao_titulo, u.nome as autor_nome FROM feedbacks_familia f
           JOIN missoes m ON m.id = f.missao_id JOIN usuarios u ON u.id = f.usuario_id
           WHERE m.plano_id = ? ORDER BY f.criado_em DESC LIMIT 10""",
        (plano["id"] if plano else -1,),
    )
    gamificacao = query_one("SELECT * FROM gamificacao_paciente WHERE paciente_id = ?", (paciente_id,))

    # Progresso considera apenas missões já publicadas (rascunho não conta nem pra cima, nem pra baixo)
    missoes_contabilizadas = [m for m in missoes if m["status"] != "rascunho"]
    total = len(missoes_contabilizadas)
    concluidas = len([m for m in missoes_contabilizadas if m["status"] == "concluida"])
    progresso_pct = round((concluidas / total) * 100) if total else 0

    return {
        "paciente": paciente,
        "jornada": jornada,
        "plano_ativo": plano,
        "objetivos": objetivos,
        "missoes": missoes,
        "marcos": marcos,
        "diarios_recentes": diarios_recentes,
        "feedbacks": feedbacks,
        "gamificacao": gamificacao,
        "progresso_pct": progresso_pct,
        "missoes_concluidas": concluidas,
        "missoes_total": total,
    }


@bp.get("/paciente/<int:paciente_id>/relatorio-pdf")
@login_required
def relatorio_pdf(paciente_id):
    """Gera e devolve o relatório de acompanhamento em PDF (insight do usuário)."""
    from flask import Response
    from relatorio_service import gerar_relatorio_pdf

    erro = _checar_acesso(paciente_id)
    if erro:
        return erro

    dados = _montar_bundle_jornada(paciente_id)
    org = query_one("SELECT nome FROM organizacoes WHERE id = ?", (g.usuario["organizacao_id"],)) if g.usuario["organizacao_id"] else None
    dados["organizacao_nome"] = org["nome"] if org else "Clínica"
    dados["idade_texto"] = _idade_por_extenso(dados["paciente"].get("data_nascimento"))

    incluir_evolucao = g.usuario["papel"] in ("gestor", "profissional", "admin_master")
    pdf_bytes = gerar_relatorio_pdf(dados, incluir_evolucao_clinica=incluir_evolucao)

    nome_arquivo = f"relatorio-{dados['paciente']['nome'].replace(' ', '-').lower()}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


def _idade_por_extenso(data_nascimento):
    if not data_nascimento:
        return ""
    from datetime import date
    nasc = date.fromisoformat(data_nascimento)
    hoje = date.today()
    anos = hoje.year - nasc.year
    meses = hoje.month - nasc.month
    if hoje.day < nasc.day:
        meses -= 1
    if meses < 0:
        anos -= 1
        meses += 12
    partes = []
    if anos > 0:
        partes.append(f"{anos} {'ano' if anos == 1 else 'anos'}")
    if meses > 0:
        partes.append(f"{meses} {'mês' if meses == 1 else 'meses'}")
    return " e ".join(partes) if partes else "recém-nascido(a)"


@bp.post("/paciente/<int:paciente_id>/criar-jornada")
@login_required
@papel_required("profissional", "gestor", "admin_master")
def criar_jornada(paciente_id):
    if not paciente_editavel(paciente_id):
        return jsonify({"erro": "Você não tem permissão para editar este paciente."}), 403
    body = request.get_json(force=True, silent=True) or {}
    objetivo = body.get("objetivo_principal", "Desenvolvimento geral")
    ativa = query_one("SELECT id FROM jornadas WHERE paciente_id = ? AND status = 'ativa'", (paciente_id,))
    if ativa:
        return jsonify({"erro": "Este paciente já possui uma jornada ativa."}), 409
    jornada_id = execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)", (paciente_id, objetivo)
    )
    log_evento(g.usuario["organizacao_id"], "jornada_criada", "jornada", jornada_id, paciente_id)
    return jsonify({"id": jornada_id}), 201


@bp.post("/jornada/<int:jornada_id>/criar-plano")
@login_required
@papel_required("profissional", "gestor", "admin_master")
def criar_plano(jornada_id):
    u = g.usuario
    jornada_check = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (jornada_id,))
    if not jornada_check or not paciente_editavel(jornada_check["paciente_id"]):
        return jsonify({"erro": "Você não tem permissão para editar este paciente."}), 403
    body = request.get_json(force=True, silent=True) or {}
    titulo = body.get("titulo", "Novo plano")
    objetivos = body.get("objetivos", [])
    if not objetivos:
        return jsonify({"erro": "Todo plano precisa de pelo menos um objetivo (regra do Documento 013)."}), 400

    # Encerra plano anterior, se houver
    execute("UPDATE planos_terapeuticos SET status='encerrado' WHERE jornada_id = ? AND status='ativo'", (jornada_id,))

    plano_id = execute(
        """INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio)
           VALUES (?, ?, ?, ?)""",
        (jornada_id, u["id"], titulo, hoje_sql()),
    )
    for desc in objetivos:
        execute("INSERT INTO objetivos_terapeuticos (plano_id, descricao) VALUES (?, ?)", (plano_id, desc))

    jornada = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (jornada_id,))
    log_evento(u["organizacao_id"], "plano_iniciado", "plano_terapeutico", plano_id, jornada["paciente_id"])
    return jsonify({"id": plano_id}), 201


@bp.post("/plano/<int:plano_id>/criar-missao")
@login_required
@papel_required("profissional", "gestor", "admin_master")
def criar_missao(plano_id):
    """
    Nenhuma missão pode existir sem estar vinculada a um plano (Doc 10, Critérios de aceite).

    Suporta o ciclo rascunho → publicada (US-017/US-019, Doc 30/31): por padrão
    a missão já nasce publicada (para não quebrar o fluxo simples do dia a dia),
    mas quem cria pode pedir explicitamente para salvar como rascunho primeiro.
    """
    u = g.usuario
    plano_check = query_one("SELECT jornada_id FROM planos_terapeuticos WHERE id = ?", (plano_id,))
    jornada_check = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (plano_check["jornada_id"],)) if plano_check else None
    if not jornada_check or not paciente_editavel(jornada_check["paciente_id"]):
        return jsonify({"erro": "Você não tem permissão para editar este paciente."}), 403
    body = request.get_json(force=True, silent=True) or {}
    titulo = (body.get("titulo") or "").strip()
    if not titulo:
        return jsonify({"erro": "Título da missão é obrigatório."}), 400

    publicar_agora = body.get("publicar", True)
    status_inicial = "pendente" if publicar_agora else "rascunho"
    tipo = body.get("tipo") if body.get("tipo") in ("diaria", "semanal") else "diaria"

    prazo = body.get("prazo") or (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    missao_id = execute(
        """INSERT INTO missoes (plano_id, objetivo_id, titulo, descricao, prazo, recompensa_xp, tempo_estimado_min, status, tipo, publicada_em)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (plano_id, body.get("objetivo_id"), titulo, body.get("descricao", ""), prazo,
         body.get("recompensa_xp", 10), body.get("tempo_estimado_min", 10), status_inicial, tipo,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S") if publicar_agora else None),
    )
    for i, exercicio_id in enumerate(body.get("exercicios_ids", []), start=1):
        execute("INSERT INTO atividades (missao_id, exercicio_id, ordem) VALUES (?, ?, ?)", (missao_id, exercicio_id, i))

    plano = query_one("SELECT jornada_id FROM planos_terapeuticos WHERE id = ?", (plano_id,))
    jornada = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (plano["jornada_id"],))
    log_evento(u["organizacao_id"], "missao_criada" if not publicar_agora else "missao_publicada",
               "missao", missao_id, jornada["paciente_id"])

    if publicar_agora:
        _notificar_nova_missao(jornada["paciente_id"], titulo, missao_id)

    return jsonify({"id": missao_id, "status": status_inicial}), 201


def _notificar_nova_missao(paciente_id, titulo_missao, missao_id=None):
    """FR-037/US-019: responsável recebe notificação quando a missão é publicada.
    Também dispara o lembrete real por WhatsApp (se a clínica tiver a
    integração conectada) — ver whatsapp_service.py."""
    responsaveis = query("SELECT usuario_id FROM responsaveis_pacientes WHERE paciente_id = ?", (paciente_id,))
    paciente = query_one("SELECT nome FROM pacientes WHERE id = ?", (paciente_id,))
    for r in responsaveis:
        criar_notificacao(
            r["usuario_id"], "Nova atividade disponível! 📋",
            f"{paciente['nome']} tem uma nova missão: \"{titulo_missao}\".",
            tipo="missao", entidade="paciente", entidade_id=paciente_id,
        )
    if missao_id:
        from whatsapp_service import enviar_lembrete_missao
        enviar_lembrete_missao(missao_id)


@bp.put("/missao/<int:missao_id>")
@login_required
@papel_required("profissional", "gestor", "admin_master")
def editar_missao(missao_id):
    """
    Edição da missão (Doc 30/31, US-018): só permitida enquanto a missão não
    foi concluída — depois de concluída, ela vira registro histórico e não
    deve mais mudar (a criança já ganhou a recompensa por aquele conteúdo).
    """
    missao = query_one("SELECT * FROM missoes WHERE id = ?", (missao_id,))
    if not missao:
        return jsonify({"erro": "Missão não encontrada."}), 404
    plano_ed = query_one("SELECT jornada_id FROM planos_terapeuticos WHERE id = ?", (missao["plano_id"],))
    jornada_ed = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (plano_ed["jornada_id"],))
    if not paciente_editavel(jornada_ed["paciente_id"]):
        return jsonify({"erro": "Você não tem permissão para editar este paciente."}), 403
    if missao["status"] == "concluida":
        return jsonify({"erro": "Não é possível editar uma missão já concluída."}), 409

    body = request.get_json(force=True, silent=True) or {}
    titulo = (body.get("titulo") or "").strip()
    if not titulo:
        return jsonify({"erro": "Título da missão é obrigatório."}), 400

    execute(
        """UPDATE missoes SET titulo = ?, descricao = ?, prazo = ?, recompensa_xp = ?, tempo_estimado_min = ?
           WHERE id = ?""",
        (titulo, body.get("descricao", ""), body.get("prazo") or missao["prazo"],
         body.get("recompensa_xp", missao["recompensa_xp"]), body.get("tempo_estimado_min", missao["tempo_estimado_min"]),
         missao_id),
    )
    if "exercicios_ids" in body:
        execute("DELETE FROM atividades WHERE missao_id = ?", (missao_id,))
        for i, exercicio_id in enumerate(body["exercicios_ids"], start=1):
            execute("INSERT INTO atividades (missao_id, exercicio_id, ordem) VALUES (?, ?, ?)", (missao_id, exercicio_id, i))

    plano = query_one("SELECT jornada_id FROM planos_terapeuticos WHERE id = ?", (missao["plano_id"],))
    jornada = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (plano["jornada_id"],))
    log_evento(g.usuario["organizacao_id"], "missao_editada", "missao", missao_id, jornada["paciente_id"])
    return jsonify({"ok": True})


@bp.delete("/missao/<int:missao_id>")
@login_required
@papel_required("profissional", "gestor", "admin_master")
def excluir_missao(missao_id):
    """Exclusão (Doc 30/31, US-018) — só permitida antes da missão ser concluída,
    pelo mesmo motivo da edição: uma vez concluída, vira histórico permanente."""
    missao = query_one("SELECT * FROM missoes WHERE id = ?", (missao_id,))
    if not missao:
        return jsonify({"erro": "Missão não encontrada."}), 404
    plano_ex = query_one("SELECT jornada_id FROM planos_terapeuticos WHERE id = ?", (missao["plano_id"],))
    jornada_ex = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (plano_ex["jornada_id"],))
    if not paciente_editavel(jornada_ex["paciente_id"]):
        return jsonify({"erro": "Você não tem permissão para editar este paciente."}), 403
    if missao["status"] == "concluida":
        return jsonify({"erro": "Não é possível excluir uma missão já concluída."}), 409

    plano = query_one("SELECT jornada_id FROM planos_terapeuticos WHERE id = ?", (missao["plano_id"],))
    jornada = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (plano["jornada_id"],))

    execute("DELETE FROM atividades WHERE missao_id = ?", (missao_id,))
    execute("DELETE FROM feedbacks_familia WHERE missao_id = ?", (missao_id,))
    execute("DELETE FROM missoes WHERE id = ?", (missao_id,))
    log_evento(g.usuario["organizacao_id"], "missao_excluida", "missao", missao_id, jornada["paciente_id"])
    return jsonify({"ok": True})


@bp.put("/missao/<int:missao_id>/publicar")
@login_required
@papel_required("profissional", "gestor", "admin_master")
def publicar_missao(missao_id):
    """Torna uma missão em rascunho visível para a família (US-019)."""
    missao = query_one("SELECT * FROM missoes WHERE id = ?", (missao_id,))
    if not missao:
        return jsonify({"erro": "Missão não encontrada."}), 404
    plano_pub = query_one("SELECT jornada_id FROM planos_terapeuticos WHERE id = ?", (missao["plano_id"],))
    jornada_pub = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (plano_pub["jornada_id"],))
    if not paciente_editavel(jornada_pub["paciente_id"]):
        return jsonify({"erro": "Você não tem permissão para editar este paciente."}), 403
    if missao["status"] != "rascunho":
        return jsonify({"erro": "Esta missão já foi publicada."}), 409

    execute("UPDATE missoes SET status = 'pendente', publicada_em = ? WHERE id = ?", (agora_sql(), missao_id))
    plano = query_one("SELECT jornada_id FROM planos_terapeuticos WHERE id = (SELECT plano_id FROM missoes WHERE id = ?)", (missao_id,))
    jornada = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (plano["jornada_id"],))
    log_evento(g.usuario["organizacao_id"], "missao_publicada", "missao", missao_id, jornada["paciente_id"])
    _notificar_nova_missao(jornada["paciente_id"], missao["titulo"], missao_id)
    return jsonify({"ok": True})


@bp.get("/missao/<int:missao_id>")
@login_required
def obter_missao(missao_id):
    """Detalhe de uma missão isolada — usado na prévia que o responsável vê antes da criança."""
    missao = query_one("SELECT * FROM missoes WHERE id = ?", (missao_id,))
    if not missao:
        return jsonify({"erro": "Missão não encontrada."}), 404
    plano = query_one("SELECT * FROM planos_terapeuticos WHERE id = ?", (missao["plano_id"],))
    jornada = query_one("SELECT * FROM jornadas WHERE id = ?", (plano["jornada_id"],)) if plano else None
    if not jornada or not paciente_acessivel(jornada["paciente_id"]):
        return jsonify({"erro": "Sem acesso a esta missão."}), 403
    if g.usuario["papel"] == "responsavel" and missao["status"] == "rascunho":
        return jsonify({"erro": "Esta missão ainda não foi publicada."}), 403

    paciente = query_one("SELECT nome FROM pacientes WHERE id = ?", (jornada["paciente_id"],))
    missao["paciente_nome"] = paciente["nome"]
    missao["atividades"] = query(
        """SELECT a.id, a.ordem, a.concluida, e.id as exercicio_id, e.titulo, e.tipo, e.conteudo_url,
                  (e.arquivo_base64 IS NOT NULL AND e.arquivo_base64 != '') as tem_arquivo
           FROM atividades a JOIN exercicios e ON e.id = a.exercicio_id
           WHERE a.missao_id = ? ORDER BY a.ordem""",
        (missao_id,),
    )
    if missao["tipo"] == "semanal":
        dias = query("SELECT data FROM missao_dias_concluidos WHERE missao_id = ? ORDER BY data", (missao_id,))
        missao["dias_concluidos"] = [d["data"] for d in dias]
        missao["dias_concluidos_total"] = len(dias)
    return jsonify(missao)


@bp.post("/missao/<int:missao_id>/iniciar")
@login_required
@papel_required("responsavel", "profissional", "gestor", "admin_master")
def iniciar_missao(missao_id):
    """
    US-021 (activity_started): registra que a criança/responsável começou a
    atividade — estado intermediário entre 'publicada' e 'concluída', usado
    pelo funil de engajamento (Doc 27/33).
    """
    missao = query_one("SELECT * FROM missoes WHERE id = ?", (missao_id,))
    if not missao:
        return jsonify({"erro": "Missão não encontrada."}), 404

    plano = query_one("SELECT * FROM planos_terapeuticos WHERE id = ?", (missao["plano_id"],))
    jornada = query_one("SELECT * FROM jornadas WHERE id = ?", (plano["jornada_id"],))
    if not paciente_acessivel(jornada["paciente_id"]):
        return jsonify({"erro": "Você não tem acesso a esta jornada."}), 403

    if missao["status"] == "pendente":
        execute("UPDATE missoes SET status = 'iniciada', iniciada_em = ? WHERE id = ?", (agora_sql(), missao_id))
        org_id = g.usuario["organizacao_id"] or query_one(
            "SELECT organizacao_id FROM pacientes WHERE id = ?", (jornada["paciente_id"],)
        )["organizacao_id"]
        log_evento(org_id, "missao_iniciada", "missao", missao_id, jornada["paciente_id"])
    return jsonify({"ok": True, "status": "iniciada" if missao["status"] == "pendente" else missao["status"]})


@bp.post("/missao/<int:missao_id>/concluir")
@login_required
@papel_required("responsavel", "profissional", "gestor", "admin_master")
def concluir_missao(missao_id):
    """
    Coração do fluxo gamificado (Documento 11 — Jornada 04, Criança):
    Selecionar missão → Realizar atividade → Receber estrela → Desbloquear prêmio.

    Este endpoint é chamado tanto pela tela 'Mundo da Criança' quanto pelo
    responsável, e dispara toda a cadeia de eventos descrita no Documento 08:
    Missão concluída → Evento → Gamificação atualiza → Notificação → Indicadores.
    """
    missao = query_one("SELECT * FROM missoes WHERE id = ?", (missao_id,))
    if not missao:
        return jsonify({"erro": "Missão não encontrada."}), 404
    if missao["status"] == "concluida":
        return jsonify({"erro": "Esta missão já foi concluída."}), 409
    if missao["status"] not in ("pendente", "iniciada"):
        return jsonify({"erro": "Esta missão ainda não foi publicada."}), 409
    if missao["tipo"] == "semanal":
        return jsonify({"erro": "Esta é uma missão semanal — conclua um dia de cada vez, não tudo de uma vez."}), 409

    plano = query_one("SELECT * FROM planos_terapeuticos WHERE id = ?", (missao["plano_id"],))
    jornada = query_one("SELECT * FROM jornadas WHERE id = ?", (plano["jornada_id"],))
    paciente_id = jornada["paciente_id"]

    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Você não tem acesso a esta jornada."}), 403

    execute("UPDATE atividades SET concluida = 1 WHERE missao_id = ?", (missao_id,))
    execute("UPDATE missoes SET status = 'concluida', concluida_em = ? WHERE id = ?", (agora_sql(), missao_id))

    org_id = g.usuario["organizacao_id"] or query_one(
        "SELECT organizacao_id FROM pacientes WHERE id = ?", (paciente_id,)
    )["organizacao_id"]

    log_evento(org_id, "missao_concluida", "missao", missao_id, paciente_id, {"titulo": missao["titulo"]})

    resultado_gamificacao = processar_missao_concluida(paciente_id, missao)

    # Notifica responsáveis (Documento 08: "Responsável recebe notificação")
    responsaveis = query("SELECT usuario_id FROM responsaveis_pacientes WHERE paciente_id = ?", (paciente_id,))
    paciente = query_one("SELECT nome FROM pacientes WHERE id = ?", (paciente_id,))
    for r in responsaveis:
        criar_notificacao(
            r["usuario_id"], "Missão concluída! 🎉",
            f"{paciente['nome']} concluiu a missão \"{missao['titulo']}\" e ganhou {missao['recompensa_xp']} XP.",
            tipo="conquista", entidade="paciente", entidade_id=paciente_id,
        )

    return jsonify({"ok": True, "gamificacao": resultado_gamificacao})


@bp.post("/missao/<int:missao_id>/concluir-dia")
@login_required
def concluir_dia_missao(missao_id):
    """
    Check diário de uma missão SEMANAL (insight do usuário): registra a data
    de HOJE (do servidor — nunca aceita data enviada pelo cliente, pra não
    dar pra "adiantar" dias) como concluída. Precisa de 7 dias distintos pra
    fechar a missão inteira — não dá pra marcar dois dias na mesma chamada,
    nem repetir o mesmo dia duas vezes (UNIQUE trava isso).
    """
    from datetime import date

    missao = query_one("SELECT * FROM missoes WHERE id = ?", (missao_id,))
    if not missao:
        return jsonify({"erro": "Missão não encontrada."}), 404
    if missao["tipo"] != "semanal":
        return jsonify({"erro": "Esta missão não é semanal — use o endpoint de concluir normal."}), 409
    if missao["status"] == "concluida":
        return jsonify({"erro": "Esta missão já foi concluída."}), 409
    if missao["status"] not in ("pendente", "iniciada"):
        return jsonify({"erro": "Esta missão ainda não foi publicada."}), 409

    plano = query_one("SELECT * FROM planos_terapeuticos WHERE id = ?", (missao["plano_id"],))
    jornada = query_one("SELECT * FROM jornadas WHERE id = ?", (plano["jornada_id"],))
    paciente_id = jornada["paciente_id"]
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Você não tem acesso a esta jornada."}), 403

    hoje = date.today().isoformat()
    ja_marcado_hoje = query_one("SELECT 1 FROM missao_dias_concluidos WHERE missao_id = ? AND data = ?", (missao_id, hoje))
    if ja_marcado_hoje:
        return jsonify({"erro": "O dia de hoje já foi marcado nesta missão."}), 409

    execute("INSERT INTO missao_dias_concluidos (missao_id, data) VALUES (?, ?)", (missao_id, hoje))
    total_dias = query_one("SELECT COUNT(*) as c FROM missao_dias_concluidos WHERE missao_id = ?", (missao_id,))["c"]

    org_id = g.usuario["organizacao_id"] or query_one("SELECT organizacao_id FROM pacientes WHERE id = ?", (paciente_id,))["organizacao_id"]

    if total_dias >= 7:
        # Semana completa — fecha a missão e dispara a mesma recompensa de gamificação de sempre.
        execute("UPDATE atividades SET concluida = 1 WHERE missao_id = ?", (missao_id,))
        execute("UPDATE missoes SET status = 'concluida', concluida_em = ? WHERE id = ?", (agora_sql(), missao_id))
        log_evento(org_id, "missao_concluida", "missao", missao_id, paciente_id, {"titulo": missao["titulo"], "tipo": "semanal"})
        resultado_gamificacao = processar_missao_concluida(paciente_id, missao)
        responsaveis = query("SELECT usuario_id FROM responsaveis_pacientes WHERE paciente_id = ?", (paciente_id,))
        paciente = query_one("SELECT nome FROM pacientes WHERE id = ?", (paciente_id,))
        for r in responsaveis:
            criar_notificacao(
                r["usuario_id"], "Missão semanal concluída! 🎉",
                f"{paciente['nome']} completou os 7 dias da missão \"{missao['titulo']}\" e ganhou {missao['recompensa_xp']} XP.",
                tipo="conquista", entidade="paciente", entidade_id=paciente_id,
            )
        return jsonify({"ok": True, "dias_concluidos": total_dias, "semana_completa": True, "gamificacao": resultado_gamificacao})

    if missao["status"] == "pendente":
        execute("UPDATE missoes SET status = 'iniciada', iniciada_em = ? WHERE id = ?", (agora_sql(), missao_id))
    log_evento(org_id, "missao_dia_concluido", "missao", missao_id, paciente_id, {"dia": total_dias})
    return jsonify({"ok": True, "dias_concluidos": total_dias, "semana_completa": False})


@bp.post("/missao/<int:missao_id>/feedback")
@login_required
@papel_required("responsavel")
def enviar_feedback(missao_id):
    """
    UX Pattern D-02 (Doc 013): depois de concluir a missão, a família pode
    deixar um feedback rápido pro profissional — texto curto + um "humor"
    (emoji) resumindo como foi.
    """
    missao = query_one("SELECT * FROM missoes WHERE id = ?", (missao_id,))
    if not missao:
        return jsonify({"erro": "Missão não encontrada."}), 404
    plano = query_one("SELECT jornada_id FROM planos_terapeuticos WHERE id = ?", (missao["plano_id"],))
    jornada = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (plano["jornada_id"],)) if plano else None
    if not jornada or not paciente_acessivel(jornada["paciente_id"]):
        return jsonify({"erro": "Sem acesso a esta missão."}), 403

    body = request.get_json(force=True, silent=True) or {}
    texto = (body.get("texto") or "").strip()
    humor = body.get("humor", "🙂")
    if humor not in ("😄", "🙂", "😐", "😕"):
        humor = "🙂"
    if not texto:
        return jsonify({"erro": "Escreva um comentário rápido antes de enviar."}), 400

    fb_id = execute(
        "INSERT INTO feedbacks_familia (missao_id, usuario_id, texto, humor) VALUES (?, ?, ?, ?)",
        (missao_id, g.usuario["id"], texto, humor),
    )
    paciente = query_one("SELECT organizacao_id FROM pacientes WHERE id = ?", (jornada["paciente_id"],))
    log_evento(paciente["organizacao_id"], "feedback_familia_enviado", "feedback_familia", fb_id, jornada["paciente_id"])
    return jsonify({"id": fb_id}), 201


# Nota: o registro de evolução clínica migrou para o Módulo 07 — Diário
# Terapêutico (ver backend/blueprints/diario_bp.py, prefixo /api/diario).


@bp.post("/jornada/<int:jornada_id>/marco")
@login_required
@papel_required("profissional", "gestor")
def registrar_marco(jornada_id):
    jornada_mc = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (jornada_id,))
    if not jornada_mc or not paciente_editavel(jornada_mc["paciente_id"]):
        return jsonify({"erro": "Você não tem permissão para editar este paciente."}), 403
    body = request.get_json(force=True, silent=True) or {}
    marco_id = execute(
        "INSERT INTO marcos_terapeuticos (jornada_id, titulo, descricao) VALUES (?, ?, ?)",
        (jornada_id, body.get("titulo", "Marco alcançado"), body.get("descricao", "")),
    )
    return jsonify({"id": marco_id}), 201
