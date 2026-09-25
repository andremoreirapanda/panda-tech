"""Planos configuráveis (25/09/2026): a migração leva o mapa antigo de
módulos por plano (que estava no código) para o banco sem mudar o resultado."""
import db
import planos_padrao


def _modulos(codigo):
    from modulos_service import modulos_do_plano
    return sorted(modulos_do_plano(codigo))


def test_resultado_igual_ao_mapa_antigo(db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    assert _modulos("starter") == []
    # "ia" fica gravado mas escondido (25/09/2026) — não entra nos módulos efetivos
    assert _modulos("pro") == sorted(["financeiro", "analytics_avancado", "integracoes", "importacao_pacientes"])
    assert _modulos("enterprise") == sorted(["financeiro", "analytics_avancado", "integracoes",
                                              "importacao_pacientes", "white_label"])


def test_enterprise_herda_de_pro(db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    ent = db.query_one("SELECT plano_base_id FROM planos WHERE codigo = 'enterprise'")
    pro = db.query_one("SELECT id FROM planos WHERE codigo = 'pro'")
    assert ent["plano_base_id"] == pro["id"]


def test_idempotente_e_nao_sobrescreve_ajuste_do_admin(db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    pro = db.query_one("SELECT id FROM planos WHERE codigo = 'pro'")["id"]
    db.execute("DELETE FROM planos_modulos WHERE plano_id = ? AND modulo_codigo = 'integracoes'", (pro,))
    planos_padrao.aplicar_modulos_padrao()
    assert "integracoes" not in _modulos("pro")


def test_pacientes_ilimitados(db_ctx):
    db.execute("INSERT INTO planos (codigo, nome, preco_mensal_centavos, limite_pacientes) VALUES ('pro', 'Pro', 1, 30)")
    planos_padrao.aplicar_modulos_padrao()
    assert db.query_one("SELECT limite_pacientes FROM planos WHERE codigo = 'pro'")["limite_pacientes"] is None
