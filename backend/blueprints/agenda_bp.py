"""
Domínio 5 — Agenda (Documento 09 / Módulo 05)

Regra de acesso (insight do usuário): por padrão, um profissional só
gerencia (cria/edita/exclui) a agenda dos pacientes vinculados a ele. O
gestor pode dar a um profissional específico permissão pra gerenciar a
agenda de QUALQUER paciente da clínica — ver `usuarios.agenda_permissao_total`,
configurável no cadastro/edição do profissional (Doc pessoas_bp.py).
Gestor e Admin sempre têm acesso total.
"""
from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute, log_evento
from auth import login_required, papel_required, paciente_acessivel
from calendar_sync_service import sincronizar_consulta_google
from whatsapp_service import enviar_lembrete_consulta

bp = Blueprint("agenda", __name__, url_prefix="/api/agenda")


def _paciente_da_mesma_clinica(paciente_id, organizacao_id):
    row = query_one("SELECT 1 FROM pacientes WHERE id = ? AND organizacao_id = ?", (paciente_id, organizacao_id))
    return bool(row)


def _pode_gerenciar_paciente_na_agenda(usuario, paciente_id):
    """Confere se o usuário pode criar/editar/excluir consultas desse paciente."""
    if usuario["papel"] in ("gestor", "admin_master"):
        return _paciente_da_mesma_clinica(paciente_id, usuario["organizacao_id"]) if usuario["papel"] == "gestor" else True
    if usuario["papel"] == "profissional":
        if usuario.get("agenda_permissao_total"):
            return _paciente_da_mesma_clinica(paciente_id, usuario["organizacao_id"])
        return paciente_acessivel(paciente_id)
    return False


def _pode_gerenciar_consulta(usuario, consulta):
    if usuario["papel"] == "admin_master":
        return True
    if usuario["papel"] == "gestor":
        # Correção de auditoria: um gestor só gerencia consultas da própria
        # clínica — antes, qualquer gestor conseguia editar/cancelar/excluir
        # consultas de QUALQUER clínica só pelo id, sem checar organizacao_id.
        return _paciente_da_mesma_clinica(consulta["paciente_id"], usuario["organizacao_id"])
    if usuario["papel"] == "profissional":
        if usuario.get("agenda_permissao_total"):
            return _paciente_da_mesma_clinica(consulta["paciente_id"], usuario["organizacao_id"])
        return consulta["profissional_id"] == usuario["id"]
    return False


def _profissional_da_mesma_clinica(profissional_id, organizacao_id):
    """Confere se o id informado é de fato um profissional ativo desta clínica —
    evita que um gestor/profissional atribua uma consulta a um profissional de
    outra clínica (o que vazaria dados do paciente pra fora da organização).
    Também aceita o próprio gestor da clínica, quando ele ligou "atuar como
    profissional" (insight do usuário — mesma conta/login, ver pessoas_bp.py)."""
    row = query_one(
        """SELECT 1 FROM usuarios WHERE id = ? AND organizacao_id = ?
           AND (papel = 'profissional' OR (papel = 'gestor' AND atua_como_profissional = 1))""",
        (profissional_id, organizacao_id),
    )
    return bool(row)


@bp.get("")
@login_required
def listar_consultas():
    u = g.usuario
    campos_prof = "prof.nome as profissional_nome, prof.cor_agenda as profissional_cor"
    if u["papel"] in ("gestor", "admin_master"):
        rows = query(
            f"""SELECT c.*, p.nome as paciente_nome, p.avatar_mascote, {campos_prof}
               FROM consultas c
               JOIN pacientes p ON p.id = c.paciente_id
               JOIN usuarios prof ON prof.id = c.profissional_id
               WHERE p.organizacao_id = ? ORDER BY c.data_hora""",
            (u["organizacao_id"],),
        )
    elif u["papel"] == "profissional":
        if u.get("agenda_permissao_total"):
            # Vê a agenda inteira da clínica, não só a própria — mesma regra do gestor.
            rows = query(
                f"""SELECT c.*, p.nome as paciente_nome, p.avatar_mascote, {campos_prof}
                   FROM consultas c
                   JOIN pacientes p ON p.id = c.paciente_id
                   JOIN usuarios prof ON prof.id = c.profissional_id
                   WHERE p.organizacao_id = ? ORDER BY c.data_hora""",
                (u["organizacao_id"],),
            )
        else:
            rows = query(
                f"""SELECT c.*, p.nome as paciente_nome, p.avatar_mascote, {campos_prof}
                   FROM consultas c
                   JOIN pacientes p ON p.id = c.paciente_id
                   JOIN usuarios prof ON prof.id = c.profissional_id
                   WHERE c.profissional_id = ? ORDER BY c.data_hora""",
                (u["id"],),
            )
    elif u["papel"] == "responsavel":
        rows = query(
            f"""SELECT c.*, p.nome as paciente_nome, p.avatar_mascote, {campos_prof}
               FROM consultas c
               JOIN pacientes p ON p.id = c.paciente_id
               JOIN usuarios prof ON prof.id = c.profissional_id
               JOIN responsaveis_pacientes rp ON rp.paciente_id = p.id
               WHERE rp.usuario_id = ? ORDER BY c.data_hora""",
            (u["id"],),
        )
    else:
        rows = []
    return jsonify(rows)


@bp.post("")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def criar_consulta():
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    paciente_id = body.get("paciente_id")
    if not _pode_gerenciar_paciente_na_agenda(u, paciente_id):
        return jsonify({"erro": "Sem acesso a este paciente."}), 403
    org_id = u["organizacao_id"] or query_one("SELECT organizacao_id FROM pacientes WHERE id=?", (paciente_id,))["organizacao_id"]
    profissional_id = body.get("profissional_id", u["id"])
    # Correção de auditoria: valida que o profissional atribuído é da mesma
    # clínica do paciente — sem isso, dava pra marcar uma consulta de um
    # paciente com o id de um profissional de outra clínica, que passava a
    # enxergar o paciente (nome, avatar, horário) na própria agenda.
    if not _profissional_da_mesma_clinica(profissional_id, org_id):
        return jsonify({"erro": "Profissional inválido para esta clínica."}), 400
    consulta_id = execute(
        """INSERT INTO consultas (paciente_id, profissional_id, data_hora, duracao_min, observacoes)
           VALUES (?, ?, ?, ?, ?)""",
        (paciente_id, profissional_id, body["data_hora"],
         body.get("duracao_min", 50), body.get("observacoes", "")),
    )
    log_evento(org_id, "consulta_agendada", "consulta", consulta_id, paciente_id)
    sincronizar_consulta_google(consulta_id, org_id, acao="criar")
    return jsonify({"id": consulta_id}), 201


FREQUENCIAS_RECORRENCIA = {"semanal": 7, "quinzenal": 14, "mensal": None}  # mensal soma meses, não dias
LIMITE_OCORRENCIAS = 52  # ~1 ano no ritmo semanal — evita gerar recorrência sem fim


@bp.post("/recorrente")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def criar_consulta_recorrente():
    """
    Agendamento recorrente (insight do usuário): agenda o mesmo paciente no
    mesmo horário, repetindo semanal/quinzenal/mensalmente por N ocorrências.
    Todas as consultas geradas compartilham `serie_recorrencia_id` — usa o id
    da primeira consulta da série, pra depois dar pra cancelar "esta e as
    futuras" de uma vez (ver excluir_consulta).
    """
    from datetime import datetime, timedelta

    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    paciente_id = body.get("paciente_id")
    if not _pode_gerenciar_paciente_na_agenda(u, paciente_id):
        return jsonify({"erro": "Sem acesso a este paciente."}), 403

    frequencia = body.get("frequencia")
    if frequencia not in FREQUENCIAS_RECORRENCIA:
        return jsonify({"erro": "Frequência inválida — use 'semanal', 'quinzenal' ou 'mensal'."}), 400
    try:
        repeticoes = int(body.get("repeticoes", 1))
    except (TypeError, ValueError):
        return jsonify({"erro": "Número de repetições inválido."}), 400
    if repeticoes < 1 or repeticoes > LIMITE_OCORRENCIAS:
        return jsonify({"erro": f"Escolha entre 1 e {LIMITE_OCORRENCIAS} repetições."}), 400
    try:
        data_hora_inicial = datetime.strptime(body["data_hora"], "%Y-%m-%d %H:%M:%S")
    except (KeyError, ValueError):
        return jsonify({"erro": "Data/hora inicial inválida."}), 400

    profissional_id = body.get("profissional_id", u["id"])
    duracao_min = body.get("duracao_min", 50)
    observacoes = body.get("observacoes", "")
    org_id = u["organizacao_id"] or query_one("SELECT organizacao_id FROM pacientes WHERE id=?", (paciente_id,))["organizacao_id"]
    if not _profissional_da_mesma_clinica(profissional_id, org_id):
        return jsonify({"erro": "Profissional inválido para esta clínica."}), 400

    ids_criados = []
    serie_id = None
    for i in range(repeticoes):
        if frequencia == "mensal":
            # Soma meses de verdade (não só 30 dias) — cai no mesmo dia do mês seguinte.
            mes_total = data_hora_inicial.month - 1 + i
            ano = data_hora_inicial.year + mes_total // 12
            mes = mes_total % 12 + 1
            try:
                data_ocorrencia = data_hora_inicial.replace(year=ano, month=mes)
            except ValueError:
                # Dia não existe no mês de destino (ex: 31 em abril) — usa o último dia válido.
                proximo_mes = mes % 12 + 1
                ano_aux = ano + (1 if mes == 12 else 0)
                data_ocorrencia = data_hora_inicial.replace(year=ano_aux, month=proximo_mes, day=1) - timedelta(days=1)
                data_ocorrencia = data_ocorrencia.replace(hour=data_hora_inicial.hour, minute=data_hora_inicial.minute)
        else:
            data_ocorrencia = data_hora_inicial + timedelta(days=FREQUENCIAS_RECORRENCIA[frequencia] * i)

        consulta_id = execute(
            """INSERT INTO consultas (paciente_id, profissional_id, data_hora, duracao_min, observacoes, serie_recorrencia_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (paciente_id, profissional_id, data_ocorrencia.strftime("%Y-%m-%d %H:%M:%S"), duracao_min, observacoes, serie_id),
        )
        if serie_id is None:
            serie_id = consulta_id
            execute("UPDATE consultas SET serie_recorrencia_id = ? WHERE id = ?", (serie_id, consulta_id))
        ids_criados.append(consulta_id)
        sincronizar_consulta_google(consulta_id, org_id, acao="criar")

    log_evento(org_id, "consulta_recorrente_agendada", "consulta", serie_id, paciente_id)
    return jsonify({"serie_recorrencia_id": serie_id, "ids": ids_criados, "total_criadas": len(ids_criados)}), 201


@bp.put("/<int:consulta_id>")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def editar_consulta(consulta_id):
    """
    Edição geral (insight do usuário): além do status, dá pra trocar data,
    horário e até o profissional que vai atender — não só cancelar e
    recriar do zero. Se a consulta faz parte de uma série recorrente,
    edita só essa ocorrência (as demais da série continuam intactas).
    """
    u = g.usuario
    consulta = query_one("SELECT * FROM consultas WHERE id = ?", (consulta_id,))
    if not consulta:
        return jsonify({"erro": "Consulta não encontrada."}), 404
    if not _pode_gerenciar_consulta(u, consulta):
        return jsonify({"erro": "Você não tem permissão para gerenciar esta consulta."}), 403
    if consulta["status"] == "realizada":
        return jsonify({"erro": "Não é possível editar uma consulta já realizada."}), 409

    body = request.get_json(force=True, silent=True) or {}
    org_id = u["organizacao_id"] or query_one("SELECT organizacao_id FROM pacientes WHERE id=?", (consulta["paciente_id"],))["organizacao_id"]
    novo_profissional_id = body.get("profissional_id", consulta["profissional_id"])
    # Trocar o profissional exige que quem edita também possa gerenciar a
    # agenda desse novo profissional pro mesmo paciente (mesma regra de criar),
    # e que o novo profissional seja de fato da mesma clínica do paciente
    # (correção de auditoria — sem isso dava pra reatribuir a consulta a um
    # profissional de outra clínica).
    if novo_profissional_id != consulta["profissional_id"]:
        if not _pode_gerenciar_paciente_na_agenda(u, consulta["paciente_id"]):
            return jsonify({"erro": "Sem permissão para reatribuir esta consulta."}), 403
        if not _profissional_da_mesma_clinica(novo_profissional_id, org_id):
            return jsonify({"erro": "Profissional inválido para esta clínica."}), 400

    execute(
        "UPDATE consultas SET data_hora = ?, profissional_id = ?, duracao_min = ?, observacoes = ? WHERE id = ?",
        (body.get("data_hora", consulta["data_hora"]), novo_profissional_id,
         body.get("duracao_min", consulta["duracao_min"]), body.get("observacoes", consulta["observacoes"]), consulta_id),
    )
    log_evento(org_id, "consulta_atualizada", "consulta", consulta_id, consulta["paciente_id"])
    sincronizar_consulta_google(consulta_id, org_id, acao="atualizar")
    return jsonify({"ok": True})


@bp.put("/<int:consulta_id>/status")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def atualizar_status(consulta_id):
    u = g.usuario
    consulta = query_one("SELECT * FROM consultas WHERE id = ?", (consulta_id,))
    if not consulta:
        return jsonify({"erro": "Consulta não encontrada."}), 404
    if not _pode_gerenciar_consulta(u, consulta):
        return jsonify({"erro": "Você não tem permissão para gerenciar esta consulta."}), 403

    body = request.get_json(force=True, silent=True) or {}
    novo_status = body.get("status")
    if novo_status not in ("agendada", "confirmada", "realizada", "cancelada", "faltou"):
        return jsonify({"erro": "Status inválido."}), 400
    execute("UPDATE consultas SET status = ? WHERE id = ?", (novo_status, consulta_id))
    tipo_evento = "consulta_realizada" if novo_status == "realizada" else (
        "consulta_cancelada" if novo_status == "cancelada" else "consulta_atualizada"
    )
    org_id = u["organizacao_id"] or query_one("SELECT organizacao_id FROM pacientes WHERE id=?", (consulta["paciente_id"],))["organizacao_id"]
    log_evento(org_id, tipo_evento, "consulta", consulta_id, consulta["paciente_id"])
    sincronizar_consulta_google(consulta_id, org_id, acao="excluir" if novo_status == "cancelada" else "atualizar")
    if novo_status == "confirmada":
        enviar_lembrete_consulta(consulta_id)
    return jsonify({"ok": True})


@bp.delete("/<int:consulta_id>")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def excluir_consulta(consulta_id):
    """
    Exclusão de verdade — só permitida antes da consulta ser realizada
    (depois disso, ela vira histórico clínico e deve ser só cancelada, não apagada).

    Se `?serie=1` for passado e a consulta fizer parte de uma série
    recorrente, exclui essa e todas as futuras da mesma série (as passadas
    ficam intactas, viram histórico).
    """
    u = g.usuario
    consulta = query_one("SELECT * FROM consultas WHERE id = ?", (consulta_id,))
    if not consulta:
        return jsonify({"erro": "Consulta não encontrada."}), 404
    if not _pode_gerenciar_consulta(u, consulta):
        return jsonify({"erro": "Você não tem permissão para gerenciar esta consulta."}), 403
    if consulta["status"] == "realizada":
        return jsonify({"erro": "Não é possível excluir uma consulta já realizada — use o cancelamento se necessário."}), 409

    org_id = u["organizacao_id"] or query_one("SELECT organizacao_id FROM pacientes WHERE id=?", (consulta["paciente_id"],))["organizacao_id"]

    excluir_serie = request.args.get("serie") == "1" and consulta["serie_recorrencia_id"]
    if excluir_serie:
        futuras = query(
            """SELECT id FROM consultas WHERE serie_recorrencia_id = ? AND data_hora >= ? AND status != 'realizada'""",
            (consulta["serie_recorrencia_id"], consulta["data_hora"]),
        )
        for c in futuras:
            execute("DELETE FROM consultas WHERE id = ?", (c["id"],))
        log_evento(org_id, "serie_recorrente_excluida", "consulta", consulta["serie_recorrencia_id"], consulta["paciente_id"])
        return jsonify({"ok": True, "total_excluidas": len(futuras)})

    execute("DELETE FROM consultas WHERE id = ?", (consulta_id,))
    log_evento(org_id, "consulta_excluida", "consulta", consulta_id, consulta["paciente_id"])
    return jsonify({"ok": True})
