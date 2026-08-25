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
