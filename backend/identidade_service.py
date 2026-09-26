"""
White Label completo (spec 25/09/2026): a regra única da identidade da clínica.

Com o módulo white_label, valem os valores da clínica (NULL vira o padrão);
sem ele, valem os padrões Panda Tech — os valores da clínica ficam guardados
e voltam se o módulo for ligado de novo. Logo e nome da clínica nunca são
travados. O `/auth/me` já devolve a identidade efetiva, então o front-end
inteiro respeita a trava sem checar o módulo tela a tela.
"""
import hashlib
import re
import unicodedata

from db import query_one, execute
from validacao_arquivo import _decodificar_binario

PADROES = {
    "cor_primaria": "#5B4FE9", "cor_secundaria": "#FFB84D",
    "nome_ia": "Lumi", "nome_moeda_gamificacao": "XP", "nome_medalha_generico": "Medalha",
    "app_nome": "Panda Tech", "login_mensagem": "Entre com sua conta para continuar a jornada.",
    "mundo_fonte": "fredoka", "mundo_fundo": "estrelas", "mundo_mascote": "🐻",
    "mundo_comemoracao": "Muito bem!!",
}
CAMPOS_GATED = tuple(PADROES)
FONTES = ("fredoka", "baloo", "nunito", "escolar")
FUNDOS = ("estrelas", "bambu", "mar", "espaco", "clinica", "pandoo")
MAX_IMAGEM_PEQUENA = 500 * 1024
_ENDERECO = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
# Passam sempre, com ou sem o módulo (não são personalização travada).
_PASSAM_SEMPRE = ("id", "nome", "logo_emoji", "logo_base64", "plano", "especialidades_json",
                  "agenda_permissao_total_padrao", "agenda_hora_inicio", "agenda_hora_fim",
                  "pandoo_cenario_padrao", "pandoo_cenario_tom", "endereco_login")


def slug_de(texto, existe, padrao="clinica"):
    """Texto → slug sem acento ([a-z0-9-]); sufixo -2, -3… enquanto `existe(slug)`."""
    base = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:36].strip("-") or padrao
    valor, n = base, 2
    while existe(valor):
        valor, n = f"{base}-{n}", n + 1
    return valor


def _endereco_existe(valor):
    return bool(query_one("SELECT 1 FROM organizacoes WHERE endereco_login = ?", (valor,)))


def gerar_endereco_login(nome):
    base = slug_de(nome, lambda s: False)
    if len(base) < 3:
        base = "clinica"
    return slug_de(base, _endereco_existe)


def garantir_endereco_login(org_id):
    """Clínicas anteriores ao White Label nascem sem endereço: gera na primeira leitura."""
    org = query_one("SELECT nome, endereco_login FROM organizacoes WHERE id = ?", (org_id,))
    if not org:
        return None
    if org["endereco_login"]:
        return org["endereco_login"]
    valor = gerar_endereco_login(org["nome"])
    execute("UPDATE organizacoes SET endereco_login = ? WHERE id = ?", (valor, org_id))
    return valor


def validar_endereco_login(valor, org_id):
    """Devolve (valor, erro, status) — status 400 (formato) ou 409 (em uso)."""
    valor = valor.strip().lower() if isinstance(valor, str) else ""
    if not _ENDERECO.match(valor):
        return None, ("Endereço inválido: use de 3 a 40 letras minúsculas, números e hífens "
                      "(sem começar ou terminar com hífen)."), 400
    dono = query_one("SELECT id FROM organizacoes WHERE endereco_login = ?", (valor,))
    if dono and dono["id"] != org_id:
        return None, "Este endereço já está em uso por outra clínica.", 409
    return valor, None, 200


def validar_texto(valor, maximo, rotulo):
    """Texto curto exibido para famílias/crianças: vazio = volta ao padrão (None)."""
    if valor is None:
        return None, None
    if not isinstance(valor, str):
        return None, f"{rotulo} inválido."
    valor = valor.strip()
    if not valor:
        return None, None
    if len(valor) > maximo:
        return None, f"{rotulo}: até {maximo} caracteres."
    if "<" in valor or ">" in valor:
        return None, f"{rotulo}: não use os caracteres < e >."
    return valor, None


def mime_imagem(b64):
    """PNG, JPEG ou WebP pelos bytes iniciais — o tipo servido pelas rotas públicas."""
    binario = _decodificar_binario(b64) if isinstance(b64, str) and b64 else None
    if not binario:
        return None
    if binario.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if binario.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if binario[:4] == b"RIFF" and binario[8:12] == b"WEBP":
        return "image/webp"
    return None


def imagem_pequena_valida(b64):
    """Ícone do app e mascote: PNG/JPEG/WebP até 500 KB."""
    return isinstance(b64, str) and len(b64) * 3 // 4 <= MAX_IMAGEM_PEQUENA and mime_imagem(b64) is not None


def _resumo_sql(coluna):
    # Tamanho + os últimos 64 caracteres do base64: basta para saber se a
    # imagem existe e para a versão mudar quando ela muda — sem trazer do banco
    # (Supabase) as centenas de KB de cada imagem. SQL válido em SQLite e Postgres.
    return (f"CASE WHEN {coluna} IS NULL OR {coluna} = '' THEN NULL ELSE "
            f"CAST(length({coluna}) AS TEXT) || ':' || substr({coluna}, length({coluna}) - 63, 64) END AS {coluna}")


# Revisão final (25/09/2026): /auth/me, o mascote padrão e a rota pública
# de dados leem as imagens só "resumidas" (identidade_efetiva só precisa
# saber se existem e de algo que mude junto com elas).
IMAGENS_RESUMIDAS_SQL = ", ".join(_resumo_sql(c) for c in ("app_icone_base64", "mundo_mascote_imagem", "pandoo_cenario_imagem"))


def versao_imagens(org):
    """Muda quando alguma imagem muda — vai na URL (?v=) para furar o cache."""
    partes = [org.get("app_icone_base64") or "", org.get("mundo_mascote_imagem") or "",
              org.get("pandoo_cenario_imagem") or ""]
    if not any(partes):
        return ""
    return hashlib.sha1("|".join(partes).encode()).hexdigest()[:10]


def identidade_efetiva(org, ativo):
    """A identidade que vale agora. Nunca inclui as imagens grandes (elas vão
    pelas rotas públicas); só as flags `tem_*` e a versão para o cache."""
    e = {k: org.get(k) for k in _PASSAM_SEMPRE if k in org}
    for campo, padrao in PADROES.items():
        e[campo] = (org.get(campo) or padrao) if ativo else padrao
    e["white_label_ativo"] = bool(ativo)
    e["tem_icone"] = bool(ativo and org.get("app_icone_base64"))
    e["tem_mascote_imagem"] = bool(ativo and org.get("mundo_mascote_imagem"))
    e["tem_cenario_imagem"] = bool(ativo and org.get("pandoo_cenario_imagem"))
    e["versao_imagens"] = versao_imagens(org) if ativo else ""
    if e["mundo_mascote"] == "clinica" and not e["tem_mascote_imagem"]:
        e["mundo_mascote"] = PADROES["mundo_mascote"]
    return e
