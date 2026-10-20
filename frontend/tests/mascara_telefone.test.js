// Máscara de telefone (util.js) aceita fixo e celular (20/10/2026): antes só
// o formato de celular "(11) 9 8888-7777" passava, e o "Telefone da clínica"
// em Configurações não salvava com um número fixo.
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ctx = { console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, "../js/util.js"), "utf8"), ctx);
const tel = vm.runInContext("MASCARAS_CAMPO.telefone", ctx);
const valido = (v) => new RegExp(`^(?:${tel.pattern})$`).test(v);

test("fixo (10 dígitos) é formatado e aceito", () => {
    assert.equal(tel.formatar("1133334444"), "(11) 3333-4444");
    assert.ok(valido("(11) 3333-4444"));
});

test("celular (11 dígitos) continua no formato de sempre", () => {
    assert.equal(tel.formatar("11988887777"), "(11) 9 8888-7777");
    assert.ok(valido("(11) 9 8888-7777"));
});

test("formatação enquanto digita", () => {
    assert.equal(tel.formatar("1"), "(1");
    assert.equal(tel.formatar("11"), "(11");
    assert.equal(tel.formatar("113"), "(11) 3");
    assert.equal(tel.formatar("113333"), "(11) 3333");
    assert.equal(tel.formatar("1133334"), "(11) 3333-4");
    assert.equal(tel.formatar("(11) 9 8888-7777"), "(11) 9 8888-7777");
    assert.equal(tel.formatar("(11) 3333-4444"), "(11) 3333-4444");
});

test("número incompleto continua inválido", () => {
    assert.ok(!valido("(11) 3333-444"));
    assert.ok(!valido("(11) 9 8888-777"));
    assert.ok(!valido("(11) 98888-7777"));
});
