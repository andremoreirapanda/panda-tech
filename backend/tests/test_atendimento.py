"""Atender/Evoluir a partir da consulta (spec 08/10/2026)."""
from datetime import timedelta

import ausencias_service

from factories import DuasClinicas, novo_usuario, vincular_responsavel

from conftest import autenticado


def _dia(delta):
    # Mesma data do backend (Brasília): o CI roda em UTC, que vira o dia às 21h.
    return (ausencias_service.hoje_brasilia() + timedelta(days=delta)).isoformat()


def _consulta(db_ctx, cen, prof=None, quando=None, status="agendada", paciente=None):
    prof = prof or cen.prof_a1
    return db_ctx.execute("""INSERT INTO consultas (paciente_id, profissional_id, data_hora, duracao_min, status)
                             VALUES (?, ?, ?, 50, ?)""",
                          (paciente or cen.paciente_a1, prof["id"], quando or f"{_dia(0)} 09:00:00", status))


def _cenario(db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("UPDATE usuarios SET especialidade = 'Fonoaudiologia', tipo_registro = 'CRFa', numero_registro = '6-13059' WHERE id = ?",
                   (cen.prof_a1["id"],))
    db_ctx.execute("UPDATE usuarios SET especialidade = 'Terapia Ocupacional' WHERE id = ?", (cen.prof_a2["id"],))
    return cen


SALVAR = {"status": "realizada", "descricao": "Treino de /ʃ/ em frases", "observacao": "Orientado treino em casa",
          "familia": {"mensagem": "Foi ótimo!", "pontos_positivos": ["Participou"], "pontos_atencao": [],
                      "objetivo_semana": "Frases com 3 palavras", "compartilhar": True}}


# ---------------------------------------------------------------- permissões

def test_profissional_da_consulta_e_gestor_acessam(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _consulta(db_ctx, cen)
    assert autenticado(client, cen.prof_a1).get(f"/api/agenda/{cid}/atendimento").status_code == 200
    assert autenticado(client, cen.gestor_a).get(f"/api/agenda/{cid}/atendimento").status_code == 200


def test_outros_nao_acessam(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _consulta(db_ctx, cen)
    db_ctx.execute("UPDATE usuarios SET agenda_permissao_total = 1 WHERE id = ?", (cen.prof_a2["id"],))
    sec = novo_usuario(cen.org_a, "Secretária", "sec@a.com", "secretaria")
    for quem in (cen.prof_a2, sec):
        assert autenticado(client, quem).get(f"/api/agenda/{cid}/atendimento").status_code == 403
        assert autenticado(client, quem).put(f"/api/agenda/{cid}/atendimento", json=SALVAR).status_code == 403
    assert autenticado(client, cen.gestor_b).get(f"/api/agenda/{cid}/atendimento").status_code == 404
    assert autenticado(client, cen.prof_a1).get("/api/agenda/99999/atendimento").status_code == 404


# ---------------------------------------------------------------- GET: sessão, histórico, atraso

def test_sessao_conta_finalizadas_da_mesma_especialidade(client, db_ctx):
    cen = _cenario(db_ctx)
    _consulta(db_ctx, cen, quando=f"{_dia(-20)} 09:00:00", status="realizada")
    _consulta(db_ctx, cen, quando=f"{_dia(-13)} 09:00:00", status="realizada")
    _consulta(db_ctx, cen, quando=f"{_dia(-6)} 09:00:00", status="faltou")
    _consulta(db_ctx, cen, prof=cen.prof_a2, quando=f"{_dia(-5)} 09:00:00", status="realizada")  # outra especialidade
    cid = _consulta(db_ctx, cen)
    d = autenticado(client, cen.prof_a1).get(f"/api/agenda/{cid}/atendimento").get_json()
    assert d["sessao_numero"] == 3
    assert d["profissional"]["especialidade"] == "Fonoaudiologia" and d["profissional"]["numero_registro"] == "6-13059"
    assert d["paciente"]["nome"] == "Paciente A1"


def test_historico_traz_desfechos_mais_recentes_primeiro(client, db_ctx):
    cen = _cenario(db_ctx)
    c1 = _consulta(db_ctx, cen, quando=f"{_dia(-10)} 09:00:00", status="realizada")
    db_ctx.execute("""INSERT INTO diarios_terapeuticos (paciente_id, profissional_id, consulta_id, evolucao_clinica, observacao)
                      VALUES (?, ?, ?, 'Evolução antiga', 'Obs antiga')""", (cen.paciente_a1, cen.prof_a1["id"], c1))
    _consulta(db_ctx, cen, prof=cen.prof_a2, quando=f"{_dia(-3)} 09:00:00", status="falta_justificada")
    _consulta(db_ctx, cen, quando=f"{_dia(5)} 09:00:00", status="agendada")       # futura: fora
    _consulta(db_ctx, cen, quando=f"{_dia(-2)} 09:00:00", status="cancelada")     # desmarcada pela recepção: fora
    _consulta(db_ctx, cen, paciente=cen.paciente_a2, quando=f"{_dia(-1)} 09:00:00", status="realizada")  # outro paciente
    cid = _consulta(db_ctx, cen)
    hist = autenticado(client, cen.prof_a1).get(f"/api/agenda/{cid}/atendimento").get_json()["historico"]
    assert [(h["status"], h["especialidade"]) for h in hist] == [("falta_justificada", "Terapia Ocupacional"), ("realizada", "Fonoaudiologia")]
    assert hist[1]["descricao"] == "Evolução antiga" and hist[1]["observacao"] == "Obs antiga" and hist[1]["profissional_nome"] == "Prof A1"


def test_atraso_so_depois_de_mais_de_um_dia(client, db_ctx):
    cen = _cenario(db_ctx)
    c = autenticado(client, cen.prof_a1)
    atrasada = _consulta(db_ctx, cen, quando=f"{_dia(-6)} 11:10:00", status="confirmada")
    ontem = _consulta(db_ctx, cen, quando=f"{_dia(-1)} 11:10:00")
    feita = _consulta(db_ctx, cen, quando=f"{_dia(-6)} 15:00:00", status="realizada")
    assert c.get(f"/api/agenda/{atrasada}/atendimento").get_json()["atraso_dias"] == 6
    assert c.get(f"/api/agenda/{ontem}/atendimento").get_json()["atraso_dias"] == 0
    assert c.get(f"/api/agenda/{feita}/atendimento").get_json()["atraso_dias"] == 0


# ---------------------------------------------------------------- PUT: salvar

def test_salvar_finalizado_cria_registro_no_diario(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _consulta(db_ctx, cen, quando=f"{_dia(-1)} 09:00:00")
    r = autenticado(client, cen.prof_a1).put(f"/api/agenda/{cid}/atendimento", json=SALVAR)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert db_ctx.query_one("SELECT status FROM consultas WHERE id = ?", (cid,))["status"] == "realizada"
    d = db_ctx.query_one("SELECT * FROM diarios_terapeuticos WHERE consulta_id = ?", (cid,))
    assert (d["evolucao_clinica"], d["observacao"], d["mensagem_familia"], d["paciente_id"], d["profissional_id"], d["data_atendimento"]) == (
        "Treino de /ʃ/ em frases", "Orientado treino em casa", "Foi ótimo!", cen.paciente_a1, cen.prof_a1["id"], _dia(-1))
    lista = autenticado(client, cen.prof_a1).get("/api/agenda").get_json()
    assert next(c for c in lista if c["id"] == cid)["diario_id"] == d["id"]


def test_validacoes_do_salvar(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _consulta(db_ctx, cen)
    c = autenticado(client, cen.prof_a1)
    assert c.put(f"/api/agenda/{cid}/atendimento", json={**SALVAR, "descricao": "  "}).status_code == 400
    assert c.put(f"/api/agenda/{cid}/atendimento", json={**SALVAR, "status": "agendada"}).status_code == 400
    assert c.put(f"/api/agenda/{cid}/atendimento", json={"status": "faltou"}).status_code == 200


def test_salvar_de_novo_atualiza_o_mesmo_registro_e_audita(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _consulta(db_ctx, cen)
    c = autenticado(client, cen.prof_a1)
    c.put(f"/api/agenda/{cid}/atendimento", json=SALVAR)
    assert c.put(f"/api/agenda/{cid}/atendimento", json={**SALVAR, "descricao": "Corrigido"}).status_code == 200
    linhas = db_ctx.query("SELECT evolucao_clinica FROM diarios_terapeuticos WHERE consulta_id = ?", (cid,))
    assert [l["evolucao_clinica"] for l in linhas] == ["Corrigido"]
    assert db_ctx.query_one("SELECT 1 FROM auditoria WHERE entidade = 'atendimento' AND entidade_id = ? AND acao = 'editar'", (cid,))
    reaberto = c.get(f"/api/agenda/{cid}/atendimento").get_json()["diario"]
    assert reaberto["evolucao_clinica"] == "Corrigido" and reaberto["observacao"] == "Orientado treino em casa"


def test_falta_sem_texto_nao_cria_registro(client, db_ctx):
    cen = _cenario(db_ctx)
    cid = _consulta(db_ctx, cen)
    autenticado(client, cen.prof_a1).put(f"/api/agenda/{cid}/atendimento", json={"status": "falta_justificada"})
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM diarios_terapeuticos")["n"] == 0
    assert db_ctx.query_one("SELECT status FROM consultas WHERE id = ?", (cid,))["status"] == "falta_justificada"


def test_familia_notificada_so_na_criacao_e_nao_ve_evolucao_nem_observacao(client, db_ctx):
    cen = _cenario(db_ctx)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    cid = _consulta(db_ctx, cen)
    c = autenticado(client, cen.prof_a1)
    c.put(f"/api/agenda/{cid}/atendimento", json=SALVAR)
    c.put(f"/api/agenda/{cid}/atendimento", json={**SALVAR, "descricao": "Corrigido"})
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM notificacoes WHERE usuario_id = ? AND tipo = 'diario'",
                            (cen.resp_a1["id"],))["n"] == 1
    lista = autenticado(client, cen.resp_a1).get(f"/api/diario/paciente/{cen.paciente_a1}").get_json()
    assert len(lista) == 1 and lista[0]["evolucao_clinica"] is None and lista[0].get("observacao") is None
    assert lista[0]["mensagem_familia"] == "Foi ótimo!"
