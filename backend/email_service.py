"""
E-mail por SMTP (spec PandaUp 12/10/2026, item B).

Configuração por variáveis de ambiente — sem SMTP_HOST, nada é enviado e o
sistema funciona como antes:
    SMTP_HOST, SMTP_PORTA (465 = SSL direto; 587 = STARTTLS), SMTP_USUARIO,
    SMTP_SENHA, EMAIL_REMETENTE ("PandaUp <nao-responda@pandaup.com.br>"),
    URL_APP (monta o link absoluto dos e-mails).

Começa com a caixa do cPanel; trocar para Brevo/Amazon SES é só mudar essas
variáveis. `enviar_email` nunca levanta exceção para quem chama: falha vira
o evento `email_falhou` (sem a senha) e devolve False.
"""
import html as _html
import os
import re
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import parseaddr

# Por operação de rede (conectar, TLS, login, envio): o pedido do usuário espera.
TIMEOUT_SEGUNDOS = 5
MARCA = "PandaUp"
_EMAIL_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def email_configurado():
    return bool(os.environ.get("SMTP_HOST", "").strip())


def _sem_quebras(texto):
    """Uma linha só: qualquer quebra (inclusive \\v, \\f, \\x85, \\u2028) vira espaço."""
    return " ".join(p.strip() for p in str(texto or "").splitlines() if p.strip())


def link_absoluto(link_relativo):
    """'#/redefinir-senha?token=x' → 'https://app.pandaup.com.br/#/redefinir-senha?token=x';
    sem URL_APP, None (um link relativo não serve num e-mail)."""
    base = os.environ.get("URL_APP", "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/{str(link_relativo).lstrip('/')}"


def _registrar_falha(para, erro):
    try:
        from db import log_evento
        log_evento(None, "email_falhou", "email", None, payload={"para": para, "erro": type(erro).__name__})
    except Exception:  # nunca deixar o registro de falha derrubar quem chamou
        pass


def enviar_email(para, assunto, texto, html=None):
    if not email_configurado():
        return False
    para = str(para or "")
    if "\r" in para or "\n" in para or not _EMAIL_VALIDO.match(para.strip()):
        return False
    para = para.strip()
    try:
        return _enviar(para, assunto, texto, html)
    except Exception as erro:  # porta inválida, cabeçalho estranho, SMTP fora do ar…
        _registrar_falha(para, erro)
        return False


def _enviar(para, assunto, texto, html):
    remetente =_sem_quebras(os.environ.get("EMAIL_REMETENTE") or os.environ.get("SMTP_USUARIO", ""))
    msg = EmailMessage()
    msg["From"] = remetente
    msg["To"] = para
    msg["Subject"] = _sem_quebras(assunto)
    if parseaddr(remetente)[1]:
        msg["Reply-To"] = parseaddr(remetente)[1]
    msg.set_content(texto or "")
    if html:
        msg.add_alternative(html, subtype="html")
    host = os.environ["SMTP_HOST"].strip()
    porta = int(os.environ.get("SMTP_PORTA", "465") or 465)
    usuario = os.environ.get("SMTP_USUARIO", "")
    senha = os.environ.get("SMTP_SENHA", "")
    contexto = ssl.create_default_context()
    if porta == 465:
        conexao = smtplib.SMTP_SSL(host, porta, timeout=TIMEOUT_SEGUNDOS, context=contexto)
    else:
        conexao = smtplib.SMTP(host, porta, timeout=TIMEOUT_SEGUNDOS)
    with conexao as s:
        if porta != 465:
            s.ehlo()
            s.starttls(context=contexto)
            s.ehlo()
        if usuario:
            s.login(usuario, senha)
        s.send_message(msg)
    return True


def enviar_em_segundo_plano(para, assunto, texto, html=None):
    """Envia sem segurar a resposta. Usado no "esqueci minha senha", que
    responde igual de qualquer jeito: assim um SMTP lento não prende o
    servidor, e o tempo de resposta não revela se a conta existe.
    Devolve a thread."""
    from flask import current_app
    app = current_app._get_current_object()

    def tarefa():
        with app.app_context():
            enviar_email(para, assunto, texto, html)

    t = threading.Thread(target=tarefa, daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------- Modelos

def _html_base(titulo, paragrafos, link, botao):
    corpo = "".join(f'<p style="margin:0 0 14px;font-size:15px;line-height:1.5;color:#26223A;">{p}</p>' for p in paragrafos)
    link_e = _html.escape(link, quote=True)
    return f"""<!doctype html><html><body style="margin:0;background:#F6F5FB;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 12px;"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#FFFFFF;border-radius:14px;padding:28px;">
<tr><td>
<p style="margin:0 0 18px;font-size:20px;font-weight:bold;color:#5B4FE9;">🐼 {MARCA}</p>
<h1 style="margin:0 0 16px;font-size:20px;color:#26223A;">{titulo}</h1>
{corpo}
<p style="margin:22px 0;"><a href="{link_e}" style="background:#5B4FE9;color:#FFFFFF;text-decoration:none;padding:12px 20px;border-radius:10px;font-weight:bold;display:inline-block;">{botao}</a></p>
<p style="margin:0;font-size:12px;color:#6A6280;">Se o botão não funcionar, copie e cole este endereço no navegador:<br>{link_e}</p>
</td></tr></table>
<p style="font-size:11px;color:#6A6280;margin-top:14px;">E-mail automático do {MARCA}. Não responda a esta mensagem.</p>
</td></tr></table></body></html>"""


def _texto_validade(minutos):
    if minutos % 60 == 0:
        horas = minutos // 60
        return f"{horas} hora{'s' if horas > 1 else ''}"
    return f"{minutos} minutos"


def email_redefinicao(nome, link):
    nome_e = _html.escape(nome or "")
    from tokens_service import VALIDADE_REDEFINICAO_MINUTOS
    validade = _texto_validade(VALIDADE_REDEFINICAO_MINUTOS)
    assunto = f"{MARCA}: redefinir sua senha"
    texto = (f"Olá, {nome or ''}!\n\nRecebemos um pedido para redefinir a sua senha no {MARCA}.\n"
             f"Use este link (vale por {validade}):\n{link}\n\nSe não foi você, ignore este e-mail: sua senha continua a mesma.\n")
    html = _html_base("Redefinir sua senha", [
        f"Olá, {nome_e}!", f"Recebemos um pedido para redefinir a sua senha no {MARCA}. O link vale por {validade}.",
        "Se não foi você, ignore este e-mail: sua senha continua a mesma."], link, "Criar nova senha")
    return assunto, texto, html


_PAPEIS = {"profissional": "profissional", "secretaria": "secretária", "gestor": "gestor(a)", "responsavel": "responsável",
           "admin_master": "administrador(a) da plataforma"}


def email_convite(nome, clinica, papel, link):
    from tokens_service import VALIDADE_CONVITE_MINUTOS
    validade = _texto_validade(VALIDADE_CONVITE_MINUTOS)
    papel_txt = _PAPEIS.get(papel, papel or "")
    nome_e, clinica_e = _html.escape(nome or ""), _html.escape(clinica or "")
    assunto = f"Seu acesso ao {MARCA}" + (f" — {_sem_quebras(clinica)}" if clinica else "")
    texto = (f"Olá, {nome or ''}!\n\n{clinica or 'A clínica'} convidou você para o {MARCA} como {papel_txt}.\n"
             f"Crie sua senha por este link (vale por {validade}):\n{link}\n")
    html = _html_base("Você foi convidado(a)", [
        f"Olá, {nome_e}!", f"<strong>{clinica_e or 'A clínica'}</strong> convidou você para o {MARCA} como {_html.escape(papel_txt)}.",
        f"Clique no botão para criar a sua senha e entrar. O link vale por {validade}."], link, "Criar minha senha")
    return assunto, texto, html


def enviar_convite(usuario_id, link_relativo):
    """Manda o convite de acesso por e-mail (nome, e-mail, papel e clínica
    lidos do banco). False quando o envio está desligado, sem URL_APP ou se
    falhar — quem chama continua devolvendo o link para copiar/WhatsApp."""
    if not email_configurado():
        return False
    link = link_absoluto(link_relativo)
    if not link:
        return False
    from db import query_one
    u = query_one(
        """SELECT u.nome, u.email, u.papel, o.nome AS clinica
           FROM usuarios u LEFT JOIN organizacoes o ON o.id = u.organizacao_id WHERE u.id = ?""",
        (usuario_id,),
    )
    if not u:
        return False
    assunto, texto, html = email_convite(u["nome"], u["clinica"] or f"A equipe {MARCA}", u["papel"], link)
    return enviar_email(u["email"], assunto, texto, html)
