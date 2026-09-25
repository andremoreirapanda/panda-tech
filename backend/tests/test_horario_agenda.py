"""
Horário de funcionamento da agenda (spec 24/09/2026): o gestor define
início e fim (HH:MM, qualquer minuto) em Configurações e a grade da agenda
se enquadra nessa faixa. Ambos vazios = modo automático.
"""
from factories import DuasClinicas

from conftest import autenticado


def _org(db_ctx, org_id):
    row = db_ctx.query_one("SELECT agenda_hora_inicio, agenda_hora_fim FROM organizacoes WHERE id = ?", (org_id,))
    return (row["agenda_hora_inicio"], row["agenda_hora_fim"])


def test_gestor_salva_horario_picado(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).put("/api/pessoas/organizacao", json={
        "agenda_hora_inicio": "08:00", "agenda_hora_fim": "19:15",
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert _org(db_ctx, cen.org_a) == ("08:00", "19:15")


def test_horario_aparece_no_auth_me(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    c.put("/api/pessoas/organizacao", json={"agenda_hora_inicio": "07:30", "agenda_hora_fim": "18:00"})
    org = c.get("/api/auth/me").get_json()["organizacao"]
    assert org["agenda_hora_inicio"] == "07:30"
    assert org["agenda_hora_fim"] == "18:00"


def test_campos_vazios_voltam_para_automatico(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    c.put("/api/pessoas/organizacao", json={"agenda_hora_inicio": "08:00", "agenda_hora_fim": "18:00"})
    r = c.put("/api/pessoas/organizacao", json={"agenda_hora_inicio": "", "agenda_hora_fim": ""})
    assert r.status_code == 200
    assert _org(db_ctx, cen.org_a) == (None, None)


def test_put_sem_os_campos_mantem_o_horario(client, db_ctx):
    """Onboarding e outras telas salvam a clínica com corpo parcial — não
    podem apagar o horário sem querer."""
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    c.put("/api/pessoas/organizacao", json={"agenda_hora_inicio": "08:00", "agenda_hora_fim": "19:15"})
    r = c.put("/api/pessoas/organizacao", json={"nome": "Clínica A renomeada"})
    assert r.status_code == 200
    assert _org(db_ctx, cen.org_a) == ("08:00", "19:15")


def test_rejeita_formatos_invalidos(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    for inicio, fim in [("8h", "18:00"), ("25:00", "26:00"), ("08:60", "18:00"), ("08:00", ""), ("", "18:00"), ("8:00", "18:00")]:
        r = c.put("/api/pessoas/organizacao", json={"agenda_hora_inicio": inicio, "agenda_hora_fim": fim})
        assert r.status_code == 400, (inicio, fim, r.get_data(as_text=True))
    assert _org(db_ctx, cen.org_a) == (None, None)


def test_rejeita_inicio_depois_ou_igual_ao_fim(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    for inicio, fim in [("19:00", "08:00"), ("08:00", "08:00")]:
        r = c.put("/api/pessoas/organizacao", json={"agenda_hora_inicio": inicio, "agenda_hora_fim": fim})
        assert r.status_code == 400, (inicio, fim)


def test_profissional_nao_altera_horario(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.prof_a1).put("/api/pessoas/organizacao", json={
        "agenda_hora_inicio": "08:00", "agenda_hora_fim": "18:00",
    })
    assert r.status_code == 403
