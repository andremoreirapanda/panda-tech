// ============================================================================
// Especialidades — ícones, etiquetas e opções do select de plano
// (spec 08/10/2026, planos por especialidade). Funções puras, testadas em
// frontend/tests/especialidades.test.js; no navegador viram globais.
// ============================================================================

const ICONES_ESPECIALIDADE = {
    "Fonoaudiologia": "🗣️", "Terapia Ocupacional": "🧩", "Psicopedagogia": "📚", "Psicologia": "🧠", "Fisioterapia": "🤸",
};

const NOMES_CURTOS_ESPECIALIDADE = {
    "Fonoaudiologia": "Fono", "Terapia Ocupacional": "TO", "Psicopedagogia": "Psicoped.", "Psicologia": "Psico",
    "Fisioterapia": "Fisio",
};

// "🗣️ Fonoaudiologia" (ou "🗣️ Fono" na versão curta, usada no Mundo da Criança).
function etiquetaEspecialidade(esp, curta = false) {
    const nome = String(esp || "").trim();
    if (!nome) return "";
    const texto = curta ? (NOMES_CURTOS_ESPECIALIDADE[nome] || nome.split(/\s+/)[0]) : nome;
    return `${ICONES_ESPECIALIDADE[nome] || "🩺"} ${texto}`;
}

// Select de especialidade: marca a de quem está criando, se estiver na lista.
function opcoesEspecialidade(lista, minha) {
    const opcoes = (lista && lista.length) ? lista.slice() : ["Geral"];
    return { opcoes, selecionada: opcoes.includes(minha) ? minha : opcoes[0] };
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { ICONES_ESPECIALIDADE, etiquetaEspecialidade, opcoesEspecialidade };
}
