// ============================================================================
// views/jornada.js — Home do Paciente (Documento 13, UX Pattern 06)
// A tela mais importante do ecossistema, vista pelo Profissional/Gestor.
// ============================================================================

async function viewJornadaPaciente(app, params) {
    const pacienteId = params.id;
    const u = Sessao.usuario;
    const base = u.papel === "gestor" ? "gestor" : "profissional";
    const dados = await Api.get(`/jornada/paciente/${pacienteId}`);
    const paciente = dados.paciente;
    // Vem do backend (paciente_editavel): Gestor sempre pode; Profissional só
    // se estiver de fato na equipe que atende esse paciente. Quem não pode
    // editar ainda vê tudo (visualização ampla), só não edita nada.
    const podeEditar = !!paciente.pode_editar;

    const modulosHabilitados = (u.organizacao && u.organizacao.modulos_habilitados) || [];
    if (dados.jornada && modulosHabilitados.includes("analytics_avancado")) {
        try { dados.ict = await Api.get(`/indicadores/paciente/${pacienteId}/ict`); } catch (e) { dados.ict = null; }
    }

    const conteudoPrincipal = dados.jornada
        ? renderJornadaConteudoPrincipal(dados, podeEditar)
        : `<div class="cartao estado-vazio">
             <div class="emoji">${paciente.avatar_mascote}</div>
             <h3>Ainda não tem uma jornada terapêutica</h3>
             ${podeEditar ? `
             <p style="margin-bottom:18px;">Inicie a jornada para começar a planejar objetivos e missões.</p>
             <button class="botao botao-primario" id="btn-iniciar-jornada">Iniciar jornada terapêutica</button>` : `
             <p>Você pode visualizar este paciente, mas só quem faz parte da equipe que o atende pode iniciar a jornada.</p>`}
           </div>`;

    const conteudo = `
    <div class="cartao" id="card-identidade-paciente" style="margin-bottom:20px;">
      ${renderCabecalhoIdentidade(paciente, podeEditar)}
      ${!podeEditar ? `<p class="texto-xs texto-suave" style="margin-top:10px;">👁️ Você está vendo este paciente em modo somente-visualização — só a equipe que atende pode editar.</p>` : ""}
    </div>
    <div class="grade grade-principal">
      <div class="coluna gap-5">${conteudoPrincipal}</div>
      <div class="coluna gap-5">${renderColunaLateral(dados, base, podeEditar)}</div>
    </div>`;

    app.innerHTML = renderShellSidebar(`#/${base}/pacientes`, "Ficha do Paciente", conteudo,
        `<a href="#/${base}/pacientes" class="botao botao-secundario botao-sm">← Voltar</a>`);
    anexarEventosShell();

    const btnIniciar = document.getElementById("btn-iniciar-jornada");
    if (btnIniciar) btnIniciar.addEventListener("click", async () => {
        const objetivo = prompt("Qual o objetivo principal desta jornada?");
        if (!objetivo) return;
        try {
            await Api.post(`/jornada/paciente/${pacienteId}/criar-jornada`, { objetivo_principal: objetivo });
            Toast.sucesso("Jornada iniciada!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });

    const btnEditarIdentidade = document.getElementById("btn-editar-identidade");
    if (btnEditarIdentidade) btnEditarIdentidade.addEventListener("click", () => abrirModalEditarIdentidade(paciente));

    const btnVincularResp = document.getElementById("btn-vincular-resp");
    if (btnVincularResp) btnVincularResp.addEventListener("click", async () => {
        const nome = prompt("Nome do responsável:");
        if (!nome) return;
        const email = prompt("E-mail do responsável:");
        if (!email) return;
        const telefone = prompt("Telefone do responsável (opcional):") || "";
        try {
            const r = await Api.post(`/pessoas/pacientes/${pacienteId}/vincular-responsavel`, { nome, email, telefone });
            if (r.link_convite) mostrarModalConvite(r.link_convite, nome);
            else { Toast.sucesso("Responsável vinculado!"); despachar(); }
        } catch (err) { Toast.erro(err.message); }
    });

    const btnVincularProf = document.getElementById("btn-vincular-prof");
    if (btnVincularProf) btnVincularProf.addEventListener("click", () => abrirModalVincularProfissional(pacienteId, paciente.profissionais || []));

    const btnRelatorio = document.getElementById("btn-baixar-relatorio");
    if (btnRelatorio) btnRelatorio.addEventListener("click", async () => {
        btnRelatorio.disabled = true;
        const textoOriginal = btnRelatorio.textContent;
        btnRelatorio.textContent = "Gerando PDF...";
        try {
            await Api.baixarArquivo(
                `/jornada/paciente/${btnRelatorio.dataset.pacienteId}/relatorio-pdf`,
                `relatorio-${btnRelatorio.dataset.pacienteNome.toLowerCase().replace(/\s+/g, "-")}.pdf`
            );
        } catch (err) {
            Toast.erro(err.message || "Não foi possível gerar o relatório.");
        } finally {
            btnRelatorio.disabled = false;
            btnRelatorio.textContent = textoOriginal;
        }
    });

    if (dados.jornada) anexarEventosJornada(dados, pacienteId, base, podeEditar);
    carregarFichaClinica(pacienteId, u.papel, podeEditar);
}

function renderCabecalhoIdentidade(paciente, podeEditar) {
    const idade = calcularIdade(paciente.data_nascimento);
    const rotulosGenero = { menino: "Menino", menina: "Menina", outro: "Outro" };
    return `
    <div class="linha gap-4" style="align-items:center; flex-wrap:wrap;">
      <div style="width:64px; height:64px; border-radius:50%; overflow:hidden; display:flex; align-items:center; justify-content:center; background:var(--cor-marca-clara); font-size:38px; flex-shrink:0;">
        ${renderFotoPaciente(paciente, 64)}
      </div>
      <div style="flex:1; min-width:200px;">
        <h2 style="margin-bottom:4px;">${escapeHtml(paciente.nome)}</h2>
        <p class="texto-sm texto-suave">
          ${idade ? escapeHtml(idade) : "Data de nascimento não informada"}
          ${paciente.genero && rotulosGenero[paciente.genero] ? " · " + rotulosGenero[paciente.genero] : ""}
        </p>
      </div>
      ${podeEditar ? `<button type="button" class="botao-icone" id="btn-editar-identidade" title="Editar dados do paciente" style="flex-shrink:0;">✏️</button>` : ""}
    </div>`;
}

function abrirModalEditarIdentidade(paciente) {
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:18px;">Editar dados do paciente</h3>
        <form id="form-editar-identidade">
          <div class="campo"><label>Nome completo ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="ei-nome" value="${escapeHtml(paciente.nome)}" required /></div>
          <div class="campo"><label>Data de nascimento</label><input type="date" id="ei-nascimento" value="${paciente.data_nascimento || ""}" /></div>
          <div class="campo">
            <label>Gênero</label>
            <select id="ei-genero">
              <option value="">Não informado</option>
              <option value="menino" ${paciente.genero === "menino" ? "selected" : ""}>Menino</option>
              <option value="menina" ${paciente.genero === "menina" ? "selected" : ""}>Menina</option>
              <option value="outro" ${paciente.genero === "outro" ? "selected" : ""}>Outro</option>
            </select>
          </div>
          <div class="linha gap-3" style="margin-top:16px;">
            <button type="submit" class="botao botao-primario">Salvar</button>
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    document.getElementById("form-editar-identidade").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            await Api.put(`/pessoas/pacientes/${paciente.id}`, {
                nome: document.getElementById("ei-nome").value.trim(),
                data_nascimento: document.getElementById("ei-nascimento").value,
                genero: document.getElementById("ei-genero").value,
            });
            Toast.sucesso("Dados atualizados!");
            modal.remove();
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });
}

function abrirModalVincularProfissional(pacienteId, profissionaisAtuais) {
    Api.get("/pessoas/profissionais").then(todos => {
        const idsAtuais = profissionaisAtuais.map(p => p.id);
        const disponiveis = todos.filter(p => !idsAtuais.includes(p.id));
        const modal = el(`
        <div class="modal-fundo">
          <div class="modal-caixa">
            <h3 style="margin-bottom:18px;">Vincular profissional à equipe</h3>
            ${disponiveis.length ? `
            <form id="form-vincular-prof">
              <div class="campo">
                <label>Profissional ${ASTERISCO_OBRIGATORIO}</label>
                <select id="vp-profissional" required>
                  ${disponiveis.map(p => `<option value="${p.id}">${escapeHtml(p.nome)} — ${escapeHtml(p.especialidade || "")}</option>`).join("")}
                </select>
              </div>
              <div class="linha gap-3" style="margin-top:16px;">
                <button type="submit" class="botao botao-primario">Vincular</button>
                <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
              </div>
            </form>` : `
            <p class="texto-sm texto-suave">Todos os profissionais da clínica já atendem este paciente.</p>
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal" style="width:100%; margin-top:16px;">Fechar</button>`}
          </div>
        </div>`);
        document.body.appendChild(modal);
        modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
        document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
        const form = document.getElementById("form-vincular-prof");
        if (form) form.addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                await Api.post(`/pessoas/pacientes/${pacienteId}/vincular-profissional`, { profissional_id: parseInt(document.getElementById("vp-profissional").value) });
                Toast.sucesso("Profissional vinculado à equipe!");
                modal.remove();
                despachar();
            } catch (err) { Toast.erro(err.message); }
        });
    });
}

function renderJornadaConteudoPrincipal(dados, podeEditar) {
    const { jornada, plano_ativo, missoes, marcos, diarios_recentes, feedbacks, progresso_pct } = dados;

    return `
        <div class="cartao">
          <div class="linha-entre" style="margin-bottom:6px;">
            <span class="badge badge-marca">🎯 Objetivo Principal</span>
          </div>
          <p style="font-size:15.5px; line-height:1.5;">${escapeHtml(jornada.objetivo_principal)}</p>
        </div>

        ${plano_ativo ? `
        <div class="cartao">
          <div class="linha-entre" style="margin-bottom:16px;">
            <h3>📋 ${escapeHtml(plano_ativo.titulo)}</h3>
            <span class="badge badge-sucesso">${progresso_pct}% concluído</span>
          </div>
          <div class="progresso-barra" style="margin-bottom:18px;"><div class="progresso-preenchimento" style="width:${progresso_pct}%"></div></div>

          <div class="linha-entre" style="margin-bottom:12px;">
            <p class="texto-sm" style="font-weight:700;">Missões do plano (${dados.missoes_concluidas}/${dados.missoes_total})</p>
            ${podeEditar ? `<button class="botao botao-sm botao-texto" id="btn-nova-missao">+ Nova missão</button>` : ""}
          </div>
          ${missoes.length ? missoes.map(m => renderMissaoCard(m, podeEditar)).join("") : `<p class="texto-sm texto-suave">Nenhuma missão criada ainda.</p>`}
        </div>` : (podeEditar ? `
        <div class="cartao estado-vazio">
          <p>Nenhum plano terapêutico ativo.</p>
          <button class="botao botao-primario botao-sm" id="btn-novo-plano" style="margin-top:10px;">+ Criar plano terapêutico</button>
        </div>` : `
        <div class="cartao estado-vazio">
          <p>Nenhum plano terapêutico ativo ainda.</p>
        </div>`)}

        <div class="cartao">
          <div class="linha-entre" style="margin-bottom:4px; flex-wrap:wrap; gap:8px;">
            <h3>📔 Diário Terapêutico</h3>
            <div class="linha gap-2" style="flex-wrap:wrap;">
              ${diarios_recentes.length ? `<button class="botao botao-sm botao-secundario" id="btn-ver-historico-diario">Ver histórico completo</button>` : ""}
              ${podeEditar ? `<button class="botao botao-sm botao-primario" id="btn-novo-diario">+ Novo Diário</button>` : ""}
            </div>
          </div>
          <p class="texto-xs texto-suave" style="margin-bottom:16px;">Evolução clínica em linguagem acessível, compartilhada com a família.</p>

          ${diarios_recentes.length || marcos.length ? `
          <div class="timeline">
            ${diarios_recentes.map(d => renderDiarioTimelineItem(d)).join("")}
            ${marcos.map(m => `
              <div class="timeline-item marco">
                <div class="timeline-data">${formatarData(m.criado_em)} · 🏆 Marco</div>
                <div class="timeline-texto"><strong>${escapeHtml(m.titulo)}</strong>${m.descricao ? " — " + escapeHtml(m.descricao) : ""}</div>
              </div>`).join("")}
          </div>` : `<p class="texto-sm texto-suave">Nenhum registro no diário ainda.</p>`}
        </div>

        ${feedbacks.length ? `
        <div class="cartao">
          <h3 style="margin-bottom:14px;">💬 Feedback da família</h3>
          <div class="coluna gap-3">
            ${feedbacks.map(f => `
              <div class="cartao-flat">
                <p class="texto-sm">${f.humor || "🙂"} "${escapeHtml(f.texto)}"</p>
                <p class="texto-xs texto-suave" style="margin-top:4px;">${escapeHtml(f.autor_nome)} sobre "${escapeHtml(f.missao_titulo)}" · ${tempoRelativo(f.criado_em)}</p>
              </div>`).join("")}
          </div>
        </div>` : ""}`;
}

function renderColunaLateral(dados, base, podeEditar) {
    const { jornada, gamificacao, paciente, ict } = dados;
    return `
        ${jornada ? `
        <div class="cartao" style="text-align:center;">
          ${svgMascote({ emoji: paciente.avatar_mascote, estagio: gamificacao?.mascote_estagio || 1, tamanho: 100, flutuar: true })}
          <h3 style="margin-top:12px;">${nivelParaTexto(gamificacao?.nivel || 1)}</h3>
          <p class="texto-sm texto-suave">Nível ${gamificacao?.nivel || 1}</p>
          <div class="linha" style="justify-content:center; gap:20px; margin-top:16px;">
            <div><div style="font-weight:700; font-size:18px;">${gamificacao?.xp_total || 0}</div><div class="texto-xs texto-suave">${nomeMoeda()}</div></div>
            <div><div style="font-weight:700; font-size:18px;">⭐ ${gamificacao?.estrelas || 0}</div><div class="texto-xs texto-suave">estrelas</div></div>
            <div><div style="font-weight:700; font-size:18px;">🔥 ${gamificacao?.sequencia_dias || 0}</div><div class="texto-xs texto-suave">dias seguidos</div></div>
          </div>
        </div>

        ${ict && ict.ict_pct !== null ? `
        <div class="cartao" style="text-align:center;">
          <h4 style="margin-bottom:14px;">🔗 Continuidade Terapêutica</h4>
          ${circuloProgresso({ pct: ict.ict_pct, tamanho: 100, espessura: 10, cor: "var(--cor-marca)" })}
          <div class="coluna gap-1" style="text-align:left; margin-top:14px;">
            <p class="texto-xs texto-suave">${ict.componentes.adesao_missoes_pct}% de adesão às missões (7 dias)</p>
            <p class="texto-xs texto-suave">${ict.componentes.familia_engajada ? "✅" : "⬜"} Família engajada esta semana</p>
            <p class="texto-xs texto-suave">${ict.componentes.profissional_acompanhou ? "✅" : "⬜"} Profissional registrou diário</p>
          </div>
        </div>` : ""}` : ""}

        <div class="cartao">
          <h4 style="margin-bottom:10px;">👨‍👩‍👧 Responsáveis</h4>
          <div class="lista-pessoas">
            ${(paciente.responsaveis || []).map(r => `
              <div class="pessoa-linha">
                <div class="pessoa-avatar">👤</div>
                <div class="pessoa-info"><div class="pessoa-nome">${escapeHtml(r.nome)}</div><div class="pessoa-sub">${escapeHtml(r.parentesco || "Responsável")}${r.telefone ? " · " + escapeHtml(r.telefone) : ""}${r.email ? " · " + escapeHtml(r.email) : ""}</div></div>
              </div>`).join("") || `<p class="texto-sm texto-suave">Nenhum responsável vinculado.</p>`}
          </div>
          ${podeEditar ? `<button class="botao botao-sm botao-texto" id="btn-vincular-resp" style="margin-top:6px;">+ Vincular responsável</button>` : ""}
        </div>

        <div class="cartao">
          <h4 style="margin-bottom:10px;">🩺 Equipe</h4>
          <div class="lista-pessoas">
            ${(paciente.profissionais || []).map(p => `
              <div class="pessoa-linha">
                <div class="pessoa-avatar">${ICONES_ESPECIALIDADE[p.especialidade] || "🩺"}</div>
                <div class="pessoa-info"><div class="pessoa-nome">${escapeHtml(p.nome)}</div><div class="pessoa-sub">${escapeHtml(p.especialidade || "")}${p.principal ? " · principal" : ""}</div></div>
              </div>`).join("") || `<p class="texto-sm texto-suave">Nenhum profissional vinculado ainda.</p>`}
          </div>
          ${Sessao.usuario.papel === "gestor" ? `<button class="botao botao-sm botao-texto" id="btn-vincular-prof" style="margin-top:6px;">+ Vincular profissional</button>` : ""}
        </div>

        <div class="cartao" id="card-ficha-clinica">
          <h4 style="margin-bottom:6px;">📋 Ficha Clínica</h4>
          <p class="texto-xs texto-suave">Carregando...</p>
        </div>

        <button type="button" class="botao botao-secundario" id="btn-baixar-relatorio" data-paciente-id="${paciente.id}" data-paciente-nome="${escapeHtml(paciente.nome)}" style="width:100%;">📄 Baixar relatório em PDF</button>
        <a href="#/${base === "gestor" ? "gestor" : "profissional"}/mensagens?paciente=${paciente.id}" class="botao botao-secundario" style="width:100%;">💬 Ver conversa</a>`;
}

async function carregarFichaClinica(pacienteId, papel, podeEditar) {
    const card = document.getElementById("card-ficha-clinica");
    if (!card) return; // paciente ainda sem jornada — o card nem existe nessa tela
    try {
        const ficha = await Api.get(`/pessoas/pacientes/${pacienteId}/ficha-clinica`);
        if (!ficha.preenchida) {
            card.innerHTML = `
              <h4 style="margin-bottom:6px;">📋 Ficha Clínica</h4>
              <p class="texto-xs texto-suave" style="margin-bottom:10px;">Ainda não preenchida — é totalmente opcional, não bloqueia nada na jornada.</p>
              ${podeEditar ? `<button type="button" class="botao botao-secundario botao-sm" id="btn-preencher-ficha">+ Preencher (opcional)</button>` : ""}
            `;
        } else {
            card.innerHTML = `
              <div class="linha-entre" style="margin-bottom:8px;">
                <h4 style="margin-bottom:0;">📋 Ficha Clínica</h4>
                ${podeEditar ? `<button type="button" class="botao-icone" id="btn-editar-ficha" title="Editar" style="width:30px; height:30px; font-size:13px;">✏️</button>` : ""}
              </div>
              <div class="coluna gap-2">
                ${ficha.diagnostico ? `<div><p class="texto-xs texto-suave" style="font-weight:700;">DIAGNÓSTICO</p><p class="texto-sm">${escapeHtml(ficha.diagnostico)}</p></div>` : ""}
                ${ficha.alergias ? `<div><p class="texto-xs texto-suave" style="font-weight:700;">⚠️ ALERGIAS</p><p class="texto-sm">${escapeHtml(ficha.alergias)}</p></div>` : ""}
                ${ficha.medicamentos_em_uso ? `<div><p class="texto-xs texto-suave" style="font-weight:700;">MEDICAÇÕES EM USO</p><p class="texto-sm">${escapeHtml(ficha.medicamentos_em_uso)}</p></div>` : ""}
                ${ficha.profissionais_externos ? `<div><p class="texto-xs texto-suave" style="font-weight:700;">PROFISSIONAIS EXTERNOS</p><p class="texto-sm">${escapeHtml(ficha.profissionais_externos)}</p></div>` : ""}
                ${ficha.observacoes ? `<div><p class="texto-xs texto-suave" style="font-weight:700;">OBSERVAÇÕES</p><p class="texto-sm">${escapeHtml(ficha.observacoes)}</p></div>` : ""}
              </div>
              <p class="texto-xs texto-suave" style="margin-top:10px;">Atualizada por ${escapeHtml(ficha.atualizado_por_nome || "—")} · ${formatarData(ficha.atualizado_em)}</p>
            `;
        }
        const btnAbrir = document.getElementById("btn-preencher-ficha") || document.getElementById("btn-editar-ficha");
        if (btnAbrir) btnAbrir.addEventListener("click", () => abrirModalFichaClinica(pacienteId, ficha.preenchida ? ficha : {}));
    } catch (err) {
        card.innerHTML = `<h4 style="margin-bottom:6px;">📋 Ficha Clínica</h4><p class="texto-xs texto-suave">Não foi possível carregar agora.</p>`;
    }
}

function abrirModalFichaClinica(pacienteId, fichaAtual) {
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:4px;">📋 Ficha Clínica</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:16px;">Totalmente opcional — preencha só o que fizer sentido, o resto pode ficar em branco.</p>
        <form id="form-ficha-clinica">
          <div class="campo"><label>Diagnóstico</label><textarea id="fc-diagnostico" rows="2" placeholder="Ex: TEA nível 1, TDAH...">${escapeHtml(fichaAtual.diagnostico || "")}</textarea></div>
          <div class="campo"><label>⚠️ Alergias</label><textarea id="fc-alergias" rows="2" placeholder="Ex: Alergia a dipirona, amendoim...">${escapeHtml(fichaAtual.alergias || "")}</textarea></div>
          <div class="campo"><label>Medicações em uso</label><textarea id="fc-medicamentos" rows="2" placeholder="Ex: Ritalina 10mg, 1x ao dia">${escapeHtml(fichaAtual.medicamentos_em_uso || "")}</textarea></div>
          <div class="campo"><label>Profissionais externos</label><textarea id="fc-externos" rows="2" placeholder="Ex: Dra. Ana Paula (neuropediatra)">${escapeHtml(fichaAtual.profissionais_externos || "")}</textarea></div>
          <div class="campo"><label>Observações gerais</label><textarea id="fc-observacoes" rows="2">${escapeHtml(fichaAtual.observacoes || "")}</textarea></div>
          <div class="linha gap-3" style="margin-top:16px;">
            <button type="submit" class="botao botao-primario">Salvar ficha</button>
            <button type="button" class="botao botao-texto" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    document.getElementById("form-ficha-clinica").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            await Api.put(`/pessoas/pacientes/${pacienteId}/ficha-clinica`, {
                diagnostico: document.getElementById("fc-diagnostico").value.trim(),
                alergias: document.getElementById("fc-alergias").value.trim(),
                medicamentos_em_uso: document.getElementById("fc-medicamentos").value.trim(),
                profissionais_externos: document.getElementById("fc-externos").value.trim(),
                observacoes: document.getElementById("fc-observacoes").value.trim(),
            });
            Toast.sucesso("Ficha clínica salva!");
            modal.remove();
            carregarFichaClinica(pacienteId, Sessao.usuario.papel);
        } catch (err) { Toast.erro(err.message); }
    });
}



function renderMissaoCard(m, podeGerenciar) {
    const atrasada = ["pendente", "iniciada"].includes(m.status) && m.prazo && m.prazo < new Date().toISOString().slice(0, 10);
    const podeEditarExcluir = podeGerenciar && m.status !== "concluida";
    const rotuloStatus = { rascunho: "Rascunho", iniciada: "Em andamento" }[m.status];
    return `
    <div class="missao-card ${m.status === "concluida" ? "concluida" : ""} ${atrasada ? "atrasada" : ""} ${m.status === "rascunho" ? "rascunho" : ""}">
      <div class="missao-checkbox">${m.status === "concluida" ? "✓" : (m.status === "iniciada" ? "▶" : "")}</div>
      <div style="flex:1;">
        <div class="linha gap-2" style="flex-wrap:wrap;">
          <div class="missao-titulo">${escapeHtml(m.titulo)}</div>
          ${rotuloStatus ? `<span class="badge ${m.status === "rascunho" ? "badge-neutro" : "badge-marca"}">${rotuloStatus}</span>` : ""}
          ${m.tipo === "semanal" ? `<span class="badge badge-neutro" title="Precisa de 1 check por dia, 7 dias">📅 Semanal${m.status !== "concluida" ? ` · ${m.dias_concluidos_total || 0}/7 dias` : ""}</span>` : ""}
        </div>
        <div class="missao-meta">
          Prazo: ${formatarData(m.prazo)} · +${m.recompensa_xp} ${nomeMoeda()}
          ${atrasada ? ` · <span style="color:var(--cor-alerta); font-weight:700;">Atrasada</span>` : ""}
          ${m.total_atividades ? ` · ${m.atividades_concluidas}/${m.total_atividades} atividades` : ""}
        </div>
      </div>
      <div class="linha gap-1" style="flex-shrink:0;">
        ${m.status === "rascunho" && podeGerenciar ? `<button type="button" class="botao botao-sm botao-primario btn-publicar-missao" data-id="${m.id}">Publicar</button>` : ""}
        ${podeEditarExcluir ? `
          <button type="button" class="botao-icone btn-editar-missao" data-id="${m.id}" title="Editar missão" style="width:34px; height:34px; font-size:14px;">✏️</button>
          <button type="button" class="botao-icone btn-excluir-missao" data-id="${m.id}" data-titulo="${escapeHtml(m.titulo)}" title="Excluir missão" style="width:34px; height:34px; font-size:14px;">🗑️</button>
        ` : ""}
      </div>
    </div>`;
}

function renderDiarioTimelineItem(d) {
    return `
    <div class="timeline-item">
      <div class="timeline-data">${formatarData(d.data_atendimento)} · ${escapeHtml(d.profissional_nome)}</div>
      <div class="timeline-texto">${escapeHtml(d.evolucao_clinica)}</div>
      ${d.objetivo_semana ? `<p class="texto-xs texto-suave" style="margin-top:4px;">🎯 Objetivo da semana: ${escapeHtml(d.objetivo_semana)}</p>` : ""}
      <button class="botao-texto botao-sm btn-ver-diario" data-id="${d.id}" style="padding:4px 0; margin-top:2px;">Ver registro completo →</button>
    </div>`;
}



function anexarEventosJornada(dados, pacienteId, base) {
    const btnNovoPlano = document.getElementById("btn-novo-plano");
    if (btnNovoPlano) btnNovoPlano.addEventListener("click", () => abrirModalNovoPlano(dados.jornada.id, pacienteId));

    const btnNovaMissao = document.getElementById("btn-nova-missao");
    if (btnNovaMissao) btnNovaMissao.addEventListener("click", () => abrirModalNovaMissao(dados.plano_ativo.id, dados.jornada.objetivo_principal));

    const btnNovoDiario = document.getElementById("btn-novo-diario");
    if (btnNovoDiario) btnNovoDiario.addEventListener("click", () => abrirModalNovoDiario(dados.jornada.id, dados.paciente));

    const btnHistoricoDiario = document.getElementById("btn-ver-historico-diario");
    if (btnHistoricoDiario) btnHistoricoDiario.addEventListener("click", () => abrirModalHistoricoDiario(dados.jornada.id));

    document.querySelectorAll(".btn-ver-diario").forEach(btn => btn.addEventListener("click", () => abrirModalDetalheDiario(btn.dataset.id)));

    document.querySelectorAll(".btn-publicar-missao").forEach(btn => btn.addEventListener("click", async () => {
        try {
            await Api.put(`/jornada/missao/${btn.dataset.id}/publicar`);
            Toast.sucesso("Missão publicada! A família já pode vê-la. 🎉");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    }));

    document.querySelectorAll(".btn-editar-missao").forEach(btn => btn.addEventListener("click", async () => {
        try {
            const missao = await Api.get(`/jornada/missao/${btn.dataset.id}`);
            abrirModalNovaMissao(dados.plano_ativo.id, dados.jornada.objetivo_principal, missao);
        } catch (err) { Toast.erro(err.message); }
    }));

    document.querySelectorAll(".btn-excluir-missao").forEach(btn => btn.addEventListener("click", async () => {
        if (!confirm(`Excluir a missão "${btn.dataset.titulo}"? Essa ação não pode ser desfeita.`)) return;
        try {
            await Api.del(`/jornada/missao/${btn.dataset.id}`);
            Toast.sucesso("Missão excluída.");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    }));
}

function abrirModalNovoPlano(jornadaId, pacienteId) {
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:18px;">Novo plano terapêutico</h3>
        <form id="form-novo-plano">
          <div class="campo"><label>Título do plano ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="pl-titulo" placeholder="Ex: Plano Agosto/2026" required /></div>
          <div class="campo"><label>Objetivos (um por linha) ${ASTERISCO_OBRIGATORIO}</label><textarea id="pl-objetivos" rows="4" required placeholder="Ex: Ampliar vocabulário funcional"></textarea></div>
          <div class="linha gap-3" style="margin-top:20px;">
            <button type="submit" class="botao botao-primario">Criar plano</button>
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    document.getElementById("form-novo-plano").addEventListener("submit", async (e) => {
        e.preventDefault();
        const objetivos = document.getElementById("pl-objetivos").value.split("\n").map(s => s.trim()).filter(Boolean);
        try {
            await Api.post(`/jornada/jornada/${jornadaId}/criar-plano`, {
                titulo: document.getElementById("pl-titulo").value.trim(), objetivos,
            });
            Toast.sucesso("Plano terapêutico criado!");
            modal.remove();
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });
}

async function abrirModalNovaMissao(planoId, objetivoTexto, missaoExistente) {
    const editando = !!missaoExistente;
    const m = missaoExistente || {};
    const idsVinculados = (m.atividades || []).map(a => a.exercicio_id);
    const [exercicios, categorias] = await Promise.all([
        Api.get("/biblioteca/exercicios"),
        Api.get("/biblioteca/categorias"),
    ]);
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa modal-grande">
        <div class="linha-entre" style="margin-bottom:18px;">
          <h3>${editando ? "Editar missão" : "Nova missão"}</h3>
          ${!editando ? `<button type="button" class="botao botao-acento botao-sm" id="btn-sugerir-ia">✨ Sugerir com IA</button>` : ""}
        </div>
        <p class="texto-xs texto-suave" id="nota-ia" style="margin:-10px 0 14px; display:none;">
          Sugestão gerada por uma heurística simples de palavras-chave (não é um modelo de IA real ainda) — revise antes de salvar.
        </p>
        <form id="form-nova-missao">
          <div class="campo"><label>Título da missão ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="ms-titulo" required placeholder="Ex: Praticar sopro com canudinho" value="${escapeHtml(m.titulo || "")}" /></div>
          <div class="campo">
            <label>Tipo de missão</label>
            <div class="linha gap-3">
              <label class="linha gap-2" style="align-items:center; cursor:pointer;">
                <input type="radio" name="ms-tipo" value="diaria" ${(m.tipo || "diaria") === "diaria" ? "checked" : ""} ${editando ? "disabled" : ""} />
                <span class="texto-sm">☀️ Diária — conclui de uma vez</span>
              </label>
              <label class="linha gap-2" style="align-items:center; cursor:pointer;">
                <input type="radio" name="ms-tipo" value="semanal" ${m.tipo === "semanal" ? "checked" : ""} ${editando ? "disabled" : ""} />
                <span class="texto-sm">📅 Semanal — 1 check por dia, 7 dias</span>
              </label>
            </div>
            ${editando ? `<p class="texto-xs texto-suave" style="margin-top:4px;">O tipo não pode ser trocado depois de criada.</p>` : ""}
          </div>
          <div class="campo"><label>Descrição para a família</label><textarea id="ms-descricao" rows="2">${escapeHtml(m.descricao || "")}</textarea></div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Prazo</label><input type="date" id="ms-prazo" value="${m.prazo || ""}" /></div>
            <div class="campo" style="flex:1;"><label>Recompensa</label><input type="number" id="ms-xp" value="${m.recompensa_xp || 15}" min="5" max="100" /></div>
          </div>
          <div class="campo">
            <div class="linha-entre" style="margin-bottom:4px;">
              <label style="margin-bottom:0;">Vincular exercícios da biblioteca (opcional)</label>
              <button type="button" class="botao-texto botao-sm" id="btn-criar-exercicio-inline" style="padding:2px 0;">+ Criar novo exercício</button>
            </div>
            <div id="lista-exercicios-modal" style="max-height:180px; overflow-y:auto; border:1.5px solid var(--cor-borda); border-radius:10px; padding:8px;">
              ${exercicios.map(ex => `
                <label class="linha gap-2" style="padding:6px 4px; font-size:13.5px;">
                  <input type="checkbox" value="${ex.id}" class="chk-exercicio" ${idsVinculados.includes(ex.id) ? "checked" : ""} /> ${ICONES_TIPO_EXERCICIO[ex.tipo] || "📝"} ${escapeHtml(ex.titulo)}
                  <span class="badge badge-neutro texto-xs" style="margin-left:auto;">${escapeHtml(ex.tags || "")}</span>
                </label>`).join("")}
            </div>
          </div>
          <div class="linha gap-3" style="margin-top:16px;">
            ${editando ? `
              <button type="submit" class="botao botao-primario">Salvar alterações</button>
            ` : `
              <button type="submit" class="botao botao-primario" data-publicar="true">Criar e publicar</button>
              <button type="button" class="botao botao-secundario" id="btn-salvar-rascunho">Salvar como rascunho</button>
            `}
            <button type="button" class="botao botao-texto" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());

    document.getElementById("btn-criar-exercicio-inline").addEventListener("click", () => {
        abrirModalExercicio(categorias, null, async () => {
            // Recarrega a lista de exercícios dentro do próprio modal de missão,
            // preservando o que já estava marcado e marcando o recém-criado.
            const marcadosAntes = Array.from(document.querySelectorAll(".chk-exercicio:checked")).map(c => parseInt(c.value));
            const novaLista = await Api.get("/biblioteca/exercicios");
            const maisRecente = novaLista.reduce((a, b) => (a.id > b.id ? a : b));
            document.getElementById("lista-exercicios-modal").innerHTML = novaLista.map(ex => `
                <label class="linha gap-2" style="padding:6px 4px; font-size:13.5px;">
                  <input type="checkbox" value="${ex.id}" class="chk-exercicio" ${(marcadosAntes.includes(ex.id) || ex.id === maisRecente.id) ? "checked" : ""} /> ${ICONES_TIPO_EXERCICIO[ex.tipo] || "📝"} ${escapeHtml(ex.titulo)}
                  <span class="badge badge-neutro texto-xs" style="margin-left:auto;">${escapeHtml(ex.tags || "")}</span>
                </label>`).join("");
        });
    });

    const btnSugerirIA = document.getElementById("btn-sugerir-ia");
    if (btnSugerirIA) btnSugerirIA.addEventListener("click", () => {
        const sugestao = sugerirMissaoIA(objetivoTexto || "", exercicios);
        if (!sugestao) { Toast.info("Não encontrei um exercício relacionado a esse objetivo na biblioteca."); return; }
        document.getElementById("ms-titulo").value = `Praticar: ${sugestao.exercicio.titulo}`;
        document.getElementById("ms-descricao").value = `Sugestão gerada a partir do objetivo da jornada: "${objetivoTexto}".`;
        document.querySelectorAll(".chk-exercicio").forEach(c => { c.checked = sugestao.idsRelacionados.includes(Number(c.value)); });
        document.getElementById("nota-ia").style.display = "block";
        Toast.sucesso("Sugestão aplicada — revise antes de salvar!");
    });

    async function salvarMissao(publicar) {
        const exercicios_ids = Array.from(document.querySelectorAll(".chk-exercicio:checked")).map(c => parseInt(c.value));
        const titulo = document.getElementById("ms-titulo").value.trim();
        if (!titulo) { Toast.erro("Título da missão é obrigatório."); return; }
        const corpo = {
            titulo,
            descricao: document.getElementById("ms-descricao").value.trim(),
            prazo: document.getElementById("ms-prazo").value || null,
            recompensa_xp: parseInt(document.getElementById("ms-xp").value) || 15,
            exercicios_ids,
        };
        if (!editando) {
            const tipoEl = document.querySelector('input[name="ms-tipo"]:checked');
            corpo.tipo = tipoEl ? tipoEl.value : "diaria";
        }
        try {
            if (editando) {
                await Api.put(`/jornada/missao/${m.id}`, corpo);
                Toast.sucesso("Missão atualizada!");
            } else {
                await Api.post(`/jornada/plano/${planoId}/criar-missao`, { ...corpo, publicar });
                Toast.sucesso(publicar ? "Missão criada e publicada! A família já pode vê-la." : "Rascunho salvo — publique quando estiver pronto.");
            }
            modal.remove();
            despachar();
        } catch (err) { Toast.erro(err.message); }
    }

    document.getElementById("form-nova-missao").addEventListener("submit", (e) => {
        e.preventDefault();
        salvarMissao(true);
    });
    const btnRascunho = document.getElementById("btn-salvar-rascunho");
    if (btnRascunho) btnRascunho.addEventListener("click", () => salvarMissao(false));
}

// ---------------------------------------------------------------- "IA" (Fase 2 — heurística por palavra-chave)
// Andaime para uma futura sugestão via LLM real: por ora, cruza palavras do
// objetivo terapêutico com as tags/especialidade dos exercícios da biblioteca.
const MAPA_PALAVRAS_CHAVE_IA = {
    linguagem: ["linguagem", "fala", "vocabul", "articul", "verbal", "comunica"],
    motricidade: ["motor", "coorden", "motricidade", "equilíbrio", "equilibrio"],
    sensorial: ["sensorial", "textura", "integração sensorial", "integracao sensorial"],
    social: ["social", "emocional", "emoç", "emoc", "interação", "interacao"],
    cognição: ["cognit", "atenção", "atencao", "lógic", "logic", "memória", "memoria"],
};

function sugerirMissaoIA(objetivoTexto, exercicios) {
    const texto = objetivoTexto.toLowerCase();
    let categoriaAlvo = null;
    for (const [categoria, palavras] of Object.entries(MAPA_PALAVRAS_CHAVE_IA)) {
        if (palavras.some(p => texto.includes(p))) { categoriaAlvo = categoria; break; }
    }
    let candidatos = categoriaAlvo
        ? exercicios.filter(ex => (ex.tags || "").toLowerCase().includes(categoriaAlvo) || (ex.categoria_nome || "").toLowerCase().includes(categoriaAlvo))
        : [];
    if (!candidatos.length) candidatos = exercicios; // fallback: não travar a demonstração
    if (!candidatos.length) return null;

    const escolhido = candidatos[0];
    const relacionados = candidatos.slice(0, 2).map(e => e.id);
    return { exercicio: escolhido, idsRelacionados: relacionados };
}
