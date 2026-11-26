// Ditado por voz (IA fase 1): funções puras do componente.
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const d = require("../js/ditado.js");

test("inserirNoCursor: no fim, põe espaço antes e seleciona o trecho novo", () => {
    assert.deepEqual(d.inserirNoCursor("Hoje", 4, 4, "ele falou"), { valor: "Hoje ele falou", inicio: 5, fim: 14 });
});
test("inserirNoCursor: antes de pontuação não põe espaço depois", () => {
    assert.deepEqual(d.inserirNoCursor("A.", 1, 1, "b"), { valor: "A b.", inicio: 2, fim: 3 });
});
test("inserirNoCursor: antes de palavra põe espaço depois", () => {
    assert.deepEqual(d.inserirNoCursor("AB", 1, 1, "x"), { valor: "A x B", inicio: 2, fim: 3 });
});
test("inserirNoCursor: campo vazio e depois de quebra de linha ficam sem espaço", () => {
    assert.deepEqual(d.inserirNoCursor("", 0, 0, "oi"), { valor: "oi", inicio: 0, fim: 2 });
    assert.deepEqual(d.inserirNoCursor("a\n", 2, 2, "oi"), { valor: "a\noi", inicio: 2, fim: 4 });
});
test("inserirNoCursor: substitui a seleção", () => {
    assert.deepEqual(d.inserirNoCursor("abc def", 4, 7, "xyz"), { valor: "abc xyz", inicio: 4, fim: 7 });
});
test("inserirNoCursor: posições fora do texto ou invertidas são ajustadas", () => {
    assert.equal(d.inserirNoCursor("ab", 99, 99, "c").valor, "ab c");
    assert.equal(d.inserirNoCursor("ab", 2, 0, "c").valor, "c");
});
test("formatarTempo", () => {
    assert.equal(d.formatarTempo(65), "1:05");
    assert.equal(d.formatarTempo(0), "0:00");
    assert.equal(d.formatarTempo(300), "5:00");
});
test("textoMinutos", () => {
    assert.equal(d.textoMinutos(1), "1 minuto");
    assert.equal(d.textoMinutos(0), "0 minutos");
    assert.equal(d.textoMinutos(12), "12 minutos");
});
