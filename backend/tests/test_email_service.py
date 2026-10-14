"""E-mail por SMTP (spec PandaUp 12/10/2026, item B)."""
import json

import pytest

import email_service as es


class SMTPFalso:
    """Guarda o que o módulo faz com a conexão; `falhar_em` simula erro."""
    instancias = []
    falhar_em = None

    def __init__(self, host, porta, timeout=None, context=None):
        self.host, self.porta, self.timeout, self.context = host, porta, timeout, context
        self.chamadas, self.mensagens = [], []
        SMTPFalso.instancias.append(self)
        if SMTPFalso.falhar_em == "conectar":
            raise OSError("sem conexão")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        self.chamadas.append("ehlo")

    def starttls(self, context=None):
        self.chamadas.append("starttls")

    def login(self, usuario, senha):
        self.chamadas.append(("login", usuario))
        if SMTPFalso.falhar_em == "login":
            raise Exception("senha errada")

    def send_message(self, msg):
        self.chamadas.append("send")
        self.mensagens.append(msg)


class SSLFalso(SMTPFalso):
    pass


@pytest.fixture()
def smtp(monkeypatch):
    SMTPFalso.instancias, SMTPFalso.falhar_em = [], None
    monkeypatch.setattr(es.smtplib, "SMTP", SMTPFalso)
    monkeypatch.setattr(es.smtplib, "SMTP_SSL", SSLFalso)
    for k, v in {"SMTP_HOST": "mail.pandaup.com.br", "SMTP_PORTA": "465", "SMTP_USUARIO": "nao-responda@pandaup.com.br",
                 "SMTP_SENHA": "segredo", "EMAIL_REMETENTE": "PandaUp <nao-responda@pandaup.com.br>",
                 "URL_APP": "https://app.pandaup.com.br/"}.items():
        monkeypatch.setenv(k, v)
    return SMTPFalso


def test_sem_host_nao_envia(monkeypatch, smtp):
    monkeypatch.delenv("SMTP_HOST")
    assert es.email_configurado() is False
    assert es.enviar_email("ana@familia.com", "Oi", "texto") is False
    assert smtp.instancias == []


def test_porta_465_usa_ssl(db_ctx, smtp):
    assert es.enviar_email("ana@familia.com", "Assunto", "texto", "<p>html</p>") is True
    con = smtp.instancias[0]
    assert isinstance(con, SSLFalso) and con.porta == 465 and con.timeout == 5
    assert ("login", "nao-responda@pandaup.com.br") in con.chamadas and "starttls" not in con.chamadas
    msg = con.mensagens[0]
    assert msg["From"] == "PandaUp <nao-responda@pandaup.com.br>" and msg["To"] == "ana@familia.com" and msg["Subject"] == "Assunto"
    assert msg.get_content_type() == "multipart/alternative"
    tipos = [p.get_content_type() for p in msg.iter_parts()]
    assert tipos == ["text/plain", "text/html"]


def test_porta_587_usa_starttls(db_ctx, smtp, monkeypatch):
    monkeypatch.setenv("SMTP_PORTA", "587")
    assert es.enviar_email("ana@familia.com", "Assunto", "texto") is True
    con = smtp.instancias[0]
    assert not isinstance(con, SSLFalso) and con.porta == 587
    assert con.chamadas.index("starttls") < con.chamadas.index(("login", "nao-responda@pandaup.com.br"))


@pytest.mark.parametrize("onde", ["conectar", "login"])
def test_falha_vira_false_e_evento_sem_senha(db_ctx, smtp, onde):
    smtp.falhar_em = onde
    assert es.enviar_email("ana@familia.com", "Assunto", "texto") is False
    ev = db_ctx.query_one("SELECT * FROM eventos WHERE tipo = 'email_falhou'")
    assert ev and "segredo" not in (ev["payload_json"] or "")
    assert json.loads(ev["payload_json"])["para"] == "ana@familia.com"


@pytest.mark.parametrize("para", ["", "sem-arroba", "ana@familia.com\r\nBcc: x@y.com", "ana@familia.com\nx"])
def test_destinatario_invalido_nao_conecta(smtp, para):
    assert es.enviar_email(para, "Assunto", "texto") is False
    assert smtp.instancias == []


def test_assunto_com_quebra_de_linha_e_limpo(db_ctx, smtp):
    es.enviar_email("ana@familia.com", "Linha 1\r\nBcc: x@y.com", "texto")
    assert smtp.instancias[0].mensagens[0]["Subject"] == "Linha 1 Bcc: x@y.com"


def test_link_absoluto(monkeypatch):
    monkeypatch.setenv("URL_APP", "https://app.pandaup.com.br/")
    assert es.link_absoluto("#/redefinir-senha?token=x") == "https://app.pandaup.com.br/#/redefinir-senha?token=x"
    monkeypatch.delenv("URL_APP")
    assert es.link_absoluto("#/redefinir-senha?token=x") is None


def test_modelos_escapam_e_tem_marca():
    assunto, texto, html = es.email_convite("<script>x</script>", "Clínica <b>Sol</b>", "profissional", "https://l/1")
    assert "PandaUp" in assunto + texto + html and "https://l/1" in texto and "https://l/1" in html
    assert "<script>" not in html and "&lt;script&gt;" in html and "<b>Sol</b>" not in html
    assunto, texto, html = es.email_redefinicao("Ana", "https://l/2")
    assert "PandaUp" in assunto + html and "https://l/2" in texto and "https://l/2" in html


def test_porta_invalida_vira_false_sem_excecao(db_ctx, smtp, monkeypatch):
    monkeypatch.setenv("SMTP_PORTA", "abc")
    assert es.enviar_email("ana@familia.com", "Assunto", "texto") is False


@pytest.mark.parametrize("quebra", ["\x0b", "\x0c", "\x1c", "\x85", " "])
def test_assunto_com_qualquer_quebra_unicode_e_limpo(db_ctx, smtp, quebra):
    assert es.enviar_email("ana@familia.com", f"Clínica{quebra}Sol", "texto") is True
    assert smtp.instancias[0].mensagens[0]["Subject"] == "Clínica Sol"


def test_convite_com_nome_de_clinica_estranho_nao_levanta(db_ctx, smtp):
    from factories import nova_organizacao, novo_usuario
    org = nova_organizacao("Clínica\x0bSol")
    u = novo_usuario(org, "Fono\x0bNova", "fono@sol.com", "profissional")
    assert es.enviar_convite(u["id"], "#/redefinir-senha?token=x") is True


def test_envio_em_segundo_plano_nao_espera_o_smtp(db_ctx, smtp, monkeypatch):
    import threading
    import time
    liberar = threading.Event()

    def lento(para, assunto, texto, html=None):
        liberar.wait(5)
        return True

    monkeypatch.setattr(es, "enviar_email", lento)
    inicio = time.monotonic()
    t = es.enviar_em_segundo_plano("ana@familia.com", "Assunto", "texto")
    assert time.monotonic() - inicio < 1 and t.is_alive()
    liberar.set()
    t.join(5)
    assert not t.is_alive()


# ---------------------------------------------------------------- Entrega (15/10/2026: e-mails caindo no spam)

def test_cabecalhos_date_e_message_id(db_ctx, smtp):
    from email.utils import parsedate_to_datetime
    es.enviar_email("ana@familia.com", "Assunto", "texto", "<p>html</p>")
    msg = smtp.instancias[0].mensagens[0]
    assert parsedate_to_datetime(msg["Date"]) is not None
    assert msg["Message-ID"].startswith("<") and msg["Message-ID"].endswith("@pandaup.com.br>")
    assert msg["Reply-To"] is None  # igual ao remetente, só somava pontos de "cabeçalho incomum"


def test_texto_puro_e_html_em_quoted_printable(db_ctx, smtp):
    es.enviar_email("ana@familia.com", "Assunto", "Olá, ação!", "<p>Olá, ação!</p>")
    partes = list(smtp.instancias[0].mensagens[0].iter_parts())
    assert [p.get_content_type() for p in partes] == ["text/plain", "text/html"]
    assert all(p["Content-Transfer-Encoding"] == "quoted-printable" for p in partes)
    assert partes[0].get_content().strip() == "Olá, ação!"


@pytest.mark.parametrize("modelo", ["redefinicao", "convite"])
def test_modelos_sem_cara_de_phishing(modelo):
    if modelo == "redefinicao":
        assunto, texto, html = es.email_redefinicao("Ana", "https://app.pandaup.com.br/#/redefinir-senha?token=x")
    else:
        assunto, texto, html = es.email_convite("Ana", "Clínica Sol", "responsavel", "https://app.pandaup.com.br/#/redefinir-senha?token=x")
    for palavra in ("senha", "acesso", "convidad", "login"):
        assert palavra not in assunto.lower(), assunto
    assert "🐼" not in html and "🐼" not in texto
    assert "convidado(a)" not in html.lower()
    assert "https://app.pandaup.com.br/#/redefinir-senha?token=x" in texto


def test_assunto_do_convite_diz_quem_cadastrou():
    assunto, texto, _ = es.email_convite("Ana", "Clínica Sol", "responsavel", "https://l/1")
    assert "Clínica Sol" in assunto and "PandaUp" in assunto
    assunto_sem_clinica, _, _ = es.email_convite("Ana", None, "admin_master", "https://l/1")
    assert "PandaUp" in assunto_sem_clinica
