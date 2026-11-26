// Texto legível sobre o fundo escuro da clínica (White Label, 25/11/2026).
//
// Com o "Fundo da clínica" escuro (Bambuzal, Fundo do mar, Espaço, cor escura
// ou imagem escura — body[data-tom-fundo="escuro"]), o texto que fica direto
// sobre o fundo, fora de cartão, botão, campo ou tabela, precisa ficar branco.
// Antes isso era uma lista de seletores presa à profundidade do HTML
// (".shell-conteudo > .surgir > h3"), que não pegava o topo da Agenda, blocos
// do Dashboard nem a tela do celular da família (.shell-mobile-conteudo).
//
// Aqui a decisão usa o fundo CALCULADO pelo navegador: a varredura desce a
// partir do #app e para em qualquer elemento com fundo próprio (cor quase cheia,
// degradê ou imagem) — o que está dentro dele não muda. O elemento com texto
// que sobra, sem nada por trás além do fundo da clínica, ganha a classe
// "sobre-fundo-escuro" (cor no layout.css). Vale para qualquer tela, inclusive
// as que ainda vão existir, sem mexer em cada uma.

const CLASSE_SOBRE_FUNDO = "sobre-fundo-escuro";
const ALFA_SUPERFICIE = 0.6;

// Fundo próprio que esconde o fundo da clínica? (valores do getComputedStyle)
function superficieOpaca(corFundo, imagemFundo) {
    if (imagemFundo && imagemFundo !== "none") return true;
    const cor = String(corFundo || "").trim().toLowerCase();
    if (!cor || cor === "transparent") return false;
    const nums = cor.match(/[\d.]+%?/g);
    if (!nums || nums.length < 3) return false;
    if (nums.length < 4) return true;
    const a = nums[3];
    const alfa = a.endsWith("%") ? parseFloat(a) / 100 : parseFloat(a);
    return alfa >= ALFA_SUPERFICIE;
}

// O elemento tem texto visível escrito nele mesmo (não só nos filhos)?
function temTextoProprio(el) {
    for (const n of el.childNodes || []) {
        if (n.nodeType === 3 && n.textContent.trim()) return true;
    }
    return false;
}

function _fundoEscuroAtivo() {
    return document.body.dataset.tomFundo === "escuro"
        && !!document.getElementById("fundo-clinica")
        && !!document.querySelector("#app > .shell, #app > .shell-mobile");
}

function _varrer(el, marcados) {
    for (const filho of el.children) {
        const cs = getComputedStyle(filho);
        if (cs.display === "none") continue;
        if (superficieOpaca(cs.backgroundColor, cs.backgroundImage)) continue;
        if (temTextoProprio(filho)) marcados.add(filho);
        _varrer(filho, marcados);
    }
}

function aplicarContrasteFundo() {
    const app = document.getElementById("app");
    if (!app) return;
    const marcados = new Set();
    if (_fundoEscuroAtivo()) _varrer(app, marcados);
    for (const el of document.querySelectorAll("." + CLASSE_SOBRE_FUNDO)) {
        if (!marcados.has(el)) el.classList.remove(CLASSE_SOBRE_FUNDO);
    }
    for (const el of marcados) el.classList.add(CLASSE_SOBRE_FUNDO);
}

let _contrasteAgendado = false;
function _agendarContraste() {
    if (_contrasteAgendado) return;
    _contrasteAgendado = true;
    requestAnimationFrame(() => { _contrasteAgendado = false; aplicarContrasteFundo(); });
}

// Refaz a varredura quando a tela muda (só elementos e texto; a classe que
// colocamos é atributo e não dispara de novo) e quando o tom do fundo muda.
function iniciarContrasteFundo() {
    const app = document.getElementById("app");
    if (!app || typeof MutationObserver === "undefined") return;
    new MutationObserver(_agendarContraste).observe(app, { childList: true, subtree: true, characterData: true });
    new MutationObserver(_agendarContraste).observe(document.body, { attributes: true, attributeFilter: ["data-tom-fundo"], childList: true });
    window.addEventListener("resize", _agendarContraste);
    _agendarContraste();
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciarContrasteFundo);
    else iniciarContrasteFundo();
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { superficieOpaca, temTextoProprio, CLASSE_SOBRE_FUNDO };
}
