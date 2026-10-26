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
