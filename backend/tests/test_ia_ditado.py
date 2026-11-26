"""IA fase 1: rotas do ditado (ia_bp)."""
import io

import pytest

import db
import ia_service
import planos_padrao
from factories import DuasClinicas, novo_usuario
from conftest import autenticado

AUDIO = b"\x1a\x45\xdf\xa3" + b"0" * 2000


@pytest.fixture
def cenario(client, db_ctx, monkeypatch):
    planos_padrao.criar_planos_padrao_para_teste()
    cen = DuasClinicas()
    db.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    pid = db.query_one("SELECT id FROM planos WHERE codigo = 'pro'")["id"]
    db.execute("UPDATE planos SET ia_minutos_mes = 10 WHERE id = ?", (pid,))
    db.execute("INSERT INTO planos_modulos (plano_id, modulo_codigo) VALUES (?, 'ia')", (pid,))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste")
    monkeypatch.setattr(ia_service, "_tabelas_ok", [False])
    chamadas = []

    def falso(audio, mime, nome, modelo):
        chamadas.append(1)
        return {"text": " Paciente evoluiu bem. ", "usage": {"type": "duration", "seconds": 7}}

    monkeypatch.setattr(ia_service, "_chamar_openai", falso)
    cen.chamadas = chamadas
    cen.secretaria = novo_usuario(cen.org_a, "Sec", "sec@a.com", "secretaria")
    return cen


def _post(c, usuario, audio=AUDIO, duracao="10"):
    autenticado(c, usuario)
    dados = {"duracao_segundos": duracao}
    if audio is not None:
        dados["audio"] = (io.BytesIO(audio), "ditado.webm", "audio/webm")
    return c.post("/api/ia/ditado", data=dados, content_type="multipart/form-data")


def _uso(org, segundos, sucesso=1):
    db.execute("INSERT INTO ia_uso (organizacao_id, recurso, mes, segundos, sucesso) VALUES (?, 'ditado', ?, ?, ?)",
               (org, ia_service.mes_atual(), segundos, sucesso))


def test_profissional_dita_e_recebe_texto(client, cenario):
    r = _post(client, cenario.prof_a1)
    assert r.status_code == 200
    d = r.get_json()
    assert d["texto"] == "Paciente evoluiu bem."
    assert d["minutos_restantes"] == 9  # 600 - 7 = 593 s
    linhas = db.query("SELECT * FROM ia_uso")
    assert len(linhas) == 1 and linhas[0]["sucesso"] == 1 and linhas[0]["segundos"] == 7
    g = autenticado(client, cenario.gestor_a).get("/api/ia/ditado/config")
    assert g.status_code == 200 and g.get_json()["disponivel"] is True


def test_secretaria_responsavel_e_admin_403(client, cenario):
    admin = novo_usuario(None, "Admin", "admin@saas.com", "admin_master")
    for u in (cenario.secretaria, cenario.resp_a1, admin):
        assert _post(client, u).status_code == 403
        assert autenticado(client, u).get("/api/ia/ditado/config").status_code == 403
    assert cenario.chamadas == []


def test_clinica_sem_modulo_403(client, cenario):
    assert _post(client, cenario.prof_b1).status_code == 403
    assert autenticado(client, cenario.prof_b1).get("/api/ia/ditado/config").status_code == 403


def test_sem_chave_503_e_config_indisponivel(client, cenario, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    c = autenticado(client, cenario.prof_a1).get("/api/ia/ditado/config").get_json()
    assert c["disponivel"] is False and c["motivo"] == "sem_chave"
    r = _post(client, cenario.prof_a1)
    assert r.status_code == 503 and r.get_json()["codigo"] == "indisponivel"


def test_sem_migracao_config_indisponivel_sem_500(client, cenario):
    db.execute("DROP TABLE ia_uso")
    db.execute("DROP TABLE ia_creditos")
    r = autenticado(client, cenario.prof_a1).get("/api/ia/ditado/config")
    assert r.status_code == 200
    assert r.get_json()["disponivel"] is False and r.get_json()["motivo"] == "sem_migracao"
    r = _post(client, cenario.prof_a1)
    assert r.status_code == 503 and r.get_json()["codigo"] == "indisponivel"
    assert cenario.chamadas == []


def test_cota_esgotada_nao_chama_fornecedor(client, cenario):
    _uso(cenario.org_a, 600)
    r = _post(client, cenario.prof_a1)
    assert r.status_code == 409 and r.get_json()["codigo"] == "cota_esgotada"
    assert cenario.chamadas == []
    c = autenticado(client, cenario.prof_a1).get("/api/ia/ditado/config").get_json()
    assert c["disponivel"] is True and c["minutos_restantes"] == 0


def test_credito_do_mes_libera(client, cenario):
    _uso(cenario.org_a, 600)
    db.execute("INSERT INTO ia_creditos (organizacao_id, mes, minutos) VALUES (?, ?, 5)",
               (cenario.org_a, ia_service.mes_atual()))
    assert _post(client, cenario.prof_a1).status_code == 200


def test_falha_fornecedor_502_sem_gastar(client, cenario, monkeypatch):
    def quebra(*a, **k):
        raise ia_service.FalhaFornecedorIA("x")
    monkeypatch.setattr(ia_service, "_chamar_openai", quebra)
    antes = autenticado(client, cenario.prof_a1).get("/api/ia/ditado/config").get_json()["minutos_restantes"]
    r = _post(client, cenario.prof_a1)
    assert r.status_code == 502 and r.get_json()["codigo"] == "falha_transcricao"
    linha = db.query_one("SELECT * FROM ia_uso")
    assert linha["sucesso"] == 0 and linha["segundos"] == 0
    depois = autenticado(client, cenario.prof_a1).get("/api/ia/ditado/config").get_json()["minutos_restantes"]
    assert antes == depois


@pytest.mark.parametrize("audio,duracao", [
    (None, "10"),
    (b"\x89PNG\r\n\x1a\n" + b"0" * 2000, "10"),
    (b"\x1a\x45\xdf\xa3" + b"0" * (16 * 1024 * 1024), "10"),
    (AUDIO, "400"),
    (AUDIO, "abc"),
    (AUDIO, "nan"),
    (AUDIO, "inf"),
    (AUDIO, "-5"),
    (b"", "10"),
], ids=["sem_arquivo", "png", "16mb", "400s", "abc", "nan", "inf", "negativo", "vazio"])
def test_audio_invalido(client, cenario, audio, duracao):
    r = _post(client, cenario.prof_a1, audio=audio, duracao=duracao)
    assert r.status_code == 400 and r.get_json()["codigo"] == "audio_invalido"
    assert cenario.chamadas == []


def test_aceita_ogg_e_mp3(client, cenario):
    assert _post(client, cenario.prof_a1, audio=b"OggS" + b"0" * 500).status_code == 200
    assert _post(client, cenario.prof_a1, audio=b"ID3" + b"0" * 500).status_code == 200


def test_nada_do_conteudo_fica_salvo(client, cenario, tmp_path, monkeypatch):
    vazio = tmp_path / "cwd"
    vazio.mkdir()
    monkeypatch.chdir(vazio)
    assert _post(client, cenario.prof_a1).status_code == 200
    for tabela in ("ia_uso", "auditoria"):
        for linha in db.query(f"SELECT * FROM {tabela}"):
            assert "evoluiu" not in str(dict(linha))
    assert list(vazio.iterdir()) == []
