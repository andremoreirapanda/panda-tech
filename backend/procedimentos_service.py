"""
Procedimentos da clínica (spec 09/10/2026, parte A): nome + valor, só o
gestor configura. A consulta guarda o procedimento e o valor do dia em que foi
marcada (`consultas.procedimento_valor_centavos`).
"""
import math
import re

from db import query, query_one

VALOR_MAXIMO_CENTAVOS = 10_000_000  # R$ 100.000,00
NOME_MAX = 120
CODIGO_MAX = 30


def reais_para_centavos(valor):
    """230 / 230.5 / "230,00" / "1.230,50" / "R$ 15" → centavos; None se inválido,
    negativo ou acima do máximo."""
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        if not math.isfinite(valor):
            return None
        centavos = round(valor * 100)
    else:
        texto = re.sub(r"^\s*R\$\s*", "", str(valor)).strip()
        if not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d{1,2})?|\d+(,\d{1,2})?|\d+\.\d{1,2}", texto):
            return None
        if "," in texto:
            inteiro, _, frac = texto.replace(".", "").partition(",")
        elif re.fullmatch(r"\d+\.\d{1,2}", texto):
            inteiro, _, frac = texto.partition(".")
        else:
            inteiro, frac = texto.replace(".", ""), ""
        centavos = int(inteiro) * 100 + int((frac + "00")[:2])
    if centavos < 0 or centavos > VALOR_MAXIMO_CENTAVOS:
        return None
    return int(centavos)


def chave_nome(nome):
    return (nome or "").strip().lower()


def ativos_da_clinica(org_id):
    return query("SELECT id, nome, codigo FROM procedimentos WHERE organizacao_id = ? AND ativo = 1 ORDER BY ordem, id",
                 (org_id,))


def clinica_tem_ativos(org_id):
    return bool(query_one("SELECT 1 AS x FROM procedimentos WHERE organizacao_id = ? AND ativo = 1 LIMIT 1", (org_id,)))


def procedimento_valido(org_id, procedimento_id, permitir_id=None):
    """O procedimento, se for da clínica e ativo (ou se for `permitir_id`, o que a
    consulta já tinha, mesmo desativado depois); senão None."""
    if isinstance(procedimento_id, bool):
        return None
    try:
        pid = int(procedimento_id)
    except (TypeError, ValueError):
        return None
    p = query_one("SELECT * FROM procedimentos WHERE id = ? AND organizacao_id = ?", (pid, org_id))
    if not p or not (p["ativo"] or pid == permitir_id):
        return None
    return p
