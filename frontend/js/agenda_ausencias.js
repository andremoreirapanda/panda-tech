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

// ---------------------------------------------------------------- Modo Geral (09/10/2026)

function _chaveDiaAus(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function _somarDias(d, n) {
    const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    x.setDate(x.getDate() + n);
    return x;
}

// Dias que cada visão mostra (a API aceita até 62 dias por pedido).
// semana: domingo a sábado; mes: as 42 células da grade; lista: hoje + 29; dia: o dia.
function periodoDaVisao(visao, dataReferencia, hoje) {
    const ref = new Date(dataReferencia.getFullYear(), dataReferencia.getMonth(), dataReferencia.getDate());
    if (visao === "lista") return { inicio: _chaveDiaAus(hoje), fim: _chaveDiaAus(_somarDias(hoje, 29)) };
    if (visao === "dia") return { inicio: _chaveDiaAus(ref), fim: _chaveDiaAus(ref) };
    if (visao === "mes") {
        const primeiro = new Date(ref.getFullYear(), ref.getMonth(), 1);
        const inicio = _somarDias(primeiro, -primeiro.getDay());
        return { inicio: _chaveDiaAus(inicio), fim: _chaveDiaAus(_somarDias(inicio, 41)) };
    }
    const domingo = _somarDias(ref, -ref.getDay());
    return { inicio: _chaveDiaAus(domingo), fim: _chaveDiaAus(_somarDias(domingo, 6)) };
}

// {"YYYY-MM-DD": [ocorrências]} — dia inteiro primeiro, depois por horário.
// `profsVisiveis` (Set de ids) = filtro da lista lateral; null = todos.
function ausenciasPorDia(ocorrencias, profsVisiveis) {
    const porDia = {};
    for (const o of ocorrencias || []) {
        if (profsVisiveis && !profsVisiveis.has(o.profissional_id)) continue;
        (porDia[o.data] = porDia[o.data] || []).push(o);
    }
    for (const lista of Object.values(porDia)) {
        lista.sort((x, y) => (y.dia_inteiro ? 1 : 0) - (x.dia_inteiro ? 1 : 0)
            || String(x.hora_inicio || "").localeCompare(String(y.hora_inicio || "")));
    }
    return porDia;
}

// "Camila · 08:00–12:00" / "Camila · dia inteiro"
function rotuloAusencia(o) {
    const nome = (o.profissional_nome || "").trim().split(/\s+/)[0] || "Ausência";
    return `${nome} · ${o.dia_inteiro ? "dia inteiro" : `${o.hora_inicio}–${o.hora_fim}`}`;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { ocorrenciasDaColuna, intervaloBloqueado, calcularFim, duracaoEntre, diasSemanaPadrao,
                       periodoDaVisao, ausenciasPorDia, rotuloAusencia };
}
