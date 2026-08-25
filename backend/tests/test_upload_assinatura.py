"""
Regressão para a validação de conteúdo real de arquivos (magic bytes) —
recomendação 1 da auditoria de segurança de 25/08/2026 ("hoje só o tamanho
é checado, não os bytes/assinatura do arquivo").

Duas camadas de teste: unidade pura da função de validação (sem Flask/DB,
mesmo padrão de test_webhook_signature.py), e um teste de integração
confirmando que uma rota real de upload recusa um "arquivo" falso.
"""
import base64

from validacao_arquivo import validar_arquivo_base64

from factories import nova_organizacao, novo_usuario
from conftest import autenticado

JPEG_VALIDO = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 20).decode()
PNG_VALIDO = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20).decode()
MP3_VALIDO = base64.b64encode(b"ID3" + b"\x00" * 20).decode()
MP4_VALIDO = base64.b64encode(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 20).decode()
PDF_VALIDO = base64.b64encode(b"%PDF-1.4\n" + b"\x00" * 20).decode()
SCRIPT_DISFARCADO = base64.b64encode(b"<script>alert(document.cookie)</script>").decode()


def test_imagem_real_e_aceita():
    ok, erro = validar_arquivo_base64(JPEG_VALIDO, "imagem")
    assert ok is True and erro is None
    ok, erro = validar_arquivo_base64(PNG_VALIDO, "imagem")
    assert ok is True and erro is None


def test_conteudo_nao_correspondente_e_recusado():
    """O achado original: um script disfarçado de 'foto' passava porque só o
    tamanho era checado."""
    ok, erro = validar_arquivo_base64(SCRIPT_DISFARCADO, "imagem")
    assert ok is False and erro


def test_audio_real_e_aceito_mas_nao_como_imagem():
    ok, _ = validar_arquivo_base64(MP3_VALIDO, "audio")
    assert ok is True
    ok, _ = validar_arquivo_base64(MP3_VALIDO, "imagem")
    assert ok is False


def test_video_real_e_aceito():
    ok, _ = validar_arquivo_base64(MP4_VALIDO, "video")
    assert ok is True


def test_qualquer_midia_aceita_pdf_para_biblioteca():
    ok, _ = validar_arquivo_base64(PDF_VALIDO, "qualquer_midia")
    assert ok is True
    # mas PDF não é uma "imagem" válida
    ok, _ = validar_arquivo_base64(PDF_VALIDO, "imagem")
    assert ok is False


def test_conteudo_vazio_ou_nao_base64_e_recusado():
    ok, erro = validar_arquivo_base64("", "imagem")
    assert ok is False and erro
    ok, erro = validar_arquivo_base64("!!! isso não é base64 !!!", "imagem")
    assert ok is False and erro


def test_rota_real_recusa_avatar_falso(client, db_ctx):
    """Integração: POST /api/pessoas/profissionais com um avatar_base64 que
    não é uma imagem de verdade deve ser recusado com 400, não gravado."""
    org = nova_organizacao("Clínica Upload")
    gestor = novo_usuario(org, "Gestora", "gestora@upload.com", "gestor")

    resp = autenticado(client, gestor).post(
        "/api/pessoas/profissionais",
        json={"nome": "Novo Prof", "email": "novo@upload.com", "avatar_base64": SCRIPT_DISFARCADO},
    )
    assert resp.status_code == 400
    assert "erro" in resp.get_json()


def test_rota_real_aceita_avatar_de_verdade(client, db_ctx):
    org = nova_organizacao("Clínica Upload 2")
    gestor = novo_usuario(org, "Gestora", "gestora2@upload.com", "gestor")

    resp = autenticado(client, gestor).post(
        "/api/pessoas/profissionais",
        json={"nome": "Novo Prof 2", "email": "novo2@upload.com", "avatar_base64": JPEG_VALIDO},
    )
    assert resp.status_code == 201
