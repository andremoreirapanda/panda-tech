"""
Validação de campos de texto curtos que o front-end exibe como emoji.

Correção de auditoria (23/09/2026): logo_emoji (clínica), icone_emoji
(pastas da Biblioteca) e avatar_mascote (na criação do paciente) eram
gravados sem validação nenhuma e várias telas interpolam esses valores
direto no HTML — um gestor podia salvar HTML no logo_emoji e ele aparecia
renderizado no painel do Admin da plataforma (injeção de HTML entre
clínicas). A CSP (script-src 'self') já impedia scripts inline, mas não
links/formulários falsos. Esta é a camada do backend; o front-end também
passou a escapar esses campos.
"""

# Tamanho máximo em code points: cobre emojis compostos (família com ZWJ,
# bandeiras, tom de pele), que chegam a ~11 code points.
_MAX_CODE_POINTS = 16

# Únicos caracteres ASCII que aparecem em emojis de verdade (keycaps: #️⃣, 1️⃣...).
_ASCII_PERMITIDO = set("#*0123456789")


def emoji_seguro(valor, padrao):
    """Devolve `valor` se parece um emoji (curto, sem nenhum caractere ASCII
    além dos de keycap — logo, sem '<', '>', aspas, '&' nem espaços), ou
    `padrao` caso contrário."""
    if not isinstance(valor, str) or not valor or len(valor) > _MAX_CODE_POINTS:
        return padrao
    if any(ord(c) < 128 and c not in _ASCII_PERMITIDO for c in valor):
        return padrao
    if all(c in _ASCII_PERMITIDO for c in valor):
        return padrao
    return valor
