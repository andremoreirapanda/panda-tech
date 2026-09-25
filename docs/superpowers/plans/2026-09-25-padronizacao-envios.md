# Padronização dos envios de arquivo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every file-upload field shows format/ideal size/max size before upload, and images are reduced in the browser so common phone photos stop failing.

**Architecture:** One new front-end file `frontend/js/envio_arquivos.js` with upload profiles (`PERFIS_ENVIO`), pure validation/dimension helpers (tested with `node --test`) and two canvas-based functions (`prepararImagemParaEnvio`, `prepararArquivoParaEnvio`) plus `renderOrientacaoEnvio`. The 11 upload handlers replace their copy-pasted "2 MB check + FileReader" block with these calls. No backend change.

**Tech Stack:** Vanilla JS (globals, no build), Canvas API, `node --test` (Node 22+ in CI), Playwright (Python via `uv`) for the browser check.

**Spec:** `docs/superpowers/specs/2026-09-25-padronizacao-envios-design.md`

## Global Constraints

- Texts exactly as in the spec table (Portuguese, with the 📐/🎬/🎧/📄 icons).
- Formats: JPG, PNG, WebP for images; MP4/WebM video; MP3/M4A audio; PDF. HEIC is refused with the iPhone hint text from the spec.
- Limits: foto 5 MB in → side ≤ 400 px, ≤ 300 KB out; logo 5 MB in → side ≤ 1024 px keeping transparency, ≤ 1,5 MB out; mídia/anexo image in ≤ 15 MB → side ≤ 1920 px, ≤ 3,5 MB out; mídia/anexo video/audio/PDF ≤ 4 MB (unchanged).
- Small-image warning (non-blocking) below: foto 200 px, logo 128 px, mídia/anexo 256 px (smaller side).
- Keep existing broad `accept` attributes (`image/*` etc.).
- No backend/schema change; CSP unchanged (canvas + `data:` already allowed).
- Branch `padronizacao-envios`; run backend suite + `node --test frontend/tests/*.test.js` before PR; auto-merge on green (no schema). Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Comments follow the codebase style (explain the why, cite "25/09/2026").

## Review Focus

1. **Transparent PNG logo** → must stay transparent after reduction (no black/white box). Covered by `formatoSaidaImagem` tests (Task 1) and the browser check (Task 5).
2. **Photo already small and light** (e.g., 300×300 JPEG 40 KB) → not upscaled, not recompressed into something bigger; sent essentially as-is. Covered in Task 1 (`dimensoesReduzidas` never upscales) and Task 2 (skip recompress when already within limits).
3. **Large phone photo 4000×3000, 6–12 MB** → for mídia/anexo accepted and reduced; for foto/logo above 5 MB refused with the orientation text. Covered in Task 1 (`validarEntradaEnvio`) and Task 5.
4. **File with wrong/empty `type`** (some Android pickers send `""`) → detected by extension; unknown → friendly refusal, never a crash. Covered in Task 1.
5. **Multiple files in the Diário** where one fails → the others are still added, one toast per failed file. Covered in Task 4 code + Task 5 check.

---

### Task 1: `envio_arquivos.js` — perfis e funções puras

**Files:**
- Create: `frontend/js/envio_arquivos.js`
- Create: `frontend/tests/envio_arquivos.test.js`
- Modify: `frontend/index.html` (script tag right after `/js/util.js`)
- Modify: `frontend/css/components.css` (append `.orientacao-envio`)

**Interfaces:**
- Produces (globals; `module.exports` in Node):
  - `PERFIS_ENVIO` — `{foto, logo, midia, anexo, planilha}`, each `{texto, maxImagemMB, maxOutrosMB, ladoMax, limiteSaidaKB, manterTransparencia, ladoMinAviso, tiposAceitos: string[]}`
  - `formatoDoArquivo(file: {name, type}) -> "jpeg"|"png"|"webp"|"gif"|"heic"|"video"|"audio"|"pdf"|"planilha"|"outro"`
  - `validarEntradaEnvio(file: {name, type, size}, perfilNome) -> {ok: true, formato} | {ok: false, erro: string}`
  - `dimensoesReduzidas(largura, altura, ladoMax) -> {largura, altura}` (never upscales, integers)
  - `formatoSaidaImagem(perfilNome, formatoEntrada) -> "image/png"|"image/webp"|"image/jpeg"`
  - `avisoImagemPequena(largura, altura, perfilNome) -> string|null`
  - `nomeComExtensao(nome, mime) -> string`

- [ ] **Step 1: Write the failing tests** — `frontend/tests/envio_arquivos.test.js`:

```js
// Padronização dos envios (25/09/2026) — funções puras de envio_arquivos.js.
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const e = require("../js/envio_arquivos.js");

const MB = 1024 * 1024;
const arq = (name, type, size = 100 * 1024) => ({ name, type, size });

test("formatoDoArquivo usa o type e, sem ele, a extensão", () => {
    assert.equal(e.formatoDoArquivo(arq("a.jpg", "image/jpeg")), "jpeg");
    assert.equal(e.formatoDoArquivo(arq("a.png", "image/png")), "png");
    assert.equal(e.formatoDoArquivo(arq("a.webp", "image/webp")), "webp");
    assert.equal(e.formatoDoArquivo(arq("IMG_1.HEIC", "")), "heic");
    assert.equal(e.formatoDoArquivo(arq("IMG_1.heic", "image/heic")), "heic");
    assert.equal(e.formatoDoArquivo(arq("foto.JPEG", "")), "jpeg");
    assert.equal(e.formatoDoArquivo(arq("v.mp4", "video/mp4")), "video");
    assert.equal(e.formatoDoArquivo(arq("s.m4a", "")), "audio");
    assert.equal(e.formatoDoArquivo(arq("d.pdf", "application/pdf")), "pdf");
    assert.equal(e.formatoDoArquivo(arq("p.xlsx", "")), "planilha");
    assert.equal(e.formatoDoArquivo(arq("x.exe", "")), "outro");
});

test("foto: aceita JPG/PNG/WebP até 5 MB, recusa HEIC com dica e vídeo", () => {
    assert.deepEqual(e.validarEntradaEnvio(arq("a.jpg", "image/jpeg", 4 * MB), "foto"), { ok: true, formato: "jpeg" });
    const grande = e.validarEntradaEnvio(arq("a.jpg", "image/jpeg", 6 * MB), "foto");
    assert.equal(grande.ok, false);
    assert.match(grande.erro, /5 MB/);
    assert.match(grande.erro, /400 × 400/);
    const heic = e.validarEntradaEnvio(arq("IMG.HEIC", "image/heic"), "foto");
    assert.equal(heic.ok, false);
    assert.match(heic.erro, /HEIC/);
    assert.match(heic.erro, /Salvar como JPEG/);
    assert.equal(e.validarEntradaEnvio(arq("v.mp4", "video/mp4"), "foto").ok, false);
});

test("mídia: imagem até 15 MB (é reduzida), vídeo/áudio/PDF até 4 MB", () => {
    assert.equal(e.validarEntradaEnvio(arq("a.jpg", "image/jpeg", 12 * MB), "midia").ok, true);
    assert.equal(e.validarEntradaEnvio(arq("a.jpg", "image/jpeg", 16 * MB), "midia").ok, false);
    assert.equal(e.validarEntradaEnvio(arq("v.mp4", "video/mp4", 3 * MB), "midia").ok, true);
    const v = e.validarEntradaEnvio(arq("v.mp4", "video/mp4", 5 * MB), "midia");
    assert.equal(v.ok, false);
    assert.match(v.erro, /YouTube/);
    assert.equal(e.validarEntradaEnvio(arq("d.pdf", "application/pdf", 1 * MB), "midia").ok, true);
});

test("anexo (diário/chat): sem PDF", () => {
    assert.equal(e.validarEntradaEnvio(arq("d.pdf", "application/pdf"), "anexo").ok, false);
    assert.equal(e.validarEntradaEnvio(arq("s.mp3", "audio/mpeg"), "anexo").ok, true);
});

test("arquivo desconhecido é recusado com a orientação, sem quebrar", () => {
    const r = e.validarEntradaEnvio(arq("x.exe", ""), "foto");
    assert.equal(r.ok, false);
    assert.match(r.erro, /JPG, PNG ou WebP/);
});

test("dimensoesReduzidas nunca aumenta e mantém a proporção", () => {
    assert.deepEqual(e.dimensoesReduzidas(4000, 3000, 400), { largura: 400, altura: 300 });
    assert.deepEqual(e.dimensoesReduzidas(1000, 3000, 400), { largura: 133, altura: 400 });
    assert.deepEqual(e.dimensoesReduzidas(300, 200, 400), { largura: 300, altura: 200 });
});

test("formatoSaidaImagem mantém transparência só no logo", () => {
    assert.equal(e.formatoSaidaImagem("logo", "png"), "image/png");
    assert.equal(e.formatoSaidaImagem("logo", "webp"), "image/webp");
    assert.equal(e.formatoSaidaImagem("logo", "jpeg"), "image/jpeg");
    assert.equal(e.formatoSaidaImagem("foto", "png"), "image/jpeg");
    assert.equal(e.formatoSaidaImagem("midia", "webp"), "image/jpeg");
});

test("avisoImagemPequena usa o lado menor e o mínimo de cada perfil", () => {
    assert.equal(e.avisoImagemPequena(150, 400, "foto") !== null, true);
    assert.equal(e.avisoImagemPequena(400, 400, "foto"), null);
    assert.equal(e.avisoImagemPequena(100, 300, "logo") !== null, true);
    assert.equal(e.avisoImagemPequena(300, 250, "midia") !== null, true);
});

test("nomeComExtensao troca a extensão pela do formato final", () => {
    assert.equal(e.nomeComExtensao("IMG_2033.PNG", "image/jpeg"), "IMG_2033.jpg");
    assert.equal(e.nomeComExtensao("logo", "image/png"), "logo.png");
    assert.equal(e.nomeComExtensao("a.b.webp", "image/webp"), "a.b.webp");
});

test("todo perfil tem o texto de orientação", () => {
    for (const nome of ["foto", "logo", "midia", "anexo", "planilha"]) {
        assert.ok(e.PERFIS_ENVIO[nome].texto.length > 10, nome);
    }
    assert.match(e.PERFIS_ENVIO.foto.texto, /400 × 400 px/);
    assert.match(e.PERFIS_ENVIO.logo.texto, /1024 × 512 px/);
});
```

- [ ] **Step 2: Run to verify it fails**

Run (repo root): `node --test frontend/tests/envio_arquivos.test.js`
Expected: FAIL — `Cannot find module '../js/envio_arquivos.js'`.

- [ ] **Step 3: Implement** — `frontend/js/envio_arquivos.js` (pure part; Task 2 appends the canvas functions to the same file):

```js
// ============================================================================
// envio_arquivos.js — padronização dos envios de arquivo (25/09/2026)
//
// Cada campo de envio mostra, antes do envio, formato + dimensão ideal +
// tamanho máximo, e imagens são reduzidas no navegador (antes, foto de
// celular acima de 2 MB era simplesmente recusada). Parte pura (sem DOM)
// testada em frontend/tests/envio_arquivos.test.js; a parte com canvas
// fica no fim do arquivo.
// ============================================================================

const _MB = 1024 * 1024;
const _TIPOS_IMAGEM = ["jpeg", "png", "webp"];
const _DICA_HEIC = "Essa foto está em HEIC (formato do iPhone). Envie em JPG, PNG ou WebP — no iPhone, Compartilhar → Salvar como JPEG resolve.";

const PERFIS_ENVIO = {
    foto: {
        texto: "📐 JPG, PNG ou WebP · ideal 400 × 400 px (quadrada) · até 5 MB",
        tiposAceitos: _TIPOS_IMAGEM, maxImagemMB: 5, maxOutrosMB: 0,
        ladoMax: 400, limiteSaidaKB: 300, manterTransparencia: false, ladoMinAviso: 200,
    },
    logo: {
        texto: "📐 PNG com fundo transparente (ou JPG/WebP) · ideal 512 × 512 px (quadrado) ou 1024 × 512 px (horizontal) · até 5 MB",
        tiposAceitos: _TIPOS_IMAGEM, maxImagemMB: 5, maxOutrosMB: 0,
        ladoMax: 1024, limiteSaidaKB: 1536, manterTransparencia: true, ladoMinAviso: 128,
    },
    midia: {
        texto: "📐 Imagem: JPG, PNG ou WebP · ideal 1280 × 720 px · 🎬 Vídeo: MP4 ou WebM · 🎧 Áudio: MP3 ou M4A · 📄 PDF · até 4 MB (vídeos maiores: use link do YouTube)",
        tiposAceitos: [..._TIPOS_IMAGEM, "video", "audio", "pdf"], maxImagemMB: 15, maxOutrosMB: 4,
        ladoMax: 1920, limiteSaidaKB: 3584, manterTransparencia: false, ladoMinAviso: 256,
    },
    anexo: {
        texto: "📐 Foto: JPG, PNG ou WebP · 🎬 Vídeo: MP4 ou WebM · 🎧 Áudio: MP3 ou M4A · até 4 MB",
        tiposAceitos: [..._TIPOS_IMAGEM, "video", "audio"], maxImagemMB: 15, maxOutrosMB: 4,
        ladoMax: 1920, limiteSaidaKB: 3584, manterTransparencia: false, ladoMinAviso: 256,
    },
    planilha: {
        texto: "📄 Planilha XLSX ou CSV · use o modelo desta tela",
        tiposAceitos: ["planilha"], maxImagemMB: 0, maxOutrosMB: 10,
        ladoMax: 0, limiteSaidaKB: 0, manterTransparencia: false, ladoMinAviso: 0,
    },
};

const _EXTENSOES = {
    jpg: "jpeg", jpeg: "jpeg", jfif: "jpeg", png: "png", webp: "webp", gif: "gif",
    heic: "heic", heif: "heic",
    mp4: "video", m4v: "video", mov: "video", webm: "video",
    mp3: "audio", m4a: "audio", aac: "audio", ogg: "audio", oga: "audio", wav: "audio", opus: "audio",
    pdf: "pdf", xlsx: "planilha", xlsm: "planilha", csv: "planilha",
};

// Alguns seletores de arquivo do Android mandam `type` vazio — por isso a
// extensão é a segunda fonte.
function formatoDoArquivo(file) {
    const tipo = String((file && file.type) || "").toLowerCase();
    if (tipo === "image/jpeg" || tipo === "image/jpg") return "jpeg";
    if (tipo === "image/png") return "png";
    if (tipo === "image/webp") return "webp";
    if (tipo === "image/gif") return "gif";
    if (tipo === "image/heic" || tipo === "image/heif") return "heic";
    if (tipo.startsWith("video/")) return "video";
    if (tipo.startsWith("audio/")) return "audio";
    if (tipo === "application/pdf") return "pdf";
    const ext = String((file && file.name) || "").split(".").pop().toLowerCase();
    return _EXTENSOES[ext] || "outro";
}

function _textoLimite(perfil) {
    return `Confira a orientação do campo: ${perfil.texto.replace(/^📐\s*|^📄\s*/, "")}`;
}

function validarEntradaEnvio(file, perfilNome) {
    const perfil = PERFIS_ENVIO[perfilNome];
    const formato = formatoDoArquivo(file);
    if (formato === "heic") return { ok: false, erro: _DICA_HEIC };
    if (!perfil.tiposAceitos.includes(formato)) {
        return { ok: false, erro: `"${file.name}" não é um formato aceito aqui. ${_textoLimite(perfil)}` };
    }
    const ehImagem = _TIPOS_IMAGEM.includes(formato);
    const maxMB = ehImagem ? perfil.maxImagemMB : perfil.maxOutrosMB;
    if (file.size > maxMB * _MB) {
        const dicaVideo = formato === "video" ? " Para vídeos maiores, use um link do YouTube." : "";
        return { ok: false, erro: `"${file.name}" passa de ${maxMB} MB.${dicaVideo} ${_textoLimite(perfil)}` };
    }
    return { ok: true, formato };
}

function dimensoesReduzidas(largura, altura, ladoMax) {
    const escala = Math.min(1, ladoMax / Math.max(largura, altura));
    return { largura: Math.round(largura * escala), altura: Math.round(altura * escala) };
}

// Só o logo guarda transparência (PNG/WebP); o resto vira JPEG, bem menor.
function formatoSaidaImagem(perfilNome, formatoEntrada) {
    if (PERFIS_ENVIO[perfilNome].manterTransparencia) {
        if (formatoEntrada === "png") return "image/png";
        if (formatoEntrada === "webp") return "image/webp";
    }
    return "image/jpeg";
}

function avisoImagemPequena(largura, altura, perfilNome) {
    const minimo = PERFIS_ENVIO[perfilNome].ladoMinAviso;
    if (!minimo || Math.min(largura, altura) >= minimo) return null;
    return `A imagem tem ${largura} × ${altura} px e pode ficar borrada — mas pode usar, se quiser.`;
}

function nomeComExtensao(nome, mime) {
    const ext = { "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp" }[mime];
    const base = String(nome || "imagem").replace(/\.[^.]+$/, "");
    return `${base}.${ext}`;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        PERFIS_ENVIO, formatoDoArquivo, validarEntradaEnvio, dimensoesReduzidas,
        formatoSaidaImagem, avisoImagemPequena, nomeComExtensao,
    };
}
```

Note: in `nomeComExtensao("logo", ...)` the regex finds no extension and keeps "logo" → "logo.png"; for "a.b.webp" → "a.b.webp". Matches the tests.

In `frontend/index.html`, add after `<script src="/js/util.js"></script>`:
```html
<script src="/js/envio_arquivos.js"></script>
```

Append to `frontend/css/components.css`:
```css
/* ---------------------------------------------------------------- Orientação de envio de arquivo (25/09/2026) */
.orientacao-envio { font-size: 11.5px; color: var(--cor-tinta-suave); margin-top: 6px; line-height: 1.45; }
```

- [ ] **Step 4: Run to verify it passes**

Run: `node --test frontend/tests/*.test.js`
Expected: all pass (existing 18 + 10 new = 28).

- [ ] **Step 5: Commit**

```bash
git add frontend/js/envio_arquivos.js frontend/tests/envio_arquivos.test.js frontend/index.html frontend/css/components.css
git commit -m "Envios: perfis e validação comuns (formato, tamanho, dimensão)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: Redução no navegador e orientação na tela

**Files:**
- Modify: `frontend/js/envio_arquivos.js` (append, before the `module.exports` block)

**Interfaces:**
- Consumes: Task 1 functions.
- Produces:
  - `renderOrientacaoEnvio(perfilNome) -> string` (HTML `<p class="orientacao-envio">…</p>`, text escaped)
  - `lerArquivoBase64(file) -> Promise<string>` (base64 without the `data:` prefix)
  - `prepararImagemParaEnvio(file, perfilNome) -> Promise<{base64, nome, mime, largura, altura, aviso}>` — throws `Error` with the friendly message
  - `prepararArquivoParaEnvio(file, perfilNome) -> Promise<{base64, nome, mime, formato, aviso}>` — images via the above, others validated + read as-is

No Node test: these use `document`/canvas. Verified in the browser in Task 5 (automated Playwright script).

- [ ] **Step 1: Implement**

```js
function renderOrientacaoEnvio(perfilNome) {
    return `<p class="orientacao-envio">${escapeHtml(PERFIS_ENVIO[perfilNome].texto)}</p>`;
}

function lerArquivoBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = () => reject(new Error(`Não foi possível ler "${file.name}".`));
        reader.readAsDataURL(file);
    });
}

function _decodificarImagem(file) {
    return new Promise((resolve, reject) => {
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
        img.onerror = () => { URL.revokeObjectURL(url); reject(new Error(`Não foi possível abrir "${file.name}" como imagem.`)); };
        img.src = url;
    });
}

function _canvasParaBlob(canvas, mime, qualidade) {
    return new Promise(resolve => canvas.toBlob(resolve, mime, qualidade));
}

// Reduz para o lado máximo do perfil e comprime até caber no limite. Imagem
// que já está pequena e leve no formato certo segue como veio (não adianta
// recomprimir e às vezes até aumenta).
async function prepararImagemParaEnvio(file, perfilNome) {
    const perfil = PERFIS_ENVIO[perfilNome];
    const validacao = validarEntradaEnvio(file, perfilNome);
    if (!validacao.ok) throw new Error(validacao.erro);
    const img = await _decodificarImagem(file);
    const { largura, altura } = dimensoesReduzidas(img.naturalWidth, img.naturalHeight, perfil.ladoMax);
    const aviso = avisoImagemPequena(img.naturalWidth, img.naturalHeight, perfilNome);
    const mime = formatoSaidaImagem(perfilNome, validacao.formato);
    const limiteBytes = perfil.limiteSaidaKB * 1024;

    const jaServe = largura === img.naturalWidth && file.size <= limiteBytes
        && ((mime === "image/jpeg" && validacao.formato === "jpeg") || (mime !== "image/jpeg" && `image/${validacao.formato}` === mime));
    if (jaServe) {
        return { base64: await lerArquivoBase64(file), nome: file.name, mime, largura, altura, aviso };
    }

    const canvas = document.createElement("canvas");
    canvas.width = largura;
    canvas.height = altura;
    const ctx = canvas.getContext("2d");
    if (mime === "image/jpeg") { ctx.fillStyle = "#FFFFFF"; ctx.fillRect(0, 0, largura, altura); } // JPEG não tem transparência: fundo branco em vez de preto
    ctx.drawImage(img, 0, 0, largura, altura);

    const tentativas = mime === "image/png"
        ? [["image/png", undefined], ["image/webp", 0.9], ["image/webp", 0.75]]
        : [[mime, 0.85], [mime, 0.72], [mime, 0.6]];
    for (const [formato, qualidade] of tentativas) {
        const blob = await _canvasParaBlob(canvas, formato, qualidade);
        if (blob && blob.size <= limiteBytes) {
            const base64 = await lerArquivoBase64(blob);
            return { base64, nome: nomeComExtensao(file.name, formato), mime: formato, largura, altura, aviso };
        }
    }
    throw new Error(`Não conseguimos deixar "${file.name}" leve o bastante. ${PERFIS_ENVIO[perfilNome].texto}`);
}

async function prepararArquivoParaEnvio(file, perfilNome) {
    const validacao = validarEntradaEnvio(file, perfilNome);
    if (!validacao.ok) throw new Error(validacao.erro);
    if (["jpeg", "png", "webp"].includes(validacao.formato)) {
        const r = await prepararImagemParaEnvio(file, perfilNome);
        return { ...r, formato: "imagem" };
    }
    return { base64: await lerArquivoBase64(file), nome: file.name, mime: file.type, formato: validacao.formato, aviso: null };
}
```

Add the four new names to the `module.exports` object (harmless in Node; keeps the file's export list complete).

- [ ] **Step 2: Verify syntax and that Node tests still load the file**

Run: `node --check frontend/js/envio_arquivos.js && node --test frontend/tests/*.test.js`
Expected: no syntax error; 28 pass (the DOM functions are only defined, not called, when loaded in Node).

- [ ] **Step 3: Commit**

```bash
git add frontend/js/envio_arquivos.js
git commit -m "Envios: redução de imagem no navegador e texto de orientação" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: Fotos de perfil, foto do paciente, contato e logo

**Files:**
- Modify: `frontend/js/views/admin.js` (~l.639 HTML, ~l.695-712 handler)
- Modify: `frontend/js/views/financeiro.js` (contato ~l.337 / ~l.520; logo ~l.413-415 / ~l.603-616; perfil ~l.685 / ~l.706-723)
- Modify: `frontend/js/views/pacientes.js` (~l.459 / ~l.526-537)
- Modify: `frontend/js/views/responsavel.js` (perfil ~l.254 / ~l.296-313; foto do filho ~l.282 / ~l.335-351)

**Interfaces:**
- Consumes: `renderOrientacaoEnvio("foto"|"logo")`, `prepararImagemParaEnvio(file, "foto"|"logo")` from Task 2.

- [ ] **Step 1: Orientation text in the HTML**

Right after each of these buttons, add `${renderOrientacaoEnvio("foto")}`:
- `admin.js`: after `<button … id="btn-trocar-avatar-plat" …>📷 Trocar foto</button>`
- `financeiro.js`: after `id="btn-trocar-avatar-contato"` button and after `id="btn-trocar-avatar"` button
- `pacientes.js`: after `id="btn-escolher-avatar-prof"` button
- `responsavel.js`: after `id="btn-trocar-avatar"` button, and after the `<input type="file" id="input-foto-filho" …>` (the per-child buttons are in a list; one line under the list is enough)

In `financeiro.js`, replace the logo hint paragraph (the one starting "Envie uma imagem (até 2MB) ou deixe em branco…") with:

```html
            ${renderOrientacaoEnvio("logo")}
            <p class="texto-xs texto-suave" style="margin-top:2px;">Ou deixe em branco para usar um emoji simples abaixo. O logo aparece inteiro, sem cortes.</p>
```

- [ ] **Step 2: Replace the 7 handlers**

Each handler has this shape today:

```js
        const file = e.target.files[0];
        if (!file) return;
        if (file.size > 2 * 1024 * 1024) { Toast.erro("A foto precisa ter até 2MB."); e.target.value = ""; return; }
        const base64 = await new Promise((resolve, reject) => { … readAsDataURL(file); });
```

Replace the size check + `FileReader` promise with:

```js
        let preparada;
        try {
            preparada = await prepararImagemParaEnvio(file, "foto");
        } catch (err) { Toast.erro(err.message); e.target.value = ""; return; }
        if (preparada.aviso) Toast.info(preparada.aviso);
        const base64 = preparada.base64;
```

and use `preparada.nome` wherever the handler used `file.name` (`avatar_nome`, `foto_nome`, `logoNomeNovo`, `{ base64, nome: … }`). For the logo handler use `"logo"` instead of `"foto"` and keep the "(até 2MB)" message out (the new error texts come from the profile). Keep the `if (!file || !filhoAlvoId) return;` guard in `responsavel.js` foto do filho.

Confirm `Toast.info` exists (`grep -n "info" frontend/js/toast.js`); if the name differs, use the existing non-error toast function.

- [ ] **Step 3: Check syntax and leftovers**

Run: `node --check` on the four files; then `grep -rn "2 \* 1024 \* 1024" frontend/js/views/` → no results in these handlers.

- [ ] **Step 4: Commit**

```bash
git add frontend/js/views/admin.js frontend/js/views/financeiro.js frontend/js/views/pacientes.js frontend/js/views/responsavel.js
git commit -m "Envios: fotos e logo reduzidos no navegador, com orientação no campo" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: Biblioteca, Diário, chat e importação

**Files:**
- Modify: `frontend/js/views/biblioteca.js` (~l.740-741 HTML; ~l.769-791 handler)
- Modify: `frontend/js/views/diario.js` (~l.94-95 HTML; ~l.131-150 handler)
- Modify: `frontend/js/views/comunicacao.js` (~l.38-39 button title; ~l.74-92 handler)
- Modify: `frontend/js/views/importacao.js` (~l.248-249 HTML)

**Interfaces:**
- Consumes: `renderOrientacaoEnvio`, `prepararArquivoParaEnvio(file, "midia"|"anexo")`, `PERFIS_ENVIO`.

- [ ] **Step 1: Biblioteca**

HTML: replace `<label class="texto-xs" style="margin-top:4px;">Adicionar arquivo (até ${LIMITE_ARQUIVO_BIBLIOTECA_MB}MB)</label>` with `<label class="texto-xs" style="margin-top:4px;">Adicionar arquivo</label>` and add `${renderOrientacaoEnvio("midia")}` right after the `<input type="file" id="ex-nova-midia-arquivo" …>`.

Handler: replace the size check and the `dataUrl` `FileReader` block with:

```js
        let preparado;
        try {
            preparado = await prepararArquivoParaEnvio(file, "midia");
        } catch (err) { Toast.erro(err.message); return; }
        if (preparado.aviso) Toast.info(preparado.aviso);
        const dataUrl = `data:${preparado.mime};base64,${preparado.base64}`;
```

and in `midiasAtuais.push`, use `arquivo_nome: preparado.nome, arquivo_base64: preparado.base64`. Keep `tipoDeArquivoCliente(file)` and the thumbnails (they now run on the reduced `dataUrl`). `LIMITE_ARQUIVO_BIBLIOTECA_MB` stays only if still referenced elsewhere; otherwise delete it.

- [ ] **Step 2: Diário**

HTML: label becomes `📎 Anexos (opcional — foto, áudio ou vídeo curto da sessão)` and add `${renderOrientacaoEnvio("anexo")}` after the input.

Handler (keeps the per-file loop so one bad file doesn't block the others):

```js
        for (const file of Array.from(e.target.files)) {
            let preparado;
            try {
                preparado = await prepararArquivoParaEnvio(file, "anexo");
            } catch (err) { Toast.erro(err.message); continue; }
            if (preparado.aviso) Toast.info(preparado.aviso);
            const tipo = preparado.formato === "imagem" ? "foto" : preparado.formato; // "video" | "audio"
            anexosPendentes.push({ tipo, nome_arquivo: preparado.nome, conteudo_base64: preparado.base64 });
        }
```

Delete `LIMITE_ANEXO_MB` if no longer used.

- [ ] **Step 3: Chat**

Button: `title="Enviar foto, áudio ou vídeo — ${escapeHtml(PERFIS_ENVIO.anexo.texto)}"`.

Handler: replace size check, type detection and `FileReader` with:

```js
        let preparado;
        try {
            preparado = await prepararArquivoParaEnvio(file, "anexo");
        } catch (err) { Toast.erro(err.message); e.target.value = ""; return; }
        const tipo = preparado.formato; // "imagem" | "video" | "audio" — mesmos valores que a rota do chat já espera
        const base64 = preparado.base64;
```

and send `anexo_nome: preparado.nome`. Delete `LIMITE_ANEXO_CHAT_MB` if unused.

- [ ] **Step 4: Importação**

Add `${renderOrientacaoEnvio("planilha")}` right after `<input type="file" id="input-arquivo-importacao" …>`. No handler change.

- [ ] **Step 5: Check and commit**

Run: `node --check` on the four files; `node --test frontend/tests/*.test.js` → 28 pass.

```bash
git add frontend/js/views/biblioteca.js frontend/js/views/diario.js frontend/js/views/comunicacao.js frontend/js/views/importacao.js
git commit -m "Envios: Biblioteca, Diário, chat e importação com orientação e imagens reduzidas" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 5: Verificação no navegador, docs e PR

**Files:**
- Modify: `CLAUDE.md` (section 5 new item, section 6 bullet, section 8 row)
- Scratch only: Playwright script + generated test images in the session scratchpad

- [ ] **Step 1: Test files** (Python + Pillow via `uv run --with pillow`): `grande.jpg` 4000×3000 (~6 MB, noisy so it doesn't compress), `media.jpg` 4000×3000 (~3 MB), `pequena.jpg` 150×150, `logo.png` 1200×600 with transparent background, `foto.heic` (any bytes, name/type HEIC), `video_grande.mp4` (5 MB of bytes with an `ftyp` header).

- [ ] **Step 2: Browser checks** — server with fresh seed (`rm -f encanto.db && seed.py`, then `app.py`), Playwright at 1366×768, using `page.set_input_files` on the hidden inputs:
1. Perfil do gestor: `media.jpg` → success toast; stored `avatar_base64` decodes to ≤ 400 px and ≤ 300 KB.
2. Perfil: `grande.jpg` (6 MB) → error toast mentioning "5 MB" and "400 × 400"; nothing saved.
3. Perfil: `pequena.jpg` → saved + "pode ficar borrada" toast.
4. Perfil: `foto.heic` → HEIC hint toast.
5. Logo: `logo.png` → saved; decoded image still has alpha (corner pixel alpha = 0) and side ≤ 1024.
6. Biblioteca: `grande.jpg` → accepted, stored ≤ 1920 px; `video_grande.mp4` → error mentioning YouTube.
7. Diário: select `media.jpg` + `video_grande.mp4` together → the photo is listed, one error toast for the video.
8. Orientation text visible under: perfil, contato, logo, Biblioteca, Diário, importação; chat button `title` contains it.
9. Console without errors.

Fix anything found (TDD for pure-function bugs), one commit per fix.

- [ ] **Step 3: Full test runs**

Backend: from `backend/`, full `pytest -q` → all pass (no backend change; sanity). Front: `node --test frontend/tests/*.test.js` → 28 pass.

- [ ] **Step 4: CLAUDE.md**

- Section 5, new item `n) Padronização dos envios de arquivo (25/09/2026)`: `envio_arquivos.js` (`PERFIS_ENVIO`, `prepararImagemParaEnvio`, `renderOrientacaoEnvio`), fields covered, images reduced in the browser, backend limits unchanged, test counts.
- Section 6 bullet: "Novo campo de envio? Use `prepararArquivoParaEnvio`/`renderOrientacaoEnvio` com um perfil de `PERFIS_ENVIO` (crie um perfil novo se precisar) — nunca `FileReader` + limite solto."
- Section 8 row: "Envio de arquivos (orientação, redução de imagem) | `frontend/js/envio_arquivos.js`".

Commit.

- [ ] **Step 5: PR and merge**

Push `padronizacao-envios`, open PR (summary, no schema, no manual step, test counts, Claude Code line), wait for CI, merge with `gh pr merge --merge --delete-branch` if green (auto-merge rule: no schema/billing/production data). Then `git checkout main && git pull` and rerun `node --test`. Deploy note for the user: only `git pull` + `touch tmp/restart.txt`; browsers may need Ctrl+F5 (new JS file).
