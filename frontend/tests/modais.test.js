// Pop-ups de preenchimento (26/09/2026): rascunho ao fechar pelo X.
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const m = require("../js/modais.js");

test("valores dos campos: texto, select e caixas de marcar", () => {
    const campos = [{ type: "text", value: "Oi" }, { type: "select-one", value: "b" }, { type: "checkbox", checked: true }];
    assert.deepEqual(m.valoresDosCampos(campos), ["Oi", "b", true]);
});

test("só guarda rascunho quando algo mudou", () => {
    assert.equal(m.valoresMudaram(["", "15"], ["", "15"]), false);
    assert.equal(m.valoresMudaram(["", "15"], ["Missão", "15"]), true);
});

test("chave do rascunho: tela (sem query) + título do pop-up", () => {
    const modal = { querySelector: () => ({ textContent: "  Nova missão " }) };
    assert.equal(m.chaveDoModal(modal, "#/gestor/paciente/2?aba=x"), "#/gestor/paciente/2|Nova missão");
    assert.equal(m.chaveDoModal({ querySelector: () => null }, "#/a"), "#/a|");
});
