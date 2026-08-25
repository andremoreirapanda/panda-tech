"""
Regressão de isolamento entre clínicas (IDOR) para o Financeiro (Módulo 07)
— cobrança, listagem, geração de PIX e confirmação de pagamento nunca podem
atravessar clínicas. Ver também o comentário de correção de segurança em
financeiro_bp.py::registrar_pagamento (a família não pode mais se
autoconfirmar como "pago").
"""
from factories import DuasClinicas, vincular_responsavel

from conftest import autenticado


def _duas_clinicas_com_financeiro(db_ctx):
    """DuasClinicas() nasce no plano 'premium', que não libera nenhum módulo
    opcional (ver modulos_service.MODULOS_POR_PLANO) — troca para 'pro' nas
    duas organizações para exercitar o Financeiro de verdade, e não um 403
    de "módulo desabilitado" mascarando o teste de isolamento."""
    cen = DuasClinicas()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id IN (?, ?)", (cen.org_a, cen.org_b))
    return cen


def _criar_cobranca(db_ctx, paciente_id, valor=10000):
    return db_ctx.execute(
        "INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento) VALUES (?, ?, ?, ?)",
        (paciente_id, "Mensalidade", valor, "2026-09-10"),
    )


def test_gestor_cria_cobranca_para_paciente_da_propria_clinica(client, db_ctx):
    cen = _duas_clinicas_com_financeiro(db_ctx)
    r = autenticado(client, cen.gestor_a).post("/api/financeiro/cobranca", json={
        "paciente_id": cen.paciente_a1, "descricao": "Mensalidade", "valor_centavos": 15000, "vencimento": "2026-09-10",
    })
    assert r.status_code == 201, r.get_data(as_text=True)


def test_gestor_nao_cria_cobranca_para_paciente_de_outra_clinica(client, db_ctx):
    cen = _duas_clinicas_com_financeiro(db_ctx)
    r = autenticado(client, cen.gestor_b).post("/api/financeiro/cobranca", json={
        "paciente_id": cen.paciente_a1, "descricao": "Mensalidade", "valor_centavos": 15000, "vencimento": "2026-09-10",
    })
    assert r.status_code == 403, r.get_data(as_text=True)


def test_gestor_de_outra_clinica_nao_lista_cobrancas(client, db_ctx):
    cen = _duas_clinicas_com_financeiro(db_ctx)
    _criar_cobranca(db_ctx, cen.paciente_a1)
    r = autenticado(client, cen.gestor_b).get(f"/api/financeiro/paciente/{cen.paciente_a1}")
    assert r.status_code == 403, r.get_data(as_text=True)


def test_gestor_da_mesma_clinica_lista_cobrancas_normalmente(client, db_ctx):
    cen = _duas_clinicas_com_financeiro(db_ctx)
    _criar_cobranca(db_ctx, cen.paciente_a1)
    r = autenticado(client, cen.gestor_a).get(f"/api/financeiro/paciente/{cen.paciente_a1}")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert len(r.get_json()) == 1


def test_gestor_de_outra_clinica_nao_gera_pix(client, db_ctx):
    cen = _duas_clinicas_com_financeiro(db_ctx)
    cobranca_id = _criar_cobranca(db_ctx, cen.paciente_a1)
    r = autenticado(client, cen.gestor_b).post(f"/api/financeiro/cobranca/{cobranca_id}/gerar-pix")
    assert r.status_code == 403, r.get_data(as_text=True)


def test_gestor_de_outra_clinica_nao_confirma_pagamento(client, db_ctx):
    cen = _duas_clinicas_com_financeiro(db_ctx)
    cobranca_id = _criar_cobranca(db_ctx, cen.paciente_a1)
    r = autenticado(client, cen.gestor_b).post(f"/api/financeiro/cobranca/{cobranca_id}/pagar", json={"forma": "dinheiro"})
    assert r.status_code == 403, r.get_data(as_text=True)
    cobranca = db_ctx.query_one("SELECT status FROM cobrancas WHERE id = ?", (cobranca_id,))
    assert cobranca["status"] == "pendente"


def test_gestor_da_mesma_clinica_confirma_pagamento_normalmente(client, db_ctx):
    cen = _duas_clinicas_com_financeiro(db_ctx)
    cobranca_id = _criar_cobranca(db_ctx, cen.paciente_a1)
    r = autenticado(client, cen.gestor_a).post(f"/api/financeiro/cobranca/{cobranca_id}/pagar", json={"forma": "dinheiro"})
    assert r.status_code == 200, r.get_data(as_text=True)
    cobranca = db_ctx.query_one("SELECT status FROM cobrancas WHERE id = ?", (cobranca_id,))
    assert cobranca["status"] == "pago"


def test_responsavel_nao_confirma_o_proprio_pagamento(client, db_ctx):
    """Regressão da correção de segurança desta rodada: antes, `paciente_acessivel()`
    também liberava responsável, permitindo à própria família se autoconfirmar
    como "pago" sem pagar nada de verdade."""
    cen = _duas_clinicas_com_financeiro(db_ctx)
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    cobranca_id = _criar_cobranca(db_ctx, cen.paciente_a1)
    r = autenticado(client, cen.resp_a1).post(f"/api/financeiro/cobranca/{cobranca_id}/pagar", json={"forma": "dinheiro"})
    assert r.status_code == 403, r.get_data(as_text=True)
    cobranca = db_ctx.query_one("SELECT status FROM cobrancas WHERE id = ?", (cobranca_id,))
    assert cobranca["status"] == "pendente"
