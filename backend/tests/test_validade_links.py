"""Links de acesso valem 24 horas (pedido do usuário, 14/10/2026): o de
"Esqueci minha senha" (era 1 hora) e o de convite/"Reenviar link" (era 3 dias)."""
from datetime import datetime, timedelta

import pytest

import email_service
import tokens_service
from factories import novo_usuario


@pytest.mark.parametrize("tipo", ["redefinicao", "convite"])
def test_link_vale_24_horas(db_ctx, tipo):
    u = novo_usuario(None, "Ana", "ana@familia.com", "responsavel")
    antes = datetime.now()
    token = tokens_service.gerar_token(u["id"], tipo=tipo)
    linha = db_ctx.query_one("SELECT expira_em FROM tokens_redefinicao_senha WHERE token = ?", (token,))
    expira = datetime.strptime(str(linha["expira_em"])[:19], "%Y-%m-%d %H:%M:%S")
    assert timedelta(hours=23, minutes=59) <= expira - antes <= timedelta(hours=24, minutes=1)
    assert tokens_service.token_valido(token)


def test_emails_dizem_24_horas():
    _, texto, html = email_service.email_redefinicao("Ana", "https://l/1")
    assert "24 horas" in texto and "24 horas" in html and "1 hora" not in texto
    _, texto, html = email_service.email_convite("Ana", "Clínica Sol", "responsavel", "https://l/2")
    assert "24 horas" in texto and "24 horas" in html
