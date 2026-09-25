"""
Pandoo (25/09/2026) — regras puras dos jogos: valida e normaliza o conteúdo
no formato único (v1), as regras de cada modelo e o resultado de uma partida.
Sem acesso a banco — as rotas ficam em blueprints/pandoo_bp.py.
"""
import json

from validacao_arquivo import validar_arquivo_base64, _decodificar_binario

MODELOS = {"roleta"}
CENARIOS = {"bambu", "mar", "espaco", "clinica"}
TONS = {"claro", "escuro"}

MIN_ITENS, MAX_ITENS = 2, 24
MAX_TEXTO = 80
MAX_IMAGEM = 300 * 1024
MAX_AUDIO = 600 * 1024
MAX_CONTEUDO = 10 * 1024 * 1024
MAX_IMAGEM_CENARIO = 800 * 1024
MAX_RODADAS = 500

REGRAS_PADRAO = {"roleta": {"fim": "todas", "giros": 10, "mostrar_palavra": True, "som": True, "voz": True}}
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


def _lado(bruto, posicao, exigir_imagem):
    bruto = bruto if isinstance(bruto, dict) else {}
    texto = str(bruto.get("texto") or "").strip()[:MAX_TEXTO]
    imagem = _midia(bruto.get("imagem"), "imagem", MAX_IMAGEM, "300 KB", posicao)
    audio = _midia(bruto.get("audio"), "áudio", MAX_AUDIO, "600 KB", posicao)
    if exigir_imagem and not imagem:
        raise ErroPandoo(f"Item {posicao}: a roleta precisa de uma imagem em cada figura.")
    return {"texto": texto, "imagem": imagem, "audio": audio}


def _regras(modelo, regras):
    padrao = dict(REGRAS_PADRAO[modelo])
    regras = regras if isinstance(regras, dict) else {}
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
        normalizados.append({
            "id": item_id,
            "pergunta": _lado(bruto.get("pergunta"), posicao, exigir_imagem=(modelo == "roleta")),
            "resposta": _lado(bruto.get("resposta"), posicao, exigir_imagem=False),
            "distratores": [str(d).strip()[:MAX_TEXTO] for d in distratores[:10]],
            "grupo": (str(bruto["grupo"]).strip()[:MAX_TEXTO] or None) if bruto.get("grupo") else None,
        })
    resultado = {"versao": 1, "itens": normalizados}
    if len(json.dumps(resultado)) > MAX_CONTEUDO:
        raise ErroPandoo("O jogo ficou pesado demais (limite de 10 MB). Use imagens e áudios menores ou menos itens.")
    return resultado, _regras(modelo, regras)


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
