"""Anexos do Diário no Supabase Storage (25/11/2026). O Storage é simulado."""
import pytest

import armazenamento_service as arm
from factories import DuasClinicas, vincular_responsavel

from conftest import autenticado

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 52
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 56


@pytest.fixture
def storage(monkeypatch):
    """Liga o Storage e guarda o que foi 'enviado' num dicionário."""
    monkeypatch.setenv("SUPABASE_URL", "https://exemplo.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "chave-secreta-teste")
    monkeypatch.delenv("DIARIO_ANEXO_LIMITE_MB", raising=False)
    estado = {"arquivos": {}, "apagados": []}
    monkeypatch.setattr(arm, "criar_link_envio", lambda caminho: f"https://exemplo.supabase.co/storage/v1/object/upload/sign/diario-anexos/{caminho}?token=t")
    monkeypatch.setattr(arm, "ler_inicio", lambda caminho, n=64: estado["arquivos"].get(caminho))
    monkeypatch.setattr(arm, "criar_link_leitura", lambda caminho, segundos=3600: f"https://exemplo.supabase.co/storage/v1/object/sign/diario-anexos/{caminho}?token=l")
    monkeypatch.setattr(arm, "apagar", lambda caminho: estado["apagados"].append(caminho) or True)
    return estado


def _diario(db_ctx, cen, compartilhado=1):
    return db_ctx.execute(
        "INSERT INTO diarios_terapeuticos (paciente_id, profissional_id, evolucao_clinica, compartilhado_familia) VALUES (?, ?, 'x', ?)",
        (cen.paciente_a1, cen.prof_a1["id"], compartilhado),
    )


def _pedir_envio(c, diario_id, **extra):
    corpo = {"tipo": "video", "nome_arquivo": "sessao.mp4", "mime": "video/mp4", "tamanho_bytes": 5_000_000, **extra}
    return c.post(f"/api/diario/{diario_id}/anexo/envio", json=corpo)


# ---------------------------------------------------------------- config e limite

def test_config_sem_storage(client, db_ctx, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    cen = DuasClinicas()
    r = autenticado(client, cen.prof_a1).get("/api/diario/anexos/config")
    assert r.get_json() == {"storage": False, "limite_mb": 4}


def test_config_com_storage_e_limite_da_variavel(client, db_ctx, storage, monkeypatch):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)
    assert c.get("/api/diario/anexos/config").get_json() == {"storage": True, "limite_mb": 30}
    monkeypatch.setenv("DIARIO_ANEXO_LIMITE_MB", "200")
    assert c.get("/api/diario/anexos/config").get_json()["limite_mb"] == 200


def test_limite_invalido_volta_ao_padrao(monkeypatch):
    for valor in ("abc", "0", "-5", ""):
        monkeypatch.setenv("DIARIO_ANEXO_LIMITE_MB", valor)
        assert arm.limite_anexo_mb() == 30
    monkeypatch.setenv("DIARIO_ANEXO_LIMITE_MB", "12,5")
    assert arm.limite_anexo_bytes() == int(12.5 * 1024 * 1024)


# ---------------------------------------------------------------- envio

def test_envio_sem_storage_da_503(client, db_ctx, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    cen = DuasClinicas()
    assert _pedir_envio(autenticado(client, cen.prof_a1), _diario(db_ctx, cen)).status_code == 503


def test_envio_devolve_link_e_caminho_do_registro(client, db_ctx, storage):
    cen = DuasClinicas()
    diario_id = _diario(db_ctx, cen)
    r = _pedir_envio(autenticado(client, cen.prof_a1), diario_id)
    assert r.status_code == 200, r.get_data(as_text=True)
    dados = r.get_json()
    assert dados["caminho"].startswith(f"clinica-{cen.org_a}/diario-{diario_id}/")
    assert dados["caminho"].endswith(".mp4")
    assert dados["url_envio"].startswith("https://exemplo.supabase.co/")


def test_envio_recusa_acima_do_limite_e_tipo_invalido(client, db_ctx, storage):
    cen = DuasClinicas()
    c, diario_id = autenticado(client, cen.prof_a1), _diario(db_ctx, cen)
    assert _pedir_envio(c, diario_id, tamanho_bytes=31 * 1024 * 1024).status_code == 400
    assert _pedir_envio(c, diario_id, tipo="pdf").status_code == 400


def test_envio_outra_clinica_e_responsavel(client, db_ctx, storage):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    diario_id = _diario(db_ctx, cen)
    assert _pedir_envio(autenticado(client, cen.gestor_b), diario_id).status_code == 403
    assert _pedir_envio(autenticado(client, cen.resp_a1), diario_id).status_code == 403


# ---------------------------------------------------------------- confirmar

def _confirmar(c, diario_id, caminho, **extra):
    corpo = {"caminho": caminho, "tipo": "video", "nome_arquivo": "sessao.mp4", "mime": "video/mp4", **extra}
    return c.post(f"/api/diario/{diario_id}/anexo/confirmar", json=corpo)


def test_confirmar_grava_anexo_no_storage(client, db_ctx, storage):
    cen = DuasClinicas()
    c, diario_id = autenticado(client, cen.prof_a1), _diario(db_ctx, cen)
    caminho = _pedir_envio(c, diario_id).get_json()["caminho"]
    storage["arquivos"][caminho] = (MP4, 5_000_000)
    r = _confirmar(c, diario_id, caminho)
    assert r.status_code == 201, r.get_data(as_text=True)
    linha = db_ctx.query_one("SELECT * FROM diario_anexos WHERE id = ?", (r.get_json()["id"],))
    assert linha["storage_path"] == caminho and linha["conteudo_base64"] is None
    assert linha["tamanho_bytes"] == 5_000_000 and linha["mime"] == "video/mp4" and linha["tipo"] == "video"
    # Confirmar duas vezes não duplica.
    assert _confirmar(c, diario_id, caminho).status_code == 409


def test_confirmar_recusa_caminho_de_outro_registro(client, db_ctx, storage):
    cen = DuasClinicas()
    c = autenticado(client, cen.prof_a1)
    meu, outro = _diario(db_ctx, cen), _diario(db_ctx, cen)
    caminho = _pedir_envio(c, outro).get_json()["caminho"]
    storage["arquivos"][caminho] = (MP4, 1000)
    for forjado in (caminho, f"clinica-{cen.org_a}/diario-{meu}/../x.mp4", "qualquer.mp4"):
        assert _confirmar(c, meu, forjado).status_code == 400
    assert db_ctx.query_one("SELECT COUNT(*) AS n FROM diario_anexos")["n"] == 0


def test_confirmar_sem_arquivo_no_storage(client, db_ctx, storage):
    cen = DuasClinicas()
    c, diario_id = autenticado(client, cen.prof_a1), _diario(db_ctx, cen)
    caminho = _pedir_envio(c, diario_id).get_json()["caminho"]
    assert _confirmar(c, diario_id, caminho).status_code == 400


def test_confirmar_recusa_assinatura_errada_e_apaga(client, db_ctx, storage):
    cen = DuasClinicas()
    c, diario_id = autenticado(client, cen.prof_a1), _diario(db_ctx, cen)
    caminho = _pedir_envio(c, diario_id).get_json()["caminho"]
    storage["arquivos"][caminho] = (b"<html><script>" + b"\x00" * 50, 1000)
    assert _confirmar(c, diario_id, caminho).status_code == 400
    assert storage["apagados"] == [caminho]


def test_confirmar_recusa_tamanho_real_acima_do_limite_e_apaga(client, db_ctx, storage):
    cen = DuasClinicas()
    c, diario_id = autenticado(client, cen.prof_a1), _diario(db_ctx, cen)
    caminho = _pedir_envio(c, diario_id).get_json()["caminho"]
    storage["arquivos"][caminho] = (MP4, 40 * 1024 * 1024)
    assert _confirmar(c, diario_id, caminho).status_code == 400
    assert storage["apagados"] == [caminho]


def test_storage_fora_do_ar_da_502(client, db_ctx, storage, monkeypatch):
    def falha(*a, **k):
        raise arm.ErroArmazenamento("O armazenamento de arquivos não respondeu. Tente de novo em instantes.")
    cen = DuasClinicas()
    c, diario_id = autenticado(client, cen.prof_a1), _diario(db_ctx, cen)
    caminho = _pedir_envio(c, diario_id).get_json()["caminho"]
    monkeypatch.setattr(arm, "criar_link_envio", falha)
    monkeypatch.setattr(arm, "ler_inicio", falha)
    r = _pedir_envio(c, diario_id)
    assert r.status_code == 502 and "não respondeu" in r.get_json()["erro"]
    assert _confirmar(c, diario_id, caminho).status_code == 502


# ---------------------------------------------------------------- ver e remover

def _anexo_no_storage(client, db_ctx, cen, storage, diario_id, conteudo=PNG, tipo="foto"):
    c = autenticado(client, cen.prof_a1)
    caminho = _pedir_envio(c, diario_id, tipo=tipo, nome_arquivo="f.png", mime="image/png").get_json()["caminho"]
    storage["arquivos"][caminho] = (conteudo, 2000)
    return _confirmar(c, diario_id, caminho, tipo=tipo, nome_arquivo="f.png", mime="image/png").get_json()["id"], caminho


def test_ver_anexo_devolve_link_e_nao_base64(client, db_ctx, storage):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    diario_id = _diario(db_ctx, cen)
    anexo_id, caminho = _anexo_no_storage(client, db_ctx, cen, storage, diario_id)
    for quem in (cen.prof_a1, cen.resp_a1):
        dados = autenticado(client, quem).get(f"/api/diario/anexo/{anexo_id}").get_json()
        assert dados["url"].endswith(f"{caminho}?token=l") and "conteudo_base64" not in dados
        assert dados["mime"] == "image/png"


def test_responsavel_nao_ve_anexo_de_registro_nao_compartilhado(client, db_ctx, storage):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    anexo_id, _ = _anexo_no_storage(client, db_ctx, cen, storage, _diario(db_ctx, cen, compartilhado=0))
    assert autenticado(client, cen.resp_a1).get(f"/api/diario/anexo/{anexo_id}").status_code == 403


def test_remover_apaga_o_arquivo(client, db_ctx, storage):
    cen = DuasClinicas()
    anexo_id, caminho = _anexo_no_storage(client, db_ctx, cen, storage, _diario(db_ctx, cen))
    assert autenticado(client, cen.prof_a1).delete(f"/api/diario/anexo/{anexo_id}").status_code == 200
    assert storage["apagados"] == [caminho]


# ---------------------------------------------------------------- CSP

def test_csp_inclui_storage_so_quando_configurado(client, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert "supabase.co" not in client.get("/api/health").headers["Content-Security-Policy"]
    monkeypatch.setenv("SUPABASE_URL", "https://exemplo.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    csp = client.get("/api/health").headers["Content-Security-Policy"]
    for diretiva in ("img-src", "media-src", "connect-src"):
        fontes = next(p for p in csp.split(";") if p.strip().startswith(diretiva)).split()
        assert fontes[-1] == "https://exemplo.supabase.co"
    assert "chave" not in csp and " k;" not in csp
