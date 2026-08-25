"""
Módulo 07 — Diário Terapêutico

"Responsável por registrar e compartilhar a evolução clínica da criança em
linguagem acessível para a família." Ao invés de apenas ver um gráfico, os
responsáveis passam a entender o que realmente está acontecendo com o filho.

Fluxo (conforme especificação):
Selecionar paciente → Abrir Jornada Terapêutica → Novo Diário Terapêutico →
Descrever evolução clínica → Registrar pontos positivos → Registrar pontos
de atenção → Definir objetivo da próxima semana → Escrever mensagem para a
família → Salvar → Família recebe notificação.

Requisitos implementados:
- FR-010: profissional registra evolução ao final de cada atendimento.
- FR-010: cada evolução é compartilhada automaticamente com os responsáveis
  (gera notificação — compartilhado_familia é True por padrão).
- FR-010: evoluções ficam organizadas em ordem cronológica na Jornada.
- BR-010: somente profissionais VINCULADOS ao paciente podem criar registros.
"""
import base64
import json
from datetime import date

from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute, log_evento, criar_notificacao
from auth import login_required, papel_required, paciente_acessivel, paciente_editavel

bp = Blueprint("diario", __name__, url_prefix="/api/diario")

# Limite de tamanho por anexo (demonstração — anexos pequenos, não é storage de produção)
LIMITE_ANEXO_BYTES = 4 * 1024 * 1024  # 4 MB


def _serializar_diario(d, ocultar_evolucao_clinica=False):
    d["pontos_positivos"] = json.loads(d.pop("pontos_positivos_json") or "[]")
    d["pontos_atencao"] = json.loads(d.pop("pontos_atencao_json") or "[]")
    anexos = query(
        "SELECT id, tipo, nome_arquivo, tamanho_bytes, criado_em FROM diario_anexos WHERE diario_id = ? ORDER BY id",
        (d["id"],),
    )
    d["anexos"] = anexos
    if ocultar_evolucao_clinica:
        # A "Evolução clínica" é linguagem técnica pra equipe — sempre fica
        # guardada no registro, mas NUNCA é exposta à família, mesmo quando
        # o registro está marcado como compartilhado (só os demais campos
        # em linguagem acessível — pontos positivos/atenção, mensagem — vão).
        d["evolucao_clinica"] = None
    return d


def _checar_profissional_vinculado(paciente_id):
    """BR-010: somente profissionais vinculados ao paciente podem criar registros."""
    u = g.usuario
    if u["papel"] == "gestor":
        return True  # gestor da clínica sempre pode (visão administrativa)
    vinculado = query_one(
        "SELECT 1 FROM profissionais_pacientes WHERE usuario_id = ? AND paciente_id = ?",
        (u["id"], paciente_id),
    )
    return bool(vinculado)


@bp.get("/jornada/<int:jornada_id>")
@login_required
def listar_diarios(jornada_id):
    """Histórico completo, em ordem cronológica (mais recente primeiro)."""
    jornada = query_one("SELECT * FROM jornadas WHERE id = ?", (jornada_id,))
    if not jornada:
        return jsonify({"erro": "Jornada não encontrada."}), 404
    if not paciente_acessivel(jornada["paciente_id"]):
        return jsonify({"erro": "Sem acesso a esta jornada."}), 403

    u = g.usuario
    sql = """SELECT d.*, u.nome as profissional_nome, u.especialidade as profissional_especialidade
              FROM diarios_terapeuticos d JOIN usuarios u ON u.id = d.profissional_id
              WHERE d.jornada_id = ?"""
    # Responsável só vê os registros marcados como compartilhados com a família
    if u["papel"] == "responsavel":
        sql += " AND d.compartilhado_familia = 1"
    sql += " ORDER BY d.data_atendimento DESC, d.criado_em DESC"

    diarios = query(sql, (jornada_id,))
    return jsonify([_serializar_diario(d, ocultar_evolucao_clinica=(u["papel"] == "responsavel")) for d in diarios])


@bp.get("/<int:diario_id>")
@login_required
def obter_diario(diario_id):
    d = query_one(
        """SELECT d.*, u.nome as profissional_nome FROM diarios_terapeuticos d
           JOIN usuarios u ON u.id = d.profissional_id WHERE d.id = ?""",
        (diario_id,),
    )
    if not d:
        return jsonify({"erro": "Registro não encontrado."}), 404
    jornada = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (d["jornada_id"],))
    if not paciente_acessivel(jornada["paciente_id"]):
        return jsonify({"erro": "Sem acesso."}), 403
    return jsonify(_serializar_diario(d, ocultar_evolucao_clinica=(g.usuario["papel"] == "responsavel")))


@bp.post("/jornada/<int:jornada_id>")
@login_required
@papel_required("profissional", "gestor")
def criar_diario(jornada_id):
    """Novo Diário Terapêutico — o coração do Módulo 07."""
    u = g.usuario
    jornada = query_one("SELECT * FROM jornadas WHERE id = ?", (jornada_id,))
    if not jornada:
        return jsonify({"erro": "Jornada não encontrada."}), 404

    # BR-010: somente profissionais vinculados ao paciente podem criar registros.
    if not _checar_profissional_vinculado(jornada["paciente_id"]):
        return jsonify({"erro": "Apenas profissionais vinculados a este paciente podem registrar o diário."}), 403

    body = request.get_json(force=True, silent=True) or {}
    evolucao = (body.get("evolucao_clinica") or "").strip()
    if not evolucao:
        return jsonify({"erro": "A evolução clínica é obrigatória."}), 400

    compartilhar = body.get("compartilhado_familia", True)

    diario_id = execute(
        """INSERT INTO diarios_terapeuticos
           (jornada_id, profissional_id, consulta_id, data_atendimento, evolucao_clinica,
            pontos_positivos_json, pontos_atencao_json, objetivo_semana, mensagem_familia, compartilhado_familia)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (jornada_id, u["id"], body.get("consulta_id"), body.get("data_atendimento") or date.today().isoformat(), evolucao,
         json.dumps(body.get("pontos_positivos", []), ensure_ascii=False),
         json.dumps(body.get("pontos_atencao", []), ensure_ascii=False),
         body.get("objetivo_semana", ""), body.get("mensagem_familia", ""), 1 if compartilhar else 0),
    )

    paciente = query_one("SELECT * FROM pacientes WHERE id = ?", (jornada["paciente_id"],))
    log_evento(paciente["organizacao_id"], "diario_registrado", "diario_terapeutico", diario_id, paciente["id"])

    # FR-010: compartilhado automaticamente — família recebe notificação.
    if compartilhar:
        responsaveis = query(
            "SELECT usuario_id FROM responsaveis_pacientes WHERE paciente_id = ?", (paciente["id"],)
        )
        for r in responsaveis:
            criar_notificacao(
                r["usuario_id"], f"Novo registro no diário de {paciente['nome']} 📔",
                (body.get("mensagem_familia") or evolucao)[:120],
                tipo="diario", entidade="paciente", entidade_id=paciente["id"],
            )

    return jsonify({"id": diario_id}), 201


@bp.put("/<int:diario_id>")
@login_required
@papel_required("profissional", "gestor")
def editar_diario(diario_id):
    """Permite ao profissional autor corrigir o próprio registro."""
    u = g.usuario
    diario = query_one("SELECT * FROM diarios_terapeuticos WHERE id = ?", (diario_id,))
    if not diario:
        return jsonify({"erro": "Registro não encontrado."}), 404
    # Isolamento multi-tenant: resolve diario -> jornada -> paciente antes de
    # qualquer outra checagem (correção de auditoria — antes era possível a um
    # gestor de QUALQUER clínica editar o diário de outra clínica).
    jornada = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (diario["jornada_id"],))
    if not jornada or not paciente_editavel(jornada["paciente_id"]):
        return jsonify({"erro": "Sem acesso a este registro."}), 403
    if diario["profissional_id"] != u["id"] and u["papel"] != "gestor":
        return jsonify({"erro": "Somente o profissional autor pode editar este registro."}), 403

    body = request.get_json(force=True, silent=True) or {}
    execute(
        """UPDATE diarios_terapeuticos SET evolucao_clinica = ?, pontos_positivos_json = ?, pontos_atencao_json = ?,
           objetivo_semana = ?, mensagem_familia = ? WHERE id = ?""",
        (body.get("evolucao_clinica", diario["evolucao_clinica"]),
         json.dumps(body.get("pontos_positivos", json.loads(diario["pontos_positivos_json"] or "[]")), ensure_ascii=False),
         json.dumps(body.get("pontos_atencao", json.loads(diario["pontos_atencao_json"] or "[]")), ensure_ascii=False),
         body.get("objetivo_semana", diario["objetivo_semana"]),
         body.get("mensagem_familia", diario["mensagem_familia"]), diario_id),
    )
    return jsonify({"ok": True})


@bp.post("/<int:diario_id>/anexo")
@login_required
@papel_required("profissional", "gestor")
def adicionar_anexo(diario_id):
    """
    Anexo opcional (foto, áudio ou vídeo curto). Armazenado inline como base64
    — adequado para anexos pequenos de demonstração; em produção isso deveria
    ir para um object storage (S3/Cloudinary) em vez do banco relacional.
    """
    diario = query_one("SELECT * FROM diarios_terapeuticos WHERE id = ?", (diario_id,))
    if not diario:
        return jsonify({"erro": "Registro não encontrado."}), 404
    # Isolamento multi-tenant: esta rota não tinha NENHUMA checagem de acesso
    # além de "o diário existe" (correção de auditoria — qualquer profissional/
    # gestor podia anexar arquivo ao diário de qualquer paciente de qualquer clínica).
    jornada = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (diario["jornada_id"],))
    if not jornada or not paciente_editavel(jornada["paciente_id"]):
        return jsonify({"erro": "Sem acesso a este registro."}), 403

    body = request.get_json(force=True, silent=True) or {}
    tipo = body.get("tipo")
    conteudo_base64 = body.get("conteudo_base64", "")
    if tipo not in ("foto", "audio", "video"):
        return jsonify({"erro": "Tipo de anexo inválido."}), 400
    if not conteudo_base64:
        return jsonify({"erro": "Conteúdo do anexo vazio."}), 400

    # Estima o tamanho real a partir do base64 (cada 4 chars ≈ 3 bytes)
    tamanho_estimado = int(len(conteudo_base64) * 3 / 4)
    if tamanho_estimado > LIMITE_ANEXO_BYTES:
        return jsonify({"erro": f"Anexo muito grande (limite de {LIMITE_ANEXO_BYTES // (1024*1024)}MB nesta versão de demonstração)."}), 400

    anexo_id = execute(
        "INSERT INTO diario_anexos (diario_id, tipo, nome_arquivo, conteudo_base64, tamanho_bytes) VALUES (?, ?, ?, ?, ?)",
        (diario_id, tipo, body.get("nome_arquivo", ""), conteudo_base64, tamanho_estimado),
    )
    return jsonify({"id": anexo_id}), 201


@bp.get("/anexo/<int:anexo_id>")
@login_required
def obter_anexo(anexo_id):
    """Retorna o conteúdo do anexo (base64) para exibição."""
    anexo = query_one("SELECT * FROM diario_anexos WHERE id = ?", (anexo_id,))
    if not anexo:
        return jsonify({"erro": "Anexo não encontrado."}), 404
    diario = query_one("SELECT jornada_id FROM diarios_terapeuticos WHERE id = ?", (anexo["diario_id"],))
    jornada = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (diario["jornada_id"],))
    if not paciente_acessivel(jornada["paciente_id"]):
        return jsonify({"erro": "Sem acesso."}), 403
    return jsonify(anexo)
