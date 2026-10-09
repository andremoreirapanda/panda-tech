// Procedimentos (09/10/2026): conversão de valores em reais.
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const p = require("../js/procedimentos_util.js");

test("reaisParaCentavos: formatos brasileiros e números", () => {
    assert.equal(p.reaisParaCentavos("230,00"), 23000);
    assert.equal(p.reaisParaCentavos("1.230,50"), 123050);
    assert.equal(p.reaisParaCentavos("230"), 23000);
    assert.equal(p.reaisParaCentavos("230,5"), 23050);
    assert.equal(p.reaisParaCentavos("R$ 15"), 1500);
    assert.equal(p.reaisParaCentavos(" 0 "), 0);
    assert.equal(p.reaisParaCentavos("100.000,00"), 10000000);
    assert.equal(p.reaisParaCentavos(230.5), 23050);
});

test("reaisParaCentavos: inválidos", () => {
    for (const v of ["-1", "abc", "", null, undefined, "100.000,01", "1,234", "12.34.5"]) {
        assert.equal(p.reaisParaCentavos(v), null, String(v));
    }
});

test("centavosParaReais", () => {
    assert.equal(p.centavosParaReais(123050), "1.230,50");
    assert.equal(p.centavosParaReais(0), "0,00");
    assert.equal(p.centavosParaReais(5), "0,05");
    assert.equal(p.centavosParaReais(10000000), "100.000,00");
});
