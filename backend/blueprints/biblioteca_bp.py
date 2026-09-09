"""
Domínio 3 — Biblioteca Terapêutica (Documento 09 / Módulo 03)

UX Pattern 04 — Biblioteca: Filtros → Categorias → Cards → Detalhes → Relacionar à jornada

Suporta upload real de arquivo (foto/PDF/vídeo/áudio pequenos, armazenados
inline como base64 — mesmo padrão usado no Diário Terapêutico) OU um link
externo (conteudo_url), à escolha de quem cadastra o exercício.

Biblioteca em 2 camadas (Doc 31A/32): um exercício com organizacao_id NULO é
"Biblioteca da Plataforma" — conteúdo do SaaS, mantido pelo Admin, visível
para TODAS as clínicas. Um exercício com organizacao_id preenchido é
"Biblioteca da Clínica" — conteúdo próprio, só visível e editável por ela.
Cada clínica sempre enxerga as duas camadas somadas; só o Admin edita a
camada da Plataforma.
"""
from flask import Blueprint, request, jsonify, g

from db import query, query_one, execute, log_evento, log_auditoria
from auth import login_required, papel_required
from validacao_arquivo import validar_arquivo_base64

bp = Blueprint("biblioteca", __name__, url_prefix="/api/biblioteca")

LIMITE_ARQUIVO_BYTES = 4 * 1024 * 1024  # 4 MB — mesma política do Diário Terapêutico

CAMPOS_LISTAGEM = """e.id, e.organizacao_id, e.categoria_id, e.titulo, e.descricao, e.tipo, e.conteudo_url,
                      e.arquivo_nome, e.arquivo_tamanho_bytes, e.faixa_etaria_min, e.faixa_etaria_max,
                      e.dificuldade, e.especialidade, e.tags, e.favoritos_count, e.ativo, e.criado_em,
                      (e.arquivo_base64 IS NOT NULL AND e.arquivo_base64 != '') as tem_arquivo"""


def _pode_editar(exercicio, usuario):
    """Só o Admin do SaaS edita a Biblioteca da Plataforma; a Biblioteca da
    Clínica só é editável por quem é da própria clínica."""
    if exercicio["organizacao_id"] is None:
        return usuario["papel"] == "admin_master"
    return exercicio["organizacao_id"] == usuario["organizacao_id"]


def _categoria_do_mesmo_escopo(categoria, organizacao_id):
    """organizacao_id aqui é o escopo de QUEM está perguntando (None = Admin
    da Plataforma) — usado tanto pra saber se dá pra editar/excluir uma
    pasta quanto pra impedir que um exercício seja vinculado a uma pasta de
    outra clínica (ou de outro escopo)."""
    return categoria is not None and categoria["organizacao_id"] == organizacao_id


def _resolver_categoria_id(categoria_id, organizacao_id_exercicio):
    """Valida que a pasta informada existe e é do MESMO escopo do exercício
    que está sendo criado/editado — sem isso, dava pra vincular um exercício
    a uma pasta de outra clínica só passando o id na mão (nunca era
    checado). Devolve o categoria_id (ou None) já validado, ou levanta
    ValueError com uma mensagem pronta pra resposta 400."""
    if not categoria_id:
        return None
    categoria = query_one("SELECT * FROM categorias_exercicio WHERE id = ?", (categoria_id,))
    if not _categoria_do_mesmo_escopo(categoria, organizacao_id_exercicio):
        raise ValueError("Pasta inválida.")
    return categoria_id


@bp.get("/categorias")
@login_required
def listar_categorias():
    """Pastas da Biblioteca (insight do usuário, 09/09/2026) — até 2 níveis
    (pasta_pai_id nulo = pasta de primeiro nível; preenchido = subpasta).
    O Admin do SaaS também organiza a Biblioteca da Plataforma em pastas,
    numa árvore própria e separada da de cada clínica (organizacao_id NULL,
    mesmo padrão de exercicios.organizacao_id)."""
    org_id = g.usuario["organizacao_id"]
    if org_id:
        rows = query("SELECT * FROM categorias_exercicio WHERE organizacao_id = ? ORDER BY nome", (org_id,))
    else:
        rows = query("SELECT * FROM categorias_exercicio WHERE organizacao_id IS NULL ORDER BY nome")
    return jsonify(rows)


@bp.post("/categorias")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def criar_categoria():
    """Cria uma pasta (pasta_pai_id ausente/nulo) ou uma subpasta
    (pasta_pai_id apontando pra uma pasta já existente do mesmo escopo).
    Limite de 2 níveis: não dá pra criar uma subpasta dentro de outra
    subpasta — só o backend garante isso, não existe CHECK de profundidade
    no banco."""
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    nome = (body.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "Nome da pasta é obrigatório."}), 400

    pasta_pai_id = body.get("pasta_pai_id")
    if pasta_pai_id:
        pasta_pai = query_one("SELECT * FROM categorias_exercicio WHERE id = ?", (pasta_pai_id,))
        if not _categoria_do_mesmo_escopo(pasta_pai, u["organizacao_id"]):
            return jsonify({"erro": "Pasta não encontrada."}), 404
        if pasta_pai["pasta_pai_id"]:
            return jsonify({"erro": "Só é permitido um nível de subpasta (pasta → subpasta)."}), 400

    cid = execute(
        "INSERT INTO categorias_exercicio (organizacao_id, pasta_pai_id, nome, icone_emoji) VALUES (?, ?, ?, ?)",
        (u["organizacao_id"], pasta_pai_id, nome, body.get("icone_emoji", "📘")),
    )
    return jsonify({"id": cid}), 201


@bp.put("/categorias/<int:categoria_id>")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def editar_categoria(categoria_id):
    u = g.usuario
    categoria = query_one("SELECT * FROM categorias_exercicio WHERE id = ?", (categoria_id,))
    if not _categoria_do_mesmo_escopo(categoria, u["organizacao_id"]):
        return jsonify({"erro": "Pasta não encontrada."}), 404

    body = request.get_json(force=True, silent=True) or {}
    nome = (body.get("nome") or categoria["nome"]).strip()
    if not nome:
        return jsonify({"erro": "Nome da pasta é obrigatório."}), 400
    execute(
        "UPDATE categorias_exercicio SET nome = ?, icone_emoji = ? WHERE id = ?",
        (nome, body.get("icone_emoji", categoria["icone_emoji"]), categoria_id),
    )
    return jsonify({"ok": True})


@bp.delete("/categorias/<int:categoria_id>")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def excluir_categoria(categoria_id):
    """Só exclui uma pasta vazia — sem subpastas e sem exercício algum
    vinculado — pra nunca deixar um exercício ou uma subpasta "órfã" sem
    dar chance de decidir pra onde eles vão antes."""
    u = g.usuario
    categoria = query_one("SELECT * FROM categorias_exercicio WHERE id = ?", (categoria_id,))
    if not _categoria_do_mesmo_escopo(categoria, u["organizacao_id"]):
        return jsonify({"erro": "Pasta não encontrada."}), 404

    tem_subpasta = query_one("SELECT 1 FROM categorias_exercicio WHERE pasta_pai_id = ?", (categoria_id,))
    if tem_subpasta:
        return jsonify({"erro": "Esta pasta tem subpastas dentro dela — mova ou exclua as subpastas primeiro."}), 400
    tem_exercicio = query_one("SELECT 1 FROM exercicios WHERE categoria_id = ?", (categoria_id,))
    if tem_exercicio:
        return jsonify({"erro": "Esta pasta tem exercícios dentro dela — mova-os pra outra pasta antes de excluir."}), 400

    execute("DELETE FROM categorias_exercicio WHERE id = ?", (categoria_id,))
    return jsonify({"ok": True})


@bp.get("/exercicios")
@login_required
def listar_exercicios():
    """
    Busca inteligente com filtros — UX Pattern 04 (Documento 13). Não traz o
    base64 do arquivo (pesado). Sempre traz Biblioteca da Clínica + Biblioteca
    da Plataforma somadas (exceto para o Admin, que só vê/gerencia a da
    Plataforma — ele não pertence a nenhuma clínica).
    """
    u = g.usuario
    termo = request.args.get("q", "").strip()
    categoria_id = request.args.get("categoria_id")
    dificuldade = request.args.get("dificuldade")
    especialidade = request.args.get("especialidade")
    apenas_plataforma = request.args.get("apenas_plataforma") == "1"
    incluir_inativos = request.args.get("incluir_inativos") == "1"

    # Duplo LEFT JOIN pra saber tanto a pasta direta do exercício quanto,
    # quando essa pasta é uma subpasta, a pasta-mãe dela (pf) — o front usa
    # isso pra mostrar "Pasta / Subpasta" e pra agrupar a grade por pasta.
    sql = f"""SELECT {CAMPOS_LISTAGEM}, c.nome as categoria_nome, c.icone_emoji as categoria_icone,
                     c.pasta_pai_id as categoria_pasta_pai_id, pf.nome as pasta_pai_nome, pf.icone_emoji as pasta_pai_icone
              FROM exercicios e
              LEFT JOIN categorias_exercicio c ON c.id = e.categoria_id
              LEFT JOIN categorias_exercicio pf ON pf.id = c.pasta_pai_id
              WHERE """
    params = []
    if apenas_plataforma or not u["organizacao_id"]:
        sql += "e.organizacao_id IS NULL"
    else:
        sql += "(e.organizacao_id = ? OR e.organizacao_id IS NULL)"
        params.append(u["organizacao_id"])

    if not incluir_inativos:
        sql += " AND e.ativo = 1"

    if termo:
        sql += " AND (e.titulo LIKE ? OR e.tags LIKE ? OR e.descricao LIKE ?)"
        like = f"%{termo}%"
        params += [like, like, like]
    if categoria_id:
        # Filtrar por uma pasta de primeiro nível também traz o que está
        # dentro das subpastas dela — igual navegação normal de pastas.
        sql += " AND (e.categoria_id = ? OR e.categoria_id IN (SELECT id FROM categorias_exercicio WHERE pasta_pai_id = ?))"
        params += [categoria_id, categoria_id]
    if dificuldade:
        sql += " AND e.dificuldade = ?"
        params.append(dificuldade)
    if especialidade:
        sql += " AND e.especialidade = ?"
        params.append(especialidade)

    sql += " ORDER BY e.favoritos_count DESC, e.titulo"
    resultado = query(sql, params)
    for ex in resultado:
        ex["escopo"] = "plataforma" if ex["organizacao_id"] is None else "clinica"
    return jsonify(resultado)


@bp.get("/exercicios/<int:exercicio_id>")
@login_required
def obter_exercicio(exercicio_id):
    """Detalhe completo, incluindo o arquivo (se houver) — usado na tela de detalhe/edição."""
    ex = query_one("SELECT * FROM exercicios WHERE id = ?", (exercicio_id,))
    if not ex:
        return jsonify({"erro": "Exercício não encontrado."}), 404
    u = g.usuario
    # Conteúdo da Plataforma (organizacao_id nulo) é sempre acessível; conteúdo
    # de uma clínica só é visível para quem é dessa mesma clínica (ou o Admin).
    if ex["organizacao_id"] is not None and u["papel"] != "admin_master" and ex["organizacao_id"] != u["organizacao_id"]:
        return jsonify({"erro": "Sem acesso a este exercício."}), 403
    ex["escopo"] = "plataforma" if ex["organizacao_id"] is None else "clinica"
    ex["pode_editar"] = _pode_editar(ex, u)
    return jsonify(ex)


def _validar_e_extrair_arquivo(body):
    """Valida tamanho do upload (se houver) e retorna (nome, base64, tamanho) ou (None, None, None)."""
    base64_conteudo = body.get("arquivo_base64")
    if not base64_conteudo:
        return None, None, None
    tamanho_estimado = int(len(base64_conteudo) * 3 / 4)
    if tamanho_estimado > LIMITE_ARQUIVO_BYTES:
        raise ValueError(f"Arquivo muito grande (limite de {LIMITE_ARQUIVO_BYTES // (1024*1024)}MB nesta versão de demonstração).")
    # Correção de auditoria (recomendação 1, 25/08/2026): o "tipo" aqui é uma
    # categoria pedagógica (não indica o formato do arquivo), então aceita
    # qualquer um dos formatos de mídia realmente suportados (foto/áudio/vídeo/PDF).
    ok, erro_assinatura = validar_arquivo_base64(base64_conteudo, "qualquer_midia")
    if not ok:
        raise ValueError(erro_assinatura)
    return body.get("arquivo_nome", ""), base64_conteudo, tamanho_estimado


@bp.post("/exercicios")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def criar_exercicio():
    """
    Gestor/Profissional criam na Biblioteca da Clínica (organizacao_id
    preenchido automaticamente). Admin do SaaS cria na Biblioteca da
    Plataforma (organizacao_id nulo, já que o Admin não pertence a
    nenhuma clínica) — vira visível para todas de uma vez.
    """
    u = g.usuario
    body = request.get_json(force=True, silent=True) or {}
    titulo = (body.get("titulo") or "").strip()
    if not titulo:
        return jsonify({"erro": "Título é obrigatório."}), 400
    try:
        arquivo_nome, arquivo_base64, arquivo_tamanho = _validar_e_extrair_arquivo(body)
        categoria_id = _resolver_categoria_id(body.get("categoria_id"), u["organizacao_id"])
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    ex_id = execute(
        """INSERT INTO exercicios (organizacao_id, categoria_id, titulo, descricao, tipo, conteudo_url,
                                    arquivo_nome, arquivo_base64, arquivo_tamanho_bytes,
                                    faixa_etaria_min, faixa_etaria_max, dificuldade, especialidade, tags)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (u["organizacao_id"], categoria_id, titulo, body.get("descricao", ""),
         body.get("tipo", "atividade"), body.get("conteudo_url", ""),
         arquivo_nome, arquivo_base64, arquivo_tamanho,
         body.get("faixa_etaria_min", 2), body.get("faixa_etaria_max", 12),
         body.get("dificuldade", "facil"), body.get("especialidade", ""), body.get("tags", "")),
    )
    if u["organizacao_id"]:
        log_evento(u["organizacao_id"], "exercicio_criado", "exercicio", ex_id)
    return jsonify({"id": ex_id}), 201


@bp.put("/exercicios/<int:exercicio_id>")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def editar_exercicio(exercicio_id):
    u = g.usuario
    ex = query_one("SELECT * FROM exercicios WHERE id = ?", (exercicio_id,))
    if not ex:
        return jsonify({"erro": "Exercício não encontrado."}), 404
    if not _pode_editar(ex, u):
        motivo = "Este exercício é da Biblioteca da Plataforma — só o Admin pode editá-lo." if ex["organizacao_id"] is None \
            else "Este exercício pertence a outra clínica."
        return jsonify({"erro": motivo}), 403

    body = request.get_json(force=True, silent=True) or {}
    titulo = (body.get("titulo") or "").strip()
    if not titulo:
        return jsonify({"erro": "Título é obrigatório."}), 400
    try:
        arquivo_nome, arquivo_base64, arquivo_tamanho = _validar_e_extrair_arquivo(body)
        categoria_id = _resolver_categoria_id(body.get("categoria_id"), ex["organizacao_id"])
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    # Se um novo arquivo não foi enviado nesta edição, preserva o que já existia
    # (a menos que o usuário peça explicitamente para remover, via remover_arquivo=true).
    if arquivo_base64 is None and not body.get("remover_arquivo"):
        arquivo_nome, arquivo_base64, arquivo_tamanho = ex["arquivo_nome"], ex["arquivo_base64"], ex["arquivo_tamanho_bytes"]

    execute(
        """UPDATE exercicios SET categoria_id = ?, titulo = ?, descricao = ?, tipo = ?, conteudo_url = ?,
           arquivo_nome = ?, arquivo_base64 = ?, arquivo_tamanho_bytes = ?,
           faixa_etaria_min = ?, faixa_etaria_max = ?, dificuldade = ?, especialidade = ?, tags = ?
           WHERE id = ?""",
        (categoria_id, titulo, body.get("descricao", ""), body.get("tipo", "atividade"),
         body.get("conteudo_url", ""), arquivo_nome, arquivo_base64, arquivo_tamanho,
         body.get("faixa_etaria_min", 2), body.get("faixa_etaria_max", 12),
         body.get("dificuldade", "facil"), body.get("especialidade", ""), body.get("tags", ""), exercicio_id),
    )
    if ex["organizacao_id"]:
        log_auditoria(u["organizacao_id"], u["id"], "editar", "exercicio", exercicio_id, titulo)
        log_evento(u["organizacao_id"], "exercicio_atualizado", "exercicio", exercicio_id)
    else:
        log_auditoria(None, u["id"], "editar_biblioteca_plataforma", "exercicio", exercicio_id, titulo)
    return jsonify({"ok": True})


@bp.put("/exercicios/<int:exercicio_id>/arquivar")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def arquivar_exercicio(exercicio_id):
    """Arquivamento (soft delete) — o exercício some da Biblioteca mas não é apagado
    (missões que já o usam continuam funcionando normalmente)."""
    u = g.usuario
    ex = query_one("SELECT * FROM exercicios WHERE id = ?", (exercicio_id,))
    if not ex:
        return jsonify({"erro": "Exercício não encontrado."}), 404
    if not _pode_editar(ex, u):
        motivo = "Este exercício é da Biblioteca da Plataforma — só o Admin pode arquivá-lo." if ex["organizacao_id"] is None \
            else "Este exercício pertence a outra clínica."
        return jsonify({"erro": motivo}), 403

    novo_estado = 0 if ex["ativo"] else 1
    execute("UPDATE exercicios SET ativo = ? WHERE id = ?", (novo_estado, exercicio_id))
    if ex["organizacao_id"]:
        log_auditoria(u["organizacao_id"], u["id"], "arquivar" if not novo_estado else "reativar", "exercicio", exercicio_id, ex["titulo"])
    else:
        log_auditoria(None, u["id"], "arquivar_biblioteca_plataforma" if not novo_estado else "reativar_biblioteca_plataforma", "exercicio", exercicio_id, ex["titulo"])
    return jsonify({"ativo": bool(novo_estado)})


@bp.post("/exercicios/<int:exercicio_id>/duplicar")
@login_required
@papel_required("gestor", "profissional", "admin_master")
def duplicar_exercicio(exercicio_id):
    """
    Duplicar um item da Biblioteca da Plataforma cria uma cópia NA Biblioteca
    da Clínica de quem duplicou — é assim que uma clínica "adota e customiza"
    um conteúdo pronto do catálogo do SaaS.
    """
    u = g.usuario
    ex = query_one("SELECT * FROM exercicios WHERE id = ?", (exercicio_id,))
    if not ex:
        return jsonify({"erro": "Exercício não encontrado."}), 404
    # Isolamento multi-tenant: só pode duplicar um exercício-fonte que consegue
    # VER (Plataforma, o da própria clínica, ou o Admin) — correção de auditoria
    # (antes qualquer clínica podia copiar conteúdo privado de outra clínica).
    if ex["organizacao_id"] is not None and u["papel"] != "admin_master" and ex["organizacao_id"] != u["organizacao_id"]:
        return jsonify({"erro": "Sem acesso a este exercício."}), 403
    destino_organizacao_id = u["organizacao_id"] if u["organizacao_id"] else ex["organizacao_id"]
    novo_id = execute(
        """INSERT INTO exercicios (organizacao_id, categoria_id, titulo, descricao, tipo, conteudo_url,
                                    arquivo_nome, arquivo_base64, arquivo_tamanho_bytes,
                                    faixa_etaria_min, faixa_etaria_max, dificuldade, especialidade, tags)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (destino_organizacao_id, ex["categoria_id"] if destino_organizacao_id == ex["organizacao_id"] else None,
         ex["titulo"] + " (cópia)", ex["descricao"], ex["tipo"],
         ex["conteudo_url"], ex["arquivo_nome"], ex["arquivo_base64"], ex["arquivo_tamanho_bytes"],
         ex["faixa_etaria_min"], ex["faixa_etaria_max"], ex["dificuldade"],
         ex["especialidade"], ex["tags"]),
    )
    return jsonify({"id": novo_id}), 201
