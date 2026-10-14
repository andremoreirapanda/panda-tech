// ============================================================================
// marca_plataforma.js — Logo da plataforma (14/10/2026)
//
// O Admin envia o logo em Perfil da Plataforma. O servidor põe a versão dele
// numa meta do index.html (<meta name="logo-plataforma">), então o menu do
// Admin, o login e as telas de recuperar acesso sabem na hora se há logo —
// sem pedido extra. Sem logo, cada tela mantém o visual de antes.
//
// 15/10/2026: segundo logo, só para o fundo roxo do login (letras claras) —
// meta "logo-plataforma-login". Sem ele, o login usa o principal.
// ============================================================================

const _METAS_LOGO = { principal: "logo-plataforma", login: "logo-plataforma-login" };
const _CAMINHOS_LOGO = { principal: "logo", login: "logo-login" };

function versaoLogoPlataforma(tipo = "principal") {
    if (typeof document === "undefined") return "";
    const meta = document.querySelector(`meta[name="${_METAS_LOGO[tipo]}"]`);
    return meta ? meta.content : "";
}

// Depois de enviar/remover o logo em Perfil da Plataforma, sem recarregar.
function atualizarVersaoLogoPlataforma(versao, tipo = "principal") {
    const nome = _METAS_LOGO[tipo];
    let meta = document.querySelector(`meta[name="${nome}"]`);
    if (!versao) { if (meta) meta.remove(); return; }
    if (!meta) {
        meta = document.createElement("meta");
        meta.name = nome;
        document.head.appendChild(meta);
    }
    meta.content = versao;
}

// Função pura (testada): qual logo vai no login.
function logoParaLogin(versaoLogin, versaoPrincipal) {
    return versaoLogin ? { versao: versaoLogin, tipo: "login" } : { versao: versaoPrincipal || "", tipo: "principal" };
}

// Função pura (testada): <img> do logo, ou "" sem logo.
function htmlLogoPlataforma(versao, alturaPx = 40, estiloExtra = "", tipo = "principal") {
    const v = String(versao || "").replace(/[^a-zA-Z0-9]/g, "");
    if (!v) return "";
    return `<img src="/api/publico/plataforma/${_CAMINHOS_LOGO[tipo] || "logo"}?v=${v}" alt="PandaUp" `
        + `style="max-height:${alturaPx}px; max-width:${alturaPx * 6}px; width:auto; height:auto; object-fit:contain; display:block;${estiloExtra}" />`;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { htmlLogoPlataforma, logoParaLogin };
}
