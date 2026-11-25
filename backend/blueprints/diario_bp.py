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
- BR-010 (revisto em 01/10/2026, pedido do usuário): qualquer profissional
  da clínica do paciente (e o gestor) pode criar registros — sem vínculo.
"""
import json
import re
import uuid
from datetime import date

from flask import Blueprint, request, jsonify, g

import armazenamento_service
from db import query, query_one, execute, log_evento, log_auditoria, criar_notificacao
from validacao_arquivo import validar_arquivo_base64, validar_bytes
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
        d["observacao"] = None  # nota da equipe no atendimento (08/10/2026)
    return d


def _pode_registrar_diario(paciente_id):
    """BR-010 (revisto em 01/10/2026): profissional ou gestor da clínica do
    paciente — o mesmo critério de `paciente_editavel`, sem vínculo."""
    return paciente_editavel(paciente_id)


def _paciente_do_diario(diario):
    """De qual paciente é o registro (spec 08/10/2026): a coluna nova; para
    registro antigo ainda sem ela, a jornada."""
    if diario.get("paciente_id"):
        return diario["paciente_id"]
    if diario.get("jornada_id"):
        j = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (diario["jornada_id"],))
        return j["paciente_id"] if j else None
    return None


# Registros do paciente: pela coluna nova ou, nos antigos sem ela, pela jornada.
WHERE_DO_PACIENTE = """(d.paciente_id = ? OR (d.paciente_id IS NULL AND d.jornada_id IN
                        (SELECT id FROM jornadas WHERE paciente_id = ?)))"""


def _listar_do_paciente(paciente_id):
    """Histórico completo, em ordem cronológica (mais recente primeiro)."""
    if not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Sem acesso a este paciente."}), 403
    u = g.usuario
    sql = f"""SELECT d.*, u.nome as profissional_nome, u.especialidade as profissional_especialidade
              FROM diarios_terapeuticos d JOIN usuarios u ON u.id = d.profissional_id
              WHERE {WHERE_DO_PACIENTE}"""
    # Responsável só vê os registros marcados como compartilhados com a família
    if u["papel"] == "responsavel":
        sql += " AND d.compartilhado_familia = 1"
    sql += " ORDER BY d.data_atendimento DESC, d.criado_em DESC"

    diarios = query(sql, (paciente_id, paciente_id))
    return jsonify([_serializar_diario(d, ocultar_evolucao_clinica=(u["papel"] == "responsavel")) for d in diarios])


def _criar_para_paciente(paciente_id, jornada_id=None):
    """Novo Diário Terapêutico — o coração do Módulo 07. Desde 08/10/2026 é do
    paciente: grava a jornada ativa junto quando houver, mas não depende dela."""
    u = g.usuario
    # BR-010 (revisto em 01/10/2026): equipe da clínica do paciente.
    if not _pode_registrar_diario(paciente_id):
        return jsonify({"erro": "Apenas a equipe da clínica deste paciente pode registrar o diário."}), 403

    body = request.get_json(force=True, silent=True) or {}
    evolucao = (body.get("evolucao_clinica") or "").strip()
    if not evolucao:
        return jsonify({"erro": "A evolução clínica é obrigatória."}), 400
    consulta_id = body.get("consulta_id")
    if consulta_id not in (None, ""):
        try:
            if isinstance(consulta_id, bool) or (isinstance(consulta_id, float) and not consulta_id.is_integer()):
                raise ValueError
            consulta_id = int(consulta_id)
        except (TypeError, ValueError):
            return jsonify({"erro": "Consulta inválida para este paciente."}), 400
        if not query_one("SELECT 1 FROM consultas WHERE id = ? AND paciente_id = ?", (consulta_id, paciente_id)):
            return jsonify({"erro": "Consulta inválida para este paciente."}), 400
        # Um registro por consulta (índice único): o existente se edita pelo Atender.
        if query_one("SELECT 1 FROM diarios_terapeuticos WHERE consulta_id = ?", (consulta_id,)):
            return jsonify({"erro": "Esta consulta já tem registro no Diário: edite pelo Atender."}), 409
    else:
        consulta_id = None

    # A rota antiga (por jornada) grava a jornada do endereço; a nova, a ativa.
    jornada = {"id": jornada_id} if jornada_id else query_one(
        "SELECT id FROM jornadas WHERE paciente_id = ? AND status = 'ativa' ORDER BY id DESC LIMIT 1", (paciente_id,))
    compartilhar = body.get("compartilhado_familia", True)

    diario_id = execute(
        """INSERT INTO diarios_terapeuticos
           (jornada_id, paciente_id, profissional_id, consulta_id, data_atendimento, evolucao_clinica,
            pontos_positivos_json, pontos_atencao_json, objetivo_semana, mensagem_familia, compartilhado_familia)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (jornada["id"] if jornada else None, paciente_id, u["id"], consulta_id,
         body.get("data_atendimento") or date.today().isoformat(), evolucao,
         json.dumps(body.get("pontos_positivos", []), ensure_ascii=False),
         json.dumps(body.get("pontos_atencao", []), ensure_ascii=False),
         body.get("objetivo_semana", ""), body.get("mensagem_familia", ""), 1 if compartilhar else 0),
    )

    paciente = query_one("SELECT * FROM pacientes WHERE id = ?", (paciente_id,))
    log_evento(paciente["organizacao_id"], "diario_registrado", "diario_terapeutico", diario_id, paciente["id"])

    # FR-010: compartilhado automaticamente — família recebe notificação.
    if compartilhar:
        responsaveis = query(
            "SELECT usuario_id FROM responsaveis_pacientes WHERE paciente_id = ?", (paciente["id"],)
        )
        for r in responsaveis:
            criar_notificacao(
                r["usuario_id"], f"Novo registro no diário de {paciente['nome']} 📔",
                # Nunca o texto clínico: sem mensagem, um aviso genérico (09/10/2026).
                (body.get("mensagem_familia") or "A equipe registrou um novo atendimento.")[:120],
                tipo="diario", entidade="paciente", entidade_id=paciente["id"],
            )

    return jsonify({"id": diario_id}), 201


@bp.get("/paciente/<int:paciente_id>")
@login_required
def listar_diarios_paciente(paciente_id):
    if not query_one("SELECT 1 FROM pacientes WHERE id = ?", (paciente_id,)):
        return jsonify({"erro": "Paciente não encontrado."}), 404
    return _listar_do_paciente(paciente_id)


@bp.post("/paciente/<int:paciente_id>")
@login_required
@papel_required("profissional", "gestor")
def criar_diario_paciente(paciente_id):
    if not query_one("SELECT 1 FROM pacientes WHERE id = ?", (paciente_id,)):
        return jsonify({"erro": "Paciente não encontrado."}), 404
    return _criar_para_paciente(paciente_id)


# Rotas antigas, por jornada: atalhos para as do paciente (telas abertas
# durante o deploy de 08/10/2026 continuam funcionando).
@bp.get("/jornada/<int:jornada_id>")
@login_required
def listar_diarios(jornada_id):
    jornada = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (jornada_id,))
    if not jornada:
        return jsonify({"erro": "Jornada não encontrada."}), 404
    return _listar_do_paciente(jornada["paciente_id"])


@bp.post("/jornada/<int:jornada_id>")
@login_required
@papel_required("profissional", "gestor")
def criar_diario(jornada_id):
    jornada = query_one("SELECT paciente_id FROM jornadas WHERE id = ?", (jornada_id,))
    if not jornada:
        return jsonify({"erro": "Jornada não encontrada."}), 404
    return _criar_para_paciente(jornada["paciente_id"], jornada_id)


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
    paciente_id = _paciente_do_diario(d)
    if not paciente_id or not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Sem acesso."}), 403
    # Correção de auditoria (rodada de testes de IDOR, 25/08/2026): esta rota
    # busca por id direto e não tinha a mesma checagem de listar_diarios()
    # (que só devolve registros com compartilhado_familia = 1 pro responsável)
    # — um responsável que soubesse/adivinhasse o id de um registro NÃO
    # compartilhado (ex: algo que o profissional ainda não considerou pronto
    # para comunicar à família) conseguia lê-lo mesmo assim.
    if g.usuario["papel"] == "responsavel" and not d["compartilhado_familia"]:
        return jsonify({"erro": "Este registro não foi compartilhado com a família."}), 403
    return jsonify(_serializar_diario(d, ocultar_evolucao_clinica=(g.usuario["papel"] == "responsavel")))


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
    paciente_id = _paciente_do_diario(diario)
    if not paciente_id or not paciente_editavel(paciente_id):
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
    paciente_id = _paciente_do_diario(diario)
    if not paciente_id or not paciente_editavel(paciente_id):
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

    # Correção de auditoria (recomendação 1, 25/08/2026): antes só o tamanho
    # era checado — o conteúdo podia ser qualquer coisa disfarçada de "foto".
    ok, erro_assinatura = validar_arquivo_base64(conteudo_base64, tipo)
    if not ok:
        return jsonify({"erro": erro_assinatura}), 400

    anexo_id = execute(
        "INSERT INTO diario_anexos (diario_id, tipo, nome_arquivo, conteudo_base64, tamanho_bytes) VALUES (?, ?, ?, ?, ?)",
        (diario_id, tipo, body.get("nome_arquivo", ""), conteudo_base64, tamanho_estimado),
    )
    return jsonify({"id": anexo_id}), 201


# ---------------------------------------------------------------- Anexos no Supabase Storage (25/11/2026)
# Spec docs/superpowers/specs/2026-11-25-anexos-diario-storage-design.md. O
# navegador envia direto para o Storage (link de uso único); o servidor confere
# o começo do arquivo antes de gravar a linha. Sem Storage configurado, a tela
# usa a rota base64 acima (até 4 MB).

_EXTENSOES_MIME = {
    "video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov", "video/x-m4v": "m4v",
    "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/aac": "aac",
    "audio/ogg": "ogg", "audio/wav": "wav", "audio/x-wav": "wav", "audio/webm": "webm",
    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif",
}
_RE_MIME = re.compile(r"^(image|video|audio)/[a-z0-9.+\-]{1,60}$")


def _mime_limpo(valor):
    valor = str(valor or "").strip().lower()
    return valor if _RE_MIME.match(valor) else None


def _extensao(mime, nome):
    if mime in _EXTENSOES_MIME:
        return _EXTENSOES_MIME[mime]
    ext = str(nome or "").rsplit(".", 1)[-1].lower() if "." in str(nome or "") else ""
    return ext if re.fullmatch(r"[a-z0-9]{1,5}", ext) else "bin"


def _diario_para_anexar(diario_id):
    """(diario, org_id, None) ou (None, None, resposta) — mesma regra de adicionar_anexo."""
    diario = query_one("SELECT * FROM diarios_terapeuticos WHERE id = ?", (diario_id,))
    if not diario:
        return None, None, (jsonify({"erro": "Registro não encontrado."}), 404)
    paciente_id = _paciente_do_diario(diario)
    if not paciente_id or not paciente_editavel(paciente_id):
        return None, None, (jsonify({"erro": "Sem acesso a este registro."}), 403)
    org = query_one("SELECT organizacao_id FROM pacientes WHERE id = ?", (paciente_id,))
    return diario, org["organizacao_id"], None


def _prefixo_storage(org_id, diario_id):
    return f"clinica-{org_id}/diario-{diario_id}/"


def _msg_limite():
    return f"O arquivo passa de {armazenamento_service.limite_anexo_mb()} MB, o limite por anexo."


@bp.get("/anexos/config")
@login_required
def config_anexos():
    """A tela decide por aqui se envia para o Storage e qual limite mostra."""
    if armazenamento_service.configurado():
        return jsonify({"storage": True, "limite_mb": armazenamento_service.limite_anexo_mb()})
    return jsonify({"storage": False, "limite_mb": LIMITE_ANEXO_BYTES // (1024 * 1024)})


@bp.post("/<int:diario_id>/anexo/envio")
@login_required
@papel_required("profissional", "gestor")
def pedir_envio_anexo(diario_id):
    if not armazenamento_service.configurado():
        return jsonify({"erro": "O envio de arquivos grandes não está ativo neste servidor."}), 503
    diario, org_id, erro = _diario_para_anexar(diario_id)
    if erro:
        return erro
    body = request.get_json(force=True, silent=True) or {}
    if body.get("tipo") not in ("foto", "audio", "video"):
        return jsonify({"erro": "Tipo de anexo inválido."}), 400
    try:
        tamanho = int(body.get("tamanho_bytes") or 0)
    except (TypeError, ValueError):
        tamanho = 0
    if tamanho <= 0:
        return jsonify({"erro": "Tamanho do arquivo inválido."}), 400
    if tamanho > armazenamento_service.limite_anexo_bytes():
        return jsonify({"erro": _msg_limite()}), 400
    caminho = f"{_prefixo_storage(org_id, diario_id)}{uuid.uuid4().hex}.{_extensao(_mime_limpo(body.get('mime')), body.get('nome_arquivo'))}"
    try:
        url = armazenamento_service.criar_link_envio(caminho)
    except armazenamento_service.ErroArmazenamento as e:
        return jsonify({"erro": str(e)}), 502
    return jsonify({"caminho": caminho, "url_envio": url})


@bp.post("/<int:diario_id>/anexo/confirmar")
@login_required
@papel_required("profissional", "gestor")
def confirmar_anexo(diario_id):
    if not armazenamento_service.configurado():
        return jsonify({"erro": "O envio de arquivos grandes não está ativo neste servidor."}), 503
    diario, org_id, erro = _diario_para_anexar(diario_id)
    if erro:
        return erro
    body = request.get_json(force=True, silent=True) or {}
    tipo = body.get("tipo")
    if tipo not in ("foto", "audio", "video"):
        return jsonify({"erro": "Tipo de anexo inválido."}), 400
    caminho = str(body.get("caminho") or "")
    prefixo = _prefixo_storage(org_id, diario_id)
    if not (caminho.startswith(prefixo) and re.fullmatch(r"[0-9a-f]{32}\.[a-z0-9]{1,5}", caminho[len(prefixo):])):
        return jsonify({"erro": "Arquivo inválido para este registro."}), 400
    if query_one("SELECT 1 FROM diario_anexos WHERE storage_path = ?", (caminho,)):
        return jsonify({"erro": "Este arquivo já foi anexado."}), 409
    try:
        lido = armazenamento_service.ler_inicio(caminho)
    except armazenamento_service.ErroArmazenamento as e:
        return jsonify({"erro": str(e)}), 502
    if not lido:
        return jsonify({"erro": "O arquivo não chegou ao armazenamento. Tente enviar de novo."}), 400
    inicio, tamanho = lido
    if tamanho > armazenamento_service.limite_anexo_bytes():
        armazenamento_service.apagar(caminho)
        return jsonify({"erro": _msg_limite()}), 400
    ok, erro_assinatura = validar_bytes(inicio, tipo)
    if not ok:
        armazenamento_service.apagar(caminho)
        return jsonify({"erro": erro_assinatura}), 400
    anexo_id = execute(
        """INSERT INTO diario_anexos (diario_id, tipo, nome_arquivo, conteudo_base64, tamanho_bytes, storage_path, mime)
           VALUES (?, ?, ?, NULL, ?, ?, ?)""",
        (diario_id, tipo, str(body.get("nome_arquivo") or "")[:200], tamanho, caminho, _mime_limpo(body.get("mime"))),
    )
    return jsonify({"id": anexo_id}), 201


@bp.get("/anexo/<int:anexo_id>")
@login_required
def obter_anexo(anexo_id):
    """Retorna o anexo para exibição: link temporário (Storage) ou base64 (antigos)."""
    anexo = query_one("SELECT * FROM diario_anexos WHERE id = ?", (anexo_id,))
    if not anexo:
        return jsonify({"erro": "Anexo não encontrado."}), 404
    diario = query_one("SELECT jornada_id, paciente_id, compartilhado_familia FROM diarios_terapeuticos WHERE id = ?", (anexo["diario_id"],))
    paciente_id = _paciente_do_diario(diario) if diario else None
    if not paciente_id or not paciente_acessivel(paciente_id):
        return jsonify({"erro": "Sem acesso."}), 403
    # Mesma correção de obter_diario() acima — o anexo pertence a um registro
    # que pode não ter sido compartilhado com a família.
    if g.usuario["papel"] == "responsavel" and not diario["compartilhado_familia"]:
        return jsonify({"erro": "Este registro não foi compartilhado com a família."}), 403
    if anexo.get("storage_path"):
        try:
            url = armazenamento_service.criar_link_leitura(anexo["storage_path"])
        except armazenamento_service.ErroArmazenamento as e:
            return jsonify({"erro": str(e)}), 502
        campos = ("id", "diario_id", "tipo", "nome_arquivo", "tamanho_bytes", "mime", "criado_em")
        return jsonify({**{c: anexo.get(c) for c in campos}, "url": url})
    anexo.pop("storage_path", None)
    return jsonify(anexo)


@bp.delete("/anexo/<int:anexo_id>")
@login_required
@papel_required("profissional", "gestor")
def excluir_anexo(anexo_id):
    """Remover um anexo (25/11/2026): mesma regra de editar o registro — o
    autor ou o gestor, da clínica do paciente."""
    u = g.usuario
    anexo = query_one("SELECT * FROM diario_anexos WHERE id = ?", (anexo_id,))
    if not anexo:
        return jsonify({"erro": "Anexo não encontrado."}), 404
    diario = query_one("SELECT * FROM diarios_terapeuticos WHERE id = ?", (anexo["diario_id"],))
    paciente_id = _paciente_do_diario(diario) if diario else None
    if not paciente_id or not paciente_editavel(paciente_id):
        return jsonify({"erro": "Sem acesso a este registro."}), 403
    if diario["profissional_id"] != u["id"] and u["papel"] != "gestor":
        return jsonify({"erro": "Somente quem escreveu o registro ou o gestor podem remover anexos."}), 403
    execute("DELETE FROM diario_anexos WHERE id = ?", (anexo_id,))
    if anexo.get("storage_path"):
        armazenamento_service.apagar(anexo["storage_path"])  # melhor esforço: a linha já saiu
    log_auditoria(u["organizacao_id"], u["id"], "excluir", "diario_anexo", anexo_id,
                  "diário %s · %s" % (diario["id"], anexo.get("nome_arquivo") or ""))
    return jsonify({"ok": True})
