// Repetição avançada (09/10/2026): regra montada a partir do formulário.
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const r = require("../js/repeticao_util.js");

const base = () => ({
    frequencia: "semanal", aCada: 3, dataInicial: "2026-10-12",
    dias: { 1: { marcado: true, inicio: "09:00", fim: "09:50" }, 3: { marcado: true, inicio: "14:00", fim: "15:00" },
            5: { marcado: false, inicio: "", fim: "" } },
    mensalPor: "dia_mes", meses: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    fimTipo: "nenhum", dataLimite: "", quantidade: "",
});

test("semanal com dois dias e sem fim", () => {
    assert.deepEqual(r.montarRegraRepeticao(base()), { regra: {
        frequencia: "semanal", dias: { 1: { inicio: "09:00", fim: "09:50" }, 3: { inicio: "14:00", fim: "15:00" } }, meses: null } });
});

test("a cada N semanas, meses escolhidos, quantidade e data limite", () => {
    const e = { ...base(), frequencia: "semanas", meses: [10, 12], fimTipo: "quantidade", quantidade: "8" };
    const { regra } = r.montarRegraRepeticao(e);
    assert.equal(regra.a_cada, 3);
    assert.deepEqual(regra.meses, [10, 12]);
    assert.equal(regra.quantidade, 8);
    const d = r.montarRegraRepeticao({ ...base(), fimTipo: "data", dataLimite: "2026-12-20" }).regra;
    assert.equal(d.data_limite, "2026-12-20");
    assert.equal(d.quantidade, undefined);
});

test("mensal não manda dias", () => {
    const { regra } = r.montarRegraRepeticao({ ...base(), frequencia: "mensal", mensalPor: "dia_semana" });
    assert.deepEqual(regra, { frequencia: "mensal", mensal_por: "dia_semana", meses: null });
});

test("erros com mensagem", () => {
    const sem = { ...base(), dias: { 1: { marcado: false, inicio: "09:00", fim: "09:50" } } };
    assert.match(r.montarRegraRepeticao(sem).erro, /dia da semana/);
    const invertido = { ...base(), dias: { 1: { marcado: true, inicio: "10:00", fim: "09:00" } } };
    assert.match(r.montarRegraRepeticao(invertido).erro, /fim/);
    assert.match(r.montarRegraRepeticao({ ...base(), meses: [] }).erro, /mês/);
    const curto = { ...base(), dias: { 1: { marcado: true, inicio: "08:00", fim: "08:01" } } };
    assert.match(r.montarRegraRepeticao(curto).erro, /5 min/);
    const longo = { ...base(), dias: { 1: { marcado: true, inicio: "07:00", fim: "21:00" } } };
    assert.match(r.montarRegraRepeticao(longo).erro, /8 h/);
    assert.match(r.montarRegraRepeticao({ ...base(), fimTipo: "quantidade", quantidade: "0" }).erro, /1 e 300/);
    assert.match(r.montarRegraRepeticao({ ...base(), fimTipo: "quantidade", quantidade: "301" }).erro, /1 e 300/);
    assert.match(r.montarRegraRepeticao({ ...base(), fimTipo: "data", dataLimite: "2026-10-01" }).erro, /data limite/i);
    assert.match(r.montarRegraRepeticao({ ...base(), fimTipo: "data", dataLimite: "" }).erro, /data limite/i);
    assert.match(r.montarRegraRepeticao({ ...base(), frequencia: "semanas", aCada: "13" }).erro, /1 e 12/);
});

test("descrição do mensal pelo dia da semana", () => {
    assert.equal(r.descreverDiaDaSemanaNoMes("2026-10-13"), "toda 2ª terça-feira do mês");
    assert.equal(r.descreverDiaDaSemanaNoMes("2026-12-29"), "toda última terça-feira do mês");
    assert.equal(r.descreverDiaDaSemanaNoMes("2026-10-04"), "todo 1º domingo do mês");
    assert.equal(r.descreverDiaDaSemanaNoMes("2026-10-31"), "todo último sábado do mês");
});

test("sincronizarDiasRepeticao: data e hora do agendamento acompanham os dias", () => {
    const dias = () => ({
        1: { marcado: true, inicio: "09:00", fim: "09:50" },     // dia da data (automático)
        3: { marcado: true, inicio: "14:00", fim: "15:00" },     // ajustado à mão
        5: { marcado: false, inicio: "09:00", fim: "09:50" },
    });
    const ant = { dia: 1, hora: "09:00", horaFim: "09:50" };
    // mudou a data para quarta e a hora para 10:00
    const n = r.sincronizarDiasRepeticao(dias(), ant, { dia: 3, hora: "10:00", horaFim: "10:50" });
    assert.deepEqual(n[1], { marcado: false, inicio: "10:00", fim: "10:50" });   // desmarca o dia antigo
    assert.deepEqual(n[3], { marcado: true, inicio: "14:00", fim: "15:00" });    // dia novo já marcado à mão: mantém o horário
    assert.deepEqual(n[5], { marcado: false, inicio: "10:00", fim: "10:50" });   // padrão acompanha a hora
    // só a hora mudou
    const h = r.sincronizarDiasRepeticao(dias(), ant, { dia: 1, hora: "11:00", horaFim: "11:40" });
    assert.deepEqual(h[1], { marcado: true, inicio: "11:00", fim: "11:40" });
    assert.deepEqual(h[3], { marcado: true, inicio: "14:00", fim: "15:00" });
    // dia novo desmarcado passa a ser marcado com o horário novo
    const d = r.sincronizarDiasRepeticao(dias(), ant, { dia: 5, hora: "09:00", horaFim: "09:50" });
    assert.equal(d[1].marcado, false);
    assert.deepEqual(d[5], { marcado: true, inicio: "09:00", fim: "09:50" });
});
