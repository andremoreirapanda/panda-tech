// Pandoo (29/10/2026) — Cruzadinha: palavras, grade, gerador e partida.
const test = require("node:test");
const assert = require("node:assert/strict");
const c = require("../js/pandoo/cruzadinha_core.js");
const p = require("../js/pandoo/pandoo_core.js");

const PNG = "iVBORw0KGgo=";
const itens = (palavras) => palavras.map(t => ({ id: t.replace(/\W/g, ""), pergunta: { texto: t, imagem: PNG, audio: null } }));
const conteudo = (palavras) => ({ versao: 1, itens: itens(palavras) });
// gerador simples e reproduzível
const semente = (s) => { let x = s * 9301 + 49297; return () => { x = (x * 9301 + 49297) % 233280; return x / 233280; }; };

const PREVIA = ["casa", "gato", "ovo", "sapo", "sol", "lua"];
const GRADE_PREVIA = { linhas: 6, colunas: 4, palavras: [
    { item_id: "casa", linha: 0, coluna: 1, direcao: "v" }, { item_id: "gato", linha: 1, coluna: 0, direcao: "h" },
    { item_id: "ovo", linha: 1, coluna: 3, direcao: "v" }, { item_id: "sapo", linha: 3, coluna: 0, direcao: "h" },
    { item_id: "sol", linha: 3, coluna: 0, direcao: "v" }, { item_id: "lua", linha: 5, coluna: 0, direcao: "h" }] };
const DEZ = ["gato", "pato", "sapo", "bola", "casa", "janela", "boneca", "cavalo", "tomate", "sorvete"];

function mapaDaGrade(grade, its) {
    const mapa = new Map();
    c.palavrasDaGrade(grade, its).forEach(pl => pl.casas.forEach(cs => {
        const atual = mapa.get(cs.chave) || { letra: cs.letra, palavras: [] };
        atual.palavras.push(pl);
        mapa.set(cs.chave, atual);
    }));
    return mapa;
}

// Toda sequência de 2+ casas ocupadas numa linha (ou coluna) precisa ser exatamente uma palavra.
function sequenciasSaoPalavras(grade, its) {
    const mapa = mapaDaGrade(grade, its);
    const ocupada = (l, col) => mapa.has(`${l},${col}`);
    const palavras = c.palavrasDaGrade(grade, its);
    for (const [dl, dc, dir] of [[0, 1, "h"], [1, 0, "v"]]) {
        for (let l = 0; l < grade.linhas; l++) for (let col = 0; col < grade.colunas; col++) {
            if (!ocupada(l, col) || ocupada(l - dl, col - dc)) continue;
            let n = 0;
            while (ocupada(l + dl * n, col + dc * n)) n++;
            if (n < 2) continue;
            if (!palavras.some(pl => pl.direcao === dir && pl.linha === l && pl.coluna === col && pl.casas.length === n)) return false;
        }
    }
    return true;
}

test("casas da palavra: hífen e espaço são fixos, acento some", () => {
    assert.equal(c.casasDaPalavra("Pé-de-moça").map(x => x.letra).join(""), "PE-DE-MOCA");
    assert.deepEqual(c.casasDaPalavra("arco íris")[4], { letra: "", fixa: true });
    assert.deepEqual(c.casasDaPalavra("pé-de")[2], { letra: "-", fixa: true });
    assert.equal(c.contarLetras("guarda-chuva"), 11);
    assert.equal(c.contarLetras(" arco   íris "), 8);
});

test("problema da palavra", () => {
    assert.equal(c.problemaDaPalavraCruzadinha("gato1"), "Use só letras, hífen e espaço");
    assert.equal(c.problemaDaPalavraCruzadinha("-gato"), "Use só letras, hífen e espaço");
    assert.equal(c.problemaDaPalavraCruzadinha("BORBOLETINHAS"), "Use até 12 letras");
    assert.equal(c.problemaDaPalavraCruzadinha("a"), "Use pelo menos 2 letras");
    assert.equal(c.problemaDaPalavraCruzadinha("guarda-chuva"), null);
    assert.equal(c.problemaDaPalavraCruzadinha(""), null);
});

test("conferirGrade aceita a da prévia e recusa as quebradas", () => {
    assert.ok(c.conferirGrade(GRADE_PREVIA, itens(PREVIA)));
    assert.ok(!c.conferirGrade(null, itens(PREVIA)));
    const faltando = { ...GRADE_PREVIA, palavras: GRADE_PREVIA.palavras.slice(1) };
    assert.ok(!c.conferirGrade(faltando, itens(PREVIA)));
    const letraDiferente = { ...GRADE_PREVIA, palavras: GRADE_PREVIA.palavras.map(x => x.item_id === "ovo" ? { ...x, coluna: 2 } : x) };
    assert.ok(!c.conferirGrade(letraDiferente, itens(PREVIA)));
    assert.ok(!c.conferirGrade({ ...GRADE_PREVIA, colunas: 3 }, itens(PREVIA)));
    // acento no cruzamento vale
    assert.ok(c.conferirGrade({ linhas: 3, colunas: 4, palavras: [{ item_id: "égua", linha: 0, coluna: 0, direcao: "h" },
        { item_id: "ela", linha: 0, coluna: 0, direcao: "v" }] }, [{ id: "égua", pergunta: { texto: "ÉGUA" } }, { id: "ela", pergunta: { texto: "ela" } }]));
});

test("grade gerada sempre confere e cabe em 15×15", () => {
    for (const palavras of [["gato", "pato"], PREVIA, DEZ, ["guarda-chuva", "arco íris", "sapo"]]) {
        for (let s = 0; s < 15; s++) {
            const r = c.montarGradeCruzadinha(itens(palavras), semente(s));
            assert.ok(r, `${palavras} semente ${s}`);
            assert.ok(c.conferirGrade(r.grade, itens(palavras)), `${palavras} semente ${s}`);
            assert.ok(r.grade.linhas <= 15 && r.grade.colunas <= 15);
            assert.ok(sequenciasSaoPalavras(r.grade, itens(palavras)), `encostou: ${palavras} semente ${s}`);
        }
    }
});

test("as palavras da prévia se cruzam todas", () => {
    const r = c.montarGradeCruzadinha(itens(PREVIA), semente(3));
    assert.deepEqual(r.soltas, []);
});

test("palavras sem letra em comum ficam soltas e não encostam", () => {
    const its = itens(["sol", "uva"]);
    const r = c.montarGradeCruzadinha(its, semente(1));
    assert.equal(r.soltas.length, 1);
    const [a, b] = c.palavrasDaGrade(r.grade, its);
    for (const x of a.casas) for (const y of b.casas) {
        const [l1, c1] = x.chave.split(",").map(Number), [l2, c2] = y.chave.split(",").map(Number);
        assert.ok(Math.abs(l1 - l2) > 1 || Math.abs(c1 - c2) > 1, `${x.chave} encosta em ${y.chave}`);
    }
});

test("sem como caber em 15×15 → null", () => {
    const palavras = "ABCDEFGHIJ".split("").map(l => l.repeat(12));
    assert.equal(c.montarGradeCruzadinha(itens(palavras), semente(1)), null);
});

test("sortear com outro aleatório pode dar outra arrumação", () => {
    const vistas = new Set();
    for (let s = 0; s < 15; s++) vistas.add(JSON.stringify(c.montarGradeCruzadinha(itens(DEZ), semente(s)).grade));
    assert.ok(vistas.size > 1);
});

test("numeração em ordem de leitura; começo compartilhado tem o mesmo número", () => {
    assert.deepEqual(c.numerarGrade(GRADE_PREVIA, itens(PREVIA)), { casa: 1, gato: 2, ovo: 3, sapo: 4, sol: 4, lua: 5 });
});

test("problemasCruzadinha", () => {
    assert.deepEqual(c.problemasCruzadinha(conteudo(PREVIA), { grade: GRADE_PREVIA }), []);
    const ruim = conteudo(["gato1", "", "Gató", "gato"]);
    const pr = c.problemasCruzadinha(ruim, { grade: null });
    assert.ok(pr.includes("Figura 1: Use só letras, hífen e espaço."));
    assert.ok(pr.includes("Figura 2: falta a palavra."));
    assert.ok(pr.includes("Figura 4: a palavra repete a de outra figura."));
    assert.deepEqual(c.problemasCruzadinha(conteudo(PREVIA), { grade: null }),
        ["Não deu para montar a cruzadinha com essas palavras. Use palavras menores ou tire alguma figura."]);
});

test("problemasDoConteudo da cruzadinha usa o limite de 10 e a imagem", () => {
    const onze = conteudo("abcdefghijk".split("").map(l => "x" + l));
    assert.ok(p.problemasDoConteudo("cruzadinha", onze, {})[0].includes("2 a 10"));
    const semImagem = conteudo(PREVIA);
    semImagem.itens[0].pergunta.imagem = null;
    assert.ok(p.problemasDoConteudo("cruzadinha", semImagem, { grade: GRADE_PREVIA }).some(t => t.includes("Figura 1: falta a imagem")));
    assert.deepEqual(p.problemasDoConteudo("cruzadinha", conteudo(PREVIA), { grade: GRADE_PREVIA }), []);
});

test("limitesDoModelo", () => {
    assert.equal(p.limitesDoModelo("cruzadinha").maxItens, 10);
    assert.equal(p.limitesDoModelo("quiz").maxItens, 24);
    assert.deepEqual(p.REGRAS_PADRAO_PANDOO.cruzadinha,
        { formas: ["teclado", "letras"], primeira_letra: false, som: true, voz: true, voz_acertar: true, grade: null });
});
