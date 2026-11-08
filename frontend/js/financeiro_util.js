// ============================================================================
// financeiro_util.js — Financeiro (07/11/2026): rótulos e validações puras,
// testadas em frontend/tests/financeiro_util.test.js. No navegador viram globais.
// ============================================================================

function rotuloStatusCobranca(status, aberta) {
    switch (status) {
        case "rascunho": return aberta ? "Em andamento" : "Para conferir";
        case "pendente": return "Em aberto";
        case "parcial": return "Pago em parte";
        case "pago": return "Pago";
        case "vencido": return "Vencido";
        case "cancelado": return "Cancelado";
        default: return String(status || "");
    }
}

const _ROTULOS_FORMA = {
    pix: "Pix", dinheiro: "Dinheiro", cartao_credito: "Cartão de crédito", cartao_debito: "Cartão de débito",
    cartao: "Cartão", transferencia: "Transferência", boleto: "Boleto",
};

function rotuloForma(forma) {
    return _ROTULOS_FORMA[forma] || String(forma || "");
}

// O Intl usa espaço sem quebra entre "R$" e o número; troca por espaço comum.
function _moedaUtil(centavos) {
    return (centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }).replace(/ /g, " ");
}

function rotuloAcordo(acordo) {
    const a = acordo || {};
    if (a.tipo === "mensalidade") return `Mensalidade · ${_moedaUtil(a.valor_centavos || 0)} · vence dia ${a.dia_vencimento}`;
    if (a.tipo === "pacote") {
        return `Pacote · ${a.sessoes_total} sessões · ${_moedaUtil(a.valor_centavos || 0)} em ${a.parcelas}x`;
    }
    const ciclo = { consulta: "a cada consulta", quinzenal: "a cada 15 dias", mensal: "mensal" }[a.ciclo] || "";
    return `Por sessão · ${ciclo}`;
}

// "1.234,56" -> 123456; "1234,5" -> 123450; "230" -> 23000; inválido -> null.
function lerValorReais(texto) {
    const t = String(texto == null ? "" : texto).replace(/R\$/gi, "").replace(/\s/g, "");
    if (!t) return null;
    const m = /^(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?$/.exec(t);
    if (!m) return null;
    const inteiro = m[1].replace(/\./g, "");
    const frac = (m[2] || "").padEnd(2, "0");
    return parseInt(inteiro, 10) * 100 + parseInt(frac || "0", 10);
}

function _inteiroUtil(v, min, max) {
    const n = typeof v === "string" && v.trim() !== "" ? Number(v) : v;
    return Number.isInteger(n) && n >= min && n <= max ? n : null;
}

function _dataUtil(v) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(v || ""))) return null;
    const d = new Date(v + "T12:00:00Z");
    return isNaN(d) || d.toISOString().slice(0, 10) !== v ? null : v;
}

// Mesmas regras de acordos_service.validar; devolve a mensagem ou null.
function validarAcordo(form) {
    const f = form || {};
    if (!["avulsa", "mensalidade", "pacote"].includes(f.tipo)) return "Escolha o tipo do acordo.";
    const esp = f.especialidade == null || f.especialidade === "" ? "Geral" : f.especialidade;
    if (typeof esp !== "string") return "Especialidade inválida.";
    if (esp.trim().length > 60) return "Especialidade com mais de 60 caracteres.";
    let inicio = null;
    if (f.inicio) {
        inicio = _dataUtil(f.inicio);
        if (!inicio) return "Data de início inválida.";
    }
    if (f.fim) {
        const fim = _dataUtil(f.fim);
        if (!fim) return "Data de fim inválida.";
        if (inicio && fim < inicio) return "O fim não pode ser antes do início.";
    }
    if (f.vence_dias != null && f.vence_dias !== "" && _inteiroUtil(f.vence_dias, 0, 60) === null) {
        return "Dias para vencer deve ficar entre 0 e 60.";
    }
    if (f.tipo === "avulsa") {
        if (!["consulta", "quinzenal", "mensal"].includes(f.ciclo)) return "Escolha o ciclo da cobrança (por consulta, quinzenal ou mensal).";
    } else if (f.tipo === "mensalidade") {
        if (_inteiroUtil(f.valor_centavos, 1, 100000000) === null) return "Informe o valor da mensalidade.";
        if (_inteiroUtil(f.dia_vencimento, 1, 28) === null) return "O dia de vencimento deve ficar entre 1 e 28.";
    } else {
        if (_inteiroUtil(f.sessoes_total, 1, 200) === null) return "Informe a quantidade de sessões (1 a 200).";
        if (_inteiroUtil(f.valor_centavos, 1, 100000000) === null) return "Informe o valor do pacote.";
        if (_inteiroUtil(f.parcelas, 1, 24) === null) return "As parcelas devem ficar entre 1 e 24.";
        if (!_dataUtil(f.primeiro_vencimento)) return "Informe o primeiro vencimento.";
    }
    return null;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { rotuloStatusCobranca, rotuloForma, rotuloAcordo, lerValorReais, validarAcordo };
}
