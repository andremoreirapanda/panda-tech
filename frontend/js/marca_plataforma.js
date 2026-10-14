// ============================================================================
// marca_plataforma.js — Logo da plataforma (14/10/2026)
//
// O Admin envia o logo em Perfil da Plataforma. O servidor põe a versão dele
// numa meta do index.html (<meta name="logo-plataforma">), então o menu do
// Admin, o login e as telas de recuperar acesso sabem na hora se há logo —
// sem pedido extra. Sem logo, cada tela mantém o visual de antes.
// ============================================================================

function versaoLogoPlataforma() {
    if (typeof document === "undefined") return "";
    const meta = document.querySelector('meta[name="logo-plataforma"]');
    return meta ? meta.content : "";
}

// Depois de enviar/remover o logo em Perfil da Plataforma, sem recarregar.
function atualizarVersaoLogoPlataforma(versao) {
    let meta = document.querySelector('meta[name="logo-plataforma"]');
    if (!versao) { if (meta) meta.remove(); return; }
    if (!meta) {
        meta = document.createElement("meta");
        meta.name = "logo-plataforma";
        document.head.appendChild(meta);
    }
    meta.content = versao;
}

// Função pura (testada): <img> do logo, ou "" sem logo.
function htmlLogoPlataforma(versao, alturaPx = 40, estiloExtra = "") {
    const v = String(versao || "").replace(/[^a-zA-Z0-9]/g, "");
    if (!v) return "";
    return `<img src="/api/publico/plataforma/logo?v=${v}" alt="PandaUp" `
        + `style="max-height:${alturaPx}px; max-width:${alturaPx * 6}px; width:auto; height:auto; object-fit:contain; display:block;${estiloExtra}" />`;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { htmlLogoPlataforma };
}
