// ============================================================================
// Pandoo (29/10/2026) — Cruzadinha: regras puras, sem DOM.
// Palavras viram casas (hífen e espaço são fixos), o gerador monta a grade que
// o editor guarda em regras.grade, e o estado da partida é sempre devolvido
// novo (nunca mutado). Espelho da validação do backend (pandoo_service.py).
// Testes: frontend/tests/pandoo_cruzadinha.test.js
// ============================================================================

const LIMITES_CRUZADINHA = { minItens: 2, maxItens: 10, maxLetras: 12, maxGrade: 15 };
const TENTATIVAS_GRADE = 150;

function _maiusculaCruz(t) {
    return String(t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase();
}

function _textoCruz(t) {
    return String(t || "").split(/\s+/).filter(Boolean).join(" ");
}

function casasDaPalavra(texto) {
    return [..._maiusculaCruz(_textoCruz(texto))].map(ch =>
        ch === "-" ? { letra: "-", fixa: true } : ch === " " ? { letra: "", fixa: true } : { letra: ch, fixa: false });
}

function contarLetras(texto) {
    return casasDaPalavra(texto).filter(x => !x.fixa).length;
}

// Mensagem curta para o contador do editor; palavra vazia não é problema aqui
// (quem avisa "falta a palavra" é problemasCruzadinha).
function problemaDaPalavraCruzadinha(texto) {
    const t = _textoCruz(texto);
    if (!t) return null;
    if (!/^[A-Z]+([ -][A-Z]+)*$/.test(_maiusculaCruz(t))) return "Use só letras, hífen e espaço";
    const n = contarLetras(t);
    if (n > LIMITES_CRUZADINHA.maxLetras) return `Use até ${LIMITES_CRUZADINHA.maxLetras} letras`;
    if (n < 2) return "Use pelo menos 2 letras";
    return null;
}

const _chave = (l, c) => `${l},${c}`;

function palavrasDaGrade(grade, itens) {
    const porId = new Map((itens || []).map(it => [it.id, it]));
    return ((grade && grade.palavras) || []).filter(p => porId.has(p.item_id)).map(p => {
        const item = porId.get(p.item_id);
        const dl = p.direcao === "v" ? 1 : 0, dc = p.direcao === "h" ? 1 : 0;
        return {
            item_id: p.item_id, item, direcao: p.direcao, linha: p.linha, coluna: p.coluna,
            casas: casasDaPalavra(item.pergunta && item.pergunta.texto).map((cs, k) => ({ ...cs, chave: _chave(p.linha + dl * k, p.coluna + dc * k) })),
        };
    });
}

const _inteiroCruz = (v) => Number.isInteger(v) ? v : null;

function conferirGrade(grade, itens) {
    if (!grade || !Array.isArray(grade.palavras)) return false;
    const linhas = _inteiroCruz(grade.linhas), colunas = _inteiroCruz(grade.colunas);
    const max = LIMITES_CRUZADINHA.maxGrade;
    if (!linhas || !colunas || linhas > max || colunas > max || linhas < 1 || colunas < 1) return false;
    const textos = new Map((itens || []).map(it => [it.id, it.pergunta && it.pergunta.texto]));
    const vistos = new Set(), casas = new Map();
    for (const p of grade.palavras) {
        if (!p || !textos.has(p.item_id) || vistos.has(p.item_id) || !["h", "v"].includes(p.direcao)) return false;
        const linha = _inteiroCruz(p.linha), coluna = _inteiroCruz(p.coluna);
        if (linha === null || coluna === null) return false;
        vistos.add(p.item_id);
        const lista = casasDaPalavra(textos.get(p.item_id));
        if (!lista.length) return false;
        for (let k = 0; k < lista.length; k++) {
            const l = linha + (p.direcao === "v" ? k : 0), c = coluna + (p.direcao === "h" ? k : 0);
            if (l < 0 || c < 0 || l >= linhas || c >= colunas) return false;
            const outra = casas.get(_chave(l, c));
            if (outra && (outra.fixa || lista[k].fixa || outra.letra !== lista[k].letra || outra.direcao === p.direcao)) return false;
            casas.set(_chave(l, c), { ...lista[k], direcao: p.direcao });
        }
    }
    return vistos.size === textos.size;
}

// ---------------------------------------------------------------------------
// Gerador. Coloca as palavras mais longas primeiro, cruzando cada nova com uma
// letra igual; entre as posições possíveis fica com a grade mais compacta e
// mais perto de quadrada. Palavra que não cruza fica solta, com uma casa de
// margem. Repete com desempates sorteados e guarda a melhor que caiba em 15×15.
// ---------------------------------------------------------------------------

function _cabe(mapa, w, l0, c0, d, isolada) {
    const dl = d === "v" ? 1 : 0, dc = d === "h" ? 1 : 0, n = w.casas.length;
    if (mapa.has(_chave(l0 - dl, c0 - dc)) || mapa.has(_chave(l0 + dl * n, c0 + dc * n))) return false;
    let novas = 0, cruzadas = 0;
    for (let k = 0; k < n; k++) {
        const l = l0 + dl * k, c = c0 + dc * k, cs = w.casas[k], cel = mapa.get(_chave(l, c));
        if (cel) {
            if (isolada || cel.fixa || cs.fixa || cel.letra !== cs.letra || cel.direcoes.has(d)) return false;
            cruzadas++;
            continue;
        }
        novas++;
        if (mapa.has(_chave(l + dc, c + dl)) || mapa.has(_chave(l - dc, c - dl))) return false;
        if (isolada) {
            for (const [a, b] of [[-1, -1], [-1, 1], [1, -1], [1, 1]]) if (mapa.has(_chave(l + a, c + b))) return false;
        }
    }
    if (isolada) {
        // nem nas diagonais das pontas
        const antes = [l0 - dl, c0 - dc], depois = [l0 + dl * n, c0 + dc * n];
        for (const [l, c] of [antes, depois]) {
            if (mapa.has(_chave(l + dc, c + dl)) || mapa.has(_chave(l - dc, c - dl))) return false;
        }
    }
    return novas > 0 && (isolada || cruzadas > 0);
}

function _caixa(colocadas, extra) {
    let l1 = Infinity, c1 = Infinity, l2 = -Infinity, c2 = -Infinity;
    for (const p of extra ? [...colocadas, extra] : colocadas) {
        const n = p.w.casas.length;
        l1 = Math.min(l1, p.l); c1 = Math.min(c1, p.c);
        l2 = Math.max(l2, p.l + (p.d === "v" ? n - 1 : 0)); c2 = Math.max(c2, p.c + (p.d === "h" ? n - 1 : 0));
    }
    return { l1, c1, linhas: l2 - l1 + 1, colunas: c2 - c1 + 1 };
}

function _pontos(caixa) {
    return caixa.linhas * caixa.colunas + Math.abs(caixa.linhas - caixa.colunas) * 0.5;
}

function _colocar(mapa, w, l0, c0, d) {
    const dl = d === "v" ? 1 : 0, dc = d === "h" ? 1 : 0;
    w.casas.forEach((cs, k) => {
        const ch = _chave(l0 + dl * k, c0 + dc * k);
        const cel = mapa.get(ch) || { letra: cs.letra, fixa: cs.fixa, direcoes: new Set() };
        cel.direcoes.add(d);
        mapa.set(ch, cel);
    });
}

function _melhorPosicao(mapa, colocadas, w, candidatas, isolada, aleatorio) {
    const max = LIMITES_CRUZADINHA.maxGrade;
    let melhor = null;
    for (const [l, c, d] of candidatas) {
        if (!_cabe(mapa, w, l, c, d, isolada)) continue;
        const caixa = _caixa(colocadas, { w, l, c, d });
        if (caixa.linhas > max || caixa.colunas > max) continue;
        const pontos = _pontos(caixa) + aleatorio() * 0.25;
        if (!melhor || pontos < melhor.pontos) melhor = { l, c, d, pontos };
    }
    return melhor;
}

function _tentativaGrade(palavras, aleatorio) {
    const ordem = palavras.map(w => ({ w, r: aleatorio() }))
        .sort((a, b) => b.w.casas.length - a.w.casas.length || a.r - b.r).map(x => x.w);
    const mapa = new Map(), colocadas = [], soltas = [];
    const primeiraDir = aleatorio() < 0.5 ? "h" : "v";
    _colocar(mapa, ordem[0], 0, 0, primeiraDir);
    colocadas.push({ w: ordem[0], l: 0, c: 0, d: primeiraDir });
    for (const w of ordem.slice(1)) {
        const candidatas = [];
        for (const [ch, cel] of mapa) {
            if (cel.fixa) continue;
            const [l, c] = ch.split(",").map(Number);
            w.casas.forEach((cs, k) => {
                if (cs.fixa || cs.letra !== cel.letra) return;
                if (!cel.direcoes.has("h")) candidatas.push([l, c - k, "h"]);
                if (!cel.direcoes.has("v")) candidatas.push([l - k, c, "v"]);
            });
        }
        const pos = _melhorPosicao(mapa, colocadas, w, candidatas, false, aleatorio);
        if (pos) { _colocar(mapa, w, pos.l, pos.c, pos.d); colocadas.push({ w, ...pos }); }
        else soltas.push(w);
    }
    for (const w of soltas) {
        const caixa = _caixa(colocadas), n = w.casas.length, candidatas = [];
        for (let l = caixa.l1 - n - 1; l <= caixa.l1 + caixa.linhas + 1; l++) {
            for (let c = caixa.c1 - n - 1; c <= caixa.c1 + caixa.colunas + 1; c++) {
                candidatas.push([l, c, "h"], [l, c, "v"]);
            }
        }
        const pos = _melhorPosicao(mapa, colocadas, w, candidatas, true, aleatorio);
        if (!pos) return null;
        _colocar(mapa, w, pos.l, pos.c, pos.d);
        colocadas.push({ w, ...pos });
    }
    const caixa = _caixa(colocadas);
    const porId = new Map(colocadas.map(p => [p.w.id, p]));
    return {
        grade: {
            linhas: caixa.linhas, colunas: caixa.colunas,
            palavras: palavras.map(w => {
                const p = porId.get(w.id);
                return { item_id: w.id, linha: p.l - caixa.l1, coluna: p.c - caixa.c1, direcao: p.d };
            }),
        },
        soltas: soltas.map(w => w.id),
        pontos: [soltas.length, _pontos(caixa)],
    };
}

function montarGradeCruzadinha(itens, aleatorio = Math.random) {
    const palavras = (itens || []).map(it => ({ id: it.id, casas: casasDaPalavra(it.pergunta && it.pergunta.texto) }));
    if (!palavras.length || palavras.some(w => !w.casas.length)) return null;
    let melhor = null;
    for (let t = 0; t < TENTATIVAS_GRADE; t++) {
        const r = _tentativaGrade(palavras, aleatorio);
        if (!r) continue;
        if (!melhor || r.pontos[0] < melhor.pontos[0] || (r.pontos[0] === melhor.pontos[0] && r.pontos[1] < melhor.pontos[1])) melhor = r;
    }
    return melhor && { grade: melhor.grade, soltas: melhor.soltas };
}

// Número de cada palavra, pela ordem de leitura do começo dela.
function numerarGrade(grade, itens) {
    const palavras = palavrasDaGrade(grade, itens);
    const comecos = [...new Set(palavras.map(p => _chave(p.linha, p.coluna)))]
        .map(ch => ch.split(",").map(Number)).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(([l, c]) => _chave(l, c));
    const numeros = {};
    palavras.forEach(p => { numeros[p.item_id] = comecos.indexOf(_chave(p.linha, p.coluna)) + 1; });
    return numeros;
}

function problemasCruzadinha(conteudo, regras = {}) {
    const itens = (conteudo && conteudo.itens) || [];
    const problemas = [], vistas = new Set();
    itens.forEach((it, i) => {
        const texto = _textoCruz(it.pergunta && it.pergunta.texto);
        if (!texto) { problemas.push(`Figura ${i + 1}: falta a palavra.`); return; }
        const problema = problemaDaPalavraCruzadinha(texto);
        if (problema) problemas.push(`Figura ${i + 1}: ${problema}.`);
        const chave = _maiusculaCruz(texto);
        if (vistas.has(chave)) problemas.push(`Figura ${i + 1}: a palavra repete a de outra figura.`);
        vistas.add(chave);
    });
    if (!problemas.length && !conferirGrade(regras && regras.grade, itens)) {
        problemas.push("Não deu para montar a cruzadinha com essas palavras. Use palavras menores ou tire alguma figura.");
    }
    return problemas;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        LIMITES_CRUZADINHA, casasDaPalavra, contarLetras, problemaDaPalavraCruzadinha, palavrasDaGrade,
        conferirGrade, montarGradeCruzadinha, numerarGrade, problemasCruzadinha,
    };
}
