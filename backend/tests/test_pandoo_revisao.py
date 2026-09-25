"""Pandoo (25/09/2026) — achados da revisão final do PR A."""
import base64

import db
import pandoo_service as ps
from factories import DuasClinicas, novo_exercicio, novo_usuario, vincular_responsavel
from conftest import autenticado
from modulos_service import definir_liberacao_admin

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def _missao_com(client, cen, exercicios):
    jornada = db.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)", (cen.paciente_a1, "Obj"))
    plano = db.execute("INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
                       (jornada, cen.prof_a1["id"], "Plano"))
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano}/criar-missao",
                                              json={"titulo": "M", "tipo": "diaria", "exercicios_ids": exercicios})
    return r.get_json()["id"]


def _jogo(client, cen):
    definir_liberacao_admin(cen.org_a, "pandoo", True)
    corpo = {"titulo": "Roleta", "modelo": "roleta",
             "conteudo": {"versao": 1, "itens": [{"id": f"i{i}", "pergunta": {"texto": "x", "imagem": PNG}} for i in range(2)]}}
    return autenticado(client, cen.prof_a1).post("/api/pandoo/jogos", json=corpo).get_json()["id"]


# ---- Crítico: exercícios antigos com tipo='jogo' (editor anterior a 09/09) não são jogos do Pandoo

def test_exercicio_antigo_tipo_jogo_nao_trava_missao(client, db_ctx):
    cen = DuasClinicas()
    antigo = novo_exercicio(cen.org_a, "Jogo antigo", tipo="jogo")["id"]
    missao = _missao_com(client, cen, [antigo])
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    c = autenticado(client, cen.resp_a1)
    atividades = c.get(f"/api/jornada/missao/{missao}").get_json()["atividades"]
    assert atividades[0]["exercicio_tipo"] != "jogo"
    assert c.post(f"/api/jornada/missao/{missao}/concluir").status_code == 200


def test_exercicio_antigo_tipo_jogo_segue_na_biblioteca_e_editavel(client, db_ctx):
    cen = DuasClinicas()
    antigo = novo_exercicio(cen.org_a, "Jogo antigo", tipo="jogo")["id"]
    c = autenticado(client, cen.prof_a1)
    lista = c.get("/api/biblioteca/exercicios").get_json()
    item = next(e for e in lista if e["id"] == antigo)
    assert item["tipo"] != "jogo"
    r = c.post(f"/api/biblioteca/exercicios/{antigo}/duplicar")
    assert r.status_code != 409


def test_jogo_do_pandoo_continua_reconhecido(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    lista = autenticado(client, cen.prof_a1).get("/api/biblioteca/exercicios").get_json()
    assert next(e for e in lista if e["id"] == jogo)["tipo"] == "jogo"


def test_migracao_normaliza_tipo_jogo_antigo(db_ctx):
    import migrar_pandoo
    cen = DuasClinicas()
    antigo = novo_exercicio(cen.org_a, "Jogo antigo", tipo="jogo")["id"]
    migrar_pandoo.migrar()
    assert db.query_one("SELECT tipo FROM exercicios WHERE id = ?", (antigo,))["tipo"] == "atividade"


# ---- Importante: WebM falso com HTML depois do cabeçalho

def test_webm_falso_com_html_recusado():
    falso = "GkXfowAAAAAAAAAA\"><img src=x onerror=alert(1)>"
    item = {"id": "i0", "pergunta": {"texto": "x", "imagem": PNG, "audio": falso}}
    conteudo = {"versao": 1, "itens": [item, {**item, "id": "i1"}]}
    try:
        ps.validar_jogo("roleta", conteudo, {}, None)
        assert False, "aceitou WebM falso"
    except ps.ErroPandoo:
        pass


def test_webm_de_verdade_aceito():
    webm = base64.b64encode(b"\x1a\x45\xdf\xa3" + b"\x00" * 200).decode()
    item = {"id": "i0", "pergunta": {"texto": "x", "imagem": PNG, "audio": webm}}
    ps.validar_jogo("roleta", {"versao": 1, "itens": [item, {**item, "id": "i1"}]}, {}, None)


# ---- Importante: responsável só lê jogo que está numa missão de um paciente dele

def test_responsavel_nao_le_jogo_fora_das_missoes_do_filho(client, db_ctx):
    cen = DuasClinicas()
    jogo = _jogo(client, cen)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    c = autenticado(client, cen.resp_a1)
    assert c.get(f"/api/pandoo/jogos/{jogo}").status_code == 403
    _missao_com(client, cen, [jogo])
    assert c.get(f"/api/pandoo/jogos/{jogo}").status_code == 200


# ---- Lista de clínicas do Admin não carrega a imagem de cenário de todas

def test_lista_do_admin_sem_imagem_de_cenario(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={
        "pandoo_cenario_padrao": "clinica", "pandoo_cenario_imagem": PNG, "pandoo_cenario_tom": "claro"})
    admin = novo_usuario(None, "Admin", "admin@saas.com", "admin_master")
    a = next(c for c in autenticado(client, admin).get("/api/admin/clinicas").get_json() if c["id"] == cen.org_a)
    assert "pandoo_cenario_imagem" not in a
    assert a["pandoo_cenario_tem_imagem"] is True
