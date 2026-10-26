// Levar quem criou a senha para a tela de entrar (26/10/2026).
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const a = require("../js/acesso_util.js");

test("loginDaOrg: tela própria só com White Label e endereço", () => {
    assert.equal(a.loginDaOrg({ white_label_ativo: true, endereco_login: "clinica-sol" }), "#/entrar/clinica-sol");
    assert.equal(a.loginDaOrg({ white_label_ativo: false, endereco_login: "clinica-sol" }), "#/login");
    assert.equal(a.loginDaOrg({ white_label_ativo: true, endereco_login: "" }), "#/login");
    assert.equal(a.loginDaOrg(null), "#/login");
    assert.equal(a.loginDaOrg({ white_label_ativo: true, endereco_login: "x y<" }), "#/login");
});

test("enderecoLogin: link completo e texto curto para mostrar", () => {
    const base = "https://app.pandaup.com.br/";
    assert.deepEqual(a.enderecoLogin("#/login", base), { url: "https://app.pandaup.com.br/#/login", texto: "app.pandaup.com.br" });
    assert.deepEqual(a.enderecoLogin("#/entrar/clinica-sol", base),
        { url: "https://app.pandaup.com.br/#/entrar/clinica-sol", texto: "app.pandaup.com.br/#/entrar/clinica-sol" });
    assert.equal(a.enderecoLogin("", base).url, "https://app.pandaup.com.br/#/login");
});

test("telaLinkIndisponivel: usado leva a entrar; vencido e inválido também", () => {
    const usado = a.telaLinkIndisponivel("usado");
    assert.match(usado.titulo, /senha já foi criada/);
    assert.match(usado.texto, /só para criar a senha/);
    assert.equal(usado.botao, "Entrar no PandaUp");
    assert.match(a.telaLinkIndisponivel("expirado").titulo, /venceu/);
    assert.match(a.telaLinkIndisponivel("expirado").texto, /24 horas/);
    assert.match(a.telaLinkIndisponivel("qualquer").titulo, /inválido/);
});

test("mensagemConviteWhatsapp: os dois endereços e o aviso de uso único", () => {
    const m = a.mensagemConviteWhatsapp({ nome: "Ana Souza", link: "https://app.pandaup.com.br/#/redefinir-senha?token=x",
        login: "https://app.pandaup.com.br/#/login", clinica: "Clínica Sol" });
    assert.match(m, /^Olá, Ana!/);
    assert.match(m, /Clínica Sol/);
    assert.match(m, /redefinir-senha\?token=x/);
    assert.match(m, /funciona uma vez/);
    assert.match(m, /https:\/\/app\.pandaup\.com\.br\/#\/login/);
    assert.match(a.mensagemConviteWhatsapp({ nome: "", link: "L", login: "E" }), /^Olá!/);
});
