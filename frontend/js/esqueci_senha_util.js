// Tela de confirmação do "Esqueci minha senha" (13/10/2026). Função pura,
// testada em frontend/tests/esqueci_senha_util.test.js; a tela fica em
// views/login.js. O texto é o mesmo para qualquer e-mail (não revela se a
// conta existe) — mostrar o e-mail digitado ajuda a pessoa a ver um erro.

function textoValidade(minutos) {
    if (!minutos) return "";
    if (minutos % 60 === 0) {
        const horas = minutos / 60;
        return ` O link vale por ${horas} hora${horas > 1 ? "s" : ""}.`;
    }
    return ` O link vale por ${minutos} minutos.`;
}

function confirmacaoEsqueciSenha(email, resposta) {
    const r = resposta || {};
    if (r.canal !== "email") {
        return { porEmail: false, icone: "🏥", titulo: "Peça um novo link à sua clínica", texto: r.mensagem || "", dicas: [] };
    }
    return {
        porEmail: true,
        icone: "📧",
        titulo: "Confira seu e-mail",
        texto: `Se ${email} estiver cadastrado, você vai receber um link em alguns minutos.${textoValidade(r.validade_minutos)}`,
        dicas: [
            "Confira a caixa de spam.",
            "Veja se o e-mail acima está certo (o mesmo que a clínica cadastrou).",
            "Se ainda assim não chegar, peça um novo link de acesso à sua clínica.",
        ],
    };
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { confirmacaoEsqueciSenha };
}
