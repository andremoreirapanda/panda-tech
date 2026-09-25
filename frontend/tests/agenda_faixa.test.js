// Testes das funções puras da grade da agenda (spec 24/09/2026).
// Rodar: node --test frontend/tests/*.test.js
process.env.TZ = "America/Sao_Paulo";
const test = require("node:test");
const assert = require("node:assert/strict");
const f = require("../js/agenda_faixa.js");

const c = (dataHora, duracao = 50) => ({ data_hora: dataHora, duracao_min: duracao });

test("hhmmParaMinutos aceita HH:MM e recusa o resto", () => {
    assert.equal(f.hhmmParaMinutos("08:00"), 480);
    assert.equal(f.hhmmParaMinutos("19:15"), 1155);
    for (const ruim of ["", null, undefined, "8:00", "24:00", "08:60", "08h", "abc"]) {
        assert.equal(f.hhmmParaMinutos(ruim), null, String(ruim));
    }
});

test("minutosParaHHMM formata e dá a volta na meia-noite", () => {
    assert.equal(f.minutosParaHHMM(1155), "19:15");
    assert.equal(f.minutosParaHHMM(1440 + 10), "00:10");
});

test("sem horário e sem consultas: 08:00-18:00", () => {
    assert.deepEqual(f.calcularFaixaAgenda([], null, null), { ini: 480, fim: 1080 });
});

test("automático estica para as consultas, em hora cheia", () => {
    const faixa = f.calcularFaixaAgenda([c("2026-09-21 07:30:00", 45), c("2026-09-22 18:40:00", 45)]);
    assert.deepEqual(faixa, { ini: 420, fim: 1200 }); // 07:00-20:00
});

test("horário da clínica é usado no minuto exato", () => {
    assert.deepEqual(f.calcularFaixaAgenda([c("2026-09-21 09:00:00")], "08:10", "19:15"), { ini: 490, fim: 1155 });
});

test("consulta fora do horário da clínica estica a faixa (hora cheia)", () => {
    const faixa = f.calcularFaixaAgenda([c("2026-09-21 19:30:00", 45), c("2026-09-22 07:20:00", 30)], "08:00", "19:15");
    assert.deepEqual(faixa, { ini: 420, fim: 1260 }); // 07:00-21:00
});

test("consulta perto da meia-noite não passa de 24:00", () => {
    const faixa = f.calcularFaixaAgenda([c("2026-09-21 23:30:00", 50)]);
    assert.equal(faixa.fim, 1440);
});

test("horário da clínica incompleto ou invertido cai no automático", () => {
    assert.deepEqual(f.calcularFaixaAgenda([], "08:00", ""), { ini: 480, fim: 1080 });
    assert.deepEqual(f.calcularFaixaAgenda([], "19:00", "08:00"), { ini: 480, fim: 1080 });
    assert.deepEqual(f.calcularFaixaAgenda([], "lixo", "18:00"), { ini: 480, fim: 1080 });
});

test("consulta com data_hora estranha é ignorada", () => {
    assert.deepEqual(f.calcularFaixaAgenda([{ data_hora: "", duracao_min: 50 }, { data_hora: null }]), { ini: 480, fim: 1080 });
});

test("minutoNaFaixa arredonda para baixo em 15 min e prende na faixa", () => {
    const faixa = { ini: 480, fim: 1080 }; // 08:00-18:00, 600 min
    assert.equal(f.minutoNaFaixa(0, 600, faixa), 480);
    assert.equal(f.minutoNaFaixa(70, 600, faixa), 540); // 09:10 -> 09:00
    assert.equal(f.minutoNaFaixa(-30, 600, faixa), 480);
    assert.equal(f.minutoNaFaixa(9999, 600, faixa), 1065); // último passo: 17:45
});

test("minutoNaFaixa com início picado não devolve horário antes da abertura", () => {
    const faixa = { ini: 490, fim: 1155 }; // 08:10-19:15
    assert.equal(f.minutoNaFaixa(0, 665, faixa), 490);
    assert.equal(f.minutoNaFaixa(3, 665, faixa), 490);
});

test("minutoDoDia aceita hora sem zero à esquerda (dado antigo/seed: '9:00:00')", () => {
    assert.equal(f.minutoDoDia("2026-09-24 09:00:00"), 540);
    assert.equal(f.minutoDoDia("2026-09-24 9:00:00"), 540);
    assert.equal(f.minutoDoDia("2026-09-24T19:15:00"), 1155);
    assert.equal(f.minutoDoDia(""), null);
    assert.equal(f.minutoDoDia(null), null);
});

test("consulta com hora sem zero à esquerda também estica a faixa", () => {
    assert.deepEqual(f.calcularFaixaAgenda([c("2026-09-24 7:30:00", 45)]), { ini: 420, fim: 1080 });
});

test("precisaDomingo só com consulta naquele domingo", () => {
    assert.equal(f.precisaDomingo("2026-09-20", [c("2026-09-21 09:00:00")]), false);
    assert.equal(f.precisaDomingo("2026-09-20", [c("2026-09-20 10:00:00")]), true);
});

test("paraChaveDia usa a data local (22h em Brasília ainda é o mesmo dia)", () => {
    assert.equal(f.paraChaveDia(new Date(2026, 8, 24, 22, 30)), "2026-09-24");
    assert.equal(f.paraChaveDia(new Date(2026, 8, 24, 0, 5)), "2026-09-24");
});
