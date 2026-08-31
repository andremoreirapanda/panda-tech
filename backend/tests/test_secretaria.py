"""
Regressão para o perfil "Secretária" (insight do usuário, 31/08/2026):
função administrativa cadastrada pelo gestor pela tela Equipe, opcional por
plano (vaga limitada, igual profissionais). Pode cadastrar paciente
(definindo o profissional), agendar consultas pra qualquer profissional da
clínica, vincular profissional/responsável a um paciente, ver a Equipe só em
modo leitura e publicar no Mural — mas NUNCA acessa dado clínico (jornada,
diário, ficha clínica) nem financeiro.
"""
from factories import DuasClinicas, novo_usuario, novo_paciente

from conftest import autenticado


def _com_secretaria(cen, org_attr="org_a", nome="Secretária A", email="secretaria@a.com"):
    org_id = getattr(cen, org_attr)
    return novo_usuario(org_id, nome, email, "secretaria")


def test_secretaria_cadastra_paciente_definindo_profissional(client, db_ctx):
    cen = DuasClinicas()
    sec = _com_secretaria(cen)
    r = autenticado(client, sec).post("/api/pessoas/pacientes", json={
        "nome": "Novo Paciente", "data_nascimento": "2020-05-01",
        "profissionais_ids": [cen.prof_a1["id"]],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    paciente_id = r.get_json()["id"]

    r = autenticado(client, sec).get(f"/api/pessoas/pacientes/{paciente_id}")
    assert r.status_code == 200
    ids_prof = [p["id"] for p in r.get_json()["profissionais"]]
    assert cen.prof_a1["id"] in ids_prof


def test_secretaria_lista_pacientes_so_ve_nome_e_responsavel(client, db_ctx):
    cen = DuasClinicas()
    sec = _com_secretaria(cen)
    from factories import vincular_responsavel
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)

    r = autenticado(client, sec).get("/api/pessoas/pacientes")
    assert r.status_code == 200
    linhas = r.get_json()
    assert len(linhas) == 2
    linha_a1 = next(p for p in linhas if p["id"] == cen.paciente_a1)
    assert linha_a1["nome"] == "Paciente A1"
    assert "Familia A1" in linha_a1["responsaveis_nomes"]
    # Nenhum campo clínico/identidade sensível vaza nessa listagem.
    assert "data_nascimento" not in linha_a1
    assert "genero" not in linha_a1


def test_secretaria_obter_paciente_nao_expoe_campos_clinicos(client, db_ctx):
    cen = DuasClinicas()
    sec = _com_secretaria(cen)
    r = autenticado(client, sec).get(f"/api/pessoas/pacientes/{cen.paciente_a1}")
    assert r.status_code == 200
    dados = r.get_json()
    assert dados["nome"] == "Paciente A1"
    assert "data_nascimento" not in dados
    assert "genero" not in dados
    assert "responsaveis" in dados and "profissionais" in dados


def test_secretaria_sem_acesso_a_ficha_clinica(client, db_ctx):
    cen = DuasClinicas()
    sec = _com_secretaria(cen)
    r = autenticado(client, sec).get(f"/api/pessoas/pacientes/{cen.paciente_a1}/ficha-clinica")
    assert r.status_code == 403, r.get_data(as_text=True)


def test_secretaria_pode_vincular_profissional_e_responsavel(client, db_ctx):
    cen = DuasClinicas()
    sec = _com_secretaria(cen)

    r = autenticado(client, sec).post(
        f"/api/pessoas/pacientes/{cen.paciente_a2}/vincular-profissional",
        json={"profissional_id": cen.prof_a2["id"]},
    )
    assert r.status_code == 200, r.get_data(as_text=True)

    r = autenticado(client, sec).post(
        f"/api/pessoas/pacientes/{cen.paciente_a2}/vincular-responsavel",
        json={"nome": "Nova Família", "email": "nova.familia@a.com", "telefone": "11999990000"},
    )
    assert r.status_code == 201, r.get_data(as_text=True)


def test_secretaria_nao_pode_vincular_profissional_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    sec = _com_secretaria(cen)
    r = autenticado(client, sec).post(
        f"/api/pessoas/pacientes/{cen.paciente_a1}/vincular-profissional",
        json={"profissional_id": cen.prof_b1["id"]},
    )
    assert r.status_code == 404, r.get_data(as_text=True)


def test_secretaria_agenda_consulta_para_qualquer_profissional_sem_permissao_total(client, db_ctx):
    cen = DuasClinicas()
    sec = _com_secretaria(cen)
    # prof_a2 não tem agenda_permissao_total nenhuma — mesmo assim a
    # secretária consegue agendar pra ele, por ser função administrativa.
    r = autenticado(client, sec).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a2["id"], "data_hora": "2026-09-01 10:00:00",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    consulta_id = r.get_json()["id"]

    r = autenticado(client, sec).put(f"/api/agenda/{consulta_id}/status", json={"status": "confirmada"})
    assert r.status_code == 200, r.get_data(as_text=True)

    r = autenticado(client, sec).delete(f"/api/agenda/{consulta_id}")
    assert r.status_code == 200, r.get_data(as_text=True)


def test_secretaria_nao_agenda_para_paciente_ou_profissional_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    sec = _com_secretaria(cen)
    r = autenticado(client, sec).post("/api/agenda", json={
        "paciente_id": cen.paciente_a1, "profissional_id": cen.prof_b1["id"], "data_hora": "2026-09-01 10:00:00",
    })
    assert r.status_code == 400, r.get_data(as_text=True)

    outro_paciente_b = novo_paciente(cen.org_b, "Paciente B2")
    r = autenticado(client, sec).post("/api/agenda", json={
        "paciente_id": outro_paciente_b, "profissional_id": cen.prof_a1["id"], "data_hora": "2026-09-01 10:00:00",
    })
    assert r.status_code == 403, r.get_data(as_text=True)


def test_secretaria_visualiza_equipe_mas_nao_cadastra_nem_arquiva_profissional(client, db_ctx):
    cen = DuasClinicas()
    sec = _com_secretaria(cen)

    r = autenticado(client, sec).get("/api/pessoas/profissionais?incluir_inativos=1&incluir_gestor=1&incluir_secretarias=1")
    assert r.status_code == 200
    papeis = {p["papel"] for p in r.get_json()}
    assert "profissional" in papeis and "secretaria" in papeis

    r = autenticado(client, sec).post("/api/pessoas/profissionais", json={"nome": "X", "email": "x@a.com"})
    assert r.status_code == 403

    r = autenticado(client, sec).put(f"/api/pessoas/profissionais/{cen.prof_a1['id']}/arquivar")
    assert r.status_code == 403


def test_secretaria_pode_publicar_e_ver_mural_da_equipe(client, db_ctx):
    cen = DuasClinicas()
    sec = _com_secretaria(cen)
    r = autenticado(client, sec).post("/api/comunicacao/avisos", json={
        "titulo": "Aviso da secretaria", "conteudo": "Oi equipe", "publico": "equipe",
    })
    assert r.status_code == 201, r.get_data(as_text=True)

    r = autenticado(client, sec).get("/api/comunicacao/avisos")
    assert r.status_code == 200
    assert any(a["titulo"] == "Aviso da secretaria" for a in r.get_json())


def test_gestor_cadastra_edita_e_arquiva_secretaria_pela_equipe(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/pessoas/secretarias", json={
        "nome": "Secretária Nova", "email": "nova.sec@a.com", "telefone": "11988887777",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    sec_id = r.get_json()["id"]
    assert r.get_json()["link_convite"]

    r = autenticado(client, cen.gestor_a).put(f"/api/pessoas/secretarias/{sec_id}", json={"nome": "Secretária Editada"})
    assert r.status_code == 200

    r = autenticado(client, cen.gestor_a).put(f"/api/pessoas/secretarias/{sec_id}/arquivar")
    assert r.status_code == 200
    assert r.get_json()["ativo"] is False


def test_gestor_nao_edita_secretaria_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    sec_b = _com_secretaria(cen, org_attr="org_b", nome="Secretária B", email="secretaria@b.com")
    r = autenticado(client, cen.gestor_a).put(f"/api/pessoas/secretarias/{sec_b['id']}", json={"nome": "Hackeada"})
    assert r.status_code == 404


def test_secretaria_nao_pode_cadastrar_outra_secretaria(client, db_ctx):
    cen = DuasClinicas()
    sec = _com_secretaria(cen)
    r = autenticado(client, sec).post("/api/pessoas/secretarias", json={"nome": "X", "email": "x2@a.com"})
    assert r.status_code == 403


def test_cadastro_de_secretaria_respeita_limite_do_plano(client, db_ctx):
    from db import execute as db_execute

    cen = DuasClinicas()
    db_execute("UPDATE organizacoes SET plano = 'basico' WHERE id = ?", (cen.org_a,))
    db_execute(
        "INSERT INTO planos (codigo, nome, preco_mensal_centavos, limite_secretarias) VALUES (?, ?, ?, ?)",
        ("basico", "Básico", 9900, 1),
    )

    r = autenticado(client, cen.gestor_a).post("/api/pessoas/secretarias", json={
        "nome": "Secretária 1", "email": "sec1@a.com",
    })
    assert r.status_code == 201, r.get_data(as_text=True)

    r = autenticado(client, cen.gestor_a).post("/api/pessoas/secretarias", json={
        "nome": "Secretária 2", "email": "sec2@a.com",
    })
    assert r.status_code == 403, r.get_data(as_text=True)


def test_plano_com_limite_zero_secretarias_bloqueia_cadastro(client, db_ctx):
    from db import execute as db_execute

    cen = DuasClinicas()
    db_execute("UPDATE organizacoes SET plano = 'starter_teste' WHERE id = ?", (cen.org_a,))
    db_execute(
        "INSERT INTO planos (codigo, nome, preco_mensal_centavos, limite_secretarias) VALUES (?, ?, ?, ?)",
        ("starter_teste", "Starter Teste", 9900, 0),
    )
    r = autenticado(client, cen.gestor_a).post("/api/pessoas/secretarias", json={
        "nome": "Secretária", "email": "sec@a.com",
    })
    assert r.status_code == 403, r.get_data(as_text=True)
