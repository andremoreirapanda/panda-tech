// ============================================================================
// Procedimentos (09/10/2026) — funções puras, testadas em
// frontend/tests/procedimentos_util.test.js. No navegador viram globais.
// Mesma regra de procedimentos_service.reais_para_centavos (backend).
// ============================================================================

const VALOR_MAXIMO_CENTAVOS = 10000000; // R$ 100.000,00

// "230,00" / "1.230,50" / "R$ 15" / 230.5 → centavos; null se inválido.
function reaisParaCentavos(valor) {
    if (valor === null || valor === undefined || typeof valor === "boolean") return null;
    let centavos;
    if (typeof valor === "number") {
        if (!isFinite(valor)) return null;
        centavos = Math.round(valor * 100);
    } else {
        const texto = String(valor).replace(/^\s*R\$\s*/, "").trim();
        if (!/^(\d{1,3}(\.\d{3})*(,\d{1,2})?|\d+(,\d{1,2})?|\d+\.\d{1,2})$/.test(texto)) return null;
        let inteiro, frac = "";
        if (texto.includes(",")) [inteiro, frac] = texto.replace(/\./g, "").split(",");
        else if (/^\d+\.\d{1,2}$/.test(texto)) [inteiro, frac] = texto.split(".");
        else inteiro = texto.replace(/\./g, "");
        centavos = parseInt(inteiro, 10) * 100 + parseInt((frac + "00").slice(0, 2), 10);
    }
    if (centavos < 0 || centavos > VALOR_MAXIMO_CENTAVOS) return null;
    return centavos;
}

// 123050 → "1.230,50"
function centavosParaReais(centavos) {
    const n = Math.round(Number(centavos) || 0);
    const inteiro = String(Math.floor(n / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return `${inteiro},${String(n % 100).padStart(2, "0")}`;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { reaisParaCentavos, centavosParaReais };
}
