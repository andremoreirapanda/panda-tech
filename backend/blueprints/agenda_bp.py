"""
Domínio 5 — Agenda (Documento 09 / Módulo 05)

Regra de acesso (insight do usuário): por padrão, um profissional só
gerencia (cria/edita/exclui) a agenda dos pacientes vinculados a ele. O
gestor pode dar a um profissional específico permissão pra gerenciar a
agenda de QUALQUER paciente da clínica — ver `usuarios.agenda_permissao_total`,
configurável no cadastro/edição do profissional (Doc pessoas_bp.py).
Gestor e Admin sempre têm acesso total.

Vínculo automático (spec 24/09/2026): agendar ou reatribuir uma consulta
vincula o profissional que atende ao paciente — ver
`_garantir_vinculo_profissional`.
"""
from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute, log_evento, log_auditoria
from auth import login_required, papel_required, paciente_acessivel
from calendar_sync_service import sincronizar_consulta_google
from whatsapp_service import enviar_lembrete_consulta
import ausencias_service
from validacao_campos import validar_duracao

bp = Blueprint("agenda", __name__, url_prefix="/api/agenda")


def _paciente_da_mesma_clinica(paciente_id, organizacao_id):
    row = query_one("SELECT 1 FROM pacientes WHERE id = ? AND organizacao_id = ?", (paciente_id, organizacao_id))
    return bool(row)


def _pode_gerenciar_paciente_na_agenda(usuario, paciente_id):
    """Confere se o usuário pode criar/editar/excluir consultas desse paciente."""
    if usuario["papel"] == "admin_master":
        return True
    if usuario["papel"] in ("gestor", "secretaria"):
        # Secretária (insight do usuário, 31/08/2026): função administrativa,
        # sempre com acesso total à agenda da própria clínica — igual gestor,
        # sem depender de `agenda_permissao_total` (essa flag é só entre
        # profissionais).
        return _paciente_da_mesma_clinica(paciente_id, usuario["organizacao_id"])
    if usuario["papel"] == "profissional":
        if usuario.get("agenda_permissao_total"):
            return _paciente_da_mesma_clinica(paciente_id, usuario["organizacao_id"])
        return paciente_acessivel(paciente_id)
    return False


def _pode_gerenciar_consulta(usuario, consulta):
    if usuario["papel"] == "admin_master":
        return True
    if usuario["papel"] in ("gestor", "secretaria"):
        # Correção de auditoria: um gestor só gerencia consultas da própria
        # clínica — antes, qualquer gestor conseguia editar/cancelar/excluir
        # consultas de QUALQUER clínica só pelo id, sem checar organizacao_id.
        # Secretária (insight do usuário, 31/08/2026): mesma regra do gestor.
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
        """SELECT 1 FROM usuarios WHERE id = ? AND organizacao_id = ? AND ativo = 1 AND excluido_em IS NULL
           AND (papel = 'profissional' OR (papel = 'gestor' AND atua_como_profissional = 1))""",
        (profissional_id, organizacao_id),
    )
    return bool(row)


def _garantir_vinculo_profissional(usuario, org_id, profissional_id, paciente_id):
    """Vínculo automático ao agendar (spec 24/09/2026): quem atende o
    paciente passa a constar em `profissionais_pacientes` ("quem atende"). Desde
    01/10/2026 isso não dá mais acesso (todo profissional da clínica edita);
    serve para avisos de mensagem e o "N pacientes" da Equipe.
    Gestor (inclusive o que atua como profissional) não precisa de vínculo —
    já tem acesso total. `principal` segue a mesma regra de
    pessoas_bp.vincular_profissional: só se o paciente ainda não tem um."""
    prof = query_one("SELECT id, nome, papel FROM usuarios WHERE id = ?", (profissional_id,))
    if not prof or prof["papel"] != "profissional":
        return
    ja_vinculado = query_one(
        "SELECT 1 FROM profissionais_pacientes WHERE usuario_id = ? AND paciente_id = ?",
        (profissional_id, paciente_id),
    )
    if ja_vinculado:
        return
    ja_tem_principal = query_one(
        "SELECT 1 FROM profissionais_pacientes WHERE paciente_id = ? AND principal = 1", (paciente_id,)
    )
    # ON CONFLICT: duplo clique em "Agendar" faz duas requisições passarem
    # juntas pela checagem acima — a segunda não pode estourar o UNIQUE
    # (erro 500 com a consulta já gravada). SQLite 3.24+ e Postgres aceitam.
    execute(
        """INSERT INTO profissionais_pacientes (usuario_id, paciente_id, principal) VALUES (?, ?, ?)
           ON CONFLICT (usuario_id, paciente_id) DO NOTHING""",
        (profissional_id, paciente_id, 0 if ja_tem_principal else 1),
    )
    log_auditoria(org_id, usuario["id"], "vincular", "profissional_paciente", paciente_id, prof["nome"])


DURACAO_MIN, DURACAO_MAX = 5, 480


def _duracao_do_corpo(body, org_id):
    """duracao_min do corpo (validada) ou o padrão da clínica (spec 07/10/2026)."""
    if "duracao_min" in body and body.get("duracao_min") not in (None, ""):
        return validar_duracao(body.get("duracao_min"), DURACAO_MIN, DURACAO_MAX)
    org = query_one("SELECT agenda_duracao_padrao FROM organizacoes WHERE id = ?", (org_id,))
    return int((org or {}).get("agenda_duracao_padrao") or 50), None


def _resposta_conflito(profissional_id, aus):
    """409 com o nome do profissional e o motivo da ausência que bloqueou."""
    prof = query_one("SELECT nome FROM usuarios WHERE id = ?", (profissional_id,))
    motivo = f" ({aus['motivo']})" if aus.get("motivo") else ""
    return jsonify({"erro": f"{(prof or {}).get('nome', 'O profissional')} está ausente nesse horário{motivo}.",
                    "ausencia_id": aus["id"]}), 409


@bp.get("")
@login_required
def listar_consultas():
    u = g.usuario
    campos_prof = "prof.nome as profissional_nome, prof.cor_agenda as profissional_cor"
    if u["papel"] in ("gestor", "admin_master", "secretaria"):
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
@papel_required("gestor", "profissional", "admin_master", "secretaria")
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
    duracao, erro_dur = _duracao_do_corpo(body, org_id)
    if erro_dur:
        return jsonify({"erro": erro_dur}), 400
    aus = ausencias_service.conflito_ausencia(profissional_id, body.get("data_hora"), duracao)
    if aus:
        return _resposta_conflito(profissional_id, aus)
    consulta_id = execute(
        """INSERT INTO consultas (paciente_id, profissional_id, data_hora, duracao_min, observacoes)
           VALUES (?, ?, ?, ?, ?)""",
        (paciente_id, profissional_id, body["data_hora"],
         duracao, body.get("observacoes", "")),
    )
    _garantir_vinculo_profissional(u, org_id, profissional_id, paciente_id)
    log_evento(org_id, "consulta_agendada", "consulta", consulta_id, paciente_id)
    sincronizar_consulta_google(consulta_id, org_id, acao="criar")
    return jsonify({"id": consulta_id}), 201


FREQUENCIAS_RECORRENCIA = {"semanal": 7, "quinzenal": 14, "mensal": None}  # mensal soma meses, não dias
LIMITE_OCORRENCIAS = 52  # ~1 ano no ritmo semanal — evita gerar recorrência sem fim


@bp.post("/recorrente")
@login_required
@papel_required("gestor", "profissional", "admin_master", "secretaria")
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
    observacoes = body.get("observacoes", "")
    org_id = u["organizacao_id"] or query_one("SELECT organizacao_id FROM pacientes WHERE id=?", (paciente_id,))["organizacao_id"]
    if not _profissional_da_mesma_clinica(profissional_id, org_id):
        return jsonify({"erro": "Profissional inválido para esta clínica."}), 400
    duracao_min, erro_dur = _duracao_do_corpo(body, org_id)
    if erro_dur:
        return jsonify({"erro": erro_dur}), 400

    # Duas fases (spec 07/10/2026): calcula as datas, separa as que caem numa
    # ausência do profissional (puladas e avisadas) e só então insere.
    datas = []
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
        datas.append(data_ocorrencia.strftime("%Y-%m-%d %H:%M:%S"))

    livres, datas_puladas = [], []
    for dh in datas:
        if ausencias_service.conflito_ausencia(profissional_id, dh, duracao_min):
            datas_puladas.append(dh[:10])
        else:
            livres.append(dh)
    if not livres:
        prof = query_one("SELECT nome FROM usuarios WHERE id = ?", (profissional_id,))
        return jsonify({"erro": f"{(prof or {}).get('nome', 'O profissional')} está ausente em todas as datas da repetição."}), 409

    ids_criados = []
    serie_id = None
    for dh in livres:
        consulta_id = execute(
            """INSERT INTO consultas (paciente_id, profissional_id, data_hora, duracao_min, observacoes, serie_recorrencia_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (paciente_id, profissional_id, dh, duracao_min, observacoes, serie_id),
        )
        if serie_id is None:
            serie_id = consulta_id
            execute("UPDATE consultas SET serie_recorrencia_id = ? WHERE id = ?", (serie_id, consulta_id))
        ids_criados.append(consulta_id)
        sincronizar_consulta_google(consulta_id, org_id, acao="criar")

    _garantir_vinculo_profissional(u, org_id, profissional_id, paciente_id)
    log_evento(org_id, "consulta_recorrente_agendada", "consulta", serie_id, paciente_id)
    return jsonify({"serie_recorrencia_id": serie_id, "ids": ids_criados, "total_criadas": len(ids_criados),
                    "datas_puladas": datas_puladas}), 201


@bp.put("/<int:consulta_id>")
@login_required
@papel_required("gestor", "profissional", "admin_master", "secretaria")
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

    nova_data_hora = body.get("data_hora", consulta["data_hora"])
    duracao_atual = consulta["duracao_min"] or 50
    nova_duracao = duracao_atual
    # Só valida a duração se ela mudou: consulta antiga com duração fora da
    # faixa (dado legado) continua editável (pendência de 08/10/2026).
    if "duracao_min" in body and body.get("duracao_min") != duracao_atual:
        nova_duracao, erro_dur = validar_duracao(body.get("duracao_min"), DURACAO_MIN, DURACAO_MAX)
        if erro_dur:
            return jsonify({"erro": erro_dur}), 400
    # Só checa ausência se mudou quando/quem (spec 07/10/2026): editar só a
    # observação de uma consulta antiga não pode travar por ausência nova.
    # A hora é comparada já normalizada ("9:00:00" == "09:00:00").
    mudou_horario = (ausencias_service.separar_data_hora(nova_data_hora) != ausencias_service.separar_data_hora(consulta["data_hora"])
                     or nova_duracao != duracao_atual or novo_profissional_id != consulta["profissional_id"])
    if mudou_horario and consulta["status"] != "cancelada":
        aus = ausencias_service.conflito_ausencia(novo_profissional_id, nova_data_hora, nova_duracao)
        if aus:
            return _resposta_conflito(novo_profissional_id, aus)

    execute(
        "UPDATE consultas SET data_hora = ?, profissional_id = ?, duracao_min = ?, observacoes = ? WHERE id = ?",
        (nova_data_hora, novo_profissional_id, nova_duracao,
         body.get("observacoes", consulta["observacoes"]), consulta_id),
    )
    if novo_profissional_id != consulta["profissional_id"]:
        _garantir_vinculo_profissional(u, org_id, novo_profissional_id, consulta["paciente_id"])
    log_evento(org_id, "consulta_atualizada", "consulta", consulta_id, consulta["paciente_id"])
    sincronizar_consulta_google(consulta_id, org_id, acao="atualizar")
    return jsonify({"ok": True})


@bp.put("/<int:consulta_id>/status")
@login_required
@papel_required("gestor", "profissional", "admin_master", "secretaria")
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
    # Desfazer o cancelamento não pode furar uma ausência criada depois
    # (revisão de 07/10/2026). Registrar desfecho (realizada/faltou) segue livre.
    if consulta["status"] == "cancelada" and novo_status in ("agendada", "confirmada"):
        aus = ausencias_service.conflito_ausencia(consulta["profissional_id"], consulta["data_hora"], consulta["duracao_min"] or 50)
        if aus:
            return _resposta_conflito(consulta["profissional_id"], aus)
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
@papel_required("gestor", "profissional", "admin_master", "secretaria")
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


# ---------------------------------------------------------------- Ausências (spec 07/10/2026)

MAX_DIAS_AUSENCIAS = 62


def _ve_agenda_toda(u):
    return u["papel"] in ("gestor", "secretaria") or (u["papel"] == "profissional" and u.get("agenda_permissao_total"))


def _pode_editar_ausencia(u, aus):
    """Profissional: só as dele. Gestor e secretária: qualquer uma da clínica."""
    if aus["organizacao_id"] != u["organizacao_id"]:
        return False
    if u["papel"] in ("gestor", "secretaria"):
        return True
    return aus["profissional_id"] == u["id"]


def _alvo_da_ausencia(u, body):
    """Profissional da ausência, ou (None, resposta_de_erro)."""
    try:
        alvo = int(body.get("profissional_id") or u["id"])
    except (TypeError, ValueError):
        return None, (jsonify({"erro": "Profissional inválido."}), 400)
    if u["papel"] == "profissional":
        if alvo != u["id"]:
            return None, (jsonify({"erro": "Você só pode lançar ausências na sua própria agenda."}), 403)
        return alvo, None
    if not _profissional_da_mesma_clinica(alvo, u["organizacao_id"]):
        return None, (jsonify({"erro": "Profissional inválido para esta clínica."}), 400)
    return alvo, None


@bp.get("/ausencias")
@login_required
@papel_required("gestor", "profissional", "secretaria")
def listar_ausencias():
    u = g.usuario
    ini = ausencias_service._data(request.args.get("inicio"))
    fim = ausencias_service._data(request.args.get("fim"))
    if not ini or not fim or fim < ini:
        return jsonify({"erro": "Intervalo de datas inválido."}), 400
    if (fim - ini).days > MAX_DIAS_AUSENCIAS:
        return jsonify({"erro": f"Peça no máximo {MAX_DIAS_AUSENCIAS} dias de cada vez."}), 400
    sql = """SELECT a.*, prof.nome AS profissional_nome FROM ausencias_profissional a
             JOIN usuarios prof ON prof.id = a.profissional_id
             WHERE a.organizacao_id = ? AND a.data_inicio <= ? AND (a.data_fim IS NULL OR a.data_fim >= ?)"""
    params = [u["organizacao_id"], fim.isoformat(), ini.isoformat()]
    if not _ve_agenda_toda(u):
        sql += " AND a.profissional_id = ?"
        params.append(u["id"])
    regras = query(sql, tuple(params))
    nomes = {r["id"]: r["profissional_nome"] for r in regras}
    editaveis = {r["id"]: _pode_editar_ausencia(u, r) for r in regras}
    saida = ausencias_service.ocorrencias(regras, ini, fim)
    for o in saida:
        o["profissional_nome"] = nomes.get(o["ausencia_id"])
        o["pode_editar"] = editaveis.get(o["ausencia_id"], False)
    return jsonify(saida)


@bp.post("/ausencias")
@login_required
@papel_required("gestor", "profissional", "secretaria")
def criar_ausencia():
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    alvo, erro_resp = _alvo_da_ausencia(u, body)
    if erro_resp:
        return erro_resp
    dados, erro = ausencias_service.validar_ausencia(body)
    if erro:
        return jsonify({"erro": erro}), 400
    aus_id = execute(
        """INSERT INTO ausencias_profissional (organizacao_id, profissional_id, data_inicio, data_fim, dia_inteiro,
           hora_inicio, hora_fim, dias_semana, motivo, criado_por) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (u["organizacao_id"], alvo, dados["data_inicio"], dados["data_fim"], dados["dia_inteiro"],
         dados["hora_inicio"], dados["hora_fim"], dados["dias_semana"], dados["motivo"], u["id"]),
    )
    log_auditoria(u["organizacao_id"], u["id"], "criar", "ausencia", aus_id, dados["motivo"] or "")
    return jsonify({"id": aus_id, "consultas_no_periodo": ausencias_service.consultas_no_periodo({**dados, "profissional_id": alvo})}), 201


def _ausencia_da_clinica(u, aus_id):
    return query_one("SELECT * FROM ausencias_profissional WHERE id = ? AND organizacao_id = ?", (aus_id, u["organizacao_id"]))


@bp.put("/ausencias/<int:aus_id>")
@login_required
@papel_required("gestor", "profissional", "secretaria")
def editar_ausencia(aus_id):
    u = g.usuario
    aus = _ausencia_da_clinica(u, aus_id)
    if not aus:
        return jsonify({"erro": "Ausência não encontrada."}), 404
    if not _pode_editar_ausencia(u, aus):
        return jsonify({"erro": "Você não pode alterar esta ausência."}), 403
    body = request.get_json(force=True, silent=True) or {}
    dados, erro = ausencias_service.validar_ausencia(body)
    if erro:
        return jsonify({"erro": erro}), 400
    execute(
        """UPDATE ausencias_profissional SET data_inicio = ?, data_fim = ?, dia_inteiro = ?, hora_inicio = ?,
           hora_fim = ?, dias_semana = ?, motivo = ? WHERE id = ?""",
        (dados["data_inicio"], dados["data_fim"], dados["dia_inteiro"], dados["hora_inicio"],
         dados["hora_fim"], dados["dias_semana"], dados["motivo"], aus_id),
    )
    log_auditoria(u["organizacao_id"], u["id"], "editar", "ausencia", aus_id, dados["motivo"] or "")
    return jsonify({"ok": True, "consultas_no_periodo": ausencias_service.consultas_no_periodo({**dados, "profissional_id": aus["profissional_id"]})})


@bp.delete("/ausencias/<int:aus_id>")
@login_required
@papel_required("gestor", "profissional", "secretaria")
def excluir_ausencia(aus_id):
    u = g.usuario
    aus = _ausencia_da_clinica(u, aus_id)
    if not aus:
        return jsonify({"erro": "Ausência não encontrada."}), 404
    if not _pode_editar_ausencia(u, aus):
        return jsonify({"erro": "Você não pode apagar esta ausência."}), 403
    execute("DELETE FROM ausencias_profissional WHERE id = ?", (aus_id,))
    log_auditoria(u["organizacao_id"], u["id"], "excluir", "ausencia", aus_id, aus.get("motivo") or "")
    return jsonify({"ok": True})
