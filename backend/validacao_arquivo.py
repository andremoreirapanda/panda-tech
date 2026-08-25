"""
Validação de conteúdo real de arquivos enviados como base64 (foto, áudio,
vídeo, PDF) — recomendação 1 da auditoria de segurança de 25/08/2026
("Faltava validação de conteúdo real — magic bytes — nos uploads; hoje só
o tamanho é checado").

Todo upload deste projeto é armazenado inline como base64 dentro do banco
(nunca como arquivo no disco), então não há risco de path traversal — mas
sem checar os bytes reais, um cliente mal-intencionado (ou só um bug no
frontend) pode enviar qualquer coisa dizendo que é uma "foto", inclusive
um payload malicioso, e o backend aceitava sem olhar. Este módulo decodifica
o começo do conteúdo e confere a assinatura (magic bytes) contra os
formatos realmente esperados para cada categoria de anexo, antes de
gravar no banco.

Isto é uma camada defensiva adicional — não substitui a extensão que o
usuário escolheu, só recusa quando o conteúdo claramente NÃO é o que diz
ser.
"""
import base64
import binascii


def _decodificar_binario(base64_conteudo):
    """Decodifica um base64 (aceita prefixo opcional 'data:...;base64,').
    Retorna os bytes decodificados, ou None se não for base64 válido.

    CORREÇÃO DE AUDITORIA (25/08/2026, achado do CodeQL em cima de
    frontend/js/util.js::renderAvatarUsuario/renderFotoPaciente/renderLogoClinica,
    que interpolam este valor sem escapar dentro de `src="data:image/...;base64,${...}"`):
    validate=True é essencial aqui. Com validate=False (o padrão do Python),
    b64decode() só IGNORA caracteres fora do alfabeto base64 antes de
    decodificar — ou seja, alguém podia mandar um base64 de imagem válido
    com caracteres extras tipo `" onerror="alert(1)` misturados no meio;
    esses caracteres eram descartados só para o CHECK de assinatura (que
    então passava normalmente), mas a string ORIGINAL — com as aspas e tudo
    — é o que ficava salvo no banco e ia parar, sem escape, dentro do
    atributo `src` no frontend. Com validate=True, qualquer caractere fora
    do alfabeto base64 (inclusive aspas, `<`, `>`) já rejeita aqui, antes
    mesmo de gravar.
    """
    conteudo = base64_conteudo or ""
    if conteudo.startswith("data:") and ";base64," in conteudo:
        conteudo = conteudo.split(";base64,", 1)[1]
    try:
        return base64.b64decode(conteudo, validate=True)
    except (binascii.Error, ValueError):
        return None


def _e_imagem(b):
    if b[:3] == b"\xff\xd8\xff":
        return True  # JPEG
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return True  # PNG
    if b[:4] == b"GIF8":
        return True  # GIF87a/GIF89a
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return True  # WEBP
    return False


def _e_audio(b):
    if b[:3] == b"ID3":
        return True  # MP3 com tag ID3
    if len(b) >= 2 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0:
        return True  # MP3 sem tag (frame sync)
    if b[:4] == b"RIFF" and b[8:12] == b"WAVE":
        return True  # WAV
    if b[:4] == b"OggS":
        return True  # OGG
    if b[4:8] == b"ftyp":
        return True  # M4A/AAC (container ISO-BMFF)
    return False


def _e_video(b):
    if b[4:8] == b"ftyp":
        return True  # MP4/MOV/M4V (container ISO-BMFF)
    if b[:4] == b"\x1a\x45\xdf\xa3":
        return True  # WEBM/MKV
    if b[:4] == b"RIFF" and b[8:12] == b"AVI ":
        return True  # AVI
    return False


def _e_pdf(b):
    return b[:5] == b"%PDF-"


CATEGORIAS = {
    "imagem": _e_imagem,
    "foto": _e_imagem,
    "audio": _e_audio,
    "video": _e_video,
    "pdf": _e_pdf,
}


def _assinatura_bate(binario, categoria):
    if not binario:
        return False
    if categoria == "qualquer_midia":
        return any(fn(binario) for fn in (_e_imagem, _e_audio, _e_video, _e_pdf))
    fn = CATEGORIAS.get(categoria)
    return bool(fn) and fn(binario)


def validar_arquivo_base64(base64_conteudo, categoria):
    """Confere se o conteúdo base64 recebido realmente tem a assinatura de
    algum formato válido para a categoria informada.

    categoria: "imagem"/"foto", "audio", "video", "pdf", ou "qualquer_midia"
    (usado pela Biblioteca, onde o campo "tipo" é pedagógico, não indica o
    formato do arquivo).

    Retorna (ok: bool, mensagem_erro: str | None).
    """
    binario = _decodificar_binario(base64_conteudo)
    if binario is None:
        return False, "O conteúdo enviado não é um arquivo em base64 válido."
    if not _assinatura_bate(binario, categoria):
        return False, "O conteúdo do arquivo não corresponde a um formato permitido para este tipo de anexo."
    return True, None
