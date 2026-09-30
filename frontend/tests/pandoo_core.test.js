// Pandoo (25/09/2026) — regras puras do catálogo e da roleta.
const test = require("node:test");
const assert = require("node:assert/strict");
const p = require("../js/pandoo/pandoo_core.js");

const item = (id, texto = id, imagem = "iVBORw0KGgo=") => ({ id, pergunta: { texto, imagem, audio: null } });
const conteudo = (n) => ({ versao: 1, itens: Array.from({ length: n }, (_, i) => item(`i${i}`, `P${i}`)) });

test("catálogo registra e encontra jogos", () => {
    p.registrarJogo("teste", { nome: "Teste", iniciar() {} });
    assert.equal(p.jogoRegistrado("teste").nome, "Teste");
    assert.equal(p.jogoRegistrado("nao-existe"), null);
});

test("conteúdo vazio tem 2 itens com ids diferentes", () => {
    const c = p.conteudoVazioPandoo();
    assert.equal(c.versao, 1);
    assert.equal(c.itens.length, 2);
    assert.notEqual(c.itens[0].id, c.itens[1].id);
});

test("problemas do conteúdo da roleta", () => {
    assert.deepEqual(p.problemasDoConteudo("roleta", conteudo(3)), []);
    assert.ok(p.problemasDoConteudo("roleta", conteudo(1))[0].includes("2 a 24"));
    assert.ok(p.problemasDoConteudo("roleta", conteudo(25))[0].includes("2 a 24"));
    const c = conteudo(3);
    c.itens[1].pergunta.imagem = null;
    assert.ok(p.problemasDoConteudo("roleta", c).some(t => t.includes("Figura 2")));
});

test("roleta 'todas': cada figura sai uma vez e a partida termina", () => {
    const c = conteudo(3);
    const regras = { ...p.REGRAS_PADRAO_PANDOO.roleta };
    let e = p.estadoInicialRoleta(c);
    const saidas = [];
    while (!p.partidaTerminou(e, regras, c)) {
        const it = p.sortearItemRoleta(e, c, () => 0);
        saidas.push(it.id);
        e = p.registrarRodada(e, it, "conseguiu", c);
    }
    assert.deepEqual([...saidas].sort(), ["i0", "i1", "i2"]);
    assert.equal(e.rodadas, 3);
});

test("roleta 'giros' maior que o número de figuras: repete só depois de sair todas", () => {
    const c = conteudo(2);
    const regras = { ...p.REGRAS_PADRAO_PANDOO.roleta, fim: "giros", giros: 5 };
    let e = p.estadoInicialRoleta(c);
    const saidas = [];
    while (!p.partidaTerminou(e, regras, c)) {
        const it = p.sortearItemRoleta(e, c, () => 0);
        saidas.push(it.id);
        e = p.registrarRodada(e, it, "treinar", c);
    }
    assert.equal(saidas.length, 5);
    assert.notEqual(saidas[0], saidas[1]); // as duas primeiras são diferentes
});

test("partida encerrada antes de girar: 0 rodadas", () => {
    const e = p.estadoInicialRoleta(conteudo(3));
    assert.equal(e.rodadas, 0);
    assert.deepEqual(p.resumoPartida(e.detalhes), { conseguiu: 0, treinar: 0 });
});

test("resumo da partida", () => {
    const d = [{ resultado: "conseguiu" }, { resultado: "treinar" }, { resultado: "conseguiu" }];
    assert.deepEqual(p.resumoPartida(d), { conseguiu: 2, treinar: 1 });
});

test("mime da imagem e do áudio pelo início do base64", () => {
    assert.equal(p.mimeDaImagem("/9j/4AAQ"), "image/jpeg");
    assert.equal(p.mimeDaImagem("iVBORw0KGgo"), "image/png");
    assert.equal(p.mimeDaImagem("UklGRiQAAABXRUJQ"), "image/webp");
    assert.equal(p.mimeDaImagem("R0lGODlh"), "image/gif");
    assert.equal(p.mimeDoAudio(Buffer.from("ID3\x03\x00").toString("base64")), "audio/mpeg");
    assert.equal(p.mimeDoAudio(Buffer.from("OggS\x00").toString("base64")), "audio/ogg");
    assert.equal(p.mimeDoAudio(Buffer.from("RIFF\x00\x00\x00\x00WAVE").toString("base64")), "audio/wav");
    assert.equal(p.mimeDoAudio(Buffer.from([0x1a, 0x45, 0xdf, 0xa3, 0, 0]).toString("base64")), "audio/webm");
    assert.equal(p.mimeDoAudio(Buffer.from("\x00\x00\x00\x20ftypM4A ").toString("base64")), "audio/mp4");
});

test("cenário efetivo segue a mesma regra do backend", () => {
    const org = { pandoo_cenario_padrao: "clinica", pandoo_cenario_imagem: "AAA", pandoo_cenario_tom: "claro" };
    assert.deepEqual(p.cenarioEfetivoPandoo(null, org), { tipo: "clinica", imagem: "AAA", tom: "claro" });
    assert.deepEqual(p.cenarioEfetivoPandoo("mar", org), { tipo: "mar", imagem: null, tom: "escuro" });
    assert.deepEqual(p.cenarioEfetivoPandoo("clinica", { pandoo_cenario_padrao: "bambu" }), { tipo: "bambu", imagem: null, tom: "escuro" });
    assert.deepEqual(p.cenarioEfetivoPandoo(null, {}), { tipo: "bambu", imagem: null, tom: "escuro" });
});

test("cenário para o palco (montarCenarioAnimado)", () => {
    assert.deepEqual(p.cenarioParaPalco({ tipo: "mar", imagem: null, tom: "escuro" }), { tipo: "mar", imagemUrl: null, tom: "escuro" });
    assert.deepEqual(p.cenarioParaPalco({ tipo: "clinica", imagem: "iVBORw0KGgo", tom: "claro" }),
        { tipo: "clinica", imagemUrl: "data:image/png;base64,iVBORw0KGgo", tom: "claro" });
    assert.deepEqual(p.cenarioParaPalco({ tipo: "clinica", imagem: null, tom: "claro" }), { tipo: "bambu", imagemUrl: null, tom: "escuro" });
    assert.deepEqual(p.cenarioParaPalco(null), { tipo: "bambu", imagemUrl: null, tom: "escuro" });
});

// Ajustes (26/09/2026): pequenos pontos da revisão.
test("conteúdo acima de 10 MB é avisado antes de enviar", () => {
    const c = conteudo(2);
    c.itens[0].pergunta.audio = "A".repeat(11 * 1024 * 1024);
    assert.ok(p.problemasDoConteudo("roleta", c).some(t => t.includes("10 MB")));
});

test("cenário com imagem que não é base64 cai no bambuzal", () => {
    assert.deepEqual(p.cenarioParaPalco({ tipo: "clinica", imagem: 'x") ; background:url(http://mau', tom: "claro" }),
        { tipo: "bambu", imagemUrl: null, tom: "escuro" });
});

// Pandoo fase 2 (30/09/2026): Quiz.
const q = (id, texto, dist = []) => ({ id, pergunta: { texto, imagem: "iVBORw0KGgo=", audio: null }, distratores: dist });
const cq = (...itens) => ({ versao: 1, itens });

test("quiz: opções no modo ouvir são figuras de outros itens, com a certa", () => {
    const c = cq(q("a", "Rato"), q("b", "Rosa"), q("c", "Robô"), q("d", "Leão"));
    const ops = p.opcoesDaPergunta(c.itens[0], c, { modo: "ouvir", opcoes: 3 }, () => 0.5);
    assert.equal(ops.length, 3);
    assert.equal(ops.filter(o => o.certa).length, 1);
    assert.equal(ops.find(o => o.certa).item_id, "a");
    assert.ok(ops.every(o => o.imagem));
    assert.equal(new Set(ops.map(o => o.item_id)).size, 3);
});

test("quiz: modo ver usa distratores próprios primeiro e não repete palavra", () => {
    const c = cq(q("a", "Rato", ["Pato", "rato", "Gato"]), q("b", "Rosa"), q("c", "Robô"));
    const ops = p.opcoesDaPergunta(c.itens[0], c, { modo: "ver", opcoes: 4 }, () => 0.1);
    const textos = ops.map(o => o.texto);
    assert.equal(ops.length, 4);
    assert.ok(textos.includes("Rato") && textos.includes("Pato") && textos.includes("Gato"));
    assert.equal(new Set(textos.map(p.normalizarPalavra)).size, 4);
    assert.equal(ops.filter(o => o.certa).length, 1);
});

test("quiz: normalizarPalavra ignora acento, caixa e espaços", () => {
    assert.equal(p.normalizarPalavra(" Robô "), "robo");
    assert.equal(p.normalizarPalavra(null), "");
});

test("quiz: poucos itens → usa o que existe", () => {
    const c = cq(q("a", "Rato"), q("b", "Rosa"));
    assert.equal(p.opcoesDaPergunta(c.itens[0], c, { modo: "ouvir", opcoes: 4 }).length, 2);
    const iguais = cq(q("a", "Rato"), q("b", "rato"));
    assert.equal(p.opcoesDaPergunta(iguais.itens[0], iguais, { modo: "ver", opcoes: 3 }).length, 1);
});

test("quiz: ordem sem repetir e fim por 'todas' / 'perguntas'", () => {
    const c = cq(q("a", "A"), q("b", "B"));
    let e = p.estadoInicialQuiz(c);
    const vistos = [];
    while (!p.quizTerminou(e, { fim: "todas" }, c)) {
        const it = p.proximaPerguntaQuiz(e, c, () => 0);
        vistos.push(it.id);
        e = p.registrarRespostaQuiz(e, it, vistos.length === 1 ? 0 : 2, c);
    }
    assert.deepEqual([...vistos].sort(), ["a", "b"]);
    assert.deepEqual(e.detalhes.map(d => d.resultado), ["conseguiu", "treinar"]);
    let f = p.estadoInicialQuiz(c);
    const seq = [];
    while (!p.quizTerminou(f, { fim: "perguntas", perguntas: 5 }, c)) {
        const it = p.proximaPerguntaQuiz(f, c, () => 0);
        seq.push(it.id);
        f = p.registrarRespostaQuiz(f, it, 0, c);
    }
    assert.equal(seq.length, 5);
    for (let i = 1; i < seq.length; i++) assert.notEqual(seq[i], seq[i - 1]);
});

test("quiz: problemas por modo", () => {
    const c = cq(q("a", ""), q("b", "Rosa"));
    assert.ok(p.problemasDoConteudo("quiz", c, { modo: "ver" }).some(t => t.includes("Figura 1")));
    assert.ok(p.problemasDoConteudo("quiz", c, { modo: "ouvir" }).some(t => t.includes("Figura 1")));
    c.itens[0].pergunta.audio = "SUQz";
    assert.equal(p.problemasDoConteudo("quiz", c, { modo: "ouvir" }).length, 0);
    c.itens[1].pergunta.imagem = null;
    assert.ok(p.problemasDoConteudo("quiz", c, {}).some(t => t.includes("Figura 2: falta a imagem")));
});
