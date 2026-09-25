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

test("foto: aceita JPG/PNG/WebP até 15 MB, recusa HEIC com dica e vídeo", () => {
    assert.deepEqual(e.validarEntradaEnvio(arq("a.jpg", "image/jpeg", 12 * MB), "foto"), { ok: true, formato: "jpeg" });
    const grande = e.validarEntradaEnvio(arq("a.jpg", "image/jpeg", 16 * MB), "foto");
    assert.equal(grande.ok, false);
    assert.match(grande.erro, /15 MB/);
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
    assert.match(e.PERFIS_ENVIO.foto.texto, /15 MB/);
    assert.match(e.PERFIS_ENVIO.logo.texto, /1024 × 512 px/);
});

// Revisão final (25/09/2026): a dica de link do YouTube só faz sentido na
// Biblioteca — no Diário e no chat não há onde colar link.
test("vídeo grande: dica do YouTube só na mídia da Biblioteca", () => {
    const anexo = e.validarEntradaEnvio(arq("v.mp4", "video/mp4", 5 * MB), "anexo");
    assert.equal(anexo.ok, false);
    assert.doesNotMatch(anexo.erro, /YouTube/);
    assert.match(e.validarEntradaEnvio(arq("v.mp4", "video/mp4", 5 * MB), "midia").erro, /YouTube/);
});

// Revisão final (25/09/2026): foto de celular em pé vem com a rotação no
// EXIF; navegadores antigos ignoravam isso no createImageBitmap sem a opção,
// e a foto era salva deitada.
test("decodificarImagem pede a rotação do EXIF ao createImageBitmap", async () => {
    let opcoes = null;
    globalThis.createImageBitmap = async (_arquivo, o) => { opcoes = o; return { width: 10, height: 20, close() {} }; };
    try {
        const r = await e.decodificarImagem({ name: "a.jpg", type: "image/jpeg" });
        assert.deepEqual(opcoes, { imageOrientation: "from-image" });
        assert.deepEqual([r.largura, r.altura], [10, 20]);
    } finally {
        delete globalThis.createImageBitmap;
    }
});

// GIF de volta na Biblioteca, no Diário e no chat (pedido do usuário,
// 25/09/2026): vai sem redução (o canvas congelaria a animação), com o
// limite de 4 MB dos outros arquivos. Foto de perfil e logo seguem sem GIF.
test("GIF: aceito como arquivo (sem redução) na mídia e no anexo, até 4 MB", () => {
    assert.deepEqual(e.validarEntradaEnvio(arq("a.gif", "image/gif", 3 * MB), "midia"), { ok: true, formato: "gif" });
    assert.equal(e.validarEntradaEnvio(arq("a.gif", "image/gif", 3 * MB), "anexo").ok, true);
    const grande = e.validarEntradaEnvio(arq("a.gif", "image/gif", 5 * MB), "anexo");
    assert.equal(grande.ok, false);
    assert.match(grande.erro, /4 MB/);
    assert.equal(e.validarEntradaEnvio(arq("a.gif", "image/gif"), "foto").ok, false);
    assert.match(e.PERFIS_ENVIO.midia.texto, /GIF/);
    assert.match(e.PERFIS_ENVIO.anexo.texto, /GIF/);
});

test("categoriaEnvio agrupa GIF com as imagens (Diário/chat esperam 'imagem')", () => {
    for (const f of ["jpeg", "png", "webp", "gif"]) assert.equal(e.categoriaEnvio(f), "imagem");
    assert.equal(e.categoriaEnvio("video"), "video");
    assert.equal(e.categoriaEnvio("audio"), "audio");
    assert.equal(e.categoriaEnvio("pdf"), "pdf");
});
