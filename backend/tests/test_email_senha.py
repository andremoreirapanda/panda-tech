"""Esqueci minha senha por e-mail (spec PandaUp 12/10/2026, item B)."""
import pytest

import auth
import email_service
from factories import novo_usuario

MENSAGEM = ("Se este e-mail estiver cadastrado, você vai receber um link em alguns minutos. "
            "Não chegou? Confira a caixa de spam e se digitou o mesmo e-mail que a clínica cadastrou. "
            "Se ainda assim não chegar, peça um novo link de acesso à sua clínica.")


@pytest.fixture()
def envios(monkeypatch):
    monkeypatch.setattr(auth, "_DEV_MODE", False)
    monkeypatch.setenv("SMTP_HOST", "mail.pandaup.com.br")
    monkeypatch.setenv("URL_APP", "https://app.pandaup.com.br")
    lista = []

    def falso(para, assunto, texto, html=None):
        lista.append({"para": para, "assunto": assunto, "texto": texto, "html": html})
        return True

    monkeypatch.setattr(email_service, "enviar_email", falso)
    return lista


def _pedir(client, email):
    return client.post("/api/auth/esqueci-senha", json={"email": email})


def test_conta_ativa_recebe_link_por_email(client, db_ctx, envios):
    novo_usuario(None, "Ana", "ana@familia.com", "responsavel")
    r = _pedir(client, "ana@familia.com")
    assert r.status_code == 200
    assert r.get_json() == {"mensagem": MENSAGEM}
    assert len(envios) == 1 and envios[0]["para"] == "ana@familia.com"
    link = next(p for p in envios[0]["texto"].split() if p.startswith("https://app.pandaup.com.br/#/redefinir-senha?token="))
    token = link.split("token=")[1]
    assert client.get(f"/api/auth/validar-token-redefinicao/{token}").get_json()["valido"] is True
    assert "token" not in r.get_data(as_text=True)


@pytest.mark.parametrize("extra", [None, {"ativo": 0}, {"excluido_em": "2026-10-01 10:00:00"}])
def test_conta_inexistente_inativa_ou_excluida_responde_igual_sem_enviar(client, db_ctx, envios, extra):
    if extra is not None:
        novo_usuario(None, "Bia", "bia@familia.com", "responsavel", **extra)
    r = _pedir(client, "bia@familia.com")
    assert r.status_code == 200 and r.get_json() == {"mensagem": MENSAGEM}
    assert envios == []


def test_email_com_maiusculas_e_espacos_acha_a_conta(client, db_ctx, envios):
    novo_usuario(None, "Ana", "ana@familia.com", "responsavel")
    _pedir(client, "  Ana@Familia.COM ")
    assert [e["para"] for e in envios] == ["ana@familia.com"]


def test_sem_email_configurado_orienta_pedir_a_clinica(client, db_ctx, envios, monkeypatch):
    monkeypatch.delenv("SMTP_HOST")
    novo_usuario(None, "Ana", "ana@familia.com", "responsavel")
    corpo = _pedir(client, "ana@familia.com").get_json()
    assert "PandaUp" in corpo["mensagem"] and "link_redefinicao" not in corpo
    assert envios == []
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM tokens_redefinicao_senha")["n"] == 0


def test_desenvolvimento_continua_devolvendo_link(client, db_ctx, envios, monkeypatch):
    monkeypatch.setattr(auth, "_DEV_MODE", True)
    novo_usuario(None, "Ana", "ana@familia.com", "responsavel")
    assert _pedir(client, "ana@familia.com").get_json().get("link_redefinicao")
