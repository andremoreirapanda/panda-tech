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

// ---------------------------------------------------------------------------
// Partida
// ---------------------------------------------------------------------------
const P = c.palavrasDaGrade(GRADE_PREVIA, itens(PREVIA));
const E0 = c.estadoInicialCruzadinha(P);

function digitar(estado, escolhida, chaves, letras) {
    let r = { estado, feitas: [] };
    const todas = [];
    chaves.forEach((ch, i) => { r = c.colocarLetraCruzadinha(P, r.estado, escolhida, ch, letras[i]); todas.push(...r.feitas); });
    return { ...r, todasFeitas: todas };
}

test("tocar no número escolhe a palavra que começa nele (caso do usuário)", () => {
    assert.equal(c.palavraAoTocar(P, E0, "gato", "1,3", null), "ovo");
    assert.equal(c.palavraAoTocar(P, E0, "ovo", "1,3", "1,3"), "gato");
});

test("começo compartilhado alterna a cada toque", () => {
    assert.equal(c.palavraAoTocar(P, E0, "sapo", "3,0", "3,0"), "sol");
    assert.equal(c.palavraAoTocar(P, E0, "sol", "3,0", "3,0"), "sapo");
    assert.equal(c.palavraAoTocar(P, E0, null, "3,0", null), "sapo");
});

test("casa de outra palavra aberta escolhe essa palavra", () => {
    assert.equal(c.palavraAoTocar(P, E0, "gato", "2,1", null), "casa");
    assert.equal(c.palavraAoTocar(P, E0, "gato", "1,2", "1,0"), "gato");
});

test("casa de palavra feita: escolhe a cruzada aberta ou null", () => {
    const { estado } = digitar(E0, "gato", ["1,0", "1,1", "1,2", "1,3"], "GATO");
    assert.equal(c.palavraAoTocar(P, estado, null, "1,1", null), "casa");
    assert.equal(c.palavraAoTocar(P, estado, null, "1,2", null), null);
});

test("letra certa avança e a palavra completa vira feita com conseguiu", () => {
    let r = c.colocarLetraCruzadinha(P, E0, "gato", "1,0", "G");
    assert.equal(r.proxima, "1,1");
    assert.equal(E0.letras["1,0"], undefined, "o estado anterior não muda");
    r = digitar(E0, "gato", ["1,0", "1,1", "1,2", "1,3"], "GATO");
    assert.deepEqual(r.todasFeitas, [{ item_id: "gato", resultado: "conseguiu" }]);
    assert.equal(r.proxima, null);
    assert.ok(r.estado.travadas["1,2"]);
    assert.equal(c.primeiraCasaAberta(P.find(x => x.item_id === "casa"), r.estado), "0,1");
});

test("palavra errada limpa só as erradas e soma erro → treinar", () => {
    let r = digitar(E0, "gato", ["1,0", "1,1", "1,2", "1,3"], "GAXO");
    assert.equal(r.errou, true);
    assert.deepEqual(r.limpar, ["1,2"]);
    assert.deepEqual([r.estado.letras["1,0"], r.estado.letras["1,1"], r.estado.letras["1,2"], r.estado.letras["1,3"]], ["G", "A", undefined, "O"]);
    assert.equal(r.proxima, "1,2");
    r = c.colocarLetraCruzadinha(P, r.estado, "gato", "1,2", "T");
    assert.deepEqual(r.feitas, [{ item_id: "gato", resultado: "treinar" }]);
    assert.equal(c.resultadoDaPalavra(r.estado, "gato"), "treinar");
});

test("letra que completa a cruzada certa faz a cruzada; errada não conta erro", () => {
    const base = digitar(E0, "casa", ["0,1", "2,1", "3,1"], "CSA").estado;
    let r = c.colocarLetraCruzadinha(P, base, "gato", "1,0", "G");
    r = c.colocarLetraCruzadinha(P, r.estado, "gato", "1,1", "A");
    assert.deepEqual(r.feitas, [{ item_id: "casa", resultado: "conseguiu" }]);
    let e = c.colocarLetraCruzadinha(P, base, "gato", "1,0", "G").estado;
    r = c.colocarLetraCruzadinha(P, e, "gato", "1,1", "E");
    assert.equal(r.errou, false);
    assert.deepEqual(r.feitas, []);
    assert.equal(r.estado.letras["1,1"], "E");
    assert.equal(r.estado.erros.casa || 0, 0);
});

test("acento: É digitado vale E", () => {
    assert.deepEqual(c.letrasDoInput("é"), ["E"]);
    assert.deepEqual(c.letrasDoInput("ç"), ["C"]);
});

test("input do Android com várias letras e lixo", () => {
    assert.deepEqual(c.letrasDoInput("Ga to!1"), ["G", "A", "T", "O"]);
    assert.deepEqual(c.letrasDoInput(""), []);
});

test("apagar limpa a casa da vez ou volta uma casa", () => {
    let e = digitar(E0, "gato", ["1,0", "1,1"], "GA").estado;
    let r = c.apagarLetraCruzadinha(P, e, "gato", "1,2");
    assert.equal(r.ativa, "1,1");
    assert.equal(r.estado.letras["1,1"], undefined);
    r = c.apagarLetraCruzadinha(P, r.estado, "gato", "1,0");
    assert.equal(r.ativa, "1,0");
    assert.equal(r.estado.letras["1,0"], undefined);
});

test("hífen é casa fixa e o cursor pula", () => {
    const its = [{ id: "pede", pergunta: { texto: "pé-de" } }];
    const pl = c.palavrasDaGrade({ linhas: 1, colunas: 5, palavras: [{ item_id: "pede", linha: 0, coluna: 0, direcao: "h" }] }, its);
    let e = c.estadoInicialCruzadinha(pl);
    assert.ok(e.travadas["0,2"]);
    let r = c.colocarLetraCruzadinha(pl, e, "pede", "0,0", "P");
    r = c.colocarLetraCruzadinha(pl, r.estado, "pede", "0,1", "E");
    assert.equal(r.proxima, "0,3");
    r = c.colocarLetraCruzadinha(pl, r.estado, "pede", "0,3", "D");
    r = c.colocarLetraCruzadinha(pl, r.estado, "pede", "0,4", "E");
    assert.deepEqual(r.feitas, [{ item_id: "pede", resultado: "conseguiu" }]);
    assert.equal(c.contarLetras("pé-de"), 4);
});

test("banco de letras: as que faltam + 2 de fora", () => {
    const gato = P.find(x => x.item_id === "gato");
    const e = digitar(E0, "gato", ["1,0"], "G").estado;
    const banco = c.bancoDeLetras(gato, e, semente(2));
    assert.equal(banco.length, 5);
    assert.deepEqual(banco.filter(l => "GATO".includes(l)).sort(), ["A", "O", "T"]);
    assert.equal(banco.filter(l => !"GATO".includes(l)).length, 2);
});

test("opções de figura: a certa + 2, só 2 com 2 figuras", () => {
    const ops = c.opcoesFigurasCruzadinha("gato", P, E0, semente(4));
    assert.equal(ops.length, 3);
    assert.ok(ops.some(o => o.id === "gato"));
    assert.equal(new Set(ops.map(o => o.id)).size, 3);
    const dois = c.palavrasDaGrade({ linhas: 4, colunas: 4, palavras: [{ item_id: "gato", linha: 0, coluna: 0, direcao: "h" },
        { item_id: "pato", linha: 0, coluna: 1, direcao: "v" }] }, itens(["gato", "pato"]));
    assert.equal(c.opcoesFigurasCruzadinha("gato", dois, c.estadoInicialCruzadinha(dois), semente(1)).length, 2);
});

test("forma figuras: escrever a palavra e errar figura antes", () => {
    let e = c.registrarErroCruzadinha(E0, "ovo");
    const r = c.escreverPalavraCruzadinha(P, e, "ovo");
    assert.deepEqual(r.feitas, [{ item_id: "ovo", resultado: "treinar" }]);
    assert.equal(r.estado.letras["2,3"], "V");
});

test("trocar de forma limpa as soltas e mantém as feitas", () => {
    let e = digitar(E0, "gato", ["1,0", "1,1", "1,2", "1,3"], "GATO").estado;
    e = digitar(e, "lua", ["5,0"], "L").estado;
    const limpo = c.limparSoltasCruzadinha(e);
    assert.equal(limpo.letras["5,0"], undefined);
    assert.equal(limpo.letras["1,0"], "G");
    assert.deepEqual(limpo.feitas, ["gato"]);
});

test("terminou quando todas feitas", () => {
    let e = E0;
    for (const pl of P) e = c.escreverPalavraCruzadinha(P, e, pl.item_id).estado;
    assert.ok(c.cruzadinhaTerminou(P, e));
    assert.ok(!c.cruzadinhaTerminou(P, E0));
});

test("revisão: grade com palavras encostadas não vale", () => {
    const its = itens(["gatos", "pato"]);
    const g = (pal) => ({ linhas: 2, colunas: 10, palavras: pal.map(([id, l, col, d]) => ({ item_id: id, linha: l, coluna: col, direcao: d })) });
    assert.ok(!c.conferirGrade(g([["gatos", 0, 0, "h"], ["pato", 0, 5, "h"]]), its));
    assert.ok(!c.conferirGrade(g([["gatos", 0, 0, "h"], ["pato", 1, 0, "h"]]), its));
    assert.ok(c.conferirGrade(g([["gatos", 0, 0, "h"], ["pato", 0, 6, "h"]]), its));
});

test("revisão: palavra cruzada feita durante uma tentativa errada volta em feitas", () => {
    // GATO deitada em (0,0) e TIA em pé em (0,2): TIA pronta menos o T; GATO digitada G,X,O e T no cruzamento.
    const its = itens(["gato", "tia"]);
    const pl = c.palavrasDaGrade({ linhas: 3, colunas: 4, palavras: [{ item_id: "gato", linha: 0, coluna: 0, direcao: "h" },
        { item_id: "tia", linha: 0, coluna: 2, direcao: "v" }] }, its);
    let e = c.estadoInicialCruzadinha(pl);
    e = c.colocarLetraCruzadinha(pl, e, "tia", "1,2", "I").estado;
    e = c.colocarLetraCruzadinha(pl, e, "tia", "2,2", "A").estado;
    for (const [ch, l] of [["0,0", "G"], ["0,1", "X"], ["0,3", "O"]]) e = c.colocarLetraCruzadinha(pl, e, "gato", ch, l).estado;
    const r = c.colocarLetraCruzadinha(pl, e, "gato", "0,2", "T");
    assert.equal(r.errou, true);
    assert.deepEqual(r.feitas, [{ item_id: "tia", resultado: "conseguiu" }]);
});

test("revisão: diferença do campo do teclado (composição do Android)", () => {
    assert.deepEqual(c.diferencaDoInput(" ", " g"), { letras: ["G"], apagar: 0 });
    assert.deepEqual(c.diferencaDoInput(" g", " ga"), { letras: ["A"], apagar: 0 });      // composição: só a letra nova
    assert.deepEqual(c.diferencaDoInput(" ", " Gato"), { letras: ["G", "A", "T", "O"], apagar: 0 });
    assert.deepEqual(c.diferencaDoInput(" ", ""), { letras: [], apagar: 1 });              // apagou o espaço sentinela
    assert.deepEqual(c.diferencaDoInput(" ga", " g"), { letras: [], apagar: 1 });
    assert.deepEqual(c.diferencaDoInput(" gato", " gado"), { letras: ["D", "O"], apagar: 2 }); // autocorreção trocou o fim
    assert.deepEqual(c.diferencaDoInput(" ", " 1!"), { letras: [], apagar: 0 });
});
