"""
Repetição avançada do agendamento (spec 09/10/2026, parte B), com as opções
da Clínica Ágil: semanal, quinzenal, a cada N semanas (vários dias, cada um
com o próprio horário) ou mensal (mesmo dia do mês ou mesmo dia da semana),
só nos meses escolhidos, até uma data, por uma quantidade ou — sem fim — por
12 meses. Função pura: quem grava é o agenda_bp.

Regra (já vinda do corpo do POST /api/agenda/recorrente, campo `repeticao`):
    frequencia   "semanal" | "quinzenal" | "mensal" | "semanas"
    a_cada       1..12 (só "semanas")
    dias         {"0".."6": {"inicio": "HH:MM", "fim": "HH:MM"}} — 0 = domingo;
                 ausente = só o dia da data inicial, no horário dela
    duracao_min  duração quando não há `dias` (padrão 50)
    mensal_por   "dia_mes" | "dia_semana" (só mensal; padrão dia_mes)
    meses        [1..12] ou None (todos)
    data_limite  "YYYY-MM-DD" ou None
    quantidade   1..300 ou None
"""
import calendar
from datetime import date, timedelta

LIMITE_CONSULTAS = 300
LIMITE_MESES = 12
FREQUENCIAS = ("semanal", "quinzenal", "mensal", "semanas")


def _somar_meses(d, meses):
    total = d.month - 1 + meses
    ano, mes = d.year + total // 12, total % 12 + 1
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def _hhmm(texto):
    try:
        h, m = str(texto).split(":")[:2]
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        return None
    return h * 60 + m if 0 <= h <= 23 and 0 <= m <= 59 else None


def _dia_semana_python(dia_app):
    """0 = domingo (app) → 6 (Python, segunda = 0)."""
    return (dia_app + 6) % 7


def _inteiro(valor, nome, minimo, maximo):
    if isinstance(valor, bool):
        raise ValueError(f"{nome} inválido.")
    try:
        n = int(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{nome} inválido.")
    if n != valor and not isinstance(valor, str):
        raise ValueError(f"{nome} inválido.")
    if not minimo <= n <= maximo:
        raise ValueError(f"{nome}: escolha entre {minimo} e {maximo}.")
    return n


def _horarios(regra, inicio):
    """{dia_python: (minuto_inicio, duracao)} para as frequências por semana."""
    dias = regra.get("dias")
    if dias is None:
        return {inicio.weekday(): (inicio.hour * 60 + inicio.minute, _inteiro(regra.get("duracao_min", 50), "Duração", 5, 480))}
    if not isinstance(dias, dict) or not dias:
        raise ValueError("Marque pelo menos um dia da semana.")
    saida = {}
    for chave, horario in dias.items():
        try:
            dia_app = int(chave)
        except (TypeError, ValueError):
            raise ValueError("Dia da semana inválido.")
        if not 0 <= dia_app <= 6 or not isinstance(horario, dict):
            raise ValueError("Dia da semana inválido.")
        ini, fim = _hhmm(horario.get("inicio")), _hhmm(horario.get("fim"))
        if ini is None or fim is None or fim <= ini:
            raise ValueError("Em cada dia marcado, o fim precisa ser depois do início.")
        saida[_dia_semana_python(dia_app)] = (ini, fim - ini)
    return saida


def _no_mes_pelo_dia_da_semana(ano, mes, dia_semana, ordem):
    """A `ordem`-ésima ocorrência do dia da semana no mês; 5 (ou inexistente) = a última."""
    ultimo = calendar.monthrange(ano, mes)[1]
    dias = [d for d in range(1, ultimo + 1) if date(ano, mes, d).weekday() == dia_semana]
    return date(ano, mes, dias[ordem - 1] if ordem <= 4 else dias[-1])


def gerar_datas(regra, inicio):
    """[("YYYY-MM-DD HH:MM:SS", duracao_min), ...] em ordem. ValueError com a
    mensagem para o usuário se a regra for inválida ou passar dos limites."""
    if not isinstance(regra, dict):
        raise ValueError("Repetição inválida.")
    frequencia = regra.get("frequencia")
    if frequencia not in FREQUENCIAS:
        raise ValueError("Frequência inválida.")
    meses = regra.get("meses")
    if meses is not None:
        if not isinstance(meses, list) or not meses:
            raise ValueError("Marque pelo menos um mês.")
        meses = {_inteiro(m, "Mês", 1, 12) for m in meses}
    quantidade = regra.get("quantidade")
    if quantidade is not None:
        quantidade = _inteiro(quantidade, "Quantidade de consultas", 1, LIMITE_CONSULTAS)
    teto = _somar_meses(inicio.date(), LIMITE_MESES)
    data_limite = regra.get("data_limite")
    if data_limite:
        try:
            data_limite = date.fromisoformat(str(data_limite))
        except ValueError:
            raise ValueError("Data limite inválida.")
        if data_limite < inicio.date():
            raise ValueError("A data limite precisa ser depois da primeira consulta.")
        if data_limite > teto:
            raise ValueError(f"A repetição vai no máximo até {teto.strftime('%d/%m/%Y')} (12 meses).")
    fim = data_limite or teto

    candidatas = []  # (date, minuto_inicio, duracao)
    if frequencia == "mensal":
        duracao = _inteiro(regra.get("duracao_min", 50), "Duração", 5, 480)
        por = regra.get("mensal_por", "dia_mes")
        if por not in ("dia_mes", "dia_semana"):
            raise ValueError("Escolha repetir no mesmo dia do mês ou no mesmo dia da semana.")
        ordem = (inicio.day - 1) // 7 + 1
        for i in range(LIMITE_MESES + 1):
            if por == "dia_mes":
                d = _somar_meses(inicio.date(), i)
            else:
                base = _somar_meses(inicio.date().replace(day=1), i)
                d = _no_mes_pelo_dia_da_semana(base.year, base.month, inicio.weekday(), ordem)
            candidatas.append((d, inicio.hour * 60 + inicio.minute, duracao))
    else:
        passo = {"semanal": 1, "quinzenal": 2}.get(frequencia) or _inteiro(regra.get("a_cada"), "A cada quantas semanas", 1, 12)
        horarios = _horarios(regra, inicio)
        domingo = inicio.date() - timedelta(days=(inicio.weekday() + 1) % 7)   # semanas de domingo a sábado
        semana = 0
        while domingo + timedelta(weeks=semana) <= fim:
            for k in range(7):
                d = domingo + timedelta(weeks=semana, days=k)
                if d.weekday() in horarios:
                    candidatas.append((d, *horarios[d.weekday()]))
            semana += passo

    datas = []
    for d, minuto, duracao in candidatas:
        if d < inicio.date() or d > fim or (meses and d.month not in meses):
            continue
        datas.append((f"{d.isoformat()} {minuto // 60:02d}:{minuto % 60:02d}:00", duracao))
        if quantidade and len(datas) == quantidade:
            break
        if len(datas) > LIMITE_CONSULTAS:
            raise ValueError(f"A repetição passa de {LIMITE_CONSULTAS} consultas; diminua os dias ou o período.")
    if quantidade and len(datas) < quantidade:
        raise ValueError(f"Em 12 meses cabem só {len(datas)} consultas com essas opções.")
    if not datas:
        raise ValueError("Nenhuma data cabe nessas opções (confira os dias e os meses).")
    return datas
