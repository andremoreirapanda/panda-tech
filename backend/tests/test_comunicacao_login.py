"""Levar quem criou a senha para a tela de entrar (26/10/2026): famílias
voltavam sempre ao link de convite (que só serve uma vez) e caíam em
"Link expirado ou já usado"."""
import db
import email_service
import identidade_service
from factories import DuasClinicas
from modulos_service import definir_liberacao_admin
from tokens_service import gerar_token


def _validar(client, token):
    return client.get(f"/api/auth/validar-token-redefinicao/{token}").get_json()


def _com_login_proprio(org_id, endereco="clinica-a"):
    db.execute("UPDATE organizacoes SET endereco_login = ? WHERE id = ?", (endereco, org_id))
    definir_liberacao_admin(org_id, "white_label", True)


# ---------------------------------------------------------------- endereço de login

def test_login_padrao_sem_tela_propria(db_ctx):
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET endereco_login = 'clinica-a' WHERE id = ?", (cen.org_a,))
    assert identidade_service.login_relativo_da_clinica(cen.org_a) == "#/login"  # sem o módulo
    assert identidade_service.login_relativo_da_clinica(None) == "#/login"


def test_login_da_clinica_com_tela_propria(db_ctx):
    cen = DuasClinicas()
    _com_login_proprio(cen.org_a)
    assert identidade_service.login_relativo_da_clinica(cen.org_a) == "#/entrar/clinica-a"
    db.execute("UPDATE organizacoes SET status_comercial = 'cancelada' WHERE id = ?", (cen.org_a,))
    assert identidade_service.login_relativo_da_clinica(cen.org_a) == "#/login"


# ---------------------------------------------------------------- situação do link

def test_link_valido_traz_o_login(client, db_ctx):
    cen = DuasClinicas()
    _com_login_proprio(cen.org_a)
    d = _validar(client, gerar_token(cen.resp_a1["id"], tipo="convite"))
    assert d["valido"] is True and d["login"] == "#/entrar/clinica-a"


def test_link_ja_usado(client, db_ctx):
    cen = DuasClinicas()
    _com_login_proprio(cen.org_a)
    token = gerar_token(cen.resp_a1["id"], tipo="convite")
    assert client.post("/api/auth/redefinir-senha", json={"token": token, "nova_senha": "senhanova123"}).status_code == 200
    d = _validar(client, token)
    assert d == {"valido": False, "motivo": "usado", "login": "#/entrar/clinica-a"}


def test_link_vencido(client, db_ctx):
    cen = DuasClinicas()
    token = gerar_token(cen.resp_a1["id"], tipo="convite")
    db.execute("UPDATE tokens_redefinicao_senha SET expira_em = '2020-01-01 00:00:00' WHERE token = ?", (token,))
    assert _validar(client, token) == {"valido": False, "motivo": "expirado", "login": "#/login"}


def test_link_que_nao_existe_nao_revela_nada(client, db_ctx):
    assert _validar(client, "nao-existe") == {"valido": False, "motivo": "invalido", "login": "#/login"}


# ---------------------------------------------------------------- e-mails

def test_emails_dizem_por_onde_entrar(db_ctx, monkeypatch):
    login = "https://app.pandaup.com.br/#/login"
    for _, texto, html in (es for es in (
            email_service.email_convite("Ana", "Clínica Sol", "responsavel", "https://l/1", login=login),
            email_service.email_redefinicao("Ana", "https://l/2", login=login))):
        assert "funciona uma vez" in texto and login in texto
        assert "funciona uma vez" in html and login in html


def test_convite_por_email_usa_o_login_da_clinica(client, db_ctx, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "mail.pandaup.com.br")
    monkeypatch.setenv("URL_APP", "https://app.pandaup.com.br")
    enviados = []
    monkeypatch.setattr(email_service, "enviar_email", lambda para, assunto, texto, html=None: enviados.append(texto) or True)
    cen = DuasClinicas()
    _com_login_proprio(cen.org_a)
    assert email_service.enviar_convite(cen.resp_a1["id"], "#/redefinir-senha?token=x") is True
    assert "https://app.pandaup.com.br/#/entrar/clinica-a" in enviados[0]
