// ============================================================================
// toast.js — Notificações rápidas (feedback do sistema)
// ============================================================================

const Toast = {
    _container() {
        let el = document.getElementById("toast-container");
        if (!el) {
            el = document.createElement("div");
            el.id = "toast-container";
            document.body.appendChild(el);
        }
        return el;
    },
    _mostrar(msg, tipo, icone) {
        const el = document.createElement("div");
        el.className = `toast ${tipo ? "toast-" + tipo : ""}`;
        // CORREÇÃO DE AUDITORIA (25/08/2026, achado do CodeQL): "msg" chega
        // aqui, sem exceção, a partir de Toast.erro(err.message) — e
        // err.message vem direto do campo "erro" da resposta da API (ver
        // api.js), texto que em pelo menos uma rota (o callback OAuth do
        // Google Agenda) é reconstruído a partir de um parâmetro da própria
        // requisição, sem exigir login. Sem este escapeHtml, isso era um XSS
        // explorável remotamente e sem autenticação (só mandar a vítima
        // clicar num link), capaz de ler o token de sessão do localStorage.
        // "icone" nunca vem de fora (é sempre um emoji fixo definido logo
        // abaixo), por isso não precisa de escape.
        el.innerHTML = `<span>${icone}</span><span>${escapeHtml(msg)}</span>`;
        this._container().appendChild(el);
        setTimeout(() => {
            el.style.transition = "opacity .3s ease";
            el.style.opacity = "0";
            setTimeout(() => el.remove(), 300);
        }, 3200);
    },
    sucesso(msg) { this._mostrar(msg, "sucesso", "✅"); },
    erro(msg) { this._mostrar(msg, "erro", "⚠️"); },
    info(msg) { this._mostrar(msg, "", "💬"); },
};

function confetes() {
    const container = document.createElement("div");
    container.className = "confete-container";
    const emojis = ["🎉", "⭐", "🎊", "✨", "🏆"];
    for (let i = 0; i < 24; i++) {
        const span = document.createElement("span");
        span.className = "confete-pedaco";
        span.textContent = emojis[Math.floor(Math.random() * emojis.length)];
        span.style.left = Math.random() * 100 + "%";
        span.style.animationDelay = (Math.random() * 0.4) + "s";
        span.style.fontSize = (14 + Math.random() * 16) + "px";
        container.appendChild(span);
    }
    document.body.appendChild(container);
    setTimeout(() => container.remove(), 2600);
}
