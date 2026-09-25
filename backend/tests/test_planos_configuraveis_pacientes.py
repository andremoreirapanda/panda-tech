"""Planos configuráveis (25/09/2026): pacientes ilimitados em todos os planos,
mesmo que um valor antigo tenha ficado em planos.limite_pacientes."""
import db
from factories import DuasClinicas
from conftest import autenticado


def test_cadastro_passa_do_antigo_limite(client, db_ctx):
    cen = DuasClinicas()
    db.execute("INSERT INTO planos (codigo, nome, preco_mensal_centavos, limite_pacientes) VALUES ('mini', 'Mini', 0, 1)")
    db.execute("UPDATE organizacoes SET plano = 'mini' WHERE id = ?", (cen.org_a,))
    c = autenticado(client, cen.gestor_a)
    for i in range(3):
        r = c.post("/api/pessoas/pacientes", json={"nome": f"Novo {i}", "data_nascimento": "2019-01-01"})
        assert r.status_code in (200, 201), r.get_data(as_text=True)
