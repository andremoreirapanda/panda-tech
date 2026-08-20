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
        el.innerHTML = `<span>${icone}</span><span>${msg}</span>`;
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
