"""
Excluir alguém da Equipe (pedido do usuário, 01/10/2026). Sem histórico, o
cadastro é apagado de vez; com histórico (consultas, planos, diários,
mensagens, avisos, ficha clínica, partidas do Pandoo) ele some da equipe para
sempre, perde o acesso e libera o e-mail — mas os registros antigos ficam.
"""
from factories import DuasClinicas, novo_usuario

from conftest import autenticado, token_de


def _usuario(db_ctx, uid):
    return db_ctx.query_one("SELECT * FROM usuarios WHERE id = ?", (uid,))


def _consulta(db_ctx, prof_id, paciente_id):
    db_ctx.execute(
        "INSERT INTO consultas (paciente_id, profissional_id, data_hora) VALUES (?, ?, '2026-09-01 09:00:00')",
        (paciente_id, prof_id),
    )


def _equipe(client, gestor):
    r = autenticado(client, gestor).get("/api/pessoas/profissionais?incluir_inativos=1&incluir_secretarias=1")
    return [p["id"] for p in r.get_json()]


def test_profissional_sem_historico_e_apagado_de_vez(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).delete(f"/api/pessoas/profissionais/{cen.prof_a2['id']}")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["modo"] == "definitivo"
    assert _usuario(db_ctx, cen.prof_a2["id"]) is None
    assert cen.prof_a2["id"] not in _equipe(client, cen.gestor_a)


def test_vinculos_nao_contam_como_historico_e_saem_junto(client, db_ctx):
    cen = DuasClinicas()   # prof_a1 está vinculado a dois pacientes, sem consulta
    r = autenticado(client, cen.gestor_a).delete(f"/api/pessoas/profissionais/{cen.prof_a1['id']}")
    assert r.get_json()["modo"] == "definitivo"
    assert db_ctx.query_one("SELECT 1 FROM profissionais_pacientes WHERE usuario_id = ?", (cen.prof_a1["id"],)) is None


def test_profissional_com_historico_some_da_equipe_e_mantem_registros(client, db_ctx):
    cen = DuasClinicas()
    _consulta(db_ctx, cen.prof_a1["id"], cen.paciente_a1)
    r = autenticado(client, cen.gestor_a).delete(f"/api/pessoas/profissionais/{cen.prof_a1['id']}")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["modo"] == "historico_mantido"
    u = _usuario(db_ctx, cen.prof_a1["id"])
    assert u is not None and u["excluido_em"] and not u["ativo"]
    assert u["nome"] == "Prof A1"                       # o histórico continua com o nome
    assert u["email"] != "prof.a1@a.com"                 # e-mail liberado
    assert db_ctx.query_one("SELECT 1 FROM consultas WHERE profissional_id = ?", (cen.prof_a1["id"],))
    assert cen.prof_a1["id"] not in _equipe(client, cen.gestor_a)
    login = client.post("/api/auth/login", json={"email": "prof.a1@a.com", "senha": "senhateste123"})
    assert login.status_code in (401, 403)
    # o e-mail pode ser usado de novo
    novo = autenticado(client, cen.gestor_a).post("/api/pessoas/profissionais", json={
        "nome": "Prof A1 de novo", "email": "prof.a1@a.com", "especialidade": "Fonoaudiologia",
    })
    assert novo.status_code == 201, novo.get_data(as_text=True)


def test_token_antigo_de_quem_foi_excluido_perde_acesso(client, db_ctx):
    cen = DuasClinicas()
    _consulta(db_ctx, cen.prof_a1["id"], cen.paciente_a1)
    token_antigo = token_de(cen.prof_a1)
    assert client.get("/api/pessoas/pacientes", headers={"Authorization": f"Bearer {token_antigo}"}).status_code == 200
    autenticado(client, cen.gestor_a).delete(f"/api/pessoas/profissionais/{cen.prof_a1['id']}")
    r = client.get("/api/pessoas/pacientes", headers={"Authorization": f"Bearer {token_antigo}"})
    assert r.status_code == 401


def test_secretaria_pode_ser_excluida(client, db_ctx):
    cen = DuasClinicas()
    sec = novo_usuario(cen.org_a, "Secretária A", "sec@a.com", "secretaria")
    r = autenticado(client, cen.gestor_a).delete(f"/api/pessoas/secretarias/{sec['id']}")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["modo"] == "definitivo"
    assert _usuario(db_ctx, sec["id"]) is None


def test_so_o_gestor_da_propria_clinica_exclui(client, db_ctx):
    cen = DuasClinicas()
    assert autenticado(client, cen.prof_a1).delete(f"/api/pessoas/profissionais/{cen.prof_a2['id']}").status_code == 403
    assert autenticado(client, cen.gestor_b).delete(f"/api/pessoas/profissionais/{cen.prof_a2['id']}").status_code == 404
    # a rota não serve para o gestor nem para responsável
    assert autenticado(client, cen.gestor_a).delete(f"/api/pessoas/profissionais/{cen.gestor_a['id']}").status_code == 404
    assert autenticado(client, cen.gestor_a).delete(f"/api/pessoas/secretarias/{cen.resp_a1['id']}").status_code == 404
    assert _usuario(db_ctx, cen.prof_a2["id"]) is not None


def test_exclusao_fica_na_auditoria(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, cen.gestor_a).delete(f"/api/pessoas/profissionais/{cen.prof_a2['id']}")
    assert db_ctx.query_one(
        "SELECT 1 FROM auditoria WHERE acao = 'excluir' AND entidade_id = ?", (cen.prof_a2["id"],))
