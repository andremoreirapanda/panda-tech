// ============================================================================
// views/pacientes.js — Lista de Pessoas + Cadastro (UX Patterns 03 e 07)
// ============================================================================

async function viewListaPacientes(app) {
    const u = Sessao.usuario;
    const base = u.papel === "gestor" ? "gestor" : u.papel === "secretaria" ? "secretaria" : "profissional";
    const pacientes = await Api.get("/pessoas/pacientes");

    const podeCadastrar = u.papel === "gestor" || u.papel === "profissional" || u.papel === "secretaria";
    const acoes = podeCadastrar ? `<button class="botao botao-primario" id="btn-novo-paciente">+ Novo Paciente</button>` : "";

    function renderLinhaPaciente(p) {
        // Secretária (insight do usuário, 31/08/2026): a API já devolve só
        // nome + responsável(is) pra esse papel — a linha mostra o
        // responsável no lugar da idade/status de jornada (dado clínico,
        // que nem chega a vir no payload dela).
        const souSecretaria = u.papel === "secretaria";
        return `
        <a href="#/${base}/paciente/${p.id}" class="pessoa-linha linha-paciente-busca" data-nome="${escapeHtml(p.nome.toLowerCase())}" style="text-decoration:none; color:inherit;">
          <div class="pessoa-avatar" style="font-size:24px;">${p.avatar_mascote}</div>
          <div class="pessoa-info">
            <div class="pessoa-nome">${escapeHtml(p.nome)}</div>
            <div class="pessoa-sub">${souSecretaria ? escapeHtml(p.responsaveis_nomes || "Sem responsável vinculado") : calcularIdade(p.data_nascimento)}</div>
          </div>
          ${!souSecretaria && p.jornadas_ativas !== undefined ? `<span class="badge ${p.jornadas_ativas > 0 ? "badge-sucesso" : "badge-neutro"}">${p.jornadas_ativas > 0 ? "Jornada ativa" : "Sem jornada"}</span>` : ""}
          ${p.pode_editar !== undefined && !p.pode_editar ? `<span class="badge badge-neutro" title="Você pode ver, mas só quem atende pode editar">👁️ Visualização</span>` : ""}
          <span class="botao botao-secundario botao-sm" style="pointer-events:none;">${p.pode_editar === false ? "👁️ Ver" : "✏️ Ver/editar"}</span>
        </a>`;
    }

    const conteudo = pacientes.length ? `
      <div class="campo" style="max-width:400px; margin-bottom:18px;">
        <input type="text" id="busca-paciente" placeholder="🔎 Buscar paciente pelo nome..." />
      </div>
      <div class="lista-pessoas" id="lista-pacientes-busca">
        ${pacientes.map(renderLinhaPaciente).join("")}
      </div>
      <p class="texto-sm texto-suave" id="msg-busca-vazia" style="display:none; text-align:center; margin-top:20px;">Nenhum paciente encontrado com esse nome.</p>
    ` : `<div class="estado-vazio"><div class="emoji">🧸</div><h3>Nenhum paciente ainda</h3><p>Cadastre o primeiro paciente para iniciar uma jornada terapêutica.</p></div>`;

    app.innerHTML = renderShellSidebar(`#/${base}/pacientes`, "Pacientes", conteudo, acoes);
    anexarEventosShell();

    const btnNovo = document.getElementById("btn-novo-paciente");
    if (btnNovo) btnNovo.addEventListener("click", () => abrirModalNovoPaciente());

    const inputBusca = document.getElementById("busca-paciente");
    if (inputBusca) inputBusca.addEventListener("input", () => {
        const termo = inputBusca.value.trim().toLowerCase();
        const linhas = document.querySelectorAll(".linha-paciente-busca");
        let algumVisivel = false;
        linhas.forEach(linha => {
            const bate = linha.dataset.nome.includes(termo);
            linha.style.display = bate ? "" : "none";
            if (bate) algumVisivel = true;
        });
        document.getElementById("msg-busca-vazia").style.display = algumVisivel ? "none" : "block";
    });
}

async function abrirModalNovoPaciente() {
    const u = Sessao.usuario;
    const podeEscolherProfissional = u.papel === "gestor" || u.papel === "secretaria";
    const profissionais = podeEscolherProfissional ? await Api.get("/pessoas/profissionais?incluir_gestor=1") : [];
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:18px;">Cadastrar novo paciente</h3>
        <form id="form-novo-paciente">
          <div class="campo"><label>Nome completo ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="np-nome" required /></div>
          <div class="campo"><label>Data de nascimento ${ASTERISCO_OBRIGATORIO}</label><input type="date" id="np-nascimento" required /></div>
          <div class="campo">
            <label>Mascote</label>
            <select id="np-avatar">
              ${["🐻", "🐰", "🦁", "🐼", "🐨", "🦊", "🐯", "🐸", "🐧", "🦄"].map(e => `<option value="${e}">${e}</option>`).join("")}
            </select>
          </div>
          <hr style="border:none; border-top:1px solid var(--cor-borda); margin: 18px 0;" />
          <p class="texto-sm" style="font-weight:700; margin-bottom:10px;">Responsável</p>
          <div class="campo"><label>Nome do responsável ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="np-resp-nome" required /></div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>E-mail do responsável ${ASTERISCO_OBRIGATORIO}</label><input type="email" id="np-resp-email" required /></div>
            <div class="campo" style="flex:1;"><label>Telefone do responsável</label><input type="tel" id="np-resp-telefone" /></div>
          </div>
          ${podeEscolherProfissional ? `
          <hr style="border:none; border-top:1px solid var(--cor-borda); margin: 18px 0;" />
          <p class="texto-sm" style="font-weight:700; margin-bottom:4px;">Equipe (opcional)</p>
          <p class="texto-xs texto-suave" style="margin-bottom:10px;">Quais profissionais vão atender este paciente? Dá pra vincular mais depois.</p>
          ${profissionais.length ? `
          <div class="coluna gap-1" style="max-height:160px; overflow-y:auto; border:1.5px solid var(--cor-borda); border-radius:10px; padding:8px;">
            ${profissionais.map(p => `
              <label class="linha gap-2" style="padding:6px 4px; font-size:13.5px; cursor:pointer;">
                <input type="checkbox" class="chk-np-profissional" value="${p.id}" /> ${ICONES_ESPECIALIDADE[p.especialidade] || "🩺"} ${escapeHtml(p.nome)} — ${escapeHtml(p.especialidade || "")}
              </label>`).join("")}
          </div>` : `<p class="texto-xs texto-suave">Nenhum profissional cadastrado na clínica ainda.</p>`}
          ` : ""}
          <div class="linha gap-3" style="margin-top:20px;">
            <button type="submit" class="botao botao-primario">Cadastrar paciente</button>
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    ativarMascaraCampo(document.getElementById("np-resp-telefone"), "telefone");

    document.getElementById("form-novo-paciente").addEventListener("submit", async (e) => {
        e.preventDefault();
        const respNome = document.getElementById("np-resp-nome").value.trim();
        const respEmail = document.getElementById("np-resp-email").value.trim();
        const respTelefone = document.getElementById("np-resp-telefone").value.trim();
        if (!respNome || !respEmail) { Toast.erro("Nome e e-mail do responsável são obrigatórios."); return; }

        const body = {
            nome: document.getElementById("np-nome").value.trim(),
            data_nascimento: document.getElementById("np-nascimento").value,
            avatar_mascote: document.getElementById("np-avatar").value,
        };
        const profissionaisSelecionados = Array.from(document.querySelectorAll(".chk-np-profissional:checked")).map(c => parseInt(c.value));
        if (profissionaisSelecionados.length) body.profissionais_ids = profissionaisSelecionados;
        let pacienteId;
        try {
            const r = await Api.post("/pessoas/pacientes", body);
            pacienteId = r.id;
        } catch (err) {
            Toast.erro(err.message);
            return;
        }
        try {
            const rResp = await Api.post(`/pessoas/pacientes/${pacienteId}/vincular-responsavel`, { nome: respNome, email: respEmail, telefone: respTelefone });
            modal.remove();
            Toast.sucesso("Paciente cadastrado com sucesso!");
            mostrarModalConvite(rResp.link_convite, respNome);
        } catch (err) {
            // O paciente já foi criado — não desfazemos isso; só avisamos que
            // falta vincular o responsável (dá pra fazer depois, na Jornada).
            modal.remove();
            Toast.erro(`Paciente criado, mas não deu pra vincular o responsável: ${err.message}. Vincule depois pela Jornada.`);
            despachar();
        }
    });
}

// ---------------------------------------------------------------- Ficha do paciente (visão restrita da Secretária)
//
// Insight do usuário (31/08/2026): a secretária NÃO abre a Jornada completa
// (viewJornadaPaciente, cheia de dado clínico — diário, evoluções, PEI,
// financeiro). Esta tela dedicada mostra só o que ela pode ver e fazer:
// nome, responsável(is) e os profissionais vinculados, com ação pra vincular
// mais um profissional ou responsável. Consultas continuam sendo agendadas
// pela Agenda normal (ela já vê/agenda pra qualquer paciente por lá).

async function viewPacienteSecretaria(app, params) {
    const [paciente, profissionaisDaClinica] = await Promise.all([
        Api.get(`/pessoas/pacientes/${params.id}`),
        Api.get("/pessoas/profissionais?incluir_gestor=1"),
    ]);
    const idsVinculados = new Set(paciente.profissionais.map(p => p.id));
    const opcoesProfissionais = profissionaisDaClinica.filter(p => !idsVinculados.has(p.id));

    const conteudo = `
      <div class="grade grade-dupla" style="max-width:820px;">
        <div class="cartao" style="grid-column: 1 / -1;">
          <p class="texto-xs texto-suave" style="font-weight:700; margin-bottom:4px;">PACIENTE</p>
          <h3 style="margin-bottom:6px;">${paciente.avatar_mascote || "🧒"} ${escapeHtml(paciente.nome)}</h3>
          <p class="texto-xs texto-suave">Como secretária, você vê só nome e responsável — dados clínicos (jornada, diário, evoluções) ficam visíveis apenas para gestor e profissionais.</p>
        </div>

        <div class="cartao">
          <p class="texto-xs texto-suave" style="font-weight:700; margin-bottom:12px;">RESPONSÁVEL</p>
          ${paciente.responsaveis.length ? `<div class="coluna gap-2">${paciente.responsaveis.map(r => `
            <div class="pessoa-linha" style="padding:4px 0;">
              <div class="pessoa-info">
                <div class="pessoa-nome">${escapeHtml(r.nome)}</div>
                <div class="pessoa-sub">${escapeHtml(r.email)}${r.telefone ? " · " + escapeHtml(r.telefone) : ""}</div>
              </div>
            </div>`).join("")}</div>` : `<p class="texto-sm texto-suave">Nenhum responsável vinculado ainda.</p>`}
          <button class="botao botao-secundario botao-sm" id="btn-add-responsavel" style="margin-top:12px;">+ Vincular responsável</button>
        </div>

        <div class="cartao">
          <p class="texto-xs texto-suave" style="font-weight:700; margin-bottom:12px;">PROFISSIONAIS QUE ATENDEM</p>
          ${paciente.profissionais.length ? `<div class="coluna gap-2">${paciente.profissionais.map(p => `
            <div class="pessoa-linha" style="padding:4px 0;">
              <div class="pessoa-info">
                <div class="pessoa-nome">${escapeHtml(p.nome)}${p.principal ? ' <span class="badge badge-marca texto-xs">Principal</span>' : ""}</div>
                <div class="pessoa-sub">${escapeHtml(p.especialidade || "")}</div>
              </div>
            </div>`).join("")}</div>` : `<p class="texto-sm texto-suave">Nenhum profissional vinculado ainda.</p>`}
          ${opcoesProfissionais.length ? `
          <div class="linha gap-2" style="margin-top:12px; align-items:center;">
            <select id="sel-add-profissional" style="flex:1;">
              ${opcoesProfissionais.map(p => `<option value="${p.id}">${escapeHtml(p.nome)} — ${escapeHtml(p.especialidade || "")}</option>`).join("")}
            </select>
            <button class="botao botao-secundario botao-sm" id="btn-add-profissional">+ Vincular</button>
          </div>` : ""}
        </div>
      </div>`;

    app.innerHTML = renderShellSidebar("#/secretaria/pacientes", paciente.nome, conteudo);
    anexarEventosShell();

    const btnAddProf = document.getElementById("btn-add-profissional");
    if (btnAddProf) btnAddProf.addEventListener("click", async () => {
        const profissionalId = parseInt(document.getElementById("sel-add-profissional").value);
        try {
            await Api.post(`/pessoas/pacientes/${params.id}/vincular-profissional`, { profissional_id: profissionalId });
            Toast.sucesso("Profissional vinculado!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });

    document.getElementById("btn-add-responsavel").addEventListener("click", () => {
        const modal = el(`
        <div class="modal-fundo">
          <div class="modal-caixa">
            <h3 style="margin-bottom:18px;">Vincular responsável</h3>
            <form id="form-add-responsavel">
              <div class="campo"><label>Nome ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="ar-nome" required /></div>
              <div class="linha gap-4">
                <div class="campo" style="flex:1;"><label>E-mail ${ASTERISCO_OBRIGATORIO}</label><input type="email" id="ar-email" required /></div>
                <div class="campo" style="flex:1;"><label>Telefone</label><input type="tel" id="ar-telefone" /></div>
              </div>
              <div class="linha gap-3" style="margin-top:16px;">
                <button type="submit" class="botao botao-primario">Vincular</button>
                <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
              </div>
            </form>
          </div>
        </div>`);
        document.body.appendChild(modal);
        modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
        document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
        ativarMascaraCampo(document.getElementById("ar-telefone"), "telefone");
        document.getElementById("form-add-responsavel").addEventListener("submit", async (e) => {
            e.preventDefault();
            const nome = document.getElementById("ar-nome").value.trim();
            const email = document.getElementById("ar-email").value.trim();
            const telefone = document.getElementById("ar-telefone").value.trim();
            try {
                const r = await Api.post(`/pessoas/pacientes/${params.id}/vincular-responsavel`, { nome, email, telefone });
                modal.remove();
                mostrarModalConvite(r.link_convite, nome);
            } catch (err) { Toast.erro(err.message); }
        });
    });
}

// ---------------------------------------------------------------- Equipe (Profissionais) — apenas Gestor

async function viewEquipe(app) {
    // Secretária (insight do usuário, 31/08/2026): enxerga a Equipe — e agora
    // também a lista de secretárias, ela incluída — mas só em modo leitura,
    // sem cadastrar/editar/arquivar ninguém.
    const souSecretaria = Sessao.usuario.papel === "secretaria";
    const base = Sessao.usuario.papel === "gestor" ? "gestor" : "secretaria";
    const profissionais = await Api.get("/pessoas/profissionais?incluir_inativos=1&incluir_gestor=1&incluir_secretarias=1");
    const padraoAtivo = !!(Sessao.usuario.organizacao && Sessao.usuario.organizacao.agenda_permissao_total_padrao);
    const conteudo = `
      ${souSecretaria ? "" : `
      <div class="cartao-flat" style="margin-bottom:16px; display:flex; gap:12px; align-items:flex-start; justify-content:space-between; flex-wrap:wrap;">
        <div class="linha gap-2" style="align-items:flex-start;">
          <span style="font-size:18px;">🗓️</span>
          <div>
            <p class="texto-sm" style="font-weight:700;">Todos os profissionais gerenciam qualquer agenda</p>
            <p class="texto-xs texto-suave" style="margin-top:2px;">
              Quando ligado, todo profissional da equipe (os já cadastrados e os próximos) ganha o mesmo acesso de agenda do
              gestor, sem precisar marcar um por um. Dá pra abrir uma exceção pontual na caixinha individual do cadastro
              de cada profissional a qualquer momento.
            </p>
          </div>
        </div>
        <label class="chave-toggle" style="flex-shrink:0;">
          <input type="checkbox" id="chk-agenda-total-padrao" ${padraoAtivo ? "checked" : ""} />
          <span class="chave-slider"></span>
        </label>
      </div>`}
      <div class="lista-pessoas">
        ${profissionais.length ? profissionais.map(p => {
            const ehGestor = p.papel === "gestor";
            const ehSecretaria = p.papel === "secretaria";
            return `
          <div class="pessoa-linha cartao" style="margin-bottom:10px; ${!p.ativo ? "opacity:.55;" : ""}">
            <div class="pessoa-avatar" style="font-size:24px; overflow:hidden;">${p.avatar_base64 ? renderAvatarUsuario(p, 40) : (ehSecretaria ? "🗂️" : (ICONES_ESPECIALIDADE[p.especialidade] || "🩺"))}</div>
            <div class="pessoa-info">
              <div class="pessoa-nome">${escapeHtml(p.nome)}</div>
              <div class="pessoa-sub">${ehSecretaria ? "" : escapeHtml(p.especialidade || "Sem especialidade") + " · "}${escapeHtml(p.email)}${p.telefone ? " · " + escapeHtml(p.telefone) : ""}</div>
            </div>
            ${ehSecretaria ? "" : `<span class="badge badge-marca">${p.total_pacientes} pacientes</span>`}
            ${ehGestor
                ? `<span class="badge badge-marca" title="Gestor(a) da clínica, atuando também como profissional — edite os dados profissionais em Configurações > Minha Conta">👑 Gestor(a)</span>`
                : `<span class="badge ${p.ativo ? "badge-sucesso" : "badge-neutro"}">${p.ativo ? "Ativo" : "Arquivado"}</span>`}
            ${ehSecretaria ? `<span class="badge badge-marca">🗂️ Secretária</span>` : ""}
            ${souSecretaria ? "" : `
            <div class="linha gap-1">
              ${ehSecretaria ? "" : `<button class="botao-icone btn-disponibilidade-prof" data-id="${p.id}" data-nome="${escapeHtml(p.nome)}" title="Disponibilidade de agenda" style="width:34px; height:34px; font-size:14px;">🕐</button>`}
              ${ehGestor ? "" : ehSecretaria ? `
              <button class="botao-icone btn-editar-secretaria" data-id="${p.id}" title="Editar" style="width:34px; height:34px; font-size:14px;">✏️</button>
              <button class="botao-icone btn-arquivar-secretaria" data-id="${p.id}" data-ativo="${p.ativo}" title="${p.ativo ? "Arquivar" : "Reativar"}" style="width:34px; height:34px; font-size:14px;">${p.ativo ? "🗑️" : "♻️"}</button>` : `
              <button class="botao-icone btn-editar-prof" data-id="${p.id}" title="Editar" style="width:34px; height:34px; font-size:14px;">✏️</button>
              <button class="botao-icone btn-arquivar-prof" data-id="${p.id}" data-ativo="${p.ativo}" data-total="${p.total_pacientes}" title="${p.ativo ? "Arquivar" : "Reativar"}" style="width:34px; height:34px; font-size:14px;">${p.ativo ? "🗑️" : "♻️"}</button>`}
            </div>`}
          </div>`;
        }).join("") : `<div class="estado-vazio"><div class="emoji">👥</div><p>Nenhum profissional cadastrado ainda.</p></div>`}
      </div>`;

    const acoesTopo = souSecretaria ? "" : `
        <button class="botao botao-primario" id="btn-novo-prof">+ Novo Profissional</button>
        <button class="botao botao-secundario" id="btn-nova-secretaria">+ Nova Secretária</button>`;
    app.innerHTML = renderShellSidebar(`#/${base}/equipe`, "Equipe", conteudo, acoesTopo);
    anexarEventosShell();

    document.querySelectorAll(".btn-disponibilidade-prof").forEach(btn => btn.addEventListener("click", () => {
        abrirModalDisponibilidade(btn.dataset.id, btn.dataset.nome);
    }));

    if (souSecretaria) return; // resto da função é só ações de escrita (gestor).

    document.getElementById("btn-novo-prof").addEventListener("click", () => abrirModalProfissional(null));
    document.getElementById("btn-nova-secretaria").addEventListener("click", () => abrirModalSecretaria(null));

    document.getElementById("chk-agenda-total-padrao").addEventListener("change", async (e) => {
        const ativo = e.target.checked;
        try {
            const r = await Api.put("/pessoas/equipe/agenda-permissao-total-padrao", { ativo });
            if (Sessao.usuario.organizacao) Sessao.usuario.organizacao.agenda_permissao_total_padrao = r.ativo;
            Toast.sucesso(
                r.ativo
                    ? `Ativado! ${r.profissionais_atualizados} profissional(is) já podem gerenciar qualquer agenda da clínica.`
                    : `Desativado. ${r.profissionais_atualizados} profissional(is) voltaram a gerenciar só a própria agenda.`
            );
            despachar();
        } catch (err) {
            Toast.erro(err.message);
            e.target.checked = !ativo;
        }
    });

    document.querySelectorAll(".btn-editar-prof").forEach(btn => btn.addEventListener("click", async () => {
        const prof = profissionais.find(p => p.id === Number(btn.dataset.id));
        abrirModalProfissional(prof);
    }));

    document.querySelectorAll(".btn-editar-secretaria").forEach(btn => btn.addEventListener("click", () => {
        const sec = profissionais.find(p => p.id === Number(btn.dataset.id));
        abrirModalSecretaria(sec);
    }));

    // Veio de um link tipo "#/gestor/equipe?abrir=12" (ex: clique num profissional
    // no dashboard) — abre o modal de edição dele automaticamente.
    const paramsUrl = new URLSearchParams(location.hash.split("?")[1] || "");
    const idParaAbrir = paramsUrl.get("abrir");
    if (idParaAbrir) {
        const prof = profissionais.find(p => p.id === Number(idParaAbrir));
        if (prof) abrirModalProfissional(prof);
    }

    document.querySelectorAll(".btn-arquivar-prof").forEach(btn => btn.addEventListener("click", async () => {
        const ativo = btn.dataset.ativo === "1" || btn.dataset.ativo === "true";
        const total = btn.dataset.total;
        const msg = ativo
            ? `Arquivar este profissional? Ele deixa de aparecer na Equipe e não poderá mais logar, mas o histórico com os ${total} paciente(s) vinculado(s) é preservado.`
            : "Reativar este profissional? Ele volta a aparecer na Equipe e recupera o acesso.";
        if (!confirm(msg)) return;
        try {
            const r = await Api.put(`/pessoas/profissionais/${btn.dataset.id}/arquivar`);
            Toast.sucesso(r.ativo ? "Profissional reativado!" : "Profissional arquivado.");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    }));

    document.querySelectorAll(".btn-arquivar-secretaria").forEach(btn => btn.addEventListener("click", async () => {
        const ativo = btn.dataset.ativo === "1" || btn.dataset.ativo === "true";
        const msg = ativo
            ? "Arquivar esta secretária? Ela deixa de aparecer na Equipe e não poderá mais logar."
            : "Reativar esta secretária? Ela volta a aparecer na Equipe e recupera o acesso.";
        if (!confirm(msg)) return;
        try {
            const r = await Api.put(`/pessoas/secretarias/${btn.dataset.id}/arquivar`);
            Toast.sucesso(r.ativo ? "Secretária reativada!" : "Secretária arquivada.");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    }));
}

function abrirModalSecretaria(secretariaExistente) {
    const editando = !!secretariaExistente;
    const s = secretariaExistente || {};
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:18px;">${editando ? "Editar secretária" : "Cadastrar secretária"}</h3>
        <form id="form-secretaria">
          <div class="campo"><label>Nome completo ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="sf-nome" value="${escapeHtml(s.nome || "")}" required /></div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>E-mail ${ASTERISCO_OBRIGATORIO}</label><input type="email" id="sf-email" value="${escapeHtml(s.email || "")}" required /></div>
            <div class="campo" style="flex:1;"><label>Telefone</label><input type="tel" id="sf-telefone" value="${escapeHtml(s.telefone || "")}" /></div>
          </div>
          <p class="texto-xs texto-suave" style="margin: 4px 0 16px;">
            A secretária poderá cadastrar pacientes (definindo o profissional), agendar consultas pra qualquer
            profissional, vincular profissional/responsável a um paciente, ver a Equipe (somente visualização) e
            publicar no Mural — sem acesso a dados clínicos, financeiro ou configurações da clínica.
          </p>
          <div class="linha gap-3" style="margin-top:20px;">
            <button type="submit" class="botao botao-primario">${editando ? "Salvar alterações" : "Cadastrar"}</button>
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    ativarMascaraCampo(document.getElementById("sf-telefone"), "telefone");

    document.getElementById("form-secretaria").addEventListener("submit", async (e) => {
        e.preventDefault();
        const body = {
            nome: document.getElementById("sf-nome").value.trim(),
            email: document.getElementById("sf-email").value.trim(),
            telefone: document.getElementById("sf-telefone").value.trim(),
        };
        try {
            if (editando) {
                await Api.put(`/pessoas/secretarias/${s.id}`, body);
                modal.remove();
                Toast.sucesso("Secretária atualizada!");
                despachar();
            } else {
                const r = await Api.post("/pessoas/secretarias", body);
                modal.remove();
                Toast.sucesso("Secretária cadastrada!");
                mostrarModalConvite(r.link_convite, body.nome);
            }
        } catch (err) { Toast.erro(err.message); }
    });
}

function abrirModalProfissional(profissionalExistente) {
    const editando = !!profissionalExistente;
    const p = profissionalExistente || {};
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:18px;">${editando ? "Editar profissional" : "Cadastrar profissional"}</h3>
        <form id="form-prof">
          <div class="linha gap-3" style="align-items:center; margin-bottom:14px;">
            <div id="preview-avatar-prof" style="width:56px; height:56px; border-radius:50%; display:flex; align-items:center; justify-content:center; background:var(--cor-marca-clara); overflow:hidden; flex-shrink:0;">
              ${renderAvatarUsuario(p, 56)}
            </div>
            <div>
              <input type="file" id="pf-avatar-arquivo" accept="image/*" style="display:none;" />
              <button type="button" class="botao botao-secundario botao-sm" id="btn-escolher-avatar-prof">📷 Foto (opcional)</button>
            </div>
          </div>
          <div class="campo"><label>Nome completo ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="pf-nome" value="${escapeHtml(p.nome || "")}" required /></div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>E-mail ${ASTERISCO_OBRIGATORIO}</label><input type="email" id="pf-email" value="${escapeHtml(p.email || "")}" required /></div>
            <div class="campo" style="flex:1;"><label>Telefone</label><input type="tel" id="pf-telefone" value="${escapeHtml(p.telefone || "")}" /></div>
          </div>
          <div class="campo">
            <label>Especialidade</label>
            <input type="text" id="pf-especialidade" list="lista-especialidades-clinica" value="${escapeHtml(p.especialidade || "")}" placeholder="Ex: Fonoaudiologia" />
            <datalist id="lista-especialidades-clinica">
              ${especialidadesDaClinica().map(e => `<option value="${escapeHtml(e)}">`).join("")}
            </datalist>
            ${!especialidadesDaClinica().length ? `<p class="texto-xs texto-suave" style="margin-top:4px;">Dica: cadastre as especialidades da clínica em Configurações pra ter sugestões aqui.</p>` : ""}
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;">
              <label>Tipo de registro</label>
              <select id="pf-tipo-registro">
                <option value="">Não informar</option>
                ${["CRFa (Fonoaudiologia)", "CREFITO (Fisio/TO)", "CRP (Psicologia)", "CRN (Nutrição)", "CRE (Pedagogia)", "Outro"].map(t => `<option value="${t}" ${p.tipo_registro === t ? "selected" : ""}>${t}</option>`).join("")}
              </select>
            </div>
            <div class="campo" style="flex:1;"><label>Número de registro</label><input type="text" id="pf-numero-registro" value="${escapeHtml(p.numero_registro || "")}" placeholder="Ex: 12345" /></div>
          </div>
          <hr style="border:none; border-top:1px solid var(--cor-borda); margin:16px 0;" />
          <div class="campo">
            <label>Cor na Agenda</label>
            <div class="linha gap-2" style="align-items:center;">
              <input type="color" id="pf-cor-agenda" value="${corSegura(p.cor_agenda, "#5B4FE9")}" style="width:48px; height:38px; padding:2px;" />
              <p class="texto-xs texto-suave">Identifica as consultas deste profissional no calendário.</p>
            </div>
          </div>
          <label class="linha gap-2" style="align-items:flex-start; cursor:pointer; padding:10px 0;">
            <input type="checkbox" id="pf-agenda-total" ${p.agenda_permissao_total ? "checked" : ""} style="margin-top:3px;" />
            <span class="texto-sm">Gerenciar a agenda de <strong>qualquer paciente</strong> da clínica (não só os vinculados a ele). Igual ao acesso do gestor, só pra Agenda.</span>
          </label>
          <div class="linha gap-3" style="margin-top:20px;">
            <button type="submit" class="botao botao-primario">${editando ? "Salvar alterações" : "Cadastrar"}</button>
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    ativarMascaraCampo(document.getElementById("pf-telefone"), "telefone");

    let avatarNovo = null; // { base64, nome } — só preenchido se trocarem a foto nesta sessão
    document.getElementById("btn-escolher-avatar-prof").addEventListener("click", () => document.getElementById("pf-avatar-arquivo").click());
    document.getElementById("pf-avatar-arquivo").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        if (file.size > 2 * 1024 * 1024) { Toast.erro("A foto precisa ter até 2MB."); e.target.value = ""; return; }
        const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        avatarNovo = { base64, nome: file.name };
        document.getElementById("preview-avatar-prof").innerHTML = `<img src="data:image/png;base64,${base64}" style="width:100%; height:100%; object-fit:cover;" alt="Foto" />`;
    });

    document.getElementById("form-prof").addEventListener("submit", async (e) => {
        e.preventDefault();
        const body = {
            nome: document.getElementById("pf-nome").value.trim(),
            email: document.getElementById("pf-email").value.trim(),
            telefone: document.getElementById("pf-telefone").value.trim(),
            especialidade: document.getElementById("pf-especialidade").value,
            cor_agenda: document.getElementById("pf-cor-agenda").value,
            agenda_permissao_total: document.getElementById("pf-agenda-total").checked,
            tipo_registro: document.getElementById("pf-tipo-registro").value,
            numero_registro: document.getElementById("pf-numero-registro").value.trim(),
        };
        if (avatarNovo) { body.avatar_base64 = avatarNovo.base64; body.avatar_nome = avatarNovo.nome; }
        try {
            if (editando) {
                await Api.put(`/pessoas/profissionais/${p.id}`, body);
                modal.remove();
                Toast.sucesso("Profissional atualizado!");
                despachar();
            } else {
                const r = await Api.post("/pessoas/profissionais", body);
                modal.remove();
                Toast.sucesso("Profissional cadastrado!");
                mostrarModalConvite(r.link_convite, body.nome);
            }
        } catch (err) { Toast.erro(err.message); }
    });
}

const DIAS_SEMANA_NOMES_UI = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"];

async function abrirModalDisponibilidade(profissionalId, nomeProfissional) {
    const dias = await Api.get(`/pessoas/profissionais/${profissionalId}/disponibilidade`);
    const podeEditar = Sessao.usuario.papel === "gestor" || (Sessao.usuario.papel === "profissional" && Sessao.usuario.id === parseInt(profissionalId));

    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa modal-grande">
        <h3 style="margin-bottom:4px;">🕐 Disponibilidade de agenda</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:18px;">${escapeHtml(nomeProfissional)}${!podeEditar ? " — somente visualização" : ""}</p>
        <form id="form-disponibilidade">
          <div class="coluna gap-2">
            ${dias.map(d => `
              <div class="linha gap-3" style="align-items:center; flex-wrap:wrap; padding:8px 0; border-bottom:1px solid var(--cor-borda);" data-dia="${d.dia_semana}">
                <strong class="texto-sm" style="width:90px;">${d.dia_nome}</strong>
                <label class="linha gap-2" style="align-items:center;">
                  <input type="checkbox" class="chk-ausente-dia" ${d.ausente ? "checked" : ""} ${!podeEditar ? "disabled" : ""} />
                  <span class="texto-xs">Ausente</span>
                </label>
                <label class="texto-xs texto-suave">Início <input type="time" class="input-hora-inicio" value="${d.hora_inicio}" ${d.ausente || !podeEditar ? "disabled" : ""} style="width:100px;" /></label>
                <label class="texto-xs texto-suave">Fim <input type="time" class="input-hora-fim" value="${d.hora_fim}" ${d.ausente || !podeEditar ? "disabled" : ""} style="width:100px;" /></label>
              </div>`).join("")}
          </div>
          <div class="linha gap-3" style="margin-top:18px;">
            ${podeEditar ? `<button type="submit" class="botao botao-primario">Salvar disponibilidade</button>` : ""}
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Fechar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    modal.querySelector("#btn-cancelar-modal").addEventListener("click", () => modal.remove());

    modal.querySelectorAll(".chk-ausente-dia").forEach(chk => chk.addEventListener("change", () => {
        const linha = chk.closest("[data-dia]");
        const ausente = chk.checked;
        linha.querySelector(".input-hora-inicio").disabled = ausente || !podeEditar;
        linha.querySelector(".input-hora-fim").disabled = ausente || !podeEditar;
    }));

    const form = modal.querySelector("#form-disponibilidade");
    if (podeEditar) form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const diasBody = Array.from(modal.querySelectorAll("[data-dia]")).map(linha => ({
            dia_semana: parseInt(linha.dataset.dia),
            ausente: linha.querySelector(".chk-ausente-dia").checked,
            hora_inicio: linha.querySelector(".input-hora-inicio").value || "08:00",
            hora_fim: linha.querySelector(".input-hora-fim").value || "18:00",
        }));
        try {
            await Api.put(`/pessoas/profissionais/${profissionalId}/disponibilidade`, { dias: diasBody });
            Toast.sucesso("Disponibilidade atualizada!");
            modal.remove();
        } catch (err) { Toast.erro(err.message); }
    });
}
