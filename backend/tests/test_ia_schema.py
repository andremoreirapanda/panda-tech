"""IA fase 1 (25/11/2026): tabelas de uso e créditos, minutos no plano e módulo `ia` visível."""
import db
import modulos_service
import planos_padrao
import migrar_ia_ditado


def _colunas(tabela):
    return {l["name"] for l in db.get_db().execute(f"PRAGMA table_info({tabela})").fetchall()}


def test_schema_tem_tabelas_e_coluna(db_ctx):
    assert "ia_minutos_mes" in _colunas("planos")
    assert _colunas("ia_uso") >= {"id", "organizacao_id", "usuario_id", "recurso", "mes", "segundos", "modelo",
                                   "custo_estimado_micro_usd", "sucesso", "criado_em"}
    assert _colunas("ia_creditos") >= {"id", "organizacao_id", "mes", "minutos", "motivo", "criado_por", "criado_em"}
    indices = {l["name"] for l in db.get_db().execute(
        "SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()}
    assert {"idx_ia_uso_org_mes", "idx_ia_creditos_org_mes"} <= indices


def test_ia_visivel(db_ctx):
    assert "ia" in modulos_service.CODIGOS_OPCIONAIS
    assert "ia" not in modulos_service.CODIGOS_OCULTOS


def test_pro_padrao_sem_ia(db_ctx):
    assert "ia" not in planos_padrao.MODULOS_PADRAO["pro"]


def test_migracao_tira_ia_dos_planos_e_eh_idempotente(db_ctx):
    planos_padrao.criar_planos_padrao_para_teste()
    pro = db.query_one("SELECT id FROM planos WHERE codigo = 'pro'")["id"]
    org = db.execute("INSERT INTO organizacoes (nome) VALUES ('Clínica IA')")
    db.execute("INSERT INTO planos_modulos (plano_id, modulo_codigo) VALUES (?, 'ia')", (pro,))
    db.execute("INSERT INTO modulos_clinica (organizacao_id, modulo_codigo, liberado_admin) VALUES (?, 'ia', 1)", (org,))
    migrar_ia_ditado.migrar()
    migrar_ia_ditado.migrar()
    assert db.query_one("SELECT 1 FROM planos_modulos WHERE modulo_codigo = 'ia'") is None
    assert db.query_one("SELECT 1 FROM modulos_clinica WHERE modulo_codigo = 'ia'") is None
    assert "ia_minutos_mes" in _colunas("planos")
    assert _colunas("ia_uso") and _colunas("ia_creditos")
