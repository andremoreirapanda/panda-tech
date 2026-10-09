// ============================================================================
// Repetição avançada do agendamento (09/10/2026) — funções puras, testadas em
// frontend/tests/repeticao_util.test.js. No navegador viram globais.
// A regra montada aqui vai como `repeticao` para POST /api/agenda/recorrente
// (ver backend/recorrencia_service.py, que valida de novo).
// ============================================================================

const REPETICAO_LIMITE = 300;
const _NOMES_DIA_SEMANA = [["domingo", "o"], ["segunda-feira", "a"], ["terça-feira", "a"], ["quarta-feira", "a"],
                           ["quinta-feira", "a"], ["sexta-feira", "a"], ["sábado", "o"]];

// estado: { frequencia, aCada, dataInicial, dias: {0..6: {marcado, inicio, fim}},
//           mensalPor, meses: [1..12 marcados], fimTipo: "nenhum"|"data"|"quantidade",
//           dataLimite, quantidade }  →  { regra } ou { erro }
function montarRegraRepeticao(estado) {
    const regra = { frequencia: estado.frequencia };
    if (estado.frequencia === "mensal") {
        regra.mensal_por = estado.mensalPor === "dia_semana" ? "dia_semana" : "dia_mes";
    } else {
        if (estado.frequencia === "semanas") {
            const n = Number(estado.aCada);
            if (!Number.isInteger(n) || n < 1 || n > 12) return { erro: "A cada quantas semanas: escolha entre 1 e 12." };
            regra.a_cada = n;
        }
        const dias = {};
        for (const [dia, info] of Object.entries(estado.dias || {})) {
            if (!info || !info.marcado) continue;
            if (!info.inicio || !info.fim || info.fim <= info.inicio) {
                return { erro: "Em cada dia marcado, o fim precisa ser depois do início." };
            }
            dias[dia] = { inicio: info.inicio, fim: info.fim };
        }
        if (!Object.keys(dias).length) return { erro: "Marque pelo menos um dia da semana." };
        regra.dias = dias;
    }
    const meses = (estado.meses || []).map(Number).filter(m => m >= 1 && m <= 12);
    if (!meses.length) return { erro: "Marque pelo menos um mês." };
    regra.meses = meses.length === 12 ? null : [...new Set(meses)].sort((a, b) => a - b);
    if (estado.fimTipo === "quantidade") {
        const q = Number(estado.quantidade);
        if (!Number.isInteger(q) || q < 1 || q > REPETICAO_LIMITE) return { erro: `Quantidade de consultas: escolha entre 1 e ${REPETICAO_LIMITE}.` };
        regra.quantidade = q;
    } else if (estado.fimTipo === "data") {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(estado.dataLimite || "")) return { erro: "Escolha a data limite." };
        if (estado.dataInicial && estado.dataLimite < estado.dataInicial) return { erro: "A data limite precisa ser depois da primeira consulta." };
        regra.data_limite = estado.dataLimite;
    }
    return { regra };
}

// "2026-10-13" → "toda 2ª terça-feira do mês"; 5ª ocorrência → "última".
function descreverDiaDaSemanaNoMes(dataISO) {
    const [a, m, d] = String(dataISO).split("-").map(Number);
    const diaSemana = new Date(a, m - 1, d).getDay();
    const ordem = Math.floor((d - 1) / 7) + 1;
    const [nome, genero] = _NOMES_DIA_SEMANA[diaSemana];
    const ordinal = ordem >= 5 ? "último".replace(/o$/, genero) : `${ordem}${genero === "a" ? "ª" : "º"}`;
    return `tod${genero} ${ordinal} ${nome} do mês`;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { montarRegraRepeticao, descreverDiaDaSemanaNoMes };
}
