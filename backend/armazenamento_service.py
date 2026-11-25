"""
Armazenamento de arquivos do Diário no Supabase Storage (25/11/2026).

Spec: docs/superpowers/specs/2026-11-25-anexos-diario-storage-design.md

Tudo o que fala com o Storage está aqui (API REST, via `requests`), para que
trocar de fornecedor (ex.: Cloudflare R2) mexa só neste arquivo. O navegador
envia o arquivo direto para o Storage por um link de envio de uso único; o
servidor só cria os links, confere o começo do arquivo e apaga.

Variáveis de ambiente:
- SUPABASE_URL           ex.: https://<projeto>.supabase.co
- SUPABASE_SERVICE_KEY   chave service_role (ou secret key) — SÓ no servidor
- DIARIO_ANEXO_LIMITE_MB limite por arquivo (padrão 30). No plano gratuito do
                         Supabase o teto global de upload é 50 MB; acima disso,
                         suba também em Supabase → Storage → Settings.
- DIARIO_ANEXO_BUCKET    nome do bucket privado (padrão diario-anexos; o app
                         cria sozinho na primeira vez)

Sem SUPABASE_URL/SUPABASE_SERVICE_KEY, `configurado()` é False e o Diário
continua guardando anexos em base64 no banco, até 4 MB (como antes).
"""
import os
import re
from urllib.parse import quote, urlparse

import requests

LIMITE_PADRAO_MB = 30
BUCKET_PADRAO = "diario-anexos"
VALIDADE_LEITURA_S = 3600
_TIMEOUT_S = 15
_MSG_FORA = "O armazenamento de arquivos não respondeu. Tente de novo em instantes."


class ErroArmazenamento(Exception):
    """Falha ao falar com o Storage. A mensagem é para o usuário (sem a chave)."""


def _url():
    return (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")


def _chave():
    return (os.getenv("SUPABASE_SERVICE_KEY") or "").strip()


def configurado():
    return bool(_url() and _chave())


def bucket():
    return (os.getenv("DIARIO_ANEXO_BUCKET") or "").strip() or BUCKET_PADRAO


def limite_anexo_mb():
    """Limite por arquivo, em MB, lido de DIARIO_ANEXO_LIMITE_MB (padrão 30)."""
    try:
        valor = float(str(os.getenv("DIARIO_ANEXO_LIMITE_MB") or "").replace(",", "."))
        if not valor > 0:
            raise ValueError
    except ValueError:
        valor = float(LIMITE_PADRAO_MB)
    return int(valor) if valor.is_integer() else valor


def limite_anexo_bytes():
    return int(limite_anexo_mb() * 1024 * 1024)


def origem():
    """'https://<projeto>.supabase.co' para a CSP, ou None sem Storage."""
    if not configurado():
        return None
    partes = urlparse(_url())
    if partes.scheme not in ("http", "https") or not re.fullmatch(r"[A-Za-z0-9.\-]+(:\d+)?", partes.netloc or ""):
        return None
    return f"{partes.scheme}://{partes.netloc}"


def _pedir(metodo, rota, **kwargs):
    cabecalhos = {"apikey": _chave(), "Authorization": f"Bearer {_chave()}"}
    cabecalhos.update(kwargs.pop("headers", {}))
    try:
        return requests.request(metodo, f"{_url()}/storage/v1{rota}", headers=cabecalhos, timeout=_TIMEOUT_S, **kwargs)
    except requests.RequestException:
        raise ErroArmazenamento(_MSG_FORA) from None


def _objeto(caminho):
    return f"{quote(bucket(), safe='')}/{quote(caminho, safe='/')}"


def _bucket_inexistente(resp):
    # O Storage 1.98 (25/11/2026) responde ao link de envio sem bucket com
    # "The related resource does not exist"; versões antigas, "Bucket not found".
    texto = (resp.text or "").lower()
    return resp.status_code in (400, 404) and (
        "bucket not found" in texto or "related resource does not exist" in texto)


def _garantir_bucket():
    resp = _pedir("POST", "/bucket", json={"id": bucket(), "name": bucket(), "public": False})
    if not resp.ok and "already exists" not in (resp.text or "").lower():
        raise ErroArmazenamento("Não foi possível preparar o armazenamento de arquivos.")


def criar_link_envio(caminho):
    """Link de envio de uso único (PUT do navegador, direto para o Storage)."""
    rota = f"/object/upload/sign/{_objeto(caminho)}"
    resp = _pedir("POST", rota)
    if _bucket_inexistente(resp):
        _garantir_bucket()
        resp = _pedir("POST", rota)
    if not resp.ok:
        raise ErroArmazenamento(_MSG_FORA)
    relativo = (resp.json() or {}).get("url") or ""
    if not relativo.startswith("/"):
        raise ErroArmazenamento(_MSG_FORA)
    return f"{_url()}/storage/v1{relativo}"


def ler_inicio(caminho, n=64):
    """(primeiros bytes, tamanho total) do arquivo, ou None se ele não existe."""
    resp = _pedir("GET", f"/object/authenticated/{_objeto(caminho)}",
                  headers={"Range": f"bytes=0-{n - 1}"}, stream=True)
    try:
        if resp.status_code in (400, 404):
            return None
        if resp.status_code not in (200, 206):
            raise ErroArmazenamento(_MSG_FORA)
        intervalo = re.search(r"/(\d+)\s*$", resp.headers.get("Content-Range") or "")
        if intervalo:
            total = int(intervalo.group(1))
        else:
            try:
                total = int(resp.headers.get("Content-Length") or "")
            except ValueError:
                raise ErroArmazenamento(_MSG_FORA) from None
        inicio = b""
        for pedaco in resp.iter_content(chunk_size=n):
            inicio += pedaco
            if len(inicio) >= n:
                break
        return inicio[:n], total
    finally:
        resp.close()


def criar_link_leitura(caminho, segundos=VALIDADE_LEITURA_S):
    """Link temporário para ver/tocar o arquivo (aceita Range: o vídeo toca sem baixar tudo)."""
    resp = _pedir("POST", f"/object/sign/{_objeto(caminho)}", json={"expiresIn": int(segundos)})
    if not resp.ok:
        raise ErroArmazenamento("Não foi possível abrir este anexo agora. Tente de novo em instantes.")
    relativo = (resp.json() or {}).get("signedURL") or (resp.json() or {}).get("signedUrl") or ""
    if not relativo.startswith("/"):
        raise ErroArmazenamento("Não foi possível abrir este anexo agora. Tente de novo em instantes.")
    return f"{_url()}/storage/v1{relativo}"


def apagar(caminho):
    """Apaga o arquivo; nunca levanta exceção (o registro no banco é o que manda)."""
    try:
        return _pedir("DELETE", f"/object/{quote(bucket(), safe='')}", json={"prefixes": [caminho]}).ok
    except ErroArmazenamento:
        return False
