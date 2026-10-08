// ============================================================================
// Agenda — ausências e hora de fim (spec 07/10/2026)
//
// Funções puras (sem DOM), testadas em frontend/tests/agenda_ausencias.test.js.
// No navegador viram globais; no Node, dependem de agenda_faixa.js via require.
// ============================================================================

const _faixaAus = (typeof module !== "undefined" && module.exports) ? require("./agenda_faixa.js") : null;
const _hhmmParaMin = (x) => (_faixaAus ? _faixaAus.hhmmParaMinutos(x) : hhmmParaMinutos(x));
const _minParaHHMM = (x) => (_faixaAus ? _faixaAus.minutosParaHHMM(x) : minutosParaHHMM(x));

function ocorrenciasDaColuna(ocorrencias, profissionalId, chaveDia) {
    return (ocorrencias || []).filter(o => o.profissional_id === profissionalId && o.data === chaveDia);
}

// Ocorrência que bate com [iniMin, fimMin) — encostar não conta.
function intervaloBloqueado(ocorrencias, profissionalId, chaveDia, iniMin, fimMin) {
    for (const o of ocorrenciasDaColuna(ocorrencias, profissionalId, chaveDia)) {
        if (o.dia_inteiro) return o;
        const ai = _hhmmParaMin(o.hora_inicio), af = _hhmmParaMin(o.hora_fim);
        if (ai !== null && af !== null && iniMin < af && fimMin > ai) return o;
    }
    return null;
}

function calcularFim(inicioHHMM, duracaoMin) {
    const ini = _hhmmParaMin(inicioHHMM);
    if (ini === null) return "";
    return _minParaHHMM(Math.min(ini + (duracaoMin || 0), 23 * 60 + 59));
}

function duracaoEntre(inicioHHMM, fimHHMM) {
    const ini = _hhmmParaMin(inicioHHMM), fim = _hhmmParaMin(fimHHMM);
    if (ini === null || fim === null || fim <= ini) return null;
    return fim - ini;
}

// Período de vários dias (ou sem fim) → seg a sáb; um dia só → o dia dele.
function diasSemanaPadrao(dataInicio, dataFim) {
    if (dataInicio && dataFim && dataInicio === dataFim) {
        return String(new Date(dataInicio + "T00:00:00").getDay());
    }
    return "123456";
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { ocorrenciasDaColuna, intervaloBloqueado, calcularFim, duracaoEntre, diasSemanaPadrao };
}
