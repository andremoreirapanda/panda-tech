// ============================================================================
// views/agenda.js — Agenda de consultas (Lista + Calendário em grade + Por Profissional)
// ============================================================================

const DIAS_SEMANA_ABREV = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const MESES_NOME = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];

// Status de consulta (insight do usuário, 02/09/2026, inspirado num sistema
// concorrente): usado só na visão "Por Profissional" da agenda, onde cada
// bloco passa a ser colorido pelo STATUS do agendamento em vez da cor do
// profissional (essa continua valendo só na visão "Geral da Clínica" — ver
// renderConsultaChip/renderConsultaLinha/renderLegendaProfissionais, que não
// mudam). Os 5 valores já existiam no banco (consultas.status) — isto é só
// a camada visual (cor + rótulo) por cima de um mecanismo que já funcionava.
const STATUS_CONSULTA_INFO = {
    agendada: { label: "Agendamento está marcado", cor: "var(--cor-status-marcado)", icone: "" },
    confirmada: { label: "Agendamento Confirmado", cor: "var(--cor-status-confirmado)", icone: "✔️ " },
    realizada: { label: "Finalizado", cor: "var(--cor-status-atendido)", icone: "" },
    faltou: { label: "Não compareceu", cor: "var(--cor-status-faltou)", icone: "" },
    // Status novos (Atender, 08/10/2026): liberam o horário na agenda.
    falta_justificada: { label: "Falta justificada", cor: "var(--cor-status-justificada)", icone: "" },
    desmarcada_profissional: { label: "Desmarcado pelo profissional", cor: "var(--cor-status-desm-prof)", icone: "" },
    cancelada: { label: "Sessão desmarcada", cor: "var(--cor-status-desmarcado)", icone: "" },
};

// Duração padrão da clínica (Configurações, spec 07/10/2026); 50 se não houver.
function duracaoPadraoClinica() {
    const d = parseInt((Sessao.usuario && Sessao.usuario.organizacao && Sessao.usuario.organizacao.agenda_duracao_padrao) || 0, 10);
    return d >= 5 && d <= 240 ? d : AGENDA_DURACAO_PADRAO;
}

// Liga Início → Fim: mudar o início desloca o fim mantendo a duração; mudar o
// fim recalcula a duração. Devolve () => duracao (null se fim <= início).
function ligarInicioFim(idInicio, idFim, duracaoInicial) {
    const elIni = document.getElementById(idInicio), elFim = document.getElementById(idFim);
    let duracao = duracaoInicial;
    if (!elFim.value) elFim.value = calcularFim(elIni.value, duracao);
    elIni.addEventListener("change", () => { elFim.value = calcularFim(elIni.value, duracao); elFim.setCustomValidity(""); });
    elFim.addEventListener("change", () => {
        const d = duracaoEntre(elIni.value, elFim.value);
        elFim.setCustomValidity(d ? "" : "O fim precisa ser depois do início.");
        if (d) duracao = d;
        elFim.reportValidity();
    });
    return () => duracaoEntre(elIni.value, elFim.value);
}

// Encaixe (rodada rápida 08/10/2026): se o horário já tem consulta do mesmo
// profissional, o servidor responde 409 com pode_encaixar; pergunta e, se a
// pessoa confirmar, refaz a chamada com encaixe=true. `enviar(encaixe)` faz a chamada.
async function comEncaixe(enviar) {
    try {
        return await enviar(false);
    } catch (err) {
        if (err.dados && err.dados.pode_encaixar) {
            if (confirm(`${err.message}\n\nMarcar como encaixe?`)) return await enviar(true);
            throw new Error("Horário ocupado — nada foi alterado.");
        }
        throw err;
    }
}

async function mudarStatusConsulta(consultaId, status) {
    return comEncaixe(encaixe => Api.put(`/agenda/${consultaId}/status`, { status, ...(encaixe ? { encaixe: true } : {}) }));
}

function inicioDaSemana(data) {
    const d = new Date(data);
    d.setDate(d.getDate() - d.getDay());
    d.setHours(0, 0, 0, 0);
    return d;
}

// Dias mostrados na grade "Por Profissional": segunda a sábado; domingo só
// se o profissional tiver consulta nele (spec 24/09/2026).
function diasDaGradeSemana(inicioDomingo, consultasDoProf) {
    const dias = Array.from({ length: 7 }, (_, i) => { const d = new Date(inicioDomingo); d.setDate(d.getDate() + i); return d; });
    return precisaDomingo(paraChaveDia(dias[0]), consultasDoProf) ? dias : dias.slice(1);
}

async function viewAgenda(app) {
    // Garante que a sessão local nunca fique com um agenda_permissao_total
    // desatualizado — mesmo que a lista de consultas em si sempre venha
    // correta do backend, isso evita qualquer decisão de UI baseada em
    // dado velho do usuário (defesa extra, não custa a mais que 1 chamada).
    try {
        const meAtualizado = await Api.get("/auth/me");
        Sessao.usuario = { ...Sessao.usuario, ...meAtualizado };
    } catch (e) { /* se falhar, segue com o que já tinha na sessão */ }

    // Sessão expirada: a API já limpou a sessão e manda para o login.
    if (!Sessao.usuario) return;
    const u = Sessao.usuario;
    const base = u.papel === "gestor" ? "gestor" : (u.papel === "profissional" ? "profissional" : (u.papel === "secretaria" ? "secretaria" : "responsavel"));
    // Secretária (insight do usuário, 31/08/2026): função administrativa,
    // sempre com acesso total de agendamento — igual ao gestor.
    const podeGerenciar = u.papel === "gestor" || u.papel === "profissional" || u.papel === "secretaria";
    let [consultas, profissionaisTodos] = await Promise.all([
        Api.get("/agenda"),
        base !== "responsavel" ? Api.get("/pessoas/profissionais?incluir_gestor=1") : Promise.resolve([]),
    ]);

    // Estado — vive só nesta função (recriada a cada render/navegação de rota).
    // Gestor/Profissional/Secretária abrem direto na visão "Por Profissional"
    // (a mais usada no dia a dia); Responsável continua na lista simples, que
    // é a única visão que ele usa.
    let modoVisao = (base === "gestor" || base === "profissional" || base === "secretaria") ? "porProfissional" : "geral"; // "geral" | "porProfissional"
    let visaoAtual = base === "responsavel" ? "lista" : "semana";
    let dataReferencia = new Date();
    let profissionalSelecionadoId = (u.papel === "profissional" ? u.id : (profissionaisTodos[0] && profissionaisTodos[0].id)) || null;
    let idArrastando = null;
    let filtroProfissional = "";
    let faixaAtual = null; // faixa da grade renderizada — usada no clique/arraste
    let escalaProf = "semana";          // "semana" | "dia" (modo Por Profissional)
    let ausencias = [];                  // ocorrências da semana exibida (GET /agenda/ausencias)
    let ausenciasChave = null;           // "inicio|fim" carregado — evita refazer o GET
    const profsOcultosDia = new Set();   // colunas escondidas na visão Dia do modo Geral

    // Ausências da semana de dataReferencia (domingo a sábado). Responsável não vê.
    async function carregarAusencias(forcar = false) {
        // Só gestor, profissional e secretária veem ausências (a API recusa os demais).
        if (!["gestor", "profissional", "secretaria"].includes(u.papel)) return;
        const ini = inicioDaSemana(dataReferencia);
        const fim = new Date(ini); fim.setDate(fim.getDate() + 6);
        const chave = `${paraChaveDia(ini)}|${paraChaveDia(fim)}`;
        if (!forcar && chave === ausenciasChave) return;
        try {
            ausencias = await Api.get(`/agenda/ausencias?inicio=${paraChaveDia(ini)}&fim=${paraChaveDia(fim)}`);
            ausenciasChave = chave;
        } catch (e) { ausencias = []; ausenciasChave = null; }
    }

    async function renderizarComAusencias() {
        await carregarAusencias();
        renderizarTudo();
    }

    function montarShell(conteudo, acoesTopo) {
        if (base === "responsavel") {
            return renderShellMobile("#/responsavel/agenda", { icone: "📅", texto: "Agenda" }, conteudo);
        }
        return renderShellSidebar(`#/${base}/agenda`, "Agenda", conteudo, acoesTopo);
    }

    function renderToggleModo() {
        return `
        <div class="linha gap-2">
          <button type="button" class="botao botao-sm ${modoVisao === "geral" ? "botao-primario" : "botao-secundario"} btn-modo-agenda" data-modo="geral">🏥 Geral da Clínica</button>
          <button type="button" class="botao botao-sm ${modoVisao === "porProfissional" ? "botao-primario" : "botao-secundario"} btn-modo-agenda" data-modo="porProfissional">👤 Por Profissional</button>
        </div>`;
    }

    function renderBotoesVisao() {
        const opcoes = [["dia", "🕘 Dia"], ["lista", "📋 Lista"], ["semana", "🗓️ Semana"], ["mes", "📆 Mês"]];
        return `
        <div class="linha gap-2">
          ${opcoes.map(([v, label]) => `<button type="button" class="botao botao-sm ${visaoAtual === v ? "botao-primario" : "botao-secundario"} btn-visao-agenda" data-visao="${v}">${label}</button>`).join("")}
        </div>`;
    }

    // Navegação da grade (Por Profissional, e Geral na visão Dia): passo de 1
    // dia na visão Dia, de 7 na Semana (spec 07/10/2026).
    function renderNavPeriodo(ehDia, comBotoesEscala) {
        let rotulo;
        if (ehDia) {
            rotulo = `${DIAS_SEMANA_ABREV[dataReferencia.getDay()]}, ${formatarData(paraChaveDia(dataReferencia))}`;
        } else {
            const inicio = inicioDaSemana(dataReferencia);
            const fim = new Date(inicio); fim.setDate(fim.getDate() + 6);
            rotulo = `${formatarData(paraChaveDia(inicio))} – ${formatarData(paraChaveDia(fim))}`;
        }
        const escala = comBotoesEscala ? `
          <button type="button" class="botao botao-sm ${ehDia ? "botao-primario" : "botao-secundario"} btn-escala-prof" data-escala="dia">Dia</button>
          <button type="button" class="botao botao-sm ${ehDia ? "botao-secundario" : "botao-primario"} btn-escala-prof" data-escala="semana">Semana</button>` : "";
        return `
        <div class="linha gap-1" style="align-items:center;">
          ${escala}
          <button type="button" class="botao-icone" id="btn-periodo-anterior" data-passo="${ehDia ? -1 : -7}" title="${ehDia ? "Dia anterior" : "Semana anterior"}">←</button>
          <button type="button" class="botao botao-sm botao-secundario" id="btn-hoje">Hoje</button>
          <button type="button" class="botao-icone" id="btn-periodo-proximo" data-passo="${ehDia ? 1 : 7}" title="${ehDia ? "Próximo dia" : "Próxima semana"}">→</button>
          <strong class="texto-sm" style="margin-left:6px; white-space:nowrap;">${rotulo}</strong>
        </div>`;
    }

    // Lista lateral de profissionais (spec 24/09/2026) — substitui as pílulas
    // do topo. No modo Geral ganha o item "Todos"; clicar num profissional
    // abre a agenda dele — menos na visão Dia do modo Geral, onde a lista é
    // filtro: clicar mostra/esconde a coluna (spec 07/10/2026).
    function renderListaProfissionais() {
        const termo = filtroProfissional.trim().toLowerCase();
        const ehDiaGeral = modoVisao === "geral" && visaoAtual === "dia";
        const itemTodos = modoVisao === "geral" ? `
          <li><button type="button" class="agenda-item-prof ${!ehDiaGeral || !profsOcultosDia.size ? "ativo" : ""}" data-todos="1">
            <span class="agenda-item-avatar">🏥</span>
            <span><span class="agenda-item-nome">Todos</span><br><span class="agenda-item-esp">Agenda geral da clínica</span></span>
          </button></li>` : "";
        return `
        <aside class="agenda-lista-profs">
          <input type="search" id="agenda-filtro-prof" placeholder="🔍 Filtrar profissional" value="${escapeHtml(filtroProfissional)}" />
          <ul>
            ${itemTodos}
            ${profissionaisTodos.map(p => {
                const nomeBusca = (p.nome || "").toLowerCase();
                const ativo = ehDiaGeral ? !profsOcultosDia.has(p.id) : (modoVisao === "porProfissional" && p.id === profissionalSelecionadoId);
                return `
                <li data-nome="${escapeHtml(nomeBusca)}" style="${termo && !nomeBusca.includes(termo) ? "display:none;" : ""}">
                  <button type="button" class="agenda-item-prof btn-selecionar-profissional ${ativo ? "ativo" : ""}" data-id="${p.id}" ${ehDiaGeral ? 'title="Mostrar/esconder a coluna"' : ""}>
                    <span class="agenda-item-avatar" style="border-color:${corSegura(p.cor_agenda, "var(--cor-marca)")};">${renderAvatarUsuario(p, 30)}</span>
                    <span><span class="agenda-item-nome">${escapeHtml(p.nome)}</span><br><span class="agenda-item-esp">${escapeHtml(p.especialidade || "")}</span></span>
                  </button>
                </li>`;
            }).join("")}
          </ul>
        </aside>`;
    }

    function renderLegendaStatus() {
        return `
        <div class="linha gap-3" style="flex-wrap:wrap; margin-bottom:0;">
          ${Object.values(STATUS_CONSULTA_INFO).map(info => `
            <span class="linha gap-1" style="align-items:center; font-size:11.5px; color:var(--cor-tinta-suave);">
              <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:${info.cor}; border:1.5px solid var(--cor-borda);"></span>${info.label}
            </span>`).join("")}
        </div>`;
    }

    function renderLegendaProfissionais() {
        const vistos = new Map();
        consultas.forEach(c => { if (c.profissional_nome && !vistos.has(c.profissional_nome)) vistos.set(c.profissional_nome, corSegura(c.profissional_cor, "var(--cor-marca)")); });
        if (!vistos.size) return "";
        return `
        <div class="linha gap-3" style="flex-wrap:wrap;">
          ${Array.from(vistos.entries()).map(([nome, cor]) => `
            <span class="linha gap-1" style="align-items:center; font-size:12px; color:var(--cor-tinta-suave);">
              <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:${cor};"></span>${escapeHtml(nome.split(" ")[0])}
            </span>`).join("")}
        </div>`;
    }

    function renderListaView() {
        const hoje = new Date().toISOString().slice(0, 10);
        const futuras = consultas.filter(c => c.data_hora >= hoje && c.status !== "cancelada");
        const passadas = consultas.filter(c => c.data_hora < hoje || c.status === "cancelada").reverse();
        return `
        <div class="coluna gap-5">
          <div class="cartao">
            <h3 style="margin-bottom:14px;">Próximas consultas</h3>
            ${futuras.length ? `<div class="lista-pessoas">${futuras.map(c => renderConsultaLinha(c, podeGerenciar)).join("")}</div>`
                : `<p class="texto-sm texto-suave">Nenhuma consulta futura agendada.</p>`}
          </div>
          <div class="cartao">
            <h3 style="margin-bottom:14px;">Histórico</h3>
            ${passadas.length ? `<div class="lista-pessoas">${passadas.slice(0, 10).map(c => renderConsultaLinha(c, podeGerenciar)).join("")}</div>`
                : `<p class="texto-sm texto-suave">Sem histórico ainda.</p>`}
          </div>
        </div>`;
    }

    function renderSemanaView() {
        const inicio = inicioDaSemana(dataReferencia);
        const dias = Array.from({ length: 7 }, (_, i) => { const d = new Date(inicio); d.setDate(d.getDate() + i); return d; });
        const fim = dias[6];
        const hojeChave = paraChaveDia(new Date());

        const porDia = {};
        dias.forEach(d => { porDia[paraChaveDia(d)] = []; });
        consultas.forEach(c => {
            const chave = c.data_hora.slice(0, 10);
            if (porDia[chave]) porDia[chave].push(c);
        });
        Object.values(porDia).forEach(lista => lista.sort((a, b) => a.data_hora.localeCompare(b.data_hora)));

        return `
        <div class="cartao">
          <div class="linha-entre" style="margin-bottom:16px;">
            <button type="button" class="botao-icone" id="btn-periodo-anterior" data-passo="-7" title="Semana anterior">←</button>
            <strong class="texto-sm">${formatarData(paraChaveDia(inicio))} – ${formatarData(paraChaveDia(fim))}</strong>
            <button type="button" class="botao-icone" id="btn-periodo-proximo" data-passo="7" title="Próxima semana">→</button>
          </div>
          <div class="agenda-grade-semana">
            ${dias.map(d => {
                const chave = paraChaveDia(d);
                const ehHoje = chave === hojeChave;
                const doDia = porDia[chave] || [];
                return `
                <div class="agenda-coluna-dia ${ehHoje ? "agenda-coluna-hoje" : ""}">
                  <div class="agenda-cabecalho-dia">
                    <div class="texto-xs texto-suave">${DIAS_SEMANA_ABREV[d.getDay()]}</div>
                    <div style="font-weight:700; font-size:15px;">${d.getDate()}</div>
                  </div>
                  <div class="agenda-corpo-dia">
                    ${doDia.length ? doDia.map(c => renderConsultaChip(c)).join("") : `<p class="texto-xs texto-suave" style="padding:6px 2px;">—</p>`}
                  </div>
                </div>`;
            }).join("")}
          </div>
        </div>`;
    }

    function renderMesView() {
        const ano = dataReferencia.getFullYear();
        const mes = dataReferencia.getMonth();
        const primeiroDiaMes = new Date(ano, mes, 1);
        const inicioGrade = inicioDaSemana(primeiroDiaMes);
        const hojeChave = paraChaveDia(new Date());

        const porDia = {};
        consultas.forEach(c => {
            const chave = c.data_hora.slice(0, 10);
            (porDia[chave] = porDia[chave] || []).push(c);
        });
        Object.values(porDia).forEach(lista => lista.sort((a, b) => a.data_hora.localeCompare(b.data_hora)));

        const celulas = Array.from({ length: 42 }, (_, i) => { const d = new Date(inicioGrade); d.setDate(d.getDate() + i); return d; });

        return `
        <div class="cartao">
          <div class="linha-entre" style="margin-bottom:16px;">
            <button type="button" class="botao-icone" id="btn-mes-anterior" title="Mês anterior">←</button>
            <strong class="texto-sm">${MESES_NOME[mes]} de ${ano}</strong>
            <button type="button" class="botao-icone" id="btn-mes-proximo" title="Próximo mês">→</button>
          </div>
          <div class="agenda-grade-mes-cabecalho">
            ${DIAS_SEMANA_ABREV.map(d => `<div class="texto-xs texto-suave" style="text-align:center; font-weight:700;">${d}</div>`).join("")}
          </div>
          <div class="agenda-grade-mes">
            ${celulas.map(d => {
                const chave = paraChaveDia(d);
                const foraDoMes = d.getMonth() !== mes;
                const ehHoje = chave === hojeChave;
                const doDia = (porDia[chave] || []);
                return `
                <div class="agenda-celula-mes ${foraDoMes ? "agenda-celula-fora" : ""} ${ehHoje ? "agenda-celula-hoje" : ""} ${doDia.length ? "btn-abrir-dia-mes" : ""}" data-dia="${chave}">
                  <div class="texto-xs" style="font-weight:${ehHoje ? "700" : "500"}; margin-bottom:3px;">${d.getDate()}</div>
                  ${doDia.slice(0, 2).map(c => { const corC = corSegura(c.profissional_cor, "var(--cor-marca)"); const corTextoC = _corTextoChipProfissional(corSegura(c.profissional_cor, "#5B4FE9")); return `<div class="agenda-pontinho-mes" style="background:${corC}22; border-left:3px solid ${corC}; color:${corTextoC};">${formatarHoraCurta(c.data_hora)} ${escapeHtml((c.paciente_nome || "").split(" ")[0])}</div>`; }).join("")}
                  ${doDia.length > 2 ? `<div class="texto-xs texto-suave">+${doDia.length - 2} mais</div>` : ""}
                </div>`;
            }).join("")}
          </div>
        </div>`;
    }

    // ------------------------------------------------------------ Visão "Por Profissional" (grade horária semanal)

    // Grade horária genérica (spec 07/10/2026): cada coluna é um dia de um
    // profissional (Semana/Dia "Por Profissional") ou um profissional num dia
    // (Dia do modo Geral). Ocupa a altura que sobra da tela e tudo é
    // posicionado em % da faixa horária — ver agenda_faixa.js.
    function renderGradeHoraria({ titulo, colunas, larga }) {
        const daGrade = consultas.filter(c => colunas.some(col => col.profissionalId === c.profissional_id && col.chave === c.data_hora.slice(0, 10)));
        const ausDaGrade = colunas.flatMap(col => ocorrenciasDaColuna(ausencias, col.profissionalId, col.chave));
        const org = Sessao.usuario.organizacao || {};
        faixaAtual = calcularFaixaAgenda(daGrade, org.agenda_hora_inicio, org.agenda_hora_fim, ausDaGrade);
        const total = faixaAtual.fim - faixaAtual.ini;
        const pct = m => ((m - faixaAtual.ini) / total) * 100;

        const linhas = [];
        for (let m = Math.ceil(faixaAtual.ini / 30) * 30; m < faixaAtual.fim; m += 30) {
            linhas.push(`<div class="agenda-linha-hora ${m % 60 ? "meia" : ""}" style="top:${pct(m)}%;"></div>`);
        }
        const rotulos = [];
        for (let m = Math.ceil(faixaAtual.ini / 60) * 60; m < faixaAtual.fim; m += 60) {
            rotulos.push(`<div class="agenda-rotulo-hora" style="top:${pct(m)}%; ${m === faixaAtual.ini ? "transform:none;" : ""}">${minutosParaHHMM(m)}</div>`);
        }

        function renderBloco(c) {
            const inicioMin = minutoDoDia(c.data_hora);
            if (inicioMin === null) return "";
            const duracao = c.duracao_min || AGENDA_DURACAO_PADRAO;
            const info = STATUS_CONSULTA_INFO[c.status] || STATUS_CONSULTA_INFO.agendada;
            const desmarcada = c.status === "cancelada";
            return `
            <div class="agenda-bloco-consulta btn-abrir-editar-consulta ${desmarcada ? "status-desmarcada" : ""}" data-id="${c.id}"
                 draggable="${podeEditarAgendaDe(c.profissional_id) ? "true" : "false"}"
                 style="top:${pct(inicioMin)}%; height:calc(${(duracao / total) * 100}% - 2px); ${desmarcada ? "" : `border-color:${info.cor};`}"
                 title="${escapeHtml(`${info.label} · ${c.paciente_nome || ""}`)}">
              <div class="agenda-bloco-hora">${info.icone}${minutosParaHHMM(inicioMin)} – ${minutosParaHHMM(inicioMin + duracao)}</div>
              <div class="agenda-bloco-nome">${escapeHtml(c.paciente_nome || "")}</div>
            </div>`;
        }

        function renderAusencia(o) {
            const ini = o.dia_inteiro ? faixaAtual.ini : hhmmParaMinutos(o.hora_inicio);
            const fim = o.dia_inteiro ? faixaAtual.fim : hhmmParaMinutos(o.hora_fim);
            if (ini === null || fim === null) return "";
            return `
            <div class="agenda-bloco-ausencia btn-abrir-ausencia" data-idx="${ausencias.indexOf(o)}"
                 style="top:${pct(ini)}%; height:${((fim - ini) / total) * 100}%;"
                 title="${escapeHtml(`Ausente${o.motivo ? " · " + o.motivo : ""}`)}">
              ⛔ Ausente${o.motivo ? ` · ${escapeHtml(o.motivo)}` : ""}
            </div>`;
        }

        return `
        <section class="agenda-cartao-grade">
          ${titulo}
          <div class="agenda-grade-rolagem">
            <div class="agenda-grade-cab ${larga ? "agenda-grade-larga" : ""}" style="--agenda-dias:${colunas.length};">
              <div></div>
              ${colunas.map(col => `<div class="agenda-grade-dia ${col.hoje ? "hoje" : ""}">${col.cabecalho}</div>`).join("")}
            </div>
            <div class="agenda-grade-corpo ${larga ? "agenda-grade-larga" : ""}" style="--agenda-dias:${colunas.length};">
              <div class="agenda-coluna-horas">${rotulos.join("")}</div>
              ${colunas.map(col => {
                  const editavel = podeEditarAgendaDe(col.profissionalId);
                  return `
                  <div class="agenda-coluna-grade droppable-dia ${editavel ? "btn-slot-vazio editavel" : ""} ${col.hoje ? "hoje" : ""}" data-dia="${col.chave}" data-prof="${col.profissionalId}">
                    ${linhas.join("")}
                    ${ocorrenciasDaColuna(ausencias, col.profissionalId, col.chave).map(renderAusencia).join("")}
                    ${daGrade.filter(c => c.profissional_id === col.profissionalId && c.data_hora.slice(0, 10) === col.chave).map(renderBloco).join("")}
                  </div>`;
              }).join("")}
            </div>
          </div>
          <div style="margin-top:8px;">${renderLegendaStatus()}</div>
        </section>`;
    }

    function renderVisaoPorProfissional() {
        if (!profissionaisTodos.length) {
            return `<div class="cartao estado-vazio"><p>Nenhum profissional cadastrado ainda.</p></div>`;
        }
        const profSelecionado = profissionaisTodos.find(p => p.id === profissionalSelecionadoId) || profissionaisTodos[0];
        const consultasDoProf = consultas.filter(c => c.profissional_id === profSelecionado.id);
        const dias = escalaProf === "dia" ? [new Date(dataReferencia)] : diasDaGradeSemana(inicioDaSemana(dataReferencia), consultasDoProf);
        const hojeChave = paraChaveDia(new Date());
        const editavel = podeEditarAgendaDe(profSelecionado.id);
        const titulo = `
          <div class="linha gap-2" style="align-items:baseline; flex-wrap:wrap; margin-bottom:6px;">
            <span class="agenda-ponto-cor" style="background:${corSegura(profSelecionado.cor_agenda, "var(--cor-marca)")}; width:12px; height:12px;"></span>
            <strong>${escapeHtml(profSelecionado.nome)}</strong>
            <span class="texto-xs texto-suave">${escapeHtml(profSelecionado.especialidade || "")}</span>
            <span class="texto-xs texto-suave">· ${editavel ? "clique num horário livre para agendar, ou arraste uma consulta para remarcar" : "somente visualização — só o Gestor ou quem atende pode editar esta agenda"}</span>
          </div>`;
        return renderGradeHoraria({
            titulo,
            colunas: dias.map(d => ({
                chave: paraChaveDia(d), profissionalId: profSelecionado.id, hoje: paraChaveDia(d) === hojeChave,
                cabecalho: `${DIAS_SEMANA_ABREV[d.getDay()]} <strong>${d.getDate()}</strong>`,
            })),
        });
    }

    // Visão Dia do modo Geral: uma coluna por profissional que o usuário
    // enxerga (profissional sem permissão total só vê a dele).
    function profissionaisVisiveisNoDia() {
        const daAgenda = (u.papel === "profissional" && !u.agenda_permissao_total)
            ? profissionaisTodos.filter(p => p.id === u.id)
            : profissionaisTodos;
        return daAgenda.filter(p => !profsOcultosDia.has(p.id));
    }

    function renderVisaoDiaGeral() {
        const lista = profissionaisVisiveisNoDia();
        if (!lista.length) return `<div class="cartao estado-vazio"><p>Nenhum profissional selecionado — escolha na lista ao lado.</p></div>`;
        const chave = paraChaveDia(dataReferencia);
        const hoje = chave === paraChaveDia(new Date());
        return renderGradeHoraria({
            titulo: `<p class="texto-xs texto-suave" style="margin-bottom:6px;">Clique num horário livre para agendar, ou arraste uma consulta para outro horário ou profissional.</p>`,
            larga: true,
            colunas: lista.map(p => ({
                chave, profissionalId: p.id, hoje,
                cabecalho: `<span class="agenda-ponto-cor" style="background:${corSegura(p.cor_agenda, "var(--cor-marca)")};"></span> <strong>${escapeHtml((p.nome || "").split(" ")[0])}</strong><br><span class="texto-xs texto-suave">${escapeHtml(p.especialidade || "")}</span>`,
            })),
        });
    }

    function podeEditarAgendaDe(profissionalIdAlvo) {
        if (u.papel === "gestor" || u.papel === "secretaria") return true;
        if (u.papel === "profissional") return u.id === profissionalIdAlvo || !!u.agenda_permissao_total;
        return false;
    }

    function renderizarTudo() {
        let conteudo;
        let acoes = "";
        if (base === "responsavel") {
            conteudo = renderListaView();
        } else {
            const area = modoVisao === "porProfissional"
                ? renderVisaoPorProfissional()
                : visaoAtual === "dia"
                  ? renderVisaoDiaGeral()
                  : `<div style="margin-bottom:12px;">${visaoAtual !== "lista" ? renderLegendaProfissionais() : ""}</div>`
                    + (visaoAtual === "lista" ? renderListaView() : visaoAtual === "semana" ? renderSemanaView() : renderMesView());
            conteudo = `<div class="agenda-corpo">${renderListaProfissionais()}<div class="agenda-area">${area}</div></div>`;
            acoes = renderToggleModo()
                + (modoVisao === "porProfissional" ? renderNavPeriodo(escalaProf === "dia", true)
                    : renderBotoesVisao() + (visaoAtual === "dia" ? renderNavPeriodo(true, false) : ""))
                + (podeGerenciar ? `<button class="botao botao-primario botao-sm" id="btn-nova-consulta">+ Agendar</button>` : "");
        }
        const app2 = document.getElementById("app");
        app2.innerHTML = montarShell(conteudo, acoes);
        if (base !== "responsavel") {
            // Página da agenda ocupa a tela inteira, sem rolar (spec 24/09/2026)
            // — a classe some sozinha quando outra tela redesenha o #app.
            const shell = app2.querySelector(".shell");
            if (shell) shell.classList.add("shell-agenda");
            anexarEventosShell();
        }
        conectarEventos();
    }

    // Reconsulta só as consultas (sem recriar a tela) e re-renderiza mantendo
    // o estado atual (semana/mês em exibição, profissional selecionado, modo
    // de visão) — usado depois de qualquer ação (agendar, editar, remarcar
    // por arrastar, mudar status, excluir), pra não jogar o usuário de volta
    // pro estado inicial da tela a cada clique.
    async function recarregarConsultas() {
        const [lista] = await Promise.all([Api.get("/agenda"), carregarAusencias(true)]);
        consultas = lista;
        renderizarTudo();
    }

    function conectarEventos() {
        document.querySelectorAll(".btn-modo-agenda").forEach(btn => btn.addEventListener("click", () => {
            modoVisao = btn.dataset.modo;
            renderizarTudo();
        }));
        document.querySelectorAll(".btn-visao-agenda").forEach(btn => btn.addEventListener("click", () => {
            visaoAtual = btn.dataset.visao;
            renderizarComAusencias();
        }));
        document.querySelectorAll(".btn-selecionar-profissional").forEach(btn => btn.addEventListener("click", () => {
            const id = parseInt(btn.dataset.id, 10);
            if (modoVisao === "geral" && visaoAtual === "dia") {
                if (profsOcultosDia.has(id)) profsOcultosDia.delete(id); else profsOcultosDia.add(id);
                renderizarTudo();
                return;
            }
            profissionalSelecionadoId = id;
            modoVisao = "porProfissional"; // nas outras visões do modo Geral, abre a agenda dele
            renderizarComAusencias();
        }));
        const btnTodos = document.querySelector(".agenda-item-prof[data-todos]");
        if (btnTodos) btnTodos.addEventListener("click", () => {
            if (modoVisao === "geral" && visaoAtual === "dia") { profsOcultosDia.clear(); renderizarTudo(); }
        });
        const filtro = document.getElementById("agenda-filtro-prof");
        if (filtro) filtro.addEventListener("input", () => {
            // Filtra sem redesenhar a tela (mantém o foco no campo).
            filtroProfissional = filtro.value;
            const termo = filtroProfissional.trim().toLowerCase();
            document.querySelectorAll(".agenda-lista-profs li[data-nome]").forEach(li => {
                li.style.display = !termo || li.dataset.nome.includes(termo) ? "" : "none";
            });
        });
        const btnHoje = document.getElementById("btn-hoje");
        if (btnHoje) btnHoje.addEventListener("click", () => { dataReferencia = new Date(); renderizarComAusencias(); });
        document.querySelectorAll(".btn-escala-prof").forEach(btn => btn.addEventListener("click", () => {
            escalaProf = btn.dataset.escala;
            renderizarComAusencias();
        }));
        ["btn-periodo-anterior", "btn-periodo-proximo"].forEach(id => {
            const b = document.getElementById(id);
            if (b) b.addEventListener("click", () => {
                dataReferencia.setDate(dataReferencia.getDate() + parseInt(b.dataset.passo, 10));
                renderizarComAusencias();
            });
        });
        document.querySelectorAll(".btn-status-consulta").forEach(btn => btn.addEventListener("click", async (e) => {
            e.stopPropagation();
            try {
                await mudarStatusConsulta(btn.dataset.id, btn.dataset.status);
                Toast.sucesso("Consulta atualizada!");
                recarregarConsultas();
            } catch (err) { Toast.erro(err.message); }
        }));
        document.querySelectorAll(".btn-excluir-consulta").forEach(btn => btn.addEventListener("click", (e) => {
            e.stopPropagation();
            excluirConsultaComPergunta(btn.dataset.id, btn.dataset.serie, recarregarConsultas);
        }));
        document.querySelectorAll(".btn-abrir-editar-consulta").forEach(el => el.addEventListener("click", (e) => {
            e.stopPropagation();
            const consulta = consultas.find(c => String(c.id) === String(el.dataset.id));
            if (consulta) abrirModalEditarConsulta(consulta, recarregarConsultas);
        }));
        const btnNova = document.getElementById("btn-nova-consulta");
        if (btnNova) btnNova.addEventListener("click", () => abrirModalNovaConsulta({}, recarregarConsultas));

        const btnMesAnt = document.getElementById("btn-mes-anterior");
        if (btnMesAnt) btnMesAnt.addEventListener("click", () => { dataReferencia.setMonth(dataReferencia.getMonth() - 1); renderizarComAusencias(); });
        const btnMesProx = document.getElementById("btn-mes-proximo");
        if (btnMesProx) btnMesProx.addEventListener("click", () => { dataReferencia.setMonth(dataReferencia.getMonth() + 1); renderizarComAusencias(); });

        document.querySelectorAll(".btn-abrir-dia-mes").forEach(cel => cel.addEventListener("click", () => {
            const chave = cel.dataset.dia;
            const doDia = consultas.filter(c => c.data_hora.slice(0, 10) === chave).sort((a, b) => a.data_hora.localeCompare(b.data_hora));
            abrirModalConsultasDoDia(chave, doDia, podeGerenciar, recarregarConsultas);
        }));

        document.querySelectorAll(".btn-abrir-ausencia").forEach(bloco => bloco.addEventListener("click", (e) => {
            e.stopPropagation();
            const o = ausencias[parseInt(bloco.dataset.idx, 10)];
            if (o) abrirModalAusencia({ ocorrencia: o }, recarregarConsultas);
        }));

        // Clique num horário livre — abre "Agendar" já preenchido (dia e profissional da coluna).
        document.querySelectorAll(".btn-slot-vazio").forEach(coluna => coluna.addEventListener("click", (e) => {
            if (e.target.closest(".agenda-bloco-consulta, .agenda-bloco-ausencia") || !faixaAtual) return;
            const profId = parseInt(coluna.dataset.prof, 10);
            if (!podeEditarAgendaDe(profId)) return;
            const rect = coluna.getBoundingClientRect();
            const minuto = minutoNaFaixa(e.clientY - rect.top, rect.height, faixaAtual);
            if (intervaloBloqueado(ausencias, profId, coluna.dataset.dia, minuto, minuto + AGENDA_PASSO_MIN)) {
                Toast.erro("Profissional ausente nesse horário."); return;
            }
            abrirModalNovaConsulta({ profissionalId: profId, data: coluna.dataset.dia, hora: minutosParaHHMM(minuto) }, recarregarConsultas);
        }));

        // Arrastar-e-soltar pra remarcar (só na visão "Por Profissional").
        document.querySelectorAll(".agenda-bloco-consulta[draggable='true']").forEach(bloco => {
            bloco.addEventListener("dragstart", (e) => {
                idArrastando = bloco.dataset.id;
                e.dataTransfer.effectAllowed = "move";
                setTimeout(() => bloco.classList.add("arrastando"), 0);
            });
            bloco.addEventListener("dragend", () => bloco.classList.remove("arrastando"));
        });
        document.querySelectorAll(".droppable-dia").forEach(coluna => {
            coluna.addEventListener("dragover", (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; });
            coluna.addEventListener("drop", async (e) => {
                e.preventDefault();
                if (!idArrastando || !faixaAtual) return;
                const consulta = consultas.find(c => String(c.id) === String(idArrastando));
                idArrastando = null;
                if (!consulta) return;
                const rect = coluna.getBoundingClientRect();
                const minuto = minutoNaFaixa(e.clientY - rect.top, rect.height, faixaAtual);
                const hhmm = minutosParaHHMM(minuto);
                const profDestino = parseInt(coluna.dataset.prof, 10);
                const duracao = consulta.duracao_min || AGENDA_DURACAO_PADRAO;
                if (intervaloBloqueado(ausencias, profDestino, coluna.dataset.dia, minuto, minuto + duracao)) {
                    Toast.erro("Profissional ausente nesse horário."); return;
                }
                const corpo = { data_hora: `${coluna.dataset.dia} ${hhmm}:00` };
                if (profDestino !== consulta.profissional_id) corpo.profissional_id = profDestino;
                try {
                    await comEncaixe(encaixe => Api.put(`/agenda/${consulta.id}`, encaixe ? { ...corpo, encaixe: true } : corpo));
                    const prof = profissionaisTodos.find(p => p.id === profDestino);
                    Toast.sucesso(`Consulta remarcada para ${formatarData(coluna.dataset.dia)} às ${hhmm}${corpo.profissional_id && prof ? ` com ${prof.nome}` : ""}.`);
                    recarregarConsultas();
                } catch (err) { Toast.erro(err.message); }
            });
        });
    }

    await renderizarComAusencias();
}

function formatarHoraCurta(dataHora) {
    return formatarHoraLocal(dataHora);   // aceita hora sem zero ("9:00:00", do seed)
}

// Contraste automático nas cores dos profissionais (insight do usuário,
// 02/09/2026): mesmo princípio do _corTextoContraste usado no botão de
// acento — calcula o brilho da cor do profissional e escolhe entre texto
// escuro ou branco automaticamente, em vez de supor que "texto escuro"
// sempre funciona. O chip pinta o fundo com a cor a ~13% de opacidade
// (${cor}22), então quem importa pro contraste é a cor JÁ misturada com o
// fundo claro, não a cor pura — daí o clarearCor(cor, 0.87) antes de medir
// o brilho (87% = o quanto o branco domina numa mistura a 13% de opacidade).
function _corTextoChipProfissional(corHex) {
    return _corTextoContraste(clarearCor(corHex, 0.87));
}

function renderConsultaChip(c) {
    const cor = corSegura(c.profissional_cor, "var(--cor-marca)");
    const corTexto = _corTextoChipProfissional(corSegura(c.profissional_cor, "#5B4FE9"));
    return `
    <div class="agenda-chip btn-abrir-editar-consulta" data-id="${c.id}" style="background:${cor}22; border-left:3px solid ${cor}; color:${corTexto}; cursor:pointer;" title="${escapeHtml(c.paciente_nome || "")} · ${escapeHtml(c.profissional_nome || "")} — clique para editar">
      <strong>${formatarHoraCurta(c.data_hora)}</strong> ${escapeHtml((c.paciente_nome || "").split(" ")[0])}
    </div>`;
}

function abrirModalConsultasDoDia(chaveDia, doDia, podeGerenciar, aoAtualizar) {
    const atualizar = aoAtualizar || despachar;
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:16px;">${formatarData(chaveDia)}</h3>
        ${doDia.length ? `<div class="lista-pessoas">${doDia.map(c => renderConsultaLinha(c, podeGerenciar)).join("")}</div>` : `<p class="texto-sm texto-suave">Nenhuma consulta neste dia.</p>`}
        <button type="button" class="botao botao-secundario" id="btn-cancelar-modal" style="width:100%; margin-top:16px;">Fechar</button>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    modal.querySelectorAll(".btn-status-consulta").forEach(btn => btn.addEventListener("click", async () => {
        try {
            await mudarStatusConsulta(btn.dataset.id, btn.dataset.status);
            Toast.sucesso("Consulta atualizada!");
            modal.remove();
            atualizar();
        } catch (err) { Toast.erro(err.message); }
    }));
    modal.querySelectorAll(".btn-excluir-consulta").forEach(btn => btn.addEventListener("click", async () => {
        await excluirConsultaComPergunta(btn.dataset.id, btn.dataset.serie, atualizar);
        modal.remove();
    }));
    modal.querySelectorAll(".btn-abrir-editar-consulta").forEach(el => el.addEventListener("click", (e) => {
        e.stopPropagation();
        const consulta = doDia.find(c => String(c.id) === String(el.dataset.id));
        if (consulta) { modal.remove(); abrirModalEditarConsulta(consulta, atualizar); }
    }));
}

function renderConsultaLinha(c, podeGerenciar) {
    const statusCor = { agendada: "neutro", confirmada: "marca", realizada: "sucesso", cancelada: "alerta", faltou: "alerta",
                        falta_justificada: "alerta", desmarcada_profissional: "neutro" }[c.status] || "neutro";
    const corProf = corSegura(c.profissional_cor, "var(--cor-marca)");
    return `
    <div class="pessoa-linha" style="border-left:3px solid ${corProf}; padding-left:8px;">
      <div class="pessoa-avatar">${c.avatar_mascote ? escapeHtml(emojiMascote(c.avatar_mascote, Sessao.usuario?.organizacao)) : "📅"}</div>
      <div class="pessoa-info">
        <div class="pessoa-nome">${escapeHtml(c.paciente_nome || "")}${c.serie_recorrencia_id ? ` <span title="Faz parte de uma série recorrente" style="font-size:12px;">🔁</span>` : ""}</div>
        <div class="pessoa-sub"><span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${corProf}; margin-right:4px;"></span>${formatarDataHoraLocal(c.data_hora)} · ${escapeHtml(c.profissional_nome || "")}</div>
      </div>
      <span class="badge badge-${statusCor}">${escapeHtml((STATUS_CONSULTA_INFO[c.status] || {}).label || c.status)}</span>
      ${podeGerenciar && c.status !== "realizada" && c.status !== "cancelada" ? `
        <div class="linha gap-1">
          <button class="botao-icone btn-abrir-editar-consulta" data-id="${c.id}" title="Editar" style="width:32px;height:32px;font-size:13px;">✏️</button>
          ${c.status === "agendada" ? `<button class="botao-icone btn-status-consulta" data-id="${c.id}" data-status="confirmada" title="Confirmar agendamento" style="width:32px;height:32px;font-size:13px;">📌</button>` : ""}
          <button class="botao-icone btn-status-consulta" data-id="${c.id}" data-status="realizada" title="Marcar como realizada" style="width:32px;height:32px;font-size:13px;">✓</button>
          <button class="botao-icone btn-status-consulta" data-id="${c.id}" data-status="cancelada" title="Cancelar" style="width:32px;height:32px;font-size:13px;">✕</button>
          <button class="botao-icone btn-excluir-consulta" data-id="${c.id}" data-serie="${c.serie_recorrencia_id || ""}" title="Excluir" style="width:32px;height:32px;font-size:13px;">🗑️</button>
        </div>` : ""}
    </div>`;
}

async function excluirConsultaComPergunta(consultaId, serieId, aoAtualizar) {
    const atualizar = aoAtualizar || despachar;
    let excluirSerieInteira = false;
    if (serieId) {
        const escolha = confirm(
            "Esta consulta faz parte de uma série recorrente.\n\n" +
            "OK = Excluir esta E todas as futuras da série\n" +
            "Cancelar = Escolher excluir só esta"
        );
        if (escolha) {
            excluirSerieInteira = true;
        } else if (!confirm("Excluir só esta consulta (mantendo as demais da série)?")) {
            return; // desistiu dos dois
        }
    } else if (!confirm("Excluir esta consulta? Essa ação não pode ser desfeita.")) {
        return;
    }
    try {
        await Api.del(`/agenda/${consultaId}${excluirSerieInteira ? "?serie=1" : ""}`);
        Toast.sucesso(excluirSerieInteira ? "Consultas futuras da série excluídas." : "Consulta excluída.");
        atualizar();
    } catch (err) { Toast.erro(err.message); }
}

async function abrirModalNovaConsulta(preSelecao, aoAtualizar) {
    preSelecao = preSelecao || {};
    const atualizar = aoAtualizar || despachar;
    const [pacientes, profissionais] = await Promise.all([
        Api.get("/pessoas/pacientes"),
        Api.get("/pessoas/profissionais?incluir_gestor=1"),
    ]);
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:14px;">Agendar</h3>
        ${renderSeletorTipoAgendamento("consulta")}
        <form id="form-nova-consulta">
          <div class="campo"><label>Paciente ${ASTERISCO_OBRIGATORIO}</label>
            <select id="ag-paciente" required>${pacientes.map(p => `<option value="${p.id}">${escapeHtml(emojiMascote(p.avatar_mascote, Sessao.usuario?.organizacao))} ${escapeHtml(p.nome)}</option>`).join("")}</select>
          </div>
          <div class="campo"><label>Profissional ${ASTERISCO_OBRIGATORIO}</label>
            <select id="ag-profissional" required>${profissionais.map(p => `<option value="${p.id}" ${preSelecao.profissionalId === p.id ? "selected" : ""}>${escapeHtml(p.nome)} (${escapeHtml(p.especialidade || "")})</option>`).join("")}</select>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1.3;"><label>Data ${ASTERISCO_OBRIGATORIO}</label><input type="date" id="ag-data" required value="${preSelecao.data || ""}" /></div>
            <div class="campo" style="flex:1;"><label>Início ${ASTERISCO_OBRIGATORIO}</label><input type="time" id="ag-hora" required value="${preSelecao.hora || "14:00"}" /></div>
            <div class="campo" style="flex:1;"><label>Fim ${ASTERISCO_OBRIGATORIO}</label><input type="time" id="ag-hora-fim" required value="" /></div>
          </div>
          <p class="texto-xs" id="aviso-disponibilidade" style="display:none; margin:-10px 0 12px; padding:8px 10px; border-radius:8px; background:#FFF3CD; color:#7A5C00;">⚠️</p>
          <div class="campo"><label>Observações</label><textarea id="ag-obs" rows="2"></textarea></div>

          <label class="linha gap-2" style="align-items:center; cursor:pointer; padding:8px 0;">
            <input type="checkbox" id="ag-recorrente" />
            <span class="texto-sm">🔁 Repetir esta consulta</span>
          </label>
          <div id="wrap-recorrencia" style="display:none;">
            <div class="linha gap-4">
              <div class="campo" style="flex:1;"><label>Frequência</label>
                <select id="ag-frequencia">
                  <option value="semanal">Toda semana</option>
                  <option value="quinzenal">A cada 2 semanas</option>
                  <option value="mensal">Todo mês</option>
                </select>
              </div>
              <div class="campo" style="flex:1;"><label>Quantas vezes?</label><input type="number" id="ag-repeticoes" value="4" min="2" max="52" /></div>
            </div>
            <p class="texto-xs texto-suave">Ex: "toda semana" + "4 vezes" agenda a mesma consulta nas próximas 4 semanas, sempre no mesmo dia e horário.</p>
          </div>

          <div class="linha gap-3" style="margin-top:16px;">
            <button type="submit" class="botao botao-primario">Agendar</button>
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    const lerDuracao = ligarInicioFim("ag-hora", "ag-hora-fim", duracaoPadraoClinica());
    modal.querySelectorAll(".btn-tipo-agendamento").forEach(btn => btn.addEventListener("click", () => {
        if (btn.dataset.tipo !== "ausencia") return;
        const pre = {
            profissionalId: parseInt(document.getElementById("ag-profissional").value, 10),
            data: document.getElementById("ag-data").value,
            hora: document.getElementById("ag-hora").value,
        };
        modal.remove();
        abrirModalAusencia(pre, atualizar);
    }));
    document.getElementById("ag-recorrente").addEventListener("change", (e) => {
        document.getElementById("wrap-recorrencia").style.display = e.target.checked ? "block" : "none";
    });

    const cacheDisponibilidade = {};
    async function checarDisponibilidade() {
        const profId = document.getElementById("ag-profissional").value;
        const dataStr = document.getElementById("ag-data").value;
        const avisoEl = document.getElementById("aviso-disponibilidade");
        if (!profId || !dataStr) { avisoEl.style.display = "none"; return; }
        if (!cacheDisponibilidade[profId]) {
            try { cacheDisponibilidade[profId] = await Api.get(`/pessoas/profissionais/${profId}/disponibilidade`); }
            catch (e) { avisoEl.style.display = "none"; return; }
        }
        const diaSemana = new Date(dataStr + "T00:00:00").getDay();
        const infoDia = cacheDisponibilidade[profId].find(d => d.dia_semana === diaSemana);
        if (infoDia && infoDia.ausente) {
            avisoEl.textContent = `⚠️ ${profissionais.find(p => String(p.id) === profId)?.nome || "Este profissional"} costuma estar ausente às ${infoDia.dia_nome}s. Confirme antes de agendar.`;
            avisoEl.style.display = "block";
        } else {
            avisoEl.style.display = "none";
        }
    }
    document.getElementById("ag-profissional").addEventListener("change", checarDisponibilidade);
    document.getElementById("ag-data").addEventListener("change", checarDisponibilidade);
    if (preSelecao.profissionalId && preSelecao.data) checarDisponibilidade();
    document.getElementById("form-nova-consulta").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            const data = document.getElementById("ag-data").value;
            const hora = document.getElementById("ag-hora").value;
            const dataHora = `${data} ${hora}:00`;
            const duracao = lerDuracao();
            if (!duracao) { Toast.erro("O horário de fim precisa ser depois do início."); return; }
            const ehRecorrente = document.getElementById("ag-recorrente").checked;
            const corpoBase = {
                paciente_id: parseInt(document.getElementById("ag-paciente").value),
                profissional_id: parseInt(document.getElementById("ag-profissional").value),
                data_hora: dataHora,
                duracao_min: duracao,
                observacoes: document.getElementById("ag-obs").value.trim(),
            };
            if (ehRecorrente) {
                const corpoSerie = {
                    ...corpoBase,
                    frequencia: document.getElementById("ag-frequencia").value,
                    repeticoes: parseInt(document.getElementById("ag-repeticoes").value) || 2,
                };
                const r = await comEncaixe(encaixe => Api.post("/agenda/recorrente", encaixe ? { ...corpoSerie, encaixe: true } : corpoSerie));
                const puladas = r.datas_puladas || [];
                Toast.sucesso(`${r.total_criadas} consultas agendadas! 🔁`);
                if (puladas.length) Toast.info(`Não agendado em ${puladas.map(formatarData).join(", ")}: profissional ausente.`);
            } else {
                await comEncaixe(encaixe => Api.post("/agenda", encaixe ? { ...corpoBase, encaixe: true } : corpoBase));
                Toast.sucesso("Consulta agendada!");
            }
            modal.remove();
            atualizar();
        } catch (err) { Toast.erro(err.message); }
    });
}

async function abrirModalEditarConsulta(consulta, aoAtualizar) {
    const atualizar = aoAtualizar || despachar;
    const profissionais = await Api.get("/pessoas/profissionais?incluir_gestor=1");
    const dataAtual = (consulta.data_hora || "").slice(0, 10);
    // minutoDoDia aceita hora sem zero ("9:00:00", de dados antigos); o slice não.
    const minutoAtual = minutoDoDia(consulta.data_hora);
    const horaAtual = minutoAtual === null ? "" : minutosParaHHMM(minutoAtual);
    // Atender (08/10/2026): só o profissional da consulta e o gestor; a
    // secretária marca presença, mas "Finalizado" é de quem atende.
    const u = Sessao.usuario || {};
    const podeAtender = consulta.status !== "cancelada" && (u.papel === "gestor" || (u.papel === "profissional" && u.id === consulta.profissional_id));
    const ehSecretaria = u.papel === "secretaria";
    const atraso = diasDeAtraso(consulta, paraChaveDia(new Date()));
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:6px;">Editar consulta</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:10px;">${escapeHtml(consulta.paciente_nome || "")}${consulta.serie_recorrencia_id ? " · 🔁 parte de uma série (só esta ocorrência é alterada)" : ""}</p>
        ${podeAtender ? `
        <div class="linha gap-2" style="align-items:center; margin-bottom:12px; flex-wrap:wrap;">
          <a class="botao botao-primario" id="btn-atender" href="#/${u.papel === "gestor" ? "gestor" : "profissional"}/atender/${consulta.id}">${consulta.diario_id ? "✏️ Ver/editar evolução" : "▶ Atender"}</a>
          <span class="texto-xs texto-suave">${consulta.diario_id ? "Esta sessão já tem evolução." : "Abre a página de evolução desta sessão."}</span>
        </div>` : ""}
        ${atraso ? `<p class="aviso-atraso">⚠️ Esta evolução está em atraso (${atraso} ${atraso === 1 ? "dia" : "dias"}). Finalize esta sessão no "Atender".</p>` : ""}
        <div class="campo" style="margin-bottom:14px;">
          <label>Status do agendamento</label>
          <div class="linha gap-2" style="align-items:center;">
            <span id="ec-status-ponto" style="display:inline-block; width:12px; height:12px; border-radius:50%; flex-shrink:0; background:${(STATUS_CONSULTA_INFO[consulta.status] || STATUS_CONSULTA_INFO.agendada).cor}; border:1.5px solid var(--cor-borda);"></span>
            <select id="ec-status" style="flex:1;">
              ${Object.entries(STATUS_CONSULTA_INFO)
                  .filter(([valor]) => !(ehSecretaria && valor === "realizada" && consulta.status !== "realizada"))
                  .map(([valor, info]) => `<option value="${valor}" ${consulta.status === valor ? "selected" : ""}>${escapeHtml(info.label)}</option>`).join("")}
            </select>
          </div>
        </div>
        <form id="form-editar-consulta">
          <div class="campo"><label>Profissional ${ASTERISCO_OBRIGATORIO}</label>
            <select id="ec-profissional" required>${profissionais.map(p => `<option value="${p.id}" ${p.id === consulta.profissional_id ? "selected" : ""}>${escapeHtml(p.nome)} (${escapeHtml(p.especialidade || "")})</option>`).join("")}</select>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1.3;"><label>Data ${ASTERISCO_OBRIGATORIO}</label><input type="date" id="ec-data" required value="${dataAtual}" /></div>
            <div class="campo" style="flex:1;"><label>Início ${ASTERISCO_OBRIGATORIO}</label><input type="time" id="ec-hora" required value="${horaAtual}" /></div>
            <div class="campo" style="flex:1;"><label>Fim ${ASTERISCO_OBRIGATORIO}</label><input type="time" id="ec-hora-fim" required value="${calcularFim(horaAtual, consulta.duracao_min || AGENDA_DURACAO_PADRAO)}" /></div>
          </div>
          <p class="texto-xs" id="aviso-disponibilidade-edicao" style="display:none; margin:-6px 0 12px; padding:8px 10px; border-radius:8px; background:#FFF3CD; color:#7A5C00;">⚠️</p>
          <div class="campo"><label>Observações</label><textarea id="ec-obs" rows="2">${escapeHtml(consulta.observacoes || "")}</textarea></div>
          <div class="linha gap-3" style="margin-top:16px;">
            <button type="submit" class="botao botao-primario">Salvar alterações</button>
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());

    const btnAtender = document.getElementById("btn-atender");
    if (btnAtender) btnAtender.addEventListener("click", () => modal.remove());  // a página Atender abre por cima da agenda
    const lerDuracaoEd = ligarInicioFim("ec-hora", "ec-hora-fim", consulta.duracao_min || AGENDA_DURACAO_PADRAO);
    const selectStatus = document.getElementById("ec-status");
    const pontoStatus = document.getElementById("ec-status-ponto");
    selectStatus.addEventListener("change", async () => {
        const statusAnterior = consulta.status;
        const novoStatus = selectStatus.value;
        selectStatus.disabled = true;
        try {
            await mudarStatusConsulta(consulta.id, novoStatus);
            consulta.status = novoStatus; // mantém o modal coerente se continuar aberto
            pontoStatus.style.background = STATUS_CONSULTA_INFO[novoStatus].cor;
            Toast.sucesso("Status atualizado!");
            atualizar(); // não fecha o modal — a pessoa pode seguir ajustando data/hora/observações
        } catch (err) {
            Toast.erro(err.message);
            selectStatus.value = statusAnterior; // desfaz a seleção visual se a chamada falhar
        } finally {
            selectStatus.disabled = false;
        }
    });

    const cacheDisponibilidadeEdicao = {};
    async function checarDisponibilidadeEdicao() {
        const profId = document.getElementById("ec-profissional").value;
        const dataStr = document.getElementById("ec-data").value;
        const avisoEl = document.getElementById("aviso-disponibilidade-edicao");
        if (!profId || !dataStr) { avisoEl.style.display = "none"; return; }
        if (!cacheDisponibilidadeEdicao[profId]) {
            try { cacheDisponibilidadeEdicao[profId] = await Api.get(`/pessoas/profissionais/${profId}/disponibilidade`); }
            catch (e) { avisoEl.style.display = "none"; return; }
        }
        const diaSemana = new Date(dataStr + "T00:00:00").getDay();
        const infoDia = cacheDisponibilidadeEdicao[profId].find(d => d.dia_semana === diaSemana);
        if (infoDia && infoDia.ausente) {
            avisoEl.textContent = `⚠️ Este profissional costuma estar ausente às ${infoDia.dia_nome}s. Confirme antes de salvar.`;
            avisoEl.style.display = "block";
        } else {
            avisoEl.style.display = "none";
        }
    }
    document.getElementById("ec-profissional").addEventListener("change", checarDisponibilidadeEdicao);
    document.getElementById("ec-data").addEventListener("change", checarDisponibilidadeEdicao);
    checarDisponibilidadeEdicao();

    document.getElementById("form-editar-consulta").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            const data = document.getElementById("ec-data").value;
            const hora = document.getElementById("ec-hora").value;
            const duracao = lerDuracaoEd();
            if (!duracao) { Toast.erro("O horário de fim precisa ser depois do início."); return; }
            const corpoEdicao = {
                profissional_id: parseInt(document.getElementById("ec-profissional").value),
                data_hora: `${data} ${hora}:00`,
                duracao_min: duracao,
                observacoes: document.getElementById("ec-obs").value.trim(),
            };
            await comEncaixe(encaixe => Api.put(`/agenda/${consulta.id}`, encaixe ? { ...corpoEdicao, encaixe: true } : corpoEdicao));
            Toast.sucesso("Consulta atualizada!");
            modal.remove();
            atualizar();
        } catch (err) { Toast.erro(err.message); }
    });
}
