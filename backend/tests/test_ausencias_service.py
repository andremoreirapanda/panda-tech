"""Regras puras das ausências da agenda (spec 07/10/2026)."""
from datetime import date

import ausencias_service as s
from validacao_campos import validar_duracao


def aus(**kw):
    base = {"data_inicio": "2026-10-05", "data_fim": None, "dia_inteiro": 0,
            "hora_inicio": "12:00", "hora_fim": "13:00", "dias_semana": "12345", "motivo": "Almoço"}
    base.update(kw)
    return base


def test_validar_duracao():
    assert validar_duracao("45", 5, 480) == (45, None)
    for ruim in (None, "", "abc", 4, 481, 12.5):
        assert validar_duracao(ruim, 5, 480)[1], ruim


def test_validar_ausencia_ok_e_normaliza():
    dados, erro = s.validar_ausencia({"data_inicio": "2026-10-10", "data_fim": "", "dia_inteiro": True,
                                      "hora_inicio": "09:00", "dias_semana": "5321", "motivo": "  Férias "})
    assert erro is None
    assert dados == {"data_inicio": "2026-10-10", "data_fim": None, "dia_inteiro": 1, "hora_inicio": None,
                     "hora_fim": None, "dias_semana": "1235", "motivo": "Férias"}


def test_validar_ausencia_erros():
    casos = [
        {"data_inicio": "10/10/2026"},
        {"data_inicio": "2026-10-10", "data_fim": "2026-10-09", "dia_inteiro": 1, "dias_semana": "1"},
        {"data_inicio": "2026-10-10", "dia_inteiro": 0, "hora_inicio": "13:00", "hora_fim": "12:00", "dias_semana": "1"},
        {"data_inicio": "2026-10-10", "dia_inteiro": 0, "hora_inicio": "", "hora_fim": "12:00", "dias_semana": "1"},
        {"data_inicio": "2026-10-10", "dia_inteiro": 1, "dias_semana": ""},
        {"data_inicio": "2026-10-10", "dia_inteiro": 1, "dias_semana": "78"},
        {"data_inicio": "2026-10-10", "dia_inteiro": 1, "dias_semana": "1", "motivo": "x" * 121},
    ]
    for body in casos:
        assert s.validar_ausencia(body)[1], body


def test_dia_semana_domingo_zero():
    assert s.dia_semana(date(2026, 10, 4)) == 0   # domingo
    assert s.dia_semana(date(2026, 10, 10)) == 6  # sábado


def test_cobre_horario_e_borda_que_encosta():
    a = aus()
    seg = date(2026, 10, 5)
    assert s.ausencia_cobre(a, seg, 11 * 60 + 30, 12 * 60 + 30)       # sobrepõe
    assert not s.ausencia_cobre(a, seg, 11 * 60, 12 * 60)             # termina 12:00 — encosta
    assert not s.ausencia_cobre(a, seg, 13 * 60, 14 * 60)             # começa 13:00 — encosta
    assert not s.ausencia_cobre(a, date(2026, 10, 4), 12 * 60, 12 * 60 + 30)  # domingo fora dos dias


def test_cobre_periodo_e_sem_fim():
    a = aus(data_fim="2026-10-09")
    assert not s.ausencia_cobre(a, date(2026, 10, 2), 12 * 60, 12 * 60 + 30)   # antes do início
    assert not s.ausencia_cobre(a, date(2026, 10, 12), 12 * 60, 12 * 60 + 30)  # depois do fim
    sem_fim = aus()
    assert s.ausencia_cobre(sem_fim, date(2030, 3, 4), 12 * 60, 12 * 60 + 30)  # segunda em 2030


def test_cobre_dia_inteiro():
    a = aus(dia_inteiro=1, hora_inicio=None, hora_fim=None, dias_semana="0123456")
    assert s.ausencia_cobre(a, date(2026, 10, 7), 7 * 60, 7 * 60 + 5)


def test_ocorrencias_no_intervalo():
    a = dict(aus(data_fim="2026-10-07"), id=9, profissional_id=3)
    occ = s.ocorrencias([a], date(2026, 10, 4), date(2026, 10, 10))
    assert [o["data"] for o in occ] == ["2026-10-05", "2026-10-06", "2026-10-07"]
    assert occ[0]["ausencia_id"] == 9 and occ[0]["profissional_id"] == 3
    assert occ[0]["hora_inicio"] == "12:00" and occ[0]["dias_semana"] == "12345"


def test_separar_data_hora_aceita_hora_sem_zero():
    assert s.separar_data_hora("2026-10-05 9:30:00") == (date(2026, 10, 5), 570)
    assert s.separar_data_hora("lixo") == (None, None)
