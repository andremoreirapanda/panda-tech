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

// Mesmos status de ausencias_service.STATUS_LIBERAM_HORARIO: a consulta fica na
// agenda, mas o horário está livre para outra (sem pedir encaixe).
const STATUS_LIBERAM_HORARIO = ["cancelada", "desmarcada_profissional", "falta_justificada"];
function statusLiberaHorario(status) {
    return STATUS_LIBERAM_HORARIO.includes(status);
}

// Status da consulta na linguagem da família (12/10/2026). Consulta de um dia
// que já passou e ainda sem desfecho: "Aguardando registro".
function rotuloStatusFamilia(consulta, hojeChave) {
    const s = consulta && consulta.status;
    if (s === "realizada") return "Aconteceu";
    if (s === "faltou") return "Faltou";
    if (s === "falta_justificada") return "Falta justificada";
    if (s === "cancelada" || s === "desmarcada_profissional") return "Desmarcada";
    const m = /^(\d{4}-\d{2}-\d{2})/.exec(String((consulta && consulta.data_hora) || ""));
    if (m && hojeChave && m[1] < hojeChave) return "Aguardando registro";
    return s === "confirmada" ? "Confirmada" : "Marcada";
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { diasDeAtraso, statusLiberaHorario, rotuloStatusFamilia };
}
