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
