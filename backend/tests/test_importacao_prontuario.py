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


# ------------------------------------------------- etapa 2: evoluções → Diário

from datetime import timedelta  # noqa: E402

import ausencias_service  # noqa: E402


def _cenario_evolucoes(db):
    cen = _clinica_com_modulo(db)
    cen.lucas = novo_paciente(cen.org_a, "Lucas Almeida", "2019-03-14")
    vincular_responsavel(cen.resp_a1["id"], cen.lucas)
    return cen


def _evolucao(nome="LÚCAS  almeida", nascimento="14/03/2019", data="12/08/2026",
              email="prof.a1@a.com", evolucao="Trabalhou fonemas /p/ e /b/.", **extra):
    linha = {"paciente_nome": nome, "paciente_nascimento": nascimento, "data_atendimento": data,
             "profissional_email": email, "evolucao": evolucao}
    linha.update(extra)
    return linha


def _evolucoes(client, usuario, linhas, etapa="preview"):
    return autenticado(client, usuario).post(f"/api/importacao/evolucoes/{etapa}", json={"linhas": linhas})


def _diarios(db, paciente_id):
    return db.query("SELECT * FROM diarios_terapeuticos WHERE paciente_id = ? ORDER BY id", (paciente_id,))


def test_evolucao_importada_vai_para_o_diario(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    prev = _evolucoes(client, cen.gestor_a, [_evolucao(observacao="Cansado")]).get_json()
    assert prev["prontas"] == 1 and prev["linhas"][0]["status"] == "pronta"
    assert prev["linhas"][0]["profissional"] == "Prof A1"
    r = _evolucoes(client, cen.gestor_a, [_evolucao(observacao="Cansado")], "confirmar")
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["importadas"] == 1
    [d] = _diarios(db_ctx, cen.lucas)
    assert d["profissional_id"] == cen.prof_a1["id"]
    assert d["data_atendimento"] == "2026-08-12"
    assert d["evolucao_clinica"] == "Trabalhou fonemas /p/ e /b/."
    assert d["observacao"] == "Cansado"
    assert d["origem"] == "importacao"
    assert d["compartilhado_familia"] == 0
    assert not d["mensagem_familia"]
    assert d["consulta_id"] is None and d["jornada_id"] is None


def test_evolucao_usa_jornada_ativa(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    jid = db_ctx.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, 'Falar')", (cen.lucas,))
    _evolucoes(client, cen.gestor_a, [_evolucao()], "confirmar")
    assert _diarios(db_ctx, cen.lucas)[0]["jornada_id"] == jid


def test_profissional_arquivado_casa_e_excluido_nao(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    db_ctx.execute("UPDATE usuarios SET ativo = 0 WHERE id = ?", (cen.prof_a1["id"],))
    novo_usuario(cen.org_a, "Saiu", "saiu@a.com", "profissional", ativo=0, excluido_em="2026-10-01 10:00:00")
    _evolucoes(client, cen.gestor_a, [_evolucao(), _evolucao(email="saiu@a.com", evolucao="Outra")], "confirmar")
    a, b = _diarios(db_ctx, cen.lucas)
    assert a["profissional_id"] == cen.prof_a1["id"]
    assert b["profissional_id"] == cen.gestor_a["id"]


def test_profissional_nao_achado_fica_com_quem_importa(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    linha = _evolucao(email="dra.ana@outro.com", profissional_nome="Dra. Ana")
    prev = _evolucoes(client, cen.gestor_a, [linha]).get_json()["linhas"][0]
    assert prev["status"] == "aviso" and prev["avisos"]
    _evolucoes(client, cen.gestor_a, [linha], "confirmar")
    [d] = _diarios(db_ctx, cen.lucas)
    assert d["profissional_id"] == cen.gestor_a["id"]
    assert d["evolucao_clinica"].startswith("Profissional no sistema anterior: Dra. Ana.")
    assert d["evolucao_clinica"].endswith("Trabalhou fonemas /p/ e /b/.")


def test_sem_profissional_nenhum_fica_sem_frase(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    _evolucoes(client, cen.gestor_a, [_evolucao(email="")], "confirmar")
    [d] = _diarios(db_ctx, cen.lucas)
    assert d["profissional_id"] == cen.gestor_a["id"]
    assert d["evolucao_clinica"] == "Trabalhou fonemas /p/ e /b/."


def test_prefixo_nao_reprova_texto_no_limite(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    linha = _evolucao(email="", profissional_nome="Dra. Ana", evolucao="x" * 10000)
    assert _evolucoes(client, cen.gestor_a, [linha], "confirmar").get_json()["importadas"] == 1


def test_evolucao_acima_do_limite(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    prev = _evolucoes(client, cen.gestor_a, [_evolucao(evolucao="x" * 10001), _evolucao(observacao="y" * 5001)]).get_json()
    assert [l["status"] for l in prev["linhas"]] == ["erro", "erro"]


def test_data_futura_paciente_inexistente_e_homonimos_dao_erro(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    novo_paciente(cen.org_a, "Bia Souza", "2018-01-01")
    novo_paciente(cen.org_a, "Bia  Souza", "2018-01-01")
    amanha = (ausencias_service.hoje_brasilia() + timedelta(days=1)).isoformat()
    hoje = ausencias_service.hoje_brasilia().isoformat()
    prev = _evolucoes(client, cen.gestor_a, [
        _evolucao(data=amanha),
        _evolucao(nome="Ninguém"),
        _evolucao(nome="Bia Souza", nascimento="2018-01-01"),
        _evolucao(data="31/02/2026"),
        _evolucao(data=hoje),
    ]).get_json()["linhas"]
    assert [l["status"] for l in prev] == ["erro", "erro", "erro", "erro", "pronta"]
    assert any("não encontrado" in e for e in prev[1]["erros"])
    assert any("mais de um paciente" in e for e in prev[2]["erros"])


def test_reimportar_nao_duplica_mesmo_editado(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    _evolucoes(client, cen.gestor_a, [_evolucao()], "confirmar")
    [d] = _diarios(db_ctx, cen.lucas)
    r = autenticado(client, cen.gestor_a).put(f"/api/diario/{d['id']}", json={"evolucao_clinica": "Editado depois"})
    assert r.status_code == 200
    prev = _evolucoes(client, cen.gestor_a, [_evolucao()]).get_json()
    assert prev["linhas"][0]["status"] == "ja_importada" and prev["ja_importadas"] == 1
    r = _evolucoes(client, cen.gestor_a, [_evolucao()], "confirmar").get_json()
    assert r["importadas"] == 0 and r["puladas"] == 1
    assert len(_diarios(db_ctx, cen.lucas)) == 1


def test_duplicata_no_mesmo_lote(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    prev = _evolucoes(client, cen.gestor_a, [_evolucao(), _evolucao(nome="Lucas Almeida")]).get_json()
    assert [l["status"] for l in prev["linhas"]] == ["pronta", "ja_importada"]
    _evolucoes(client, cen.gestor_a, [_evolucao(), _evolucao()], "confirmar")
    assert len(_diarios(db_ctx, cen.lucas)) == 1


def test_familia_nao_ve_e_nao_e_notificada(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    antes = db_ctx.query_one("SELECT COUNT(*) c FROM notificacoes")["c"]
    _evolucoes(client, cen.gestor_a, [_evolucao()], "confirmar")
    assert db_ctx.query_one("SELECT COUNT(*) c FROM notificacoes")["c"] == antes
    r = autenticado(client, cen.resp_a1).get(f"/api/diario/paciente/{cen.lucas}")
    assert r.status_code == 200 and r.get_json() == []
    r = autenticado(client, cen.gestor_a).get(f"/api/diario/paciente/{cen.lucas}")
    assert r.get_json()[0]["origem"] == "importacao"


def test_sem_modulo_403_e_so_gestor(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    assert _evolucoes(client, cen.prof_a1, [_evolucao()]).status_code == 403
    assert _evolucoes(client, cen.gestor_b, [_evolucao()]).status_code == 403  # clínica B sem o módulo


def test_paciente_de_outra_clinica_nao_e_encontrado(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    novo_paciente(cen.org_b, "Rafa Lima", "2017-05-05")
    prev = _evolucoes(client, cen.gestor_a, [_evolucao(nome="Rafa Lima", nascimento="2017-05-05")]).get_json()
    assert prev["linhas"][0]["status"] == "erro"


def test_auditoria_importar_evolucoes(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    _evolucoes(client, cen.gestor_a, [_evolucao()], "confirmar")
    log = db_ctx.query_one("SELECT * FROM auditoria WHERE acao = 'importar' AND entidade = 'evolucoes'")
    assert log is not None and "1 registros" in log["detalhes"]


def test_erro_no_meio_nao_grava_nada(client, db_ctx, monkeypatch):
    from blueprints import importacao_bp
    cen = _cenario_evolucoes(db_ctx)
    original = importacao_bp.execute
    chamadas = {"n": 0}

    def falha_no_segundo(sql, params=()):
        if "INSERT INTO diarios_terapeuticos" in sql:
            chamadas["n"] += 1
            if chamadas["n"] == 2:
                raise RuntimeError("falha simulada")
        return original(sql, params)

    monkeypatch.setattr(importacao_bp, "execute", falha_no_segundo)
    monkeypatch.setattr(importacao_bp, "LINHAS_POR_INSERT", 1)  # um INSERT por linha: falha na 2ª
    r = _evolucoes(client, cen.gestor_a, [_evolucao(), _evolucao(evolucao="Outra")], "confirmar")
    assert r.status_code == 500
    assert "Nada foi gravado" in r.get_json()["erro"]
    assert _diarios(db_ctx, cen.lucas) == []


def test_erro_no_confirmar_vai_para_o_log(client, db_ctx, monkeypatch, caplog):
    from blueprints import importacao_bp
    cen = _cenario_evolucoes(db_ctx)

    def falha(sql, params=()):
        raise RuntimeError("falha simulada no banco")

    monkeypatch.setattr(importacao_bp, "execute", falha)
    r = _evolucoes(client, cen.gestor_a, [_evolucao()], "confirmar")
    assert r.status_code == 500
    assert "falha simulada no banco" in caplog.text


def test_confirmar_grava_em_poucos_insert(client, db_ctx, monkeypatch):
    # Supabase fica longe do servidor: uma ida ao banco por linha estoura o
    # tempo do Passenger num lote de 1.000 (revisão final, 26/10/2026).
    from blueprints import importacao_bp
    cen = _cenario_evolucoes(db_ctx)
    db_ctx.execute("INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, 'Falar')", (cen.lucas,))
    original = importacao_bp.execute
    inserts = {"n": 0}

    def contar(sql, params=()):
        if "INSERT INTO diarios_terapeuticos" in sql:
            inserts["n"] += 1
        return original(sql, params)

    monkeypatch.setattr(importacao_bp, "execute", contar)
    linhas = [_evolucao(evolucao=f"Sessão {i}") for i in range(250)]
    r = _evolucoes(client, cen.gestor_a, linhas, "confirmar")
    assert r.get_json()["importadas"] == 250
    assert inserts["n"] <= 3
    diarios = _diarios(db_ctx, cen.lucas)
    assert len(diarios) == 250
    assert len({d["importacao_chave"] for d in diarios}) == 250
    assert all(d["jornada_id"] and d["origem"] == "importacao" and d["compartilhado_familia"] == 0 for d in diarios)


def test_sem_colunas_503(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    _sem_colunas_novas(db_ctx)
    r = _evolucoes(client, cen.gestor_a, [_evolucao()])
    assert r.status_code == 503 and "atualização do banco" in r.get_json()["erro"]
    assert autenticado(client, cen.gestor_a).get(f"/api/diario/paciente/{cen.lucas}").status_code == 200


def test_mais_de_1000_linhas_400(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    assert _evolucoes(client, cen.gestor_a, [_evolucao()] * 1001).status_code == 400


def test_ficha_do_paciente_traz_origem_e_funciona_sem_migracao(client, db_ctx):
    cen = _cenario_evolucoes(db_ctx)
    _evolucoes(client, cen.gestor_a, [_evolucao()], "confirmar")
    r = autenticado(client, cen.gestor_a).get(f"/api/jornada/paciente/{cen.lucas}")
    assert r.get_json()["diarios_recentes"][0]["origem"] == "importacao"
    _sem_colunas_novas(db_ctx)
    importacao_service._colunas_ok[0] = False
    assert autenticado(client, cen.gestor_a).get(f"/api/jornada/paciente/{cen.lucas}").status_code == 200
