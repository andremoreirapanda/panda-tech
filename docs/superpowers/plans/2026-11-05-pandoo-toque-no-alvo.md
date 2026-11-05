# Pandoo "Toque só no alvo" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Novo modelo de jogo do Pandoo, `alvo` ("Toque só no alvo" 🎯): figuras aparecem em 3 fases e a criança toca só na figura-alvo; a ficha mostra alvos tocados/perdidos, toques errados, tempo de reação e fase alcançada.

**Architecture:** Igual aos modelos anteriores (Quiz, Memória, Cruzadinha): validação e regras em `pandoo_service.py`; regras puras num arquivo próprio (`alvo_core.js`) testado em Node; o jogo em `frontend/js/pandoo/jogos/alvo.js` usando o palco comum; sem migração (medidas vão em `detalhes_json`). O palco ganha três ganchos opcionais (campos extras no detalhe, registro silencioso, resumo/“houve jogada” do jogo) e o `PandooSom` ganha a fala de comando.

**Tech Stack:** Flask/Python 3.11 (pytest), JS puro no navegador, `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-05-pandoo-toque-no-alvo-design.md`

## Global Constraints

- Código do modelo `alvo`; nome na tela "Toque só no alvo"; ícone 🎯.
- `REGRAS_PADRAO["alvo"] = {"alvo_item_id": None, "frase_inicio": "Toque só no", "fase_inicio": 1, "fase_fim": 3, "subir_sozinho": True, "figuras_por_fase": 20, "velocidade": "media", "som": True}` — **sem** chave `voz`.
- `frase_inicio` até 40 caracteres (vazia → padrão); fases ∈ {1,2,3}, `fase_fim ≥ fase_inicio` (senão = `fase_inicio`); `figuras_por_fase` 10–60; `velocidade` ∈ {`lenta`,`media`,`rapida`}.
- 2 a 24 figuras, imagem obrigatória em todas; o alvo precisa de palavra ou voz gravada.
- Detalhe: `{item_id, texto, resultado, alvo, tocou, fase, tempo_ms}`; mapeamento alvo+tocou=conseguiu, alvo+não=treinar, pegadinha+tocou=treinar, pegadinha+não=conseguiu.
- Para `alvo`, `total_rodadas` = figuras **tocadas**; partida sem toque não libera missão nem trava o dia.
- Subida: passou a fase se tocou ≥ 80% dos alvos e ≤ 1 toque errado; com `subir_sozinho`, não passou → partida termina.
- Sorteio: ~1 alvo a cada 3 (`Math.round(n/3)`, mínimo 1), não começa por alvo, nunca 3 alvos seguidos.
- Tempos (ms) por velocidade lenta/media/rapida: fase 1 na tela 2000/1500/1000 + intervalo 600; fase 2 fora da toca 2200/1700/1200; fase 3 travessia 4500/3500/2500.
- Textos da tela em português e com o nome PandaUp onde houver marca (teste `nome_pandaup` varre o front). Nenhum texto promete melhora de sintoma.
- Testes: `cd backend && PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q` e `node --test frontend/tests/*.test.js`.
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Detalhe forjado pelo navegador** (ex.: pegadinha com `alvo: true`, ou `resultado` incoerente com `tocou`) — o servidor recalcula `alvo` pelo `alvo_item_id` e rejeita incoerência com 400. Teste na Task 2.
2. **Partida só com figuras passando** (criança não toca) — não libera missão, não trava o dia, e "Finalizar" fecha sem resumo. Testes nas Tasks 2 e 4.
3. **Jogo editado depois de partidas** (alvo trocado, figura apagada) — `GET /pandoo/resultados` calcula medidas só dos campos guardados no detalhe (`alvo` gravado na hora), sem reler o jogo. Teste na Task 2.
4. **Jogo com 2 figuras** (1 alvo + 1 pegadinha) e `figuras_por_fase` 10 — o sorteio ainda respeita "não 3 alvos seguidos" e "não começa por alvo". Teste na Task 3.
5. **Trocar de modelo no editor para `alvo` e voltar** — `lerRegras` não pode quebrar por falta do checkbox de voz; o alvo escolhido some se a figura for apagada. Verificação na Task 6.

---

### Task 1: Backend — modelo `alvo` (regras e validação)

**Files:**
- Modify: `backend/pandoo_service.py` (`MODELOS`, `REGRAS_PADRAO`, `NOME_MODELO`, `_regras`, `validar_jogo`)
- Test: `backend/tests/test_pandoo_alvo.py` (novo; helpers `_c`/`_it` como em `test_pandoo_memoria.py`)

**Interfaces:**
- Produces: `validar_jogo("alvo", conteudo, regras, cenario) -> (conteudo_norm, regras_norm)`; `NOME_MODELO["alvo"] = "o jogo do alvo"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_regras_padrao_e_normalizacao():
    _, r = ps.validar_jogo("alvo", _c([_it(1), _it(2)]), {"alvo_item_id": "i1"}, None)
    assert r == {"alvo_item_id": "i1", "frase_inicio": "Toque só no", "fase_inicio": 1, "fase_fim": 3,
                 "subir_sozinho": True, "figuras_por_fase": 20, "velocidade": "media", "som": True}
    _, r = ps.validar_jogo("alvo", _c([_it(1), _it(2)]),
        {"alvo_item_id": "i2", "frase_inicio": "  ", "fase_inicio": 3, "fase_fim": 1, "figuras_por_fase": 999,
         "velocidade": "turbo", "som": 0, "voz": True, "subir_sozinho": 0}, None)
    assert r["frase_inicio"] == "Toque só no" and (r["fase_inicio"], r["fase_fim"]) == (3, 3)
    assert r["figuras_por_fase"] == 60 and r["velocidade"] == "media"
    assert r["som"] is False and r["subir_sozinho"] is False and "voz" not in r
    _, r = ps.validar_jogo("alvo", _c([_it(1), _it(2)]), {"alvo_item_id": "i1", "frase_inicio": "Toque só na " + "x" * 60}, None)
    assert len(r["frase_inicio"]) == 40

def test_alvo_obrigatorio_e_existente():
    for regras in ({}, {"alvo_item_id": "nao-existe"}):
        with pytest.raises(ps.ErroPandoo, match="Escolha qual figura é o alvo"):
            ps.validar_jogo("alvo", _c([_it(1), _it(2)]), regras, None)

def test_imagem_obrigatoria():
    with pytest.raises(ps.ErroPandoo, match="precisa de uma imagem"):
        ps.validar_jogo("alvo", _c([_it(1), _it(2, imagem=None)]), {"alvo_item_id": "i1"}, None)

def test_alvo_precisa_palavra_ou_voz_pegadinha_nao():
    with pytest.raises(ps.ErroPandoo, match="palavra ou a voz"):
        ps.validar_jogo("alvo", _c([_it(1, texto=""), _it(2)]), {"alvo_item_id": "i1"}, None)
    ps.validar_jogo("alvo", _c([_it(1), _it(2, texto="")]), {"alvo_item_id": "i1"}, None)
```

- [ ] **Step 2: Run** `venv/Scripts/python.exe -m pytest tests/test_pandoo_alvo.py -q` — Expected: FAIL ("Esse modelo de jogo ainda não existe").

- [ ] **Step 3: Implement** — `"alvo"` em `MODELOS`, `REGRAS_PADRAO`, `NOME_MODELO`; ramo `alvo` em `_regras` (usar `_inteiro`; `alvo_item_id` só guarda `str(...)[:40]` aqui); em `validar_jogo`: `exigir_imagem` inclui `alvo`; depois do laço, se `modelo == "alvo"`, achar o item de `regras_norm["alvo_item_id"]` (senão `ErroPandoo("Escolha qual figura é o alvo.")`) e exigir `texto or audio` (`ErroPandoo(f"Item {pos}: o alvo precisa da palavra ou a voz, porque ela é dita no começo do jogo.")`).

- [ ] **Step 4: Run** the same command — Expected: PASS.

- [ ] **Step 5: Commit** `git commit -m "Pandoo alvo: regras e validação no servidor"`

### Task 2: Backend — resultado da partida e medidas

**Files:**
- Modify: `backend/pandoo_service.py` (`calcular_resultado`, nova `medidas_alvo`)
- Modify: `backend/blueprints/pandoo_bp.py` (`salvar_resultado`, `listar_resultados`)
- Test: `backend/tests/test_pandoo_alvo.py` (helpers `_jogo`/`_missao` como em `test_pandoo_resultados.py`, criando o jogo com `modelo: "alvo"` e `regras: {"alvo_item_id": "i0"}`)

**Interfaces:**
- Consumes: Task 1.
- Produces: `calcular_resultado(detalhes, modelo="roleta", regras=None) -> dict` (mesmas chaves de hoje); `medidas_alvo(detalhes) -> {"alvos_tocados", "alvos_total", "alvos_perdidos", "toques_errados", "tempo_medio_ms", "fase_alcancada"}`; partidas `alvo` no `GET /pandoo/resultados` ganham `medidas` e ficam **fora** de `por_jogo`.

- [ ] **Step 1: Write the failing tests**

```python
D = lambda item, alvo, tocou, fase=1, tempo=None: {"item_id": item, "texto": "", "alvo": alvo, "tocou": tocou, "fase": fase,
    "resultado": "conseguiu" if alvo == tocou else "treinar", **({"tempo_ms": tempo} if tempo is not None else {})}

def test_calcular_resultado_alvo_conta_so_toques():
    det = [D("i0", True, True, 1, 500), D("i1", False, False), D("i0", True, False), D("i1", False, True, 2)]
    r = ps.calcular_resultado(det, "alvo", {"alvo_item_id": "i0"})
    assert (r["total_rodadas"], r["acertos"], r["a_treinar"]) == (2, 2, 2)
    assert r["detalhes"][0] == {"item_id": "i0", "texto": "", "resultado": "conseguiu", "alvo": True, "tocou": True, "fase": 1, "tempo_ms": 500}
    assert "tempo_ms" not in r["detalhes"][1]

def test_calcular_resultado_alvo_sem_toque_zero_rodadas():
    assert ps.calcular_resultado([D("i0", True, False), D("i1", False, False)], "alvo", {"alvo_item_id": "i0"})["total_rodadas"] == 0

def test_servidor_confere_alvo_e_resultado():
    with pytest.raises(ps.ErroPandoo):  # pegadinha dizendo ser alvo
        ps.calcular_resultado([D("i1", True, True)], "alvo", {"alvo_item_id": "i0"})
    with pytest.raises(ps.ErroPandoo):  # resultado incoerente
        ps.calcular_resultado([{**D("i0", True, True), "resultado": "treinar"}], "alvo", {"alvo_item_id": "i0"})
    with pytest.raises(ps.ErroPandoo):  # fase fora de 1..3
        ps.calcular_resultado([D("i0", True, True, 4)], "alvo", {"alvo_item_id": "i0"})

def test_medidas_alvo():
    det = [D("i0", True, True, 1, 400), D("i0", True, True, 2, 800), D("i0", True, False, 2), D("i1", False, True, 2), D("i1", False, False)]
    assert ps.medidas_alvo(det) == {"alvos_tocados": 2, "alvos_total": 3, "alvos_perdidos": 1,
                                    "toques_errados": 1, "tempo_medio_ms": 600, "fase_alcancada": 2}
    assert ps.medidas_alvo([D("i1", False, False)])["tempo_medio_ms"] is None

def test_partida_sem_toque_nao_libera_missao_nem_trava_dia(client, db_ctx):
    # responsável salva partida só com figuras passando → 201, total_rodadas 0;
    # GET da missão: jogo_jogado False e jogou_hoje False; uma segunda partida com toque → 201 (não 409).

def test_listagem_traz_medidas_e_ignora_jogo_editado(client, db_ctx):
    # salva partida alvo; troca o alvo do jogo (PUT) para "i1"; GET /pandoo/resultados?paciente_id=...
    # → partida com "medidas" iguais às de antes e o jogo alvo não aparece em "por_jogo".
```

(As duas últimas: escreva os corpos com os helpers do arquivo de resultados; as asserções estão nos comentários.)

- [ ] **Step 2: Run** `venv/Scripts/python.exe -m pytest tests/test_pandoo_alvo.py -q` — Expected: FAIL.

- [ ] **Step 3: Implement**
  - `calcular_resultado`: para `modelo == "alvo"`, cada detalhe precisa `tocou` bool e `fase` int 1–3; `alvo = item_id == regras["alvo_item_id"]` (ignora o `alvo` enviado se bater; se vier diferente → `ErroPandoo("Resultado inválido.")`); `resultado` tem de bater com a tabela; `tempo_ms` só quando alvo tocado, `_inteiro(…, 0, 10000, None)`; `total_rodadas = sum(tocou)`; `acertos`/`a_treinar` contam todos os detalhes. Outros modelos: igual a hoje.
  - `salvar_resultado`: `calcular_resultado(body.get("detalhes"), jogo["modelo"], json.loads(jogo["regras_json"] or "{}"))`.
  - `listar_resultados`: para `p["modelo"] == "alvo"`, `p["medidas"] = medidas_alvo(p["detalhes"])` e `continue` antes de somar em `por_jogo`.

- [ ] **Step 4: Run** `pytest tests/test_pandoo_alvo.py tests/test_pandoo_resultados.py tests/test_pandoo_missao.py -q` — Expected: PASS.

- [ ] **Step 5: Commit** `git commit -m "Pandoo alvo: resultado conferido no servidor e medidas na listagem"`

### Task 3: Regras puras no front (`alvo_core.js`)

**Files:**
- Create: `frontend/js/pandoo/alvo_core.js` (cabeçalho e `module.exports` no estilo de `cruzadinha_core.js`)
- Modify: `frontend/js/pandoo/pandoo_core.js` (`REGRAS_PADRAO_PANDOO.alvo`; `problemasDoConteudo` ramo `alvo`; `alvo` na lista de imagem obrigatória)
- Modify: `frontend/index.html` (script `alvo_core.js` logo após `cruzadinha_core.js`)
- Test: `frontend/tests/pandoo_alvo.test.js`

**Interfaces:**
- Produces (globais no navegador, exportadas no Node):
  - `TEMPOS_ALVO = {1: {lenta: 2000, media: 1500, rapida: 1000}, 2: {lenta: 2200, media: 1700, rapida: 1200}, 3: {lenta: 4500, media: 3500, rapida: 2500}}`, `INTERVALO_FASE1_MS = 600`.
  - `sortearFigurasAlvo(itens, alvoId, quantidade, aleatorio = Math.random) -> item[]`
  - `detalheAlvo(item, alvoId, tocou, fase, tempoMs) -> detalhe` (aplica o mapeamento; `tempo_ms` só em alvo tocado)
  - `avaliarFaseAlvo(detalhesDaFase) -> boolean`
  - `proximaFaseAlvo(regras, faseAtual, detalhesDaFase) -> number | null` (null = acabou)
  - `medidasAlvo(detalhes) -> mesmo formato de `medidas_alvo` do backend`
  - `houveToqueAlvo(detalhes) -> boolean`
  - `fraseComandoAlvo(regras, item) -> string` (`"Toque só no cachorro!"`; sem palavra → só `frase_inicio`)

- [ ] **Step 1: Write the failing tests** (gerador reproduzível igual ao de `pandoo_cruzadinha.test.js`)

```js
test("sorteio: proporção, não começa por alvo, nunca 3 alvos seguidos", () => {
  for (let s = 1; s <= 50; s++) for (const n of [10, 20, 60]) {
    const lista = a.sortearFigurasAlvo(ITENS, "i0", n, semente(s));
    assert.equal(lista.length, n);
    assert.equal(lista.filter(i => i.id === "i0").length, Math.max(1, Math.round(n / 3)));
    assert.notEqual(lista[0].id, "i0");
    assert.ok(!lista.some((it, k) => k >= 2 && [0, 1, 2].every(d => lista[k - d].id === "i0")));
  }
});
test("sorteio com só 2 figuras ainda respeita as regras", () => { /* ITENS2 = [i0, i1], n = 10, mesmas asserções */ });
test("detalheAlvo aplica o mapeamento", () => {
  assert.equal(a.detalheAlvo(ALVO, "i0", true, 1, 500).resultado, "conseguiu");
  assert.equal(a.detalheAlvo(ALVO, "i0", false, 1).resultado, "treinar");
  assert.equal(a.detalheAlvo(PEG, "i0", true, 1, 300).resultado, "treinar");
  assert.equal(a.detalheAlvo(PEG, "i0", true, 1, 300).tempo_ms, undefined);
  assert.equal(a.detalheAlvo(PEG, "i0", false, 1).resultado, "conseguiu");
});
test("avaliarFaseAlvo: ≥80% dos alvos e ≤1 toque errado", () => { /* 4/5 alvos + 1 erro → true; 3/5 → false; 5/5 + 2 erros → false */ });
test("proximaFaseAlvo", () => {
  const r = { fase_inicio: 1, fase_fim: 3, subir_sozinho: true };
  assert.equal(a.proximaFaseAlvo(r, 1, BOA), 2);
  assert.equal(a.proximaFaseAlvo(r, 1, RUIM), null);
  assert.equal(a.proximaFaseAlvo({ ...r, subir_sozinho: false }, 1, RUIM), 2);
  assert.equal(a.proximaFaseAlvo(r, 3, BOA), null);
});
test("medidasAlvo igual ao backend", () => { /* mesmo caso de test_medidas_alvo */ });
test("houveToqueAlvo e fraseComandoAlvo", () => {
  assert.equal(a.houveToqueAlvo([a.detalheAlvo(ALVO, "i0", false, 1)]), false);
  assert.equal(a.fraseComandoAlvo({ frase_inicio: "Toque só na" }, { pergunta: { texto: "bola" } }), "Toque só na bola!");
});
test("problemasDoConteudo do alvo", () => {
  assert.match(p.problemasDoConteudo("alvo", CONTEUDO, {})[0], /Escolha qual figura é o alvo/);
  // alvo sem palavra nem voz → "Figura 1: o alvo precisa da palavra ou da voz."
});
```

- [ ] **Step 2: Run** `node --test frontend/tests/pandoo_alvo.test.js` — Expected: FAIL (módulo não existe).

- [ ] **Step 3: Implement** as funções acima. Sorteio: monte a lista de pegadinhas (sorteadas com reposição das outras figuras) e insira os alvos em posições sorteadas que respeitem as duas regras (tente de novo até 50 vezes; na falha, distribua os alvos espaçados por igual a partir da posição 1).

- [ ] **Step 4: Run** `node --test frontend/tests/*.test.js` — Expected: PASS (todos).

- [ ] **Step 5: Commit** `git commit -m "Pandoo alvo: regras puras (sorteio, fases, medidas)"`

### Task 4: Palco e som — ganchos para o jogo

**Files:**
- Modify: `frontend/js/pandoo/pandoo_palco.js`
- Modify: `frontend/js/pandoo/pandoo_som.js`

**Interfaces:**
- Produces:
  - `palco.registrar(item, resultado, { comemorar, silencioso = false, extra = {} })` — `extra` é mesclado no detalhe (`{...base, ...extra}`); `silencioso: true` não chama `PandooSom.parar()`, nem som, nem confete.
  - `def.houveJogada(detalhes) -> boolean` (opcional; padrão `detalhes.length > 0`) — usado no `finalizar` da missão **e da prévia** para fechar sem resumo.
  - `def.resumo(detalhes, conteudo, regras) -> string HTML` (opcional) — substitui o parágrafo "Você ganhou…" e as miniaturas no resumo.
  - `PandooSom.falarComando(frase, item, { atrasoMs = 0 } = {})` — fala `frase` pela voz do navegador e, ao terminar, a palavra do item (gravação se houver, senão texto); respeita `som.ligado`; `pararVoz()` cancela tudo.

- [ ] **Step 1: Implement** os quatro ganchos sem mudar o comportamento dos jogos atuais (todos os parâmetros novos são opcionais).
- [ ] **Step 2: Run** `node --test frontend/tests/*.test.js` e `node --check frontend/js/pandoo/pandoo_palco.js frontend/js/pandoo/pandoo_som.js` — Expected: PASS, sem erro.
- [ ] **Step 3: Verify** (Playwright, servidor local com `seed.py`): prévia da Roleta e do Quiz continuam com resumo e sons iguais.
- [ ] **Step 4: Commit** `git commit -m "Pandoo: palco com detalhe extra, registro silencioso e resumo próprio do jogo"`

### Task 5: O jogo (`jogos/alvo.js`) e o CSS

**Files:**
- Create: `frontend/js/pandoo/jogos/alvo.js`
- Modify: `frontend/css/pandoo.css` (classes `.pda-*`)
- Modify: `frontend/index.html` (script após `jogos/cruzadinha.js`)

**Interfaces:**
- Consumes: Task 3 (todas) e Task 4 (ganchos).
- Produces: `registrarJogo("alvo", {nome: "Toque só no alvo", icone: "🎯", rotuloRodada: ["figura", "figuras"], avisoSemRodada: "Você ainda não tocou em nenhuma figura. Toque no alvo pelo menos uma vez para liberar a missão 🎯", requisitos, houveJogada: houveToqueAlvo, resumo, iniciar})`.

- [ ] **Step 1: Implement** conforme a spec, seção 3:
  - Abertura: alvo grande + `fraseComandoAlvo` escrita + botão "Começar"; `PandooSom.falarComando` ao abrir; tocar no modelo do topo repete.
  - Fase 1: uma figura por vez no centro (`TEMPOS_ALVO[1]` + `INTERVALO_FASE1_MS`). Fase 2: grade 3×2 de tocas, até 2 figuras visíveis. Fase 3: figuras atravessam a área (CSS transform), até 3 ao mesmo tempo; com `prefers-reduced-motion`, usar a velocidade `lenta`.
  - Cada figura: primeiro toque conta; ao sair da tela sem toque → `registrar(item, res, {silencioso: true, extra})`; toque no alvo → `registrar(..., {extra})` (comemora); toque na pegadinha → balanço `.pda-balanca` + `registrar(..., {comemorar: false, extra})`. `extra` vem de `detalheAlvo` (tempo medido com `performance.now()` desde a figura ficar visível).
  - Pegadinha não tocada também é registrada silenciosa (`conseguiu`).
  - Troca de fase: aviso "Fase N!" + fala do comando. Fim: `proximaFaseAlvo` devolve `null` → `palco.finalizar()`.
  - `resumo`: "Você pegou X de Y <img do alvo>!" + "Chegou até a fase N".
  - Placar: ⭐ = alvos tocados; progresso "Fase N · k/total".
  - Limpar timers em `palco.aoEncerrar`; nada roda depois de `palco.encerrado`.
- [ ] **Step 2: Run** `node --check frontend/js/pandoo/jogos/alvo.js` e `node --test frontend/tests/*.test.js` — Expected: sem erro, PASS.
- [ ] **Step 3: Commit** `git commit -m "Pandoo alvo: jogo com as três fases"`

### Task 6: Editor e ficha do paciente

**Files:**
- Modify: `frontend/js/views/pandoo.js` (`MODELOS_PANDOO_EDITOR`, `renderRegras`, `lerRegras`, textos de itens)
- Modify: `frontend/js/views/jornada.js` (`carregarPandooFicha`)

**Interfaces:**
- Consumes: Tasks 2, 3 e 5.

- [ ] **Step 1: Implement**
  - `MODELOS_PANDOO_EDITOR`: `{ codigo: "alvo", nome: "Toque só no alvo", icone: "🎯", pronto: true }` depois da Cruzadinha.
  - Painel `alvo`: escolher o alvo entre as figuras (miniaturas como rádio `pd-alvo`; figura sem imagem mostra o número), "Frase do comando" (input, máx. 40, placeholder "Toque só no"), "Começar na fase"/"Ir até a fase" (chips 1–3, com o nome de cada fase), "Subir de fase sozinho" (checkbox), "Figuras por fase" (number 10–60), velocidade (chips Lenta/Média/Rápida), som. Texto de ajuda sem promessa clínica.
  - `lerRegras`: ler `pd-voz-regra` só se existir (o `alvo` não tem); ramo `alvo`. Se a figura escolhida for apagada, `alvo_item_id` volta a `null` (o salvar avisa via `problemasDoConteudo`).
  - Textos dos itens: `alvo: ["2. Figuras do jogo", "De 2 a 24 figuras, todas com imagem. Escolha abaixo qual é o alvo; as outras viram as pegadinhas. O alvo precisa da palavra ou da sua voz."]`.
  - Ficha: partidas com `p.medidas` mostram "🎯 Fase N · alvos X/Y · perdidos P · toques errados E · reação T s" (T = `tempo_medio_ms/1000` com 1 casa, "—" se nulo) no lugar de "⭐ · 💪".
- [ ] **Step 2: Verify** com Playwright (servidor local, gestor do seed, módulo Pandoo liberado): criar jogo `alvo` com 4 figuras, trocar para Quiz e voltar sem erro no console, salvar, abrir prévia, jogar as 3 fases (tocar alvos e uma pegadinha), conferir resumo; colocar numa missão, jogar como responsável no Mundo da Criança, conferir a ficha.
- [ ] **Step 3: Run** suíte completa (backend + Node) — Expected: PASS.
- [ ] **Step 4: Commit** `git commit -m "Pandoo alvo: editor e medidas na ficha"`

### Task 7: Documentação e fechamento

**Files:**
- Modify: `CLAUDE.md` (item novo na seção 5 depois de "as"; seção 7: fila do Pandoo agora "Sequência de memória → Caça-figura → Separar por grupo/Associação → Quebra-cabeça → Flashcards"; tabela da seção 8 com `alvo_core.js`)

- [ ] **Step 1:** Atualizar o `CLAUDE.md` com o resumo (modelo, ganchos novos do palco, sem migração, números finais de testes).
- [ ] **Step 2: Run** suíte completa e anotar os números.
- [ ] **Step 3: Commit** `git commit -m "CLAUDE.md: Pandoo Toque só no alvo"`
