"""Pontos menores deixados nas revisões das partes 3b, A, B e C (09/10/2026)."""
from datetime import date, datetime, timedelta

import pytest

import ausencias_service
import procedimentos_service as ps
import recorrencia_service
from blueprints import agenda_bp
from factories import DuasClinicas, novo_usuario, vincular_responsavel
from conftest import autenticado


def _dia(delta):
    return (ausencias_service.hoje_brasilia() + timedelta(days=delta)).isoformat()


def _consulta(db_ctx, cen, prof=None, quando=None, status="agendada"):
    prof = prof or cen.prof_a1
    return db_ctx.execute("""INSERT INTO consultas (paciente_id, profissional_id, data_hora, duracao_min, status)
                             VALUES (?, ?, ?, 50, ?)""", (cen.paciente_a1, prof["id"], quando or f"{_dia(-1)} 09:00:00", status))


SALVAR = {"status": "realizada", "descricao": "Treino", "observacao": "", "familia": {"compartilhar": True}}


# ---------------------------------------------------------------- Procedimentos

@pytest.mark.parametrize("valor", [float("nan"), float("inf"), float("-inf")])
def test_valor_nao_finito_e_invalido(valor):
    assert ps.reais_para_centavos(valor) is None


def test_procedimento_id_booleano_e_invalido(db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("INSERT INTO procedimentos (id, organizacao_id, nome, valor_centavos) VALUES (1, ?, 'X', 1)", (cen.org_a,))
    assert ps.procedimento_valido(cen.org_a, True) is None
    assert ps.procedimento_valido(cen.org_a, 1)


@pytest.mark.parametrize("ativo,esperado", [(0, 0), ("0", 0), ("false", 0), (False, 0), (1, 1), (True, 1), (None, 1)])
def test_ativo_aceita_zero_e_texto(client, db_ctx, ativo, esperado):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).put("/api/procedimentos", json={"procedimentos": [{"nome": "S", "valor": 1, "ativo": ativo}]})
    assert r.status_code == 200
    assert db_ctx.query_one("SELECT ativo FROM procedimentos")["ativo"] == esperado


def test_nome_reservado_recusado(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).put("/api/procedimentos", json={"procedimentos": [{"nome": "__provisorio__9", "valor": 1}]})
    assert r.status_code == 400


def test_conflito_ao_gravar_vira_409(client, db_ctx, monkeypatch):
    cen = DuasClinicas()
    from blueprints import procedimentos_bp

    class IntegrityError(Exception):
        pass

    def falha(*a, **k):
        raise IntegrityError("unique")
    monkeypatch.setattr(procedimentos_bp, "execute", falha)
    r = autenticado(client, cen.gestor_a).put("/api/procedimentos", json={"procedimentos": [{"nome": "S", "valor": 1}]})
    assert r.status_code == 409 and "recarregue" in r.get_json()["erro"].lower()


def test_admin_master_agenda_sem_procedimento(client, db_ctx):
    cen = DuasClinicas()
    autenticado(client, cen.gestor_a).put("/api/procedimentos", json={"procedimentos": [{"nome": "S", "valor": 1}]})
    admin = novo_usuario(None, "Admin", "admin@x.com", "admin_master")
    r = autenticado(client, admin).post("/api/agenda", json={"paciente_id": cen.paciente_a1, "profissional_id": cen.prof_a1["id"],
                                                         "data_hora": f"{_dia(3)} 09:00:00", "duracao_min": 50})
    assert r.status_code == 201, r.get_data(as_text=True)


# ---------------------------------------------------------------- Repetição

def test_mensagem_da_data_limite_quando_nao_cabe():
    inicio = datetime(2026, 10, 12, 9, 0)
    with pytest.raises(ValueError, match="Até 26/10/2026"):
        recorrencia_service.gerar_datas({"frequencia": "semanal", "quantidade": 5, "data_limite": "2026-10-26"}, inicio)


# ---------------------------------------------------------------- Atender (3b)

def test_status_que_libera_horario_exclui_do_google(client, db_ctx, monkeypatch):
    cen = DuasClinicas()
    chamadas = []
    monkeypatch.setattr(agenda_bp, "sincronizar_consulta_google", lambda cid, org, acao: chamadas.append(acao))
    cid = _consulta(db_ctx, cen, quando=f"{_dia(2)} 09:00:00")
    c = autenticado(client, cen.prof_a1)
    for status in ("desmarcada_profissional", "falta_justificada", "cancelada"):
        assert c.put(f"/api/agenda/{cid}/status", json={"status": status}).status_code == 200
    assert chamadas == ["excluir", "excluir", "excluir"]


def test_atender_sincroniza_google(client, db_ctx, monkeypatch):
    cen = DuasClinicas()
    chamadas = []
    monkeypatch.setattr(agenda_bp, "sincronizar_consulta_google", lambda cid, org, acao: chamadas.append(acao))
    cid = _consulta(db_ctx, cen)
    c = autenticado(client, cen.prof_a1)
    c.put(f"/api/agenda/{cid}/atendimento", json=SALVAR)
    c.put(f"/api/agenda/{cid}/atendimento", json={"status": "falta_justificada"})
    assert chamadas == ["atualizar", "excluir"]


def test_atender_recusa_cancelada_e_finalizar_no_futuro(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)
    cancelada = _consulta(db_ctx, cen, status="cancelada")
    assert c.put(f"/api/agenda/{cancelada}/atendimento", json=SALVAR).status_code == 409
    futura = _consulta(db_ctx, cen, quando=f"{_dia(2)} 09:00:00")
    r = c.put(f"/api/agenda/{futura}/atendimento", json=SALVAR)
    assert r.status_code == 409 and "ainda não aconteceu" in r.get_json()["erro"]
    # desmarcar uma futura continua valendo
    assert c.put(f"/api/agenda/{futura}/atendimento", json={"status": "desmarcada_profissional"}).status_code == 200
    hoje = _consulta(db_ctx, cen, quando=f"{_dia(0)} 07:00:00")
    assert c.put(f"/api/agenda/{hoje}/atendimento", json=SALVAR).status_code == 200


def test_familia_avisada_quando_registro_passa_a_ser_compartilhado(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    cid = _consulta(db_ctx, cen)
    c = autenticado(client, cen.prof_a1)
    c.put(f"/api/agenda/{cid}/atendimento", json={"status": "faltou", "observacao": "Avisar a família"})
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM notificacoes WHERE usuario_id = ?", (cen.resp_a1["id"],))["n"] == 0
    c.put(f"/api/agenda/{cid}/atendimento", json=SALVAR)
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM notificacoes WHERE usuario_id = ?", (cen.resp_a1["id"],))["n"] == 1
    c.put(f"/api/agenda/{cid}/atendimento", json={**SALVAR, "descricao": "Outra"})
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM notificacoes WHERE usuario_id = ?", (cen.resp_a1["id"],))["n"] == 1


def test_editar_evolucao_e_do_autor_ou_gestor(client, db_ctx):
    cen = DuasClinicas()
    cid = _consulta(db_ctx, cen)
    autenticado(client, cen.prof_a1).put(f"/api/agenda/{cid}/atendimento", json=SALVAR)
    db_ctx.execute("UPDATE consultas SET profissional_id = ? WHERE id = ?", (cen.prof_a2["id"], cid))   # reatribuída
    novo = autenticado(client, cen.prof_a2)
    assert novo.get(f"/api/agenda/{cid}/atendimento").status_code == 200
    assert novo.put(f"/api/agenda/{cid}/atendimento", json={**SALVAR, "descricao": "Tentei"}).status_code == 403
    autor = autenticado(client, cen.prof_a1)
    assert autor.put(f"/api/agenda/{cid}/atendimento", json={**SALVAR, "descricao": "Autor corrigiu"}).status_code == 200
    assert autenticado(client, cen.gestor_a).put(f"/api/agenda/{cid}/atendimento", json={**SALVAR, "descricao": "Gestor"}).status_code == 200


def test_gravacao_simultanea_nao_duplica_nem_quebra(client, db_ctx, monkeypatch):
    cen = DuasClinicas()
    cid = _consulta(db_ctx, cen)
    c = autenticado(client, cen.prof_a1)
    c.put(f"/api/agenda/{cid}/atendimento", json=SALVAR)
    # simula a outra requisição que não viu o registro criado
    real, chamadas = agenda_bp._id_diario_da_consulta, []

    def primeira_vez_nada(consulta_id):
        chamadas.append(consulta_id)
        return None if len(chamadas) <= 2 else real(consulta_id)   # acesso + PUT não veem; depois do conflito, vê
    monkeypatch.setattr(agenda_bp, "_id_diario_da_consulta", primeira_vez_nada)
    r = c.put(f"/api/agenda/{cid}/atendimento", json={**SALVAR, "descricao": "Segunda"})
    assert r.status_code == 200, r.get_data(as_text=True)
    linhas = db_ctx.query("SELECT evolucao_clinica FROM diarios_terapeuticos WHERE consulta_id = ?", (cid,))
    assert [l["evolucao_clinica"] for l in linhas] == ["Segunda"]


def test_numero_da_sessao_com_hora_sem_zero(client, db_ctx):
    cen = DuasClinicas()
    _consulta(db_ctx, cen, quando=f"{_dia(-1)} 9:00:00", status="realizada")       # dado antigo, sem zero
    cid = _consulta(db_ctx, cen, quando=f"{_dia(-1)} 10:00:00")
    assert autenticado(client, cen.prof_a1).get(f"/api/agenda/{cid}/atendimento").get_json()["sessao_numero"] == 2


# ---------------------------------------------------------------- Diário

def test_aviso_do_diario_nao_leva_evolucao_para_a_familia(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    r = autenticado(client, cen.prof_a1).post(f"/api/diario/paciente/{cen.paciente_a1}", json={
        "evolucao_clinica": "Texto clínico sigiloso", "compartilhado_familia": True})
    assert r.status_code == 201, r.get_data(as_text=True)
    n = db_ctx.query_one("SELECT mensagem FROM notificacoes WHERE usuario_id = ?", (cen.resp_a1["id"],))
    assert n and "sigiloso" not in n["mensagem"]


def test_diario_com_consulta_ja_registrada_da_409(client, db_ctx):
    cen = DuasClinicas()
    cid = _consulta(db_ctx, cen)
    c = autenticado(client, cen.prof_a1)
    c.put(f"/api/agenda/{cid}/atendimento", json=SALVAR)
    r = c.post(f"/api/diario/paciente/{cen.paciente_a1}", json={"evolucao_clinica": "x", "consulta_id": cid})
    assert r.status_code == 409
