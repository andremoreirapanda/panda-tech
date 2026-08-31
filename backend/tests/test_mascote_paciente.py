"""
Regressão para a troca de mascote do paciente (insight do usuário,
31/08/2026): provisório até a Gamificação ganhar mascotes de verdade — o
responsável pode trocar o emoji do filho (mesma regra de acesso do upload de
foto, `paciente_acessivel`), mas só entre os mascotes válidos, e nunca de um
paciente sem vínculo com ele.
"""
from factories import DuasClinicas, vincular_responsavel

from conftest import autenticado


def test_responsavel_troca_mascote_do_proprio_filho(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)

    r = autenticado(client, cen.resp_a1).put(
        f"/api/pessoas/pacientes/{cen.paciente_a1}/mascote", json={"avatar_mascote": "🦁"}
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["avatar_mascote"] == "🦁"

    r = autenticado(client, cen.resp_a1).get(f"/api/pessoas/pacientes/{cen.paciente_a1}")
    assert r.get_json()["avatar_mascote"] == "🦁"


def test_responsavel_nao_troca_mascote_de_paciente_sem_vinculo(client, db_ctx):
    cen = DuasClinicas()
    # resp_a1 não está vinculado a paciente_a2 nesse cenário.
    r = autenticado(client, cen.resp_a1).put(
        f"/api/pessoas/pacientes/{cen.paciente_a2}/mascote", json={"avatar_mascote": "🦁"}
    )
    assert r.status_code == 403, r.get_data(as_text=True)


def test_mascote_invalido_e_recusado(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    r = autenticado(client, cen.resp_a1).put(
        f"/api/pessoas/pacientes/{cen.paciente_a1}/mascote", json={"avatar_mascote": "💀"}
    )
    assert r.status_code == 400, r.get_data(as_text=True)


def test_gestor_tambem_pode_trocar_mascote(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).put(
        f"/api/pessoas/pacientes/{cen.paciente_a1}/mascote", json={"avatar_mascote": "🐧"}
    )
    assert r.status_code == 200, r.get_data(as_text=True)
