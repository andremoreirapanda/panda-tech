// ============================================================================
// cenarios_animados.js — Cenários animados (White Label completo, 25/09/2026)
//
// Fundo animado do Mundo da Criança — e, depois, dos jogos do Pandoo (PR B
// reusa este arquivo). Visual copiado da prévia aprovada do Pandoo. A imagem
// da clínica vem por URL pública (/api/publico/...), porque a CSP não deixa
// usar blob:. O HTML gerado aqui só tem números e emojis fixos — nada vindo
// do usuário além da URL, que é montada com um endereço já validado.
// ============================================================================

const TONS_CENARIO = { estrelas: "claro", bambu: "escuro", mar: "escuro", espaco: "escuro" };
const _ENDERECO_SEGURO = /^[a-z0-9-]{3,40}$/;

// Decide o cenário do Mundo a partir da identidade efetiva da clínica
// (/auth/me). Função pura — testada em frontend/tests/cenarios_animados.test.js.
function cenarioDoMundo(org) {
    org = org || {};
    let tipo = org.mundo_fundo || "estrelas";
    if (tipo === "pandoo") tipo = org.pandoo_cenario_padrao || "bambu";
    if (tipo === "clinica") {
        if (org.tem_cenario_imagem && _ENDERECO_SEGURO.test(org.endereco_login || "")) {
            return {
                tipo: "clinica",
                imagemUrl: `/api/publico/clinica/${org.endereco_login}/cenario?v=${encodeURIComponent(org.versao_imagens || "")}`,
                tom: org.pandoo_cenario_tom === "escuro" ? "escuro" : "claro",
            };
        }
        tipo = "estrelas";
    }
    if (!TONS_CENARIO[tipo]) tipo = "estrelas";
    return { tipo, imagemUrl: null, tom: TONS_CENARIO[tipo] };
}

function _aleatorio(a, b) { return (a + Math.random() * (b - a)).toFixed(2); }

// Preenche `elemento` com a camada animada do cenário e devolve o tom
// ("claro"/"escuro"), que decide a cor dos textos por cima.
function montarCenarioAnimado(elemento, cen) {
    if (!elemento) return "claro";
    cen = cen || { tipo: "estrelas", imagemUrl: null, tom: "claro" };
    const r = _aleatorio;
    let h = "";
    elemento.style.backgroundImage = "";
    if (cen.tipo === "bambu") {
        for (let i = 0; i < 8; i++) h += `<div class="el haste" style="left:${i < 4 ? r(0, 14) : r(84, 97)}%; height:${r(55, 95)}%; animation-delay:-${r(0, 5)}s"></div>`;
        for (let i = 0; i < 10; i++) h += `<div class="el folha" style="left:${r(0, 90)}%; animation-duration:${r(7, 13)}s; animation-delay:-${r(0, 12)}s"></div>`;
    } else if (cen.tipo === "mar") {
        for (let i = 0; i < 14; i++) {
            const t = Math.round(r(8, 22));
            h += `<div class="el bolha" style="left:${r(0, 100)}%; width:${t}px; height:${t}px; animation-duration:${r(6, 12)}s; animation-delay:-${r(0, 12)}s"></div>`;
        }
        ["🐟", "🐠", "🐡", "🐢"].forEach((f, i) => {
            h += `<div class="el peixe" style="top:${22 + i * 20}%; animation-duration:${r(12, 20)}s; animation-delay:-${r(0, 18)}s">${f}</div>`;
        });
    } else if (cen.tipo === "espaco") {
        for (let i = 0; i < 50; i++) h += `<div class="el estrela" style="left:${r(0, 100)}%; top:${r(0, 100)}%; animation-duration:${r(1.5, 4)}s; animation-delay:-${r(0, 4)}s"></div>`;
        h += `<div class="el planeta" style="left:4%; bottom:4%">🪐</div><div class="el planeta" style="right:5%; top:3%; font-size:40px; animation-delay:-3s">🚀</div>`;
    } else if (cen.tipo === "clinica" && cen.imagemUrl) {
        elemento.style.backgroundImage = `url("${cen.imagemUrl}")`;
        for (let i = 0; i < 10; i++) h += `<div class="el brilho" style="left:${r(0, 100)}%; top:${r(0, 100)}%; animation-duration:${r(2, 4)}s; animation-delay:-${r(0, 4)}s"></div>`;
    }
    elemento.className = "cenario-animado c-" + cen.tipo;
    elemento.setAttribute("aria-hidden", "true");
    elemento.innerHTML = h;
    return cen.tom;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { TONS_CENARIO, cenarioDoMundo, montarCenarioAnimado };
}
