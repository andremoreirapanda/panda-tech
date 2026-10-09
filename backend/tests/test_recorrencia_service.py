"""Repetição avançada do agendamento (spec 09/10/2026, parte B): datas da série."""
from datetime import datetime

import pytest

from recorrencia_service import gerar_datas, LIMITE_CONSULTAS

SEG = datetime(2026, 10, 12, 9, 0)   # segunda-feira


def _dias(lista):
    return [d[:10] for d, _ in lista]


def test_semanal_dois_dias_com_horarios_proprios():
    regra = {"frequencia": "semanal", "dias": {"1": {"inicio": "09:00", "fim": "09:50"}, "3": {"inicio": "14:00", "fim": "15:00"}},
             "quantidade": 4}
    assert gerar_datas(regra, SEG) == [("2026-10-12 09:00:00", 50), ("2026-10-14 14:00:00", 60),
                                       ("2026-10-19 09:00:00", 50), ("2026-10-21 14:00:00", 60)]


def test_sem_dias_usa_o_dia_e_horario_do_inicio():
    assert gerar_datas({"frequencia": "semanal", "quantidade": 2, "duracao_min": 45}, SEG) == [
        ("2026-10-12 09:00:00", 45), ("2026-10-19 09:00:00", 45)]


def test_quinzenal_e_a_cada_n_semanas():
    assert _dias(gerar_datas({"frequencia": "quinzenal", "quantidade": 3}, SEG)) == ["2026-10-12", "2026-10-26", "2026-11-09"]
    assert _dias(gerar_datas({"frequencia": "semanas", "a_cada": 3, "quantidade": 3}, SEG)) == ["2026-10-12", "2026-11-02", "2026-11-23"]


def test_nada_antes_do_inicio():
    regra = {"frequencia": "semanal", "dias": {"0": {"inicio": "10:00", "fim": "11:00"}, "1": {"inicio": "09:00", "fim": "09:50"}},
             "quantidade": 3}
    assert _dias(gerar_datas(regra, SEG)) == ["2026-10-12", "2026-10-18", "2026-10-19"]


def test_mensal_pelo_dia_do_mes_usa_ultimo_dia():
    r = gerar_datas({"frequencia": "mensal", "mensal_por": "dia_mes", "quantidade": 3}, datetime(2027, 1, 31, 10, 0))
    assert _dias(r) == ["2027-01-31", "2027-02-28", "2027-03-31"]


def test_mensal_pelo_dia_da_semana():
    r = gerar_datas({"frequencia": "mensal", "mensal_por": "dia_semana", "quantidade": 3}, datetime(2026, 10, 13, 9, 0))
    assert _dias(r) == ["2026-10-13", "2026-11-10", "2026-12-08"]          # 2ª terça
    r = gerar_datas({"frequencia": "mensal", "mensal_por": "dia_semana", "quantidade": 2}, datetime(2026, 12, 29, 9, 0))
    assert _dias(r) == ["2026-12-29", "2027-01-26"]                          # 5ª terça → última


def test_meses_desmarcados_sao_pulados():
    r = gerar_datas({"frequencia": "semanal", "meses": [10, 12], "quantidade": 6}, SEG)
    assert _dias(r) == ["2026-10-12", "2026-10-19", "2026-10-26", "2026-12-07", "2026-12-14", "2026-12-21"]


def test_data_limite():
    assert _dias(gerar_datas({"frequencia": "semanal", "data_limite": "2026-10-31"}, SEG)) == ["2026-10-12", "2026-10-19", "2026-10-26"]


def test_sem_fim_vai_ate_12_meses():
    r = gerar_datas({"frequencia": "semanal"}, SEG)
    assert r[-1][0][:10] <= "2027-10-12" and len(r) == 53
    assert _dias(r)[-1] == "2027-10-11"


@pytest.mark.parametrize("regra", [
    {"frequencia": "semanal", "data_limite": "2027-10-13"},                       # passa de 12 meses
    {"frequencia": "semanal", "quantidade": LIMITE_CONSULTAS + 1},
    {"frequencia": "semanal", "dias": {str(d): {"inicio": "08:00", "fim": "09:00"} for d in range(7)}},  # sem fim → 366 > 300
    {"frequencia": "mensal", "quantidade": 14},                                   # não cabe em 12 meses
    {"frequencia": "semanal", "dias": {}},
    {"frequencia": "semanal", "dias": {"1": {"inicio": "10:00", "fim": "09:00"}}},
    {"frequencia": "semanal", "dias": {"9": {"inicio": "10:00", "fim": "11:00"}}},
    {"frequencia": "semanal", "meses": []},
    {"frequencia": "semanas", "a_cada": 13},
    {"frequencia": "diaria"},
    {"frequencia": "semanal", "data_limite": "2026-10-01"},                       # antes do início
    {"frequencia": "semanal", "quantidade": 0},
    {"frequencia": "semanal", "dias": {"1": {"inicio": "08:00", "fim": "08:01"}}},   # 1 min < 5
    {"frequencia": "semanal", "dias": {"1": {"inicio": "07:00", "fim": "21:00"}}},   # 840 min > 480
])
def test_regras_invalidas(regra):
    with pytest.raises(ValueError):
        gerar_datas(regra, SEG)
