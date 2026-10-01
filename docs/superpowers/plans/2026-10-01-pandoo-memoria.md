# Pandoo fase 2 — Memória — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Third Pandoo game, the Memória (flip two cards, find pairs; pair type "figura+figura" or "figura+palavra"; ⭐ only when the child remembered where the card was).

**Architecture:** Backend accepts model `memoria` with its rules and validation (`pandoo_service.py`). Pure logic (deck, move, end, table layout) in `pandoo_core.js`, Node-tested. Game file `frontend/js/pandoo/jogos/memoria.js` runs inside the existing stage; the stage gets a legible title and a way to speak after the success sound without cutting it. Editor gets the Memória rules panel.

**Tech Stack:** Flask/pytest; vanilla JS globals, `node --test`; Playwright (Python via `uv`).

**Spec:** `docs/superpowers/specs/2026-10-01-pandoo-memoria-design.md`

## Global Constraints

- CSP: `script-src 'self'`, `img-src 'self' data:`; no `blob:`. User text through `escapeHtml`; images via `_imgItemPandoo`/`base64Seguro`.
- Rules: `{"pares": "figura"|"palavra", "quantidade": 3|4|6|8|10, "som": bool, "voz": bool}`; default `{"pares": "figura", "quantidade": 6, "som": true, "voz": true}`.
- Image required always; `palavra` type: word required and words distinct (normalized without accent/case). Memória stores no distratores.
- Backend messages: `Item N: a memória precisa de uma imagem em cada figura.` / `Item N: a memória precisa da palavra de cada figura no tipo 'Figura + palavra'.` / `Item N: a palavra repete a de outra figura — no tipo 'Figura + palavra' as palavras precisam ser diferentes.`
- Result per pair: "treinar" if, in some move, the FIRST card flipped belonged to that pair, its partner had appeared in an earlier move, and the second card was wrong; else "conseguiu".
- Miss: cards stay visible 1,2 s, table locked meanwhile. Last pair → summary after 1,2 s.
- Texts: "Isso! Achou o par ⭐", "Achou! Vamos treinar mais 💪", "Quase! Lembre onde estavam 💚", "Vire duas cartas e ache o par 💚", placar "🧠 x de N pares", resumo "em N pares", aviso "Você ainda não achou nenhum par. Ache pelo menos um para liberar a missão 🧠".
- Editor: "2. Figuras da memória"; "Como são os pares" (🖼️🖼️ Figura + figura igual / 🖼️🔤 Figura + palavra); "Quantos pares em cada partida" 3/4/6/8/10 + "Se o jogo tiver mais figuras, cada partida sorteia quais entram."; "Som de acerto e comemoração"; "Falar a palavra quando achar o par".
- `.pd-titulo`: solid white pill, dark text, for all games.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. No migration → auto-merge after CI.

## Review Focus

1. Fast taps: third card while two are open, same card twice, a card of an already-found pair → ignored, no double registration.
2. "Finalizar jogo" or closing the stage during the 1,2 s miss timer / before the final summary → no errors, no move after close.
3. Game with fewer figures than `quantidade` (2 figures, quantidade 6) → 2 pairs, game ends normally.
4. Phone 390×844 with 10 pairs (20 cards) and window resize → all cards visible without horizontal scroll, ≥ 56 px.
5. Figure without word and without audio in `figura` type with voz on → no speech, no error.

---

### Task 1: Backend — model `memoria`

**Files:** Modify `backend/pandoo_service.py`; Create `backend/tests/test_pandoo_memoria.py`

- [ ] **Step 1: Failing tests**
```python
"""Pandoo fase 2 (01/10/2026): Memória — regras e validação."""
import base64

import pytest

import pandoo_service as ps

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def _c(itens):
    return {"versao": 1, "itens": itens}


def _it(i, texto=None, imagem=PNG, distratores=None):
    texto = f"Palavra {i}" if texto is None else texto
    return {"id": f"i{i}", "pergunta": {"texto": texto, "imagem": imagem, "audio": None},
            "distratores": distratores or []}


def test_regras_padrao_e_normalizacao():
    _, r = ps.validar_jogo("memoria", _c([_it(1), _it(2)]), {}, None)
    assert r == {"pares": "figura", "quantidade": 6, "som": True, "voz": True}
    _, r = ps.validar_jogo("memoria", _c([_it(1), _it(2)]), {"pares": "xx", "quantidade": 7, "voz": 0, "giros": 3}, None)
    assert r == {"pares": "figura", "quantidade": 6, "som": True, "voz": False}
    _, r = ps.validar_jogo("memoria", _c([_it(1), _it(2)]), {"pares": "palavra", "quantidade": "10"}, None)
    assert (r["pares"], r["quantidade"]) == ("palavra", 10)


def test_imagem_obrigatoria():
    with pytest.raises(ps.ErroPandoo, match="a memória precisa de uma imagem"):
        ps.validar_jogo("memoria", _c([_it(1, imagem=None), _it(2)]), {}, None)


def test_tipo_figura_aceita_sem_palavra_e_repetida():
    ps.validar_jogo("memoria", _c([_it(1, texto=""), _it(2, texto="")]), {"pares": "figura"}, None)
    ps.validar_jogo("memoria", _c([_it(1, "Gato"), _it(2, "gato")]), {"pares": "figura"}, None)


def test_tipo_palavra_exige_palavra_diferente():
    with pytest.raises(ps.ErroPandoo, match="precisa da palavra de cada figura"):
        ps.validar_jogo("memoria", _c([_it(1, texto=""), _it(2)]), {"pares": "palavra"}, None)
    with pytest.raises(ps.ErroPandoo, match="Item 2: a palavra repete"):
        ps.validar_jogo("memoria", _c([_it(1, "Robô"), _it(2, " robo ")]), {"pares": "palavra"}, None)


def test_memoria_nao_guarda_distratores():
    c, _ = ps.validar_jogo("memoria", _c([_it(1, distratores=["Pato"]), _it(2)]), {}, None)
    assert c["itens"][0]["distratores"] == []
```
- [ ] **Step 2: Run** `pytest tests/test_pandoo_memoria.py -q` → FAIL ("Esse modelo de jogo ainda não existe").
- [ ] **Step 3: Implement** — `MODELOS` += `"memoria"`; `REGRAS_PADRAO["memoria"] = {"pares": "figura", "quantidade": 6, "som": True, "voz": True}`; `NOME_MODELO["memoria"] = "a memória"`; `_regras`: branch for memoria (pares ∈ {figura, palavra}; quantidade int ∈ {3,4,6,8,10}; som/voz bool); `exigir_imagem` for memoria; after `_lado`, memoria+palavra without texto → message 2; after the loop, memoria+palavra: a set of `_normalizar_palavra(texto)`; repeated → message 3 with the position of the second.
- [ ] **Step 4: Run** new file + `tests/test_pandoo_*.py` → PASS.
- [ ] **Step 5: Commit** "Pandoo Memória: modelo, regras e validação no backend".

### Task 2: Pure logic in `pandoo_core.js`

**Files:** Modify `frontend/js/pandoo/pandoo_core.js`; Test `frontend/tests/pandoo_core.test.js`

**Produces:**
- `REGRAS_PADRAO_PANDOO.memoria`
- `problemasDoConteudo("memoria", conteudo, regras)` — "Figura N: falta a imagem." / "Figura N: falta a palavra." / "Figura N: a palavra repete a de outra figura."
- `montarCartasMemoria(conteudo, regras, aleatorio = Math.random) -> [{id: "c0".., item_id, face: "figura"|"palavra"}]`
- `estadoInicialMemoria() -> {vistas: [], achados: [], treinar: [], rodadas: 0, detalhes: []}`
- `jogadaMemoria(estado, cartas, primeiraId, segundaId, conteudo) -> {estado, acertou, item_id, resultado}`
- `memoriaTerminou(estado, cartas) -> bool`
- `layoutMesaMemoria(nCartas, largura, altura, gap = 10) -> {colunas, tamanho}` (tamanho = card width; height = width*4/3)

- [ ] **Step 1: Failing tests** (append):
```js
// Pandoo fase 2 (01/10/2026): Memória.
const mi = (id, texto) => ({ id, pergunta: { texto, imagem: "iVBORw0KGgo=", audio: null }, distratores: [] });
const cm = (n) => ({ versao: 1, itens: Array.from({ length: n }, (_, i) => mi(`m${i}`, `Pal${i}`)) });

test("memória: cartas em pares, sorteio e faces", () => {
    const c = cm(10);
    const cartas = p.montarCartasMemoria(c, { pares: "figura", quantidade: 6 }, () => 0.3);
    assert.equal(cartas.length, 12);
    const porItem = {};
    cartas.forEach(k => { porItem[k.item_id] = (porItem[k.item_id] || 0) + 1; });
    assert.equal(Object.keys(porItem).length, 6);
    assert.ok(Object.values(porItem).every(v => v === 2));
    assert.ok(cartas.every(k => k.face === "figura"));
    assert.equal(new Set(cartas.map(k => k.id)).size, 12);
    const pal = p.montarCartasMemoria(c, { pares: "palavra", quantidade: 3 });
    assert.equal(pal.filter(k => k.face === "palavra").length, 3);
    assert.equal(p.montarCartasMemoria(cm(2), { pares: "figura", quantidade: 6 }).length, 4);
});

test("memória: acerto, erro sem ter visto e erro de quem já viu", () => {
    const c = cm(3);
    const cartas = [
        { id: "a1", item_id: "m0", face: "figura" }, { id: "b1", item_id: "m1", face: "figura" },
        { id: "a2", item_id: "m0", face: "figura" }, { id: "b2", item_id: "m1", face: "figura" },
        { id: "c1", item_id: "m2", face: "figura" }, { id: "c2", item_id: "m2", face: "figura" },
    ];
    let e = p.estadoInicialMemoria();
    let r = p.jogadaMemoria(e, cartas, "a1", "b1", c);      // chute: nada era visto
    assert.equal(r.acertou, false);
    r = p.jogadaMemoria(r.estado, cartas, "a2", "c1", c);   // 1ª carta a2, par a1 já visto → m0 treinar
    assert.equal(r.acertou, false);
    r = p.jogadaMemoria(r.estado, cartas, "b2", "b1", c);   // m1: b2 nova, b1 vista → acerta = conseguiu
    assert.deepEqual([r.acertou, r.item_id, r.resultado], [true, "m1", "conseguiu"]);
    r = p.jogadaMemoria(r.estado, cartas, "a1", "a2", c);
    assert.deepEqual([r.acertou, r.resultado], [true, "treinar"]);
    assert.equal(p.memoriaTerminou(r.estado, cartas), false);
    const antes = r.estado;
    const ignorada = p.jogadaMemoria(antes, cartas, "a1", "c1", c); // carta já achada
    assert.equal(ignorada.estado, antes);
    r = p.jogadaMemoria(r.estado, cartas, "c2", "c1", c);
    assert.equal(r.resultado, "conseguiu");
    assert.equal(p.memoriaTerminou(r.estado, cartas), true);
    assert.equal(r.estado.rodadas, 3);
    assert.deepEqual(r.estado.detalhes.map(d => d.resultado), ["conseguiu", "treinar", "conseguiu"]);
    assert.equal(p.jogadaMemoria(r.estado, cartas, "c1", "c1", c).estado, r.estado);
});

test("memória: mesa cabe na tela", () => {
    for (const [n, w, h] of [[12, 390, 600], [20, 390, 600], [20, 1366, 600], [6, 1366, 600]]) {
        const { colunas, tamanho } = p.layoutMesaMemoria(n, w, h);
        const linhas = Math.ceil(n / colunas);
        assert.ok(tamanho >= 56 && tamanho <= 150, `${n} ${w}x${h}: ${tamanho}`);
        assert.ok(colunas * tamanho + (colunas - 1) * 10 <= w, `largura ${n} ${w}`);
        assert.ok(linhas * tamanho * 4 / 3 + (linhas - 1) * 10 <= h, `altura ${n} ${w}x${h}`);
    }
    assert.equal(p.layoutMesaMemoria(20, 200, 200).tamanho, 56);
});

test("memória: problemas por tipo", () => {
    const c = { versao: 1, itens: [mi("a", "Robô"), mi("b", "robo")] };
    assert.equal(p.problemasDoConteudo("memoria", c, { pares: "figura" }).length, 0);
    assert.ok(p.problemasDoConteudo("memoria", c, { pares: "palavra" }).some(t => t.startsWith("Figura 2: a palavra repete")));
    c.itens[1].pergunta.texto = "";
    assert.ok(p.problemasDoConteudo("memoria", c, { pares: "palavra" }).some(t => t === "Figura 2: falta a palavra."));
    c.itens[0].pergunta.imagem = null;
    assert.ok(p.problemasDoConteudo("memoria", c, {}).some(t => t === "Figura 1: falta a imagem."));
});
```
- [ ] **Step 2: Run** `node --test frontend/tests/pandoo_core.test.js` → FAIL.
- [ ] **Step 3: Implement**:
  - `montarCartasMemoria`: `_embaralhar(itens)`, take `min(quantidade, n)`; for each item push `{item_id, face:"figura"}` and `{item_id, face: pares==="palavra" ? "palavra" : "figura"}`; shuffle; assign ids `c0..`.
  - `jogadaMemoria`: ignore (return same estado object, `acertou:false`) when ids equal, either unknown, or either card's item already in `achados`. `primeira`/`segunda` cards; `vistasAntes = estado.vistas`. If same item: `resultado = treinar.includes(item) ? "treinar" : "conseguiu"`; new estado with `achados+item`, `rodadas+1`, `detalhes+{item_id, texto, resultado}` (texto from conteudo item), `vistas` ∪ both. Else: if the partner of `primeira` (other card with same item_id) is in `vistasAntes` → add `primeira.item_id` to `treinar` (no duplicates); `vistas` ∪ both.
  - `memoriaTerminou`: `achados.length === new Set(cartas.map(c => c.item_id)).size`.
  - `layoutMesaMemoria`: for colunas 2..8 compute `tamanho = min((w-(c-1)*gap)/c, ((h-(l-1)*gap)/l)*3/4)` with `l=ceil(n/c)`; pick max; clamp to `[56,150]` (floor).
  - `problemasDoConteudo`: memoria → image check (shared with roleta/quiz) + palavra type: missing word; repeated normalized word → "Figura N: a palavra repete a de outra figura." (second occurrence).
  - Export all.
- [ ] **Step 4: Run** all node tests → PASS.
- [ ] **Step 5: Commit** "Pandoo Memória: regras puras (cartas, jogada, mesa)".

### Task 3: Stage title + speech after success + game + CSS

**Files:** Modify `frontend/js/pandoo/pandoo_som.js`, `frontend/js/pandoo/pandoo_palco.js`, `frontend/css/pandoo.css`, `frontend/index.html`; Create `frontend/js/pandoo/jogos/memoria.js`

- [ ] **Step 1: Som/palco** — `PandooSom.falarItem(item, {atrasoMs = 1000, voz = true, cortarSom = true} = {})`: when `cortarSom` is false, only cancel the pending timer, speech and audio (not `notasAgendadas`). Palco `falarItem(item, opcoes = {})` → `PandooSom.falarItem(item, { voz: true, ...opcoes })` when `regras.voz`.
- [ ] **Step 2: Title CSS** — `.pd-titulo { background: #ffffffdd; color: var(--cor-tinta, #2B2640); text-shadow: none; }` placed after the shared pill rule.
- [ ] **Step 3: `jogos/memoria.js`** — `registrarJogo("memoria", {nome: "Memória", icone: "🧠", rotuloRodada: ["par", "pares"], avisoSemRodada, requisitos, iniciar})`:
  - `cartas = montarCartasMemoria(conteudo, regras)`; renders `.pdm` with `.pdm-mesa` of `<button class="pdm-carta" data-id>` (verso 🐾 / frente `_imgItemPandoo(item, "pdm-img")` or `<span class="pdm-palavra">escapeHtml(texto)</span>`), `.pdq-dica`-style `.pdm-dica`.
  - `ajustar()`: `layoutMesaMemoria(cartas.length, area.clientWidth, window.innerHeight - mesa.getBoundingClientRect().top - 90)` → CSS vars `--pdm-col`, `--pdm-tam`; on `resize` (listener removed when `palco.encerrado`).
  - click: ignore if `travado`, `palco.encerrado`, card `.virada`/`.par`; flip; first stored; second → `r = jogadaMemoria(...)`; hit → `.par` both, `palco.registrar(item, r.resultado, {comemorar: true})`, `palco.falarItem(item, {atrasoMs: 800, cortarSom: false})`, dica, placar, if `memoriaTerminou` → `setTimeout(finalizar, 1200)` guarded by `palco.encerrado`; miss → `.erro`, `palco.efeito("treinar")`, dica, `travado = true`, after 1200 ms (guarded) remove `.virada .erro`, `travado=false`.
  - placar `🧠 ${achados} de ${pares} pares`, ⭐ = detalhes conseguiu.
- [ ] **Step 4: CSS** `.pdm-*`: mesa grid `repeat(var(--pdm-col), var(--pdm-tam))`, card aspect 3/4, 3D flip `.virada/.par` rotateY(180deg), verso striped purple + white 🐾 circle, frente white, `.par` green border/bg + pop, `.erro` shake, palavra Fredoka/`--fonte-crianca` font-size `calc(var(--pdm-tam) * .2)`; reduced-motion: no transition/animation.
- [ ] **Step 5:** `index.html` script after `quiz.js`; `node --check`; node tests; commit "Pandoo Memória: jogo no palco e título legível".

### Task 4: Editor

**Files:** Modify `frontend/js/views/pandoo.js`

- [ ] **Step 1:** `MODELOS_PANDOO_EDITOR` memoria `pronto: true`.
- [ ] **Step 2:** `renderRegras` memoria branch (radios `pd-pares` figura/palavra as `.pd-modo` cards, chips `pd-quantidade` 3/4/6/8/10 as `.pd-chip`, note, `#pd-som-regra`, `#pd-voz-regra` "Falar a palavra quando achar o par"); titles/dica for memoria; `lerRegras` memoria branch; change handler re-renders also for `pd-pares`/`pd-quantidade`.
- [ ] **Step 3:** `node --check`, node tests; commit "Pandoo Memória: editor".

### Task 5: Browser check, docs

- [ ] **Step 1:** Fresh seed, Playwright `memoria_e2e.py`: editor switch to Memória (title, panel), "palavra" type with repeated word shows toast; save figura type with 4 figures, quantidade 3; preview: force a miss (two cards of different items via DOM data) → cards flip back after 1,2 s; find all pairs → summary "em 3 pares"; title pill computed background white; mission for child on 390×844: finalizar sem par → aviso; one pair → libera; ficha shows game; 10 pairs on phone: no horizontal scroll, cards ≥ 56 px; no JS errors.
- [ ] **Step 2:** Full backend + node suites.
- [ ] **Step 3:** CLAUDE.md item 5v + pending (next: Associação).
- [ ] **Step 4:** Final review (opus), fixes with tests, PR, CI, merge.
