// ============================================================================
// Busca de paciente no agendamento (09/10/2026) — funções puras, testadas em
// frontend/tests/busca_paciente.test.js. No navegador viram globais.
// Como na Clínica Ágil: a partir de 3 letras, ignorando acentos e maiúsculas.
// ============================================================================

const BUSCA_PACIENTE_MINIMO = 3;
const BUSCA_PACIENTE_LIMITE = 8;

// "  Benício  ÇÃO " → "benicio cao"
function normalizarBusca(texto) {
    return String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "")
        .toLowerCase().replace(/\s+/g, " ").trim();
}

// Pacientes cujo nome tem todas as palavras digitadas. Quem começa com o termo
// vem primeiro; depois, ordem alfabética. Menos de 3 letras → [].
function filtrarPacientes(pacientes, termo, limite = BUSCA_PACIENTE_LIMITE) {
    const busca = normalizarBusca(termo);
    if (busca.replace(/\s/g, "").length < BUSCA_PACIENTE_MINIMO) return [];
    const palavras = busca.split(" ");
    return (pacientes || [])
        .map(p => ({ p, nome: normalizarBusca(p.nome) }))
        .filter(({ nome }) => palavras.every(w => nome.includes(w)))
        .sort((a, b) => (b.nome.startsWith(busca) - a.nome.startsWith(busca)) || a.nome.localeCompare(b.nome, "pt-BR"))
        .slice(0, limite)
        .map(({ p }) => p);
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { normalizarBusca, filtrarPacientes, BUSCA_PACIENTE_MINIMO };
}
