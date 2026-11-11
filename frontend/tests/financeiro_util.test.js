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
    assert.equal(f.lerValorReais("1.234"), 123400);
    assert.equal(f.lerValorReais("1.234.567,89"), 123456789);
    assert.equal(f.lerValorReais("0,5"), 50);
    assert.equal(f.lerValorReais("1234.56"), null);
    assert.equal(f.lerValorReais("-5"), null);
    assert.equal(f.lerValorReais(" 50 "), 5000);
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

test("rotuloEspecialidadeAcordo mostra '*' como todas", () => {
    assert.equal(f.rotuloEspecialidadeAcordo("*"), "Todas as especialidades");
    assert.equal(f.rotuloEspecialidadeAcordo("Fonoaudiologia"), "Fonoaudiologia");
    assert.equal(f.rotuloEspecialidadeAcordo(""), "Geral");
});

test("rotuloSessaoPacote", () => {
    assert.equal(f.rotuloSessaoPacote(1, 10), "Sessão 1 de 10");
    assert.equal(f.rotuloSessaoPacote(null, null), "");
    assert.equal(f.rotuloSessaoPacote(undefined, 10), "");
    assert.equal(f.rotuloSessaoPacote(0, 10), "");
});

test("resumoCobrancaFamilia: saldo no parcial, desconto, Pix só se falta pagar", () => {
    const parcial = f.resumoCobrancaFamilia({ status: "parcial", valor_centavos: 20000, desconto_centavos: 2000,
        a_pagar_centavos: 18000, pago_centavos: 5000, saldo_centavos: 13000 });
    assert.equal(parcial.valorPrincipal, 13000);
    assert.equal(parcial.rotuloPrincipal, "Falta pagar");
    assert.equal(parcial.temDesconto, true);
    assert.equal(parcial.mostrarPix, true);
    const aberta = f.resumoCobrancaFamilia({ status: "pendente", valor_centavos: 20000, desconto_centavos: 0,
        a_pagar_centavos: 20000, pago_centavos: 0, saldo_centavos: 20000 });
    assert.equal(aberta.valorPrincipal, 20000);
    assert.equal(aberta.rotuloPrincipal, "");
    assert.equal(aberta.temDesconto, false);
    assert.equal(aberta.mostrarPix, true);
    assert.equal(f.resumoCobrancaFamilia({ status: "vencido", valor_centavos: 100, a_pagar_centavos: 100, saldo_centavos: 100 }).mostrarPix, true);
    const paga = f.resumoCobrancaFamilia({ status: "pago", valor_centavos: 100, a_pagar_centavos: 100, pago_centavos: 100, saldo_centavos: 0 });
    assert.equal(paga.mostrarPix, false);
    assert.equal(paga.valorPrincipal, 100);
    assert.equal(f.resumoCobrancaFamilia({ status: "pendente", valor_centavos: 100, a_pagar_centavos: 0, saldo_centavos: 0 }).mostrarPix, false);
});

test("resumoSessoesMarcadas soma só as marcadas", () => {
    const sessoes = [
        { consulta_id: 1, valor_centavos: 15000 },
        { consulta_id: 2, procedimento_valor_centavos: 20000 },
        { consulta_id: 3, valor_centavos: 0 },
    ];
    assert.deepEqual(f.resumoSessoesMarcadas(sessoes, []), { quantidade: 0, valor_centavos: 0 });
    assert.deepEqual(f.resumoSessoesMarcadas(sessoes, [1, 2]), { quantidade: 2, valor_centavos: 35000 });
    assert.deepEqual(f.resumoSessoesMarcadas(sessoes, [3]), { quantidade: 1, valor_centavos: 0 });
});

test("textoSessoesMarcadas", () => {
    assert.equal(f.textoSessoesMarcadas({ quantidade: 0, valor_centavos: 0 }), "Nenhuma sessão marcada.");
    assert.equal(f.textoSessoesMarcadas({ quantidade: 1, valor_centavos: 15000 }), "1 sessão marcada · soma R$ 150,00");
    assert.equal(f.textoSessoesMarcadas({ quantidade: 2, valor_centavos: 35000 }), "2 sessões marcadas · soma R$ 350,00");
});

test("limiteEncerrarAcordo: hoje, ou o fim que já passou", () => {
    assert.equal(f.limiteEncerrarAcordo("2026-11-08", null), "2026-11-08");
    assert.equal(f.limiteEncerrarAcordo("2026-11-08", "2026-12-31"), "2026-11-08");
    assert.equal(f.limiteEncerrarAcordo("2026-11-08", "2026-10-31"), "2026-10-31");
});

test("podeDarDesconto: só cobrança em aberto", () => {
    for (const s of ["pendente", "parcial", "vencido"]) assert.equal(f.podeDarDesconto({ status: s }), true);
    for (const s of ["rascunho", "pago", "cancelado"]) assert.equal(f.podeDarDesconto({ status: s }), false);
});

test("valorPorProcedimento: preço × sessões, null se faltar dado", () => {
    assert.equal(f.valorPorProcedimento(25000, 4), 100000);
    assert.equal(f.valorPorProcedimento(25000, 1), 25000);
    assert.equal(f.valorPorProcedimento(null, 4), null);
    assert.equal(f.valorPorProcedimento(0, 4), null);
    assert.equal(f.valorPorProcedimento(25000, 0), null);
    assert.equal(f.valorPorProcedimento(25000, 2.5), null);
    assert.equal(f.valorPorProcedimento(25000, ""), null);
});

const CAIXA = {
    de: "2026-11-09", ate: "2026-11-09",
    recebimentos: [{ pago_em: "2026-11-09 14:05:00", paciente_nome: "Paciente A", cobranca_id: 7, cobranca_descricao: "Sessão 09/11",
                     forma: "pix", valor_centavos: 12500, recebido_por: "Ana", estornado: false }],
    estornos: [{ estornado_em: "2026-11-09 16:00:00", pago_em: "2026-11-01 10:00:00", paciente_nome: "Paciente B", cobranca_id: 8,
                 cobranca_descricao: "Pacote", forma: "dinheiro", valor_centavos: 2500, recebido_por: "Bia", motivo: "Duplicado" }],
    por_forma: [{ forma: "pix", recebido_centavos: 12500, estornado_centavos: 0, liquido_centavos: 12500 },
                { forma: "dinheiro", recebido_centavos: 0, estornado_centavos: 2500, liquido_centavos: -2500 }],
    por_quem: [{ recebido_por: "Ana", recebido_centavos: 12500, estornado_centavos: 0, liquido_centavos: 12500 },
               { recebido_por: "Bia", recebido_centavos: 0, estornado_centavos: 2500, liquido_centavos: -2500 }],
    totais: { recebido_centavos: 12500, estornado_centavos: 2500, liquido_centavos: 10000, quantidade: 1 },
};

test("planilhasCaixa: cabeçalhos e valores em reais", () => {
    const p = f.planilhasCaixa(CAIXA);
    assert.deepEqual(p.Recebimentos[0], ["Data/hora", "Paciente", "Cobrança", "Forma", "Quem recebeu", "Situação", "Valor (R$)"]);
    assert.deepEqual(p.Recebimentos[1], ["09/11/2026 14:05", "Paciente A", "Sessão 09/11", "Pix", "Ana", "Recebido", 125]);
    assert.deepEqual(p.Estornos[0], ["Data do estorno", "Paciente", "Cobrança", "Forma", "Quem recebeu", "Motivo", "Valor (R$)"]);
    assert.deepEqual(p.Estornos[1], ["09/11/2026 16:00", "Paciente B", "Pacote", "Dinheiro", "Bia", "Duplicado", 25]);
    assert.ok(p.Resumo.some(l => l[0] === "Líquido" && l[1] === 100));
    assert.ok(p.Resumo.some(l => l[0] === "Recebido" && l[1] === 125));
    assert.ok(p.Resumo.some(l => l[0] === "Dinheiro" && l[3] === -25));
});

test("planilhasCaixa: sem movimento", () => {
    const vazio = { de: "2026-11-09", ate: "2026-11-09", recebimentos: [], estornos: [], por_forma: [], por_quem: [],
                    totais: { recebido_centavos: 0, estornado_centavos: 0, liquido_centavos: 0, quantidade: 0 } };
    const p = f.planilhasCaixa(vazio);
    assert.equal(p.Recebimentos.length, 1);
    assert.equal(p.Estornos.length, 1);
    assert.ok(p.Resumo.some(l => l[0] === "Líquido" && l[1] === 0));
});

test("periodoAtalhoCaixa: hoje, ontem e este mês", () => {
    assert.deepEqual(f.periodoAtalhoCaixa("hoje", "2026-11-09"), { de: "2026-11-09", ate: "2026-11-09" });
    assert.deepEqual(f.periodoAtalhoCaixa("ontem", "2026-11-01"), { de: "2026-10-31", ate: "2026-10-31" });
    assert.deepEqual(f.periodoAtalhoCaixa("mes", "2026-11-09"), { de: "2026-11-01", ate: "2026-11-09" });
});
