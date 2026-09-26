# Pandoo fase 1 — PR B (tela) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Front-end of Pandoo: menu + game list + editor (figures with image, word and recorded voice; rules; scene), the shared game "stage" (scene animations, sounds, voice, finish button, trophy summary, result upload), the first game (roleta), and the integrations — Biblioteca, Nova Missão picker, Mundo da Criança (mission gating), patient file results, clinic scene in Configurações, Admin switch, Módulos screen.

> **Revisado em 26/09/2026, antes da execução** — depois deste plano entraram os planos configuráveis (PR #18: o Pandoo virou módulo comum, liberado em "Módulos da clínica"; `modulos_so_admin`/`so_admin` não existem mais) e o White Label (PRs #20–#24: `frontend/js/cenarios_animados.js` com os cenários animados, o perfil de envio `cenario` e `tomDaImagemBase64` já existem). As tarefas abaixo já estão ajustadas a isso.

**Architecture:** New folder `frontend/js/pandoo/` with small global-script files: `pandoo_core.js` (catalog + pure helpers, Node-tested), scenes from the shared `frontend/js/cenarios_animados.js` (`montarCenarioAnimado`, already loaded), `pandoo_som.js` (Web Audio sounds + voice), `pandoo_palco.js` (full-screen stage shared by every game), `jogos/roleta.js` (first game, registers itself). New view `frontend/js/views/pandoo.js` (list + editor) and `frontend/css/pandoo.css`. Integrations are small edits in existing views. Visual reference: the approved preview `.superpowers/brainstorm/230-1790306451/content/pandoo-v4.html` (not versioned) — copy its look (colors, panda SVG, wheel, card, buttons, scenes, sounds).

**Tech Stack:** Vanilla JS globals (no build, no libraries), SVG + CSS animations, Web Audio API, `speechSynthesis`, `MediaRecorder`, `node --test` for pure logic, Playwright (Python via `uv`) for the browser pass.

**Spec:** `docs/superpowers/specs/2026-09-25-pandoo-fase1-design.md` · Backend already merged (PR #16): routes `/api/pandoo/jogos`, `/api/pandoo/jogos/<id>`, `/api/pandoo/resultados`; mission atividades carry `exercicio_tipo` ("jogo"/"atividade") and `jogo_jogado`; `GET /pandoo/jogos/<id>` returns `cenario_efetivo = {tipo, imagem (base64|null), tom}`; the Pandoo module is released per clinic in Admin → Clínicas → "Módulos da clínica" (or by plan); org has `pandoo_cenario_padrao/imagem/tom` (`GET /pessoas/organizacao` returns the image; `/auth/me` only `tem_cenario_imagem`).

## Global Constraints

- CSP: `script-src 'self'` (no inline scripts/handlers, no `eval`, no CDN), `img-src 'self' data:`, `media-src 'self' data:` — **no `blob:` URLs** anywhere (use `data:`; `createImageBitmap` for decoding).
- Every user text is escaped with `escapeHtml` when interpolated in HTML. Images/audio only as `data:<mime>;base64,<b64>` with the mime detected from the bytes (`mimeDaImagem`, `mimeDoAudio`).
- Texts (pt-BR, exact): after the spin — "Depois que a criança tentar, é só tocar em como foi 💚"; summary — "Prontinho! A equipe da clínica já vai ver como você foi 💚"; buttons "Conseguiu ⭐", "Vamos treinar mais 💪", "Finalizar jogo", "Girar! 🎉", "🔊 Ouvir de novo"; mission gate hint "Jogue o jogo para liberar 🎮".
- Voice: recorded audio of the item has priority; otherwise browser voice pt-BR (rate 0.85, pitch 1.15); starts **2 s** after the figure appears; can be turned off with the sound.
- Scenes: `bambu` 🎋 Bambuzal, `mar` 🐠 Fundo do mar, `espaco` 🚀 Espaço (tone "escuro"), `clinica` 🖼️ Imagem da clínica (tone from image brightness: > 0.6 → "claro"). Texts over the scene use the tone: claro → dark text + light translucent pill; escuro → white text + dark translucent pill.
- Upload guidance (spec table): figura "📐 JPG, PNG ou WebP · ideal 512 × 512 px (quadrada) · até 5 MB" → reduced to 512 px/≤ 300 KB; cenário: the existing `cenario` profile (1600 px, ≤ 780 KB, up to 15 MB input — created by the White Label, keep it); voz "🎙️ MP3, M4A, OGG, WAV ou WebM · até 30 segundos · até 600 KB".
- Pandoo menu/editor only for gestor and profissional **with** `pandoo` in `Sessao.usuario.organizacao.modulos_habilitados`. Playing a game in a mission never depends on the module.
- Branch `pandoo-fase1-tela`. No backend/schema change → auto-merge after tests + CI green. Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Comments in pt-BR, explaining the why, citing "Pandoo, 25/09/2026".

## Review Focus

1. **Game ends in every way** — all figures drawn ("todas"), N spins ("giros" with N larger than the number of figures → figures repeat only after all were used), "Finalizar jogo" before the first spin (0 rounds). Covered by `pandoo_core.test.js` (Task 2) and the browser pass (Task 10).
2. **Result upload fails** (network/500) at the end of a mission game → summary shows the error with "Tentar de novo"; the child is never stuck and the mission stays locked until a save succeeds. Task 4 code + Task 10 check (block the route with Playwright).
3. **Scene image light vs dark** → text color and pill follow the computed tone; tone recomputed when the clinic uploads a new image. Tests for `tomPorBrilho`/`luminanciaMedia` (Task 3) + browser check.
4. **Microphone denied / unsupported / recording > 30 s / > 600 KB** → friendly message; recording auto-stops at 30 s; nothing crashes. Task 5 code + browser check with a fake media stream.
5. **Weekly mission** — game played today unlocks "Marquei hoje!"; the next day (new `jogo_jogado=false` from the API) it is locked again. UI reads only `jogo_jogado` from the API; browser check by posting a result and reloading (Task 10).

---

### Task 1: Perfis de envio do Pandoo (figura, cenário, voz)

**Files:**
- Modify: `frontend/js/envio_arquivos.js` (`PERFIS_ENVIO`; limit formatting in `validarEntradaEnvio`)
- Modify: `frontend/tests/envio_arquivos.test.js`

**Interfaces:**
- Produces: profiles `figura`, `voz` in `PERFIS_ENVIO` (`cenario` already exists — White Label); limits below 1 MB printed as KB in errors ("passa de 600 KB").

- [ ] **Step 1: Failing tests** — append to `frontend/tests/envio_arquivos.test.js`:

```js
// Pandoo (25/09/2026): figuras do jogo e voz gravada.
test("perfis do Pandoo: figura e voz", () => {
    assert.match(e.PERFIS_ENVIO.figura.texto, /512 × 512 px/);
    assert.match(e.PERFIS_ENVIO.voz.texto, /30 segundos/);
    assert.equal(e.validarEntradaEnvio(arq("a.png", "image/png", 4 * MB), "figura").ok, true);
    assert.equal(e.validarEntradaEnvio(arq("a.png", "image/png", 6 * MB), "figura").ok, false);
    assert.equal(e.validarEntradaEnvio(arq("v.mp3", "audio/mpeg", 500 * 1024), "voz").ok, true);
    assert.equal(e.validarEntradaEnvio(arq("v.webm", "audio/webm", 500 * 1024), "voz").ok, true);
    const grande = e.validarEntradaEnvio(arq("v.mp3", "audio/mpeg", 700 * 1024), "voz");
    assert.equal(grande.ok, false);
    assert.match(grande.erro, /600 KB/);
    assert.equal(e.validarEntradaEnvio(arq("a.png", "image/png"), "voz").ok, false);
});
```

- [ ] **Step 2: Run — expect FAIL** (`Cannot read properties of undefined (reading 'texto')`): `node --test frontend/tests/envio_arquivos.test.js`

- [ ] **Step 3: Implement** — in `PERFIS_ENVIO` add:

```js
    // Pandoo (25/09/2026)
    figura: {
        texto: "📐 JPG, PNG ou WebP · ideal 512 × 512 px (quadrada) · até 5 MB",
        tiposAceitos: _TIPOS_IMAGEM, maxImagemMB: 5, maxOutrosMB: 0,
        ladoMax: 512, limiteSaidaKB: 300, manterTransparencia: false, ladoMinAviso: 200,
    },
    voz: {
        texto: "🎙️ MP3, M4A, OGG, WAV ou WebM · até 30 segundos · até 600 KB",
        tiposAceitos: ["audio"], maxImagemMB: 0, maxOutrosMB: 600 / 1024,
        ladoMax: 0, limiteSaidaKB: 0, manterTransparencia: false, ladoMinAviso: 0,
    },
```

In `validarEntradaEnvio`, format the limit: replace `` `"${file.name}" passa de ${maxMB} MB.` `` with `` `"${file.name}" passa de ${_rotuloTamanho(maxMB)}.` `` and add:

```js
function _rotuloTamanho(mb) {
    return mb >= 1 ? `${mb} MB` : `${Math.round(mb * 1024)} KB`;
}
```

(`.webm` with empty `type` maps to `video` by extension — fine: files picked by the user come with a type; recordings are built in code, not validated here.)

- [ ] **Step 4: Run — expect PASS** (all `node --test frontend/tests/*.test.js`).
- [ ] **Step 5: Commit** — "Pandoo: perfis de envio de figura e voz".

### Task 2: `pandoo_core.js` — catálogo e regras puras

**Files:**
- Create: `frontend/js/pandoo/pandoo_core.js`
- Create: `frontend/tests/pandoo_core.test.js`
- Modify: `frontend/index.html` (script tags, see Step 3)

**Interfaces:**
- Produces (globals; `module.exports` in Node):
  - `registrarJogo(codigo, def)`, `jogoRegistrado(codigo) -> def|null`, `PANDOO_JOGOS`
  - `REGRAS_PADRAO_PANDOO = {roleta: {fim: "todas", giros: 10, mostrar_palavra: true, som: true, voz: true}}`
  - `novoItemPandoo() -> item`, `conteudoVazioPandoo() -> {versao: 1, itens: [item, item]}`
  - `problemasDoConteudo(modelo, conteudo) -> string[]`
  - `estadoInicialRoleta(conteudo) -> {pool: string[], rodadas: 0, detalhes: []}`
  - `sortearItemRoleta(estado, conteudo, aleatorio = Math.random) -> item` (pool refills with all ids when empty)
  - `registrarRodada(estado, item, resultado, conteudo) -> novoEstado` (removes the item from the current pool — refilled with every id when it was empty —, appends `{item_id, texto, resultado}`)
  - `partidaTerminou(estado, regras, conteudo) -> bool` ("todas": every item has been drawn at least once; "giros": `rodadas >= giros`)
  - `resumoPartida(detalhes) -> {conseguiu, treinar}`
  - `mimeDaImagem(b64) -> "image/jpeg"|"image/png"|"image/webp"|"image/gif"`, `mimeDoAudio(b64) -> "audio/mpeg"|"audio/ogg"|"audio/wav"|"audio/webm"|"audio/mp4"`
  - `cenarioEfetivoPandoo(cenarioJogo, org) -> {tipo, imagem, tom}` (same rule as the backend `_cenario_efetivo`)
  - `cenarioParaPalco(efetivo) -> {tipo, imagemUrl, tom}` — adapts `cenario_efetivo` to the shared `montarCenarioAnimado` (`tipo` "clinica" + `imagemUrl = data:<mime>;base64,<img>`; missing image → "bambu")

- [ ] **Step 1: Failing tests** — `frontend/tests/pandoo_core.test.js`:

```js
// Pandoo (25/09/2026) — regras puras do catálogo e da roleta.
const test = require("node:test");
const assert = require("node:assert/strict");
const p = require("../js/pandoo/pandoo_core.js");

const item = (id, texto = id, imagem = "iVBORw0KGgo=") => ({ id, pergunta: { texto, imagem, audio: null } });
const conteudo = (n) => ({ versao: 1, itens: Array.from({ length: n }, (_, i) => item(`i${i}`, `P${i}`)) });

test("catálogo registra e encontra jogos", () => {
    p.registrarJogo("teste", { nome: "Teste", iniciar() {} });
    assert.equal(p.jogoRegistrado("teste").nome, "Teste");
    assert.equal(p.jogoRegistrado("nao-existe"), null);
});

test("conteúdo vazio tem 2 itens com ids diferentes", () => {
    const c = p.conteudoVazioPandoo();
    assert.equal(c.versao, 1);
    assert.equal(c.itens.length, 2);
    assert.notEqual(c.itens[0].id, c.itens[1].id);
});

test("problemas do conteúdo da roleta", () => {
    assert.deepEqual(p.problemasDoConteudo("roleta", conteudo(3)), []);
    assert.ok(p.problemasDoConteudo("roleta", conteudo(1))[0].includes("2 a 24"));
    assert.ok(p.problemasDoConteudo("roleta", conteudo(25))[0].includes("2 a 24"));
    const c = conteudo(3);
    c.itens[1].pergunta.imagem = null;
    assert.ok(p.problemasDoConteudo("roleta", c).some(t => t.includes("Figura 2")));
});

test("roleta 'todas': cada figura sai uma vez e a partida termina", () => {
    const c = conteudo(3);
    const regras = { ...p.REGRAS_PADRAO_PANDOO.roleta };
    let e = p.estadoInicialRoleta(c);
    const saidas = [];
    while (!p.partidaTerminou(e, regras, c)) {
        const it = p.sortearItemRoleta(e, c, () => 0);
        saidas.push(it.id);
        e = p.registrarRodada(e, it, "conseguiu", c);
    }
    assert.deepEqual([...saidas].sort(), ["i0", "i1", "i2"]);
    assert.equal(e.rodadas, 3);
});

test("roleta 'giros' maior que o número de figuras: repete só depois de sair todas", () => {
    const c = conteudo(2);
    const regras = { ...p.REGRAS_PADRAO_PANDOO.roleta, fim: "giros", giros: 5 };
    let e = p.estadoInicialRoleta(c);
    const saidas = [];
    while (!p.partidaTerminou(e, regras, c)) {
        const it = p.sortearItemRoleta(e, c, () => 0);
        saidas.push(it.id);
        e = p.registrarRodada(e, it, "treinar", c);
    }
    assert.equal(saidas.length, 5);
    assert.notEqual(saidas[0], saidas[1]); // as duas primeiras são diferentes
});

test("partida encerrada antes de girar: 0 rodadas", () => {
    const e = p.estadoInicialRoleta(conteudo(3));
    assert.equal(e.rodadas, 0);
    assert.deepEqual(p.resumoPartida(e.detalhes), { conseguiu: 0, treinar: 0 });
});

test("resumo da partida", () => {
    const d = [{ resultado: "conseguiu" }, { resultado: "treinar" }, { resultado: "conseguiu" }];
    assert.deepEqual(p.resumoPartida(d), { conseguiu: 2, treinar: 1 });
});

test("mime da imagem e do áudio pelo início do base64", () => {
    assert.equal(p.mimeDaImagem("/9j/4AAQ"), "image/jpeg");
    assert.equal(p.mimeDaImagem("iVBORw0KGgo"), "image/png");
    assert.equal(p.mimeDaImagem("UklGRiQAAABXRUJQ"), "image/webp");
    assert.equal(p.mimeDaImagem("R0lGODlh"), "image/gif");
    assert.equal(p.mimeDoAudio(Buffer.from("ID3\x03\x00").toString("base64")), "audio/mpeg");
    assert.equal(p.mimeDoAudio(Buffer.from("OggS\x00").toString("base64")), "audio/ogg");
    assert.equal(p.mimeDoAudio(Buffer.from("RIFF\x00\x00\x00\x00WAVE").toString("base64")), "audio/wav");
    assert.equal(p.mimeDoAudio(Buffer.from([0x1a, 0x45, 0xdf, 0xa3, 0, 0]).toString("base64")), "audio/webm");
    assert.equal(p.mimeDoAudio(Buffer.from("\x00\x00\x00\x20ftypM4A ").toString("base64")), "audio/mp4");
});

test("cenário efetivo segue a mesma regra do backend", () => {
    const org = { pandoo_cenario_padrao: "clinica", pandoo_cenario_imagem: "AAA", pandoo_cenario_tom: "claro" };
    assert.deepEqual(p.cenarioEfetivoPandoo(null, org), { tipo: "clinica", imagem: "AAA", tom: "claro" });
    assert.deepEqual(p.cenarioEfetivoPandoo("mar", org), { tipo: "mar", imagem: null, tom: "escuro" });
    assert.deepEqual(p.cenarioEfetivoPandoo("clinica", { pandoo_cenario_padrao: "bambu" }), { tipo: "bambu", imagem: null, tom: "escuro" });
    assert.deepEqual(p.cenarioEfetivoPandoo(null, {}), { tipo: "bambu", imagem: null, tom: "escuro" });
});

test("cenário para o palco (montarCenarioAnimado)", () => {
    assert.deepEqual(p.cenarioParaPalco({ tipo: "mar", imagem: null, tom: "escuro" }), { tipo: "mar", imagemUrl: null, tom: "escuro" });
    assert.deepEqual(p.cenarioParaPalco({ tipo: "clinica", imagem: "iVBORw0KGgo", tom: "claro" }),
        { tipo: "clinica", imagemUrl: "data:image/png;base64,iVBORw0KGgo", tom: "claro" });
    assert.deepEqual(p.cenarioParaPalco({ tipo: "clinica", imagem: null, tom: "claro" }), { tipo: "bambu", imagemUrl: null, tom: "escuro" });
    assert.deepEqual(p.cenarioParaPalco(null), { tipo: "bambu", imagemUrl: null, tom: "escuro" });
});
```

- [ ] **Step 2: Run — expect FAIL** (`Cannot find module`).

- [ ] **Step 3: Implement** — `frontend/js/pandoo/pandoo_core.js`:

```js
// ============================================================================
// Pandoo (25/09/2026) — núcleo: catálogo de jogos plugáveis + regras puras.
// Um jogo novo = um arquivo em js/pandoo/jogos/ que chama registrarJogo().
// Funções puras testadas em frontend/tests/pandoo_core.test.js.
// ============================================================================

const PANDOO_JOGOS = {};
const PANDOO_LIMITES = { minItens: 2, maxItens: 24, maxTexto: 80 };
const REGRAS_PADRAO_PANDOO = {
    roleta: { fim: "todas", giros: 10, mostrar_palavra: true, som: true, voz: true },
};

function registrarJogo(codigo, def) {
    PANDOO_JOGOS[codigo] = { codigo, ...def };
}

function jogoRegistrado(codigo) {
    return PANDOO_JOGOS[codigo] || null;
}

function novoItemPandoo() {
    const id = "i" + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
    return { id, pergunta: { texto: "", imagem: null, audio: null }, resposta: { texto: "", imagem: null, audio: null }, distratores: [], grupo: null };
}

function conteudoVazioPandoo() {
    return { versao: 1, itens: [novoItemPandoo(), novoItemPandoo()] };
}

// Espelho amigável das regras do backend (pandoo_service.py), para avisar no
// editor antes de salvar. O backend continua sendo quem decide.
function problemasDoConteudo(modelo, conteudo) {
    const itens = (conteudo && conteudo.itens) || [];
    const problemas = [];
    if (itens.length < PANDOO_LIMITES.minItens || itens.length > PANDOO_LIMITES.maxItens) {
        problemas.push(`O jogo precisa ter de ${PANDOO_LIMITES.minItens} a ${PANDOO_LIMITES.maxItens} figuras.`);
    }
    if (modelo === "roleta") {
        itens.forEach((it, i) => {
            if (!it.pergunta || !it.pergunta.imagem) problemas.push(`Figura ${i + 1}: falta a imagem.`);
        });
    }
    return problemas;
}

function estadoInicialRoleta(conteudo) {
    return { pool: conteudo.itens.map(i => i.id), sorteados: [], rodadas: 0, detalhes: [] };
}

// Sorteia entre as figuras que ainda não saíram; quando todas já saíram (modo
// "N giros" com N maior que o total), o sorteio recomeça com todas.
function sortearItemRoleta(estado, conteudo, aleatorio = Math.random) {
    const pool = estado.pool.length ? estado.pool : conteudo.itens.map(i => i.id);
    const id = pool[Math.min(pool.length - 1, Math.floor(aleatorio() * pool.length))];
    return conteudo.itens.find(i => i.id === id);
}

function registrarRodada(estado, item, resultado, conteudo) {
    const atual = estado.pool.length ? estado.pool : conteudo.itens.map(i => i.id);
    return {
        pool: atual.filter(id => id !== item.id),
        sorteados: estado.sorteados.includes(item.id) ? estado.sorteados : [...estado.sorteados, item.id],
        rodadas: estado.rodadas + 1,
        detalhes: [...estado.detalhes, { item_id: item.id, texto: (item.pergunta && item.pergunta.texto) || "", resultado }],
    };
}

function partidaTerminou(estado, regras, conteudo) {
    if (regras.fim === "giros") return estado.rodadas >= regras.giros;
    return estado.sorteados.length >= conteudo.itens.length;
}

function resumoPartida(detalhes) {
    const conseguiu = detalhes.filter(d => d.resultado === "conseguiu").length;
    return { conseguiu, treinar: detalhes.length - conseguiu };
}

function mimeDaImagem(b64) {
    const s = String(b64 || "");
    if (s.startsWith("/9j/")) return "image/jpeg";
    if (s.startsWith("iVBOR")) return "image/png";
    if (s.startsWith("UklGR")) return "image/webp";
    if (s.startsWith("R0lGOD")) return "image/gif";
    return "image/jpeg";
}

function _primeirosBytes(b64, n) {
    try {
        const bin = typeof atob === "function" ? atob(String(b64).slice(0, 24)) : Buffer.from(String(b64).slice(0, 24), "base64").toString("binary");
        return Array.from(bin.slice(0, n), c => c.charCodeAt(0));
    } catch (e) { return []; }
}

function mimeDoAudio(b64) {
    const b = _primeirosBytes(b64, 12);
    const txt = (i, j) => String.fromCharCode(...b.slice(i, j));
    if (txt(0, 3) === "ID3" || (b[0] === 0xff && (b[1] & 0xe0) === 0xe0)) return "audio/mpeg";
    if (txt(0, 4) === "OggS") return "audio/ogg";
    if (txt(0, 4) === "RIFF") return "audio/wav";
    if (b[0] === 0x1a && b[1] === 0x45 && b[2] === 0xdf && b[3] === 0xa3) return "audio/webm";
    if (txt(4, 8) === "ftyp") return "audio/mp4";
    return "audio/mpeg";
}

// Mesma regra de pandoo_bp._cenario_efetivo (backend).
function cenarioEfetivoPandoo(cenarioJogo, org) {
    org = org || {};
    let tipo = cenarioJogo || org.pandoo_cenario_padrao || "bambu";
    if (tipo === "clinica" && org.pandoo_cenario_imagem) {
        return { tipo: "clinica", imagem: org.pandoo_cenario_imagem, tom: org.pandoo_cenario_tom || "claro" };
    }
    if (tipo === "clinica") tipo = "bambu";
    return { tipo, imagem: null, tom: "escuro" };
}

// Adapta o cenario_efetivo (API) ao montarCenarioAnimado compartilhado
// (cenarios_animados.js, White Label 25/09/2026). data: porque a CSP bloqueia blob:.
function cenarioParaPalco(efetivo) {
    const e = efetivo || {};
    if (e.tipo === "clinica" && e.imagem) {
        return { tipo: "clinica", imagemUrl: `data:${mimeDaImagem(e.imagem)};base64,${e.imagem}`, tom: e.tom === "escuro" ? "escuro" : "claro" };
    }
    const tipo = ["bambu", "mar", "espaco"].includes(e.tipo) ? e.tipo : "bambu";
    return { tipo, imagemUrl: null, tom: "escuro" };
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        PANDOO_JOGOS, PANDOO_LIMITES, REGRAS_PADRAO_PANDOO, registrarJogo, jogoRegistrado,
        novoItemPandoo, conteudoVazioPandoo, problemasDoConteudo, estadoInicialRoleta, sortearItemRoleta,
        registrarRodada, partidaTerminou, resumoPartida, mimeDaImagem, mimeDoAudio, cenarioEfetivoPandoo, cenarioParaPalco,
    };
}
```

(`registrarRodada` receives `conteudo` so it can refill the pool the same way `sortearItemRoleta` does.)

`frontend/index.html`: add, right before `<script src="/js/views/login.js"></script>`:
```html
<script src="/js/pandoo/pandoo_core.js"></script>
<script src="/js/pandoo/pandoo_som.js"></script>
<script src="/js/pandoo/pandoo_palco.js"></script>
<script src="/js/pandoo/jogos/roleta.js"></script>
```
and right before `<script src="/js/app.js"></script>`: `<script src="/js/views/pandoo.js"></script>`; and after the `components.css` link: `<link rel="stylesheet" href="/css/pandoo.css">`. Create the other three JS files and `pandoo.css` as empty placeholders with just their header comment in this task (filled in Tasks 3–5) so the page never 404s a script.

- [ ] **Step 4: Run — expect PASS** (`node --test frontend/tests/*.test.js`).
- [ ] **Step 5: Commit** — "Pandoo: núcleo (catálogo de jogos e regras puras)".

### Task 3: Sons/voz e estilos do palco

**Files:**
- Modify: `frontend/js/pandoo/pandoo_som.js`, `frontend/css/pandoo.css`

**Interfaces:**
- Consumes: `montarCenarioAnimado(elemento, {tipo, imagemUrl, tom})` from `frontend/js/cenarios_animados.js` (shared with the White Label; its scene CSS `.cenario-animado.c-bambu/.c-mar/.c-espaco/.c-clinica` already lives in `components.css`), `cenarioParaPalco` (Task 2), `mimeDoAudio` (Task 2).
- Produces:
  - `PandooSom`: `{ligado, alternar(), giro(ms), conseguiu(), treinar(), final(), falarItem(item, {atrasoMs = 2000, voz = true}), repetirItem(item), parar()}`
  - `.pandoo-palco` styles with tone variables (`data-tom` claro/escuro).

- [ ] **Step 1: `pandoo_som.js`** — port the preview's Web Audio synth (`nota`, `somGiro` ticking that slows down, `somConseguiu` arpeggio, `somTreinar`, `somFinal`) and voice into a `PandooSom` object:
  - `falarItem(item, {atrasoMs = 2000, voz = true})`: cancels any pending voice; after `atrasoMs` plays `new Audio(\`data:${mimeDoAudio(a)};base64,${a}\`)` if `item.pergunta.audio`, else `speechSynthesis` pt-BR (rate 0.85, pitch 1.15, pick a `pt-BR` voice if present); does nothing when `!ligado || !voz || !texto && !audio`.
  - `repetirItem(item)`: same with `atrasoMs: 0`.
  - `parar()`: clears the timer, `speechSynthesis.cancel()`, pauses the current `Audio`.
  - `alternar()`: flips `ligado`, calls `parar()` when turning off, returns the new state.
  - AudioContext created lazily on first sound (user gesture).
- [ ] **Step 2: `pandoo.css`** — `.pandoo-palco` (fixed inset 0, z-index 1000, flex column, Fredoka titles; the scene layer is a `.cenario-animado` child at z-index 0, everything else above), tone variables:
```css
.pandoo-palco { --texto-cenario: #fff; --sombra-texto: 0 3px 0 #0003; --pilula: #0000001f; }
.pandoo-palco[data-tom="claro"] { --texto-cenario: #2B2640; --sombra-texto: 0 2px 0 #ffffffb3; --pilula: #ffffffa6; }
```
Pandoo palette as variables on `.pandoo-palco` (`--pd-bambu:#34B36B; --pd-amora:#FF5C8A; --pd-sol:#FFC93C; --pd-ceu:#4DB8FF; --pd-uva:#8B5FBF; --pd-laranja:#FF8A3D`). `body.pandoo-aberto { overflow: hidden; }`.
- [ ] **Step 3:** `node --check frontend/js/pandoo/pandoo_som.js`; `node --test frontend/tests/*.test.js` green.
- [ ] **Step 4: Commit** — "Pandoo: sons, voz e estilos do palco".

### Task 4: Palco comum + roleta

**Files:**
- Modify: `frontend/js/pandoo/pandoo_palco.js`, `frontend/js/pandoo/jogos/roleta.js`, `frontend/css/pandoo.css`

**Interfaces:**
- Consumes: Task 2 helpers, `montarCenarioAnimado` + `cenarioParaPalco`, `PandooSom`, `Api.post`, `confetes()` (toast.js), `escapeHtml`, `Toast`.
- Produces:
  - `abrirPalcoPandoo({jogo, modo, contexto, aoFechar})` — `jogo` = response of `GET /pandoo/jogos/<id>` (or the editor state with the same shape + `cenario_efetivo`); `modo`: `"previa"` (never saves) or `"missao"` (saves to `/pandoo/resultados` with `contexto = {paciente_id, missao_id, atividade_id}`); `aoFechar(resultado|null)` called when the stage closes (`resultado` = API response or null).
  - Stage API passed to the game: `palco = {area, regras, som: PandooSom, falarItem(item), repetirItem(item), registrar(item, resultado), atualizarPlacar({progresso, estrelas}), finalizar({encerradoAntes})}`.
  - Game contract (roleta): `registrarJogo("roleta", {nome: "Roleta", icone: "🎡", requisitos: c => problemasDoConteudo("roleta", c), iniciar(palco, conteudo, regras)})`.

- [ ] **Step 1: Implement `pandoo_palco.js`** (no Node test — DOM; verified in Task 10):
  - Builds `<div class="pandoo-palco">` appended to `document.body` (and `document.body.classList.add("pandoo-aberto")` to hide page scroll), with: scene layer (`const tom = montarCenarioAnimado(camada, cenarioParaPalco(jogo.cenario_efetivo))`; `palco.dataset.tom = tom`), top bar (panda SVG + "Pandoo" mark, game title — both on the tone pill —, placar `🎡 x de N`/`⭐ n`, sound toggle button "🔊"/"🔇" calling `PandooSom.alternar()`), `area` div, and a footer button "Finalizar jogo".
  - Keeps `iniciadoEm = new Date().toISOString()`, `detalhes = []`.
  - `registrar(item, resultado)` pushes `{item_id, texto, resultado}`, plays `conseguiu`/`treinar` sound, confetti on "conseguiu".
  - `finalizar({encerradoAntes})` (idempotent — second call ignored):
    - stops voice, shows the summary card: 🏆, "Muito bem!", "Você ganhou N ⭐ em M giros", lists "Conseguiu"/"Vamos treinar mais" with small figure thumbnails (`<img src="data:...">`), the text "Prontinho! A equipe da clínica já vai ver como você foi 💚" (only in `missao` mode; in `previa` show "Prévia — nada foi salvo."), final sound + confetti;
    - in `missao` mode POSTs `{paciente_id, exercicio_id: jogo.id, missao_id, atividade_id, iniciado_em, encerrado_antes, detalhes}`; while saving the button reads "Salvando…" (disabled); on success the button "Voltar para a missão" closes and calls `aoFechar(resposta)`; on error shows the API message + "Tentar de novo" (re-POST) and a "Sair sem salvar" link that closes with `aoFechar(null)`.
    - in `previa` mode the button "Fechar" closes with `aoFechar(null)`.
  - Close = `PandooSom.parar()`, remove the element, remove the body class.
  - Unknown model → `Toast.erro("Esse modelo de jogo ainda não está disponível.")` and don't open.

- [ ] **Step 2: Implement `jogos/roleta.js`** — port the v4 wheel:
  - SVG wheel (viewBox −100…100), one slice per item with palette colors (cycle), each slice shows the figure as `<image href="data:${mimeDaImagem(img)};base64,${img}">` clipped to a circle at 66 % radius, rotated to stay readable; panda in the center; pointer on top.
  - Button "Girar! 🎉": `const item = sortearItemRoleta(estado, conteudo)`; compute the target angle for that slice (`360 - (idx + .5) * passo`), rotate with the 4 s ease-out transition (same cubic-bezier), `PandooSom.giro(4000)`; disable during the spin.
  - After the spin: card overlay with the big figure (`<img>`), the word when `regras.mostrar_palavra` and text not empty, "🔊 Ouvir de novo" (when `regras.voz`), buttons "Conseguiu ⭐" / "Vamos treinar mais 💪" / "Finalizar jogo", and the hint "Depois que a criança tentar, é só tocar em como foi 💚"; `palco.falarItem(item)` (2 s delay handled by `PandooSom`) when `regras.voz`.
  - Result buttons → `palco.registrar(item, "conseguiu"|"treinar")`, `estado = registrarRodada(...)`, `palco.atualizarPlacar(...)`, close the card; if `partidaTerminou(estado, regras, conteudo)` → `palco.finalizar({encerradoAntes: false})`.
  - "Finalizar jogo" (card or footer) → `palco.finalizar({encerradoAntes: true})`.
  - Placar progress: "todas" → `sorteados de N`; "giros" → `rodadas de giros`.

- [ ] **Step 3: CSS** — wheel, pointer, center, "Girar!" button, card (pop animation), result buttons, summary, confetti colors — ported from the preview into `pandoo.css` (namespaced under `.pandoo-palco`). Mobile: wheel `min(80vw, 440px)`, buttons full width.
- [ ] **Step 4:** `node --check` both files; `node --test frontend/tests/*.test.js` still green.
- [ ] **Step 5: Commit** — "Pandoo: palco comum e roleta de figuras".

### Task 5: Menu, lista de jogos e editor

**Files:**
- Create/modify: `frontend/js/views/pandoo.js`
- Modify: `frontend/js/shell.js` (menu items), `frontend/js/app.js` (routes), `frontend/css/pandoo.css` (editor styles)

**Interfaces:**
- Consumes: `/api/pandoo/jogos` (GET list, POST), `/api/pandoo/jogos/<id>` (GET, PUT), `/api/biblioteca/categorias`, `/api/pessoas/organizacao` (for the clinic scene in the preview), Task 1 profiles, Task 2–4 functions, `prepararImagemParaEnvio`, `prepararArquivoParaEnvio`, `renderOrientacaoEnvio`, `lerArquivoBase64`.
- Produces: `viewPandoo(app)`, `viewPandooEditor(app, params)`; routes `#/gestor/pandoo`, `#/gestor/pandoo/novo`, `#/gestor/pandoo/:id` and the same for `profissional`.

- [ ] **Step 1: Menu and routes**
  - `shell.js` `MENUS.gestor`, after Biblioteca: `{ rota: "#/gestor/pandoo", icone: "🎮", label: "Pandoo", modulo: "pandoo" }`; `MENUS.profissional`, after Biblioteca: same with `#/profissional/pandoo`.
  - `app.js`: `rota("/gestor/pandoo", ["gestor"], (app) => viewPandoo(app));`, `rota("/gestor/pandoo/novo", ["gestor"], (app) => viewPandooEditor(app, {}));`, `rota("/gestor/pandoo/:id", ["gestor"], (app, p) => viewPandooEditor(app, p));` + the three `profissional` equivalents. Put `/novo` before `/:id` (check `router.js` matching order).

- [ ] **Step 2: `viewPandoo`**
  - If the module is off (`!modulosHabilitados.includes("pandoo")`): card "O Pandoo ainda não está liberado para a sua clínica. Fale com a Panda Tech para ativar." inside the shell.
  - Else `GET /pandoo/jogos` → grid of cards (🎡 icon by model, title, "N figuras", "atualizado em dd/mm") + top action "+ Novo jogo" → `#/{base}/pandoo/novo`; empty state with the Pandoo panda and "Crie o primeiro jogo da clínica".
  - Card click → `#/{base}/pandoo/{id}`.

- [ ] **Step 3: `viewPandooEditor`** — state `{titulo, descricao, categoria_id, modelo: "roleta", conteudo, regras, cenario}` (new: `conteudoVazioPandoo()`, `REGRAS_PADRAO_PANDOO.roleta`; existing: from `GET /pandoo/jogos/<id>`; 403/404 → toast + back to list). Loads categorias and org in parallel.
  - Layout (two columns, stacks on mobile), like preview v1:
    1. Header: Pandoo mark, title input, "Pré-visualizar", "Salvar jogo".
    2. "1. Escolha o modelo": Roleta active; Quiz, Memória, Associação, Flashcards shown disabled with "em breve".
    3. "2. Figuras da roleta": one row per item — number, thumbnail (button "Escolher imagem" → hidden `<input type="file" accept="image/*">` → `prepararImagemParaEnvio(file, "figura")`, warning toast if `aviso`), word input (maxlength 80), voice controls, ↑/↓ reorder, ✕ remove (disabled at 2 items). Under the list: "+ Adicionar figura" (disabled at 24) and `renderOrientacaoEnvio("figura")`.
    4. "3. Regras": end mode radios ("Quando sair todas as figuras (sem repetir)" / "Depois de [N] giros", N 1–100) + note "…ou antes, no botão 'Finalizar jogo'."; checkboxes "Mostrar a palavra embaixo da figura", "Som de roleta e comemoração", "Ler a palavra em voz alta quando a figura aparecer".
    5. "Cenário": select "Padrão da clínica (…nome…)" + the 4 scenes; small swatches.
    6. "Pasta da Biblioteca": select with the clinic's folders (+ "Sem pasta").
  - Voice controls per item:
    - "🎙️ Gravar" → `navigator.mediaDevices.getUserMedia({audio: true})` → `MediaRecorder` (mimeType `audio/webm;codecs=opus` when supported, else default); button turns into "⏹ Parar (0:12)" with a counter; auto-stop at 30 s; on stop: `blob.size > 600 * 1024` → toast "A gravação passou de 600 KB — grave uma frase mais curta."; else `item.pergunta.audio = await lerArquivoBase64(blob)`; stop all tracks.
    - Errors: no `mediaDevices`/`MediaRecorder` → toast "Seu navegador não permite gravar aqui — envie um arquivo de áudio."; `NotAllowedError` → toast "Sem permissão para usar o microfone. Libere o microfone no navegador ou envie um arquivo."
    - "📎 Enviar áudio" → hidden `<input type="file" accept="audio/*">` → `prepararArquivoParaEnvio(file, "voz")`; `renderOrientacaoEnvio("voz")` shown once under the list.
    - With audio: "▶ Ouvir" (`new Audio(data:…)`) and "🗑 Apagar voz".
  - Re-render the list only (not the whole page) on item changes; keep typed text in state on `input`.
  - "Pré-visualizar": if `problemasDoConteudo` non-empty → toast with the first problem; else `abrirPalcoPandoo({jogo: {...estado, id: estado.id || 0, cenario_efetivo: cenarioEfetivoPandoo(estado.cenario, org)}, modo: "previa"})`.
  - "Salvar jogo": title required (toast "Dê um nome ao jogo."); problems → toast; POST or PUT with `{titulo, descricao, categoria_id, modelo, conteudo, regras, cenario}`; button "Salvando…"; success toast "Jogo salvo! Ele já aparece na Biblioteca." → back to the list; error → toast with the API message.

- [ ] **Step 4:** `node --check` changed files; `node --test` green.
- [ ] **Step 5: Commit** — "Pandoo: menu, lista de jogos e editor".

### Task 6: Biblioteca, seletor da missão e tela de Módulos

**Files:**
- Modify: `frontend/js/views/biblioteca.js` (`renderExercicioCard` ~l.365, `anexarCliquesCard` ~l.343, `renderExercicioCardEscolher` ~l.405, the card rendering in the "+ Novo Exercício" area is unchanged)

- [ ] **Step 1: Card** — when `ex.tipo === "jogo"`: thumbnail area shows "🎮" (large) and a small badge "🎮 Pandoo" next to the existing badges; the media count text becomes "Jogo Pandoo".
- [ ] **Step 2: Click** — in `anexarCliquesCard`, after `const ex = await Api.get(...)`: if `ex.tipo === "jogo"`:
  - `ex.pode_editar` and the module is on → `location.hash = \`#/${base}/pandoo/${ex.id}\`` (`base` = "gestor"/"profissional" from `Sessao.usuario.papel`);
  - otherwise → `const jogo = await Api.get(\`/pandoo/jogos/${ex.id}\`)` and `abrirPalcoPandoo({jogo, modo: "previa"})`.
- [ ] **Step 3: Picker** — `renderExercicioCardEscolher`: same "🎮 Pandoo" badge/icon when `ex.tipo === "jogo"`.
- [ ] **Step 4: Módulos** — nothing to do: since the configurable plans (PR #18) the Pandoo is a normal module and `modulos.js` already shows "Liberado pela Panda Tech" for extras.
- [ ] **Step 5:** `node --check`; commit — "Pandoo: jogos na Biblioteca e no seletor da missão".

### Task 7: Mundo da Criança e prévia da missão do responsável

**Files:**
- Modify: `frontend/js/views/crianca.js` (`viewMissaoCrianca` activity render ~l.134-145, media loading ~l.161-174, daily/weekly buttons ~l.151-153 / `renderProgressoSemanal` ~l.215)
- Modify: `frontend/js/views/responsavel.js` (`abrirPreviaMissao` ~l.179-184)

**Interfaces:**
- Consumes: atividades `exercicio_tipo`, `jogo_jogado`; `GET /pandoo/jogos/<exercicio_id>`; `abrirPalcoPandoo`.

- [ ] **Step 1: Activity card** — for `a.exercicio_tipo === "jogo"` render, instead of the media placeholder, a big button `<button class="botao botao-acento btn-jogar-pandoo" data-exercicio-id data-atividade-id>🎮 Jogar ${escapeHtml(a.titulo)}</button>` and, when `a.jogo_jogado`, a badge "✅ Já jogou${missao.tipo === "semanal" ? " hoje" : ""}" and the button text "🎮 Jogar de novo". Skip `/biblioteca/exercicios/<id>` for game activities in the media loop.
- [ ] **Step 2: Play** — click → `const jogo = await Api.get(\`/pandoo/jogos/${id}\`)` → `abrirPalcoPandoo({jogo, modo: "missao", contexto: {paciente_id: Number(Sessao.pacienteAtivoId), missao_id: missao.id, atividade_id: Number(btn.dataset.atividadeId)}, aoFechar: (r) => { if (r) despachar(); }})` (re-render fetches the updated `jogo_jogado`). Error loading → `Toast.erro(err.message)`.
- [ ] **Step 3: Gate** — `const jogosPendentes = missao.atividades.filter(a => a.exercicio_tipo === "jogo" && !a.jogo_jogado)`; when non-empty, the daily "Concluí essa missão! 🎉" and the weekly "Marquei hoje! 🎉" buttons render `disabled` with, right above them, `<p class="texto-sm" style="text-align:center">Jogue o jogo para liberar 🎮</p>`. (If the API still answers 409 — e.g. stale page — the existing error handling shows the message; keep it.)
- [ ] **Step 4: Prévia do responsável** — in `abrirPreviaMissao`, activities with `exercicio_tipo === "jogo"` show "🎮" as icon and "Jogo Pandoo" as subtitle.
- [ ] **Step 5:** `node --check`; commit — "Pandoo: jogos no Mundo da Criança".

### Task 8: Resultados na ficha do paciente

**Files:**
- Modify: `frontend/js/views/jornada.js` (`renderJornadaConteudoPrincipal` between the Plano card ~l.285 and the Diário card ~l.287; after-render loaders ~l.110)
- Modify: `frontend/css/pandoo.css` (small result styles)

**Interfaces:**
- Consumes: `GET /pandoo/resultados?paciente_id=` → `{partidas, por_jogo}`.

- [ ] **Step 1:** In the main column, between Plano and Diário, only for gestor/profissional: `<div class="cartao" id="card-pandoo" style="display:none;"></div>`.
- [ ] **Step 2:** After render (next to `carregarFichaClinica(...)`): `carregarPandooFicha(pacienteId)`:
  - `GET /pandoo/resultados?paciente_id=`; any error or `partidas.length === 0` → keep hidden;
  - else fill: header "🎮 Pandoo — jogos da criança"; "Últimas partidas" (up to 8): date (`formatarData(p.data_local)`), game title, "⭐ {acertos} · 💪 {a_treinar}", and "encerrado antes" tag when `encerrado_antes`; "Por figura" per game: rows "Rato — 4 de 5" with a small progress bar (`width: conseguiu/total %`), sorted by lowest rate first (what needs practice on top).
  - All text escaped.
- [ ] **Step 3:** `node --check`; commit — "Pandoo: resultados na ficha do paciente".

### Task 9: Cenário do Pandoo em Configurações

**Files:**
- Modify: `frontend/js/views/financeiro.js` (`viewConfiguracoes`: new card after the "Dados institucionais" card; listeners after render)

- [ ] **Step 1: Configurações** — only when `pandoo` is in `Sessao.usuario.organizacao.modulos_habilitados`: card "🎮 Cenário do Pandoo" with:
  - 4 choices (cards with swatch + name, reuse the `.wl-cena` look: 🎋 Bambuzal, 🐠 Fundo do mar, 🚀 Espaço, 🖼️ Imagem da clínica) — current `org.pandoo_cenario_padrao` (`org` = `GET /pessoas/organizacao`, already loaded by the view);
  - "Imagem da clínica": preview (`<img>` of `org.pandoo_cenario_imagem` when present), button "Enviar imagem" (hidden input) → `prepararImagemParaEnvio(file, "cenario")` → `tom = await tomDaImagemBase64(b64)` (identidade_clinica.js) → shows "Fundo claro detectado — os textos do jogo ficam escuros" / "Fundo escuro detectado — os textos do jogo ficam brancos"; `renderOrientacaoEnvio("cenario")` under the button; note "É a mesma imagem usada no fundo do Mundo da Criança e no fundo da clínica.";
  - "Salvar cenário" → `PUT /pessoas/organizacao` with `{pandoo_cenario_padrao}` plus `{pandoo_cenario_imagem, pandoo_cenario_tom}` only when a new image was chosen; choosing "Imagem da clínica" without any image → toast "Envie a imagem da clínica primeiro."; success → refresh the session with `/auth/me` (same pattern as the other cards) and `Toast.sucesso("Cenário salvo!")`.
- [ ] **Step 2:** (the Admin switch of the original plan is gone — the Pandoo is released in Admin → Clínicas → "Módulos da clínica").
- [ ] **Step 3:** `node --check`; commit — "Pandoo: cenário da clínica em Configurações".

### Task 10: Verificação no navegador, docs e PR

- [ ] **Step 1: Setup** — fresh seed (`rm -f encanto.db && seed.py`), start `app.py`; Playwright via `uv run --with playwright --with pillow`; remember the login rate limit (10/5 min per IP — reuse tokens, restart the server if needed) and that the CSP blocks `wait_for_function` string eval (poll with `page.evaluate` in Python).
- [ ] **Step 2: Scenario** (1366×768 unless noted), generating PNG figures with Pillow and a fake microphone (Chromium flags `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream`):
  1. Admin libera o Pandoo para a clínica em "Módulos da clínica" (extra) → gestor recarrega → menu "🎮 Pandoo" aparece; Módulos mostra "Liberado pela Panda Tech".
  2. Profissional cria "Roleta do /R/" com 3 figuras (upload), palavra, uma voz gravada (fake mic, ~2 s) e uma voz por arquivo; tenta salvar com 1 figura → aviso; salva com 3 → aparece na lista e na Biblioteca com o selo 🎮; clicar no card da Biblioteca abre o editor.
  3. Pré-visualizar: gira, a figura aparece, placar atualiza, "Conseguiu" toca confete, "Finalizar jogo" mostra o resumo "Prévia — nada foi salvo."; nenhum POST em `/pandoo/resultados` (monitor requests).
  4. Gestor cria missão **diária** e uma **semanal** para o paciente com o jogo (seletor mostra 🎮).
  5. Responsável entra no modo criança → missão diária: botão de concluir desabilitado com "Jogue o jogo para liberar 🎮"; joga até o fim ("todas") → resumo "Prontinho!…" → volta → botão liberado → conclui (celebração).
  6. Semanal: "Finalizar jogo" antes de girar → resultado salvo com 0 rodadas → "Marquei hoje!" liberado.
  7. Falha ao salvar: bloquear `**/api/pandoo/resultados` (route.abort) → resumo mostra erro + "Tentar de novo"; desbloquear → "Tentar de novo" salva.
  8. Ficha do paciente (profissional): card "🎮 Pandoo" com as partidas e "por figura".
  9. Configurações: escolher "Imagem da clínica" sem imagem → aviso; enviar imagem clara (Pillow, branca) → "Fundo claro detectado"; salvar; abrir a prévia do jogo → `data-tom="claro"` no palco; trocar por imagem escura → `data-tom="escuro"`.
  10. Celular 390×844: palco e editor utilizáveis (sem rolagem horizontal), screenshots.
  11. Console sem erros em todas as telas.
  Fix what fails (TDD for pure logic), one commit per fix.
- [ ] **Step 3:** Full backend suite (sanity, nothing changed there) + `node --test frontend/tests/*.test.js`.
- [ ] **Step 4: CLAUDE.md** — section 5 new item `p) Pandoo fase 1 — tela (25/09/2026, PR B)` (files, flows, how to add a new game: file in `js/pandoo/jogos/` + `registrarJogo` + backend `MODELOS`), section 6 bullet on the stage contract, section 7 remove "PR B (tela)" pending and the three production-migration items (White Label, fundo da clínica, recursos dos planos — the user confirmed on 26/09/2026 that all ran) and add "Pandoo fase 2: quiz, memória, associação, flashcards (motor de arrastar com toque)", section 8 rows for the new files.
- [ ] **Step 5: PR** — push, PR (summary, screenshots description, no schema/no manual step, how to release the module: Admin → clínica → Pandoo), CI green → merge (auto-merge rule: no schema/billing/production data), `git pull`, `node --test` again. Tell the user: deploy = `git pull` + restart (+ Ctrl+F5); then the Admin turns Pandoo on for the clinic.
