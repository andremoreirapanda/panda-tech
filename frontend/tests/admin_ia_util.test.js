// IA — ditado: formatações das telas do Admin.
const test = require("node:test");
const assert = require("node:assert/strict");
const u = require("../js/admin_ia_util.js");

test("formatarUsd usa vírgula decimal e ponto de milhar", () => {
    assert.equal(u.formatarUsd(0.42), "US$ 0,42");
    assert.equal(u.formatarUsd(0), "US$ 0,00");
    assert.equal(u.formatarUsd(1234.5), "US$ 1.234,50");
    assert.equal(u.formatarUsd(null), "US$ 0,00");
});

test("nomeDoMes escreve o mês em português", () => {
    assert.equal(u.nomeDoMes("2026-11"), "novembro de 2026");
    assert.equal(u.nomeDoMes("2027-03"), "março de 2027");
    assert.equal(u.nomeDoMes("lixo"), "lixo");
    assert.equal(u.nomeDoMes(""), "");
});

test("ultimosMeses volta no tempo atravessando o ano", () => {
    const l = u.ultimosMeses("2026-02", 4);
    assert.deepEqual(l, ["2026-02", "2026-01", "2025-12", "2025-11"]);
    assert.deepEqual(u.ultimosMeses("x"), []);
});
