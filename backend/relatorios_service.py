"""Relatórios do Financeiro (seção 6.5 da spec, 23/11/2026). Só leitura sobre o que a etapa 1 grava.

- `extrato_paciente`: sessão por sessão (data, procedimento, valor e em que cobrança/pacote/mensalidade
  ela está), as cobranças e os pagamentos do período e os totais. É um documento para a família:
  nunca leva repasse, anotação interna da cobrança (`revisar_motivo`) nem texto clínico.
- `em_aberto`, `acabando`, `sem_acordo`: relatórios da clínica (só gestor).
"""
from datetime import date

from db import query, query_one
import acordos_service
import ausencias_service
import cobranca_regras as regras

STATUS_COBRANCA = {"pendente": "em aberto", "parcial": "paga em parte", "pago": "paga", "vencido": "vencida",
                   "rascunho": "em conferência", "cancelado": "cancelada"}
ABERTAS = ("pendente", "parcial", "vencido")


def _hoje(hoje):
    return hoje or ausencias_service.hoje_brasilia().isoformat()


def _mm_aaaa(dia):
    return f"{dia[5:7]}/{dia[:4]}"


def _pago_por_cobranca(ids):
    if not ids:
        return {}
    marc = ", ".join("?" for _ in ids)
    saida = {}
    for r in query(f"""SELECT cobranca_id, COALESCE(SUM(valor_centavos), 0) AS total FROM pagamentos
                       WHERE cobranca_id IN ({marc}) AND estornado_em IS NULL GROUP BY cobranca_id""", tuple(ids)):
        saida[r["cobranca_id"]] = int(r["total"] or 0)
    return saida


def _cobranca_publica(c, pago):
    a_pagar = int(c["valor_centavos"] or 0) - int(c["desconto_centavos"] or 0)
    return {"id": c["id"], "descricao": c["descricao"], "vencimento": c["vencimento"], "status": c["status"],
            "a_pagar_centavos": a_pagar, "pago_centavos": pago, "saldo_centavos": max(0, a_pagar - pago)}


# ------------------------------------------------------------------ extrato do paciente

def _sessoes_do_extrato(org_id, paciente_id, de, ate, hoje):
    org = query_one("SELECT fin_cobrar_falta, fin_cobrar_desde FROM organizacoes WHERE id = ?", (org_id,))
    cobrar_falta = bool(org and org["fin_cobrar_falta"])
    corte = str(org["fin_cobrar_desde"])[:10] if org and org["fin_cobrar_desde"] else None
    fim = min(ate, hoje)
    linhas = query(
        """SELECT c.id AS consulta_id, c.data_hora, c.status, c.especialidade, c.procedimento_valor_centavos,
                  prof.nome AS profissional_nome, pr.nome AS procedimento_nome,
                  i.valor_centavos AS item_valor, cb.descricao AS cobranca_descricao, cb.status AS cobranca_status,
                  pc.numero AS pacote_numero, ap.sessoes_total AS pacote_total,
                  dn.decisao AS decisao, v.acordo_id AS vinculo_acordo_id, v.incluida AS vinculo_incluida
           FROM consultas c
           JOIN pacientes p ON p.id = c.paciente_id
           JOIN usuarios prof ON prof.id = c.profissional_id
           LEFT JOIN procedimentos pr ON pr.id = c.procedimento_id
           LEFT JOIN cobranca_itens i ON i.consulta_id = c.id
           LEFT JOIN cobrancas cb ON cb.id = i.cobranca_id
           LEFT JOIN acordo_pacote_consumo pc ON pc.consulta_id = c.id
           LEFT JOIN acordos_pagamento ap ON ap.id = pc.acordo_id
           LEFT JOIN consulta_decisao_cobranca dn ON dn.consulta_id = c.id AND dn.decisao = 'nao_cobrar'
           LEFT JOIN consulta_acordo_incluida v ON v.consulta_id = c.id
           WHERE p.organizacao_id = ? AND c.paciente_id = ? AND c.status IN ('realizada', 'faltou')
             AND substr(c.data_hora, 1, 10) BETWEEN ? AND ?""",
        (org_id, paciente_id, de, fim))
    acordos = acordos_service.acordos_por_paciente(org_id, paciente_id).get(paciente_id, [])
    saida = []
    for r in linhas:
        dia = str(r["data_hora"])[:10]
        valor = int(r["procedimento_valor_centavos"] or 0)
        if r["item_valor"] is not None:
            status = STATUS_COBRANCA.get(r["cobranca_status"], r["cobranca_status"] or "")
            situacao = f"Cobrança: {r['cobranca_descricao'] or ''} ({status})"
            valor = int(r["item_valor"] or 0)
        elif r["pacote_numero"] is not None:
            situacao = f"Pacote: sessão {r['pacote_numero']} de {r['pacote_total'] or '?'}"
        elif r["status"] == "faltou" and not cobrar_falta:
            continue                                   # falta que não gera cobrança fica fora
        elif r["decisao"] == "nao_cobrar" or (corte and dia < corte):
            situacao = "Não cobrada"
        else:
            esp = regras.normalizar_especialidade(r["especialidade"])
            a = acordos_service.acordo_da_sessao(acordos, esp, dia, dict(r))
            if a and a["tipo"] == "mensalidade":
                situacao = f"Mensalidade {_mm_aaaa(dia)}"
            elif a:
                situacao = "Aguardando cobrança"
            else:
                situacao = "Sem acordo"
        saida.append({"consulta_id": r["consulta_id"], "data_hora": r["data_hora"],
                      "especialidade": r["especialidade"], "profissional_nome": r["profissional_nome"],
                      "procedimento_nome": r["procedimento_nome"], "valor_centavos": valor, "situacao": situacao})
    saida.sort(key=lambda s: acordos_service.chave_data_hora(s["data_hora"], s["consulta_id"]))
    return saida


def extrato_paciente(org_id, paciente_id, de, ate, hoje=None):
    hoje = _hoje(hoje)
    p = query_one("SELECT id, nome, data_nascimento FROM pacientes WHERE id = ? AND organizacao_id = ?",
                  (paciente_id, org_id))
    if not p:
        raise LookupError("Paciente não encontrado.")
    sessoes = _sessoes_do_extrato(org_id, paciente_id, de, ate, hoje)

    todas = query("""SELECT id, descricao, vencimento, status, valor_centavos, desconto_centavos FROM cobrancas
                     WHERE paciente_id = ? AND COALESCE(organizacao_id, ?) = ?
                       AND status NOT IN ('rascunho', 'cancelado')
                     ORDER BY vencimento, id""", (paciente_id, org_id, org_id))
    pagos = _pago_por_cobranca([c["id"] for c in todas])
    publicas = {c["id"]: _cobranca_publica(c, pagos.get(c["id"], 0)) for c in todas}
    cobrancas = [publicas[c["id"]] for c in todas if de <= str(c["vencimento"] or "")[:10] <= ate]
    saldo_aberto = sum(publicas[c["id"]]["saldo_centavos"] for c in todas if c["status"] in ABERTAS)

    pagamentos = [{"id": r["id"], "pago_em": r["pago_em"], "forma": r["forma"], "valor_centavos": r["valor_centavos"],
                   "cobranca_descricao": r["descricao"], "estornado": bool(r["estornado_em"])}
                  for r in query("""SELECT pg.id, pg.pago_em, pg.forma, pg.valor_centavos, pg.estornado_em, cb.descricao
                                    FROM pagamentos pg JOIN cobrancas cb ON cb.id = pg.cobranca_id
                                    WHERE cb.paciente_id = ? AND COALESCE(cb.organizacao_id, ?) = ?
                                      AND substr(pg.pago_em, 1, 10) BETWEEN ? AND ?
                                    ORDER BY pg.pago_em, pg.id""", (paciente_id, org_id, org_id, de, ate))]
    return {
        "paciente": {"id": p["id"], "nome": p["nome"], "nascimento": p["data_nascimento"]},
        "de": de, "ate": ate,
        "sessoes": sessoes, "cobrancas": cobrancas, "pagamentos": pagamentos,
        "totais": {"cobrado_centavos": sum(c["a_pagar_centavos"] for c in cobrancas),
                   "pago_centavos": sum(x["valor_centavos"] for x in pagamentos if not x["estornado"]),
                   "saldo_aberto_centavos": saldo_aberto},
    }


def periodo_padrao_extrato(hoje):
    """Últimos 3 meses até hoje."""
    h = date.fromisoformat(hoje)
    m = h.month - 3
    ano, mes = (h.year, m) if m >= 1 else (h.year - 1, m + 12)
    dia = min(h.day, [31, 29 if ano % 4 == 0 and (ano % 100 or ano % 400 == 0) else 28, 31, 30, 31, 30,
                      31, 31, 30, 31, 30, 31][mes - 1])
    return date(ano, mes, dia).isoformat(), hoje
