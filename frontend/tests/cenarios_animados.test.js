// White Label completo (25/09/2026): cenários animados compartilhados.
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const c = require("../js/cenarios_animados.js");

const base = { endereco_login: "enc", versao_imagens: "abc", tem_cenario_imagem: false };

test("fundos prontos com o tom certo", () => {
    assert.deepEqual(c.cenarioDoMundo({ ...base, mundo_fundo: "estrelas" }), { tipo: "estrelas", imagemUrl: null, tom: "claro" });
    assert.deepEqual(c.cenarioDoMundo({ ...base, mundo_fundo: "mar" }), { tipo: "mar", imagemUrl: null, tom: "escuro" });
    assert.deepEqual(c.cenarioDoMundo({}), { tipo: "estrelas", imagemUrl: null, tom: "claro" });
    assert.deepEqual(c.cenarioDoMundo(null), { tipo: "estrelas", imagemUrl: null, tom: "claro" });
    assert.equal(c.cenarioDoMundo({ mundo_fundo: "praia" }).tipo, "estrelas");
});

test("'pandoo' segue o cenário padrão dos jogos", () => {
    assert.equal(c.cenarioDoMundo({ ...base, mundo_fundo: "pandoo", pandoo_cenario_padrao: "espaco" }).tipo, "espaco");
    assert.equal(c.cenarioDoMundo({ ...base, mundo_fundo: "pandoo" }).tipo, "bambu");
});

test("imagem da clínica com URL versionada, ou estrelas sem imagem", () => {
    const org = { ...base, mundo_fundo: "clinica", tem_cenario_imagem: true, pandoo_cenario_tom: "escuro" };
    assert.deepEqual(c.cenarioDoMundo(org), { tipo: "clinica", imagemUrl: "/api/publico/clinica/enc/cenario?v=abc", tom: "escuro" });
    assert.equal(c.cenarioDoMundo({ ...org, tem_cenario_imagem: false }).tipo, "estrelas");
    assert.equal(c.cenarioDoMundo({ ...base, mundo_fundo: "pandoo", pandoo_cenario_padrao: "clinica" }).tipo, "estrelas");
    assert.equal(c.cenarioDoMundo({ ...org, pandoo_cenario_tom: null }).tom, "claro");
    assert.equal(c.cenarioDoMundo({ ...org, mundo_fundo: "pandoo", pandoo_cenario_padrao: "clinica" }).tipo, "clinica");
});

test("endereço com caractere estranho não entra na URL", () => {
    const org = { ...base, endereco_login: "a\"b", mundo_fundo: "clinica", tem_cenario_imagem: true };
    assert.equal(c.cenarioDoMundo(org).tipo, "estrelas");
});
