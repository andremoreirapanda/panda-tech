// ============================================================================
// IA — ditado (26/11/2026): formatações puras das telas do Admin, testadas em
// frontend/tests/admin_ia_util.test.js. No navegador viram globais.
// ============================================================================

const MESES_PT_IA = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

// 0.42 → "US$ 0,42"; 1234.5 → "US$ 1.234,50"
function formatarUsd(valor) {
    const n = Number(valor);
    const v = isFinite(n) ? n : 0;
    const [inteiro, frac] = v.toFixed(2).split(".");
    return `US$ ${inteiro.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${frac}`;
}

// "2026-11" → "novembro de 2026" (vazio/inválido → o texto recebido)
function nomeDoMes(mes) {
    const m = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(String(mes || ""));
    if (!m) return String(mes || "");
    return `${MESES_PT_IA[parseInt(m[2], 10) - 1]} de ${m[1]}`;
}

// Os 12 últimos meses terminando em `mesAtual` ("AAAA-MM"), do mais novo ao mais antigo.
function ultimosMeses(mesAtual, quantidade = 12) {
    const m = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(String(mesAtual || ""));
    if (!m) return [];
    let ano = parseInt(m[1], 10), mes = parseInt(m[2], 10);
    const lista = [];
    for (let i = 0; i < quantidade; i++) {
        lista.push(`${ano}-${String(mes).padStart(2, "0")}`);
        mes -= 1;
        if (mes === 0) { mes = 12; ano -= 1; }
    }
    return lista;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { formatarUsd, nomeDoMes, ultimosMeses };
}
