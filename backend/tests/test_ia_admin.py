"""IA fase 1 (Task 4): minutos no plano, créditos e consumo no Admin."""
import db
import ia_service
import planos_padrao
from factories import DuasClinicas, novo_usuario
from conftest import autenticado


def _prep(client):
    planos_padrao.criar_planos_padrao_para_teste()
    cen = DuasClinicas()
    admin_user = novo_usuario(None, "Admin", "admin@saas.com", "admin_master")
    return cen, admin_user


def _liga_ia(codigo_plano, minutos):
    pid = db.query_one("SELECT id FROM planos WHERE codigo = ?", (codigo_plano,))["id"]
    db.execute("UPDATE planos SET ia_minutos_mes = ? WHERE id = ?", (minutos, pid))
    db.execute("INSERT INTO planos_modulos (plano_id, modulo_codigo) VALUES (?, 'ia')", (pid,))
    return pid


def _uso(org, segundos, sucesso=1, custo=None, mes=None):
    db.execute(
        "INSERT INTO ia_uso (organizacao_id, recurso, mes, segundos, sucesso, custo_estimado_micro_usd) "
        "VALUES (?, 'ditado', ?, ?, ?, ?)",
        (org, mes or ia_service.mes_atual(), segundos, sucesso, custo))


def test_plano_grava_e_devolve_minutos(client, db_ctx):
    _, adm = _prep(client)
    a = autenticado(client, adm)
    r = a.post("/api/admin/planos", json={"nome": "Plano IA", "ia_minutos_mes": 120})
    assert r.status_code == 201
    cod = r.get_json()["codigo"]
    lista = {p["codigo"]: p for p in a.get("/api/admin/planos").get_json()}
    assert lista[cod]["ia_minutos_mes"] == 120
    # PUT sem a chave mantém; null herda
    assert a.put(f"/api/admin/planos/{cod}", json={"nome": "Plano IA 2"}).status_code == 200
    assert db.query_one("SELECT ia_minutos_mes FROM planos WHERE codigo = ?", (cod,))["ia_minutos_mes"] == 120
    assert a.put(f"/api/admin/planos/{cod}", json={"ia_minutos_mes": None}).status_code == 200
    assert db.query_one("SELECT ia_minutos_mes FROM planos WHERE codigo = ?", (cod,))["ia_minutos_mes"] is None
    assert a.put(f"/api/admin/planos/{cod}", json={"ia_minutos_mes": ""}).status_code == 200


def test_plano_minutos_invalidos_400(client, db_ctx):
    _, adm = _prep(client)
    a = autenticado(client, adm)
    for ruim in (-1, 100001, "abc", True, 1.5):
        r = a.post("/api/admin/planos", json={"nome": "X", "ia_minutos_mes": ruim})
        assert r.status_code == 400 and r.get_json()["erro"] == "Minutos de ditado inválidos."


def test_recurso_automatico_ditado(client, db_ctx):
    _, adm = _prep(client)
    _liga_ia("pro", 300)
    a = autenticado(client, adm)
    lista = {p["codigo"]: p for p in a.get("/api/admin/planos").get_json()}
    assert "🎤 Ditado por voz: 300 minutos por mês" in lista["pro"]["recursos_auto"]
    assert not any("Ditado" in r for r in lista["starter"]["recursos_auto"])
    db.execute("UPDATE planos SET ia_minutos_mes = 1 WHERE codigo = 'pro'")
    lista = {p["codigo"]: p for p in a.get("/api/admin/planos").get_json()}
    assert "🎤 Ditado por voz: 1 minuto por mês" in lista["pro"]["recursos_auto"]
    db.execute("UPDATE planos SET ia_minutos_mes = 0 WHERE codigo = 'pro'")
    lista = {p["codigo"]: p for p in a.get("/api/admin/planos").get_json()}
    assert not any("Ditado" in r for r in lista["pro"]["recursos_auto"])


def test_liberar_creditos_entra_na_cota(client, db_ctx):
    cen, adm = _prep(client)
    a = autenticado(client, adm)
    plano = db.query_one("SELECT plano FROM organizacoes WHERE id = ?", (cen.org_a,))["plano"]
    r = a.post(f"/api/admin/clinicas/{cen.org_a}/ia/creditos", json={"minutos": 40, "motivo": "Teste"})
    assert r.status_code == 201
    d = a.get(f"/api/admin/clinicas/{cen.org_a}/ia").get_json()
    assert d["mes"] == ia_service.mes_atual()
    assert d["cota"]["minutos_cota"] == ia_service.minutos_do_plano(plano) + 40
    assert d["creditos"][0]["minutos"] == 40 and d["creditos"][0]["criado_por_nome"] == "Admin"
    aud = db.query_one("SELECT * FROM auditoria WHERE acao = 'liberar' AND entidade = 'ia_creditos'")
    assert aud
    for ruim in (0, 10001, "x", True):
        assert a.post(f"/api/admin/clinicas/{cen.org_a}/ia/creditos",
                      json={"minutos": ruim, "motivo": "ok"}).status_code == 400
    assert a.post("/api/admin/clinicas/999999/ia/creditos", json={"minutos": 5, "motivo": "ok"}).status_code == 404


def test_creditos_motivo_obrigatorio_400(client, db_ctx):
    cen, adm = _prep(client)
    a = autenticado(client, adm)
    for motivo in (None, "", "   ", "x" * 201):
        r = a.post(f"/api/admin/clinicas/{cen.org_a}/ia/creditos", json={"minutos": 5, "motivo": motivo})
        assert r.status_code == 400


def test_uso_do_mes_por_clinica(client, db_ctx):
    cen, adm = _prep(client)
    _liga_ia("pro", 100)
    db.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    _uso(cen.org_a, 120, custo=9000)
    _uso(cen.org_a, 60, custo=4500)
    _uso(cen.org_a, 0, sucesso=0)
    _uso(cen.org_b, 30, custo=2250)  # org_b sem módulo, mas com uso
    _uso(cen.org_a, 600, custo=1, mes="2020-01")
    a = autenticado(client, adm)
    d = a.get("/api/admin/ia/uso").get_json()
    por = {c["id"]: c for c in d["clinicas"]}
    ca = por[cen.org_a]
    assert ca["minutos_usados"] == 3 and ca["ditados"] == 2 and ca["falhas"] == 1
    assert ca["minutos_cota"] == 100 and ca["custo_estimado_usd"] == 0.01
    assert por[cen.org_b]["ditados"] == 1
    assert d["total"]["ditados"] == 3 and d["total"]["falhas"] == 1 and d["total"]["minutos_usados"] == 4
    assert d["total"]["custo_estimado_usd"] == 0.02
    assert a.get("/api/admin/ia/uso?mes=2020-01").get_json()["clinicas"][0]["ditados"] == 1
    for ruim in ("2026-13", "abc", "2026-1"):
        assert a.get(f"/api/admin/ia/uso?mes={ruim}").status_code == 400


def test_rotas_ia_admin_so_admin(client, db_ctx):
    cen, _ = _prep(client)
    g = autenticado(client, cen.gestor_a)
    assert g.get("/api/admin/ia/uso").status_code == 403
    assert g.get(f"/api/admin/clinicas/{cen.org_a}/ia").status_code == 403
    assert g.post(f"/api/admin/clinicas/{cen.org_a}/ia/creditos",
                  json={"minutos": 5, "motivo": "x"}).status_code == 403


def test_antes_da_migracao_nao_da_500(client, db_ctx, monkeypatch):
    cen, adm = _prep(client)
    monkeypatch.setattr(ia_service, "tabelas_existem", lambda: False)
    a = autenticado(client, adm)
    d = a.get("/api/admin/ia/uso").get_json()
    assert d["clinicas"] == [] and d["total"]["ditados"] == 0
    r = a.get(f"/api/admin/clinicas/{cen.org_a}/ia")
    assert r.status_code == 200 and r.get_json()["creditos"] == []
    assert r.get_json()["cota"]["minutos_cota"] == 0
    assert a.post(f"/api/admin/clinicas/{cen.org_a}/ia/creditos",
                  json={"minutos": 5, "motivo": "x"}).status_code == 503
