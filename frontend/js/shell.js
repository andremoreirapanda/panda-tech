// ============================================================================
// shell.js — Shells de navegação por perfil
// ============================================================================

const MENUS = {
    gestor: [
        { rota: "#/gestor/dashboard", icone: "🏠", label: "Início" },
        { rota: "#/gestor/pacientes", icone: "🧒", label: "Pacientes" },
        { rota: "#/gestor/equipe", icone: "👥", label: "Equipe" },
        { rota: "#/gestor/agenda", icone: "📅", label: "Agenda" },
        { rota: "#/gestor/biblioteca", icone: "📚", label: "Biblioteca" },
        { rota: "#/gestor/mural", icone: "📣", label: "Mural" },
        { rota: "#/gestor/financeiro", icone: "💳", label: "Financeiro", modulo: "financeiro" },
        { rota: "#/gestor/indicadores", icone: "📊", label: "Indicadores", modulo: "analytics_avancado" },
        { rota: "#/gestor/integracoes", icone: "🔌", label: "Integrações", modulo: "integracoes" },
        { rota: "#/gestor/modulos", icone: "🧩", label: "Módulos" },
        { rota: "#/gestor/configuracoes", icone: "⚙️", label: "Configurações" },
    ],
    profissional: [
        { rota: "#/profissional/dashboard", icone: "🏠", label: "Início" },
        { rota: "#/profissional/pacientes", icone: "🧒", label: "Meus Pacientes" },
        { rota: "#/profissional/agenda", icone: "📅", label: "Agenda" },
        { rota: "#/profissional/biblioteca", icone: "📚", label: "Biblioteca" },
        { rota: "#/profissional/mural", icone: "📣", label: "Mural" },
        { rota: "#/profissional/perfil", icone: "👤", label: "Meu Perfil" },
    ],
    admin_master: [
        { rota: "#/admin/monitoramento", icone: "📈", label: "Painel Comercial" },
        { rota: "#/admin/clinicas", icone: "🏥", label: "Clínicas" },
        { rota: "#/admin/planos", icone: "💎", label: "Planos" },
        { rota: "#/admin/biblioteca", icone: "📚", label: "Biblioteca" },
        { rota: "#/admin/auditoria", icone: "🛡️", label: "Auditoria" },
    ],
};

// Feature Flags (Doc 22A) — some itens de menu só aparecem se o módulo
// opcional estiver liberado pelo plano E habilitado pela clínica.
function itensMenuVisiveis(papel) {
    const todos = MENUS[papel] || [];
    const modulosHabilitados = (Sessao.usuario.organizacao && Sessao.usuario.organizacao.modulos_habilitados) || [];
    return todos.filter(item => !item.modulo || modulosHabilitados.includes(item.modulo));
}

function renderShellSidebar(rotaAtiva, tituloPagina, conteudoHtml, acoesTopo = "") {
    const u = Sessao.usuario;
    const menu = itensMenuVisiveis(u.papel);
    const org = u.organizacao;
    const temLogoReal = org && org.logo_base64;
    // Com imagem real, o logo fica empilhado acima do nome (tamanho de verdade,
    // sem recorte). Sem imagem (só emoji), mantém o layout compacto lado a lado.
    const nomeMarca = temLogoReal
        ? `${renderLogoClinica(org, 40)}<strong style="font-size:15px;">${escapeHtml(org.nome)}</strong>`
        : `<span class="linha gap-2" style="align-items:center;">${renderLogoClinica(org, 22)} <strong style="font-size:15px;">${escapeHtml(org ? org.nome : "Encanto em Casa")}</strong></span>`;

    return `
    <div class="shell">
      <div class="shell-overlay" id="shell-overlay"></div>
      <aside class="shell-sidebar" id="shell-sidebar">
        <div class="shell-marca" style="display:flex; flex-direction:${temLogoReal ? "column" : "row"}; align-items:${temLogoReal ? "flex-start" : "center"}; gap:8px;">${nomeMarca}</div>
        <span class="badge badge-marca" style="align-self:flex-start; margin:2px 0 14px;">${rotuloPapel(u.papel)}</span>
        <nav class="shell-nav">
          ${menu.map(item => `
            <a href="${item.rota}" class="shell-nav-item ${rotaAtiva === item.rota ? "ativo" : ""}">
              <span class="icone">${item.icone}</span> ${item.label}
            </a>`).join("")}
        </nav>
        <div class="shell-rodape">
          <div class="avatar-usuario">${renderAvatarUsuario(u, 36)}</div>
          <div class="shell-rodape-info">
            <div class="shell-rodape-nome">${escapeHtml(u.nome)}</div>
            ${u.especialidade ? `<div class="shell-rodape-papel">${escapeHtml(u.especialidade)}</div>` : ""}
          </div>
          <button class="botao-icone" id="btn-sair" title="Sair">🚪</button>
        </div>
      </aside>
      <main class="shell-conteudo">
        <div class="shell-topo-mobile">
          <button class="btn-hamburguer" id="btn-abrir-menu">☰</button>
          <div class="shell-marca" style="font-size:14px;">${nomeMarca}</div>
          ${renderSinoNotificacoes()}
        </div>
        <div class="shell-topo">
          <h1>${tituloPagina}</h1>
          <div class="linha gap-3">${acoesTopo}${renderSinoNotificacoes("desktop")}</div>
        </div>
        <div class="surgir">${conteudoHtml}</div>
      </main>
    </div>`;
}

function renderSinoNotificacoes(variante) {
    const idExtra = variante ? `-${variante}` : "";
    return `
    <div class="wrap-notificacoes">
      <button class="botao-icone btn-sino" id="btn-sino${idExtra}" title="Notificações">
        🔔<span class="sino-contador oculto" id="sino-contador${idExtra}">0</span>
      </button>
    </div>`;
}

function rotuloPapel(papel) {
    return { gestor: "Gestor(a)", profissional: "Profissional", responsavel: "Responsável", admin_master: "Administrador da Plataforma" }[papel] || papel;
}

function anexarEventosShell() {
    const btn = document.getElementById("btn-sair");
    if (btn) btn.addEventListener("click", () => {
        Sessao.limpar();
        location.hash = "#/login";
    });

    const sidebar = document.getElementById("shell-sidebar");
    const overlay = document.getElementById("shell-overlay");
    const btnAbrir = document.getElementById("btn-abrir-menu");
    if (btnAbrir && sidebar && overlay) {
        btnAbrir.addEventListener("click", () => { sidebar.classList.add("aberto"); overlay.classList.add("aberto"); });
        overlay.addEventListener("click", () => { sidebar.classList.remove("aberto"); overlay.classList.remove("aberto"); });
        sidebar.querySelectorAll("a").forEach(a => a.addEventListener("click", () => {
            sidebar.classList.remove("aberto"); overlay.classList.remove("aberto");
        }));
    }
}

async function carregarContadorNotificacoes() {
    try {
        const notifs = await Api.get("/notificacoes");
        const naoLidas = notifs.filter(n => !n.lida).length;
        document.querySelectorAll(".sino-contador").forEach(el => {
            if (naoLidas > 0) { el.textContent = naoLidas > 9 ? "9+" : naoLidas; el.classList.remove("oculto"); }
            else el.classList.add("oculto");
        });
        return notifs;
    } catch (e) { return []; }
}

function anexarSino(sufixo) {
    const btnSino = document.getElementById(`btn-sino${sufixo}`);
    if (!btnSino) return;
    btnSino.addEventListener("click", async (e) => {
        e.stopPropagation();
        const existente = document.querySelector(".painel-notificacoes");
        if (existente) { existente.remove(); return; }
        const notifs = await carregarContadorNotificacoes();
        const painel = el(`
        <div class="painel-notificacoes">
          <div class="linha-entre" style="margin-bottom:10px; padding:0 4px;">
            <strong class="texto-sm">Notificações</strong>
            ${notifs.length ? `<button class="botao-texto botao-sm" id="btn-marcar-todas-lidas" style="padding:4px 8px;">Marcar todas como lidas</button>` : ""}
          </div>
          ${notifs.length ? notifs.map(n => `
            <div class="notificacao-item ${n.lida ? "" : "nao-lida"}">
              <div class="texto-sm" style="font-weight:700;">${escapeHtml(n.titulo)}</div>
              <div class="texto-xs texto-suave">${escapeHtml(n.mensagem)}</div>
              <div class="texto-xs texto-suave" style="margin-top:3px;">${tempoRelativo(n.criado_em)}</div>
            </div>`).join("") : `<p class="texto-sm texto-suave" style="padding:10px 4px;">Nenhuma notificação por aqui.</p>`}
        </div>`);
        if (!btnSino.isConnected || !btnSino.parentElement) return; // usuário já navegou para outra tela
        btnSino.parentElement.appendChild(painel);
        const fechar = (ev) => { if (!painel.contains(ev.target) && ev.target !== btnSino) { painel.remove(); document.removeEventListener("click", fechar); } };
        setTimeout(() => document.addEventListener("click", fechar), 10);
        const btnMarcar = document.getElementById("btn-marcar-todas-lidas");
        if (btnMarcar) btnMarcar.addEventListener("click", async () => {
            await Api.post("/notificacoes/marcar-todas-lidas");
            painel.remove();
            carregarContadorNotificacoes();
        });
    });
}

// ---------------------------------------------------------------- Shell mobile (Responsável)
const MENU_RESPONSAVEL = [
    { rota: "#/responsavel/inicio", icone: "🏠", label: "Início" },
    { rota: "#/responsavel/mensagens", icone: "💬", label: "Chat" },
    { rota: "#/responsavel/agenda", icone: "📅", label: "Agenda" },
    { rota: "#/responsavel/mural", icone: "📣", label: "Mural" },
    { rota: "#/responsavel/financeiro", icone: "💳", label: "Financeiro", modulo: "financeiro" },
    { rota: "#/responsavel/perfil", icone: "👤", label: "Perfil" },
];

function menuResponsavelVisivel() {
    return MENU_RESPONSAVEL.filter(item => !item.modulo || Sessao.usuario.financeiro_visivel);
}

function renderShellMobile(rotaAtiva, tituloTopo, conteudoHtml, mostrarNav = true) {
    const acoesExtra = (typeof tituloTopo === "object" && tituloTopo.acoes) ? tituloTopo.acoes : "";
    return `
    <div class="shell-mobile">
      <div class="shell-mobile-topo">
        <div class="linha gap-2">
          <span style="font-size:20px">${tituloTopo.icone || "💛"}</span>
          <h1 style="font-size:19px">${tituloTopo.texto || tituloTopo}</h1>
        </div>
        <div class="linha gap-2">${acoesExtra}${renderSinoNotificacoes("mobile")}</div>
      </div>
      <div class="shell-mobile-conteudo surgir">${conteudoHtml}</div>
      ${mostrarNav ? `
      <nav class="shell-mobile-nav">
        ${menuResponsavelVisivel().map(item => `
          <a href="${item.rota}" class="shell-mobile-nav-item ${rotaAtiva === item.rota ? "ativo" : ""}">
            <span class="icone">${item.icone}</span>${item.label}
          </a>`).join("")}
      </nav>` : ""}
    </div>`;
}

// Chamado pelo router após CADA renderização de tela (sidebar, mobile ou criança).
// Garante que o sino de notificações funcione em qualquer shell, sem cada view
// precisar se preocupar com isso.
function inicializarNotificacoesGlobais() {
    if (!Sessao.logado() || Sessao.modoCrianca) return;
    ["", "-desktop", "-mobile"].forEach(s => anexarSino(s));
    carregarContadorNotificacoes();
}
