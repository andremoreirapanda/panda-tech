// Importação do prontuário (26/10/2026): funções puras da tela.
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const u = require("../js/importacao_util.js");

test("campos das planilhas com os nomes do modelo", () => {
    assert.deepEqual(u.CAMPOS_FICHA_CSV,
        ["diagnostico", "alergias", "medicamentos_em_uso", "profissionais_externos", "observacoes_clinicas"]);
    assert.deepEqual(u.CAMPOS_EVOLUCOES_CSV,
        ["paciente_nome", "paciente_nascimento", "data_atendimento", "profissional_email",
            "profissional_nome", "evolucao", "observacao"]);
});

test("colunas de data de cada aba (série do Excel vira AAAA-MM-DD)", () => {
    assert.deepEqual(u.colunasDeData("pacientes"), ["data_nascimento"]);
    assert.deepEqual(u.colunasDeData("evolucoes"), ["paciente_nascimento", "data_atendimento"]);
    assert.equal(u.ehColunaDeData("data_atendimento"), true);
    assert.equal(u.ehColunaDeData("evolucao"), false);
});

test("dividirEmEnvios: pedaços de até 1.000", () => {
    const linhas = Array.from({ length: 2500 }, (_, i) => i);
    assert.deepEqual(u.dividirEmEnvios(linhas).map(p => p.length), [1000, 1000, 500]);
    assert.equal(u.dividirEmEnvios(linhas)[1][0], 1000);
    assert.deepEqual(u.dividirEmEnvios([]), []);
    assert.deepEqual(u.dividirEmEnvios([1, 2, 3], 2), [[1, 2], [3]]);
});

test("juntarPrevias: soma contadores e corrige o número da linha", () => {
    const a = { linhas: [{ linha: 0, status: "pronta" }, { linha: 1, status: "erro" }], total: 2, prontas: 1, avisos: 0, erros: 1, ja_importadas: 0 };
    const b = { linhas: [{ linha: 0, status: "ja_importada" }], total: 1, prontas: 0, avisos: 0, erros: 0, ja_importadas: 1 };
    const j = u.juntarPrevias([a, b], 2);
    assert.equal(j.total, 3);
    assert.equal(j.prontas, 1);
    assert.equal(j.erros, 1);
    assert.equal(j.ja_importadas, 1);
    assert.deepEqual(j.linhas.map(l => l.linha), [0, 1, 2]);
    assert.equal(u.juntarPrevias([], 1000).total, 0);
});

test("selo do registro importado", () => {
    const selo = u.seloDiarioImportado();
    assert.match(selo, /Importado/);
    assert.match(selo, /Só a equipe vê/);
});
