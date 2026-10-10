"""
Versão nos endereços do front-end (09/10/2026).

Em produção o LiteSpeed entrega JS e CSS com cache de 1 ano
(`Cache-Control: max-age=31536000`), e o celular não tem como forçar a
atualização: ficava rodando scripts antigos. Agora o `index.html` (que nunca
fica em cache) sai com `?v=<impressão do conteúdo>` em cada script e CSS — o
arquivo que mudou ganha endereço novo e é baixado na hora; o que não mudou
continua no cache. A impressão é calculada quando o app sobe (o deploy faz
`touch tmp/restart.txt`). A versão geral vai numa <meta> e em /api/versao,
para o app aberto perceber que há versão nova.
"""
import hashlib
import os
import re

_PASTAS = ("js", "css")
_TAMANHO = 10
_REF_LOCAL = re.compile(r'((?:src|href)=")(/(?:js|css)/[^"?#]+)(")')


def calcular_versoes(frontend_dir):
    """{"arquivos": {"/js/x.js": "<10 hex>"}, "geral": "<10 hex>"} dos .js/.css."""
    arquivos = {}
    for pasta in _PASTAS:
        raiz = os.path.join(frontend_dir, pasta)
        for dirpath, _dirs, nomes in os.walk(raiz):
            for nome in nomes:
                if not nome.endswith((".js", ".css")):
                    continue
                caminho = os.path.join(dirpath, nome)
                with open(caminho, "rb") as f:
                    impressao = hashlib.sha256(f.read()).hexdigest()[:_TAMANHO]
                relativo = os.path.relpath(caminho, frontend_dir).replace(os.sep, "/")
                arquivos["/" + relativo] = impressao
    geral = hashlib.sha256("".join(f"{k}={v};" for k, v in sorted(arquivos.items())).encode()).hexdigest()[:_TAMANHO]
    return {"arquivos": arquivos, "geral": geral}


def index_versionado(html, versoes):
    """Acrescenta ?v= aos scripts/CSS locais conhecidos e a <meta name="versao-app">."""
    def trocar(m):
        impressao = versoes["arquivos"].get(m.group(2))
        return f"{m.group(1)}{m.group(2)}?v={impressao}{m.group(3)}" if impressao else m.group(0)

    saida = _REF_LOCAL.sub(trocar, html)
    meta = f'<meta name="versao-app" content="{versoes["geral"]}">'
    charset = re.search(r"<meta charset=[^>]*>", saida)
    if charset:   # o charset precisa continuar no começo do <head>
        return saida[:charset.end()] + "\n" + meta + saida[charset.end():]
    return saida.replace("<head>", "<head>\n" + meta, 1) if "<head>" in saida else meta + saida
