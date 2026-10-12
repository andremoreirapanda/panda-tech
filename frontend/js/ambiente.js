// Faixa do ambiente de teste (spec PandaUp 12/10/2026). O servidor de
// homologação (AMBIENTE=homologacao) põe <meta name="ambiente"> no
// index.html; em produção a meta não existe e este arquivo não faz nada.
(function () {
    const meta = document.querySelector('meta[name="ambiente"]');
    if (!meta || meta.content !== "homologacao") return;
    function mostrarFaixa() {
        if (document.querySelector(".faixa-ambiente")) return;
        const faixa = document.createElement("div");
        faixa.className = "faixa-ambiente";
        faixa.setAttribute("role", "status");
        faixa.textContent = "AMBIENTE DE TESTE — dados fictícios";
        document.body.prepend(faixa);
        document.body.classList.add("com-faixa-ambiente");
    }
    if (document.body) mostrarFaixa();
    else document.addEventListener("DOMContentLoaded", mostrarFaixa);
})();
