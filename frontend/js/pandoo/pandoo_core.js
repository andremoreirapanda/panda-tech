// ============================================================================
// Pandoo (25/09/2026) — núcleo: catálogo de jogos plugáveis + regras puras.
// Um jogo novo = um arquivo em js/pandoo/jogos/ que chama registrarJogo().
// Funções puras testadas em frontend/tests/pandoo_core.test.js.
// ============================================================================

const PANDOO_JOGOS = {};
const PANDOO_LIMITES = { minItens: 2, maxItens: 24, maxTexto: 80 };
const REGRAS_PADRAO_PANDOO = {
    roleta: { fim: "todas", giros: 10, mostrar_palavra: true, som: true, voz: true },
};

function registrarJogo(codigo, def) {
    PANDOO_JOGOS[codigo] = { codigo, ...def };
}

function jogoRegistrado(codigo) {
    return PANDOO_JOGOS[codigo] || null;
}

function novoItemPandoo() {
    const id = "i" + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
    return { id, pergunta: { texto: "", imagem: null, audio: null }, resposta: { texto: "", imagem: null, audio: null }, distratores: [], grupo: null };
}

function conteudoVazioPandoo() {
    return { versao: 1, itens: [novoItemPandoo(), novoItemPandoo()] };
}

// Espelho amigável das regras do backend (pandoo_service.py), para avisar no
// editor antes de salvar. O backend continua sendo quem decide.
function problemasDoConteudo(modelo, conteudo) {
    const itens = (conteudo && conteudo.itens) || [];
    const problemas = [];
    if (itens.length < PANDOO_LIMITES.minItens || itens.length > PANDOO_LIMITES.maxItens) {
        problemas.push(`O jogo precisa ter de ${PANDOO_LIMITES.minItens} a ${PANDOO_LIMITES.maxItens} figuras.`);
    }
    if (modelo === "roleta") {
        itens.forEach((it, i) => {
            if (!it.pergunta || !it.pergunta.imagem) problemas.push(`Figura ${i + 1}: falta a imagem.`);
        });
    }
    return problemas;
}

function estadoInicialRoleta(conteudo) {
    return { pool: conteudo.itens.map(i => i.id), sorteados: [], rodadas: 0, detalhes: [] };
}

// Sorteia entre as figuras que ainda não saíram; quando todas já saíram (modo
// "N giros" com N maior que o total), o sorteio recomeça com todas.
function sortearItemRoleta(estado, conteudo, aleatorio = Math.random) {
    const pool = estado.pool.length ? estado.pool : conteudo.itens.map(i => i.id);
    const id = pool[Math.min(pool.length - 1, Math.floor(aleatorio() * pool.length))];
    return conteudo.itens.find(i => i.id === id);
}

function registrarRodada(estado, item, resultado, conteudo) {
    const atual = estado.pool.length ? estado.pool : conteudo.itens.map(i => i.id);
    return {
        pool: atual.filter(id => id !== item.id),
        sorteados: estado.sorteados.includes(item.id) ? estado.sorteados : [...estado.sorteados, item.id],
        rodadas: estado.rodadas + 1,
        detalhes: [...estado.detalhes, { item_id: item.id, texto: (item.pergunta && item.pergunta.texto) || "", resultado }],
    };
}

function partidaTerminou(estado, regras, conteudo) {
    if (regras.fim === "giros") return estado.rodadas >= regras.giros;
    return estado.sorteados.length >= conteudo.itens.length;
}

function resumoPartida(detalhes) {
    const conseguiu = detalhes.filter(d => d.resultado === "conseguiu").length;
    return { conseguiu, treinar: detalhes.length - conseguiu };
}

function mimeDaImagem(b64) {
    const s = String(b64 || "");
    if (s.startsWith("/9j/")) return "image/jpeg";
    if (s.startsWith("iVBOR")) return "image/png";
    if (s.startsWith("UklGR")) return "image/webp";
    if (s.startsWith("R0lGOD")) return "image/gif";
    return "image/jpeg";
}

function _primeirosBytes(b64, n) {
    try {
        const bin = typeof atob === "function" ? atob(String(b64).slice(0, 24)) : Buffer.from(String(b64).slice(0, 24), "base64").toString("binary");
        return Array.from(bin.slice(0, n), c => c.charCodeAt(0));
    } catch (e) { return []; }
}

function mimeDoAudio(b64) {
    const b = _primeirosBytes(b64, 12);
    const txt = (i, j) => String.fromCharCode(...b.slice(i, j));
    if (txt(0, 3) === "ID3" || (b[0] === 0xff && (b[1] & 0xe0) === 0xe0)) return "audio/mpeg";
    if (txt(0, 4) === "OggS") return "audio/ogg";
    if (txt(0, 4) === "RIFF") return "audio/wav";
    if (b[0] === 0x1a && b[1] === 0x45 && b[2] === 0xdf && b[3] === 0xa3) return "audio/webm";
    if (txt(4, 8) === "ftyp") return "audio/mp4";
    return "audio/mpeg";
}

// Mesma regra de pandoo_bp._cenario_efetivo (backend).
function cenarioEfetivoPandoo(cenarioJogo, org) {
    org = org || {};
    let tipo = cenarioJogo || org.pandoo_cenario_padrao || "bambu";
    if (tipo === "clinica" && org.pandoo_cenario_imagem) {
        return { tipo: "clinica", imagem: org.pandoo_cenario_imagem, tom: org.pandoo_cenario_tom || "claro" };
    }
    if (tipo === "clinica") tipo = "bambu";
    return { tipo, imagem: null, tom: "escuro" };
}

// Adapta o cenario_efetivo (API) ao montarCenarioAnimado compartilhado
// (cenarios_animados.js, White Label 25/09/2026). data: porque a CSP bloqueia blob:.
function cenarioParaPalco(efetivo) {
    const e = efetivo || {};
    if (e.tipo === "clinica" && e.imagem) {
        return { tipo: "clinica", imagemUrl: `data:${mimeDaImagem(e.imagem)};base64,${e.imagem}`, tom: e.tom === "escuro" ? "escuro" : "claro" };
    }
    const tipo = ["bambu", "mar", "espaco"].includes(e.tipo) ? e.tipo : "bambu";
    return { tipo, imagemUrl: null, tom: "escuro" };
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        PANDOO_JOGOS, PANDOO_LIMITES, REGRAS_PADRAO_PANDOO, registrarJogo, jogoRegistrado,
        novoItemPandoo, conteudoVazioPandoo, problemasDoConteudo, estadoInicialRoleta, sortearItemRoleta,
        registrarRodada, partidaTerminou, resumoPartida, mimeDaImagem, mimeDoAudio, cenarioEfetivoPandoo, cenarioParaPalco,
    };
}
