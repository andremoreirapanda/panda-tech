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
from email.utils import formatdate, make_msgid, parseaddr

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
    # Cabeçalhos padrão que o smtplib não põe sozinho: sem Date e Message-ID
    # o e-mail perde pontos nos filtros de spam (relatório de 15/10/2026).
    dominio = (parseaddr(remetente)[1].rpartition("@")[2] or "pandaup.com.br").lower()
    msg = EmailMessage()
    msg["From"] = remetente
    msg["To"] = para
    msg["Subject"] = _sem_quebras(assunto)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=dominio)
    # Sempre texto puro + HTML, em quoted-printable (o mais aceito pelos filtros).
    msg.set_content(texto or "", cte="quoted-printable")
    if html:
        msg.add_alternative(html, subtype="html", cte="quoted-printable")
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
# Texto simples, sem emoji e sem imagem, com assunto que diz quem mandou e por
# quê: "acesso", "senha" e "convidado" no assunto são o padrão de phishing que
# os filtros barram (15/10/2026). O link aponta sempre para o próprio domínio
# (URL_APP), e o corpo traz o endereço por extenso além do botão.

def _cabecalho_marca():
    """Logo da plataforma (Perfil da Plataforma) no topo do e-mail, pelo endereço
    público do próprio domínio; sem logo enviado ou sem URL_APP, o nome em texto."""
    base = os.environ.get("URL_APP", "").strip().rstrip("/")
    versao = ""
    if base:
        try:
            from plataforma_service import versao_logo
            versao = versao_logo()
        except Exception:
            versao = ""
    if versao:
        src = _html.escape(f"{base}/api/publico/plataforma/logo?v={versao}", quote=True)
        return (f'<p style="margin:0 0 18px;"><img src="{src}" alt="{MARCA}" width="160" '
                f'style="display:block;width:160px;max-width:100%;height:auto;border:0;"></p>')
    return f'<p style="margin:0 0 18px;font-size:18px;font-weight:bold;color:#5B4FE9;">{MARCA}</p>'


def _html_base(titulo, paragrafos, link, botao, rodape, aviso=None):
    corpo = "".join(f'<p style="margin:0 0 14px;font-size:15px;line-height:1.5;color:#26223A;">{p}</p>' for p in paragrafos)
    bloco_aviso = (f'<p style="margin:18px 0 0;padding:12px 14px;background:#F1EFFD;border-radius:8px;'
                   f'font-size:14px;line-height:1.5;color:#26223A;">{aviso}</p>') if aviso else ""
    link_e = _html.escape(link, quote=True)
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>{titulo}</title></head>
<body style="margin:0;padding:24px 12px;background:#F6F5FB;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#FFFFFF;border-radius:12px;">
<tr><td style="padding:28px;">
{_cabecalho_marca()}
<h1 style="margin:0 0 16px;font-size:19px;color:#26223A;">{titulo}</h1>
{corpo}
<p style="margin:22px 0;"><a href="{link_e}" style="background:#5B4FE9;color:#FFFFFF;text-decoration:none;padding:12px 20px;border-radius:8px;font-weight:bold;display:inline-block;">{botao}</a></p>
<p style="margin:0;font-size:12px;line-height:1.5;color:#6A6280;">Ou copie este endereço no navegador:<br>{link_e}</p>
{bloco_aviso}
</td></tr></table>
<p style="max-width:520px;font-size:11px;line-height:1.5;color:#6A6280;margin:14px auto 0;">{rodape}</p>
</td></tr></table></body></html>"""


def _saudacao(nome):
    primeiro = (_sem_quebras(nome).split(" ") or [""])[0]
    return f"Olá, {primeiro}!" if primeiro else "Olá!"


def _texto_validade(minutos):
    if minutos % 60 == 0:
        horas = minutos // 60
        return f"{horas} hora{'s' if horas > 1 else ''}"
    return f"{minutos} minutos"


def _avisos_login(login):
    """(26/10/2026) As famílias voltavam sempre ao link de convite, que só
    serve uma vez: o e-mail diz por onde entrar depois. (texto, html) ou ("", None)."""
    if not login:
        return "", None
    texto = (f"Importante: este link serve só para criar a senha e funciona uma vez. "
             f"Depois, entre sempre por:\n{login}\n(salve nos favoritos)\n\n")
    html = (f"<strong>Importante:</strong> este link serve só para criar a senha e funciona uma vez. "
            f"Depois, entre sempre por <a href=\"{_html.escape(login, quote=True)}\" style=\"color:#5B4FE9;\">"
            f"{_html.escape(login)}</a> (salve nos favoritos).")
    return texto, html


def email_redefinicao(nome, link, login=None):
    from tokens_service import VALIDADE_REDEFINICAO_MINUTOS
    validade = _texto_validade(VALIDADE_REDEFINICAO_MINUTOS)
    saudacao = _saudacao(nome)
    aviso_texto, aviso_html = _avisos_login(login)
    assunto = f"Redefinição solicitada no {MARCA}"
    rodape = f"Mensagem automática do {MARCA}, enviada porque alguém pediu uma nova senha para este e-mail."
    texto = (f"{saudacao}\n\n"
             f"Recebemos um pedido para criar uma nova senha na sua conta do {MARCA}.\n"
             f"Para continuar, abra o endereço abaixo (vale por {validade}):\n\n{link}\n\n"
             f"{aviso_texto}"
             f"Se você não fez esse pedido, ignore esta mensagem: nada muda na sua conta.\n\n"
             f"Equipe {MARCA}\n")
    html = _html_base("Pedido de nova senha", [
        _html.escape(saudacao),
        f"Recebemos um pedido para criar uma nova senha na sua conta do {MARCA}. O link vale por {validade}.",
        "Se você não fez esse pedido, ignore esta mensagem: nada muda na sua conta."],
        link, "Criar nova senha", rodape, aviso=aviso_html)
    return assunto, texto, html


_PAPEIS = {"profissional": "profissional", "secretaria": "secretária", "gestor": "gestor(a)", "responsavel": "responsável",
           "admin_master": "administrador(a) da plataforma"}


def email_convite(nome, clinica, papel, link, login=None):
    from tokens_service import VALIDADE_CONVITE_MINUTOS
    validade = _texto_validade(VALIDADE_CONVITE_MINUTOS)
    papel_txt = _PAPEIS.get(papel, papel or "")
    saudacao = _saudacao(nome)
    aviso_texto, aviso_html = _avisos_login(login)
    clinica_txt = _sem_quebras(clinica)
    quem = clinica_txt or f"A equipe {MARCA}"
    # Textos do assunto e do título escolhidos pelo usuário (15/10/2026).
    # ("cadastro" no lugar de "acesso", que é gatilho de spam no assunto).
    assunto = f"Seu cadastro no App {MARCA} foi solicitado" + (f" pela {clinica_txt}" if clinica_txt else "")
    rodape = (f"Mensagem automática do {MARCA}, enviada porque {_html.escape(quem)} cadastrou este e-mail. "
              f"Se você não esperava por ela, pode ignorar.")
    texto = (f"{saudacao}\n\n"
             f"{quem} cadastrou você no {MARCA} como {papel_txt}.\n"
             f"Para ativar o cadastro, abra o endereço abaixo e escolha a sua senha (vale por {validade}):\n\n{link}\n\n"
             f"{aviso_texto}"
             f"Se você não esperava por esta mensagem, pode ignorar.\n\n"
             f"Equipe {MARCA}\n")
    html = _html_base(f"Você foi cadastrado no App {MARCA}!", [
        _html.escape(saudacao),
        f"<strong>{_html.escape(quem)}</strong> cadastrou você no {MARCA} como {_html.escape(papel_txt)}.",
        f"Para ativar o cadastro, clique no botão e escolha a sua senha. O link vale por {validade}."],
        link, "Ativar meu cadastro", rodape, aviso=aviso_html)
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
    from identidade_service import login_relativo_do_usuario
    login = link_absoluto(login_relativo_do_usuario(usuario_id))
    assunto, texto, html = email_convite(u["nome"], u["clinica"], u["papel"], link, login=login)
    return enviar_email(u["email"], assunto, texto, html)
