// App instalável (29/10/2026): orienta a família a pôr o PandaUp na tela
// inicial do celular. No Android (Chrome) o navegador oferece a instalação
// (evento beforeinstallprompt); no iPhone não há botão — só o passo a passo
// pelo Compartilhar do Safari.

const CHAVE_DISPENSADO = "pandaup_instalar_dispensado";
let _promptInstalacao = null;

// Funções puras --------------------------------------------------------------

// "instalado" | "android" | "android-menu" | "iphone" | "iphone-outro-app" | "computador"
function comoInstalar({ userAgent = "", standalone = false, temPrompt = false, toque = false } = {}) {
    if (standalone) return "instalado";
    const ua = String(userAgent);
    const ios = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && toque);
    if (ios) {
        // Navegador dentro de outro app (Instagram, Facebook, WhatsApp...) não tem "Adicionar à Tela de Início".
        const emOutroApp = /FBAN|FBAV|Instagram|Line\/|WhatsApp/.test(ua)
            || !/Safari\//.test(ua);
        return emOutroApp ? "iphone-outro-app" : "iphone";
    }
    if (/Android/.test(ua)) return temPrompt ? "android" : "android-menu";
    return "computador";
}

function mostrarConvite(modo, dispensado) {
    return !dispensado && modo !== "instalado" && modo !== "computador";
}

function passosInstalar(modo) {
    if (modo === "iphone") {
        return [
            "Toque no botão Compartilhar (o quadrado com a seta para cima ⬆️), na barra do navegador.",
            "Role a lista e toque em \"Adicionar à Tela de Início\".",
            "Toque em \"Adicionar\". O ícone do app aparece junto dos seus outros apps.",
            "Abra pelo ícone e entre com seu e-mail e senha (só na primeira vez).",
        ];
    }
    if (modo === "iphone-outro-app") {
        return [
            "Este link abriu dentro de outro app. Toque em \"…\" e escolha \"Abrir no Safari\" (ou copie o endereço e cole no Safari).",
            "No Safari, toque em Compartilhar (o quadrado com a seta para cima ⬆️).",
            "Toque em \"Adicionar à Tela de Início\" e depois em \"Adicionar\".",
        ];
    }
    if (modo === "android-menu" || modo === "android") {
        return [
            "Abra o PandaUp no Chrome e toque no menu ⋮ (canto de cima).",
            "Toque em \"Instalar app\" ou \"Adicionar à tela inicial\".",
            "Confirme. O ícone do app aparece junto dos seus outros apps.",
        ];
    }
    return [];
}

// Tela -----------------------------------------------------------------------

if (typeof window !== "undefined") {
    window.addEventListener("beforeinstallprompt", (e) => {
        e.preventDefault(); // guarda para o botão "Instalar o app"
        _promptInstalacao = e;
    });
    window.addEventListener("appinstalled", () => { _promptInstalacao = null; });
}

function modoInstalacaoAtual() {
    const standalone = (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches)
        || window.navigator.standalone === true;
    return comoInstalar({
        userAgent: navigator.userAgent, standalone, temPrompt: !!_promptInstalacao,
        toque: (navigator.maxTouchPoints || 0) > 1,
    });
}

// Nome e ícone que vão para a tela inicial: os da clínica (White Label) ou os do PandaUp.
function _linksDoApp() {
    const org = typeof Sessao !== "undefined" && Sessao.usuario ? Sessao.usuario.organizacao : null;
    return linksIdentidade(org);
}

function _iconeDoApp() {
    return _linksDoApp().iconeApple;
}

function _dispensado() {
    try { return localStorage.getItem(CHAVE_DISPENSADO) === "1"; } catch (e) { return false; }
}

// Cartão para o início da família; "" quando não faz sentido mostrar.
function htmlConviteInstalar() {
    if (!mostrarConvite(modoInstalacaoAtual(), _dispensado())) return "";
    return `
      <div class="cartao" id="cartao-instalar-app" style="margin-bottom:16px; display:flex; gap:12px; align-items:center;">
        <img src="${escapeHtml(_iconeDoApp())}" alt="" width="48" height="48" style="border-radius:12px; flex-shrink:0;">
        <div style="flex:1; min-width:0;">
          <p style="font-weight:700;">Tenha o ${escapeHtml(_linksDoApp().nomeApp)} na tela do celular</p>
          <p class="texto-xs texto-suave">Abre direto, em tela cheia, como um aplicativo.</p>
          <div class="linha gap-2" style="margin-top:8px; flex-wrap:wrap;">
            <button type="button" class="botao botao-primario botao-sm" data-instalar-app>📲 Instalar o app</button>
            <button type="button" class="botao botao-texto botao-sm" id="btn-instalar-depois">Agora não</button>
          </div>
        </div>
      </div>`;
}

// Liga todos os botões [data-instalar-app] da tela e o "Agora não" do cartão.
function ligarInstalarApp(raiz) {
    raiz = raiz || document;
    raiz.querySelectorAll("[data-instalar-app]").forEach((btn) => btn.addEventListener("click", instalarApp));
    const depois = raiz.querySelector("#btn-instalar-depois");
    if (depois) depois.addEventListener("click", () => {
        try { localStorage.setItem(CHAVE_DISPENSADO, "1"); } catch (e) { /* sem armazenamento: só some agora */ }
        const cartao = document.getElementById("cartao-instalar-app");
        if (cartao) cartao.remove();
    });
}

async function instalarApp() {
    const modo = modoInstalacaoAtual();
    if (modo === "android" && _promptInstalacao) {
        const prompt = _promptInstalacao;
        _promptInstalacao = null; // o navegador só deixa usar uma vez
        try {
            await prompt.prompt();
        } catch (e) {
            abrirPassosInstalar("android-menu"); // o Chrome recusou a janela: ensina pelo menu
            return;
        }
        const escolha = await prompt.userChoice.catch(() => null);
        if (escolha && escolha.outcome === "accepted") {
            const cartao = document.getElementById("cartao-instalar-app");
            if (cartao) cartao.remove();
        }
        return;
    }
    abrirPassosInstalar(modo);
}

function abrirPassosInstalar(modo) {
    if (modo === "instalado") {
        Toast.sucesso("Você já está usando o app instalado. 🎉");
        return;
    }
    const passos = passosInstalar(modo);
    const titulo = modo.startsWith("iphone") ? "Instalar no iPhone" : modo === "computador" ? "Instalar no celular" : "Instalar no Android";
    const corpo = passos.length
        ? `<ol class="coluna gap-2" style="padding-left:20px; margin:0;">${passos.map((p) => `<li class="texto-sm">${escapeHtml(p)}</li>`).join("")}</ol>`
        : `<p class="texto-sm">Abra o PandaUp no navegador do celular (Safari no iPhone, Chrome no Android) e toque em "📲 Instalar o app" na tela inicial.</p>`;
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <div class="linha gap-3" style="align-items:center; margin-bottom:14px;">
          <img src="${escapeHtml(_iconeDoApp())}" alt="" width="44" height="44" style="border-radius:10px;">
          <h3 style="margin:0;">${titulo}</h3>
        </div>
        ${corpo}
        <button type="button" class="botao botao-secundario" id="btn-fechar-instalar" style="width:100%; margin-top:18px;">Entendi</button>
      </div>
    </div>`);
    document.body.appendChild(modal);
    document.getElementById("btn-fechar-instalar").addEventListener("click", () => modal.remove());
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { comoInstalar, mostrarConvite, passosInstalar };
}
