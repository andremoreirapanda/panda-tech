// Texto legível sobre o fundo escuro da clínica (25/11/2026).
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const c = require("../js/contraste_fundo.js");

test("superficieOpaca: cor transparente ou quase não é superfície", () => {
    assert.equal(c.superficieOpaca("rgba(0, 0, 0, 0)", "none"), false);
    assert.equal(c.superficieOpaca("transparent", "none"), false);
    assert.equal(c.superficieOpaca("rgba(255, 255, 255, 0.16)", "none"), false);  // botão-texto claro sobre o fundo
    assert.equal(c.superficieOpaca("", "none"), false);
});

test("superficieOpaca: cor cheia ou quase cheia é superfície", () => {
    assert.equal(c.superficieOpaca("rgb(255, 255, 255)", "none"), true);
    assert.equal(c.superficieOpaca("rgba(255, 255, 255, 0.9)", "none"), true);
    assert.equal(c.superficieOpaca("rgba(91, 79, 233, 0.6)", "none"), true);
    assert.equal(c.superficieOpaca("rgb(255 255 255 / 0.95)", "none"), true);
});

test("superficieOpaca: degradê ou imagem de fundo conta como superfície", () => {
    assert.equal(c.superficieOpaca("rgba(0, 0, 0, 0)", "linear-gradient(160deg, rgb(237, 235, 252), rgb(250, 247, 242))"), true);
    assert.equal(c.superficieOpaca("rgba(0, 0, 0, 0)", 'url("/api/publico/clinica/x/cenario")'), true);
});

test("temTextoProprio: só texto visível direto no elemento", () => {
    const no = (filhos) => ({ childNodes: filhos });
    const txt = (t) => ({ nodeType: 3, textContent: t });
    const el = { nodeType: 1, textContent: "dentro" };
    assert.equal(c.temTextoProprio(no([txt("  "), el])), false);
    assert.equal(c.temTextoProprio(no([txt("\n"), txt("←")])), true);
    assert.equal(c.temTextoProprio(no([txt("Missões desta semana")])), true);
});
