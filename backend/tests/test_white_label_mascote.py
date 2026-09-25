"""White Label completo (25/09/2026): mascote padrão da clínica para pacientes novos."""
import base64

import db
from factories import DuasClinicas, vincular_responsavel
from conftest import autenticado
from modulos_service import definir_liberacao_admin
from blueprints.pessoas_bp import criar_paciente_core

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def _masc(pid):
    return db.query_one("SELECT avatar_mascote FROM pacientes WHERE id = ?", (pid,))["avatar_mascote"]


def test_sem_escolha_usa_mascote_da_clinica_so_com_modulo(db_ctx):
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET mundo_mascote = '🦊' WHERE id = ?", (cen.org_a,))
    assert _masc(criar_paciente_core(cen.org_a, "Sem módulo", "2019-01-01")) == "🐻"
    definir_liberacao_admin(cen.org_a, "white_label", True)
    assert _masc(criar_paciente_core(cen.org_a, "Com módulo", "2019-01-01")) == "🦊"
    assert _masc(criar_paciente_core(cen.org_a, "Escolheu", "2019-01-01", avatar_mascote="🐸")) == "🐸"


def test_cadastro_pela_rota_sem_mascote_usa_o_da_clinica(client, db_ctx):
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET mundo_mascote = '🦁' WHERE id = ?", (cen.org_a,))
    definir_liberacao_admin(cen.org_a, "white_label", True)
    r = autenticado(client, cen.gestor_a).post("/api/pessoas/pacientes", json={
        "nome": "Nova Criança", "data_nascimento": "2019-05-05"})
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    pid = db.query_one("SELECT id FROM pacientes WHERE nome = 'Nova Criança'")["id"]
    assert _masc(pid) == "🦁"


def test_mascote_clinica_so_com_imagem_e_modulo(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    rota = f"/api/pessoas/pacientes/{cen.paciente_a1}/mascote"
    assert autenticado(client, cen.resp_a1).put(rota, json={"avatar_mascote": "clinica"}).status_code == 400
    db.execute("UPDATE organizacoes SET mundo_mascote_imagem = ? WHERE id = ?", (PNG, cen.org_a))
    assert autenticado(client, cen.resp_a1).put(rota, json={"avatar_mascote": "clinica"}).status_code == 400
    definir_liberacao_admin(cen.org_a, "white_label", True)
    assert autenticado(client, cen.resp_a1).put(rota, json={"avatar_mascote": "clinica"}).status_code == 200
    assert _masc(cen.paciente_a1) == "clinica"
    assert criar_paciente_core(cen.org_a, "X", "2019-01-01", avatar_mascote="clinica")
    assert _masc(db.query_one("SELECT id FROM pacientes WHERE nome = 'X'")["id"]) == "clinica"


def test_mascote_clinica_de_outra_clinica_nao_vale(client, db_ctx):
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET mundo_mascote_imagem = ? WHERE id = ?", (PNG, cen.org_a))
    definir_liberacao_admin(cen.org_a, "white_label", True)
    pid = criar_paciente_core(cen.org_b, "Y", "2019-01-01", avatar_mascote="clinica")
    assert _masc(pid) == "🐻"
