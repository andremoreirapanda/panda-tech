// Busca de paciente no agendamento (09/10/2026).
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const b = require("../js/busca_paciente.js");

const pacientes = [
    { id: 1, nome: "Benício Alonso de Lima" }, { id: 2, nome: "Benício de Castro Pereira" },
    { id: 3, nome: "Ana Beatriz" }, { id: 4, nome: "BENICIO Lorenzo" }, { id: 5, nome: "Alice Benévolo" },
    { id: 6, nome: "Rubens Beni" }, { id: 7, nome: "Bento" }, { id: 8, nome: "Benício 8" }, { id: 9, nome: "Benício 9" },
    { id: 10, nome: "Benício 10" }, { id: 11, nome: "Benício 11" },
];

test("menos de 3 letras não busca", () => {
    assert.deepEqual(b.filtrarPacientes(pacientes, "be"), []);
    assert.deepEqual(b.filtrarPacientes(pacientes, "  b "), []);
});

test("ignora acentos e maiúsculas e limita a 8", () => {
    const r = b.filtrarPacientes(pacientes, "beni");
    assert.equal(r.length, 8);
    assert.ok(r.every(p => /beni/i.test(b.normalizarBusca(p.nome))));
    assert.ok(r.some(p => p.id === 4));
});

test("quem começa com o termo vem primeiro, depois ordem alfabética", () => {
    const r = b.filtrarPacientes(pacientes, "bén", 20).map(p => p.nome);
    assert.equal(r[r.length - 2], "Alice Benévolo");          // contém no meio do nome
    assert.equal(r[r.length - 1], "Rubens Beni");
    assert.ok(r.indexOf("Bento") < r.indexOf("Alice Benévolo"));
});

test("várias palavras: todas precisam aparecer", () => {
    assert.deepEqual(b.filtrarPacientes(pacientes, "beni lima").map(p => p.id), [1]);
    assert.deepEqual(b.filtrarPacientes(pacientes, "xyz"), []);
});

test("normalizarBusca", () => {
    assert.equal(b.normalizarBusca("  Benício  ÇÃO "), "benicio cao");
});
