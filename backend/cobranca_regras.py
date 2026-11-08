"""Regras puras de cobrança das famílias (sem banco). Valores em centavos."""
import calendar
from datetime import date, timedelta


def _d(texto):
    return date.fromisoformat(str(texto)[:10])


def normalizar_especialidade(texto):
    t = (texto or "").strip()
    return t or "Geral"


def mesma_especialidade(a, b):
    return (a or "").strip().lower() == (b or "").strip().lower()


def escolher_acordo(acordos, especialidade, data):
    """Acordo ativo e vigente na data; o específico vence o '*'."""
    vigentes = []
    for a in acordos:
        if a.get("status") != "ativo":
            continue
        if str(a.get("inicio") or "")[:10] > data:
            continue
        fim = a.get("fim")
        if fim and str(fim)[:10] < data:
            continue
        vigentes.append(a)
    for a in vigentes:
        if a.get("especialidade") != "*" and mesma_especialidade(a.get("especialidade"), especialidade):
            return a
    for a in vigentes:
        if a.get("especialidade") == "*":
            return a
    return None


def status_gera_cobranca(status, cobrar_falta):
    if status == "realizada":
        return True
    if status == "faltou":
        return bool(cobrar_falta)
    return False


def periodo_da_data(data, ciclo):
    d = _d(data)
    ultimo = calendar.monthrange(d.year, d.month)[1]
    if ciclo == "consulta":
        return (d.isoformat(), d.isoformat())
    if ciclo == "quinzenal":
        if d.day <= 15:
            return (date(d.year, d.month, 1).isoformat(), date(d.year, d.month, 15).isoformat())
        return (date(d.year, d.month, 16).isoformat(), date(d.year, d.month, ultimo).isoformat())
    if ciclo == "mensal":
        return (date(d.year, d.month, 1).isoformat(), date(d.year, d.month, ultimo).isoformat())
    raise ValueError(f"ciclo inválido: {ciclo}")


def vencimento_do_periodo(fim, vence_dias):
    return (_d(fim) + timedelta(days=int(vence_dias))).isoformat()


def vencimento_minimo(venc, hoje, prazo_dias=5):
    """Cobrança não nasce vencida: se a data calculada já passou, vence em hoje + prazo."""
    if str(venc)[:10] >= str(hoje)[:10]:
        return str(venc)[:10]
    return (_d(hoje) + timedelta(days=prazo_dias)).isoformat()


def mensalidade_do_mes(valor, ano, mes, inicio, fim):
    dias_mes = calendar.monthrange(ano, mes)[1]
    p, u = date(ano, mes, 1), date(ano, mes, dias_mes)
    ini = max(_d(inicio), p)
    ate = min(_d(fim), u) if fim else u
    if ate < ini:
        return 0
    dias = (ate - ini).days + 1
    return round(valor * dias / dias_mes)


def ratear_desconto(valores, desconto):
    total = sum(valores)
    if not valores or desconto <= 0 or total <= 0:
        return list(valores)
    descontos = [round(v * desconto / total) for v in valores]
    sobra = desconto - sum(descontos)
    descontos[valores.index(max(valores))] += sobra
    return [v - d for v, d in zip(valores, descontos)]


def parcelas_do_pacote(valor, parcelas, primeiro_vencimento):
    base = valor // parcelas
    resto = valor - base * parcelas
    p = _d(primeiro_vencimento)
    saida = []
    for i in range(parcelas):
        m = p.month - 1 + i
        ano, mes = p.year + m // 12, m % 12 + 1
        dia = min(p.day, calendar.monthrange(ano, mes)[1])
        saida.append((date(ano, mes, dia).isoformat(), base + (resto if i == 0 else 0)))
    return saida
