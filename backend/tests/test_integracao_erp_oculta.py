"""ERP escondido (pedido do usuário, 26/09/2026): o cartão só guardava a
"intenção" — não integra nada. Some da Central de Integrações até existir."""
from factories import DuasClinicas
from conftest import autenticado
from modulos_service import definir_liberacao_admin


def test_listagem_nao_traz_erp(client, db_ctx):
    cen = DuasClinicas()
    definir_liberacao_admin(cen.org_a, "integracoes", True)
    r = autenticado(client, cen.gestor_a).get("/api/integracoes")
    assert r.status_code == 200, r.get_data(as_text=True)
    tipos = {i["tipo"] for i in r.get_json()}
    assert "erp" not in tipos and {"whatsapp", "google_calendar", "pagamento"} <= tipos


def test_toggle_do_erp_recusado(client, db_ctx):
    cen = DuasClinicas()
    definir_liberacao_admin(cen.org_a, "integracoes", True)
    assert autenticado(client, cen.gestor_a).post("/api/integracoes/erp/toggle").status_code == 400
