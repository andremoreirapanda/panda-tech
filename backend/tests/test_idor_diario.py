"""
Regressão de isolamento entre clínicas (IDOR) para o Diário Terapêutico
(Módulo 07) — dado clínico sensível de crianças. Nenhuma clínica pode ler,
criar, editar ou anexar mídia num diário de paciente de outra clínica; e um
responsável nunca pode ler um registro que o profissional não marcou como
compartilhado com a família, mesmo dentro da própria clínica.
"""
import base64

from factories import DuasClinicas, vincular_responsavel

from conftest import autenticado

PNG_VALIDO = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20).decode()


def _criar_jornada(db_ctx, paciente_id):
    return db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (paciente_id, "Objetivo geral"),
    )


def _criar_diario(db_ctx, jornada_id, profissional_id, compartilhado_familia=1):
    return db_ctx.execute(
        "INSERT INTO diarios_terapeuticos (jornada_id, profissional_id, evolucao_clinica, compartilhado_familia) VALUES (?, ?, ?, ?)",
        (jornada_id, profissional_id, "Evolução clínica confidencial", compartilhado_familia),
    )


def test_profissional_nao_vinculado_nao_cria_diario_de_paciente_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = _criar_jornada(db_ctx, cen.paciente_a1)
    r = autenticado(client, cen.prof_b1).post(f"/api/diario/jornada/{jornada_id}", json={
        "evolucao_clinica": "Tentativa de acesso indevido",
    })
    assert r.status_code == 403, r.get_data(as_text=True)


def test_profissional_vinculado_cria_diario_normalmente(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = _criar_jornada(db_ctx, cen.paciente_a1)
    r = autenticado(client, cen.prof_a1).post(f"/api/diario/jornada/{jornada_id}", json={
        "evolucao_clinica": "Evolução real",
    })
    assert r.status_code == 201, r.get_data(as_text=True)


def test_gestor_de_outra_clinica_nao_edita_diario(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = _criar_jornada(db_ctx, cen.paciente_a1)
    diario_id = _criar_diario(db_ctx, jornada_id, cen.prof_a1["id"])
    r = autenticado(client, cen.gestor_b).put(f"/api/diario/{diario_id}", json={"evolucao_clinica": "hackeado"})
    assert r.status_code == 403, r.get_data(as_text=True)
    diario = db_ctx.query_one("SELECT evolucao_clinica FROM diarios_terapeuticos WHERE id = ?", (diario_id,))
    assert diario["evolucao_clinica"] != "hackeado"


def test_gestor_da_mesma_clinica_edita_diario_normalmente(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = _criar_jornada(db_ctx, cen.paciente_a1)
    diario_id = _criar_diario(db_ctx, jornada_id, cen.prof_a1["id"])
    r = autenticado(client, cen.gestor_a).put(f"/api/diario/{diario_id}", json={"evolucao_clinica": "ajuste legítimo"})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_gestor_de_outra_clinica_nao_anexa_midia(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = _criar_jornada(db_ctx, cen.paciente_a1)
    diario_id = _criar_diario(db_ctx, jornada_id, cen.prof_a1["id"])
    r = autenticado(client, cen.gestor_b).post(f"/api/diario/{diario_id}/anexo", json={
        "tipo": "foto", "conteudo_base64": PNG_VALIDO, "nome_arquivo": "foto.png",
    })
    assert r.status_code == 403, r.get_data(as_text=True)


def test_responsavel_de_outra_clinica_nao_ve_diario(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = _criar_jornada(db_ctx, cen.paciente_a1)
    diario_id = _criar_diario(db_ctx, jornada_id, cen.prof_a1["id"])
    r = autenticado(client, cen.resp_b1).get(f"/api/diario/{diario_id}")
    assert r.status_code == 403, r.get_data(as_text=True)


def test_responsavel_de_outra_clinica_nao_ve_anexo(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = _criar_jornada(db_ctx, cen.paciente_a1)
    diario_id = _criar_diario(db_ctx, jornada_id, cen.prof_a1["id"])
    anexo_id = db_ctx.execute(
        "INSERT INTO diario_anexos (diario_id, tipo, nome_arquivo, conteudo_base64, tamanho_bytes) VALUES (?, 'foto', 'x.png', ?, 10)",
        (diario_id, PNG_VALIDO),
    )
    r = autenticado(client, cen.resp_b1).get(f"/api/diario/anexo/{anexo_id}")
    assert r.status_code == 403, r.get_data(as_text=True)


def test_responsavel_da_mesma_clinica_ve_diario_compartilhado(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    jornada_id = _criar_jornada(db_ctx, cen.paciente_a1)
    diario_id = _criar_diario(db_ctx, jornada_id, cen.prof_a1["id"], compartilhado_familia=1)
    r = autenticado(client, cen.resp_a1).get(f"/api/diario/{diario_id}")
    assert r.status_code == 200, r.get_data(as_text=True)
    # Evolução clínica (linguagem técnica interna) nunca é exposta à família.
    assert r.get_json()["evolucao_clinica"] is None


def test_responsavel_nao_ve_diario_nao_compartilhado_mesmo_da_propria_clinica(client, db_ctx):
    """Achado desta rodada: obter_diario() buscava por id direto sem checar
    compartilhado_familia (só listar_diarios() checava) — um responsável que
    soubesse/adivinhasse o id de um registro não compartilhado conseguia lê-lo."""
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    jornada_id = _criar_jornada(db_ctx, cen.paciente_a1)
    diario_id = _criar_diario(db_ctx, jornada_id, cen.prof_a1["id"], compartilhado_familia=0)
    r = autenticado(client, cen.resp_a1).get(f"/api/diario/{diario_id}")
    assert r.status_code == 403, r.get_data(as_text=True)


def test_responsavel_nao_ve_anexo_de_diario_nao_compartilhado(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    jornada_id = _criar_jornada(db_ctx, cen.paciente_a1)
    diario_id = _criar_diario(db_ctx, jornada_id, cen.prof_a1["id"], compartilhado_familia=0)
    anexo_id = db_ctx.execute(
        "INSERT INTO diario_anexos (diario_id, tipo, nome_arquivo, conteudo_base64, tamanho_bytes) VALUES (?, 'foto', 'x.png', ?, 10)",
        (diario_id, PNG_VALIDO),
    )
    r = autenticado(client, cen.resp_a1).get(f"/api/diario/anexo/{anexo_id}")
    assert r.status_code == 403, r.get_data(as_text=True)


def test_profissional_da_mesma_clinica_ve_diario_nao_compartilhado(client, db_ctx):
    """A restrição de compartilhado_familia é só para o papel 'responsavel' —
    a equipe clínica sempre pode ver, compartilhado ou não."""
    cen = DuasClinicas()
    jornada_id = _criar_jornada(db_ctx, cen.paciente_a1)
    diario_id = _criar_diario(db_ctx, jornada_id, cen.prof_a1["id"], compartilhado_familia=0)
    r = autenticado(client, cen.prof_a1).get(f"/api/diario/{diario_id}")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["evolucao_clinica"] == "Evolução clínica confidencial"
