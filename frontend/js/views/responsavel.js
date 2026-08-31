// ============================================================================
// views/responsavel.js — Início do Responsável + Troca de perfil/filho
// ============================================================================

async function garantirPacienteAtivo() {
    if (Sessao.pacienteAtivoId) return Sessao.pacienteAtivoId;
    const me = await Api.get("/auth/me");
    if (me.filhos && me.filhos.length) {
        Sessao.pacienteAtivoId = me.filhos[0].id;
        return me.filhos[0].id;
    }
    return null;
}

async function viewResponsavelInicio(app) {
    const pacienteId = await garantirPacienteAtivo();
    if (!pacienteId) {
        app.innerHTML = renderShellMobile("#/responsavel/inicio", { icone: "💛", texto: "Encanto em Casa" },
            `<div class="estado-vazio"><div class="emoji">🧸</div><h3>Nenhuma criança vinculada</h3><p>Entre em contato com a clínica para vincular seu perfil.</p></div>`);
        return;
    }

    const [dados, me] = await Promise.all([
        Api.get(`/jornada/paciente/${pacienteId}`),
        Api.get("/auth/me"),
    ]);
    const paciente = dados.paciente;
    const diarios = dados.jornada ? await Api.get(`/diario/jornada/${dados.jornada.id}`) : [];

    const seletorFilhos = me.filhos.length > 1 ? `
      <div class="linha gap-2" style="margin-bottom:20px; overflow-x:auto; padding-bottom:4px;">
        ${me.filhos.map(f => `
          <button class="botao ${String(f.id) === String(pacienteId) ? "botao-primario" : "botao-secundario"} botao-sm btn-trocar-filho" data-id="${f.id}" style="flex-shrink:0;">
            ${f.avatar_mascote} ${f.nome.split(" ")[0]}
          </button>`).join("")}
      </div>` : "";

    const missoesPendentes = (dados.missoes || []).filter(m => m.status === "pendente" || m.status === "iniciada");
    // Sem feedback ainda vem primeiro (é o que precisa de atenção), e dentro de
    // cada grupo, a mais recente primeiro — assim quem falta avaliar não se perde lá embaixo.
    const missoesConcluidas = (dados.missoes || []).filter(m => m.status === "concluida")
        .sort((a, b) => (a.tem_feedback === b.tem_feedback ? 0 : a.tem_feedback ? 1 : -1) || (b.concluida_em || "").localeCompare(a.concluida_em || ""));

    const conteudo = `
    ${seletorFilhos}
    <div class="cartao" style="text-align:center; background:linear-gradient(160deg, var(--cor-marca-clara), var(--cor-fundo)); border:none; margin-bottom:20px;">
      ${svgMascote({ emoji: paciente.avatar_mascote, estagio: dados.gamificacao?.mascote_estagio || 1, tamanho: 110, flutuar: true })}
      <h2 style="margin-top:10px; font-size:20px;">${escapeHtml(paciente.nome)}</h2>
      <p class="texto-sm texto-suave">${nivelParaTexto(dados.gamificacao?.nivel || 1)} · Nível ${dados.gamificacao?.nivel || 1}</p>
      <div class="linha" style="justify-content:center; gap:22px; margin-top:14px;">
        <div><div style="font-weight:700;">⭐ ${dados.gamificacao?.estrelas || 0}</div><div class="texto-xs texto-suave">estrelas</div></div>
        <div><div style="font-weight:700;">🔥 ${dados.gamificacao?.sequencia_dias || 0}</div><div class="texto-xs texto-suave">sequência</div></div>
        <div><div style="font-weight:700;">${dados.progresso_pct || 0}%</div><div class="texto-xs texto-suave">da semana</div></div>
      </div>
      <button class="botao botao-acento" id="btn-entrar-mundo-crianca" style="width:100%; margin-top:18px;">🎮 Entrar no Mundo de ${paciente.nome.split(" ")[0]}</button>
    </div>

    ${dados.jornada ? `
    <div class="cartao" style="margin-bottom:16px;">
      <p class="texto-xs texto-suave" style="font-weight:700; margin-bottom:6px;">🎯 OBJETIVO DA JORNADA</p>
      <p class="texto-sm">${escapeHtml(dados.jornada.objetivo_principal)}</p>
    </div>

    ${diarios.length ? `
    <div class="cartao" style="margin-bottom:16px; border-color:var(--cor-marca);">
      <div class="linha-entre" style="margin-bottom:8px;">
        <p class="texto-xs texto-suave" style="font-weight:700;">📔 DIÁRIO TERAPÊUTICO · ${formatarData(diarios[0].data_atendimento)}</p>
        ${diarios.length > 1 ? `<button class="botao-texto botao-sm" id="btn-ver-historico-diario-resp" style="padding:2px 0;">Histórico →</button>` : ""}
      </div>
      <p class="texto-sm texto-suave" style="margin-bottom:10px;">${escapeHtml(truncarTexto(diarios[0].mensagem_familia || "A equipe registrou o atendimento — toque para ver os detalhes.", 90))}</p>
      <div class="linha gap-2" style="flex-wrap:wrap;">
        ${diarios[0].pontos_positivos.length ? `<span class="badge badge-sucesso">✔️ ${diarios[0].pontos_positivos.length} ponto(s) positivo(s)</span>` : ""}
        ${diarios[0].mensagem_familia ? `<span class="badge badge-marca">💛 mensagem da equipe</span>` : ""}
      </div>
      <button class="botao botao-primario botao-sm btn-ver-diario-resp" data-id="${diarios[0].id}" style="width:100%; margin-top:12px;">Ver registro completo</button>
    </div>` : ""}

    <h3 style="margin-bottom:12px;">📋 Missões desta semana</h3>
    <div class="coluna gap-2" style="margin-bottom:20px;">
      ${missoesPendentes.length ? missoesPendentes.map(renderMissaoResponsavel).join("") : `<p class="texto-sm texto-suave">Todas as missões da semana foram concluídas! 🎉</p>`}
    </div>

    ${missoesConcluidas.length ? `
    <h3 style="margin-bottom:12px;">✅ Já conquistadas</h3>
    <div class="coluna gap-2" style="margin-bottom:20px;">
      ${missoesConcluidas.map(renderMissaoResponsavel).join("")}
    </div>` : ""}
    ` : `<div class="estado-vazio"><div class="emoji">🌱</div><p>A jornada terapêutica ainda não foi iniciada pela equipe.</p></div>`}
    `;

    app.innerHTML = renderShellMobile("#/responsavel/inicio", { icone: "💛", texto: "Olá, " + Sessao.usuario.nome.split(" ")[0] }, conteudo);

    document.querySelectorAll(".btn-trocar-filho").forEach(b => b.addEventListener("click", () => {
        Sessao.pacienteAtivoId = b.dataset.id;
        despachar();
    }));

    const btnVerDiario = document.querySelector(".btn-ver-diario-resp");
    if (btnVerDiario) btnVerDiario.addEventListener("click", () => abrirModalDetalheDiario(btnVerDiario.dataset.id));
    const btnHistoricoResp = document.getElementById("btn-ver-historico-diario-resp");
    if (btnHistoricoResp && dados.jornada) btnHistoricoResp.addEventListener("click", () => abrirModalHistoricoDiario(dados.jornada.id));

    document.querySelectorAll(".btn-avaliar-missao").forEach(btn => btn.addEventListener("click", (e) => {
        e.stopPropagation();
        abrirModalFeedbackMissao(btn.dataset.id, btn.dataset.titulo);
    }));

    document.querySelectorAll(".btn-preview-missao").forEach(card => card.addEventListener("click", () => {
        abrirPreviaMissao(card.dataset.id);
    }));

    document.getElementById("btn-entrar-mundo-crianca").addEventListener("click", () => {
        Sessao.modoCrianca = true;
        location.hash = "#/crianca/mundo";
    });
}

// Troca de mascote pelo responsável (insight do usuário, 31/08/2026):
// provisório, "até que possamos criar a parte de gamificação" — troca só o
// emoji exibido (pacientes.avatar_mascote), sem nenhuma outra consequência.
function abrirModalTrocarMascote(pacienteId, mascoteAtual) {
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:4px;">Trocar mascote</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:16px;">Escolha o novo mascote — em breve isso vai fazer parte da Gamificação.</p>
        <div class="linha gap-2" style="flex-wrap:wrap; justify-content:center;">
          ${MASCOTES_DISPONIVEIS.map(e => `
            <button type="button" class="btn-opcao-mascote" data-mascote="${e}" style="border:2px solid ${e === mascoteAtual ? "var(--cor-marca)" : "var(--cor-borda)"}; background:${e === mascoteAtual ? "var(--cor-marca-clara)" : "#fff"}; border-radius:14px; width:52px; height:52px; font-size:26px; cursor:pointer;">${e}</button>`).join("")}
        </div>
        <button type="button" class="botao botao-secundario" id="btn-cancelar-modal" style="width:100%; margin-top:18px;">Cancelar</button>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());

    modal.querySelectorAll(".btn-opcao-mascote").forEach(btn => btn.addEventListener("click", async () => {
        const mascote = btn.dataset.mascote;
        try {
            await Api.put(`/pessoas/pacientes/${pacienteId}/mascote`, { avatar_mascote: mascote });
            Toast.sucesso("Mascote atualizado!");
            modal.remove();
            despachar();
        } catch (err) { Toast.erro(err.message); }
    }));
}

function renderMissaoResponsavel(m) {
    const podeAvaliar = m.status === "concluida" && !m.tem_feedback;
    return `
    <div class="missao-card btn-preview-missao ${m.status === "concluida" ? "concluida" : ""}" data-id="${m.id}" style="cursor:pointer;">
      <div class="missao-checkbox">${m.status === "concluida" ? "✓" : (m.status === "iniciada" ? "▶" : "")}</div>
      <div style="flex:1;">
        <div class="missao-titulo">${escapeHtml(m.titulo)}</div>
        <div class="missao-meta">+${m.recompensa_xp} ${escapeHtml(nomeMoeda())} · ${formatarData(m.prazo)}${m.status === "iniciada" ? " · <span style=\"color:var(--cor-marca); font-weight:700;\">em andamento</span>" : ""}</div>
        ${podeAvaliar ? `<button type="button" class="botao-texto botao-sm btn-avaliar-missao" data-id="${m.id}" data-titulo="${escapeHtml(m.titulo)}" style="padding:4px 0; margin-top:2px;">💬 Como foi essa atividade?</button>` : ""}
        ${m.tem_feedback ? `<p class="texto-xs texto-suave" style="margin-top:2px;">✅ Feedback enviado</p>` : ""}
      </div>
    </div>`;
}

async function abrirPreviaMissao(missaoId) {
    let missao;
    try {
        missao = await Api.get(`/jornada/missao/${missaoId}`);
    } catch (err) {
        Toast.erro(err.message);
        return;
    }
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <div style="text-align:center; padding:8px 0 4px;">
          <div style="font-size:50px;">${missao.atividades && missao.atividades[0] ? (ICONES_TIPO_EXERCICIO[missao.atividades[0].tipo] || "🎯") : "🎯"}</div>
          <h3 style="margin-top:8px;">${escapeHtml(missao.titulo)}</h3>
          <p class="texto-sm texto-suave" style="margin-top:6px;">${escapeHtml(missao.descricao || "Vamos praticar juntos!")}</p>
        </div>
        ${(missao.atividades || []).length ? `
        <div class="coluna gap-2" style="margin-top:16px; text-align:left;">
          ${missao.atividades.map(a => `
            <div class="cartao-flat linha gap-3">
              <span style="font-size:18px;">${ICONES_TIPO_EXERCICIO[a.tipo] || "📝"}</span>
              <span class="texto-sm" style="font-weight:600;">${escapeHtml(a.titulo)}</span>
            </div>`).join("")}
        </div>` : ""}
        <div class="cartao-flat" style="margin-top:16px; text-align:center;">
          <p class="texto-sm">🌟 Recompensa: <strong>+${missao.recompensa_xp} ${escapeHtml(nomeMoeda())}</strong></p>
        </div>
        <p class="texto-xs texto-suave" style="text-align:center; margin-top:14px;">Essa é a prévia de como ${escapeHtml((missao.paciente_nome || "seu filho(a)").split(" ")[0])} vê essa missão no Mundo dele(a).</p>
        <button type="button" class="botao botao-secundario" id="btn-cancelar-modal" style="width:100%; margin-top:14px;">Fechar</button>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
}

function abrirModalFeedbackMissao(missaoId, tituloMissao) {
    const HUMORES = [["😄", "Adorou"], ["🙂", "Gostou"], ["😐", "Neutro"], ["😕", "Difícil"]];
    let humorEscolhido = "🙂";
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:4px;">Como foi essa atividade?</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:16px;">"${escapeHtml(tituloMissao)}"</p>
        <div class="linha gap-2" style="justify-content:center; margin-bottom:18px;">
          ${HUMORES.map(([emoji, label]) => `
            <button type="button" class="btn-humor-feedback" data-humor="${emoji}" style="border:2px solid var(--cor-borda); background:#fff; border-radius:14px; padding:10px 14px; cursor:pointer; text-align:center;">
              <div style="font-size:26px;">${emoji}</div>
              <div class="texto-xs texto-suave" style="margin-top:2px;">${label}</div>
            </button>`).join("")}
        </div>
        <div class="campo"><label>Conte um pouco mais (opcional)</label><textarea id="fb-texto" rows="2" placeholder="Ex: Ele adorou fazer essa atividade hoje!"></textarea></div>
        <div class="linha gap-3" style="margin-top:12px;">
          <button type="button" class="botao botao-primario" id="btn-enviar-feedback">Enviar</button>
          <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Agora não</button>
        </div>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());

    function marcarHumor(botao) {
        modal.querySelectorAll(".btn-humor-feedback").forEach(b => { b.style.borderColor = "var(--cor-borda)"; b.style.background = "#fff"; });
        botao.style.borderColor = "var(--cor-marca)";
        botao.style.background = "var(--cor-marca-clara)";
        humorEscolhido = botao.dataset.humor;
    }
    modal.querySelectorAll(".btn-humor-feedback").forEach(b => b.addEventListener("click", () => marcarHumor(b)));
    marcarHumor(modal.querySelector('.btn-humor-feedback[data-humor="🙂"]'));

    document.getElementById("btn-enviar-feedback").addEventListener("click", async () => {
        const texto = document.getElementById("fb-texto").value.trim() || "Ele(a) adorou fazer essa atividade hoje!";
        try {
            await Api.post(`/jornada/missao/${missaoId}/feedback`, { texto, humor: humorEscolhido });
            Toast.sucesso("Obrigado pelo feedback! A equipe vai adorar ler isso. 💛");
            modal.remove();
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });
}

// ---------------------------------------------------------------- Perfil / Troca de perfil (UX Pattern 18)

async function viewPerfilResponsavel(app) {
    const me = await Api.get("/auth/me");
    const conteudo = `
    <div class="cartao" style="text-align:center; margin-bottom:20px;">
      <div id="preview-avatar-perfil" style="width:76px; height:76px; border-radius:50%; margin:0 auto; display:flex; align-items:center; justify-content:center; background:var(--cor-marca-clara); overflow:hidden; font-size:40px;">
        ${renderAvatarUsuario(me, 76)}
      </div>
      <input type="file" id="input-avatar-perfil" accept="image/*" style="display:none;" />
      <button type="button" class="botao-texto botao-sm" id="btn-trocar-avatar" style="margin-top:8px;">📷 Trocar foto</button>
      <p class="texto-sm texto-suave" style="margin-top:2px;">${escapeHtml(me.email)}</p>
    </div>

    <div class="cartao" style="margin-bottom:20px;">
      <p class="texto-xs texto-suave" style="font-weight:700; margin-bottom:12px;">MEUS DADOS</p>
      <form id="form-perfil-resp">
        <div class="campo"><label>Nome completo ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="perfil-nome" value="${escapeHtml(me.nome)}" required /></div>
        <div class="campo"><label>Telefone</label><input type="tel" id="perfil-telefone" value="${escapeHtml(me.telefone || "")}" /></div>
        <button type="submit" class="botao botao-primario" style="width:100%;">Salvar alterações</button>
      </form>
    </div>

    <div class="cartao" style="margin-bottom:20px;">
      <p class="texto-xs texto-suave" style="font-weight:700; margin-bottom:10px;">MEUS FILHOS</p>
      <div class="lista-pessoas">
        ${me.filhos.map(f => `
          <div class="pessoa-linha">
            <div class="pessoa-avatar btn-trocar-foto-filho" data-id="${f.id}" style="cursor:pointer; position:relative;" title="Trocar foto">
              ${renderFotoPaciente(f, 40)}
            </div>
            <div class="pessoa-info"><div class="pessoa-nome">${escapeHtml(f.nome)}</div><div class="pessoa-sub">${calcularIdade(f.data_nascimento)}</div></div>
            <button type="button" class="botao-texto botao-sm btn-ver-ficha-filho" data-id="${f.id}" data-nome="${escapeHtml(f.nome)}">📋 Ficha</button>
            <button type="button" class="botao-texto botao-sm btn-trocar-foto-filho" data-id="${f.id}">📷 Foto</button>
            <button type="button" class="botao-texto botao-sm btn-trocar-mascote-filho" data-id="${f.id}" data-mascote="${f.avatar_mascote}">✏️ Mascote</button>
          </div>`).join("")}
      </div>
      <input type="file" id="input-foto-filho" accept="image/*" style="display:none;" />
    </div>
    <button class="botao botao-perigo" id="btn-sair-mobile" style="width:100%; margin-top:20px;">Sair da conta</button>
    `;
    app.innerHTML = renderShellMobile("#/responsavel/perfil", { icone: "👤", texto: "Meu perfil" }, conteudo);
    document.getElementById("btn-sair-mobile").addEventListener("click", () => {
        Sessao.limpar();
        location.hash = "#/login";
    });

    ativarMascaraCampo(document.getElementById("perfil-telefone"), "telefone");

    // --- Avatar do responsável ---
    document.getElementById("btn-trocar-avatar").addEventListener("click", () => document.getElementById("input-avatar-perfil").click());
    document.getElementById("input-avatar-perfil").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        if (file.size > 2 * 1024 * 1024) { Toast.erro("A foto precisa ter até 2MB."); e.target.value = ""; return; }
        const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        try {
            await Api.put("/pessoas/perfil", { avatar_base64: base64, avatar_nome: file.name });
            const u = Sessao.usuario; u.avatar_base64 = base64; Sessao.usuario = u;
            document.getElementById("preview-avatar-perfil").innerHTML = `<img src="data:image/png;base64,${base64}" style="width:100%; height:100%; object-fit:cover;" alt="Foto" />`;
            Toast.sucesso("Foto atualizada!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });

    // --- Dados básicos ---
    document.getElementById("form-perfil-resp").addEventListener("submit", async (e) => {
        e.preventDefault();
        const nome = document.getElementById("perfil-nome").value.trim();
        const telefone = document.getElementById("perfil-telefone").value.trim();
        try {
            await Api.put("/pessoas/perfil", { nome, telefone });
            const u = Sessao.usuario; u.nome = nome; u.telefone = telefone; Sessao.usuario = u;
            Toast.sucesso("Dados atualizados!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });

    // --- Foto de cada filho ---
    const inputFotoFilho = document.getElementById("input-foto-filho");
    let filhoAlvoId = null;
    document.querySelectorAll(".btn-trocar-foto-filho").forEach(el => el.addEventListener("click", () => {
        filhoAlvoId = el.dataset.id;
        inputFotoFilho.click();
    }));
    inputFotoFilho.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file || !filhoAlvoId) return;
        if (file.size > 2 * 1024 * 1024) { Toast.erro("A foto precisa ter até 2MB."); e.target.value = ""; return; }
        const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        try {
            await Api.put(`/pessoas/pacientes/${filhoAlvoId}/foto`, { foto_base64: base64, foto_nome: file.name });
            Toast.sucesso("Foto atualizada!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
        e.target.value = "";
    });

    document.querySelectorAll(".btn-ver-ficha-filho").forEach(btn => btn.addEventListener("click", () => {
        abrirModalFichaClinicaLeitura(btn.dataset.id, btn.dataset.nome);
    }));

    document.querySelectorAll(".btn-trocar-mascote-filho").forEach(btn => btn.addEventListener("click", () => {
        abrirModalTrocarMascote(btn.dataset.id, btn.dataset.mascote);
    }));
}

async function abrirModalFichaClinicaLeitura(pacienteId, nomeCrianca) {
    let ficha;
    try {
        ficha = await Api.get(`/pessoas/pacientes/${pacienteId}/ficha-clinica`);
    } catch (err) {
        Toast.erro(err.message);
        return;
    }
    const linhas = [
        ["DIAGNÓSTICO", ficha.diagnostico],
        ["⚠️ ALERGIAS", ficha.alergias],
        ["MEDICAÇÕES EM USO", ficha.medicamentos_em_uso],
        ["PROFISSIONAIS EXTERNOS", ficha.profissionais_externos],
        ["OBSERVAÇÕES", ficha.observacoes],
    ].filter(([, valor]) => valor);

    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:4px;">📋 Ficha Clínica</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:16px;">${escapeHtml(nomeCrianca)}</p>
        ${ficha.preenchida ? `
          <div class="coluna gap-2">
            ${linhas.map(([rotulo, valor]) => `<div><p class="texto-xs texto-suave" style="font-weight:700;">${rotulo}</p><p class="texto-sm">${escapeHtml(valor)}</p></div>`).join("")}
          </div>
          <p class="texto-xs texto-suave" style="margin-top:14px;">Preenchida pela equipe da clínica · ${formatarData(ficha.atualizado_em)}</p>
        ` : `<p class="texto-sm texto-suave">A equipe da clínica ainda não preencheu a ficha clínica. Isso é normal — é um campo opcional.</p>`}
        <button type="button" class="botao botao-secundario" id="btn-cancelar-modal" style="width:100%; margin-top:16px;">Fechar</button>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
}
