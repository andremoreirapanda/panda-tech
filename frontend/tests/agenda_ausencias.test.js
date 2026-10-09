// Funções puras das ausências da agenda (spec 07/10/2026).
// Rodar: node --test frontend/tests/*.test.js
process.env.TZ = "America/Sao_Paulo";
const test = require("node:test");
const assert = require("node:assert/strict");
const a = require("../js/agenda_ausencias.js");

const almoco = { ausencia_id: 1, profissional_id: 7, data: "2026-10-06", dia_inteiro: 0, hora_inicio: "12:00", hora_fim: "13:00" };
const ferias = { ausencia_id: 2, profissional_id: 8, data: "2026-10-06", dia_inteiro: 1, hora_inicio: null, hora_fim: null };

test("ocorrenciasDaColuna filtra por profissional e dia", () => {
    assert.deepEqual(a.ocorrenciasDaColuna([almoco, ferias], 7, "2026-10-06"), [almoco]);
    assert.deepEqual(a.ocorrenciasDaColuna([almoco], 7, "2026-10-07"), []);
});

test("intervaloBloqueado: sobrepor bloqueia, encostar não", () => {
    assert.equal(a.intervaloBloqueado([almoco], 7, "2026-10-06", 690, 750), almoco);
    assert.equal(a.intervaloBloqueado([almoco], 7, "2026-10-06", 660, 720), null);
    assert.equal(a.intervaloBloqueado([almoco], 7, "2026-10-06", 780, 840), null);
    assert.equal(a.intervaloBloqueado([ferias], 8, "2026-10-06", 420, 425), ferias);
});

test("calcularFim e duracaoEntre", () => {
    assert.equal(a.calcularFim("09:00", 50), "09:50");
    assert.equal(a.calcularFim("23:30", 50), "23:59");
    assert.equal(a.calcularFim("", 50), "");
    assert.equal(a.duracaoEntre("09:00", "09:45"), 45);
    assert.equal(a.duracaoEntre("09:00", "09:00"), null);
    assert.equal(a.duracaoEntre("10:00", "09:00"), null);
    assert.equal(a.duracaoEntre("", "09:00"), null);
});

test("diasSemanaPadrao", () => {
    assert.equal(a.diasSemanaPadrao("2026-10-07", "2026-10-07"), "3"); // quarta
    assert.equal(a.diasSemanaPadrao("2026-10-07", ""), "123456");
    assert.equal(a.diasSemanaPadrao("2026-10-07", "2026-10-20"), "123456");
});

// ---------------------------------------------------------------- Parte C (09/10/2026): ausências no modo Geral

const occ = (data, prof, extra = {}) => ({ data, profissional_id: prof, profissional_nome: prof === 1 ? "Camila Ribeiro" : "Rafael Souza",
                                         dia_inteiro: 0, hora_inicio: "08:00", hora_fim: "12:00", motivo: "Curso", ...extra });

test("periodoDaVisao", () => {
    const ref = new Date(2026, 9, 14);   // qua 14/10/2026
    const hoje = new Date(2026, 9, 9);
    assert.deepEqual(a.periodoDaVisao("semana", ref, hoje), { inicio: "2026-10-11", fim: "2026-10-17" });
    assert.deepEqual(a.periodoDaVisao("mes", ref, hoje), { inicio: "2026-09-27", fim: "2026-11-07" });
    assert.deepEqual(a.periodoDaVisao("lista", ref, hoje), { inicio: "2026-10-09", fim: "2026-11-07" });
    assert.deepEqual(a.periodoDaVisao("dia", ref, hoje), { inicio: "2026-10-14", fim: "2026-10-14" });
});

test("ausenciasPorDia: ordena, filtra e cobre vários dias", () => {
    const ocorrencias = [
        occ("2026-10-12", 1, { hora_inicio: "14:00", hora_fim: "16:00" }),
        occ("2026-10-12", 2, { dia_inteiro: 1, hora_inicio: null, hora_fim: null }),
        occ("2026-10-12", 1),
        ...["2026-10-13", "2026-10-14", "2026-10-15"].map(d => occ(d, 2, { dia_inteiro: 1, motivo: "Férias" })),
    ];
    const todos = a.ausenciasPorDia(ocorrencias, null);
    assert.deepEqual(todos["2026-10-12"].map(o => [o.profissional_id, o.dia_inteiro, o.hora_inicio]),
                     [[2, 1, null], [1, 0, "08:00"], [1, 0, "14:00"]]);
    assert.deepEqual(Object.keys(todos).sort(), ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15"]);
    const soCamila = a.ausenciasPorDia(ocorrencias, new Set([1]));
    assert.deepEqual(Object.keys(soCamila), ["2026-10-12"]);
    assert.equal(soCamila["2026-10-12"].length, 2);
});

test("rotuloAusencia", () => {
    assert.equal(a.rotuloAusencia(occ("2026-10-12", 1)), "Camila · 08:00–12:00");
    assert.equal(a.rotuloAusencia(occ("2026-10-12", 2, { dia_inteiro: 1 })), "Rafael · dia inteiro");
    assert.equal(a.rotuloAusencia({ dia_inteiro: 1 }), "Ausência · dia inteiro");
});
