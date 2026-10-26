// ============================================================================
// acesso_util.js — Levar quem criou a senha para a tela de entrar (26/10/2026)
//
// As famílias guardavam o link de convite (que só funciona uma vez) como se
// fosse o endereço do app e caíam em "Link expirado ou já usado". Funções
// puras (testadas em frontend/tests/acesso_util.test.js) para as telas de
// views/login.js e para a mensagem pronta do WhatsApp (util.js).
// ============================================================================

// Por onde a equipe e as famílias da clínica entram: a tela de login própria
// (White Label) ou a comum.
function loginDaOrg(org) {
    const endereco = org && org.white_label_ativo && org.endereco_login;
    return endereco && /^[a-z0-9-]+$/i.test(endereco) ? `#/entrar/${endereco}` : "#/login";
}

// `loginRel` ("#/login" ou "#/entrar/x") + a base do app → link completo e um
// texto curto para mostrar ("app.pandaup.com.br" no login comum).
function enderecoLogin(loginRel, base) {
    const raiz = String(base || "").replace(/#.*$/, "").replace(/\/?$/, "/");
    const rel = loginRel || "#/login";
    const url = raiz + rel;
    const semProtocolo = url.replace(/^https?:\/\//, "");
    return { url, texto: rel === "#/login" ? semProtocolo.replace(/\/#\/login$/, "") : semProtocolo };
}

// Textos da tela quando o link de convite/nova senha não serve mais.
function telaLinkIndisponivel(motivo) {
    if (motivo === "usado") {
        return {
            icone: "✅",
            titulo: "Sua senha já foi criada!",
            texto: "Este link servia só para criar a senha e não funciona de novo. "
                + "Para entrar, use o botão abaixo com o seu e-mail e a senha que você criou.",
            botao: "Entrar no PandaUp",
        };
    }
    if (motivo === "expirado") {
        return {
            icone: "⏰",
            titulo: "Este link venceu",
            texto: "Os links de cadastro e de nova senha valem por 24 horas. "
                + "Se você já criou a sua senha, é só entrar. Se ainda não criou, peça um novo link à sua clínica.",
            botao: "Entrar no PandaUp",
        };
    }
    return {
        icone: "🔒",
        titulo: "Link inválido",
        texto: "Confira se o link foi copiado inteiro. Se você já criou a sua senha, é só entrar.",
        botao: "Entrar no PandaUp",
    };
}

// Mensagem pronta para o gestor colar no WhatsApp: o link de criar a senha
// (uso único) e o endereço de entrar depois.
function mensagemConviteWhatsapp({ nome, link, login, clinica } = {}) {
    const primeiro = String(nome || "").trim().split(/\s+/)[0];
    const saudacao = primeiro ? `Olá, ${primeiro}!` : "Olá!";
    const quem = clinica ? `A ${clinica} cadastrou você no app PandaUp.` : "Você foi cadastrado(a) no app PandaUp.";
    return `${saudacao} ${quem}\n\n`
        + `1️⃣ Para criar a sua senha, abra este link (ele funciona uma vez e vale por 24 horas):\n${link}\n\n`
        + `2️⃣ Depois, entre sempre por este endereço, com o seu e-mail e a senha que você criou:\n${login}\n\n`
        + `Dica: salve o endereço de entrar nos favoritos ou na tela inicial do celular.`;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { loginDaOrg, enderecoLogin, telaLinkIndisponivel, mensagemConviteWhatsapp };
}
