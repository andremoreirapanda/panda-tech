// ============================================================================
// router.js — Roteador SPA (hash-based) com guarda de papel
// ============================================================================

const Rotas = [];

function rota(padrao, papeisPermitidos, handler) {
    // padrao: "/gestor/paciente/:id" -> regex com grupos nomeados
    const nomesParams = [];
    const regexStr = padrao.replace(/:[a-zA-Z]+/g, (m) => {
        nomesParams.push(m.slice(1));
        return "([^/]+)";
    });
    const regex = new RegExp(`^${regexStr}$`);
    Rotas.push({ regex, nomesParams, papeisPermitidos, handler });
}

function paginaInicialPara(papel) {
    switch (papel) {
        case "gestor": return "#/gestor/dashboard";
        case "profissional": return "#/profissional/dashboard";
        case "secretaria": return "#/secretaria/pacientes";
        case "responsavel": return "#/responsavel/inicio";
        case "admin_master": return "#/admin/monitoramento";
        default: return "#/login";
    }
}

async function despachar() {
    const hash = location.hash || "#/login";
    const caminho = hash.slice(1).split("?")[0] || "/";

    if (caminho !== "/login" && caminho !== "/esqueci-senha" && caminho !== "/redefinir-senha" && !Sessao.logado()) {
        location.hash = "#/login";
        return;
    }
    if (caminho === "/login" && Sessao.logado()) {
        location.hash = paginaInicialPara(Sessao.usuario.papel);
        return;
    }

    for (const r of Rotas) {
        const m = caminho.match(r.regex);
        if (!m) continue;

        if (r.papeisPermitidos && Sessao.logado()) {
            const papelAtual = Sessao.modoCrianca ? "crianca" : Sessao.usuario.papel;
            if (!r.papeisPermitidos.includes(papelAtual)) {
                Toast.erro("Você não tem permissão para acessar esta área.");
                location.hash = paginaInicialPara(Sessao.usuario.papel);
                return;
            }
        }

        const params = {};
        r.nomesParams.forEach((nome, i) => { params[nome] = m[i + 1]; });

        const app = document.getElementById("app");
        app.innerHTML = `<div class="carregando"><div class="spinner"></div></div>`;
        try {
            await r.handler(app, params);
            inicializarNotificacoesGlobais();
        } catch (e) {
            console.error(e);
            // CORREÇÃO DE AUDITORIA (25/08/2026, achado do CodeQL): mesma
            // razão do toast.js — e.message pode conter texto vindo direto
            // da resposta da API (campo "erro"), então precisa de escape
            // antes de virar HTML.
            app.innerHTML = `<div class="estado-vazio"><div class="emoji">😕</div><h3>Algo deu errado</h3><p class="texto-suave">${escapeHtml(e.message || "Tente novamente.")}</p></div>`;
        }
        return;
    }

    document.getElementById("app").innerHTML = `<div class="estado-vazio"><div class="emoji">🔍</div><h3>Página não encontrada</h3></div>`;
}

window.addEventListener("hashchange", despachar);
