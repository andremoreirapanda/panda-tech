"""
Regressão para a funcionalidade "Gestor pode atuar como profissional"
(insight do usuário, 31/08/2026): o gestor pode, opcionalmente, também
atuar como profissional da própria clínica, usando a MESMA conta (mesmo
login/senha) — sem precisar de um cadastro separado na Equipe.

Cobre: ativar/desativar a flag (com validação de especialidade obrigatória),
o gestor virar um alvo válido de `profissional_id` em consultas, o gestor
poder ser vinculado a um paciente como profissional, e o isolamento entre
clínicas (um gestor de outra clínica não pode ser atribuído/vinculado).
"""
from factories import DuasClinicas, novo_usuario

from conftest import autenticado


def test_gestor_nao_pode_ser_atribuido_a_consulta_antes_de_ativar(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.gestor_a["id"], "data_hora": "2026-09-01 10:00:00",
    })
    assert r.status_code == 400, r.get_data(as_text=True)


def test_ativar_exige_especialidade(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).put("/api/pessoas/perfil/atuar-como-profissional", json={
        "atua_como_profissional": True,
    })
    assert r.status_code == 400, r.get_data(as_text=True)


def test_ativar_e_atribuir_consulta_ao_proprio_gestor(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).put("/api/pessoas/perfil/atuar-como-profissional", json={
        "atua_como_profissional": True, "especialidade": "Fonoaudiologia", "cor_agenda": "#ff0000",
    })
    assert r.status_code == 200, r.get_data(as_text=True)

    r = autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.gestor_a["id"], "data_hora": "2026-09-01 10:00:00",
    })
    assert r.status_code == 201, r.get_data(as_text=True)


def test_desativar_impede_nova_atribuicao_mas_nao_apaga_consultas_antigas(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, cen.gestor_a).put("/api/pessoas/perfil/atuar-como-profissional", json={
        "atua_como_profissional": True, "especialidade": "Fonoaudiologia",
    })
    r = autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.gestor_a["id"], "data_hora": "2026-09-01 10:00:00",
    })
    assert r.status_code == 201

    r = autenticado(client, cen.gestor_a).put("/api/pessoas/perfil/atuar-como-profissional", json={
        "atua_como_profissional": False,
    })
    assert r.status_code == 200

    # Consulta antiga continua existindo, listável normalmente.
    r = autenticado(client, cen.gestor_a).get("/api/agenda")
    assert r.status_code == 200
    assert any(c["profissional_id"] == cen.gestor_a["id"] for c in r.get_json())

    # Mas não é mais um alvo válido para uma consulta NOVA.
    r = autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.gestor_a["id"], "data_hora": "2026-09-08 10:00:00",
    })
    assert r.status_code == 400, r.get_data(as_text=True)


def test_gestor_de_outra_clinica_nao_e_atribuivel(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, cen.gestor_b).put("/api/pessoas/perfil/atuar-como-profissional", json={
        "atua_como_profissional": True, "especialidade": "Psicologia",
    })
    r = autenticado(client, cen.gestor_a).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.gestor_b["id"], "data_hora": "2026-09-01 10:00:00",
    })
    assert r.status_code == 400, r.get_data(as_text=True)


def test_vincular_gestor_como_profissional_do_paciente(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, cen.gestor_a).put("/api/pessoas/perfil/atuar-como-profissional", json={
        "atua_como_profissional": True, "especialidade": "Terapia Ocupacional",
    })
    r = autenticado(client, cen.gestor_a).post(
        f"/api/pessoas/pacientes/{cen.paciente_a2}/vincular-profissional",
        json={"profissional_id": cen.gestor_a["id"]},
    )
    assert r.status_code == 200, r.get_data(as_text=True)

    r = autenticado(client, cen.gestor_a).get(f"/api/pessoas/pacientes/{cen.paciente_a2}")
    ids = [p["id"] for p in r.get_json()["profissionais"]]
    assert cen.gestor_a["id"] in ids


def test_listar_profissionais_so_inclui_gestor_com_incluir_gestor(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, cen.gestor_a).put("/api/pessoas/perfil/atuar-como-profissional", json={
        "atua_como_profissional": True, "especialidade": "Psicopedagogia",
    })

    r = autenticado(client, cen.gestor_a).get("/api/pessoas/profissionais")
    ids_padrao = [p["id"] for p in r.get_json()]
    assert cen.gestor_a["id"] not in ids_padrao  # tela de Equipe não deve listar o gestor

    r = autenticado(client, cen.gestor_a).get("/api/pessoas/profissionais?incluir_gestor=1")
    ids_com_gestor = [p["id"] for p in r.get_json()]
    assert cen.gestor_a["id"] in ids_com_gestor


def test_profissional_nao_pode_ativar_a_flag_de_outro_papel(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.prof_a1).put("/api/pessoas/perfil/atuar-como-profissional", json={
        "atua_como_profissional": True, "especialidade": "Fonoaudiologia",
    })
    assert r.status_code == 403, r.get_data(as_text=True)


def test_atua_como_profissional_nao_conta_no_limite_de_vagas_do_plano(client, db_ctx):
    """
    _limite_do_plano_excedido conta só papel='profissional' — o gestor
    atuando como profissional não deve consumir vaga do plano.
    """
    from db import execute as db_execute, query_one

    cen = DuasClinicas()
    db_execute("UPDATE organizacoes SET plano = 'basico' WHERE id = ?", (cen.org_a,))
    db_execute(
        "INSERT INTO planos (codigo, nome, preco_mensal_centavos, limite_profissionais) VALUES (?, ?, ?, ?)",
        ("basico", "Básico", 9900, 2),
    )

    autenticado(client, cen.gestor_a).put("/api/pessoas/perfil/atuar-como-profissional", json={
        "atua_como_profissional": True, "especialidade": "Fonoaudiologia",
    })
    # org_a já tem prof_a1 e prof_a2 = 2 profissionais reais (no limite de 2).
    total = query_one(
        "SELECT COUNT(*) as c FROM usuarios WHERE organizacao_id = ? AND papel = 'profissional'", (cen.org_a,)
    )["c"]
    assert total == 2  # o gestor (papel='gestor') não entrou nessa contagem
