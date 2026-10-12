// Trava dos pais no Mundo da Criança (12/10/2026).
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const t = require("../js/trava_adulto.js");

test("gerarDesafioAdulto: soma com três opções, uma certa", () => {
    let i = 0;
    const sequencia = [0.0, 0.99, 0.5, 0.2, 0.8, 0.4, 0.6];
    const rand = () => sequencia[i++ % sequencia.length];
    const d = t.gerarDesafioAdulto(rand);
    assert.match(d.pergunta, /^Quanto é \d \+ \d\?$/);
    const [x, y] = d.pergunta.match(/\d/g).map(Number);
    assert.equal(d.resposta, x + y);
    assert.equal(d.opcoes.length, 3);
    assert.equal(new Set(d.opcoes).size, 3);
    assert.ok(d.opcoes.includes(d.resposta));
    assert.ok(x >= 3 && x <= 9 && y >= 3 && y <= 9);
});

test("gerarDesafioAdulto: muitas rodadas sem repetir opções nem negativas", () => {
    for (let k = 0; k < 200; k++) {
        const d = t.gerarDesafioAdulto(Math.random);
        assert.equal(new Set(d.opcoes).size, 3);
        assert.ok(d.opcoes.every(n => n > 0));
        assert.ok(d.opcoes.includes(d.resposta));
    }
});
