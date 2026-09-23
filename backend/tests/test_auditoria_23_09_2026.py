"""
Regressão para os achados da revisão de segurança de 23/09/2026:

1. Limite de tentativas de login contornável trocando o X-Forwarded-For.
2. Campos de emoji (logo da clínica, ícone de pasta, mascote na criação do
   paciente) aceitavam HTML.
3. "Esqueci minha senha" devolvia o link de redefinição na resposta também
   em produção (tomada de qualquer conta) + a rota nova do admin para
   reenviar o link de acesso ao gestor, que substitui esse caminho.
"""
import auth
import rate_limit
from factories import DuasClinicas, novo_usuario

from conftest import autenticado
from validacao_campos import emoji_seguro

HTML = '<img src=x onerror="alert(1)">'


# ---------------------------------------------------------------- 1. Rate limit

def _login_errado(client, email="ninguem@teste.com", **headers):
    return client.post("/api/auth/login", json={"email": email, "senha": "errada"}, headers=headers).status_code


def test_trocar_x_forwarded_for_nao_contorna_limite_de_login(client, db_ctx):
    codigos = [_login_errado(client, **{"X-Forwarded-For": f"10.0.0.{i}"}) for i in range(15)]
    assert codigos[:10] == [401] * 10, codigos
    assert set(codigos[10:]) == {429}, codigos


def test_limite_por_email_segura_ataque_vindo_de_muitos_ips(client, db_ctx):
    codigos = [
        client.post("/api/auth/login", json={"email": "alvo@teste.com", "senha": "errada"},
                    environ_base={"REMOTE_ADDR": f"10.1.0.{i}"}).status_code
        for i in range(25)
    ]
    assert codigos[:20] == [401] * 20, codigos
    assert set(codigos[20:]) == {429}, codigos


def test_limite_por_email_nao_afeta_outra_conta(client, db_ctx):
    for i in range(20):
        client.post("/api/auth/login", json={"email": "alvo@teste.com", "senha": "errada"},
                    environ_base={"REMOTE_ADDR": f"10.2.0.{i}"})
    r = client.post("/api/auth/login", json={"email": "outra@teste.com", "senha": "errada"},
                    environ_base={"REMOTE_ADDR": "10.2.1.1"})
    assert r.status_code == 401, r.get_data(as_text=True)


def test_proxy_confiavel_usa_o_ip_mais_a_direita(client, db_ctx, monkeypatch):
    monkeypatch.setattr(rate_limit, "_PROXIES_CONFIAVEIS", 1)
    # O cliente forja o começo da cadeia; o proxy acrescenta o IP real no fim.
    codigos = [_login_errado(client, **{"X-Forwarded-For": f"1.2.3.{i}, 200.0.0.1"}) for i in range(12)]
    assert codigos[10:] == [429, 429], codigos


# ---------------------------------------------------------------- 2. Emojis

def test_emoji_seguro():
    assert emoji_seguro("🐼", "x") == "🐼"
    assert emoji_seguro("👨‍👩‍👧‍👦", "x") == "👨‍👩‍👧‍👦"
    assert emoji_seguro("1️⃣", "x") == "1️⃣"
    assert emoji_seguro(HTML, "x") == "x"
    assert emoji_seguro("abc", "x") == "x"
    assert emoji_seguro("123", "x") == "x"
    assert emoji_seguro("", "x") == "x"
    assert emoji_seguro(None, "x") == "x"
    assert emoji_seguro(42, "x") == "x"
    assert emoji_seguro("🐼" * 20, "x") == "x"


def test_logo_emoji_da_clinica_recusa_html(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    r = c.put("/api/pessoas/organizacao", json={"logo_emoji": HTML})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert db_ctx.query_one("SELECT logo_emoji FROM organizacoes WHERE id = ?", (cen.org_a,))["logo_emoji"] != HTML

    r = c.put("/api/pessoas/organizacao", json={"logo_emoji": "🦋"})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert db_ctx.query_one("SELECT logo_emoji FROM organizacoes WHERE id = ?", (cen.org_a,))["logo_emoji"] == "🦋"


def test_admin_criar_clinica_recusa_logo_html(client, db_ctx):
    db_ctx.execute("INSERT INTO planos (codigo, nome, preco_mensal_centavos) VALUES (?, ?, ?)", ("premium", "Premium", 19900))
    admin = novo_usuario(None, "Admin", "admin@plataforma.com", "admin_master")
    r = autenticado(client, admin).post("/api/admin/clinicas", json={
        "nome": "Clínica Nova", "plano": "premium", "gestor_email": "gestor@nova.com", "logo_emoji": HTML,
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    org = db_ctx.query_one("SELECT logo_emoji FROM organizacoes WHERE id = ?", (r.get_json()["id"],))
    assert org["logo_emoji"] == "🌟"


def test_icone_da_pasta_recusa_html(client, db_ctx):
    cen = DuasClinicas()
    c = autenticado(client, cen.gestor_a)
    r = c.post("/api/biblioteca/categorias", json={"nome": "Pasta", "icone_emoji": HTML})
    assert r.status_code == 201, r.get_data(as_text=True)
    cat_id = r.get_json()["id"]
    assert db_ctx.query_one("SELECT icone_emoji FROM categorias_exercicio WHERE id = ?", (cat_id,))["icone_emoji"] == "📘"

    c.put(f"/api/biblioteca/categorias/{cat_id}", json={"nome": "Pasta", "icone_emoji": "🎨"})
    c.put(f"/api/biblioteca/categorias/{cat_id}", json={"nome": "Pasta", "icone_emoji": HTML})
    assert db_ctx.query_one("SELECT icone_emoji FROM categorias_exercicio WHERE id = ?", (cat_id,))["icone_emoji"] == "🎨"


def test_criar_paciente_recusa_mascote_fora_da_lista(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/pessoas/pacientes", json={
        "nome": "Criança", "data_nascimento": "2019-05-05", "avatar_mascote": HTML,
    })
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    paciente = db_ctx.query_one("SELECT avatar_mascote FROM pacientes WHERE nome = 'Criança'")
    assert paciente["avatar_mascote"] == "🐻"


# ---------------------------------------------------------------- 3. Recuperação de acesso

def test_esqueci_senha_nao_devolve_link_em_producao(client, db_ctx):
    cen = DuasClinicas()
    r = client.post("/api/auth/esqueci-senha", json={"email": "gestora@a.com"})
    assert r.status_code == 200
    corpo = r.get_json()
    assert "link_redefinicao" not in corpo, corpo
    assert "token" not in r.get_data(as_text=True)
    assert db_ctx.query_one(
        "SELECT COUNT(*) AS n FROM tokens_redefinicao_senha WHERE usuario_id = ?", (cen.gestor_a["id"],)
    )["n"] == 0


def test_esqueci_senha_devolve_link_em_desenvolvimento(client, db_ctx, monkeypatch):
    monkeypatch.setattr(auth, "_DEV_MODE", True)
    DuasClinicas()
    r = client.post("/api/auth/esqueci-senha", json={"email": "gestora@a.com"})
    assert r.get_json().get("link_redefinicao"), r.get_json()


def test_admin_reenvia_link_de_acesso_ao_gestor(client, db_ctx):
    cen = DuasClinicas()
    admin = novo_usuario(None, "Admin", "admin@plataforma.com", "admin_master")
    c = autenticado(client, admin)

    clinica = next(o for o in c.get("/api/admin/clinicas").get_json() if o["id"] == cen.org_a)
    assert [gst["id"] for gst in clinica["gestores"]] == [cen.gestor_a["id"]]

    r = c.post(f"/api/admin/clinicas/{cen.org_a}/gestores/{cen.gestor_a['id']}/reenviar-convite")
    assert r.status_code == 200, r.get_data(as_text=True)
    token = r.get_json()["link_convite"].split("token=")[1]

    r = client.post("/api/auth/redefinir-senha", json={"token": token, "nova_senha": "novasenha123"})
    assert r.status_code == 200, r.get_data(as_text=True)
    r = client.post("/api/auth/login", json={"email": "gestora@a.com", "senha": "novasenha123"})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_reenviar_link_do_gestor_valida_clinica_e_papel(client, db_ctx):
    cen = DuasClinicas()
    admin = novo_usuario(None, "Admin", "admin@plataforma.com", "admin_master")
    c = autenticado(client, admin)
    # Gestor de outra clínica, e usuário que não é gestor.
    assert c.post(f"/api/admin/clinicas/{cen.org_a}/gestores/{cen.gestor_b['id']}/reenviar-convite").status_code == 404
    assert c.post(f"/api/admin/clinicas/{cen.org_a}/gestores/{cen.prof_a1['id']}/reenviar-convite").status_code == 404


def test_reenviar_link_do_gestor_e_exclusivo_do_admin(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post(
        f"/api/admin/clinicas/{cen.org_a}/gestores/{cen.gestor_a['id']}/reenviar-convite"
    )
    assert r.status_code == 403, r.get_data(as_text=True)
