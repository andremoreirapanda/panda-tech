// Atender (08/10/2026): dias de atraso da evolução.
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const a = require("../js/atendimento_util.js");

test("statusLiberaHorario: cancelada, desmarcada pelo profissional e falta justificada", () => {
    for (const s of ["cancelada", "desmarcada_profissional", "falta_justificada"]) assert.equal(a.statusLiberaHorario(s), true);
    for (const s of ["agendada", "confirmada", "realizada", "faltou"]) assert.equal(a.statusLiberaHorario(s), false);
});

test("diasDeAtraso: só conta depois de mais de 1 dia e sem desfecho", () => {
    const hoje = "2026-10-08";
    assert.equal(a.diasDeAtraso({ data_hora: "2026-10-02 11:10:00", status: "confirmada" }, hoje), 6);
    assert.equal(a.diasDeAtraso({ data_hora: "2026-10-02 9:00:00", status: "agendada" }, hoje), 6);
    assert.equal(a.diasDeAtraso({ data_hora: "2026-10-07 09:00:00", status: "agendada" }, hoje), 0);   // ontem
    assert.equal(a.diasDeAtraso({ data_hora: "2026-10-06 09:00:00", status: "agendada" }, hoje), 2);
    assert.equal(a.diasDeAtraso({ data_hora: "2026-10-02 09:00:00", status: "realizada" }, hoje), 0);
    assert.equal(a.diasDeAtraso({ data_hora: "2026-10-02 09:00:00", status: "falta_justificada" }, hoje), 0);
    assert.equal(a.diasDeAtraso({ data_hora: "2026-10-20 09:00:00", status: "agendada" }, hoje), 0);
    assert.equal(a.diasDeAtraso({ data_hora: "lixo", status: "agendada" }, hoje), 0);
});

test("rotuloStatusFamilia: o que a família entende", () => {
    const hoje = "2026-10-12";
    const r = (status, data_hora) => a.rotuloStatusFamilia({ status, data_hora }, hoje);
    assert.equal(r("realizada", "2026-10-08 09:00:00"), "Aconteceu");
    assert.equal(r("faltou", "2026-10-08 09:00:00"), "Faltou");
    assert.equal(r("falta_justificada", "2026-10-08 09:00:00"), "Falta justificada");
    assert.equal(r("cancelada", "2026-10-08 09:00:00"), "Desmarcada");
    assert.equal(r("desmarcada_profissional", "2026-10-20 09:00:00"), "Desmarcada");
    assert.equal(r("agendada", "2026-10-20 09:00:00"), "Marcada");
    assert.equal(r("confirmada", "2026-10-12 15:00:00"), "Confirmada");      // hoje: ainda não passou o dia
    assert.equal(r("agendada", "2026-10-11 15:00:00"), "Aguardando registro");
    assert.equal(r("confirmada", "2026-10-09 9:00:00"), "Aguardando registro");
});
