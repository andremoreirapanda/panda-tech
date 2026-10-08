"""Correções das pendências menores das partes 2, 3a e 3c (08/10/2026)."""
from datetime import date, datetime

import pytest

from factories import DuasClinicas, novo_usuario, vincular_responsavel

from conftest import autenticado

ALMOCO = {"data_inicio": "2026-10-05", "data_fim": "", "dia_inteiro": False,
          "hora_inicio": "09:00", "hora_fim": "10:00", "dias_semana": "12345", "motivo": "Reunião"}
INICIO = {"objetivo_principal": "Autonomia", "especialidade": "Fonoaudiologia", "titulo": "Fono Out", "objetivos": ["A"]}


# ---------------------------------------------------------------- 1. editar só a observação

def test_editar_observacao_de_consulta_sem_zero_nao_checa_ausencia(client, db_ctx):
    cen = DuasClinicas()
    cid = db_ctx.execute("""INSERT INTO consultas (paciente_id, profissional_id, data_hora, duracao_min)
                            VALUES (?, ?, '2026-10-06 9:00:00', 50)""", (cen.paciente_a1, cen.prof_a1["id"]))
    c = autenticado(client, cen.gestor_a)
    c.post("/api/agenda/ausencias", json={**ALMOCO, "profissional_id": cen.prof_a1["id"]})
    # O pop-up reenvia a hora com zero e a duração: não mudou nada de verdade.
    r = c.put(f"/api/agenda/{cid}", json={"data_hora": "2026-10-06 09:00:00", "duracao_min": 50, "observacoes": "Trazer exames"})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_editar_observacao_com_duracao_antiga_fora_da_faixa(client, db_ctx):
    cen = DuasClinicas()
    cid = db_ctx.execute("""INSERT INTO consultas (paciente_id, profissional_id, data_hora, duracao_min)
                            VALUES (?, ?, '2026-10-06 14:00:00', 600)""", (cen.paciente_a1, cen.prof_a1["id"]))
    r = autenticado(client, cen.gestor_a).put(f"/api/agenda/{cid}", json={"duracao_min": 600, "observacoes": "x"})
    assert r.status_code == 200, r.get_data(as_text=True)
    r2 = autenticado(client, cen.gestor_a).put(f"/api/agenda/{cid}", json={"duracao_min": 700})
    assert r2.status_code == 400  # mudar para outro valor fora da faixa continua barrado


# ---------------------------------------------------------------- 2. "hoje" no horário de Brasília

def test_hoje_das_ausencias_e_no_horario_de_brasilia(monkeypatch):
    import ausencias_service
    monkeypatch.setattr(ausencias_service, "_agora_utc", lambda: datetime(2026, 10, 9, 1, 30))  # 22h30 de 08/10 em Brasília
    assert ausencias_service.hoje_brasilia() == date(2026, 10, 8)


# ---------------------------------------------------------------- 5. exclusão da Equipe desfaz a transação

def test_exclusao_definitiva_que_falha_desfaz_antes_de_tentar_de_novo(client, db_ctx, monkeypatch):
    import db
    from blueprints import pessoas_bp
    cen = DuasClinicas()
    chamadas = []
    conexao = db.get_db()
    original_rollback = conexao.rollback
    execute_original = pessoas_bp.execute

    def execute_falhando(sql, params=()):
        if sql.strip().startswith("DELETE FROM usuarios"):
            raise RuntimeError("FK")
        return execute_original(sql, params)

    monkeypatch.setattr(pessoas_bp, "execute", execute_falhando)
    monkeypatch.setattr(pessoas_bp, "get_db", lambda: type("C", (), {"rollback": lambda self: chamadas.append(1) or original_rollback()})())
    r = autenticado(client, cen.gestor_a).delete(f"/api/pessoas/profissionais/{cen.prof_a2['id']}")
    assert r.status_code == 200 and r.get_json()["modo"] == "historico_mantido"
    assert chamadas == [1]


# ---------------------------------------------------------------- 6. diários recentes da família

def test_familia_recebe_os_5_compartilhados_mesmo_com_privados_mais_novos(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    for i in range(6):
        db_ctx.execute("""INSERT INTO diarios_terapeuticos (paciente_id, profissional_id, evolucao_clinica, data_atendimento)
                          VALUES (?, ?, 'c', ?)""", (cen.paciente_a1, cen.prof_a1["id"], f"2026-09-0{i + 1}"))
    for i in range(3):
        db_ctx.execute("""INSERT INTO diarios_terapeuticos (paciente_id, profissional_id, evolucao_clinica, data_atendimento,
                          compartilhado_familia) VALUES (?, ?, 'p', ?, 0)""", (cen.paciente_a1, cen.prof_a1["id"], f"2026-10-0{i + 1}"))
    d = autenticado(client, cen.resp_a1).get(f"/api/jornada/paciente/{cen.paciente_a1}").get_json()
    assert [x["data_atendimento"] for x in d["diarios_recentes"]] == [f"2026-09-0{i}" for i in (6, 5, 4, 3, 2)]


# ---------------------------------------------------------------- 7 e 15. validação de plano

@pytest.mark.parametrize("ruim", [{"objetivos": "abc"}, {"objetivos": ["x" * 301]}, {"titulo": "x" * 121}])
def test_iniciar_e_criar_plano_validam_objetivos_e_titulo(client, db_ctx, ruim):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)
    assert c.post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json={**INICIO, **ruim}).status_code == 400
    jor = c.post(f"/api/jornada/paciente/{cen.paciente_a2}/iniciar", json=INICIO).get_json()["jornada_id"]
    corpo = {"titulo": "T", "objetivos": ["X"], "especialidade": "Psicologia", **ruim}
    assert c.post(f"/api/jornada/jornada/{jor}/criar-plano", json=corpo).status_code == 400


def test_criar_plano_reclama_da_especialidade_primeiro(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)
    jor = c.post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=INICIO).get_json()["jornada_id"]
    r = c.post(f"/api/jornada/jornada/{jor}/criar-plano", json={"titulo": "T"})
    assert r.status_code == 400 and "especialidade" in r.get_json()["erro"]


# ---------------------------------------------------------------- 8 e 9. diário: consulta_id e rota antiga

@pytest.mark.parametrize("valor", ["abc", [1], {"a": 1}])
def test_consulta_id_em_formato_errado_da_400(client, db_ctx, valor):
    cen = DuasClinicas()
    r = autenticado(client, cen.prof_a1).post(f"/api/diario/paciente/{cen.paciente_a1}",
                                               json={"evolucao_clinica": "x", "consulta_id": valor})
    assert r.status_code == 400


def test_rota_antiga_grava_a_jornada_do_endereco(client, db_ctx):
    cen = DuasClinicas()
    antiga = db_ctx.execute("INSERT INTO jornadas (paciente_id, objetivo_principal, status) VALUES (?, 'Velha', 'encerrada')",
                            (cen.paciente_a1,))
    db_ctx.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, 'Atual')", (cen.paciente_a1,))
    r = autenticado(client, cen.prof_a1).post(f"/api/diario/jornada/{antiga}", json={"evolucao_clinica": "x"})
    assert db_ctx.query_one("SELECT jornada_id FROM diarios_terapeuticos WHERE id = ?", (r.get_json()["id"],))["jornada_id"] == antiga


# ---------------------------------------------------------------- 10. iniciar jornada desfaz se falhar no meio

def test_iniciar_jornada_desfaz_o_que_criou_se_falhar(client, db_ctx, monkeypatch):
    from blueprints import jornada_bp
    cen = DuasClinicas()
    original = jornada_bp.execute

    def falha_nos_objetivos(sql, params=()):
        if "INSERT INTO objetivos_terapeuticos" in sql:
            raise RuntimeError("queda no meio")
        return original(sql, params)

    monkeypatch.setattr(jornada_bp, "execute", falha_nos_objetivos)
    with pytest.raises(RuntimeError):
        autenticado(client, cen.prof_a1).post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=INICIO)
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM jornadas")["n"] == 0
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM planos_terapeuticos")["n"] == 0


# ---------------------------------------------------------------- 13. ficha sem jornada no formato novo

def test_ficha_sem_jornada_no_formato_novo(client, db_ctx):
    cen = DuasClinicas()
    d = autenticado(client, cen.prof_a1).get(f"/api/jornada/paciente/{cen.paciente_a1}").get_json()
    assert "planos" not in d
    assert (d["planos_ativos"], d["missoes"], d["progresso_pct"], d["missoes_total"]) == ([], [], 0, 0)


# ---------------------------------------------------------------- 14. especialidades quase iguais

def test_especialidades_quase_iguais_viram_uma_so(client, db_ctx):
    from blueprints.jornada_bp import especialidades_disponiveis
    cen = DuasClinicas()
    db_ctx.execute("UPDATE organizacoes SET especialidades_json = '[\"Fonoaudiologia\"]' WHERE id = ?", (cen.org_a,))
    db_ctx.execute("UPDATE usuarios SET especialidade = 'fonoaudiologia ' WHERE id = ?", (cen.prof_a1["id"],))
    db_ctx.execute("UPDATE usuarios SET especialidade = 'Terapia  Ocupacional' WHERE id = ?", (cen.prof_a2["id"],))
    novo_usuario(cen.org_a, "Outra TO", "to2@a.com", "profissional", especialidade="terapia ocupacional")
    assert especialidades_disponiveis(cen.org_a) == ["Fonoaudiologia", "Terapia  Ocupacional"]


# ---------------------------------------------------------------- 15. isolamento entre clínicas (guarda)

def test_ficha_e_especialidades_nao_misturam_clinicas(client, db_ctx):
    from blueprints.jornada_bp import especialidades_disponiveis
    cen = DuasClinicas()
    db_ctx.execute("UPDATE usuarios SET especialidade = 'Musicoterapia' WHERE id = ?", (cen.prof_b1["id"],))
    assert "Musicoterapia" not in especialidades_disponiveis(cen.org_a)
    autenticado(client, cen.prof_a1).post(f"/api/jornada/paciente/{cen.paciente_a1}/iniciar", json=INICIO)
    assert autenticado(client, cen.gestor_b).get(f"/api/jornada/paciente/{cen.paciente_a1}").status_code == 403
