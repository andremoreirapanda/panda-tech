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
        // "Indicadores" saiu do menu — o conteúdo dessa tela (gráfico semanal +
        // KPIs) já foi incorporado ao "Início" (ver dashboard_gestor.js), então
        // manter os dois deixaria a informação duplicada. A rota "#/gestor/indicadores"
        // continua registrada em app.js (não foi removida), só não aparece mais no menu.
        { rota: "#/gestor/integracoes", icone: "🔌", label: "Integrações", modulo: "integracoes" },
        { rota: "#/gestor/importar-pacientes", icone: "📥", label: "Importar Pacientes", modulo: "importacao_pacientes" },
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
    secretaria: [
        { rota: "#/secretaria/pacientes", icone: "🧒", label: "Pacientes" },
        { rota: "#/secretaria/agenda", icone: "📅", label: "Agenda" },
        { rota: "#/secretaria/equipe", icone: "👥", label: "Equipe" },
        { rota: "#/secretaria/mural", icone: "📣", label: "Mural" },
        { rota: "#/secretaria/perfil", icone: "👤", label: "Meu Perfil" },
    ],
    admin_master: [
        { rota: "#/admin/monitoramento", icone: "📈", label: "Painel Comercial" },
        { rota: "#/admin/clinicas", icone: "🏥", label: "Clínicas" },
        { rota: "#/admin/planos", icone: "💎", label: "Planos" },
        { rota: "#/admin/cobrancas-planos", icone: "🧾", label: "Cobranças" },
        { rota: "#/admin/biblioteca", icone: "📚", label: "Biblioteca" },
        { rota: "#/admin/integracoes", icone: "🔌", label: "Integrações" },
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
        : `<span class="linha gap-2" style="align-items:center;">${renderLogoClinica(org, 22)} <strong style="font-size:15px;">${escapeHtml(org ? org.nome : "Panda Tech")}</strong></span>`;

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
          <h1>${escapeHtml(tituloPagina)}</h1>
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
    return { gestor: "Gestor(a)", profissional: "Profissional", secretaria: "Secretária", responsavel: "Responsável", admin_master: "Administrador da Plataforma" }[papel] || papel;
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

// Pra onde o clique numa notificação deve levar — depende do tipo dela e do
// papel de quem está logado (a mesma notificação pode não fazer sentido pra
// todo mundo, mas cada tipo hoje só é criado pra um papel específico mesmo).
// Quando `entidade === "paciente"`, também troca o filho ativo do Responsável
// antes de navegar, senão a tela abriria mostrando o filho errado.
function rotaParaNotificacao(n) {
    const papel = Sessao.usuario?.papel;
    const base = papel === "gestor" ? "gestor" : papel === "profissional" ? "profissional" : papel === "responsavel" ? "responsavel" : null;
    if (!base) return null;

    switch (n.tipo) {
        case "financeiro":
            // Só Gestor recebe esse tipo hoje — é onde fica "Sua Assinatura".
            if (base !== "gestor") return null;
            sessionStorage.setItem("destacar_assinatura", "1");
            return "#/gestor/configuracoes";

        case "mensagem":
            return n.entidade_id ? `#/${base}/mensagens?paciente=${n.entidade_id}` : `#/${base}/mensagens`;

        case "missao":
        case "conquista":
        case "diario":
            // Só Responsável recebe esses tipos hoje — tudo (missões, diário)
            // fica na própria tela de Início, sem sub-rota por criança.
            if (base !== "responsavel") return null;
            if (n.entidade === "paciente" && n.entidade_id) Sessao.pacienteAtivoId = n.entidade_id;
            return "#/responsavel/inicio";

        default:
            return null;
    }
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
            <div class="notificacao-item ${n.lida ? "" : "nao-lida"}" data-id="${n.id}" ${rotaParaNotificacao(n) ? 'style="cursor:pointer;"' : ""}>
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
        painel.querySelectorAll(".notificacao-item").forEach(itemEl => {
            const n = notifs.find(x => String(x.id) === itemEl.dataset.id);
            if (!n) return;
            itemEl.addEventListener("click", () => {
                // CORREÇÃO (27/08/2026): antes, este handler era `async` e
                // dava `await` na chamada de marcar-como-lida ANTES de
                // fechar o painel/navegar — ou seja, o painel só fechava (e
                // só navegava) depois da resposta da API chegar. Em conexão
                // mobile mais lenta, essa janela de espera dava tempo pro
                // listener "fechar" (fechar o painel ao clicar fora, ainda
                // registrado no `document` durante toda a espera) reagir a
                // qualquer toque intermediário, e o toque na notificação
                // simplesmente parecia não fazer nada. Agora o painel fecha
                // e a navegação acontece IMEDIATAMENTE, de forma síncrona,
                // no mesmo clique; marcar como lida roda em segundo plano,
                // sem bloquear nada visualmente.
                const destino = rotaParaNotificacao(n);
                painel.remove();
                document.removeEventListener("click", fechar);
                if (!n.lida) {
                    Api.post(`/notificacoes/${n.id}/marcar-lida`).catch(() => { /* não bloqueia a navegação por causa disso */ });
                }
                carregarContadorNotificacoes();
                if (destino) {
                    // Se já está na tela de destino, mudar o hash pro mesmo
                    // valor não dispara "hashchange" — despacha na mão pra
                    // não deixar o clique parecendo que não fez nada.
                    if (location.hash === destino) despachar();
                    else location.hash = destino;
                }
            });
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
    // CORREÇÃO DE AUDITORIA (25/08/2026, sweep manual após o achado do
    // CodeQL): "tituloTopo.texto" às vezes é o nome de um paciente
    // (comunicacao.js, tela de chat do responsável) ou do próprio usuário
    // logado (responsavel.js) — ambos texto salvo por outra pessoa (quem
    // cadastrou o paciente), então precisam de escapeHtml aqui, no ponto
    // único usado por todo mundo que chama renderShellMobile.
    return `
    <div class="shell-mobile">
      <div class="shell-mobile-topo">
        <div class="linha gap-2">
          <span style="font-size:20px">${tituloTopo.icone || "💛"}</span>
          <h1 style="font-size:19px">${escapeHtml(tituloTopo.texto || tituloTopo)}</h1>
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
