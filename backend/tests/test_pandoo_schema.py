"""Pandoo (25/09/2026): tabelas e colunas novas existem no schema de teste,
e pandoo_jogos (sem coluna id) grava pelo db.execute sem quebrar."""
import db
from factories import nova_organizacao, novo_exercicio


def _colunas(tabela):
    return {c["name"] for c in db.query(f"PRAGMA table_info({tabela})")}


def test_tabelas_e_colunas_novas(db_ctx):
    assert {"exercicio_id", "modelo", "conteudo_json", "regras_json", "cenario", "total_itens", "atualizado_em"} <= _colunas("pandoo_jogos")
    assert {"organizacao_id", "paciente_id", "exercicio_id", "missao_id", "atividade_id", "modelo", "encerrado_antes",
            "total_rodadas", "acertos", "a_treinar", "detalhes_json", "usuario_id", "data_local"} <= _colunas("pandoo_resultados")
    assert {"pandoo_cenario_padrao", "pandoo_cenario_imagem", "pandoo_cenario_tom"} <= _colunas("organizacoes")
    assert "liberado_admin" in _colunas("modulos_clinica")


def test_pandoo_jogos_sem_id_grava_pelo_execute(db_ctx):
    org = nova_organizacao()
    ex = novo_exercicio(org, "Roleta", tipo="jogo")
    db.execute("INSERT INTO pandoo_jogos (exercicio_id, modelo, conteudo_json, regras_json, total_itens) VALUES (?, ?, ?, ?, ?)",
               (ex["id"], "roleta", '{"versao":1,"itens":[]}', "{}", 0))
    assert db.query_one("SELECT modelo FROM pandoo_jogos WHERE exercicio_id = ?", (ex["id"],))["modelo"] == "roleta"


def test_cenario_padrao_da_clinica_e_bambu(db_ctx):
    org = nova_organizacao()
    assert db.query_one("SELECT pandoo_cenario_padrao FROM organizacoes WHERE id = ?", (org,))["pandoo_cenario_padrao"] == "bambu"


def test_tabela_sem_id_registrada_no_db():
    assert "pandoo_jogos" in db._TABELAS_SEM_ID_AUTO
