"""Convites por e-mail (spec PandaUp 12/10/2026, item B)."""
import pytest

import email_service
import planos_padrao
from factories import DuasClinicas, novo_usuario

from conftest import autenticado


class _Envios(list):
    """Lista dos e-mails "enviados"; `.falso.resultado` simula falha do SMTP."""


@pytest.fixture()
def envios(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "mail.pandaup.com.br")
    monkeypatch.setenv("URL_APP", "https://app.pandaup.com.br")
    lista = _Envios()

    def falso(para, assunto, texto, html=None):
        lista.append({"para": para, "assunto": assunto, "texto": texto, "html": html})
        return falso.resultado

    falso.resultado = True
    monkeypatch.setattr(email_service, "enviar_email", falso)
    lista.falso = falso
    return lista


def _admin(client):
    return autenticado(client, novo_usuario(None, "Admin", "admin@plataforma.com", "admin_master"))


def _rotas(client, cen):
    """Cada rota que devolve link_convite: (função que chama, e-mail esperado)."""
    g = autenticado(client, cen.gestor_a)
    return {
        "profissional": (lambda: g.post("/api/pessoas/profissionais", json={
            "nome": "Nova Fono", "email": "nova.fono@a.com", "especialidade": "Fonoaudiologia"}), "nova.fono@a.com"),
        "secretaria": (lambda: g.post("/api/pessoas/secretarias", json={
            "nome": "Nova Sec", "email": "nova.sec@a.com"}), "nova.sec@a.com"),
        "responsavel": (lambda: g.post(f"/api/pessoas/pacientes/{cen.paciente_a1}/vincular-responsavel", json={
            "nome": "Mãe Nova", "email": "mae.nova@a.com"}), "mae.nova@a.com"),
        "reenviar_profissional": (lambda: g.post(f"/api/pessoas/profissionais/{cen.prof_a1['id']}/reenviar-convite"),
                                  "prof.a1@a.com"),
    }


@pytest.mark.parametrize("rota", ["profissional", "secretaria", "responsavel", "reenviar_profissional"])
def test_convite_da_clinica_vai_por_email(client, db_ctx, envios, rota):
    cen = DuasClinicas()
    chamar, email = _rotas(client, cen)[rota]
    r = chamar()
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["enviado_email"] is True and corpo["link_convite"]
    assert len(envios) == 1 and envios[0]["para"] == email
    assert "Clínica A" in envios[0]["texto"]
    assert "https://app.pandaup.com.br/" + corpo["link_convite"] in envios[0]["texto"]


def test_reenviar_secretaria_e_responsavel(client, db_ctx, envios):
    cen = DuasClinicas()
    g = autenticado(client, cen.gestor_a)
    sec = g.post("/api/pessoas/secretarias", json={"nome": "Sec", "email": "sec@a.com"}).get_json()
    resp = g.post(f"/api/pessoas/pacientes/{cen.paciente_a1}/vincular-responsavel",
                  json={"nome": "Pai", "email": "pai@a.com"}).get_json()
    envios.clear()
    assert g.post(f"/api/pessoas/secretarias/{sec['id']}/reenviar-convite").get_json()["enviado_email"] is True
    r = g.post(f"/api/pessoas/pacientes/{cen.paciente_a1}/responsaveis/{resp['usuario_id']}/reenviar-convite")
    assert r.get_json()["enviado_email"] is True
    assert [e["para"] for e in envios] == ["sec@a.com", "pai@a.com"]


def test_admin_clinica_nova_e_reenviar_ao_gestor(client, db_ctx, envios):
    db_ctx.execute("INSERT INTO planos (codigo, nome, preco_mensal_centavos) VALUES (?, ?, ?)", ("premium", "Premium", 19900))
    a = _admin(client)
    r = a.post("/api/admin/clinicas", json={"nome": "Clínica Sol", "plano": "premium",
                                             "gestor_nome": "Gi", "gestor_email": "gi@sol.com"})
    assert r.status_code == 201 and r.get_json()["enviado_email"] is True
    assert envios[-1]["para"] == "gi@sol.com" and "Clínica Sol" in envios[-1]["texto"]
    org_id = r.get_json()["id"]
    gestor = db_ctx.query_one("SELECT id FROM usuarios WHERE email = 'gi@sol.com'")
    r = a.post(f"/api/admin/clinicas/{org_id}/gestores/{gestor['id']}/reenviar-convite")
    assert r.get_json()["enviado_email"] is True and len(envios) == 2


def test_clinica_nova_sem_email_do_gestor_nao_envia(client, db_ctx, envios):
    db_ctx.execute("INSERT INTO planos (codigo, nome, preco_mensal_centavos) VALUES (?, ?, ?)", ("premium", "Premium", 19900))
    r = _admin(client).post("/api/admin/clinicas", json={"nome": "Clínica Lua", "plano": "premium"})
    assert r.status_code == 201 and r.get_json()["enviado_email"] is False and envios == []


def test_novo_administrador_recebe_convite(client, db_ctx, envios):
    r = _admin(client).post("/api/admin/administradores", json={"nome": "Novo Admin", "email": "novo@pandaup.com.br"})
    assert r.status_code == 201 and r.get_json()["enviado_email"] is True
    assert envios[0]["para"] == "novo@pandaup.com.br" and "PandaUp" in envios[0]["texto"]


def test_sem_smtp_enviado_email_false(client, db_ctx, envios, monkeypatch):
    monkeypatch.delenv("SMTP_HOST")
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/pessoas/secretarias", json={"nome": "Sec", "email": "s@a.com"})
    assert r.status_code == 201 and r.get_json()["enviado_email"] is False and envios == []


def test_smtp_falhando_nao_impede_o_cadastro(client, db_ctx, envios):
    envios.falso.resultado = False
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/pessoas/profissionais", json={
        "nome": "Fono", "email": "fono@a.com", "especialidade": "Fonoaudiologia"})
    assert r.status_code == 201 and r.get_json()["enviado_email"] is False and r.get_json()["link_convite"]
    assert db_ctx.query_one("SELECT id FROM usuarios WHERE email = 'fono@a.com'")


def test_importacao_nao_manda_email(client, db_ctx, envios):
    cen = DuasClinicas()
    planos_padrao.criar_planos_padrao_para_teste()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    linhas = [{"nome": "Filho", "data_nascimento": "2019-05-20",
               "responsavel_nome": "Familia", "responsavel_email": "lote@exemplo.com"}]
    r = autenticado(client, cen.gestor_a).post("/api/importacao/pacientes/confirmar", json={"linhas": linhas})
    assert r.status_code == 201, r.get_data(as_text=True)
    assert envios == []
