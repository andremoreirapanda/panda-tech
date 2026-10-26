"""
Importação do prontuário (26/10/2026): Ficha Clínica na planilha de pacientes
(sem duplicar quem já existe) e uma 2ª planilha de evoluções que vira
registros "Importado" no Diário, só para a equipe.

Spec: docs/superpowers/specs/2026-10-26-importacao-prontuario-design.md
"""
import pytest

import importacao_service
from factories import DuasClinicas


@pytest.fixture(autouse=True)
def _sem_cache_das_colunas():
    # O serviço guarda "as colunas existem" depois da 1ª vez; aqui há testes
    # que apagam as colunas, então cada teste pergunta de novo.
    importacao_service._colunas_ok[0] = False
    yield
    importacao_service._colunas_ok[0] = False


def _sem_colunas_novas(db):
    db.execute("DROP INDEX IF EXISTS idx_diario_importacao_chave")
    db.execute("ALTER TABLE diarios_terapeuticos DROP COLUMN importacao_chave")
    db.execute("ALTER TABLE diarios_terapeuticos DROP COLUMN origem")


# ----------------------------------------------------------------- banco e ICT

def test_colunas_novas_do_diario(db_ctx):
    import importacao_service
    assert importacao_service.colunas_diario_importacao_existem() is True


def test_sem_colunas_responde_false(db_ctx):
    _sem_colunas_novas(db_ctx)
    import importacao_service
    assert importacao_service.colunas_diario_importacao_existem() is False


def test_migracao_idempotente(db_ctx):
    import importacao_service
    import migrar_importacao_prontuario
    _sem_colunas_novas(db_ctx)
    migrar_importacao_prontuario.migrar()
    migrar_importacao_prontuario.migrar()
    assert importacao_service.colunas_diario_importacao_existem() is True


def _diario(db, paciente_id, profissional_id, origem=None):
    db.execute(
        "INSERT INTO diarios_terapeuticos (paciente_id, profissional_id, evolucao_clinica, origem) VALUES (?, ?, ?, ?)",
        (paciente_id, profissional_id, "Texto", origem),
    )


def test_ict_ignora_diario_importado(db_ctx):
    from ict_service import calcular_ict_paciente
    cen = DuasClinicas()
    db_ctx.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, 'Falar')", (cen.paciente_a1,))
    _diario(db_ctx, cen.paciente_a1, cen.prof_a1["id"], origem="importacao")
    assert calcular_ict_paciente(cen.paciente_a1)["componentes"]["profissional_acompanhou"] is False
    _diario(db_ctx, cen.paciente_a1, cen.prof_a1["id"])
    assert calcular_ict_paciente(cen.paciente_a1)["componentes"]["profissional_acompanhou"] is True


def test_ict_funciona_antes_da_migracao(db_ctx):
    from ict_service import calcular_ict_paciente
    cen = DuasClinicas()
    db_ctx.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, 'Falar')", (cen.paciente_a1,))
    _sem_colunas_novas(db_ctx)
    db_ctx.execute(
        "INSERT INTO diarios_terapeuticos (paciente_id, profissional_id, evolucao_clinica) VALUES (?, ?, 'Texto')",
        (cen.paciente_a1, cen.prof_a1["id"]),
    )
    assert calcular_ict_paciente(cen.paciente_a1)["componentes"]["profissional_acompanhou"] is True


# ------------------------------------------------------------ funções puras

def test_normalizar_nome():
    from importacao_service import normalizar_nome
    assert normalizar_nome("  Lúcas   ALMEIDA ") == normalizar_nome("lucas almeida") == "lucas almeida"
    assert normalizar_nome(None) == ""


def test_converter_data():
    from importacao_service import converter_data
    assert converter_data("2026-08-12") == "2026-08-12"
    assert converter_data("12/08/2026") == "2026-08-12"
    assert converter_data(" 12/08/2026 ") == "2026-08-12"
    assert converter_data("31/02/2026") is None
    assert converter_data("2026-8-12") is None
    assert converter_data("") is None and converter_data(None) is None


def test_chave_importacao_estavel():
    from importacao_service import chave_importacao
    assert chave_importacao(1, "2026-08-12", " Texto ") == chave_importacao(1, "2026-08-12", "Texto")
    assert chave_importacao(1, "2026-08-12", "Texto") != chave_importacao(2, "2026-08-12", "Texto")
    assert chave_importacao(1, "2026-08-12", "Texto") != chave_importacao(1, "2026-08-13", "Texto")


# ------------------------------------------- etapa 1: ficha + paciente existente

import planos_padrao  # noqa: E402
from conftest import autenticado  # noqa: E402
from factories import novo_paciente, novo_usuario, vincular_responsavel  # noqa: E402


def _clinica_com_modulo(db):
    cen = DuasClinicas()
    planos_padrao.criar_planos_padrao_para_teste()
    db.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    return cen


def _linha_paciente(nome="Lucas Almeida", nascimento="2019-03-14", email="mae.lucas@x.com", **extra):
    linha = {"nome": nome, "data_nascimento": nascimento,
             "responsavel_nome": "Mãe do Lucas" if email else "", "responsavel_email": email}
    linha.update(extra)
    return linha


def _pacientes(client, cen, linhas, etapa="preview"):
    return autenticado(client, cen.gestor_a).post(f"/api/importacao/pacientes/{etapa}", json={"linhas": linhas})


def _ficha(db, paciente_id):
    return db.query_one("SELECT * FROM fichas_clinicas WHERE paciente_id = ?", (paciente_id,))


def test_ficha_em_paciente_novo(client, db_ctx):
    cen = _clinica_com_modulo(db_ctx)
    linhas = [_linha_paciente(diagnostico="TEA nível 1", observacoes_clinicas="Gosta de música")]
    linha = _pacientes(client, cen, linhas).get_json()["linhas"][0]
    assert linha["paciente_status"] == "novo" and linha["ficha_campos"] == 2
    r = _pacientes(client, cen, linhas, "confirmar")
    assert r.status_code == 201, r.get_data(as_text=True)
    pid = r.get_json()["criados"][0]["paciente_id"]
    ficha = _ficha(db_ctx, pid)
    assert ficha["diagnostico"] == "TEA nível 1"
    assert ficha["observacoes"] == "Gosta de música"
    assert ficha["atualizado_por"] == cen.gestor_a["id"]


def test_paciente_novo_sem_ficha_nao_cria_ficha(client, db_ctx):
    cen = _clinica_com_modulo(db_ctx)
    r = _pacientes(client, cen, [_linha_paciente()], "confirmar")
    assert _ficha(db_ctx, r.get_json()["criados"][0]["paciente_id"]) is None


def test_paciente_existente_nao_duplica_e_so_completa_vazios(client, db_ctx):
    cen = _clinica_com_modulo(db_ctx)
    pid = novo_paciente(cen.org_a, "Lúcas Almeida", "2019-03-14")
    db_ctx.execute("INSERT INTO fichas_clinicas (paciente_id, alergias, diagnostico) VALUES (?, 'Lactose', '')", (pid,))
    linha = _linha_paciente(nome="  LUCAS   almeida", email="", alergias="Glúten", diagnostico="TDAH")
    prev = _pacientes(client, cen, [linha]).get_json()["linhas"][0]
    assert prev["valido"] is True
    assert prev["paciente_status"] == "existente"
    assert prev["ficha_mantidos"] == 1
    assert prev["responsavel_acao"] == "sem_responsavel"
    r = _pacientes(client, cen, [linha], "confirmar")
    assert r.status_code == 201
    assert db_ctx.query_one("SELECT COUNT(*) c FROM pacientes WHERE organizacao_id = ?", (cen.org_a,))["c"] == 3
    ficha = _ficha(db_ctx, pid)
    assert ficha["alergias"] == "Lactose"
    assert ficha["diagnostico"] == "TDAH"
    assert r.get_json()["atualizados"][0]["paciente_status"] == "existente"


def test_paciente_arquivado_conta_como_existente(client, db_ctx):
    cen = _clinica_com_modulo(db_ctx)
    pid = novo_paciente(cen.org_a, "Lucas Almeida", "2019-03-14")
    db_ctx.execute("UPDATE pacientes SET ativo = 0 WHERE id = ?", (pid,))
    prev = _pacientes(client, cen, [_linha_paciente(email="")]).get_json()["linhas"][0]
    assert prev["paciente_status"] == "existente" and prev["paciente_arquivado"] is True
    assert any("arquivado" in a for a in prev["avisos"])
    _pacientes(client, cen, [_linha_paciente(email="", alergias="Pó")], "confirmar")
    assert db_ctx.query_one("SELECT COUNT(*) c FROM pacientes WHERE nome = 'Lucas Almeida'")["c"] == 1
    assert db_ctx.query_one("SELECT ativo FROM pacientes WHERE id = ?", (pid,))["ativo"] == 0
    assert _ficha(db_ctx, pid)["alergias"] == "Pó"


def test_homonimos_dao_erro(client, db_ctx):
    cen = _clinica_com_modulo(db_ctx)
    novo_paciente(cen.org_a, "Lucas Almeida", "2019-03-14")
    novo_paciente(cen.org_a, "Lucas  Almeida", "2019-03-14")
    prev = _pacientes(client, cen, [_linha_paciente()]).get_json()["linhas"][0]
    assert prev["valido"] is False
    assert any("mais de um paciente" in e for e in prev["erros"])


def test_paciente_de_outra_clinica_nao_conta(client, db_ctx):
    cen = _clinica_com_modulo(db_ctx)
    novo_paciente(cen.org_b, "Lucas Almeida", "2019-03-14")
    prev = _pacientes(client, cen, [_linha_paciente()]).get_json()["linhas"][0]
    assert prev["paciente_status"] == "novo"


def test_existente_com_outro_email_nao_vincula(client, db_ctx):
    cen = _clinica_com_modulo(db_ctx)
    pid = novo_paciente(cen.org_a, "Lucas Almeida", "2019-03-14")
    vincular_responsavel(cen.resp_a1["id"], pid)
    linha = _linha_paciente(email="outra.pessoa@x.com")
    prev = _pacientes(client, cen, [linha]).get_json()["linhas"][0]
    assert prev["valido"] is True
    assert prev["responsavel_acao"] == "nao_vinculado"
    assert any("responsável diferente do cadastrado" in a.lower() for a in prev["avisos"])
    _pacientes(client, cen, [linha], "confirmar")
    assert db_ctx.query_one("SELECT id FROM usuarios WHERE email = 'outra.pessoa@x.com'") is None
    assert db_ctx.query_one("SELECT COUNT(*) c FROM responsaveis_pacientes WHERE paciente_id = ?", (pid,))["c"] == 1


def test_existente_com_mesmo_responsavel(client, db_ctx):
    cen = _clinica_com_modulo(db_ctx)
    pid = novo_paciente(cen.org_a, "Lucas Almeida", "2019-03-14")
    vincular_responsavel(cen.resp_a1["id"], pid)
    prev = _pacientes(client, cen, [_linha_paciente(email="FAMILIA.A1@a.com")]).get_json()["linhas"][0]
    assert prev["responsavel_acao"] == "ja_vinculado"
    assert all("diferente" not in a for a in prev["avisos"])


def test_paciente_novo_continua_exigindo_responsavel(client, db_ctx):
    cen = _clinica_com_modulo(db_ctx)
    prev = _pacientes(client, cen, [_linha_paciente(email="")]).get_json()["linhas"][0]
    assert prev["valido"] is False


def test_ficha_limite(client, db_ctx):
    cen = _clinica_com_modulo(db_ctx)
    prev = _pacientes(client, cen, [
        _linha_paciente(diagnostico="x" * 2001),
        _linha_paciente(nome="Outra", observacoes_clinicas="x" * 5000),
        _linha_paciente(nome="Mais Uma", observacoes_clinicas="x" * 5001),
    ]).get_json()["linhas"]
    assert prev[0]["valido"] is False and any("2.000" in e for e in prev[0]["erros"])
    assert prev[1]["valido"] is True
    assert prev[2]["valido"] is False and any("5.000" in e for e in prev[2]["erros"])


def test_mesmo_paciente_duas_vezes_no_lote(client, db_ctx):
    cen = _clinica_com_modulo(db_ctx)
    linhas = [_linha_paciente(diagnostico="TEA"), _linha_paciente(email="", diagnostico="Outro", alergias="Ovo")]
    prev = _pacientes(client, cen, linhas).get_json()["linhas"]
    assert prev[0]["paciente_status"] == "novo"
    assert prev[1]["paciente_status"] == "existente" and prev[1]["avisos"]
    assert prev[1]["ficha_mantidos"] == 1
    _pacientes(client, cen, linhas, "confirmar")
    rows = db_ctx.query("SELECT id FROM pacientes WHERE nome = 'Lucas Almeida'")
    assert len(rows) == 1
    ficha = _ficha(db_ctx, rows[0]["id"])
    assert ficha["diagnostico"] == "TEA" and ficha["alergias"] == "Ovo"


def test_reimportar_mesma_planilha_nao_duplica(client, db_ctx):
    cen = _clinica_com_modulo(db_ctx)
    linhas = [_linha_paciente(diagnostico="TEA")]
    _pacientes(client, cen, linhas, "confirmar")
    _pacientes(client, cen, linhas, "confirmar")
    assert db_ctx.query_one("SELECT COUNT(*) c FROM pacientes WHERE nome = 'Lucas Almeida'")["c"] == 1


def test_auditoria_importar_pacientes(client, db_ctx):
    cen = _clinica_com_modulo(db_ctx)
    _pacientes(client, cen, [_linha_paciente()], "confirmar")
    log = db_ctx.query_one("SELECT * FROM auditoria WHERE acao = 'importar' AND entidade = 'pacientes'")
    assert log is not None and log["usuario_id"] == cen.gestor_a["id"] and "1 registros" in log["detalhes"]
