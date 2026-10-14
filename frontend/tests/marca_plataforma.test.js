// Logo da plataforma (14/10/2026).
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const m = require("../js/marca_plataforma.js");

test("sem versão, sem logo (cada tela mantém o visual de antes)", () => {
    assert.equal(m.htmlLogoPlataforma("", 40), "");
    assert.equal(m.htmlLogoPlataforma(null, 40), "");
});

test("com versão: imagem no endereço público com ?v=, altura e largura máximas", () => {
    const h = m.htmlLogoPlataforma("a1b2c3d4e5", 40);
    assert.match(h, /<img src="\/api\/publico\/plataforma\/logo\?v=a1b2c3d4e5"/);
    assert.match(h, /alt="PandaUp"/);
    assert.match(h, /max-height:40px/);
    assert.match(h, /max-width:240px/);
});

test("versão estranha não quebra o HTML", () => {
    const h = m.htmlLogoPlataforma('x" onerror="alert(1)', 40);
    assert.doesNotMatch(h, /onerror=/);
});
