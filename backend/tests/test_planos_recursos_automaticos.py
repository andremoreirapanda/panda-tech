"""Planos (25/09/2026, pedido do usuário): os recursos exibidos no plano são
gerados a partir dos campos (base, limites, módulos); o texto livre vira só
"outros benefícios". O módulo de IA fica escondido até existir."""
import db
import planos_padrao
from factories import DuasClinicas, novo_usuario
from conftest import autenticado
from modulos_service import MODULOS_VISIVEIS


def _admin(client):
    return autenticado(client, novo_usuario(None, "Admin", "admin@saas.com", "admin_master"))


def test_recursos_gerados_dos_campos(client, db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    c = _admin(client)
    c.put("/api/admin/planos/pro", json={"limite_profissionais": 10, "limite_secretarias": 1, "recursos": ["Suporte prioritário"]})
    c.put("/api/admin/planos/enterprise", json={"limite_profissionais": None, "limite_secretarias": None})
    planos = {p["codigo"]: p for p in c.get("/api/admin/planos").get_json()}
    pro = planos["pro"]
    assert pro["recursos_auto"][:3] == ["Pacientes ilimitados", "Até 10 profissionais", "1 secretária administrativa"]
    assert "📊 Indicadores Avançados" in pro["recursos_auto"]
    assert pro["recursos"] == ["Suporte prioritário"]
    ent = planos["enterprise"]
    assert ent["recursos_auto"][0] == "Tudo do plano Pro"
    assert "Profissionais ilimitados" in ent["recursos_auto"] and "Secretárias ilimitadas" in ent["recursos_auto"]
    assert "🎨 Identidade Visual Própria" in ent["recursos_auto"]
    assert not any("Financeiro" in r for r in ent["recursos_auto"])  # herdado: coberto por "Tudo do plano Pro"


def test_secretaria_zero_nao_vira_item(client, db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    c = _admin(client)
    c.put("/api/admin/planos/starter", json={"limite_profissionais": 3, "limite_secretarias": 0})
    starter = next(p for p in c.get("/api/admin/planos").get_json() if p["codigo"] == "starter")
    assert starter["recursos_auto"] == ["Pacientes ilimitados", "Até 3 profissionais"]


def test_modulo_ia_escondido(client, db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    assert "ia" not in [m["codigo"] for m in MODULOS_VISIVEIS]
    c = _admin(client)
    assert "ia" not in [m["codigo"] for m in c.get("/api/admin/modulos-disponiveis").get_json()]
    pro = next(p for p in c.get("/api/admin/planos").get_json() if p["codigo"] == "pro")
    assert "ia" not in pro["modulos_efetivos"]
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    mods = autenticado(client, cen.gestor_a).get("/api/modulos").get_json()
    assert "ia" not in [m["codigo"] for m in mods]


def test_descricoes_completas(db_ctx):
    for m in MODULOS_VISIVEIS:
        assert len(m["descricao"]) > 120, m["codigo"]
