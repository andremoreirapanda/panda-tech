// ============================================================================
// Aviso de nova versão (09/10/2026). Quem deixa o app aberto (atalho na tela
// inicial do celular) pode passar dias sem recarregar: de tempos em tempos —
// e quando o app volta a ficar visível — compara a versão desta página (a
// <meta name="versao-app">, posta pelo servidor) com /api/versao e, se mudou,
// mostra uma faixa "Atualizar". Nunca recarrega sozinho (não perde o que a
// pessoa está digitando). Funções puras testadas em frontend/tests/versao_app.test.js.
// ============================================================================

const VERSAO_INTERVALO_MS = 5 * 60 * 1000;     // conferência periódica
const VERSAO_MINIMO_MS = 60 * 1000;            // nunca mais de uma vez por minuto

function deveConferirVersao(agoraMs, ultimaMs, intervaloMs) {
    return ultimaMs === null || ultimaMs === undefined || agoraMs - ultimaMs >= intervaloMs;
}

function haNovaVersao(versaoPagina, versaoServidor) {
    return !!versaoPagina && !!versaoServidor && versaoPagina !== versaoServidor;
}

function iniciarAvisoNovaVersao() {
    const meta = document.querySelector('meta[name="versao-app"]');
    const versaoPagina = meta ? meta.content : "";
    if (!versaoPagina) return;
    let ultima = null;
    let avisado = false;

    function mostrarFaixa() {
        if (avisado) return;
        avisado = true;
        const faixa = document.createElement("div");
        faixa.className = "faixa-nova-versao";
        faixa.setAttribute("role", "status");
        faixa.innerHTML = `<span>Há uma nova versão do app.</span>
            <button type="button" class="botao botao-sm botao-primario" id="btn-atualizar-versao">Atualizar</button>
            <button type="button" class="faixa-nova-versao-fechar" aria-label="Fechar aviso">✕</button>`;
        document.body.appendChild(faixa);
        faixa.querySelector("#btn-atualizar-versao").addEventListener("click", () => location.reload());
        faixa.querySelector(".faixa-nova-versao-fechar").addEventListener("click", () => faixa.remove());
    }

    async function conferir(intervaloMinimo) {
        if (avisado || document.visibilityState === "hidden") return;
        const agora = Date.now();
        if (!deveConferirVersao(agora, ultima, intervaloMinimo)) return;
        ultima = agora;
        try {
            const r = await fetch("/api/versao", { cache: "no-store" });
            if (!r.ok) return;
            const { versao } = await r.json();
            if (haNovaVersao(versaoPagina, versao)) mostrarFaixa();
        } catch (e) { /* sem internet: confere na próxima */ }
    }

    setInterval(() => conferir(VERSAO_INTERVALO_MS), VERSAO_INTERVALO_MS);
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") conferir(VERSAO_MINIMO_MS);
    });
    window.addEventListener("focus", () => conferir(VERSAO_MINIMO_MS));
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { deveConferirVersao, haNovaVersao };
} else if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciarAvisoNovaVersao);
    else iniciarAvisoNovaVersao();
}
