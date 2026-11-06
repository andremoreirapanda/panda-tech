// Pandoo (05/11/2026) — "Toque só no alvo": sorteio, mapeamento, fases e medidas.
const test = require("node:test");
const assert = require("node:assert/strict");
const a = require("../js/pandoo/alvo_core.js");
const p = require("../js/pandoo/pandoo_core.js");

const PNG = "iVBORw0KGgo=";
const item = (id, texto = id) => ({ id, pergunta: { texto, imagem: PNG, audio: null } });
const ITENS = [item("i0", "cachorro"), item("i1", "gato"), item("i2", "coelho"), item("i3", "pato")];
const ALVO = ITENS[0];
const PEG = ITENS[1];
// gerador simples e reproduzível
const semente = (s) => { let x = s * 9301 + 49297; return () => { x = (x * 9301 + 49297) % 233280; return x / 233280; }; };

function conferirSorteio(itens, n, s) {
    const lista = a.sortearFigurasAlvo(itens, "i0", n, semente(s));
    assert.equal(lista.length, n);
    assert.equal(lista.filter(i => i.id === "i0").length, Math.max(1, Math.round(n / 3)));
    assert.notEqual(lista[0].id, "i0");
    assert.ok(!lista.some((it, k) => k >= 2 && [0, 1, 2].every(d => lista[k - d].id === "i0")), "3 alvos seguidos");
    assert.ok(lista.every(it => itens.includes(it)));
}

test("sorteio: proporção, não começa por alvo, nunca 3 alvos seguidos", () => {
    for (let s = 1; s <= 50; s++) for (const n of [10, 20, 60]) conferirSorteio(ITENS, n, s);
});

test("sorteio com só 2 figuras ainda respeita as regras", () => {
    for (let s = 1; s <= 50; s++) conferirSorteio(ITENS.slice(0, 2), 10, s);
});

test("detalheAlvo aplica o mapeamento", () => {
    assert.deepEqual(a.detalheAlvo(ALVO, "i0", true, 1, 500),
        { item_id: "i0", texto: "cachorro", resultado: "conseguiu", alvo: true, tocou: true, fase: 1, tempo_ms: 500 });
    assert.equal(a.detalheAlvo(ALVO, "i0", false, 1).resultado, "treinar");
    assert.equal(a.detalheAlvo(ALVO, "i0", false, 1).tempo_ms, undefined);
    assert.equal(a.detalheAlvo(PEG, "i0", true, 1, 300).resultado, "treinar");
    assert.equal(a.detalheAlvo(PEG, "i0", true, 1, 300).tempo_ms, undefined);
    assert.equal(a.detalheAlvo(PEG, "i0", false, 1).resultado, "conseguiu");
});

const fase = (alvosTocados, alvosTotal, erros) => [
    ...Array.from({ length: alvosTotal }, (_, k) => a.detalheAlvo(ALVO, "i0", k < alvosTocados, 1, 400)),
    ...Array.from({ length: erros }, () => a.detalheAlvo(PEG, "i0", true, 1)),
    a.detalheAlvo(PEG, "i0", false, 1),
];
const BOA = fase(5, 5, 0);
const RUIM = fase(3, 5, 0);

test("avaliarFaseAlvo: ≥80% dos alvos e ≤1 toque errado", () => {
    assert.equal(a.avaliarFaseAlvo(fase(4, 5, 1)), true);
    assert.equal(a.avaliarFaseAlvo(fase(3, 5, 0)), false);
    assert.equal(a.avaliarFaseAlvo(fase(5, 5, 2)), false);
});

test("proximaFaseAlvo", () => {
    const r = { fase_inicio: 1, fase_fim: 3, subir_sozinho: true };
    assert.equal(a.proximaFaseAlvo(r, 1, BOA), 2);
    assert.equal(a.proximaFaseAlvo(r, 1, RUIM), null);
    assert.equal(a.proximaFaseAlvo({ ...r, subir_sozinho: false }, 1, RUIM), 2);
    assert.equal(a.proximaFaseAlvo(r, 3, BOA), null);
    assert.equal(a.proximaFaseAlvo({ ...r, fase_fim: 2 }, 2, BOA), null);
});

test("medidasAlvo igual ao backend", () => {
    const det = [a.detalheAlvo(ALVO, "i0", true, 1, 400), a.detalheAlvo(ALVO, "i0", true, 2, 800),
        a.detalheAlvo(ALVO, "i0", false, 2), a.detalheAlvo(PEG, "i0", true, 2), a.detalheAlvo(PEG, "i0", false, 1)];
    assert.deepEqual(a.medidasAlvo(det), { alvos_tocados: 2, alvos_total: 3, alvos_perdidos: 1,
        toques_errados: 1, tempo_medio_ms: 600, fase_alcancada: 2 });
    assert.equal(a.medidasAlvo([a.detalheAlvo(PEG, "i0", false, 1)]).tempo_medio_ms, null);
});

test("houveToqueAlvo e fraseComandoAlvo", () => {
    assert.equal(a.houveToqueAlvo([]), false);
    assert.equal(a.houveToqueAlvo([a.detalheAlvo(ALVO, "i0", false, 1)]), false);
    assert.equal(a.houveToqueAlvo([a.detalheAlvo(PEG, "i0", true, 1)]), true);
    assert.equal(a.fraseComandoAlvo({ frase_inicio: "Toque só na" }, { pergunta: { texto: "bola" } }), "Toque só na bola!");
    assert.equal(a.fraseComandoAlvo({}, { pergunta: { texto: "" } }), "Toque só no!");
});

test("problemasDoConteudo do alvo", () => {
    const conteudo = { versao: 1, itens: ITENS };
    assert.match(p.problemasDoConteudo("alvo", conteudo, {})[0], /Escolha qual figura é o alvo/);
    assert.deepEqual(p.problemasDoConteudo("alvo", conteudo, { alvo_item_id: "i0" }), []);
    const semPalavra = { versao: 1, itens: [item("i0", ""), PEG] };
    assert.deepEqual(p.problemasDoConteudo("alvo", semPalavra, { alvo_item_id: "i0" }),
        ["Figura 1: o alvo precisa da palavra ou da voz."]);
    const semImagem = { versao: 1, itens: [ALVO, { id: "x", pergunta: { texto: "x" } }] };
    assert.match(p.problemasDoConteudo("alvo", semImagem, { alvo_item_id: "i0" })[0], /Figura 2: falta a imagem/);
});

test("regras padrão do alvo no front iguais às do servidor", () => {
    assert.deepEqual(p.REGRAS_PADRAO_PANDOO.alvo, { alvo_item_id: null, frase_inicio: "Toque só no", fase_inicio: 1,
        fase_fim: 3, subir_sozinho: true, figuras_por_fase: 20, velocidade: "media", som: true });
});

// --- revisão final (05/11/2026) --------------------------------------------
test("reação começa quando a figura fica visível", () => {
    assert.equal(a.atrasoVisivelAlvo(1, 1500, 100, 400), 0);
    assert.equal(a.atrasoVisivelAlvo(2, 1700, 100, 400), 300);
    // fase 3: anda a própria largura (90 de 440 px) antes de aparecer
    assert.equal(a.atrasoVisivelAlvo(3, 3500, 90, 350), Math.round(3500 * 90 / 440));
    assert.equal(a.atrasoVisivelAlvo(3, 3500, 0, 0), 0);
});

test("resumo sem alvo não diz 0 de 0", () => {
    assert.equal(a.textoResumoAlvo({ alvos_tocados: 0, alvos_total: 0, toques_errados: 1 }).pegou, null);
    assert.deepEqual(a.textoResumoAlvo({ alvos_tocados: 3, alvos_total: 4, toques_errados: 0 }), { pegou: "3 de 4", segurou: true });
    assert.equal(a.textoResumoAlvo({ alvos_tocados: 3, alvos_total: 4, toques_errados: 2 }).segurou, false);
});

test("aviso sem toque vale para qualquer figura", () => {
    assert.doesNotMatch(a.AVISO_SEM_TOQUE_ALVO, /no alvo/);
    assert.match(a.AVISO_SEM_TOQUE_ALVO, /nenhuma figura/);
});
