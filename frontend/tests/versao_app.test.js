// Aviso de nova versão do app (09/10/2026).
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const v = require("../js/versao_app.js");

test("deveConferirVersao: respeita o intervalo mínimo", () => {
    assert.equal(v.deveConferirVersao(1000, null, 60000), true);
    assert.equal(v.deveConferirVersao(30000, 1000, 60000), false);
    assert.equal(v.deveConferirVersao(61000, 1000, 60000), true);
});

test("haNovaVersao: só quando as duas existem e são diferentes", () => {
    assert.equal(v.haNovaVersao("aaaa", "bbbb"), true);
    assert.equal(v.haNovaVersao("aaaa", "aaaa"), false);
    assert.equal(v.haNovaVersao("", "bbbb"), false);       // página sem a <meta> (servida sem versão)
    assert.equal(v.haNovaVersao("aaaa", undefined), false); // falha ao consultar
});
