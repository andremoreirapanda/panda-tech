// ============================================================================
// modais.js — comportamento comum dos pop-ups de preenchimento (26/09/2026)
//
// Pedido do usuário: um pop-up com campos só fecha pelos botões (Salvar,
// Cancelar) ou por um X no alto — clicar fora não fecha mais. Fechado pelo X,
// o que foi digitado vira rascunho e volta quando o mesmo pop-up for aberto de
// novo (na mesma tela). Salvar/Cancelar (qualquer outro jeito de fechar)
// descartam o rascunho. Vale para todo `.modal-fundo` que tenha campos; os
// sem campos (comemoração, confirmações) continuam como estavam.
// Funções puras testadas em frontend/tests/modais.test.js.
// ============================================================================

const _rascunhosModais = {};

// Campos que entram no rascunho (senha e arquivo nunca).
function camposDoModal(modal) {
    return [...modal.querySelectorAll("input, select, textarea")]
        .filter(c => !["hidden", "file", "password", "button", "submit"].includes(c.type));
}

function valoresDosCampos(campos) {
    return campos.map(c => (c.type === "checkbox" || c.type === "radio") ? c.checked : c.value);
}

function valoresMudaram(iniciais, atuais) {
    return JSON.stringify(iniciais) !== JSON.stringify(atuais);
}

function chaveDoModal(modal, hash) {
    const titulo = modal.querySelector("h1, h2, h3");
    return `${String(hash || "").split("?")[0]}|${titulo ? titulo.textContent.trim() : ""}`;
}

function _ehBotaoFechar(b) {
    const t = b.textContent.trim();
    return ["×", "✕", "✖"].includes(t) || /fechar/i.test(b.getAttribute("aria-label") || "");
}

function _prepararModal(modal) {
    if (modal.dataset.modalPreparado) return;
    if (!camposDoModal(modal).length) return;
    modal.dataset.modalPreparado = "1";
    modal.dataset.modalFormulario = "1";
    const caixa = modal.querySelector(".modal-caixa") || modal.firstElementChild || modal;
    let x = [...caixa.querySelectorAll("button")].find(_ehBotaoFechar);
    if (!x) {
        x = document.createElement("button");
        x.type = "button";
        x.className = "modal-x";
        x.setAttribute("aria-label", "Fechar");
        x.textContent = "✕";
        if (getComputedStyle(caixa).position === "static") caixa.style.position = "relative";
        caixa.prepend(x);
        x.addEventListener("click", () => modal.remove());
    }
    // Marca antes do handler que remove o modal (listeners do alvo rodam em ordem).
    x.addEventListener("click", () => { modal.dataset.fechadoPeloX = "1"; }, true);

    const chave = chaveDoModal(modal, location.hash);
    modal.dataset.chaveRascunho = chave;
    modal._valoresIniciais = valoresDosCampos(camposDoModal(modal));
    const rascunho = _rascunhosModais[chave];
    if (rascunho) {
        const campos = camposDoModal(modal);
        if (campos.length === rascunho.length) {
            campos.forEach((c, i) => {
                if (c.type === "checkbox" || c.type === "radio") c.checked = rascunho[i];
                else c.value = rascunho[i];
                c.dispatchEvent(new Event("input", { bubbles: true }));
                c.dispatchEvent(new Event("change", { bubbles: true }));
            });
            const aviso = document.createElement("p");
            aviso.className = "texto-xs modal-aviso-rascunho";
            aviso.textContent = "✏️ Rascunho recuperado — continue de onde parou.";
            (caixa.querySelector("h1, h2, h3") || x).insertAdjacentElement("afterend", aviso);
        }
    }
}

function _modalSaiu(modal) {
    if (!modal.dataset.modalFormulario) return;
    const chave = modal.dataset.chaveRascunho;
    const atuais = valoresDosCampos(camposDoModal(modal));
    if (modal.dataset.fechadoPeloX && valoresMudaram(modal._valoresIniciais || [], atuais)) {
        _rascunhosModais[chave] = atuais;
    } else {
        delete _rascunhosModais[chave];
    }
}

if (typeof document !== "undefined" && typeof MutationObserver !== "undefined") {
    new MutationObserver((mutacoes) => {
        for (const m of mutacoes) {
            m.addedNodes.forEach(n => {
                if (n.nodeType === 1 && n.classList.contains("modal-fundo")) {
                    _prepararModal(n);
                    // Alguns pop-ups montam os campos logo depois de abrir.
                    setTimeout(() => { if (n.isConnected) _prepararModal(n); }, 300);
                }
            });
            m.removedNodes.forEach(n => {
                if (n.nodeType === 1 && n.classList && n.classList.contains("modal-fundo")) _modalSaiu(n);
            });
        }
    }).observe(document.body, { childList: true });

    // Clicar fora (no fundo escuro) não fecha pop-up de preenchimento.
    document.addEventListener("click", (e) => {
        const alvo = e.target;
        if (alvo && alvo.classList && alvo.classList.contains("modal-fundo") && alvo.dataset.modalFormulario) {
            e.stopPropagation();
        }
    }, true);
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { valoresDosCampos, valoresMudaram, chaveDoModal };
}
