"""Planos configuráveis (25/09/2026): módulos por plano vêm do banco, com
herança viva, e extras por clínica valem para qualquer módulo."""
import db
import planos_padrao
from factories import DuasClinicas
from modulos_service import (modulos_do_plano, modulos_habilitados_clinica, modulo_ativo_para_clinica,
                             definir_liberacao_admin)


def _plano(codigo, base=None, modulos=()):
    base_id = db.query_one("SELECT id FROM planos WHERE codigo = ?", (base,))["id"] if base else None
    pid = db.execute("INSERT INTO planos (codigo, nome, preco_mensal_centavos, plano_base_id) VALUES (?, ?, 0, ?)",
                     (codigo, codigo.title(), base_id))
    for m in modulos:
        db.execute("INSERT INTO planos_modulos (plano_id, modulo_codigo) VALUES (?, ?)", (pid, m))
    return pid


def test_heranca_em_cadeia_e_viva(db_ctx):
    a = _plano("a", modulos=["financeiro"])
    _plano("b", base="a", modulos=["integracoes"])
    _plano("c", base="b", modulos=["pandoo"])
    assert modulos_do_plano("c") == ["financeiro", "integracoes", "pandoo"]
    db.execute("INSERT INTO planos_modulos (plano_id, modulo_codigo) VALUES (?, 'white_label')", (a,))
    assert "white_label" in modulos_do_plano("c")  # mudou a base → mudou o neto na hora


def test_ciclo_no_banco_nao_trava(db_ctx):
    a = _plano("a", modulos=["financeiro"])
    b = _plano("b", base="a", modulos=["integracoes"])
    db.execute("UPDATE planos SET plano_base_id = ? WHERE id = ?", (b, a))  # ciclo forçado direto no banco
    assert modulos_do_plano("a") == ["financeiro", "integracoes"]


def test_plano_inexistente_nao_libera_nada(db_ctx):
    assert modulos_do_plano("nao-existe") == []


def test_clinica_recebe_modulos_do_plano_e_extras(db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET plano = 'starter' WHERE id = ?", (cen.org_a,))
    assert modulos_habilitados_clinica(cen.org_a, "starter") == set()
    definir_liberacao_admin(cen.org_a, "financeiro", True)
    assert modulo_ativo_para_clinica(cen.org_a, "starter", "financeiro")
    definir_liberacao_admin(cen.org_a, "financeiro", False)
    assert not modulo_ativo_para_clinica(cen.org_a, "starter", "financeiro")


def test_gestor_desligou_modulo_do_plano(db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    assert modulo_ativo_para_clinica(cen.org_a, "pro", "integracoes")
    db.execute("UPDATE modulos_clinica SET habilitado = 0 WHERE organizacao_id = ? AND modulo_codigo = 'integracoes'", (cen.org_a,))
    assert not modulo_ativo_para_clinica(cen.org_a, "pro", "integracoes")
