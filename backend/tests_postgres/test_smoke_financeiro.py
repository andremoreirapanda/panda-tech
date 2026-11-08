"""
Teste de fumaça do Financeiro (cobrança das famílias) contra Postgres REAL: o
caminho acordo → sincronizar → liberar → pagar → estornar → cancelar, mais o que
a revisão final acrescentou (sessão incluída, status de origem, fim da mensalidade,
desconto, webhook do QR anterior). Só para pegar o que quebra no dialeto do Postgres
(RETURNING id, tradução de `?`, transação abortada por uma instrução com erro);
as regras em si estão em tests/test_cobranca_*.py e tests/test_financeiro_revisao_final.py.
Como rodar: ver o cabeçalho de test_smoke_fluxo_principal.py.
"""
import uuid
from datetime import timedelta

import ausencias_service
import cobranca_service
import db
import pagamento_service
import planos_padrao

from conftest import autenticado, REQUER_POSTGRES

pytestmark = REQUER_POSTGRES

HOJE = ausencias_service.hoje_brasilia()


def _dia(dias_atras):
    return (HOJE - timedelta(days=dias_atras)).isoformat()


def _usuario(db_ctx, org_id, nome, papel, especialidade=None):
    import auth
    senha_hash, salt = auth.hash_senha("senhateste123")
    uid = db_ctx.execute(
        "INSERT INTO usuarios (organizacao_id, nome, email, senha_hash, senha_salt, papel, especialidade) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (org_id, nome, f"{uuid.uuid4().hex}@smoke-financeiro.com", senha_hash, salt, papel, especialidade))
    return db_ctx.query_one("SELECT * FROM usuarios WHERE id = ?", (uid,))


def _sessao(db_ctx, paciente, prof, proc, dias_atras, status="realizada", valor=15000):
    return db_ctx.execute(
        """INSERT INTO consultas (paciente_id, profissional_id, data_hora, status, especialidade,
                                  procedimento_id, procedimento_valor_centavos)
           VALUES (?, ?, ?, ?, 'Fonoaudiologia', ?, ?)""",
        (paciente, prof["id"], f"{_dia(dias_atras)} 09:00:00", status, proc, valor))


class _SDK:
    def __init__(self, referencia):
        self.referencia = referencia

    def payment(self):
        return self

    def get(self, payment_id, opcoes=None):
        return {"response": {"status": "approved", "transaction_amount": 10.0, "external_reference": self.referencia,
                             "date_approved": f"{_dia(0)}T10:00:00.000-03:00"}}


def test_financeiro_contra_postgres(client, db_ctx, monkeypatch):
    planos_padrao.criar_planos_padrao_para_teste()
    org = db_ctx.execute("INSERT INTO organizacoes (nome, plano) VALUES (?, 'pro')", (f"Smoke {uuid.uuid4().hex}",))
    gestor = _usuario(db_ctx, org, "Gestora", "gestor")
    prof = _usuario(db_ctx, org, "Prof", "profissional", "Fonoaudiologia")
    paciente = db_ctx.execute("INSERT INTO pacientes (organizacao_id, nome, data_nascimento) VALUES (?, 'Pac', '2019-01-01')", (org,))
    outro = db_ctx.execute("INSERT INTO pacientes (organizacao_id, nome, data_nascimento) VALUES (?, 'Outro', '2019-01-01')", (org,))
    terceiro = db_ctx.execute("INSERT INTO pacientes (organizacao_id, nome, data_nascimento) VALUES (?, 'Terceiro', '2019-01-01')", (org,))
    proc = db_ctx.execute("INSERT INTO procedimentos (organizacao_id, nome, valor_centavos) VALUES (?, 'Sessão', 15000)", (org,))
    g = autenticado(client, gestor)

    # ---- acordo por período com sessão incluída e outra deixada de fora
    incluida = _sessao(db_ctx, paciente, prof, proc, 70)
    de_fora = _sessao(db_ctx, paciente, prof, proc, 69)
    r = g.post(f"/api/financeiro/paciente/{paciente}/acordos", json={
        "tipo": "avulsa", "ciclo": "mensal", "especialidade": "Fonoaudiologia", "inicio": _dia(100),
        "incluir_consultas": [incluida]})
    assert r.status_code == 201, r.get_data(as_text=True)

    # ---- sincronizar (a tela sincroniza ao abrir) e sem duplicar
    r = g.get("/api/financeiro/cobrancas")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert cobranca_service.sincronizar(org) == {"criadas": 0, "itens": 0, "revisar": 0}
    [rascunho] = [c for c in r.get_json()["cobrancas"] if c["paciente_id"] == paciente and c["status"] == "rascunho"]
    assert [i["consulta_id"] for i in rascunho["itens"]] == [incluida]
    r = g.get(f"/api/financeiro/paciente/{paciente}/sem-acordo")
    assert [s["consulta_id"] for s in r.get_json()] == [de_fora]
    assert g.get("/api/financeiro/pendencias").status_code == 200

    # ---- conferir → liberar → pagar → estornar → desconto → cancelar
    cid = rascunho["id"]
    r = g.put(f"/api/financeiro/cobranca/{cid}/conferir", json={"desconto_centavos": 1000, "desconto_motivo": "Combinado"})
    assert r.status_code == 200, r.get_data(as_text=True)
    r = g.post(f"/api/financeiro/cobranca/{cid}/liberar")
    assert r.status_code == 200 and r.get_json()["status"] == "pendente", r.get_data(as_text=True)
    r = g.post(f"/api/financeiro/cobranca/{cid}/pagar", json={"forma": "pix", "valor_centavos": 5000})
    assert r.status_code == 200 and r.get_json()["status"] == "parcial", r.get_data(as_text=True)
    pagamento = r.get_json()["pagamento_id"]
    r = g.post(f"/api/financeiro/pagamento/{pagamento}/estornar", json={"motivo": "Lançado errado"})
    assert r.status_code == 200, r.get_data(as_text=True)
    r = g.post(f"/api/financeiro/cobranca/{cid}/desconto", json={"desconto_centavos": 2000, "desconto_motivo": "Ajuste"})
    assert r.status_code == 200, r.get_data(as_text=True)
    r = g.post(f"/api/financeiro/cobranca/{cid}/cancelar", json={"motivo": "Teste"})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert g.get("/api/indicadores/gestor").status_code == 200

    # ---- recebido filtrado por especialidade
    r = g.get("/api/financeiro/cobrancas?especialidade=Fonoaudiologia")
    assert r.status_code == 200, r.get_data(as_text=True)

    # ---- mensalidade: o fim mexe na cobrança do mês
    r = g.post(f"/api/financeiro/paciente/{outro}/acordos", json={
        "tipo": "mensalidade", "especialidade": "Fonoaudiologia", "valor_centavos": 80000, "dia_vencimento": 10,
        "inicio": HOJE.replace(day=1).isoformat()})
    assert r.status_code == 201, r.get_data(as_text=True)
    mensalidade = r.get_json()["id"]
    cobranca_service.sincronizar(org)
    r = g.post(f"/api/financeiro/acordos/{mensalidade}/encerrar", json={"fim": HOJE.isoformat()})
    assert r.status_code == 200, r.get_data(as_text=True)

    # ---- pacote: consumo, volta atrás por status de origem e edição da data
    db_ctx.execute("UPDATE organizacoes SET fin_cobrar_falta = 1 WHERE id = ?", (org,))
    r = g.post(f"/api/financeiro/paciente/{terceiro}/acordos", json={
        "tipo": "pacote", "especialidade": "Fonoaudiologia", "sessoes_total": 1, "valor_centavos": 10000, "parcelas": 1,
        "primeiro_vencimento": (HOJE + timedelta(days=5)).isoformat(), "inicio": _dia(30)})
    assert r.status_code == 201, r.get_data(as_text=True)
    falta = _sessao(db_ctx, terceiro, prof, proc, 3, status="faltou")
    cobranca_service.sincronizar(org)
    assert db.query_one("SELECT status_origem FROM acordo_pacote_consumo WHERE consulta_id = ?", (falta,))["status_origem"] == "faltou"
    r = g.put(f"/api/agenda/{falta}", json={"data_hora": f"{_dia(4)} 09:00:00"})
    assert r.status_code == 200, r.get_data(as_text=True)
    # pacote esgotado: o acordo novo encerra o velho
    r = g.post(f"/api/financeiro/paciente/{terceiro}/acordos", json={
        "tipo": "avulsa", "ciclo": "consulta", "especialidade": "Fonoaudiologia"})
    assert r.status_code == 201, r.get_data(as_text=True)
    avulsa = _sessao(db_ctx, terceiro, prof, proc, 0)
    cobranca_service.sincronizar(org)
    item = db.query_one("SELECT cobranca_id, status_origem FROM cobranca_itens WHERE consulta_id = ?", (avulsa,))
    assert item["status_origem"] == "realizada"

    # ---- webhook do QR anterior: acha pela referência e grava a data de Brasília
    monkeypatch.setattr(pagamento_service, "_sdk", lambda o: _SDK(f"cobranca-{item['cobranca_id']}"))
    resultado = pagamento_service.processar_webhook(f"qr-velho-{uuid.uuid4().hex}", org)
    assert resultado.get("status") == "parcial", resultado
    pg = db.query_one("SELECT pago_em FROM pagamentos WHERE cobranca_id = ?", (item["cobranca_id"],))
    assert pg["pago_em"] == f"{_dia(0)} 12:00:00"
