"""Financeiro etapa 1 (spec 07/11/2026): acordos, itens, status novos, especialidade na consulta."""
import os
import sqlite3

import pytest

import db
import migrar_financeiro_cobranca
from factories import DuasClinicas


def _cols(tabela):
    return {l["name"] for l in db.get_db().execute(f"PRAGMA table_info({tabela})").fetchall()}


def test_colunas_e_tabelas_existem(db_ctx):
    assert {"fin_cobrar_falta", "fin_repasse_falta"} <= _cols("organizacoes")
    assert "especialidade" in _cols("consultas")
    assert {"id", "organizacao_id", "paciente_id", "especialidade", "tipo", "ciclo", "vence_dias",
            "valor_centavos", "dia_vencimento", "sessoes_total", "parcelas", "primeiro_vencimento",
            "inicio", "fim", "status", "criado_por", "criado_em", "encerrado_em"} <= _cols("acordos_pagamento")
    assert {"organizacao_id", "acordo_id", "tipo", "periodo_inicio", "periodo_fim", "desconto_centavos",
            "desconto_motivo", "liberada_em", "revisar", "revisar_motivo"} <= _cols("cobrancas")
    assert {"id", "cobranca_id", "consulta_id", "data_hora", "procedimento_nome", "valor_centavos"} <= _cols("cobranca_itens")
    assert {"recebido_por_usuario_id", "recebido_por_nome", "estornado_em", "estorno_motivo",
            "estornado_por"} <= _cols("pagamentos")
    assert {"consulta_id", "decisao", "valor_centavos", "motivo", "decidido_por",
            "decidido_em"} <= _cols("consulta_decisao_cobranca")
    assert {"consulta_id", "acordo_id", "numero"} <= _cols("acordo_pacote_consumo")


def _paciente(cen):
    return cen.paciente_a1


def _cobranca(pac, status):
    return db.execute(
        "INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status) VALUES (?, 'x', 100, '2026-12-01', ?)",
        (pac, status))


def test_status_rascunho_e_cancelado_aceitos(db_ctx):
    pac = _paciente(DuasClinicas())
    for st in ("rascunho", "pendente", "parcial", "pago", "vencido", "cancelado"):
        _cobranca(pac, st)
    with pytest.raises(sqlite3.IntegrityError):
        _cobranca(pac, "inventado")
    db.get_db().rollback()


def test_forma_cartao_credito_aceita(db_ctx):
    pac = _paciente(DuasClinicas())
    cob = _cobranca(pac, "pendente")
    for forma in ("pix", "cartao", "cartao_credito", "cartao_debito", "boleto", "dinheiro", "transferencia"):
        db.execute("INSERT INTO pagamentos (cobranca_id, valor_centavos, forma) VALUES (?, 1, ?)", (cob, forma))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO pagamentos (cobranca_id, valor_centavos, forma) VALUES (?, 1, 'cheque')", (cob,))
    db.get_db().rollback()


def test_item_mesma_consulta_duas_vezes_falha(db_ctx):
    cen = DuasClinicas()
    pac = _paciente(cen)
    cob = _cobranca(pac, "rascunho")
    prof = cen.prof_a1["id"]
    cons = db.execute("INSERT INTO consultas (paciente_id, profissional_id, data_hora) VALUES (?, ?, '2026-11-10 09:00:00')", (pac, prof))
    sql = "INSERT INTO cobranca_itens (cobranca_id, consulta_id, valor_centavos) VALUES (?, ?, 100)"
    db.execute(sql, (cob, cons))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(sql, (cob, cons))
    db.get_db().rollback()


def test_dois_acordos_ativos_mesma_especialidade_falha(db_ctx):
    cen = DuasClinicas()
    pac = _paciente(cen)
    sql = ("INSERT INTO acordos_pagamento (organizacao_id, paciente_id, especialidade, tipo, inicio) "
           "VALUES (?, ?, ?, 'avulsa', '2026-11-01')")
    db.execute(sql, (cen.org_a, pac, "Fono"))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(sql, (cen.org_a, pac, " fono "))
    db.get_db().rollback()
    db.execute(sql, (cen.org_a, pac, "TO"))


# --- migração sobre banco no formato antigo ---------------------------------

def _banco_antigo(caminho, prof_especialidade):
    c = sqlite3.connect(caminho)
    c.executescript("""
    CREATE TABLE organizacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL);
    CREATE TABLE usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, organizacao_id INTEGER, nome TEXT, especialidade TEXT);
    CREATE TABLE pacientes (id INTEGER PRIMARY KEY AUTOINCREMENT, organizacao_id INTEGER, nome TEXT);
    CREATE TABLE consultas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
        profissional_id INTEGER NOT NULL REFERENCES usuarios(id),
        data_hora TEXT NOT NULL, status TEXT DEFAULT 'agendada');
    CREATE TABLE cobrancas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
        descricao TEXT NOT NULL, valor_centavos INTEGER NOT NULL, vencimento TEXT NOT NULL,
        status TEXT DEFAULT 'pendente' CHECK(status IN ('pendente','pago','vencido')),
        criado_em TEXT DEFAULT (datetime('now')),
        mp_payment_id TEXT, pix_qr_code TEXT, pix_qr_code_base64 TEXT, pix_copia_cola TEXT);
    CREATE TABLE pagamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cobranca_id INTEGER NOT NULL REFERENCES cobrancas(id),
        valor_centavos INTEGER NOT NULL,
        forma TEXT DEFAULT 'pix' CHECK(forma IN ('pix','cartao','boleto','dinheiro','transferencia')),
        pago_em TEXT DEFAULT (datetime('now')));
    INSERT INTO organizacoes (nome) VALUES ('Clinica');
    INSERT INTO pacientes (organizacao_id, nome) VALUES (1, 'Pac');
    INSERT INTO consultas (paciente_id, profissional_id, data_hora) VALUES (1, 1, '2026-11-10 09:00:00');
    INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status) VALUES (1, 'Antiga', 5000, '2026-11-30', 'pago');
    INSERT INTO pagamentos (cobranca_id, valor_centavos, forma) VALUES (1, 5000, 'pix');
    """)
    c.execute("INSERT INTO usuarios (organizacao_id, nome, especialidade) VALUES (1, 'Prof', ?)", (prof_especialidade,))
    c.commit()
    c.close()


@pytest.fixture
def banco_antigo(tmp_path, monkeypatch):
    def criar(esp):
        caminho = str(tmp_path / "antigo.db")
        if os.path.exists(caminho):
            os.remove(caminho)
        _banco_antigo(caminho, esp)
        monkeypatch.setattr(db, "DB_PATH", caminho)
        monkeypatch.setattr(db, "_standalone_conn", None)
        return caminho
    yield criar
    if db._standalone_conn is not None:
        db._standalone_conn.close()
    monkeypatch.setattr(db, "_standalone_conn", None)


def test_migracao_idempotente(banco_antigo):
    caminho = banco_antigo("Fono")
    migrar_financeiro_cobranca.migrar()
    migrar_financeiro_cobranca.migrar()
    c = sqlite3.connect(caminho)
    cols = lambda t: {r[1] for r in c.execute(f"PRAGMA table_info({t})")}
    assert {"acordo_id", "tipo", "desconto_centavos", "organizacao_id"} <= cols("cobrancas")
    assert {"estornado_em", "recebido_por_nome"} <= cols("pagamentos")
    assert {"fin_cobrar_falta", "fin_repasse_falta"} <= cols("organizacoes")
    assert c.execute("SELECT COUNT(*) FROM cobrancas").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM pagamentos").fetchone()[0] == 1
    row = c.execute("SELECT descricao, valor_centavos, status, tipo, organizacao_id, desconto_centavos FROM cobrancas").fetchone()
    assert row == ("Antiga", 5000, "pago", "manual", 1, 0)
    # os CHECKs novos valem
    c.execute("INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status) VALUES (1,'r',1,'2026-12-01','rascunho')")
    c.execute("INSERT INTO pagamentos (cobranca_id, valor_centavos, forma) VALUES (1, 1, 'cartao_credito')")
    c.close()


def test_migracao_preenche_especialidade(banco_antigo):
    caminho = banco_antigo(" Fono ")
    migrar_financeiro_cobranca.migrar()
    c = sqlite3.connect(caminho)
    assert c.execute("SELECT especialidade FROM consultas").fetchone()[0] == "Fono"
    c.close()
    db._standalone_conn.close()
    db._standalone_conn = None
    caminho = banco_antigo(None)
    migrar_financeiro_cobranca.migrar()
    c = sqlite3.connect(caminho)
    assert c.execute("SELECT especialidade FROM consultas").fetchone()[0] == "Geral"
    c.close()


def test_um_mes_de_mensalidade_por_acordo(db_ctx):
    cen = DuasClinicas()
    pac = _paciente(cen)
    aid = db.execute("INSERT INTO acordos_pagamento (organizacao_id, paciente_id, especialidade, tipo, inicio) "
                     "VALUES (?, ?, 'Geral', 'mensalidade', '2026-11-01')", (cen.org_a, pac))
    sql = ("INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, acordo_id, tipo, periodo_inicio) "
           "VALUES (?, 'm', 100, '2026-11-10', ?, ?, '2026-11-01')")
    db.execute(sql, (pac, aid, "mensalidade"))
    db.execute(sql, (pac, aid, "periodo"))
    db.execute(sql, (pac, aid, "periodo"))   # o índice só vale para mensalidade
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(sql, (pac, aid, "mensalidade"))
    db.get_db().rollback()


def test_migracao_cria_indice_da_mensalidade(banco_antigo):
    caminho = banco_antigo("Fono")
    migrar_financeiro_cobranca.migrar()
    migrar_financeiro_cobranca.migrar()
    c = sqlite3.connect(caminho)
    assert c.execute("SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'idx_cobranca_mensalidade_mes'").fetchone()
    c.close()


def test_tabelas_sem_id_estao_no_conjunto_sem_returning():
    assert {"consulta_decisao_cobranca", "acordo_pacote_consumo"} <= db._TABELAS_SEM_ID_AUTO
