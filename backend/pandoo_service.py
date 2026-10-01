"""
Pandoo (25/09/2026) — regras puras dos jogos: valida e normaliza o conteúdo
no formato único (v1), as regras de cada modelo e o resultado de uma partida.
Sem acesso a banco — as rotas ficam em blueprints/pandoo_bp.py.
"""
import json
import unicodedata

from validacao_arquivo import validar_arquivo_base64, _decodificar_binario

MODELOS = {"roleta", "quiz"}
CENARIOS = {"bambu", "mar", "espaco", "clinica"}
TONS = {"claro", "escuro"}

MIN_ITENS, MAX_ITENS = 2, 24
MAX_TEXTO = 80
MAX_IMAGEM = 300 * 1024
MAX_AUDIO = 600 * 1024
MAX_CONTEUDO = 10 * 1024 * 1024
MAX_IMAGEM_CENARIO = 800 * 1024
MAX_RODADAS = 500

REGRAS_PADRAO = {
    "roleta": {"fim": "todas", "giros": 10, "mostrar_palavra": True, "som": True, "voz": True},
    # Pandoo fase 2 (30/09/2026): Quiz.
    "quiz": {"modo": "ouvir", "opcoes": 3, "fim": "todas", "perguntas": 10, "som": True, "voz": True},
}
NOME_MODELO = {"roleta": "a roleta", "quiz": "o quiz"}
MAX_DISTRATORES = {"quiz": 3}
_EBML = b"\x1a\x45\xdf\xa3"  # WebM: o Chrome grava voz nesse formato


class ErroPandoo(ValueError):
    pass


def _bytes_b64(b64):
    return len(b64) * 3 // 4


def _eh_webm(b64):
    # Decodifica o valor INTEIRO com validate=True (revisão final): olhar só o
    # começo deixava passar aspas/HTML depois do cabeçalho — a mesma brecha
    # que a auditoria de 25/08 fechou em validacao_arquivo._decodificar_binario.
    binario = _decodificar_binario(b64)
    return binario is not None and binario[:4] == _EBML


def _midia(valor, tipo, limite, rotulo_limite, posicao):
    if valor in (None, ""):
        return None
    if not isinstance(valor, str):
        raise ErroPandoo(f"Item {posicao}: {tipo} inválida.")
    if _bytes_b64(valor) > limite:
        raise ErroPandoo(f"Item {posicao}: {tipo} passa de {rotulo_limite}.")
    categoria = "imagem" if tipo == "imagem" else "audio"
    ok, _ = validar_arquivo_base64(valor, categoria)
    if not ok and not (tipo == "áudio" and _eh_webm(valor)):
        raise ErroPandoo(f"Item {posicao}: o arquivo enviado não é um(a) {tipo} válido(a).")
    return valor


def _lado(bruto, posicao, exigir_imagem, modelo="roleta"):
    bruto = bruto if isinstance(bruto, dict) else {}
    texto = str(bruto.get("texto") or "").strip()[:MAX_TEXTO]
    imagem = _midia(bruto.get("imagem"), "imagem", MAX_IMAGEM, "300 KB", posicao)
    audio = _midia(bruto.get("audio"), "áudio", MAX_AUDIO, "600 KB", posicao)
    if exigir_imagem and not imagem:
        raise ErroPandoo(f"Item {posicao}: {NOME_MODELO.get(modelo, 'o jogo')} precisa de uma imagem em cada figura.")
    return {"texto": texto, "imagem": imagem, "audio": audio}


def _inteiro(valor, minimo, maximo, padrao):
    try:
        return max(minimo, min(maximo, int(valor)))
    except (TypeError, ValueError):
        return padrao


def _regras(modelo, regras):
    padrao = dict(REGRAS_PADRAO[modelo])
    regras = regras if isinstance(regras, dict) else {}
    if modelo == "quiz":
        if regras.get("modo") in ("ouvir", "ver"):
            padrao["modo"] = regras["modo"]
        opcoes = _inteiro(regras.get("opcoes"), 0, 99, None)
        if opcoes in (2, 3, 4):
            padrao["opcoes"] = opcoes
        if regras.get("fim") in ("todas", "perguntas"):
            padrao["fim"] = regras["fim"]
        padrao["perguntas"] = _inteiro(regras.get("perguntas", padrao["perguntas"]), 1, 100, padrao["perguntas"])
        for chave in ("som", "voz"):
            if chave in regras:
                padrao[chave] = bool(regras[chave])
        return padrao
    if regras.get("fim") in ("todas", "giros"):
        padrao["fim"] = regras["fim"]
    try:
        padrao["giros"] = max(1, min(100, int(regras.get("giros", padrao["giros"]))))
    except (TypeError, ValueError):
        pass
    for chave in ("mostrar_palavra", "som", "voz"):
        if chave in regras:
            padrao[chave] = bool(regras[chave])
    return padrao


def _normalizar_palavra(texto):
    """Igual ao normalizarPalavra do front: sem acento, sem caixa, sem espaços nas pontas."""
    nfd = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in nfd if not unicodedata.combining(c)).strip().lower()


def _checar_opcoes_quiz(itens, modo):
    """Revisão final (30/09/2026): toda pergunta precisa de pelo menos uma opção
    errada com palavra diferente da certa (senão ela teria 1 opção só)."""
    for posicao, item in enumerate(itens, start=1):
        propria = _normalizar_palavra(item["pergunta"]["texto"])
        outros = [o for o in itens if o is not item]
        if modo == "ver":
            candidatas = list(item["distratores"]) + [o["pergunta"]["texto"] for o in outros]
            ok = any(_normalizar_palavra(c) and _normalizar_palavra(c) != propria for c in candidatas)
        else:
            ok = any(not propria or not _normalizar_palavra(o["pergunta"]["texto"])
                     or _normalizar_palavra(o["pergunta"]["texto"]) != propria for o in outros)
        if not ok:
            raise ErroPandoo(f"Item {posicao}: o quiz precisa de pelo menos 2 palavras diferentes "
                             "para ter opções erradas.")


def validar_jogo(modelo, conteudo, regras, cenario):
    if modelo not in MODELOS:
        raise ErroPandoo("Esse modelo de jogo ainda não existe.")
    if cenario is not None and cenario not in CENARIOS:
        raise ErroPandoo("Cenário inválido.")
    if not isinstance(conteudo, dict) or conteudo.get("versao") != 1:
        raise ErroPandoo("Conteúdo em versão desconhecida.")
    itens = conteudo.get("itens")
    if not isinstance(itens, list) or not (MIN_ITENS <= len(itens) <= MAX_ITENS):
        raise ErroPandoo(f"O jogo precisa ter de {MIN_ITENS} a {MAX_ITENS} itens.")
    regras_norm = _regras(modelo, regras)
    normalizados, ids = [], set()
    for posicao, bruto in enumerate(itens, start=1):
        bruto = bruto if isinstance(bruto, dict) else {}
        item_id = str(bruto.get("id") or "").strip()[:40]
        if not item_id:
            raise ErroPandoo(f"Item {posicao}: sem identificador.")
        if item_id in ids:
            raise ErroPandoo(f"Item {posicao}: identificador repetido.")
        ids.add(item_id)
        distratores = bruto.get("distratores") if isinstance(bruto.get("distratores"), list) else []
        pergunta = _lado(bruto.get("pergunta"), posicao, exigir_imagem=(modelo in ("roleta", "quiz")), modelo=modelo)
        if modelo == "quiz" and not pergunta["texto"]:
            if regras_norm["modo"] == "ver":
                raise ErroPandoo(f"Item {posicao}: o quiz precisa da palavra de cada figura no modo "
                                 "'Ver a figura e achar a palavra'.")
            if not regras_norm["voz"]:
                raise ErroPandoo(f"Item {posicao}: o quiz precisa da palavra de cada figura quando a leitura "
                                 "em voz alta está desligada.")
            if not pergunta["audio"]:
                raise ErroPandoo(f"Item {posicao}: o quiz precisa da palavra ou a voz de cada figura no modo "
                                 "'Ouvir e achar a figura'.")
        normalizados.append({
            "id": item_id,
            "pergunta": pergunta,
            "resposta": _lado(bruto.get("resposta"), posicao, exigir_imagem=False),
            # Só texto não vazio; o limite vale depois de limpar (01/10/2026).
            # Modelo sem opções erradas próprias (ex.: roleta) não guarda nenhuma.
            "distratores": [d.strip()[:MAX_TEXTO] for d in distratores
                            if isinstance(d, str) and d.strip()][:MAX_DISTRATORES.get(modelo, 0)],
            "grupo": (str(bruto["grupo"]).strip()[:MAX_TEXTO] or None) if bruto.get("grupo") else None,
        })
    if modelo == "quiz":
        _checar_opcoes_quiz(normalizados, regras_norm["modo"])
    resultado = {"versao": 1, "itens": normalizados}
    if len(json.dumps(resultado)) > MAX_CONTEUDO:
        raise ErroPandoo("O jogo ficou pesado demais (limite de 10 MB). Use imagens e áudios menores ou menos itens.")
    return resultado, regras_norm


def calcular_resultado(detalhes):
    if not isinstance(detalhes, list) or len(detalhes) > MAX_RODADAS:
        raise ErroPandoo("Resultado inválido.")
    limpos = []
    for d in detalhes:
        if not isinstance(d, dict) or d.get("resultado") not in ("conseguiu", "treinar"):
            raise ErroPandoo("Resultado inválido.")
        limpos.append({"item_id": str(d.get("item_id") or "")[:40], "texto": str(d.get("texto") or "")[:MAX_TEXTO],
                       "resultado": d["resultado"]})
    acertos = sum(1 for d in limpos if d["resultado"] == "conseguiu")
    return {"total_rodadas": len(limpos), "acertos": acertos, "a_treinar": len(limpos) - acertos, "detalhes": limpos}


def imagem_cenario_valida(b64):
    if not isinstance(b64, str) or not b64 or _bytes_b64(b64) > MAX_IMAGEM_CENARIO:
        return False
    return validar_arquivo_base64(b64, "imagem")[0]
