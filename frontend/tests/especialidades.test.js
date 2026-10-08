// Etiquetas e opções de especialidade dos planos (spec 08/10/2026).
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const e = require("../js/especialidades.js");

test("etiqueta completa e curta", () => {
    assert.equal(e.etiquetaEspecialidade("Fonoaudiologia"), "🗣️ Fonoaudiologia");
    assert.equal(e.etiquetaEspecialidade("Fonoaudiologia", true), "🗣️ Fono");
    assert.equal(e.etiquetaEspecialidade("Terapia Ocupacional", true), "🧩 TO");
    assert.equal(e.etiquetaEspecialidade("Psicopedagogia", true), "📚 Psicoped.");
    assert.equal(e.etiquetaEspecialidade("Musicoterapia Infantil", true), "🩺 Musicoterapia");
    assert.equal(e.etiquetaEspecialidade("", true), "");
    assert.equal(e.etiquetaEspecialidade(null), "");
});

test("opções do select: marca a minha se estiver na lista", () => {
    assert.deepEqual(e.opcoesEspecialidade(["Fonoaudiologia", "Terapia Ocupacional"], "Terapia Ocupacional"),
        { opcoes: ["Fonoaudiologia", "Terapia Ocupacional"], selecionada: "Terapia Ocupacional" });
    assert.deepEqual(e.opcoesEspecialidade(["Fonoaudiologia"], "Psicologia"),
        { opcoes: ["Fonoaudiologia"], selecionada: "Fonoaudiologia" });
    assert.deepEqual(e.opcoesEspecialidade([], null), { opcoes: ["Geral"], selecionada: "Geral" });
});
