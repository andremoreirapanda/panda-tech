"""
Regressão para os cabeçalhos de segurança HTTP (auditoria de 25/08/2026,
recomendação 4 — CSP endurecida depois de confirmar que o front-end não
depende de <script> nem onXXX= inline).

Trava o essencial: script-src 'self' (o ganho real contra XSS) e
frame-ancestors 'none' (clickjacking) precisam sempre estar presentes.
Não testa a lista inteira de diretivas byte a byte — isso deixaria o teste
frágil a ajustes finos (ex: adicionar um novo host de imagem) sem ganhar
nada em proteção real.
"""


def test_csp_trava_script_src_e_frame_ancestors(client):
    resp = client.get("/api/auth/login", follow_redirects=False)
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp


def test_csp_nao_permite_script_de_qualquer_origem(client):
    """O achado que essa correção fecha: antes a CSP só tinha frame-ancestors,
    então um <script> injetado (XSS refletido/armazenado) rodava livremente."""
    resp = client.get("/api/auth/login")
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "script-src *" not in csp
    assert "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]


def test_headers_de_seguranca_basicos_presentes(client):
    resp = client.get("/api/auth/login")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Strict-Transport-Security")


def test_csp_permite_midia_data_uri(client):
    """Achado do usuário (09/09/2026): vídeo/áudio de exercício da Biblioteca
    aparecia preto/mudo (0:00) na tela da criança — não era bug de detecção
    de tipo (o backend já identificava corretamente como "video" pelos
    magic bytes), era a CSP bloqueando o próprio <video><source
    src="data:video/mp4;base64,...">: img-src já tinha a exceção "data:"
    (por isso fotos funcionavam), mas media-src não, então caía no
    default-src 'self' e o navegador recusava tocar a mídia."""
    resp = client.get("/api/auth/login")
    csp = resp.headers.get("Content-Security-Policy", "")
    media_src = [d for d in csp.split(";") if d.strip().startswith("media-src")]
    assert media_src, "CSP precisa de uma diretiva media-src explícita"
    assert "data:" in media_src[0]
    assert "'self'" in media_src[0]


def test_csp_permite_embed_de_youtube_e_vimeo(client):
    """Mesmo achado do usuário (09/09/2026), segunda metade: um exercício com
    link do YouTube/Vimeo mostra um <iframe src="https://www.youtube.com/embed/...">
    (ou player.vimeo.com) — sem frame-src explícita, o navegador recusava
    carregar o player (caía no default-src 'self'). frame-ancestors 'none'
    continua intacto (isso protege o Panda Tech contra ser embutido em OUTRO
    site — é o sentido contrário de frame-src, que controla o que o Panda
    Tech pode embutir)."""
    resp = client.get("/api/auth/login")
    csp = resp.headers.get("Content-Security-Policy", "")
    frame_src = [d for d in csp.split(";") if d.strip().startswith("frame-src")]
    assert frame_src, "CSP precisa de uma diretiva frame-src explícita"
    assert "https://www.youtube.com" in frame_src[0]
    assert "https://player.vimeo.com" in frame_src[0]
    assert "frame-ancestors 'none'" in csp
