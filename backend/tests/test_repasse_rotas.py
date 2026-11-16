"""Financeiro etapa 3, task 5: rotas, regras e PDF do repasse."""
import base64
import io

import db
from conftest import autenticado
from factories import novo_usuario, vincular_responsavel
from test_repasse_relatorio import DE, ATE, _cenario, _regra, _acordo, _consulta, _sync, _cobranca_da
from test_repasse_fechamento import _pagar

B = "/api/financeiro/repasse"


def _com_sec(cen):
    cen.sec_a = novo_usuario(cen.org_a, "Secretaria A", "sec@a.com", "secretaria")
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    return cen


def _png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), (91, 79, 233)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _duas_pagas(cen):
    _regra(cen, cen.prof_a1, pct=6500)
    _acordo(cen, "avulsa")
    c1 = _consulta(cen, "2026-10-05")
    c2 = _consulta(cen, "2026-10-12")
    _sync(cen.org_a)
    _pagar(_cobranca_da(c1)["id"])
    _pagar(_cobranca_da(c2)["id"])
    return c1, c2


def _confirmado(cliente, pid):
    """O valor e os ajustes que a tela mostra (enviados ao marcar como pago)."""
    p = next(x for x in cliente.get(f"{B}?de={DE}&ate={ATE}&profissional_id={pid}").get_json()["profissionais"]
             if x["profissional_id"] == pid)
    return {"a_pagar_centavos": p["a_pagar_centavos"], "ajuste_ids": [a["id"] for a in p["ajustes"]]}


def _regras(*itens):
    return {"regras": list(itens)}


def _contagem():
    return db.query_one("SELECT COUNT(*) AS n FROM regras_repasse")["n"]


def test_so_gestor(client, db_ctx):
    cen = _com_sec(_cenario(db_ctx))
    pid = cen.prof_a1["id"]
    rotas = [("get", f"{B}/regras", None), ("put", f"{B}/regras/{pid}", _regras()),
             ("get", B, None), ("get", f"{B}/pdf?profissional_id={pid}", None),
             ("post", f"{B}/fechar", {"profissional_id": pid, "de": DE, "ate": ATE, "consulta_ids": []}),
             ("get", f"{B}/fechamentos", None), ("get", f"{B}/fechamentos/1", None),
             ("get", f"{B}/fechamentos/1/pdf", None),
             ("post", f"{B}/fechamentos/1/desfazer", {"motivo": "x"}),
             ("post", f"{B}/ajustes", {"profissional_id": pid, "descricao": "x", "valor_centavos": 1}),
             ("delete", f"{B}/ajustes/1", None)]
    for u in (cen.sec_a, cen.prof_a1, cen.resp_a1):
        c = autenticado(client, u)
        for metodo, url, corpo in rotas:
            r = getattr(c, metodo)(url, json=corpo) if corpo is not None else getattr(c, metodo)(url)
            assert r.status_code == 403, (u["papel"], metodo, url, r.status_code)
    assert autenticado(client, cen.gestor_a).get(f"{B}/regras").status_code == 200


def test_sem_modulo_403(client, db_ctx):
    cen = _cenario(db_ctx)
    db.execute("UPDATE organizacoes SET plano = 'starter' WHERE id = ?", (cen.org_a,))
    g = autenticado(client, cen.gestor_a)
    for url in (f"{B}/regras", B, f"{B}/fechamentos", f"{B}/pdf?profissional_id={cen.prof_a1['id']}"):
        assert g.get(url).status_code == 403, url
    assert g.put(f"{B}/regras/{cen.prof_a1['id']}", json=_regras()).status_code == 403


def test_get_regras_lista_profissionais_e_procedimentos(client, db_ctx):
    cen = _cenario(db_ctx)
    db.execute("UPDATE usuarios SET especialidade = 'Fonoaudiologia' WHERE id = ?", (cen.prof_a1["id"],))
    db.execute("UPDATE usuarios SET excluido_em = '2026-11-01 10:00:00', ativo = 0 WHERE id = ?", (cen.prof_a2["id"],))
    _regra(cen, cen.prof_a1, pct=6550)
    d = autenticado(client, cen.gestor_a).get(f"{B}/regras").get_json()
    assert d["base"] == "procedimento"
    ids = {p["id"] for p in d["profissionais"]}
    assert cen.prof_a1["id"] in ids and cen.gestor_a["id"] in ids
    assert cen.prof_a2["id"] not in ids and cen.prof_b1["id"] not in ids and cen.resp_a1["id"] not in ids
    p1 = next(p for p in d["profissionais"] if p["id"] == cen.prof_a1["id"])
    assert p1["especialidade"] == "Fonoaudiologia" and p1["nome"] == "Prof A1"
    assert len(p1["regras"]) == 1 and p1["regras"][0]["percentual_centesimos"] == 6550
    assert {x["id"] for x in d["procedimentos"]} == {cen.proc_230, cen.proc_150}
    assert {"id", "nome", "valor_centavos"} <= set(d["procedimentos"][0])


def test_salvar_regras_substitui_e_audita(client, db_ctx):
    cen = _cenario(db_ctx)
    g = autenticado(client, cen.gestor_a)
    url = f"{B}/regras/{cen.prof_a1['id']}"
    r = g.put(url, json=_regras(
        {"procedimento_id": None, "tipo_acordo": None, "modo": "percentual", "percentual": 65.5},
        {"procedimento_id": cen.proc_230, "tipo_acordo": "pacote", "modo": "fixo", "valor_centavos": 8000}))
    assert r.status_code == 200, r.get_data()
    rows = db.query("SELECT * FROM regras_repasse WHERE profissional_id = ? ORDER BY id", (cen.prof_a1["id"],))
    assert rows[0]["percentual_centesimos"] == 6550 and rows[0]["modo"] == "percentual"
    assert rows[1]["valor_centavos"] == 8000 and rows[1]["tipo_acordo"] == "pacote"
    assert all(x["organizacao_id"] == cen.org_a for x in rows)
    # substitui (e não toca em outro profissional)
    _regra(cen, cen.prof_a2, pct=5000)
    g.put(url, json=_regras({"modo": "percentual", "percentual": 70}))
    rows = db.query("SELECT * FROM regras_repasse WHERE profissional_id = ?", (cen.prof_a1["id"],))
    assert len(rows) == 1 and rows[0]["percentual_centesimos"] == 7000
    assert db.query_one("SELECT COUNT(*) AS n FROM regras_repasse WHERE profissional_id = ?",
                        (cen.prof_a2["id"],))["n"] == 1
    assert db.query_one("SELECT COUNT(*) AS n FROM auditoria WHERE entidade = 'regras_repasse'")["n"] >= 2
    g.put(url, json=_regras())
    assert db.query("SELECT * FROM regras_repasse WHERE profissional_id = ?", (cen.prof_a1["id"],)) == []


def test_salvar_regras_valida(client, db_ctx):
    cen = _cenario(db_ctx)
    outra = db.execute("INSERT INTO procedimentos (organizacao_id, nome, valor_centavos) VALUES (?, 'X', 100)",
                       (cen.org_b,))
    _regra(cen, cen.prof_a1, pct=5000)
    antes = _contagem()
    g = autenticado(client, cen.gestor_a)
    url = f"{B}/regras/{cen.prof_a1['id']}"
    bom = {"modo": "percentual", "percentual": 50}
    ruins = [
        {"modo": "percentual", "percentual": 100.01},
        {"modo": "percentual", "percentual": -1},
        {"modo": "percentual", "percentual": 10.123},
        {"modo": "percentual", "percentual": True},
        {"modo": "percentual", "percentual": "abc"},
        {"modo": "percentual", "percentual": float("nan")},
        {"modo": "percentual"},
        {"modo": "fixo", "valor_centavos": 10000001},
        {"modo": "fixo", "valor_centavos": -1},
        {"modo": "fixo", "valor_centavos": 10.5},
        {"modo": "fixo", "valor_centavos": True},
        {"modo": "fixo"},
        {"modo": "outro", "percentual": 10},
        {"modo": "percentual", "percentual": 10, "tipo_acordo": "x"},
        {"modo": "percentual", "percentual": 10, "procedimento_id": outra},
        {"modo": "percentual", "percentual": 10, "procedimento_id": 99999},
        {"modo": "percentual", "percentual": 10, "procedimento_id": True},
    ]
    for ruim in ruins:
        r = g.put(url, json=_regras(bom | {"tipo_acordo": "mensalidade"}, ruim))
        assert r.status_code == 400, (ruim, r.status_code)
    # dois padrões
    assert g.put(url, json=_regras(bom, {"modo": "fixo", "valor_centavos": 5})).status_code == 400
    # par repetido
    par = {"procedimento_id": cen.proc_230, "tipo_acordo": "avulsa", "modo": "percentual", "percentual": 10}
    assert g.put(url, json=_regras(par, dict(par))).status_code == 400
    assert g.put(url, json={"regras": "x"}).status_code == 400
    assert g.put(url, json=[1]).status_code == 400
    assert _contagem() == antes
    assert db.query_one("SELECT percentual_centesimos AS p FROM regras_repasse")["p"] == 5000
    # limites aceitos
    assert g.put(url, json=_regras({"modo": "percentual", "percentual": 100})).status_code == 200
    assert g.put(url, json=_regras({"modo": "fixo", "valor_centavos": 10000000})).status_code == 200
    assert g.put(url, json=_regras({"modo": "percentual", "percentual": 0})).status_code == 200


def test_outra_clinica_404(client, db_ctx):
    cen = _cenario(db_ctx)
    gb = autenticado(client, cen.gestor_b)
    assert gb.put(f"{B}/regras/{cen.prof_a1['id']}", json=_regras()).status_code == 404
    c1, c2 = _duas_pagas(cen)
    ga = autenticado(client, cen.gestor_a)
    rid = ga.post(f"{B}/fechar", json={"profissional_id": cen.prof_a1["id"], "de": DE, "ate": ATE,
                                       "consulta_ids": [c1, c2],
                                       **_confirmado(ga, cen.prof_a1["id"])}).get_json()["repasse_id"]
    aj = ga.post(f"{B}/ajustes", json={"profissional_id": cen.prof_a1["id"], "descricao": "Vale",
                                       "valor_centavos": -100}).get_json()
    gb = autenticado(client, cen.gestor_b)   # o cliente de teste é um só: volta para a clínica B
    for r in (gb.get(f"{B}/fechamentos/{rid}"), gb.get(f"{B}/fechamentos/{rid}/pdf"),
              gb.post(f"{B}/fechamentos/{rid}/desfazer", json={"motivo": "x"}),
              gb.delete(f"{B}/ajustes/{aj['id']}"),
              gb.post(f"{B}/ajustes", json={"profissional_id": cen.prof_a1["id"], "descricao": "x",
                                            "valor_centavos": 5}),
              gb.post(f"{B}/fechar", json={"profissional_id": cen.prof_a1["id"], "de": DE, "ate": ATE,
                                           "consulta_ids": []})):
        assert r.status_code == 404, r.get_data()
    assert gb.get(f"{B}/fechamentos").get_json() == []


def test_config_repasse_base(client, db_ctx):
    cen = _cenario(db_ctx)
    g = autenticado(client, cen.gestor_a)
    assert g.get("/api/financeiro/config").get_json()["repasse_base"] == "procedimento"
    r = g.put("/api/financeiro/config", json={"repasse_base": "rateado"})
    assert r.status_code == 200 and r.get_json()["repasse_base"] == "rateado"
    assert g.get("/api/financeiro/config").get_json()["repasse_base"] == "rateado"
    assert g.get(f"{B}/regras").get_json()["base"] == "rateado"
    assert g.put("/api/financeiro/config", json={"repasse_base": "outro"}).status_code == 400
    assert g.put("/api/financeiro/config", json={"repasse_base": True}).status_code == 400
    g.put("/api/financeiro/config", json={"cobrar_falta": True})   # outra chave mantém
    assert g.get("/api/financeiro/config").get_json()["repasse_base"] == "rateado"
    assert autenticado(client, cen.gestor_b).get("/api/financeiro/config").get_json()["repasse_base"] == "procedimento"


def test_relatorio_pela_rota(client, db_ctx):
    cen = _cenario(db_ctx)
    _duas_pagas(cen)
    g = autenticado(client, cen.gestor_a)
    r = g.get(f"{B}?de={DE}&ate={ATE}&profissional_id={cen.prof_a1['id']}")
    assert r.status_code == 200
    d = r.get_json()
    assert d["profissionais"][0]["a_pagar_centavos"] == 29900
    assert g.get(f"{B}?de=2026-10-31&ate=2026-10-01").status_code == 400
    assert g.get(f"{B}?profissional_id=abc").status_code == 400
    assert g.get(f"{B}?de={DE}&ate={ATE}&especialidade=Fonoaudiologia").status_code == 200


def test_pdf_relatorio_e_fechamento(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2 = _duas_pagas(cen)
    g = autenticado(client, cen.gestor_a)
    pid = cen.prof_a1["id"]
    db.execute("UPDATE organizacoes SET logo_base64 = ? WHERE id = ?", (_png(), cen.org_a))
    g.post(f"{B}/ajustes", json={"profissional_id": pid, "descricao": "Vale <b>& co", "valor_centavos": -5000})
    r = g.get(f"{B}/pdf?de={DE}&ate={ATE}&profissional_id={pid}")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")
    assert g.get(f"{B}/pdf?de={DE}&ate={ATE}").status_code == 400          # sem profissional
    assert g.get(f"{B}/pdf?de=2026-10-31&ate=2026-10-01&profissional_id={pid}").status_code == 400
    # logo quebrado e sem logo
    db.execute("UPDATE organizacoes SET logo_base64 = 'lixo' WHERE id = ?", (cen.org_a,))
    assert g.get(f"{B}/pdf?de={DE}&ate={ATE}&profissional_id={pid}").data.startswith(b"%PDF")
    db.execute("UPDATE organizacoes SET logo_base64 = NULL WHERE id = ?", (cen.org_a,))
    # sem sessões: ainda gera
    assert g.get(f"{B}/pdf?de=2026-09-01&ate=2026-09-30&profissional_id={cen.prof_a2['id']}").status_code == 200
    # fechamento
    rid = g.post(f"{B}/fechar", json={"profissional_id": pid, "de": DE, "ate": ATE,
                                      "consulta_ids": [c1, c2], **_confirmado(g, pid)}).get_json()["repasse_id"]
    r = g.get(f"{B}/fechamentos/{rid}/pdf")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")
    import repasse_pdf
    pdf = repasse_pdf.gerar_repasse_pdf(
        {"clinica_nome": "Clínica A", "logo_base64": None, "emitido_em": "2026-11-12 10:00:00",
         "de": DE, "ate": ATE, "profissional_nome": "Prof A1", "registro": "CRFa 2-12345", "sessoes": [],
         "por_especialidade": [], "ajustes": [], "total_sessoes_centavos": 0, "total_profissional_centavos": 0,
         "total_ajustes_centavos": 0, "a_pagar_centavos": 0, "base": "procedimento",
         "pago_em": "2026-11-10 09:00:00"})
    assert pdf.startswith(b"%PDF")


def test_fechar_pela_rota_e_desfazer(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2 = _duas_pagas(cen)
    g = autenticado(client, cen.gestor_a)
    pid = cen.prof_a1["id"]
    corpo = {"profissional_id": pid, "de": DE, "ate": ATE, **_confirmado(g, pid)}
    # relatório mudou / lista errada -> 409
    assert g.post(f"{B}/fechar", json={**corpo, "consulta_ids": [c1]}).status_code == 409
    # dado inválido -> 400
    assert g.post(f"{B}/fechar", json={**corpo, "consulta_ids": "x"}).status_code == 400
    assert g.post(f"{B}/fechar", json={**corpo, "de": "2026-10-31", "ate": "2026-10-01",
                                       "consulta_ids": []}).status_code == 400
    r = g.post(f"{B}/fechar", json={**corpo, "consulta_ids": [c1, c2]})
    assert r.status_code == 201
    rid = r.get_json()["repasse_id"]
    # de novo -> 409
    assert g.post(f"{B}/fechar", json={**corpo, "consulta_ids": [c1, c2]}).status_code == 409
    lista = g.get(f"{B}/fechamentos?profissional_id={pid}").get_json()
    assert [x["id"] for x in lista] == [rid] and lista[0]["a_pagar_centavos"] == 29900
    assert g.get(f"{B}/fechamentos?profissional_id={cen.prof_a2['id']}").get_json() == []
    det = g.get(f"{B}/fechamentos/{rid}").get_json()
    assert len(det["itens"]) == 2 and det["profissional_nome"] == "Prof A1"
    assert g.get(f"{B}/fechamentos/99999").status_code == 404
    # desfazer
    assert g.post(f"{B}/fechamentos/{rid}/desfazer", json={}).status_code == 400
    assert g.post(f"{B}/fechamentos/{rid}/desfazer", json={"motivo": "Erro"}).status_code == 200
    assert g.get(f"{B}/fechamentos").get_json() == []
    assert g.post(f"{B}/fechamentos/{rid}/desfazer", json={"motivo": "Erro"}).status_code == 404


def test_ajustes_pela_rota(client, db_ctx):
    cen = _cenario(db_ctx)
    g = autenticado(client, cen.gestor_a)
    pid = cen.prof_a1["id"]
    r = g.post(f"{B}/ajustes", json={"profissional_id": pid, "descricao": "Vale", "valor_centavos": -5000})
    assert r.status_code == 201 and r.get_json()["valor_centavos"] == -5000
    aid = r.get_json()["id"]
    assert g.post(f"{B}/ajustes", json={"profissional_id": pid, "descricao": "", "valor_centavos": 5}).status_code == 400
    assert g.post(f"{B}/ajustes", json={"profissional_id": pid, "descricao": "x",
                                        "valor_centavos": 0}).status_code == 400
    assert g.post(f"{B}/ajustes", json={"profissional_id": 99999, "descricao": "x",
                                        "valor_centavos": 5}).status_code == 404
    assert g.delete(f"{B}/ajustes/{aid}").status_code == 200
    assert g.delete(f"{B}/ajustes/{aid}").status_code == 404


def test_fechar_pela_rota_exige_valor_e_ajustes_confirmados(client, db_ctx):
    cen = _cenario(db_ctx)
    c1, c2 = _duas_pagas(cen)
    g = autenticado(client, cen.gestor_a)
    corpo = {"profissional_id": cen.prof_a1["id"], "de": DE, "ate": ATE, "consulta_ids": [c1, c2]}
    for extra in ({}, {"a_pagar_centavos": 29900}, {"ajuste_ids": []},
                  {"a_pagar_centavos": "29900", "ajuste_ids": []}, {"a_pagar_centavos": 29900, "ajuste_ids": "x"}):
        r = g.post(f"{B}/fechar", json={**corpo, **extra})
        assert r.status_code == 400, (extra, r.get_data())
    # valor diferente do relatório de agora -> 409
    assert g.post(f"{B}/fechar", json={**corpo, "a_pagar_centavos": 1, "ajuste_ids": []}).status_code == 409
    assert db.query_one("SELECT COUNT(*) AS n FROM repasses")["n"] == 0
    r = g.post(f"{B}/fechar", json={**corpo, "a_pagar_centavos": 29900, "ajuste_ids": []})
    assert r.status_code == 201
