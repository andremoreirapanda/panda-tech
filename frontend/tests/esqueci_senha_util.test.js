// Tela de confirmação do "Esqueci minha senha" (13/10/2026).
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const u = require("../js/esqueci_senha_util.js");

test("por e-mail: mostra o e-mail digitado, a validade e as dicas", () => {
    const c = u.confirmacaoEsqueciSenha("ana@familia.com", { canal: "email", validade_minutos: 60, mensagem: "x" });
    assert.equal(c.porEmail, true);
    assert.equal(c.titulo, "Confira seu e-mail");
    assert.match(c.texto, /ana@familia\.com/);
    assert.match(c.texto, /1 hora/);
    assert.equal(c.dicas.length, 3);
    assert.match(c.dicas[0], /spam/);
});

test("validade em minutos quando não é hora cheia; sem validade, sem frase", () => {
    assert.match(u.confirmacaoEsqueciSenha("a@b.co", { canal: "email", validade_minutos: 30 }).texto, /30 minutos/);
    assert.doesNotMatch(u.confirmacaoEsqueciSenha("a@b.co", { canal: "email" }).texto, /vale por/);
});

test("sem e-mail no servidor: orienta a pedir à clínica, com o texto do servidor", () => {
    const c = u.confirmacaoEsqueciSenha("ana@familia.com", { canal: "clinica", mensagem: "Peça ao gestor." });
    assert.equal(c.porEmail, false);
    assert.equal(c.texto, "Peça ao gestor.");
    assert.deepEqual(c.dicas, []);
});

test("24 horas aparece como '24 horas'", () => {
    assert.match(u.confirmacaoEsqueciSenha("a@b.co", { canal: "email", validade_minutos: 1440 }).texto, /O link vale por 24 horas\./);
});
