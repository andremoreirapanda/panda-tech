// Financeiro (07/11/2026): rótulos e validações puras.
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const f = require("../js/financeiro_util.js");

test("rotuloStatusCobranca", () => {
    assert.equal(f.rotuloStatusCobranca("rascunho", true), "Em andamento");
    assert.equal(f.rotuloStatusCobranca("rascunho", false), "Para conferir");
    assert.equal(f.rotuloStatusCobranca("pendente", false), "Em aberto");
    assert.equal(f.rotuloStatusCobranca("parcial", false), "Pago em parte");
    assert.equal(f.rotuloStatusCobranca("pago", false), "Pago");
    assert.equal(f.rotuloStatusCobranca("vencido", false), "Vencido");
    assert.equal(f.rotuloStatusCobranca("cancelado", false), "Cancelado");
});

test("rotuloForma", () => {
    const esperado = { pix: "Pix", dinheiro: "Dinheiro", cartao_credito: "Cartão de crédito", cartao_debito: "Cartão de débito",
        cartao: "Cartão", transferencia: "Transferência", boleto: "Boleto" };
    for (const [k, v] of Object.entries(esperado)) assert.equal(f.rotuloForma(k), v);
});

test("rotuloAcordo", () => {
    assert.equal(f.rotuloAcordo({ tipo: "avulsa", ciclo: "consulta" }), "Por sessão · a cada consulta");
    assert.equal(f.rotuloAcordo({ tipo: "avulsa", ciclo: "quinzenal" }), "Por sessão · a cada 15 dias");
    assert.equal(f.rotuloAcordo({ tipo: "avulsa", ciclo: "mensal" }), "Por sessão · mensal");
    assert.equal(f.rotuloAcordo({ tipo: "mensalidade", valor_centavos: 60000, dia_vencimento: 10 }), "Mensalidade · R$ 600,00 · vence dia 10");
    assert.equal(f.rotuloAcordo({ tipo: "pacote", sessoes_total: 10, valor_centavos: 100000, parcelas: 3 }), "Pacote · 10 sessões · R$ 1.000,00 em 3x");
});

test("lerValorReais", () => {
    assert.equal(f.lerValorReais("1.234,56"), 123456);
    assert.equal(f.lerValorReais("1234,5"), 123450);
    assert.equal(f.lerValorReais("230"), 23000);
    assert.equal(f.lerValorReais("R$ 50,00"), 5000);
    assert.equal(f.lerValorReais("abc"), null);
    assert.equal(f.lerValorReais(""), null);
    assert.equal(f.lerValorReais("1,234"), null);
});

test("validarAcordo", () => {
    assert.equal(f.validarAcordo({}), "Escolha o tipo do acordo.");
    assert.equal(f.validarAcordo({ tipo: "avulsa" }), "Escolha o ciclo da cobrança (por consulta, quinzenal ou mensal).");
    assert.equal(f.validarAcordo({ tipo: "avulsa", ciclo: "mensal" }), null);
    assert.equal(f.validarAcordo({ tipo: "mensalidade", valor_centavos: 0, dia_vencimento: 10 }), "Informe o valor da mensalidade.");
    assert.equal(f.validarAcordo({ tipo: "mensalidade", valor_centavos: 5000, dia_vencimento: 29 }), "O dia de vencimento deve ficar entre 1 e 28.");
    assert.equal(f.validarAcordo({ tipo: "mensalidade", valor_centavos: 5000, dia_vencimento: 10 }), null);
    assert.equal(f.validarAcordo({ tipo: "avulsa", ciclo: "mensal", inicio: "2026-05-10", fim: "2026-05-01" }), "O fim não pode ser antes do início.");
    assert.equal(f.validarAcordo({ tipo: "avulsa", ciclo: "mensal", vence_dias: 61 }), "Dias para vencer deve ficar entre 0 e 60.");
    const pacote = { tipo: "pacote", sessoes_total: 10, valor_centavos: 100000, parcelas: 3, primeiro_vencimento: "2026-12-10" };
    assert.equal(f.validarAcordo(pacote), null);
    assert.equal(f.validarAcordo({ ...pacote, sessoes_total: 201 }), "Informe a quantidade de sessões (1 a 200).");
    assert.equal(f.validarAcordo({ ...pacote, parcelas: 25 }), "As parcelas devem ficar entre 1 e 24.");
    assert.equal(f.validarAcordo({ ...pacote, primeiro_vencimento: "" }), "Informe o primeiro vencimento.");
    assert.equal(f.validarAcordo({ tipo: "avulsa", ciclo: "mensal", especialidade: "x".repeat(61) }), "Especialidade com mais de 60 caracteres.");
});
