"""
Ausências do profissional na agenda (spec 07/10/2026).

Uma linha de `ausencias_profissional` é uma REGRA: período (data_fim NULL =
sem fim), dia inteiro ou horário, e dias da semana ("0".."6", 0 = domingo).
As ocorrências são calculadas na hora. Aqui ficam as funções puras (testadas
em tests/test_ausencias_service.py) e as consultas ao banco usadas pelas
rotas da agenda.
"""
import re
from datetime import datetime, timedelta, timezone

from db import query

_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DATA_HORA = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2})")
MAX_MOTIVO = 120
# Status de consulta que liberam o horário (Atender, 08/10/2026): não contam
# como horário ocupado (encaixe, consultas no período, ausências).
STATUS_LIBERAM_HORARIO = ("cancelada", "desmarcada_profissional", "falta_justificada")
SQL_STATUS_LIBERAM = "('cancelada', 'desmarcada_profissional', 'falta_justificada')"


def _agora_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hoje_brasilia():
    """Data de hoje em Brasília (UTC−3, sem horário de verão desde 2019) — o
    servidor pode estar em UTC, e depois das 21h já seria o dia seguinte."""
    return (_agora_utc() - timedelta(hours=3)).date()


def _data(texto):
    texto = str(texto or "").strip()
    if not _DATA.match(texto):
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return None


def _minutos(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def dia_semana(d):
    """0 = domingo ... 6 = sábado (mesma convenção do JS getDay())."""
    return (d.weekday() + 1) % 7


def separar_data_hora(data_hora):
    m = _DATA_HORA.match(str(data_hora or ""))
    if not m:
        return None, None
    d = _data(m.group(1))
    h, mi = int(m.group(2)), int(m.group(3))
    if d is None or h > 23 or mi > 59:
        return None, None
    return d, h * 60 + mi


def validar_ausencia(body):
    inicio = _data(body.get("data_inicio"))
    if not inicio:
        return None, "Data de início inválida — use o calendário para escolher."
    fim_txt = str(body.get("data_fim") or "").strip()
    fim = None
    if fim_txt:
        fim = _data(fim_txt)
        if not fim:
            return None, "Data de fim inválida."
        if fim < inicio:
            return None, "A data de fim precisa ser igual ou depois da data de início."
    dia_inteiro = 1 if body.get("dia_inteiro") in (True, 1, "1", "true") else 0
    hora_inicio = hora_fim = None
    if not dia_inteiro:
        hora_inicio = str(body.get("hora_inicio") or "").strip()
        hora_fim = str(body.get("hora_fim") or "").strip()
        if not (_HHMM.match(hora_inicio) and _HHMM.match(hora_fim)):
            return None, "Informe o horário da ausência (início e fim) ou marque 'Dia inteiro'."
        if hora_inicio >= hora_fim:
            return None, "O horário de fim da ausência precisa ser depois do início."
    dias = str(body.get("dias_semana") or "").strip()
    if not dias or any(c not in "0123456" for c in dias):
        return None, "Escolha pelo menos um dia da semana."
    dias = "".join(sorted(set(dias)))
    motivo = str(body.get("motivo") or "").strip()
    if len(motivo) > MAX_MOTIVO:
        return None, f"O motivo pode ter no máximo {MAX_MOTIVO} caracteres."
    return {
        "data_inicio": inicio.isoformat(), "data_fim": fim.isoformat() if fim else None,
        "dia_inteiro": dia_inteiro, "hora_inicio": hora_inicio, "hora_fim": hora_fim,
        "dias_semana": dias, "motivo": motivo or None,
    }, None


def _vale_no_dia(aus, d):
    inicio = _data(aus["data_inicio"])
    fim = _data(aus.get("data_fim")) if aus.get("data_fim") else None
    if inicio is None or d < inicio or (fim and d > fim):
        return False
    return str(dia_semana(d)) in str(aus.get("dias_semana") or "")


def ausencia_cobre(aus, d, ini_min, fim_min):
    """A regra vale no dia `d` e o intervalo [ini_min, fim_min) se sobrepõe a
    ela? Encostar (terminar quando ela começa) não conta."""
    if not _vale_no_dia(aus, d):
        return False
    if aus.get("dia_inteiro"):
        return True
    a_ini, a_fim = _minutos(aus["hora_inicio"]), _minutos(aus["hora_fim"])
    return ini_min < a_fim and fim_min > a_ini


def ocorrencias(ausencias, data_ini, data_fim):
    saida = []
    d = data_ini
    while d <= data_fim:
        for a in ausencias:
            if _vale_no_dia(a, d):
                saida.append({
                    "ausencia_id": a.get("id"), "profissional_id": a.get("profissional_id"),
                    "data": d.isoformat(), "dia_inteiro": int(a.get("dia_inteiro") or 0),
                    "hora_inicio": a.get("hora_inicio"), "hora_fim": a.get("hora_fim"),
                    "motivo": a.get("motivo"), "data_inicio": a.get("data_inicio"),
                    "data_fim": a.get("data_fim"), "dias_semana": a.get("dias_semana"),
                })
        d += timedelta(days=1)
    return saida


# ------------------------------------------------------------ consultas ao banco

def ausencias_do_profissional(profissional_id, d):
    return query(
        """SELECT * FROM ausencias_profissional WHERE profissional_id = ?
           AND data_inicio <= ? AND (data_fim IS NULL OR data_fim >= ?)""",
        (profissional_id, d.isoformat(), d.isoformat()),
    )


def ausencias_do_profissional_no_periodo(profissional_id, d_ini, d_fim):
    """Regras do profissional que tocam [d_ini, d_fim] — uma leitura para uma série inteira."""
    return query(
        """SELECT * FROM ausencias_profissional WHERE profissional_id = ?
           AND data_inicio <= ? AND (data_fim IS NULL OR data_fim >= ?)""",
        (profissional_id, d_fim.isoformat(), d_ini.isoformat()),
    )


def conflito_em_regras(regras, data_hora, duracao_min):
    """Mesma regra de `conflito_ausencia`, mas sobre regras já lidas."""
    d, ini = separar_data_hora(data_hora)
    if d is None:
        return None
    fim = min(ini + int(duracao_min or 0), 24 * 60)
    for a in regras:
        if ausencia_cobre(a, d, ini, fim):
            return a
    return None


def conflito_ausencia(profissional_id, data_hora, duracao_min):
    """Primeira ausência do profissional que bate com a consulta, ou None.
    Consulta que passa da meia-noite só é checada no dia em que começa."""
    d, ini = separar_data_hora(data_hora)
    if d is None:
        return None
    fim = min(ini + int(duracao_min or 0), 24 * 60)
    for a in ausencias_do_profissional(profissional_id, d):
        if ausencia_cobre(a, d, ini, fim):
            return a
    return None


def consultas_no_periodo(aus, hoje=None):
    """Consultas não canceladas, de hoje em diante, que caem na regra."""
    hoje = hoje or hoje_brasilia()
    desde = max(hoje, _data(aus["data_inicio"]))
    params = [aus["profissional_id"], desde.isoformat()]
    sql = f"""SELECT c.id, c.data_hora, c.duracao_min, p.nome AS paciente_nome
             FROM consultas c JOIN pacientes p ON p.id = c.paciente_id
             WHERE c.profissional_id = ? AND c.status NOT IN {SQL_STATUS_LIBERAM} AND c.data_hora >= ?"""
    if aus.get("data_fim"):
        sql += " AND c.data_hora < ?"
        params.append((_data(aus["data_fim"]) + timedelta(days=1)).isoformat())
    saida = []
    for c in query(sql + " ORDER BY c.data_hora", tuple(params)):
        d, ini = separar_data_hora(c["data_hora"])
        if d and ausencia_cobre(aus, d, ini, ini + int(c["duracao_min"] or 50)):
            saida.append({"id": c["id"], "data_hora": c["data_hora"], "paciente_nome": c["paciente_nome"]})
    return saida
