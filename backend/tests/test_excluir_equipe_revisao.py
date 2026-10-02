"""
Revisão do PR #35 (01/10/2026): quem foi excluído da Equipe não pode voltar
por outras rotas (editar, arquivar/reativar, reenviar convite); a exclusão é
bloqueada enquanto houver consultas futuras; e a agenda não aceita consulta
para profissional arquivado ou excluído.
"""
from factories import DuasClinicas, novo_usuario

from conftest import autenticado


def _consulta(db_ctx, prof_id, paciente_id, data_hora):
    db_ctx.execute(
        "INSERT INTO consultas (paciente_id, profissional_id, data_hora) VALUES (?, ?, ?)",
        (paciente_id, prof_id, data_hora),
    )


def _excluir_com_historico(client, db_ctx, cen, usuario, rota):
    _consulta(db_ctx, usuario["id"], cen.paciente_a1, "2020-01-01 09:00:00") if rota == "profissionais" else \
        db_ctx.execute("INSERT INTO avisos (organizacao_id, autor_id, titulo, conteudo) VALUES (?, ?, 'a', 'b')",
                       (cen.org_a, usuario["id"]))
    r = autenticado(client, cen.gestor_a).delete(f"/api/pessoas/{rota}/{usuario['id']}")
    assert r.get_json()["modo"] == "historico_mantido", r.get_data(as_text=True)


def test_excluido_nao_volta_por_editar_arquivar_ou_convite(client, db_ctx):
    cen = DuasClinicas()
    _excluir_com_historico(client, db_ctx, cen, cen.prof_a1, "profissionais")
    g = autenticado(client, cen.gestor_a)
    pid = cen.prof_a1["id"]
    assert g.put(f"/api/pessoas/profissionais/{pid}", json={"nome": "Volta", "email": "prof.a1@a.com"}).status_code == 404
    assert g.put(f"/api/pessoas/profissionais/{pid}/arquivar").status_code == 404
    assert g.post(f"/api/pessoas/profissionais/{pid}/reenviar-convite").status_code == 404
    u = db_ctx.query_one("SELECT ativo, email FROM usuarios WHERE id = ?", (pid,))
    assert not u["ativo"] and u["email"] != "prof.a1@a.com"


def test_secretaria_excluida_nao_volta(client, db_ctx):
    cen = DuasClinicas()
    sec = novo_usuario(cen.org_a, "Secretária A", "sec@a.com", "secretaria")
    _excluir_com_historico(client, db_ctx, cen, sec, "secretarias")
    g = autenticado(client, cen.gestor_a)
    assert g.put(f"/api/pessoas/secretarias/{sec['id']}", json={"nome": "Volta", "email": "sec@a.com"}).status_code == 404
    assert g.put(f"/api/pessoas/secretarias/{sec['id']}/arquivar").status_code == 404
    assert g.post(f"/api/pessoas/secretarias/{sec['id']}/reenviar-convite").status_code == 404


def test_exclusao_bloqueada_com_consultas_futuras(client, db_ctx):
    cen = DuasClinicas()
    _consulta(db_ctx, cen.prof_a1["id"], cen.paciente_a1, "2099-01-10 09:00:00")
    _consulta(db_ctx, cen.prof_a1["id"], cen.paciente_a2, "2099-01-11 09:00:00")
    r = autenticado(client, cen.gestor_a).delete(f"/api/pessoas/profissionais/{cen.prof_a1['id']}")
    assert r.status_code == 409, r.get_data(as_text=True)
    assert "2 consultas" in r.get_json()["erro"]
    assert db_ctx.query_one("SELECT ativo FROM usuarios WHERE id = ?", (cen.prof_a1["id"],))["ativo"]
    # consulta futura cancelada não bloqueia
    db_ctx.execute("UPDATE consultas SET status = 'cancelada' WHERE profissional_id = ?", (cen.prof_a1["id"],))
    r = autenticado(client, cen.gestor_a).delete(f"/api/pessoas/profissionais/{cen.prof_a1['id']}")
    assert r.status_code == 200 and r.get_json()["modo"] == "historico_mantido"


def test_agenda_nao_aceita_profissional_arquivado_ou_excluido(client, db_ctx):
    cen = DuasClinicas()
    g = autenticado(client, cen.gestor_a)
    g.put(f"/api/pessoas/profissionais/{cen.prof_a2['id']}/arquivar")
    r = g.post("/api/agenda", json={"paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a2["id"],
                                    "data_hora": "2099-02-01 09:00:00"})
    assert r.status_code in (400, 403, 404), r.get_data(as_text=True)
    assert db_ctx.query_one("SELECT 1 FROM profissionais_pacientes WHERE usuario_id = ?", (cen.prof_a2["id"],)) is None
