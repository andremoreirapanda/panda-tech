// ============================================================================
// views/agenda.js — Agenda de consultas (Lista + Calendário em grade + Por Profissional)
// ============================================================================

const DIAS_SEMANA_ABREV = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const MESES_NOME = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
const AGENDA_HORA_INICIO = 7;
const AGENDA_HORA_FIM = 22;
const AGENDA_ALTURA_SLOT = 30; // px por bloco de 30 min

function inicioDaSemana(data) {
    const d = new Date(data);
    d.setDate(d.getDate() - d.getDay());
    d.setHours(0, 0, 0, 0);
    return d;
}
function paraChaveDia(data) { return data.toISOString().slice(0, 10); }

async function viewAgenda(app) {
    // Garante que a sessão local nunca fique com um agenda_permissao_total
    // desatualizado — mesmo que a lista de consultas em si sempre venha
    // correta do backend, isso evita qualquer decisão de UI baseada em
    // dado velho do usuário (defesa extra, não custa a mais que 1 chamada).
    try {
        const meAtualizado = await Api.get("/auth/me");
        Sessao.usuario = { ...Sessao.usuario, ...meAtualizado };
    } catch (e) { /* se falhar, segue com o que já tinha na sessão */ }

    const u = Sessao.usuario;
    const base = u.papel === "gestor" ? "gestor" : (u.papel === "profissional" ? "profissional" : "responsavel");
    const podeGerenciar = u.papel === "gestor" || u.papel === "profissional";
    let [consultas, profissionaisTodos] = await Promise.all([
        Api.get("/agenda"),
        base !== "responsavel" ? Api.get("/pessoas/profissionais?incluir_gestor=1") : Promise.resolve([]),
    ]);

    // Estado — vive só nesta função (recriada a cada render/navegação de rota).
    // Gestor/Profissional abrem direto na visão "Por Profissional" (a mais usada no dia a dia);
    // Responsável continua na lista simples, que é a única visão que ele usa.
    let modoVisao = (base === "gestor" || base === "profissional") ? "porProfissional" : "geral"; // "geral" | "porProfissional"
    let visaoAtual = base === "responsavel" ? "lista" : "semana";
    let dataReferencia = new Date();
    let profissionalSelecionadoId = (u.papel === "profissional" ? u.id : (profissionaisTodos[0] && profissionaisTodos[0].id)) || null;
    let idArrastando = null;

    function montarShell(conteudo, acoesTopo) {
        if (base === "responsavel") {
            return renderShellMobile("#/responsavel/agenda", { icone: "📅", texto: "Agenda" }, conteudo);
        }
        return renderShellSidebar(`#/${base}/agenda`, "Agenda", conteudo, acoesTopo);
    }

    function renderToggleModo() {
        if (base === "responsavel") return "";
        return `
        <div class="linha gap-2" style="margin-bottom:14px;">
          <button type="button" class="botao botao-sm ${modoVisao === "geral" ? "botao-primario" : "botao-secundario"} btn-modo-agenda" data-modo="geral">🏥 Geral da Clínica</button>
          <button type="button" class="botao botao-sm ${modoVisao === "porProfissional" ? "botao-primario" : "botao-secundario"} btn-modo-agenda" data-modo="porProfissional">👤 Por Profissional</button>
        </div>`;
    }

    function renderSeletorVisao() {
        if (base === "responsavel") return ""; // responsável só usa a visão de lista, mais simples no celular
        const opcoes = [["lista", "📋 Lista"], ["semana", "🗓️ Semana"], ["mes", "📆 Mês"]];
        return `
        <div class="linha-entre gap-2" style="margin-bottom:16px; flex-wrap:wrap;">
          <div class="linha gap-2">
            ${opcoes.map(([v, label]) => `<button type="button" class="botao botao-sm ${visaoAtual === v ? "botao-primario" : "botao-secundario"} btn-visao-agenda" data-visao="${v}">${label}</button>`).join("")}
          </div>
          ${visaoAtual !== "lista" ? renderLegendaProfissionais() : ""}
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
            <button type="button" class="botao-icone" id="btn-semana-anterior" title="Semana anterior">←</button>
            <strong class="texto-sm">${formatarData(paraChaveDia(inicio))} – ${formatarData(paraChaveDia(fim))}</strong>
            <button type="button" class="botao-icone" id="btn-semana-proxima" title="Próxima semana">→</button>
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
                  ${doDia.slice(0, 2).map(c => { const corC = corSegura(c.profissional_cor, "var(--cor-marca)"); return `<div class="agenda-pontinho-mes" style="background:${corC}22; border-left:3px solid ${corC};">${formatarHoraCurta(c.data_hora)} ${escapeHtml((c.paciente_nome || "").split(" ")[0])}</div>`; }).join("")}
                  ${doDia.length > 2 ? `<div class="texto-xs texto-suave">+${doDia.length - 2} mais</div>` : ""}
                </div>`;
            }).join("")}
          </div>
        </div>`;
    }

    // ------------------------------------------------------------ Visão "Por Profissional" (grade horária semanal)

    function renderVisaoPorProfissional() {
        if (!profissionaisTodos.length) {
            return `<div class="cartao estado-vazio"><p>Nenhum profissional cadastrado ainda.</p></div>`;
        }
        const inicio = inicioDaSemana(dataReferencia);
        const dias = Array.from({ length: 7 }, (_, i) => { const d = new Date(inicio); d.setDate(d.getDate() + i); return d; });
        const fim = dias[6];
        const hojeChave = paraChaveDia(new Date());
        const totalSlots = (AGENDA_HORA_FIM - AGENDA_HORA_INICIO) * 2;
        const alturaGrade = totalSlots * AGENDA_ALTURA_SLOT;

        const profSelecionado = profissionaisTodos.find(p => p.id === profissionalSelecionadoId) || profissionaisTodos[0];
        const consultasDoProf = consultas.filter(c => c.profissional_id === profSelecionado.id);
        const porDia = {};
        dias.forEach(d => { porDia[paraChaveDia(d)] = []; });
        consultasDoProf.forEach(c => { const chave = c.data_hora.slice(0, 10); if (porDia[chave]) porDia[chave].push(c); });

        function possicaoBloco(c) {
            const hora = parseInt(c.data_hora.slice(11, 13));
            const minuto = parseInt(c.data_hora.slice(14, 16));
            const minutosDoInicio = (hora - AGENDA_HORA_INICIO) * 60 + minuto;
            const top = Math.max(0, (minutosDoInicio / 30) * AGENDA_ALTURA_SLOT);
            const altura = Math.max(AGENDA_ALTURA_SLOT * 0.8, ((c.duracao_min || 50) / 30) * AGENDA_ALTURA_SLOT);
            return { top, altura };
        }

        return `
        <div>
          <p class="texto-xs texto-suave" style="font-weight:700; margin-bottom:8px;">PROFISSIONAIS</p>
          <div class="agenda-pills-profissionais">
            ${profissionaisTodos.map(p => `
              <button type="button" class="agenda-pill-profissional btn-selecionar-profissional ${p.id === profSelecionado.id ? "ativo" : ""}" data-id="${p.id}">
                <span class="agenda-ponto-cor" style="background:${corSegura(p.cor_agenda, "var(--cor-marca)")};"></span>
                <span class="texto-sm">${escapeHtml(p.nome)}</span>
              </button>`).join("")}
          </div>
          <div class="cartao">
            <div class="linha-entre" style="margin-bottom:14px; flex-wrap:wrap; gap:8px;">
              <div class="linha gap-2" style="align-items:center;">
                <span class="agenda-ponto-cor" style="background:${corSegura(profSelecionado.cor_agenda, "var(--cor-marca)")}; width:12px; height:12px;"></span>
                <strong>${escapeHtml(profSelecionado.nome)}</strong>
                <span class="texto-xs texto-suave">${escapeHtml(profSelecionado.especialidade || "")}</span>
              </div>
              <div class="linha gap-2" style="align-items:center;">
                <button type="button" class="botao-icone" id="btn-semana-anterior" title="Semana anterior">←</button>
                <span class="texto-sm" style="font-weight:700;">${formatarData(paraChaveDia(inicio))} – ${formatarData(paraChaveDia(fim))}</span>
                <button type="button" class="botao-icone" id="btn-semana-proxima" title="Próxima semana">→</button>
              </div>
            </div>
            <p class="texto-xs texto-suave" style="margin-bottom:10px;">${podeEditarAgendaDe(profSelecionado.id) ? "Clique num horário livre para agendar, ou arraste uma consulta para remarcar." : "Somente visualização — só o Gestor ou quem atende pode editar esta agenda."}</p>
            <div class="agenda-grade-horaria" style="overflow-x:auto;">
              <div class="agenda-grade-horaria-inner" style="display:grid; grid-template-columns:56px repeat(7, minmax(120px, 1fr));">
                <div></div>
                ${dias.map(d => `
                  <div class="agenda-cabecalho-dia" style="${paraChaveDia(d) === hojeChave ? "background:var(--cor-marca-clara); border-radius:8px 8px 0 0;" : ""}">
                    <div class="texto-xs texto-suave">${DIAS_SEMANA_ABREV[d.getDay()]}</div>
                    <div style="font-weight:700; font-size:14px;">${d.getDate()}</div>
                  </div>`).join("")}

                <div class="agenda-coluna-horas" style="height:${alturaGrade}px;">
                  ${Array.from({ length: AGENDA_HORA_FIM - AGENDA_HORA_INICIO }, (_, i) => `
                    <div class="agenda-rotulo-hora" style="height:${AGENDA_ALTURA_SLOT * 2}px;">${String(AGENDA_HORA_INICIO + i).padStart(2, "0")}:00</div>`).join("")}
                </div>

                ${dias.map(d => {
                    const chave = paraChaveDia(d);
                    const doDia = porDia[chave] || [];
                    return `
                    <div class="agenda-coluna-grade droppable-dia" data-dia="${chave}" style="height:${alturaGrade}px; position:relative;">
                      ${Array.from({ length: totalSlots }, (_, i) => `<div class="agenda-slot-vazio btn-slot-vazio" data-dia="${chave}" data-slot="${i}" style="height:${AGENDA_ALTURA_SLOT}px;"></div>`).join("")}
                      ${doDia.map(c => {
                          const { top, altura } = possicaoBloco(c);
                          const cor = corSegura(c.profissional_cor, "var(--cor-marca)");
                          const statusRotulo = { agendada: "", confirmada: "📌", realizada: "✓", cancelada: "✕ ", faltou: "⚠️" }[c.status] || "";
                          return `
                          <div class="agenda-bloco-consulta btn-abrir-editar-consulta" data-id="${c.id}" draggable="${podeEditarAgendaDe(c.profissional_id) ? "true" : "false"}"
                               style="top:${top}px; height:${altura}px; background:${cor}; ${c.status === "cancelada" ? "opacity:.45; text-decoration:line-through;" : ""}">
                            <div class="texto-xs" style="font-weight:700; line-height:1.2;">${statusRotulo}${formatarHoraCurta(c.data_hora)} ${escapeHtml((c.paciente_nome || "").split(" ")[0])}</div>
                          </div>`;
                      }).join("")}
                    </div>`;
                }).join("")}
              </div>
            </div>
          </div>
        </div>`;
    }

    function podeEditarAgendaDe(profissionalIdAlvo) {
        if (u.papel === "gestor") return true;
        if (u.papel === "profissional") return u.id === profissionalIdAlvo || !!u.agenda_permissao_total;
        return false;
    }

    function renderizarTudo() {
        let conteudoPrincipal;
        if (modoVisao === "porProfissional") {
            conteudoPrincipal = renderVisaoPorProfissional();
        } else {
            conteudoPrincipal = renderSeletorVisao() + (visaoAtual === "lista" ? renderListaView() : visaoAtual === "semana" ? renderSemanaView() : renderMesView());
        }
        const conteudo = renderToggleModo() + conteudoPrincipal;
        const app2 = document.getElementById("app");
        app2.innerHTML = montarShell(conteudo, podeGerenciar ? `<button class="botao botao-primario botao-sm" id="btn-nova-consulta">+ Agendar</button>` : "");
        if (base !== "responsavel") anexarEventosShell();
        conectarEventos();
    }

    // Reconsulta só as consultas (sem recriar a tela) e re-renderiza mantendo
    // o estado atual (semana/mês em exibição, profissional selecionado, modo
    // de visão) — usado depois de qualquer ação (agendar, editar, remarcar
    // por arrastar, mudar status, excluir), pra não jogar o usuário de volta
    // pro estado inicial da tela a cada clique.
    async function recarregarConsultas() {
        consultas = await Api.get("/agenda");
        renderizarTudo();
    }

    function conectarEventos() {
        document.querySelectorAll(".btn-modo-agenda").forEach(btn => btn.addEventListener("click", () => {
            modoVisao = btn.dataset.modo;
            renderizarTudo();
        }));
        document.querySelectorAll(".btn-visao-agenda").forEach(btn => btn.addEventListener("click", () => {
            visaoAtual = btn.dataset.visao;
            renderizarTudo();
        }));
        document.querySelectorAll(".btn-selecionar-profissional").forEach(btn => btn.addEventListener("click", () => {
            profissionalSelecionadoId = parseInt(btn.dataset.id);
            renderizarTudo();
        }));
        document.querySelectorAll(".btn-status-consulta").forEach(btn => btn.addEventListener("click", async (e) => {
            e.stopPropagation();
            await Api.put(`/agenda/${btn.dataset.id}/status`, { status: btn.dataset.status });
            Toast.sucesso("Consulta atualizada!");
            recarregarConsultas();
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

        const btnSemAnt = document.getElementById("btn-semana-anterior");
        if (btnSemAnt) btnSemAnt.addEventListener("click", () => { dataReferencia.setDate(dataReferencia.getDate() - 7); renderizarTudo(); });
        const btnSemProx = document.getElementById("btn-semana-proxima");
        if (btnSemProx) btnSemProx.addEventListener("click", () => { dataReferencia.setDate(dataReferencia.getDate() + 7); renderizarTudo(); });
        const btnMesAnt = document.getElementById("btn-mes-anterior");
        if (btnMesAnt) btnMesAnt.addEventListener("click", () => { dataReferencia.setMonth(dataReferencia.getMonth() - 1); renderizarTudo(); });
        const btnMesProx = document.getElementById("btn-mes-proximo");
        if (btnMesProx) btnMesProx.addEventListener("click", () => { dataReferencia.setMonth(dataReferencia.getMonth() + 1); renderizarTudo(); });

        document.querySelectorAll(".btn-abrir-dia-mes").forEach(cel => cel.addEventListener("click", () => {
            const chave = cel.dataset.dia;
            const doDia = consultas.filter(c => c.data_hora.slice(0, 10) === chave).sort((a, b) => a.data_hora.localeCompare(b.data_hora));
            abrirModalConsultasDoDia(chave, doDia, podeGerenciar, recarregarConsultas);
        }));

        // Clique num horário livre da grade "Por Profissional" — abre já preenchido.
        document.querySelectorAll(".btn-slot-vazio").forEach(slot => slot.addEventListener("click", () => {
            const profSelecionado = profissionaisTodos.find(p => p.id === profissionalSelecionadoId);
            if (!profSelecionado || !podeEditarAgendaDe(profSelecionado.id)) return;
            const totalMin = parseInt(slot.dataset.slot) * 30;
            const hora = String(AGENDA_HORA_INICIO + Math.floor(totalMin / 60)).padStart(2, "0");
            const minuto = String(totalMin % 60).padStart(2, "0");
            abrirModalNovaConsulta({ profissionalId: profSelecionado.id, data: slot.dataset.dia, hora: `${hora}:${minuto}` }, recarregarConsultas);
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
                if (!idArrastando) return;
                const rect = coluna.getBoundingClientRect();
                const y = e.clientY - rect.top;
                const totalMinBruto = (y / AGENDA_ALTURA_SLOT) * 30;
                const totalMinArredondado = Math.max(0, Math.round(totalMinBruto / 15) * 15);
                const hora = String(AGENDA_HORA_INICIO + Math.floor(totalMinArredondado / 60)).padStart(2, "0");
                const minuto = String(totalMinArredondado % 60).padStart(2, "0");
                const novaDataHora = `${coluna.dataset.dia} ${hora}:${minuto}:00`;
                const idSolto = idArrastando;
                idArrastando = null;
                try {
                    await Api.put(`/agenda/${idSolto}`, { data_hora: novaDataHora });
                    Toast.sucesso(`Consulta remarcada para ${formatarData(coluna.dataset.dia)} às ${hora}:${minuto}.`);
                    recarregarConsultas();
                } catch (err) { Toast.erro(err.message); }
            });
        });
    }

    renderizarTudo();
}

function formatarHoraCurta(dataHora) {
    return (dataHora || "").slice(11, 16);
}

function renderConsultaChip(c) {
    const cor = corSegura(c.profissional_cor, "var(--cor-marca)");
    return `
    <div class="agenda-chip btn-abrir-editar-consulta" data-id="${c.id}" style="background:${cor}22; border-left:3px solid ${cor}; color:var(--cor-tinta); cursor:pointer;" title="${escapeHtml(c.paciente_nome || "")} · ${escapeHtml(c.profissional_nome || "")} — clique para editar">
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
        await Api.put(`/agenda/${btn.dataset.id}/status`, { status: btn.dataset.status });
        Toast.sucesso("Consulta atualizada!");
        modal.remove();
        atualizar();
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
    const statusCor = { agendada: "neutro", confirmada: "marca", realizada: "sucesso", cancelada: "alerta", faltou: "alerta" }[c.status] || "neutro";
    const corProf = corSegura(c.profissional_cor, "var(--cor-marca)");
    return `
    <div class="pessoa-linha" style="border-left:3px solid ${corProf}; padding-left:8px;">
      <div class="pessoa-avatar">${c.avatar_mascote || "📅"}</div>
      <div class="pessoa-info">
        <div class="pessoa-nome">${escapeHtml(c.paciente_nome || "")}${c.serie_recorrencia_id ? ` <span title="Faz parte de uma série recorrente" style="font-size:12px;">🔁</span>` : ""}</div>
        <div class="pessoa-sub"><span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${corProf}; margin-right:4px;"></span>${formatarDataHora(c.data_hora)} · ${escapeHtml(c.profissional_nome || "")}</div>
      </div>
      <span class="badge badge-${statusCor}">${c.status}</span>
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
        <h3 style="margin-bottom:18px;">Agendar consulta</h3>
        <form id="form-nova-consulta">
          <div class="campo"><label>Paciente ${ASTERISCO_OBRIGATORIO}</label>
            <select id="ag-paciente" required>${pacientes.map(p => `<option value="${p.id}">${p.avatar_mascote} ${escapeHtml(p.nome)}</option>`).join("")}</select>
          </div>
          <div class="campo"><label>Profissional ${ASTERISCO_OBRIGATORIO}</label>
            <select id="ag-profissional" required>${profissionais.map(p => `<option value="${p.id}" ${preSelecao.profissionalId === p.id ? "selected" : ""}>${escapeHtml(p.nome)} (${escapeHtml(p.especialidade || "")})</option>`).join("")}</select>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Data ${ASTERISCO_OBRIGATORIO}</label><input type="date" id="ag-data" required value="${preSelecao.data || ""}" /></div>
            <div class="campo" style="flex:1;"><label>Hora ${ASTERISCO_OBRIGATORIO}</label><input type="time" id="ag-hora" required value="${preSelecao.hora || "14:00"}" /></div>
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
            const ehRecorrente = document.getElementById("ag-recorrente").checked;
            const corpoBase = {
                paciente_id: parseInt(document.getElementById("ag-paciente").value),
                profissional_id: parseInt(document.getElementById("ag-profissional").value),
                data_hora: dataHora,
                observacoes: document.getElementById("ag-obs").value.trim(),
            };
            if (ehRecorrente) {
                const r = await Api.post("/agenda/recorrente", {
                    ...corpoBase,
                    frequencia: document.getElementById("ag-frequencia").value,
                    repeticoes: parseInt(document.getElementById("ag-repeticoes").value) || 2,
                });
                Toast.sucesso(`${r.total_criadas} consultas agendadas! 🔁`);
            } else {
                await Api.post("/agenda", corpoBase);
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
    const horaAtual = (consulta.data_hora || "").slice(11, 16);
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:6px;">Editar consulta</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:10px;">${escapeHtml(consulta.paciente_nome || "")}${consulta.serie_recorrencia_id ? " · 🔁 parte de uma série (só esta ocorrência é alterada)" : ""}</p>
        ${consulta.status === "agendada" || consulta.status === "confirmada" ? `
        <div class="linha gap-2" style="margin-bottom:14px;">
          <button type="button" class="botao botao-sm ${consulta.status === "confirmada" ? "botao-primario" : "botao-secundario"}" id="btn-confirmar-consulta">📌 ${consulta.status === "confirmada" ? "Confirmada" : "Confirmar agendamento"}</button>
        </div>` : `<span class="badge badge-neutro" style="margin-bottom:14px;">Status: ${consulta.status}</span>`}
        <form id="form-editar-consulta">
          <div class="campo"><label>Profissional ${ASTERISCO_OBRIGATORIO}</label>
            <select id="ec-profissional" required>${profissionais.map(p => `<option value="${p.id}" ${p.id === consulta.profissional_id ? "selected" : ""}>${escapeHtml(p.nome)} (${escapeHtml(p.especialidade || "")})</option>`).join("")}</select>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Data ${ASTERISCO_OBRIGATORIO}</label><input type="date" id="ec-data" required value="${dataAtual}" /></div>
            <div class="campo" style="flex:1;"><label>Hora ${ASTERISCO_OBRIGATORIO}</label><input type="time" id="ec-hora" required value="${horaAtual}" /></div>
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

    const btnConfirmar = document.getElementById("btn-confirmar-consulta");
    if (btnConfirmar) btnConfirmar.addEventListener("click", async () => {
        try {
            await Api.put(`/agenda/${consulta.id}/status`, { status: "confirmada" });
            Toast.sucesso("Agendamento confirmado!");
            modal.remove();
            atualizar();
        } catch (err) { Toast.erro(err.message); }
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
            await Api.put(`/agenda/${consulta.id}`, {
                profissional_id: parseInt(document.getElementById("ec-profissional").value),
                data_hora: `${data} ${hora}:00`,
                observacoes: document.getElementById("ec-obs").value.trim(),
            });
            Toast.sucesso("Consulta atualizada!");
            modal.remove();
            atualizar();
        } catch (err) { Toast.erro(err.message); }
    });
}
