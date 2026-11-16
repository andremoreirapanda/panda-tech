"""Regras puras do repasse aos profissionais (sem banco)."""
from cobranca_regras import ratear_desconto


def escolher_regra(regras, procedimento_id, tipo_acordo):
    """procedimento + tipo > procedimento > tipo > padrao (os dois NULL)."""
    for proc, tipo in ((procedimento_id, tipo_acordo), (procedimento_id, None),
                       (None, tipo_acordo), (None, None)):
        for r in regras:
            if r.get("procedimento_id") == proc and r.get("tipo_acordo") == tipo:
                return r
    return None


def valor_profissional(regra, base_centavos):
    if regra["modo"] == "fixo":
        return int(regra["valor_centavos"])
    return (int(base_centavos) * int(regra["percentual_centesimos"]) + 5000) // 10000


def bases_avulsa(itens, desconto):
    return ratear_desconto(list(itens), desconto)


def rateio_igual(total, n):
    base = total // n
    saida = [base] * n
    saida[-1] += total - base * n
    return saida


def pacote_liberadas(valor_pacote, sessoes_total, pago):
    if valor_pacote <= 0:
        return sessoes_total
    k = (pago * sessoes_total) // valor_pacote
    return max(0, min(sessoes_total, k))


def _brl(centavos):
    reais, cent = divmod(int(centavos), 100)
    return "R$ " + f"{reais:,}".replace(",", ".") + f",{cent:02d}"


def rotulo_regra(regra):
    if not regra:
        return "a definir"
    if regra["modo"] == "fixo":
        return _brl(regra["valor_centavos"]) + " fixo"
    inteiro, frac = divmod(int(regra["percentual_centesimos"]), 100)
    txt = str(inteiro) + ("," + f"{frac:02d}".rstrip("0") if frac else "")
    return txt + "%"
