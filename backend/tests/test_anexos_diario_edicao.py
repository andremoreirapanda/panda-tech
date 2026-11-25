"""Anexos no Atender e no "Editar registro" do Diário (25/11/2026)."""
import base64
from datetime import timedelta

import ausencias_service

from factories import DuasClinicas, vincular_responsavel

from conftest import autenticado

PNG_VALIDO = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20).decode()


def _diario_com_anexo(db_ctx, paciente_id, autor_id):
    diario_id = db_ctx.execute(
        "INSERT INTO diarios_terapeuticos (paciente_id, profissional_id, evolucao_clinica, compartilhado_familia) VALUES (?, ?, ?, 1)",
        (paciente_id, autor_id, "Evolução"),
    )
    anexo_id = db_ctx.execute(
        "INSERT INTO diario_anexos (diario_id, tipo, nome_arquivo, conteudo_base64, tamanho_bytes) VALUES (?, 'foto', 'x.png', ?, 10)",
        (diario_id, PNG_VALIDO),
    )
    return diario_id, anexo_id


def _existe(db_ctx, anexo_id):
    return db_ctx.query_one("SELECT 1 FROM diario_anexos WHERE id = ?", (anexo_id,)) is not None


def test_autor_apaga_anexo(client, db_ctx):
    cen = DuasClinicas()
    _, anexo_id = _diario_com_anexo(db_ctx, cen.paciente_a1, cen.prof_a1["id"])
    r = autenticado(client, cen.prof_a1).delete(f"/api/diario/anexo/{anexo_id}")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert not _existe(db_ctx, anexo_id)


def test_gestor_apaga_anexo(client, db_ctx):
    cen = DuasClinicas()
    _, anexo_id = _diario_com_anexo(db_ctx, cen.paciente_a1, cen.prof_a1["id"])
    assert autenticado(client, cen.gestor_a).delete(f"/api/diario/anexo/{anexo_id}").status_code == 200
    assert not _existe(db_ctx, anexo_id)


def test_outro_profissional_nao_apaga(client, db_ctx):
    cen = DuasClinicas()
    _, anexo_id = _diario_com_anexo(db_ctx, cen.paciente_a1, cen.prof_a1["id"])
    assert autenticado(client, cen.prof_a2).delete(f"/api/diario/anexo/{anexo_id}").status_code == 403
    assert _existe(db_ctx, anexo_id)


def test_responsavel_nao_apaga(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    _, anexo_id = _diario_com_anexo(db_ctx, cen.paciente_a1, cen.prof_a1["id"])
    assert autenticado(client, cen.resp_a1).delete(f"/api/diario/anexo/{anexo_id}").status_code == 403
    assert _existe(db_ctx, anexo_id)


def test_outra_clinica_nao_apaga(client, db_ctx):
    cen = DuasClinicas()
    _, anexo_id = _diario_com_anexo(db_ctx, cen.paciente_a1, cen.prof_a1["id"])
    assert autenticado(client, cen.gestor_b).delete(f"/api/diario/anexo/{anexo_id}").status_code == 403
    assert _existe(db_ctx, anexo_id)


def test_anexo_inexistente(client, db_ctx):
    cen = DuasClinicas()
    assert autenticado(client, cen.gestor_a).delete("/api/diario/anexo/999999").status_code == 404


# ---------------------------------------------------------------- Atender

def _consulta(db_ctx, cen):
    hoje = ausencias_service.hoje_brasilia().isoformat()
    return db_ctx.execute(
        "INSERT INTO consultas (paciente_id, profissional_id, data_hora, duracao_min, status) VALUES (?, ?, ?, 50, 'agendada')",
        (cen.paciente_a1, cen.prof_a1["id"], f"{hoje} 09:00:00"),
    )


def test_atendimento_devolve_diario_id(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)
    cid = _consulta(db_ctx, cen)
    r = c.put(f"/api/agenda/{cid}/atendimento", json={"status": "realizada", "descricao": "Sessão boa"})
    assert r.status_code == 200, r.get_data(as_text=True)
    diario = db_ctx.query_one("SELECT id FROM diarios_terapeuticos WHERE consulta_id = ?", (cid,))
    assert r.get_json()["diario_id"] == diario["id"]
    # Editar de novo devolve o mesmo registro.
    assert c.put(f"/api/agenda/{cid}/atendimento", json={"status": "realizada", "descricao": "Corrigido"}).get_json()["diario_id"] == diario["id"]


def test_falta_sem_texto_devolve_diario_id_vazio(client, db_ctx):
    cen = DuasClinicas()
    cid = _consulta(db_ctx, cen)
    r = autenticado(client, cen.prof_a1).put(f"/api/agenda/{cid}/atendimento", json={"status": "faltou"})
    assert r.status_code == 200
    assert r.get_json()["diario_id"] is None


def test_get_atendimento_traz_anexos(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)
    cid = _consulta(db_ctx, cen)
    diario_id = c.put(f"/api/agenda/{cid}/atendimento", json={"status": "realizada", "descricao": "x"}).get_json()["diario_id"]
    assert c.post(f"/api/diario/{diario_id}/anexo", json={"tipo": "foto", "conteudo_base64": PNG_VALIDO,
                                                          "nome_arquivo": "sessao.png"}).status_code == 201
    anexos = c.get(f"/api/agenda/{cid}/atendimento").get_json()["diario"]["anexos"]
    assert [(a["tipo"], a["nome_arquivo"]) for a in anexos] == [("foto", "sessao.png")]
    assert "conteudo_base64" not in anexos[0]
