"""Testar a credencial do Mercado Pago da plataforma (14/10/2026): o Admin vê
de qual conta é o Access Token salvo, e um token errado não chega a ser salvo."""
import pytest

import pagamento_plataforma_service as pps
from db import obter_config_integracao_plataforma
from factories import novo_usuario

from conftest import autenticado

TOKEN = "APP_USR-1234567890123456-101012-abcdef0123456789abcdef0123456789-123456789"
PUBLIC_KEY = "APP_USR-1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
SEGREDO = "segredo-do-webhook"


@pytest.fixture()
def mp(monkeypatch):
    """Consulta ao Mercado Pago simulada: `respostas[token]` ou 401."""
    chamadas = []
    respostas = {TOKEN: {"status": 200, "response": {"id": 3645457488, "nickname": "PANDAUP", "email": "x@y.com"}}}

    def consultar(token):
        chamadas.append(token)
        if isinstance(respostas.get(token), Exception):
            raise respostas[token]
        return respostas.get(token, {"status": 401, "response": {"message": "invalid access token"}})

    monkeypatch.setattr(pps, "_consultar_conta", consultar)
    return {"chamadas": chamadas, "respostas": respostas}


def _admin(client):
    return autenticado(client, novo_usuario(None, "Admin", "admin@plataforma.com", "admin_master"))


def _salvar(c, **campos):
    corpo = {"access_token": TOKEN, "public_key": PUBLIC_KEY, "webhook_secret": SEGREDO}
    corpo.update(campos)
    return c.post("/api/admin/integracoes/mercadopago", json=corpo)


def test_salvar_token_certo_grava(client, db_ctx, mp):
    r = _salvar(_admin(client))
    assert r.status_code == 200, r.get_data(as_text=True)
    cfg = obter_config_integracao_plataforma("mercadopago")
    assert cfg["access_token"] == TOKEN and cfg["public_key"] == PUBLIC_KEY and cfg["webhook_secret"] == SEGREDO
    assert r.get_json()["conta"]["nome"] == "PANDAUP"


@pytest.mark.parametrize("token, trecho", [
    (PUBLIC_KEY, "Public Key"),
    ("TEST-1234567890123456-101012-abcdef0123456789abcdef0123456789-123456789", "TESTE"),
    ("abc123", "APP_USR-"),
])
def test_formato_errado_nao_grava_e_nem_consulta(client, db_ctx, mp, token, trecho):
    r = _salvar(_admin(client), access_token=token)
    assert r.status_code == 400 and trecho in r.get_json()["erro"]
    assert obter_config_integracao_plataforma("mercadopago") == {} and mp["chamadas"] == []


def test_public_key_no_lugar_errado(client, db_ctx, mp):
    r = _salvar(_admin(client), public_key=TOKEN)
    assert r.status_code == 400 and "Public Key" in r.get_json()["erro"]


def test_mercado_pago_recusa_nao_grava(client, db_ctx, mp):
    outro = "APP_USR-9999999999999999-101012-ffffffffffffffffffffffffffffffff-999999999"
    r = _salvar(_admin(client), access_token=outro)
    assert r.status_code == 400 and "recusou" in r.get_json()["erro"]
    assert obter_config_integracao_plataforma("mercadopago") == {}


def test_sem_conexao_com_mercado_pago_nao_grava(client, db_ctx, mp):
    mp["respostas"][TOKEN] = OSError("timeout")
    r = _salvar(_admin(client))
    assert r.status_code == 400 and "tente de novo" in r.get_json()["erro"]
    assert obter_config_integracao_plataforma("mercadopago") == {}


def test_testar_conexao_do_token_salvo(client, db_ctx, mp):
    c = _admin(client)
    _salvar(c)
    r = c.post("/api/admin/integracoes/mercadopago/testar")
    assert r.status_code == 200
    corpo = r.get_json()
    assert corpo["ok"] is True and corpo["conta"] == {"id": 3645457488, "nome": "PANDAUP"}
    assert TOKEN not in r.get_data(as_text=True)


def test_testar_conexao_aponta_token_salvo_errado(client, db_ctx, mp):
    # Caso real de 14/10/2026: a Public Key tinha ido para o campo do Access Token.
    from db import salvar_config_integracao_plataforma
    salvar_config_integracao_plataforma("mercadopago", {"access_token": PUBLIC_KEY, "public_key": ""}, status="conectado")
    corpo = _admin(client).post("/api/admin/integracoes/mercadopago/testar").get_json()
    assert corpo["ok"] is False and "Public Key" in corpo["erro"]


def test_testar_sem_token_salvo(client, db_ctx, mp):
    corpo = _admin(client).post("/api/admin/integracoes/mercadopago/testar").get_json()
    assert corpo["ok"] is False and mp["chamadas"] == []


def test_so_admin_testa(client, db_ctx, mp):
    gestor = novo_usuario(None, "Gi", "gi@x.com", "gestor")
    assert autenticado(client, gestor).post("/api/admin/integracoes/mercadopago/testar").status_code == 403
