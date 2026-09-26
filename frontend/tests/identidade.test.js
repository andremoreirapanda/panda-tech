// White Label completo (25/09/2026): helpers puros da identidade da clínica (util.js).
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ctx = { console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, "../js/util.js"), "utf8"), ctx);

test("fonte da criança: família e URL do Google Fonts só quando precisa", () => {
    assert.equal(ctx.fonteCrianca("fredoka").url, null);
    assert.match(ctx.fonteCrianca("baloo").url, /^https:\/\/fonts\.googleapis\.com\/css2\?family=Baloo\+2/);
    assert.match(ctx.fonteCrianca("escolar").familia, /Patrick Hand/);
    assert.match(ctx.fonteCrianca("nunito").familia, /Nunito/);
    assert.equal(ctx.fonteCrianca("comic").familia, ctx.fonteCrianca("fredoka").familia);
    assert.equal(ctx.fonteCrianca(undefined).url, null);
});

test("links de identidade: padrão e da clínica", () => {
    const padrao = ctx.linksIdentidade({ app_nome: "Panda Tech", white_label_ativo: false });
    assert.equal(padrao.titulo, "Panda Tech — Plataforma de Desenvolvimento Infantil");
    assert.match(padrao.favicon, /^data:image\/svg\+xml/);
    assert.equal(padrao.manifest, null);
    assert.equal(ctx.linksIdentidade(null).manifest, null);
    const wl = ctx.linksIdentidade({ app_nome: "Encantar", white_label_ativo: true, tem_icone: true, endereco_login: "enc", versao_imagens: "v1" });
    assert.equal(wl.titulo, "Encantar");
    assert.equal(wl.favicon, "/api/publico/clinica/enc/icone?v=v1");
    assert.equal(wl.manifest, "/api/publico/clinica/enc/manifest.webmanifest");
    const semIcone = ctx.linksIdentidade({ app_nome: "Encantar", white_label_ativo: true, endereco_login: "enc" });
    assert.match(semIcone.favicon, /^data:image\/svg\+xml/);
    const ruim = ctx.linksIdentidade({ app_nome: "X", white_label_ativo: true, tem_icone: true, endereco_login: "a\"b" });
    assert.equal(ruim.manifest, null);
    assert.match(ruim.favicon, /^data:/);
});

test("emojiMascote nunca mostra a palavra 'clinica'", () => {
    assert.equal(ctx.emojiMascote("🦊", {}), "🦊");
    assert.equal(ctx.emojiMascote("clinica", { logo_emoji: "🌈" }), "🌈");
    assert.equal(ctx.emojiMascote("clinica", {}), "🐻");
    assert.equal(ctx.emojiMascote("clinica", null), "🐻");
});

test("urlMascoteClinica só com imagem e endereço válido", () => {
    assert.equal(ctx.urlMascoteClinica({ tem_mascote_imagem: true, endereco_login: "enc", versao_imagens: "v2" }), "/api/publico/clinica/enc/mascote?v=v2");
    assert.equal(ctx.urlMascoteClinica({ tem_mascote_imagem: false, endereco_login: "enc" }), null);
    assert.equal(ctx.urlMascoteClinica({ tem_mascote_imagem: true, endereco_login: "<x>" }), null);
    assert.equal(ctx.urlMascoteClinica(null), null);
});

// Revisão final (25/09/2026): o logo aparece na tela de login pública.
test("renderLogoClinica escapa o emoji do logo", () => {
    const html = ctx.renderLogoClinica({ logo_emoji: '<img src=x onerror="alert(1)">' }, 30);
    assert.ok(!html.includes("<img src=x"), html);
});
