"""
Regressão pro Domínio 3 — Biblioteca Terapêutica (biblioteca_bp.py), que até
09/09/2026 não tinha nenhum teste automatizado próprio. Cobre o isolamento
multi-tenant (Biblioteca da Clínica x Biblioteca da Plataforma), CRUD de
exercícios, e o arquivamento — em especial o achado do usuário de que
"Arquivar" escondia o exercício pra sempre, sem nenhuma tela pra revê-lo
(a listagem nunca pedia os inativos, embora o backend já suportasse
incluir_inativos=1).

A partir daqui também cobre as Pastas da Biblioteca (09/09/2026, até 2
níveis: pasta → subpasta), incluindo o isolamento multi-tenant delas e a
correção de auditoria de que categoria_id nunca era validado contra o
escopo de quem estava criando/editando o exercício.
"""
from factories import DuasClinicas, novo_exercicio, nova_categoria, novo_usuario, nova_midia

# 1x1 PNG válido (menor imagem real possível) — usado pra exercitar a
# validação de magic bytes sem depender de um arquivo de verdade no disco.
PNG_1X1_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="

from conftest import autenticado


def test_listagem_traz_biblioteca_da_clinica_mais_a_da_plataforma(client, db_ctx):
    cen = DuasClinicas()
    ex_a = novo_exercicio(cen.org_a, "Exercício da Clínica A")
    ex_b = novo_exercicio(cen.org_b, "Exercício da Clínica B")
    ex_plataforma = novo_exercicio(None, "Exercício da Plataforma")

    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/exercicios")
    assert r.status_code == 200
    ids = {e["id"] for e in r.get_json()}
    assert ex_a["id"] in ids
    assert ex_plataforma["id"] in ids
    assert ex_b["id"] not in ids  # isolamento entre clínicas


def test_admin_master_so_ve_biblioteca_da_plataforma(client, db_ctx):
    from factories import novo_usuario
    admin = novo_usuario(None, "Admin", "admin.biblioteca@plataforma.com", "admin_master")
    cen = DuasClinicas()
    ex_a = novo_exercicio(cen.org_a, "Exercício da Clínica A")
    ex_plataforma = novo_exercicio(None, "Exercício da Plataforma")

    r = autenticado(client, admin).get("/api/biblioteca/exercicios?apenas_plataforma=1")
    assert r.status_code == 200
    ids = {e["id"] for e in r.get_json()}
    assert ex_plataforma["id"] in ids
    assert ex_a["id"] not in ids


def test_gestor_cria_exercicio_na_biblioteca_da_propria_clinica(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/exercicios", json={
        "titulo": "Novo exercício", "midias": [{"conteudo_url": "https://youtube.com/watch?v=abc123"}],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    ex_id = r.get_json()["id"]

    r = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{ex_id}")
    assert r.status_code == 200
    assert r.get_json()["organizacao_id"] == cen.org_a


def test_gestor_nao_edita_exercicio_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    ex_b = novo_exercicio(cen.org_b, "Exercício da Clínica B")
    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex_b['id']}", json={"titulo": "Hackeado"})
    assert r.status_code == 403, r.get_data(as_text=True)


def test_gestor_nao_edita_biblioteca_da_plataforma(client, db_ctx):
    cen = DuasClinicas()
    ex_plataforma = novo_exercicio(None, "Exercício da Plataforma")
    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex_plataforma['id']}", json={"titulo": "Hackeado"})
    assert r.status_code == 403, r.get_data(as_text=True)


def test_listagem_esconde_arquivados_por_padrao(client, db_ctx):
    cen = DuasClinicas()
    ex = novo_exercicio(cen.org_a, "Exercício Arquivado", ativo=0)

    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/exercicios")
    ids = {e["id"] for e in r.get_json()}
    assert ex["id"] not in ids


def test_incluir_inativos_traz_ativos_e_arquivados_juntos(client, db_ctx):
    """Achado do usuário (09/09/2026): o parâmetro já existia no backend, mas
    nenhuma tela pedia — sem isso, um exercício arquivado ficava invisível
    pra sempre, mesmo sem ter sido de fato excluído."""
    cen = DuasClinicas()
    ex_ativo = novo_exercicio(cen.org_a, "Exercício Ativo")
    ex_arquivado = novo_exercicio(cen.org_a, "Exercício Arquivado", ativo=0)

    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/exercicios?incluir_inativos=1")
    assert r.status_code == 200
    por_id = {e["id"]: e for e in r.get_json()}
    assert por_id[ex_ativo["id"]]["ativo"] == 1
    assert por_id[ex_arquivado["id"]]["ativo"] == 0


def test_arquivar_e_reativar_exercicio(client, db_ctx):
    cen = DuasClinicas()
    ex = novo_exercicio(cen.org_a, "Exercício")

    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex['id']}/arquivar")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["ativo"] is False

    # Some da listagem padrão...
    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/exercicios")
    assert ex["id"] not in {e["id"] for e in r.get_json()}

    # ...mas continua acessível diretamente por ID (missões que já o usam
    # continuam funcionando, como o próprio texto de confirmação do botão diz).
    r = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{ex['id']}")
    assert r.status_code == 200

    # E dá pra reativar.
    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex['id']}/arquivar")
    assert r.status_code == 200
    assert r.get_json()["ativo"] is True
    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/exercicios")
    assert ex["id"] in {e["id"] for e in r.get_json()}


def test_gestor_nao_arquiva_exercicio_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    ex_b = novo_exercicio(cen.org_b, "Exercício da Clínica B")
    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex_b['id']}/arquivar")
    assert r.status_code == 403, r.get_data(as_text=True)


def test_duplicar_exercicio_da_plataforma_para_a_clinica(client, db_ctx):
    cen = DuasClinicas()
    ex_plataforma = novo_exercicio(None, "Exercício da Plataforma")
    nova_midia(ex_plataforma["id"], tipo="pdf", conteudo_url="https://exemplo.com/a.pdf")
    r = autenticado(client, cen.gestor_a).post(f"/api/biblioteca/exercicios/{ex_plataforma['id']}/duplicar")
    assert r.status_code == 201, r.get_data(as_text=True)
    novo_id = r.get_json()["id"]

    r = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{novo_id}")
    dados = r.get_json()
    assert dados["organizacao_id"] == cen.org_a
    assert dados["titulo"] == "Exercício da Plataforma (cópia)"


# ---------------------------------------------------------------- Pastas (categorias_exercicio)

def test_listar_categorias_traz_so_as_da_propria_clinica(client, db_ctx):
    cen = DuasClinicas()
    pasta_a = nova_categoria(cen.org_a, "Fala")
    pasta_b = nova_categoria(cen.org_b, "Coordenação")

    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/categorias")
    assert r.status_code == 200
    ids = {c["id"] for c in r.get_json()}
    assert pasta_a["id"] in ids
    assert pasta_b["id"] not in ids


def test_admin_master_lista_e_cria_pastas_na_biblioteca_da_plataforma(client, db_ctx):
    """Antes de 09/09/2026 o Admin nem tinha pastas próprias — listar_categorias
    devolvia [] pra quem não tinha organizacao_id."""
    admin = novo_usuario(None, "Admin", "admin.pastas@plataforma.com", "admin_master")
    r = autenticado(client, admin).post("/api/biblioteca/categorias", json={"nome": "Fala", "icone_emoji": "🗣️"})
    assert r.status_code == 201, r.get_data(as_text=True)

    r = autenticado(client, admin).get("/api/biblioteca/categorias")
    assert r.status_code == 200
    nomes = {c["nome"] for c in r.get_json()}
    assert "Fala" in nomes


def test_criar_subpasta_com_pasta_pai_valida(client, db_ctx):
    cen = DuasClinicas()
    pasta = nova_categoria(cen.org_a, "Fala")
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/categorias", json={
        "nome": "Articulação", "pasta_pai_id": pasta["id"],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    sub_id = r.get_json()["id"]

    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/categorias")
    subpasta = next(c for c in r.get_json() if c["id"] == sub_id)
    assert subpasta["pasta_pai_id"] == pasta["id"]


def test_nao_permite_terceiro_nivel_de_subpasta(client, db_ctx):
    """Limite de 2 níveis (pasta → subpasta): não dá pra criar uma subpasta
    dentro de outra subpasta."""
    cen = DuasClinicas()
    pasta = nova_categoria(cen.org_a, "Fala")
    sub = nova_categoria(cen.org_a, "Articulação", pasta_pai_id=pasta["id"])
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/categorias", json={
        "nome": "Sub-subpasta", "pasta_pai_id": sub["id"],
    })
    assert r.status_code == 400, r.get_data(as_text=True)


def test_nao_cria_subpasta_com_pasta_pai_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    pasta_b = nova_categoria(cen.org_b, "Coordenação")
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/categorias", json={
        "nome": "Sub", "pasta_pai_id": pasta_b["id"],
    })
    assert r.status_code == 404, r.get_data(as_text=True)


def test_editar_categoria_renomeia(client, db_ctx):
    cen = DuasClinicas()
    pasta = nova_categoria(cen.org_a, "Fala")
    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/categorias/{pasta['id']}", json={"nome": "Comunicação"})
    assert r.status_code == 200, r.get_data(as_text=True)

    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/categorias")
    pasta_atualizada = next(c for c in r.get_json() if c["id"] == pasta["id"])
    assert pasta_atualizada["nome"] == "Comunicação"


def test_gestor_nao_edita_pasta_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    pasta_b = nova_categoria(cen.org_b, "Coordenação")
    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/categorias/{pasta_b['id']}", json={"nome": "Hackeado"})
    assert r.status_code == 404, r.get_data(as_text=True)


def test_excluir_categoria_vazia(client, db_ctx):
    cen = DuasClinicas()
    pasta = nova_categoria(cen.org_a, "Fala")
    r = autenticado(client, cen.gestor_a).delete(f"/api/biblioteca/categorias/{pasta['id']}")
    assert r.status_code == 200, r.get_data(as_text=True)


def test_nao_exclui_pasta_com_subpasta(client, db_ctx):
    cen = DuasClinicas()
    pasta = nova_categoria(cen.org_a, "Fala")
    nova_categoria(cen.org_a, "Articulação", pasta_pai_id=pasta["id"])
    r = autenticado(client, cen.gestor_a).delete(f"/api/biblioteca/categorias/{pasta['id']}")
    assert r.status_code == 400, r.get_data(as_text=True)


def test_nao_exclui_pasta_com_exercicio(client, db_ctx):
    cen = DuasClinicas()
    pasta = nova_categoria(cen.org_a, "Fala")
    novo_exercicio(cen.org_a, "Exercício de Fala", categoria_id=pasta["id"])
    r = autenticado(client, cen.gestor_a).delete(f"/api/biblioteca/categorias/{pasta['id']}")
    assert r.status_code == 400, r.get_data(as_text=True)


def test_filtro_por_pasta_de_topo_traz_exercicios_das_subpastas(client, db_ctx):
    """Filtrar pela pasta de primeiro nível também traz o que está dentro das
    subpastas dela — igual navegação normal de pastas."""
    cen = DuasClinicas()
    pasta = nova_categoria(cen.org_a, "Fala")
    sub = nova_categoria(cen.org_a, "Articulação", pasta_pai_id=pasta["id"])
    ex_na_pasta = novo_exercicio(cen.org_a, "Direto na pasta", categoria_id=pasta["id"])
    ex_na_subpasta = novo_exercicio(cen.org_a, "Dentro da subpasta", categoria_id=sub["id"])
    ex_fora = novo_exercicio(cen.org_a, "Sem pasta nenhuma")

    r = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios?categoria_id={pasta['id']}")
    assert r.status_code == 200
    ids = {e["id"] for e in r.get_json()}
    assert ex_na_pasta["id"] in ids
    assert ex_na_subpasta["id"] in ids
    assert ex_fora["id"] not in ids


def test_listagem_de_exercicios_traz_nome_da_pasta_mae_da_subpasta(client, db_ctx):
    """listar_exercicios junta a pasta-mãe de uma subpasta pra o front poder
    montar o breadcrumb "Pasta / Subpasta" e agrupar a grade por pasta."""
    cen = DuasClinicas()
    pasta = nova_categoria(cen.org_a, "Fala", icone_emoji="🗣️")
    sub = nova_categoria(cen.org_a, "Articulação", pasta_pai_id=pasta["id"])
    novo_exercicio(cen.org_a, "Dentro da subpasta", categoria_id=sub["id"])

    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/exercicios")
    ex = next(e for e in r.get_json() if e["titulo"] == "Dentro da subpasta")
    assert ex["categoria_nome"] == "Articulação"
    assert ex["categoria_pasta_pai_id"] == pasta["id"]
    assert ex["pasta_pai_nome"] == "Fala"
    assert ex["pasta_pai_icone"] == "🗣️"


def test_criar_exercicio_com_categoria_de_outra_clinica_e_rejeitado(client, db_ctx):
    """Correção de auditoria (09/09/2026): categoria_id nunca era validado
    contra o escopo de quem estava criando o exercício — dava pra vincular
    um exercício a uma pasta de outra clínica só passando o id na mão."""
    cen = DuasClinicas()
    pasta_b = nova_categoria(cen.org_b, "Coordenação")
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/exercicios", json={
        "titulo": "Tentativa de vincular pasta alheia", "categoria_id": pasta_b["id"],
        "midias": [{"conteudo_url": "https://exemplo.com/x"}],
    })
    assert r.status_code == 400, r.get_data(as_text=True)


def test_editar_exercicio_com_categoria_de_outra_clinica_e_rejeitado(client, db_ctx):
    cen = DuasClinicas()
    pasta_b = nova_categoria(cen.org_b, "Coordenação")
    ex_a = novo_exercicio(cen.org_a, "Exercício da Clínica A")
    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex_a['id']}", json={
        "titulo": ex_a["titulo"], "categoria_id": pasta_b["id"],
        "midias": [{"conteudo_url": "https://exemplo.com/x"}],
    })
    assert r.status_code == 400, r.get_data(as_text=True)


def test_criar_exercicio_com_pasta_propria_funciona(client, db_ctx):
    cen = DuasClinicas()
    pasta = nova_categoria(cen.org_a, "Fala")
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/exercicios", json={
        "titulo": "Exercício de Fala", "categoria_id": pasta["id"],
        "midias": [{"conteudo_url": "https://exemplo.com/video"}],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    ex_id = r.get_json()["id"]

    r = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{ex_id}")
    assert r.get_json()["categoria_id"] == pasta["id"]


# ---------------------------------------------------------------- Fase 3 — Múltiplas mídias (09/09/2026)

def test_criar_exercicio_sem_midias_e_rejeitado(client, db_ctx):
    """"Deixar cada mídia falar por si": sem o antigo campo `tipo` genérico
    (que podia ser "atividade" sem conteúdo nenhum), todo exercício precisa
    de pelo menos uma mídia."""
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/exercicios", json={"titulo": "Sem mídia nenhuma"})
    assert r.status_code == 400, r.get_data(as_text=True)


def test_criar_exercicio_com_link_generico_deriva_tipo_link(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/exercicios", json={
        "titulo": "Com link", "midias": [{"conteudo_url": "https://exemplo.com/atividade"}],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    ex_id = r.get_json()["id"]
    dados = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{ex_id}").get_json()
    assert len(dados["midias"]) == 1
    assert dados["midias"][0]["tipo"] == "link"


def test_criar_exercicio_com_link_youtube_deriva_tipo_youtube(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/exercicios", json={
        "titulo": "Com vídeo do YouTube", "midias": [{"conteudo_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    dados = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{r.get_json()['id']}").get_json()
    assert dados["midias"][0]["tipo"] == "youtube"


def test_criar_exercicio_com_arquivo_de_conteudo_invalido_e_rejeitado(client, db_ctx):
    """Recusa mesmo que o "arquivo" venha marcado como se fosse uma imagem —
    a validação olha os magic bytes reais, não confia em rótulo nenhum."""
    cen = DuasClinicas()
    import base64
    conteudo_falso = base64.b64encode(b"isso aqui nao e nenhum formato de midia valido").decode()
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/exercicios", json={
        "titulo": "Arquivo inválido", "midias": [{"arquivo_base64": conteudo_falso, "arquivo_nome": "foto.png"}],
    })
    assert r.status_code == 400, r.get_data(as_text=True)


def test_criar_exercicio_com_arquivo_real_deriva_tipo_pela_assinatura(client, db_ctx):
    """O tipo da mídia vem do CONTEÚDO real (magic bytes), não do nome do
    arquivo nem de nada que o cliente diga — aqui manda um PNG de verdade
    com nome "documento.pdf" só pra provar que o nome não importa."""
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/exercicios", json={
        "titulo": "Foto disfarçada", "midias": [{"arquivo_base64": PNG_1X1_BASE64, "arquivo_nome": "documento.pdf"}],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    dados = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{r.get_json()['id']}").get_json()
    assert dados["midias"][0]["tipo"] == "imagem"


def test_criar_exercicio_com_multiplas_midias(client, db_ctx):
    """O ponto central da Fase 3: um exercício pode ter VÁRIAS mídias ao
    mesmo tempo (ex.: um vídeo + um PDF de apoio no mesmo exercício), coisa
    que o modelo antigo de "um exercício = um conteúdo só" não permitia."""
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/exercicios", json={
        "titulo": "Exercício completo",
        "midias": [
            {"conteudo_url": "https://youtube.com/watch?v=abc123"},
            {"arquivo_base64": PNG_1X1_BASE64, "arquivo_nome": "apoio.png"},
            {"conteudo_url": "https://exemplo.com/material-extra"},
        ],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    dados = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{r.get_json()['id']}").get_json()
    assert len(dados["midias"]) == 3
    tipos = [m["tipo"] for m in dados["midias"]]
    assert tipos == ["youtube", "imagem", "link"]  # preserva a ordem de envio


def test_editar_exercicio_substitui_todas_as_midias(client, db_ctx):
    """Estratégia de substituição total: editar manda a lista COMPLETA
    desejada, e a antiga é inteiramente descartada — não um merge."""
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/exercicios", json={
        "titulo": "Original",
        "midias": [{"conteudo_url": "https://exemplo.com/1"}, {"conteudo_url": "https://exemplo.com/2"}],
    })
    ex_id = r.get_json()["id"]

    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex_id}", json={
        "titulo": "Original", "midias": [{"conteudo_url": "https://exemplo.com/novo-unico"}],
    })
    assert r.status_code == 200, r.get_data(as_text=True)

    dados = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{ex_id}").get_json()
    assert len(dados["midias"]) == 1
    assert dados["midias"][0]["conteudo_url"] == "https://exemplo.com/novo-unico"


def test_editar_exercicio_sem_midias_e_rejeitado(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/exercicios", json={
        "titulo": "Original", "midias": [{"conteudo_url": "https://exemplo.com/1"}],
    })
    ex_id = r.get_json()["id"]
    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex_id}", json={"titulo": "Original", "midias": []})
    assert r.status_code == 400, r.get_data(as_text=True)


def test_listagem_traz_midias_count_e_midia_capa(client, db_ctx):
    cen = DuasClinicas()
    ex = novo_exercicio(cen.org_a, "Com duas mídias")
    nova_midia(ex["id"], tipo="video", conteudo_url="https://exemplo.com/v", ordem=0)
    nova_midia(ex["id"], tipo="pdf", arquivo_nome="apoio.pdf", arquivo_base64="ZmFrZQ==", ordem=1)

    r = autenticado(client, cen.gestor_a).get("/api/biblioteca/exercicios")
    item = next(e for e in r.get_json() if e["id"] == ex["id"])
    assert item["midias_count"] == 2
    assert item["midia_capa_tipo"] == "video"  # ordem=0 é a capa
    assert item["midia_capa_url"] == "https://exemplo.com/v"


def test_duplicar_exercicio_copia_todas_as_midias(client, db_ctx):
    cen = DuasClinicas()
    ex_plataforma = novo_exercicio(None, "Exercício com 3 mídias")
    nova_midia(ex_plataforma["id"], tipo="youtube", conteudo_url="https://youtube.com/watch?v=xyz", ordem=0)
    nova_midia(ex_plataforma["id"], tipo="pdf", arquivo_nome="a.pdf", arquivo_base64="ZmFrZQ==", ordem=1)
    nova_midia(ex_plataforma["id"], tipo="link", conteudo_url="https://exemplo.com/extra", ordem=2)

    r = autenticado(client, cen.gestor_a).post(f"/api/biblioteca/exercicios/{ex_plataforma['id']}/duplicar")
    assert r.status_code == 201, r.get_data(as_text=True)
    novo_id = r.get_json()["id"]

    dados = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{novo_id}").get_json()
    assert len(dados["midias"]) == 3
    assert [m["tipo"] for m in dados["midias"]] == ["youtube", "pdf", "link"]


def test_midia_nao_pode_ter_link_e_arquivo_ao_mesmo_tempo(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/biblioteca/exercicios", json={
        "titulo": "Mídia ambígua",
        "midias": [{"conteudo_url": "https://exemplo.com/x", "arquivo_base64": PNG_1X1_BASE64}],
    })
    assert r.status_code == 400, r.get_data(as_text=True)


# ---------------------------------------------------------------- Mover exercício (arrastar-e-soltar, 09/09/2026)

def test_mover_exercicio_solto_para_uma_pasta(client, db_ctx):
    """Insight do usuário (09/09/2026): arrastar um exercício sem pasta pra
    dentro de uma pasta na grade, sem precisar abrir o editor inteiro."""
    cen = DuasClinicas()
    pasta = nova_categoria(cen.org_a, "Fala")
    ex = novo_exercicio(cen.org_a, "Exercício solto")
    assert ex["categoria_id"] is None

    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex['id']}/mover", json={"categoria_id": pasta["id"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["categoria_id"] == pasta["id"]

    dados = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{ex['id']}").get_json()
    assert dados["categoria_id"] == pasta["id"]


def test_mover_exercicio_preserva_as_midias(client, db_ctx):
    """O motivo de existir uma rota própria em vez de reusar o PUT normal:
    esse PUT sempre substitui a lista de mídias inteira — mandar só
    categoria_id nele apagaria as mídias por engano. /mover não mexe em
    midias_exercicio."""
    cen = DuasClinicas()
    pasta = nova_categoria(cen.org_a, "Fala")
    ex = novo_exercicio(cen.org_a, "Exercício com mídia")
    nova_midia(ex["id"], tipo="video", conteudo_url="https://exemplo.com/v", ordem=0)
    nova_midia(ex["id"], tipo="pdf", arquivo_nome="apoio.pdf", arquivo_base64="ZmFrZQ==", ordem=1)

    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex['id']}/mover", json={"categoria_id": pasta["id"]})
    assert r.status_code == 200, r.get_data(as_text=True)

    dados = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{ex['id']}").get_json()
    assert len(dados["midias"]) == 2


def test_mover_exercicio_de_volta_para_fora_de_qualquer_pasta(client, db_ctx):
    cen = DuasClinicas()
    pasta = nova_categoria(cen.org_a, "Fala")
    ex = novo_exercicio(cen.org_a, "Exercício", categoria_id=pasta["id"])

    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex['id']}/mover", json={"categoria_id": None})
    assert r.status_code == 200, r.get_data(as_text=True)
    dados = autenticado(client, cen.gestor_a).get(f"/api/biblioteca/exercicios/{ex['id']}").get_json()
    assert dados["categoria_id"] is None


def test_mover_exercicio_para_pasta_de_outra_clinica_e_rejeitado(client, db_ctx):
    cen = DuasClinicas()
    pasta_b = nova_categoria(cen.org_b, "Coordenação")
    ex_a = novo_exercicio(cen.org_a, "Exercício da Clínica A")

    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex_a['id']}/mover", json={"categoria_id": pasta_b["id"]})
    assert r.status_code == 400, r.get_data(as_text=True)


def test_gestor_nao_move_exercicio_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    pasta_a = nova_categoria(cen.org_a, "Fala")
    ex_b = novo_exercicio(cen.org_b, "Exercício da Clínica B")

    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex_b['id']}/mover", json={"categoria_id": pasta_a["id"]})
    assert r.status_code == 403, r.get_data(as_text=True)


def test_gestor_nao_move_exercicio_da_biblioteca_da_plataforma(client, db_ctx):
    cen = DuasClinicas()
    pasta_a = nova_categoria(cen.org_a, "Fala")
    ex_plataforma = novo_exercicio(None, "Exercício da Plataforma")

    r = autenticado(client, cen.gestor_a).put(f"/api/biblioteca/exercicios/{ex_plataforma['id']}/mover", json={"categoria_id": pasta_a["id"]})
    assert r.status_code == 403, r.get_data(as_text=True)
