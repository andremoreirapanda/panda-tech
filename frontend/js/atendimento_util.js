// ============================================================================
// Atender (08/10/2026) — funções puras, testadas em
// frontend/tests/atendimento_util.test.js. No navegador viram globais.
// ============================================================================

// Dias desde a consulta, se passou mais de 1 dia e ela ainda não teve
// desfecho (agendada/confirmada); senão 0. `hojeChave` = "YYYY-MM-DD" local.
function diasDeAtraso(consulta, hojeChave) {
    if (!consulta || !["agendada", "confirmada"].includes(consulta.status)) return 0;
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(consulta.data_hora || ""));
    const h = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(hojeChave || ""));
    if (!m || !h) return 0;
    const dias = Math.round((Date.UTC(+h[1], +h[2] - 1, +h[3]) - Date.UTC(+m[1], +m[2] - 1, +m[3])) / 86400000);
    return dias > 1 ? dias : 0;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { diasDeAtraso };
}
