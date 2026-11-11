"""Fechamento de caixa da clínica (Financeiro, etapa 2 — 09/11/2026).

Relatório de conferência, só leitura sobre `pagamentos`:
- Recebido = pagamentos com `pago_em` no período (os estornados depois também,
  marcados como "estornado");
- Estornado = pagamentos com `estornado_em` no período (saída no dia do estorno,
  na forma e em "quem recebeu" do pagamento original);
- Líquido = Recebido − Estornado.
Assim o fechamento de um dia que passou não muda quando alguém estorna depois.
`pago_em` e `estornado_em` são horário de Brasília.
"""
from datetime import date

from db import query

SEM_NOME = "Não informado"
ORDEM_FORMAS = ("pix", "dinheiro", "cartao_credito", "cartao_debito", "transferencia", "cartao", "boleto")
MAX_DIAS = 366

_BASE = """SELECT pg.id, pg.valor_centavos, pg.forma, pg.pago_em, pg.estornado_em, pg.estorno_motivo,
                  COALESCE(NULLIF(TRIM(pg.recebido_por_nome), ''), ?) AS recebido_por,
                  cb.id AS cobranca_id, cb.descricao AS cobranca_descricao, p.nome AS paciente_nome
           FROM pagamentos pg
           JOIN cobrancas cb ON cb.id = pg.cobranca_id
           JOIN pacientes p ON p.id = cb.paciente_id
           WHERE COALESCE(cb.organizacao_id, p.organizacao_id) = ?"""


def _data_iso(texto):
    try:
        return date.fromisoformat(texto).isoformat() if len(texto) == 10 else None
    except (TypeError, ValueError):
        return None


def validar_periodo(de, ate, hoje):
    """(de, ate) em ISO, ou a mensagem de erro. Vazio = hoje."""
    datas = []
    for valor in (de, ate):
        if valor in (None, ""):
            datas.append(hoje)
            continue
        iso = _data_iso(str(valor))
        if not iso:
            return "Data inválida."
        datas.append(iso)
    de, ate = datas
    if de > ate:
        return "A data inicial é depois da final."
    if (date.fromisoformat(ate) - date.fromisoformat(de)).days > MAX_DIAS:
        return "Escolha um período de até 1 ano."
    return de, ate


def _linhas(org_id, coluna, de, ate):
    return query(f"{_BASE} AND pg.{coluna} IS NOT NULL AND substr(pg.{coluna}, 1, 10) BETWEEN ? AND ? "
                 f"ORDER BY pg.{coluna}, pg.id", (SEM_NOME, org_id, de, ate))


def _ordem_forma(forma):
    return (ORDEM_FORMAS.index(forma) if forma in ORDEM_FORMAS else len(ORDEM_FORMAS), forma or "")


def fechamento(org_id, de, ate, recebido_por=None, forma=None):
    entradas = _linhas(org_id, "pago_em", de, ate)
    saidas = _linhas(org_id, "estornado_em", de, ate)
    opcoes = {
        "quem": sorted({r["recebido_por"] for r in entradas + saidas}, key=str.lower),
        "formas": sorted({r["forma"] for r in entradas + saidas}, key=_ordem_forma),
    }

    def passa(r):
        return (not recebido_por or r["recebido_por"] == recebido_por) and (not forma or r["forma"] == forma)

    entradas = [r for r in entradas if passa(r)]
    saidas = [r for r in saidas if passa(r)]

    recebimentos = [{
        "id": r["id"], "pago_em": r["pago_em"], "paciente_nome": r["paciente_nome"],
        "cobranca_id": r["cobranca_id"], "cobranca_descricao": r["cobranca_descricao"], "forma": r["forma"],
        "valor_centavos": r["valor_centavos"], "recebido_por": r["recebido_por"], "estornado": bool(r["estornado_em"]),
    } for r in entradas]
    estornos = [{
        "id": r["id"], "estornado_em": r["estornado_em"], "pago_em": r["pago_em"], "paciente_nome": r["paciente_nome"],
        "cobranca_id": r["cobranca_id"], "cobranca_descricao": r["cobranca_descricao"], "forma": r["forma"],
        "valor_centavos": r["valor_centavos"], "recebido_por": r["recebido_por"], "motivo": r["estorno_motivo"],
    } for r in saidas]

    def agrupar(chave):
        grupos = {}
        for lista, campo in ((recebimentos, "recebido_centavos"), (estornos, "estornado_centavos")):
            for r in lista:
                g = grupos.setdefault(r[chave], {"recebido_centavos": 0, "estornado_centavos": 0})
                g[campo] += r["valor_centavos"]
        for g in grupos.values():
            g["liquido_centavos"] = g["recebido_centavos"] - g["estornado_centavos"]
        return grupos

    por_forma = [{"forma": f, **v} for f, v in sorted(agrupar("forma").items(), key=lambda kv: _ordem_forma(kv[0]))]
    por_quem = [{"recebido_por": q, **v} for q, v in sorted(agrupar("recebido_por").items(), key=lambda kv: kv[0].lower())]
    recebido = sum(r["valor_centavos"] for r in recebimentos)
    estornado = sum(r["valor_centavos"] for r in estornos)
    return {
        "de": de, "ate": ate,
        "recebimentos": recebimentos, "estornos": estornos,
        "por_forma": por_forma, "por_quem": por_quem,
        "totais": {"recebido_centavos": recebido, "estornado_centavos": estornado,
                   "liquido_centavos": recebido - estornado, "quantidade": len(recebimentos)},
        "opcoes": opcoes,
    }
