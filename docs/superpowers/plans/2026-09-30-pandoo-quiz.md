# Pandoo fase 2 — Quiz — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Second Pandoo game, the Quiz (hear the word → tap the figure, or see the figure → tap the word; wrong answer shakes and the child tries again; "conseguiu" only on first try).

**Architecture:** Backend accepts model `quiz` with its own rules and per-model item validation (`pandoo_service.py`). Front-end adds pure quiz logic to `pandoo_core.js` (Node-tested), a new game file `frontend/js/pandoo/jogos/quiz.js` registered in the existing catalog and run by the existing stage (`pandoo_palco.js`, which gains a per-game round label), and editor support in `views/pandoo.js` (model switch, quiz rules panel, optional wrong options per figure in "ver" mode).

**Tech Stack:** Flask/pytest; vanilla JS globals, `node --test`; Playwright (Python via `uv`).

**Spec:** `docs/superpowers/specs/2026-09-30-pandoo-quiz-design.md`

## Global Constraints

- CSP: `script-src 'self'`, `img-src 'self' data:`, `media-src 'self' data:`; no `blob:`. All user text through `escapeHtml`; images as `data:` with `base64Seguro`.
- Quiz rules: `{"modo": "ouvir"|"ver", "opcoes": 2|3|4, "fim": "todas"|"perguntas", "perguntas": 1..100, "som": bool, "voz": bool}`; default `{"modo": "ouvir", "opcoes": 3, "fim": "todas", "perguntas": 10, "som": true, "voz": true}`.
- Item requirements (quiz): `pergunta.imagem` always; `ver` → `pergunta.texto`; `ouvir` → `pergunta.texto` or `pergunta.audio`. `distratores` ≤ 3 (quiz), used only in `ver`.
- Result per question: `conseguiu` if right on the first try, else `treinar`. Mission rule unchanged (needs ≥ 1 round).
- Texts (pt-BR): "Onde está…", "Qual é o nome?", "🔊 Ouvir de novo", "Quase! Tente outra 💚", "Acertou de primeira! ⭐", "Isso! Conseguiu 💪", "Toque na resposta certa 💚"; editor: "2. Perguntas do quiz", "Como a criança responde", "👂 Ouvir e achar a figura", "👀 Ver a figura e achar a palavra", "Quantas opções em cada pergunta", "+ opções erradas próprias (opcional)".
- Voice 1 s after the question appears (existing `PandooSom`).
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. No migration → auto-merge after CI green.

## Review Focus

1. Game with fewer figures than options (2 figures, 4 options) → shows 2 options, never crashes or loops.
2. "ver" mode with repeated/accented words (e.g., "Rosa" and "rosa", "Robô"/"robo") → no duplicate option buttons; the right answer always present exactly once.
3. Switching the model in the editor (roleta ↔ quiz) keeps the figures and does not send roleta-only rules to the quiz (and vice versa).
4. Tapping several wrong options quickly / tapping during the 1.5 s transition → no double registration, no skipped question.
5. "perguntas" mode with N > number of items → repeats only after all were asked; placar counts answered questions.

---

### Task 1: Backend — model `quiz`, rules and validation

**Files:** Modify `backend/pandoo_service.py`; Test `backend/tests/test_pandoo_quiz.py`

- [ ] **Step 1: Failing tests** (`test_pandoo_quiz.py`):
```python
"""Pandoo fase 2 (30/09/2026): Quiz — regras e validação."""
import base64
import pytest
import pandoo_service as ps

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
MP3 = base64.b64encode(b"ID3\x03\x00" + b"\x00" * 64).decode()


def _c(itens):
    return {"versao": 1, "itens": itens}


def _it(i, texto="Rato", imagem=PNG, audio=None, distratores=None):
    return {"id": f"i{i}", "pergunta": {"texto": texto, "imagem": imagem, "audio": audio}, "distratores": distratores or []}


def test_quiz_ouvir_valido_e_regras_padrao():
    c, r = ps.validar_jogo("quiz", _c([_it(1), _it(2, "Rosa")]), {}, None)
    assert r == {"modo": "ouvir", "opcoes": 3, "fim": "todas", "perguntas": 10, "som": True, "voz": True}
    assert len(c["itens"]) == 2


def test_quiz_ouvir_aceita_audio_sem_texto():
    ps.validar_jogo("quiz", _c([_it(1, texto="", audio=MP3), _it(2)]), {"modo": "ouvir"}, None)


def test_quiz_recusas():
    with pytest.raises(ps.ErroPandoo, match="imagem"):
        ps.validar_jogo("quiz", _c([_it(1, imagem=None), _it(2)]), {}, None)
    with pytest.raises(ps.ErroPandoo, match="palavra"):
        ps.validar_jogo("quiz", _c([_it(1, texto=""), _it(2)]), {"modo": "ver"}, None)
    with pytest.raises(ps.ErroPandoo, match="palavra ou a voz"):
        ps.validar_jogo("quiz", _c([_it(1, texto=""), _it(2)]), {"modo": "ouvir"}, None)


def test_quiz_regras_normalizadas():
    _, r = ps.validar_jogo("quiz", _c([_it(1), _it(2)]), {"modo": "xx", "opcoes": 7, "fim": "perguntas", "perguntas": 999, "som": 0}, None)
    assert r == {"modo": "ouvir", "opcoes": 3, "fim": "perguntas", "perguntas": 100, "som": False, "voz": True}
    _, r = ps.validar_jogo("quiz", _c([_it(1), _it(2)]), {"modo": "ver", "opcoes": 2}, None)
    assert (r["modo"], r["opcoes"]) == ("ver", 2)


def test_quiz_distratores_ate_3():
    c, _ = ps.validar_jogo("quiz", _c([_it(1, distratores=["Pato", "Gato", "Mato", "Fato"]), _it(2)]), {"modo": "ver"}, None)
    assert c["itens"][0]["distratores"] == ["Pato", "Gato", "Mato"]


def test_roleta_sem_mudanca():
    _, r = ps.validar_jogo("roleta", _c([_it(1), _it(2)]), {}, None)
    assert r == {"fim": "todas", "giros": 10, "mostrar_palavra": True, "som": True, "voz": True}
```
- [ ] **Step 2: Run** `pytest tests/test_pandoo_quiz.py -q` → FAIL ("Esse modelo de jogo ainda não existe").
- [ ] **Step 3: Implement** in `pandoo_service.py`:
  - `MODELOS = {"roleta", "quiz"}`; `REGRAS_PADRAO["quiz"] = {"modo": "ouvir", "opcoes": 3, "fim": "todas", "perguntas": 10, "som": True, "voz": True}`.
  - `_regras(modelo, regras)` per model: roleta as today; quiz: `modo` ∈ {ouvir, ver}; `opcoes` int ∈ {2,3,4} else default; `fim` ∈ {todas, perguntas}; `perguntas` clamp 1..100 (invalid → default); `som`/`voz` bool.
  - `validar_jogo`: compute `regras_norm = _regras(modelo, regras)` **before** the item loop; `exigir_imagem = modelo in ("roleta", "quiz")` with message by model ("a roleta precisa…"/"o quiz precisa de uma imagem em cada figura."); after `_lado`, for quiz: `ver` and no texto → `Item N: o quiz precisa da palavra de cada figura no modo 'Ver a figura e achar a palavra'.`; `ouvir` and no texto and no audio → `Item N: o quiz precisa da palavra ou a voz de cada figura no modo 'Ouvir e achar a figura'.`; distratores limit `3 if modelo == "quiz" else 10`. Return `resultado, regras_norm`.
- [ ] **Step 4: Run** the new file + `tests/test_pandoo_*.py` → PASS.
- [ ] **Step 5: Commit** "Pandoo Quiz: modelo, regras e validação no backend".

### Task 2: Pure quiz logic in `pandoo_core.js`

**Files:** Modify `frontend/js/pandoo/pandoo_core.js`; Test `frontend/tests/pandoo_core.test.js`

**Produces:** `REGRAS_PADRAO_PANDOO.quiz`; `problemasDoConteudo(modelo, conteudo, regras)`; `normalizarPalavra(t)`; `opcoesDaPergunta(item, conteudo, regras, aleatorio = Math.random) -> [{item_id|null, texto, imagem, certa}]`; `estadoInicialQuiz(conteudo)`; `proximaPerguntaQuiz(estado, conteudo, aleatorio)`; `registrarRespostaQuiz(estado, item, tentativas, conteudo) -> estado` (detalhe `resultado` = tentativas === 0 ? "conseguiu" : "treinar"); `quizTerminou(estado, regras, conteudo)`.

- [ ] **Step 1: Failing tests** (append):
```js
// Pandoo fase 2 (30/09/2026): Quiz.
const q = (id, texto, dist = []) => ({ id, pergunta: { texto, imagem: "iVBORw0KGgo=", audio: null }, distratores: dist });
const cq = (...itens) => ({ versao: 1, itens });

test("quiz: opções no modo ouvir são figuras de outros itens, com a certa", () => {
    const c = cq(q("a", "Rato"), q("b", "Rosa"), q("c", "Robô"), q("d", "Leão"));
    const ops = p.opcoesDaPergunta(c.itens[0], c, { modo: "ouvir", opcoes: 3 }, () => 0.5);
    assert.equal(ops.length, 3);
    assert.equal(ops.filter(o => o.certa).length, 1);
    assert.equal(ops.find(o => o.certa).item_id, "a");
    assert.ok(ops.every(o => o.imagem));
});

test("quiz: modo ver usa distratores próprios primeiro e não repete palavra", () => {
    const c = cq(q("a", "Rato", ["Pato", "rato", "Gato"]), q("b", "Rosa"), q("c", "Robô"));
    const ops = p.opcoesDaPergunta(c.itens[0], c, { modo: "ver", opcoes: 4 }, () => 0.1);
    const textos = ops.map(o => o.texto);
    assert.equal(ops.length, 4);
    assert.ok(textos.includes("Rato") && textos.includes("Pato") && textos.includes("Gato"));
    assert.equal(new Set(textos.map(p.normalizarPalavra)).size, 4);
});

test("quiz: poucos itens → usa o que existe (mínimo 2)", () => {
    const c = cq(q("a", "Rato"), q("b", "Rosa"));
    assert.equal(p.opcoesDaPergunta(c.itens[0], c, { modo: "ouvir", opcoes: 4 }).length, 2);
    const iguais = cq(q("a", "Rato"), q("b", "rato"));
    assert.equal(p.opcoesDaPergunta(iguais.itens[0], iguais, { modo: "ver", opcoes: 3 }).length, 1);
});

test("quiz: ordem sem repetir e fim por 'todas' / 'perguntas'", () => {
    const c = cq(q("a", "A"), q("b", "B"));
    let e = p.estadoInicialQuiz(c);
    const vistos = [];
    while (!p.quizTerminou(e, { fim: "todas" }, c)) {
        const it = p.proximaPerguntaQuiz(e, c, () => 0);
        vistos.push(it.id);
        e = p.registrarRespostaQuiz(e, it, vistos.length === 1 ? 0 : 2, c);
    }
    assert.deepEqual([...vistos].sort(), ["a", "b"]);
    assert.deepEqual(e.detalhes.map(d => d.resultado), ["conseguiu", "treinar"]);
    let f = p.estadoInicialQuiz(c);
    const seq = [];
    while (!p.quizTerminou(f, { fim: "perguntas", perguntas: 5 }, c)) {
        const it = p.proximaPerguntaQuiz(f, c, () => 0);
        seq.push(it.id);
        f = p.registrarRespostaQuiz(f, it, 0, c);
    }
    assert.equal(seq.length, 5);
    assert.notEqual(seq[0], seq[1]);
});

test("quiz: problemas por modo", () => {
    const c = cq(q("a", ""), q("b", "Rosa"));
    assert.ok(p.problemasDoConteudo("quiz", c, { modo: "ver" }).some(t => t.includes("Figura 1")));
    assert.ok(p.problemasDoConteudo("quiz", c, { modo: "ouvir" }).some(t => t.includes("Figura 1")));
    c.itens[0].pergunta.audio = "SUQz";
    assert.equal(p.problemasDoConteudo("quiz", c, { modo: "ouvir" }).length, 0);
});
```
- [ ] **Step 2: Run** `node --test frontend/tests/pandoo_core.test.js` → FAIL.
- [ ] **Step 3: Implement** in `pandoo_core.js`:
  - `REGRAS_PADRAO_PANDOO.quiz = { modo: "ouvir", opcoes: 3, fim: "todas", perguntas: 10, som: true, voz: true }`.
  - `normalizarPalavra(t)`: `String(t||"").normalize("NFD").replace(/[̀-ͯ]/g, "").trim().toLowerCase()`.
  - `problemasDoConteudo(modelo, conteudo, regras = {})`: keep current checks; for quiz: each item without image → `Figura N: falta a imagem.`; `ver` without texto → `Figura N: falta a palavra.`; `ouvir` without texto and audio → `Figura N: falta a palavra ou a voz.`
  - `opcoesDaPergunta`: `ouvir` → other items with image, shuffled (Fisher-Yates using `aleatorio`), take `opcoes-1`, map `{item_id, texto, imagem, certa:false}`; plus right `{item_id: item.id, texto, imagem, certa: true}`; shuffle all. `ver` → candidates = item.distratores then other items' texts (shuffled), skip empty and any whose `normalizarPalavra` equals one already chosen (including the right one), take up to `opcoes-1`; options `{item_id: null|otherId, texto, imagem: null, certa}`; shuffle.
  - Quiz state mirrors the roleta: `{pool, sorteados, rodadas, detalhes}`; `proximaPerguntaQuiz` = `sortearItemRoleta`-like; `registrarRespostaQuiz(estado, item, tentativas, conteudo)` = `registrarRodada(estado, item, tentativas === 0 ? "conseguiu" : "treinar", conteudo)`; `quizTerminou(e, regras, c)` = `regras.fim === "perguntas" ? e.rodadas >= regras.perguntas : e.sorteados.length >= c.itens.length`.
  - Export all in `module.exports`.
- [ ] **Step 4: Run** → PASS (all node tests).
- [ ] **Step 5: Commit** "Pandoo Quiz: regras puras (opções, ordem, fim)".

### Task 3: Stage label + quiz game + CSS

**Files:** Modify `frontend/js/pandoo/pandoo_palco.js`, `frontend/css/pandoo.css`, `frontend/index.html`; Create `frontend/js/pandoo/jogos/quiz.js`

- [ ] **Step 1: Stage** — summary text uses the game's label: `const [um, varios] = def.rotuloRodada || ["giro", "giros"]` → `em ${n} ${n === 1 ? um : varios}`; the no-round mission message uses `def.avisoSemRodada || "Você ainda não girou a roleta. Gire pelo menos uma vez para liberar a missão 🎡"`. Expose `palco.efeito` already exists; add `PandooSom.erro()` is not required — use `efeito("treinar")` for the wrong-answer sound.
- [ ] **Step 2: `jogos/quiz.js`** — `registrarJogo("quiz", {nome: "Quiz", icone: "❓", rotuloRodada: ["pergunta", "perguntas"], avisoSemRodada: "Você ainda não respondeu nenhuma pergunta. Responda pelo menos uma para liberar a missão ❓", requisitos: c => problemasDoConteudo("quiz", c), iniciar(palco, conteudo, regras)})`:
  - state via Task 2; `rodada()` picks `item = proximaPerguntaQuiz`, `ops = opcoesDaPergunta`, `tentativas = 0`, `travado = false`;
  - renders into `palco.area`: `.pdq-pergunta` card (ouvir: "Onde está…", 🔊 big icon, escaped word when present, "🔊 Ouvir de novo"; ver: figure `<img>` via `_imgItemPandoo(item, "pdq-fig")`, "Qual é o nome?", "🔊 Ouvir de novo"), `.pdq-opcoes.figs|.palavras` with buttons (`data-certa`), `.pdq-dica` "Toque na resposta certa 💚";
  - `palco.falarItem(item)` on render (1 s delay handled by `PandooSom`);
  - click: if `travado` return; wrong → `tentativas++`, add `.errada` (disabled), dica "Quase! Tente outra 💚", `palco.efeito("treinar")`; right → `travado = true`, `.certa`, `palco.registrar(item, tentativas === 0 ? "conseguiu" : "treinar")` (sound + confetti), dica accordingly, `estado = registrarRespostaQuiz(...)`, update placar (`❓ ${estado.rodadas} de ${total}` where total = `regras.fim === "perguntas" ? regras.perguntas : itens.length`; ⭐ count of first-try), after 1500 ms: if `palco.encerrado` return; if `quizTerminou` → `palco.finalizar({encerradoAntes:false})` else `rodada()`.
- [ ] **Step 3: CSS** (`pandoo.css`, namespaced `.pdq-*`) — ported from the preview: question card (white, radius 26, shadow), `.pdq-fig` 180 px contain, option grid (`figs`: 3 cols desktop / 2 cols ≤ 800 px; `palavras`: 1 col, big Fredoka 26 px), `.errada` shake + opacity .35 + `pointer-events:none`, `.certa` green + pop, `.pdq-dica` pill; `prefers-reduced-motion` disables shake/pop.
- [ ] **Step 4:** `index.html`: `<script src="/js/pandoo/jogos/quiz.js"></script>` after `roleta.js`. `node --check`; node tests green.
- [ ] **Step 5: Commit** "Pandoo Quiz: jogo no palco comum".

### Task 4: Editor — model switch, quiz rules, own wrong options

**Files:** Modify `frontend/js/views/pandoo.js`, `frontend/css/pandoo.css`

- [ ] **Step 1:** `MODELOS_PANDOO_EDITOR` quiz `pronto: true`; model cards become buttons (`data-modelo`) — only `pronto` ones clickable. Switching model: keep `est.conteudo`, set `est.regras = {...REGRAS_PADRAO_PANDOO[novo], ...regrasCompatíveis}` (only `som`/`voz` carried over), re-render rules panel and items (title "2. Figuras da roleta" / "2. Perguntas do quiz"; hint text per model).
- [ ] **Step 2:** Rules panel rendered by `renderRegras()` per model: roleta = current markup; quiz = "Como a criança responde" (two `.pd-modo` cards 👂/👀 with explanations), "Quantas opções em cada pergunta" (2/3/4 chips), "Quando o jogo termina" (radios `todas` / `perguntas` + number 1–100), checkboxes "Som de acerto e comemoração", "Ler a pergunta em voz alta". `lerFormulario()` reads per model into `est.regras`.
- [ ] **Step 3:** In quiz `ver` mode each item shows "+ opções erradas próprias (opcional)" → inline up to 3 text inputs (`maxlength 80`) bound to `item.distratores`; collapsed summary "Opções erradas: Pato · Gato". Hidden in `ouvir` (data kept, not shown).
- [ ] **Step 4:** Preview/save call `problemasDoConteudo(est.modelo, est.conteudo, est.regras)`. List/Biblioteca icon already comes from `jogoRegistrado(modelo).icone` (check `viewPandoo` uses it; the Biblioteca card shows 🎮 — keep).
- [ ] **Step 5:** `node --check`; node tests; commit "Pandoo Quiz: editor (modelo, regras e opções erradas próprias)".

### Task 5: Browser check, docs, PR

- [ ] **Step 1:** Fresh seed, server; Playwright (Pillow figures, `uv run --with playwright --with pillow`), liberate Pandoo via API: create quiz "ouvir" (4 figures), preview: tap a wrong option (dims) then right (next question after 1.5 s), finish → summary "em N perguntas"; switch to "ver" with own wrong options on figure 1, preview shows the words (no duplicates); save; mission with the quiz → child: locked, play one question, "Finalizar", unlocked; ficha shows per-figure; 2-figure quiz with 4 options → 2 options; phone 390×844 layout; no JS errors.
- [ ] **Step 2:** Full backend suite + node tests.
- [ ] **Step 3:** CLAUDE.md item 5u (Quiz), section 7 pending → "Pandoo: Memória, Associação, Quebra-cabeça; Flashcards por último (com pronúncia)".
- [ ] **Step 4:** Final review (subagent, opus), fix Important with tests, PR, CI green → merge.
