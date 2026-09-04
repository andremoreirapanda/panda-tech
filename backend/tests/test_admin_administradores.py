"""
Regressão para a gestão de administradores da plataforma (tela "Perfil da
Plataforma", insight do usuário, 04/09/2026): antes disso o único
admin_master do sistema nascia direto pelo seed.py, sem nenhum jeito de
incluir um segundo pelo próprio app. Reaproveita o mesmo padrão de convite
por link já usado em Equipe (ver test_secretaria.py). Cobre: criação,
restrição de papel, e-mail duplicado, edição, e as duas guardas de
arquivamento (não pode arquivar a própria conta; não pode arquivar o
último admin_master ativo).
"""
from factories import DuasClinicas, novo_usuario

from conftest import autenticado


def _admin(nome="Admin A", email="admin.a@plataforma.com"):
    return novo_usuario(None, nome, email, "admin_master")


def test_admin_master_lista_administradores(client, db_ctx):
    a1 = _admin()
    a2 = _admin("Admin B", "admin.b@plataforma.com")
    r = autenticado(client, a1).get("/api/admin/administradores")
    assert r.status_code == 200, r.get_data(as_text=True)
    emails = {a["email"] for a in r.get_json()}
    assert {"admin.a@plataforma.com", "admin.b@plataforma.com"} <= emails


def test_gestor_nao_acessa_administradores_da_plataforma(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).get("/api/admin/administradores")
    assert r.status_code == 403, r.get_data(as_text=True)


def test_admin_master_cadastra_novo_administrador(client, db_ctx):
    a1 = _admin()
    r = autenticado(client, a1).post("/api/admin/administradores", json={
        "nome": "Novo Admin", "email": "novo.admin@plataforma.com", "telefone": "11988887777",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["link_convite"]

    r = autenticado(client, a1).get("/api/admin/administradores")
    emails = {a["email"] for a in r.get_json()}
    assert "novo.admin@plataforma.com" in emails


def test_cadastro_de_administrador_recusa_email_ja_usado(client, db_ctx):
    cen = DuasClinicas()
    a1 = _admin()
    # E-mail já usado por uma gestora de clínica — a checagem é global,
    # não só entre admin_master (mesmo helper de pessoas_bp.py).
    r = autenticado(client, a1).post("/api/admin/administradores", json={
        "nome": "Duplicado", "email": cen.gestor_a["email"],
    })
    assert r.status_code == 409, r.get_data(as_text=True)


def test_gestor_nao_pode_cadastrar_administrador_da_plataforma(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/admin/administradores", json={
        "nome": "X", "email": "x@plataforma.com",
    })
    assert r.status_code == 403, r.get_data(as_text=True)


def test_admin_master_edita_outro_administrador(client, db_ctx):
    a1 = _admin()
    a2 = _admin("Admin B", "admin.b@plataforma.com")
    r = autenticado(client, a1).put(f"/api/admin/administradores/{a2['id']}", json={
        "nome": "Admin B Editado", "telefone": "11977776666",
    })
    assert r.status_code == 200, r.get_data(as_text=True)


def test_administrador_nao_pode_arquivar_a_propria_conta(client, db_ctx):
    a1 = _admin()
    _admin("Admin B", "admin.b@plataforma.com")  # garante que não é o último
    r = autenticado(client, a1).put(f"/api/admin/administradores/{a1['id']}/arquivar")
    assert r.status_code == 400, r.get_data(as_text=True)


def test_nao_pode_arquivar_o_ultimo_administrador_ativo(client, db_ctx):
    a1 = _admin()
    a2 = _admin("Admin B", "admin.b@plataforma.com")
    # a1 arquiva a2 primeiro (a1 continua ativo) — ok, sobra só a1 ativo.
    r = autenticado(client, a1).put(f"/api/admin/administradores/{a2['id']}/arquivar")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["ativo"] is False

    # Agora a1 é o único admin_master ativo do sistema — a plataforma nunca
    # pode ficar sem nenhum administrador com acesso, então essa tentativa
    # (mesmo sendo também a própria conta, já que um admin_master arquivado
    # não consegue mais nem autenticar pra tentar arquivar outro) é bloqueada.
    r = autenticado(client, a1).put(f"/api/admin/administradores/{a1['id']}/arquivar")
    assert r.status_code == 400, r.get_data(as_text=True)


def test_reativar_administrador_arquivado_funciona(client, db_ctx):
    a1 = _admin()
    a2 = _admin("Admin B", "admin.b@plataforma.com")
    autenticado(client, a1).put(f"/api/admin/administradores/{a2['id']}/arquivar")

    r = autenticado(client, a1).put(f"/api/admin/administradores/{a2['id']}/arquivar")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["ativo"] is True
