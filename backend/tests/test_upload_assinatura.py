"""
Regressão para a validação de conteúdo real de arquivos (magic bytes) —
recomendação 1 da auditoria de segurança de 25/08/2026 ("hoje só o tamanho
é checado, não os bytes/assinatura do arquivo").

Duas camadas de teste: unidade pura da função de validação (sem Flask/DB,
mesmo padrão de test_webhook_signature.py), e um teste de integração
confirmando que uma rota real de upload recusa um "arquivo" falso.
"""
import base64

from validacao_arquivo import validar_arquivo_base64, detectar_tipo_arquivo

from factories import nova_organizacao, novo_usuario
from conftest import autenticado

JPEG_VALIDO = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 20).decode()
PNG_VALIDO = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20).decode()
MP3_VALIDO = base64.b64encode(b"ID3" + b"\x00" * 20).decode()
MP4_VALIDO = base64.b64encode(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 20).decode()
PDF_VALIDO = base64.b64encode(b"%PDF-1.4\n" + b"\x00" * 20).decode()
SCRIPT_DISFARCADO = base64.b64encode(b"<script>alert(document.cookie)</script>").decode()

# HEIC/HEIF (09/09/2026, achado do usuário): formato padrão de foto do
# iPhone desde o iOS 11 — usa o mesmo container ISO-BMFF ("ftyp") de
# MP4/MOV/M4A, só muda a "brand" nos bytes 8-12.
HEIC_VALIDO = base64.b64encode(b"\x00\x00\x00\x18ftypheic" + b"\x00" * 20).decode()
# Variante em que a major brand (bytes 8-12) não é conclusiva ("isom",
# genérica) e a marca de imagem só aparece na lista de "compatible brands"
# logo em seguida — também acontece em fotos reais.
HEIC_MARCA_COMPATIVEL = base64.b64encode(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00mif1heic" + b"\x00" * 20).decode()
M4A_VALIDO = base64.b64encode(b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00" + b"\x00" * 20).decode()


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


# ---------------------------------------------------------------- HEIC/HEIF (Fase 3, 09/09/2026)
# Achado do usuário: fotos tiradas com iPhone (formato HEIC, padrão desde o
# iOS 11) apareciam quebradas na tela da criança. Causa: o container HEIC é
# o mesmo ISO-BMFF ("ftyp") usado por vídeo MP4/MOV e áudio M4A — sem checar
# a "brand" certa, toda foto HEIC virava "vídeo" por engano.

def test_heic_e_reconhecido_como_imagem_na_validacao_por_categoria():
    ok, erro = validar_arquivo_base64(HEIC_VALIDO, "imagem")
    assert ok is True and erro is None


def test_detectar_tipo_arquivo_reconhece_heic_como_imagem():
    assert detectar_tipo_arquivo(HEIC_VALIDO) == "imagem"


def test_detectar_tipo_arquivo_reconhece_heic_por_marca_compativel():
    """Algumas câmeras só marcam o formato real numa "compatible brand"
    (depois da major brand), não na principal — tem que olhar as duas."""
    assert detectar_tipo_arquivo(HEIC_MARCA_COMPATIVEL) == "imagem"


def test_detectar_tipo_arquivo_nao_confunde_m4a_com_imagem():
    """Continua reconhecendo áudio M4A corretamente — a correção do HEIC não
    pode fazer um arquivo de áudio real virar "imagem" por engano."""
    assert detectar_tipo_arquivo(M4A_VALIDO) == "audio"


def test_detectar_tipo_arquivo_reconhece_outros_formatos():
    assert detectar_tipo_arquivo(JPEG_VALIDO) == "imagem"
    assert detectar_tipo_arquivo(PNG_VALIDO) == "imagem"
    assert detectar_tipo_arquivo(MP3_VALIDO) == "audio"
    assert detectar_tipo_arquivo(MP4_VALIDO) == "video"
    assert detectar_tipo_arquivo(PDF_VALIDO) == "pdf"
    assert detectar_tipo_arquivo(SCRIPT_DISFARCADO) is None
