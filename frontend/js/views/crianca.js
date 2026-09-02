// ============================================================================
// views/crianca.js — Mundo da Criança (UX Pattern 09, Documento 11 Jornada 04)
// Tela cheia, lúdica, sem densidade de informação — feita para toque de criança.
// ============================================================================

// Seta do botão "Voltar" (redesenho 03/09/2026, insight do usuário): SVG de
// ponta arredondada em vez do caractere "←" — fica nítida em qualquer tela,
// e herda a cor do botão via currentColor.
function svgSetaVoltar() {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" style="width:16px; height:16px;"><path d="M19 12H5M11 18l-6-6 6-6"/></svg>`;
}

function topoCrianca(paciente) {
    return `
    <div class="crianca-topo-barra">
      <a href="#/responsavel/inicio" id="btn-sair-mundo-crianca" class="btn-crianca-voltar" title="Voltar para o Responsável">${svgSetaVoltar()}<span>Voltar</span></a>
      <span class="fonte-display" style="font-weight:700; font-size:15px;">Mundo de ${escapeHtml((paciente.nome || "").split(" ")[0])}</span>
      <a href="#/crianca/medalhas" class="botao-icone" style="background:#fff;" title="Ver minhas medalhas">🏅</a>
    </div>`;
}

async function viewMundoCrianca(app) {
    const pacienteId = Sessao.pacienteAtivoId;
    const dados = await Api.get(`/jornada/paciente/${pacienteId}`);
    const paciente = dados.paciente;
    const gam = dados.gamificacao || {};
    const missoesPendentes = (dados.missoes || []).filter(m => m.status === "pendente" || m.status === "iniciada");
    const missoesFeitas = (dados.missoes || []).filter(m => m.status === "concluida");

    const conteudo = `
    ${topoCrianca(paciente)}
    <div style="text-align:center; padding: 16px 20px 8px;">
      ${svgMascote({ emoji: paciente.avatar_mascote, estagio: gam.mascote_estagio || 1, tamanho: 150, flutuar: true })}
      <h1 class="fonte-display" style="font-size:22px; margin-top:8px;">Oi, ${escapeHtml((paciente.nome || "").split(" ")[0])}! 👋</h1>
      <p class="texto-sm texto-suave">${missoesPendentes.length > 0 ? "Vamos brincar e aprender hoje?" : "Você completou tudo por hoje! 🎉"}</p>

      <div class="linha" style="justify-content:center; gap:14px; margin: 16px 0;">
        <div class="badge badge-acento" style="font-size:14px; padding:8px 16px;" title="Estrelas que você já ganhou completando missões">⭐ ${gam.estrelas || 0} <span style="font-weight:400; opacity:.85;">estrelas</span></div>
        <div class="badge badge-marca" style="font-size:14px; padding:8px 16px;" title="Dias seguidos praticando — não perca essa sequência!">🔥 ${gam.sequencia_dias || 0} <span style="font-weight:400; opacity:.85;">${gam.sequencia_dias === 1 ? "dia seguido" : "dias seguidos"}</span></div>
      </div>
    </div>

    <div style="padding: 0 20px 100px;">
      ${missoesPendentes.length ? `
        <h3 class="fonte-display" style="margin-bottom:14px; font-size:17px;">🗺️ Missões de hoje</h3>
        <div class="coluna gap-3">
          ${missoesPendentes.map(m => {
              // Missão bloqueada pro paciente depois que o Prazo passa (insight
              // do usuário, 02/09/2026) — ainda aparece na lista (pra não
              // "sumir" sem explicação), mas já avisa que está travada.
              const prazoExpirado = m.prazo && m.prazo < new Date().toISOString().slice(0, 10);
              return `
            <button class="missao-crianca-card btn-abrir-missao ${prazoExpirado ? "bloqueada" : ""}" data-id="${m.id}" style="width:100%; border:none; text-align:left;">
              <div class="missao-crianca-icone">${m.atividades && m.atividades[0] ? (ICONES_TIPO_EXERCICIO[m.atividades[0].tipo] || "🎯") : "🎯"}</div>
              <div style="flex:1;">
                <div class="missao-crianca-titulo">${escapeHtml(m.titulo)}</div>
                <div class="missao-crianca-xp">${prazoExpirado
                    ? `<span style="color:var(--cor-alerta); font-weight:700;">⏰ Prazo esgotado</span>`
                    : `+${m.recompensa_xp} ${escapeHtml(nomeMoeda())} · ${m.tempo_estimado_min} min ${m.status === "iniciada" ? " · <span style=\"color:var(--cor-marca);\">em andamento</span>" : ""}`}</div>
              </div>
              <span style="font-size:22px;">${prazoExpirado ? "🔒" : (m.status === "iniciada" ? "⏳" : "▶️")}</span>
            </button>`;
          }).join("")}
        </div>` : `
        <div style="text-align:center; padding:30px 0;">
          <div style="font-size:50px;">🎉</div>
          <p class="fonte-display" style="font-size:17px; margin-top:8px;">Você é demais!</p>
          <p class="texto-sm texto-suave">Volte amanhã para novas missões.</p>
        </div>`}

      ${missoesFeitas.length ? `
        <h3 class="fonte-display" style="margin: 24px 0 14px; font-size:17px;">✅ Já conquistadas</h3>
        <div class="coluna gap-2">
          ${missoesFeitas.map(m => `
            <div class="missao-crianca-card" style="opacity:.6;">
              <div class="missao-crianca-icone" style="background:var(--cor-sucesso-clara);">✅</div>
              <div style="flex:1;"><div class="missao-crianca-titulo">${escapeHtml(m.titulo)}</div></div>
            </div>`).join("")}
        </div>` : ""}
    </div>
    `;

    app.innerHTML = `<div class="shell-crianca">${conteudo}</div>`;
    document.querySelectorAll(".btn-abrir-missao").forEach(btn => btn.addEventListener("click", () => {
        location.hash = `#/crianca/missao/${btn.dataset.id}`;
    }));
    anexarSaidaMundoCrianca();
}

function anexarSaidaMundoCrianca() {
    const btn = document.getElementById("btn-sair-mundo-crianca");
    if (btn) btn.addEventListener("click", (e) => {
        e.preventDefault();
        Sessao.modoCrianca = false;
        location.hash = "#/responsavel/inicio";
    });
}

// ---------------------------------------------------------------- Detalhe / Execução da missão (UX Pattern 10)

async function viewMissaoCrianca(app, params) {
    const missaoId = params.id;
    const pacienteId = Sessao.pacienteAtivoId;
    const dados = await Api.get(`/jornada/paciente/${pacienteId}`);
    const missao = (dados.missoes || []).find(m => String(m.id) === String(missaoId));
    if (!missao) { location.hash = "#/crianca/mundo"; return; }
    const paciente = dados.paciente;
    const gam = dados.gamificacao || {};

    // US-021 (activity_started): abrir a missão já conta como "iniciada" para a criança.
    if (missao.status === "pendente") {
        Api.post(`/jornada/missao/${missaoId}/iniciar`).catch(() => {});
    }

    // Missão bloqueada pro paciente depois que o Prazo passa (insight do
    // usuário, 02/09/2026) — o backend também recusa (/concluir e
    // /concluir-dia), isso aqui só evita mostrar um botão que vai dar erro.
    const prazoExpirado = missao.prazo && missao.prazo < new Date().toISOString().slice(0, 10);
    const cartaoPrazoExpirado = `
    <div class="cartao-flat" style="margin-top:24px; text-align:center; background:var(--cor-alerta-clara);">
      <p class="texto-sm" style="font-weight:700;">🔒 O prazo dessa missão acabou</p>
      <p class="texto-xs texto-suave" style="margin-top:4px;">Peça pro seu responsável falar com o profissional pra abrir mais um tempinho.</p>
    </div>`;

    const conteudo = `
    <div class="crianca-topo-barra">
      <a href="#/crianca/mundo" class="btn-crianca-voltar" title="Voltar">${svgSetaVoltar()}<span>Voltar</span></a>
      ${svgMascote({ emoji: paciente.avatar_mascote, estagio: gam.mascote_estagio || 1, tamanho: 36 })}
    </div>
    <div style="text-align:center; padding: 4px 24px 0;">
      <h1 class="fonte-display" style="font-size:22px; margin-top:6px;">${escapeHtml(missao.titulo)}</h1>
      <p class="texto-sm texto-suave" style="margin-top:8px;">${escapeHtml(missao.descricao || "Vamos praticar juntos!")}</p>

      ${(missao.atividades || []).length ? `
      <div class="coluna gap-2" style="margin-top:20px; text-align:left;">
        ${missao.atividades.map(a => `
          <div class="cartao-flat" data-atividade-id="${a.id}" data-exercicio-id="${a.exercicio_id}" data-tem-arquivo="${a.tem_arquivo ? "1" : "0"}" data-conteudo-url="${escapeHtml(a.conteudo_url || "")}">
            <div class="linha gap-3">
              <span style="font-size:20px;">${ICONES_TIPO_EXERCICIO[a.tipo] || "📝"}</span>
              <span class="texto-sm" style="font-weight:600;">${escapeHtml(a.titulo)}</span>
            </div>
            ${a.descricao ? `<p class="texto-xs texto-suave" style="margin-top:6px;">${escapeHtml(a.descricao)}</p>` : ""}
            <div class="midia-atividade-crianca" style="margin-top:10px;"></div>
          </div>`).join("")}
      </div>` : ""}

      <div class="cartao-flat" style="margin-top:24px;">
        <p class="texto-sm">🌟 Recompensa: <strong>+${missao.recompensa_xp} ${escapeHtml(nomeMoeda())}</strong></p>
      </div>

      ${missao.tipo === "semanal" ? renderProgressoSemanal(missao, prazoExpirado) : (prazoExpirado ? cartaoPrazoExpirado : `
      <button class="botao botao-acento" id="btn-concluir-missao" style="width:100%; margin-top:24px; padding:16px; font-size:16px;">
        Concluí essa missão! 🎉
      </button>`)}
    </div>
    `;
    app.innerHTML = `<div class="shell-crianca">${conteudo}</div>`;

    document.querySelectorAll("[data-atividade-id]").forEach(async (cartao) => {
        const midiaEl = cartao.querySelector(".midia-atividade-crianca");
        const temArquivo = cartao.dataset.temArquivo === "1";
        const conteudoUrl = cartao.dataset.conteudoUrl;
        if (temArquivo) {
            midiaEl.innerHTML = `<p class="texto-xs texto-suave">carregando...</p>`;
            try {
                const ex = await Api.get(`/biblioteca/exercicios/${cartao.dataset.exercicioId}`);
                const mime = ex.tipo === "imagem" ? "image/png" : ex.tipo === "video" ? "video/mp4" : ex.tipo === "audio" ? "audio/mpeg" : "application/pdf";
                const src = `data:${mime};base64,${ex.arquivo_base64}`;
                if (ex.tipo === "imagem") midiaEl.innerHTML = `<img src="${src}" style="width:100%; border-radius:10px; display:block;" alt="${escapeHtml(ex.titulo)}" />`;
                else if (ex.tipo === "video") midiaEl.innerHTML = `<video controls style="width:100%; border-radius:10px;"><source src="${src}"></video>`;
                else if (ex.tipo === "audio") midiaEl.innerHTML = `<audio controls style="width:100%;"><source src="${src}"></audio>`;
                else midiaEl.innerHTML = `<a href="${src}" download="${escapeHtml(ex.arquivo_nome || "arquivo")}" class="botao botao-secundario botao-sm">📄 Abrir arquivo</a>`;
            } catch (err) {
                midiaEl.innerHTML = "";
            }
        } else if (conteudoUrl) {
            midiaEl.innerHTML = `<a href="${escapeHtml(conteudoUrl)}" target="_blank" class="botao botao-secundario botao-sm">🔗 Ver conteúdo</a>`;
        }
    });

    if (missao.tipo === "semanal") {
        const btnDia = document.getElementById("btn-concluir-dia-missao");
        if (btnDia) btnDia.addEventListener("click", async () => {
            btnDia.disabled = true;
            btnDia.textContent = "Marcando...";
            try {
                const r = await Api.post(`/jornada/missao/${missaoId}/concluir-dia`);
                if (r.semana_completa) {
                    mostrarCelebracao(r.gamificacao, () => { location.hash = "#/crianca/mundo"; });
                } else {
                    Toast.sucesso(`Dia ${r.dias_concluidos}/7 marcado! Volte amanhã pra continuar 💪`);
                    location.hash = "#/crianca/mundo";
                }
            } catch (err) {
                Toast.erro(err.message);
                btnDia.disabled = false;
                btnDia.textContent = "Marquei hoje! 🎉";
            }
        });
        return;
    }

    const btnConcluirMissao = document.getElementById("btn-concluir-missao");
    if (!btnConcluirMissao) return; // prazo expirado — sem botão pra ligar o listener
    btnConcluirMissao.addEventListener("click", async () => {
        const btn = document.getElementById("btn-concluir-missao");
        btn.disabled = true;
        btn.textContent = "Concluindo...";
        try {
            const r = await Api.post(`/jornada/missao/${missaoId}/concluir`);
            mostrarCelebracao(r.gamificacao, () => { location.hash = "#/crianca/mundo"; });
        } catch (err) {
            Toast.erro(err.message);
            btn.disabled = false;
            btn.textContent = "Concluí essa missão! 🎉";
        }
    });
}

function renderProgressoSemanal(missao, prazoExpirado) {
    const diasConcluidos = missao.dias_concluidos || [];
    const hojeChave = new Date().toISOString().slice(0, 10);
    const jaMarcouHoje = diasConcluidos.includes(hojeChave);
    const total = missao.dias_concluidos_total || 0;
    // Frequência configurável por missão (achado de UAT, 26/08/2026) — antes fixa em 7.
    const frequenciaDias = missao.frequencia_dias || 7;

    return `
    <div class="cartao-flat" style="margin-top:16px;">
      <p class="texto-sm" style="font-weight:700; margin-bottom:10px;">📅 Progresso: ${total}/${frequenciaDias} dias</p>
      <div class="linha gap-2" style="justify-content:center; flex-wrap:wrap;">
        ${Array.from({ length: frequenciaDias }, (_, i) => `
          <div style="width:32px; height:32px; border-radius:8px; display:flex; align-items:center; justify-content:center; font-size:16px; background:${i < total ? "var(--cor-marca)" : "var(--cor-fundo-alt)"}; color:${i < total ? "#fff" : "var(--cor-tinta-suave)"};">
            ${i < total ? "✓" : ""}
          </div>`).join("")}
      </div>
    </div>
    ${prazoExpirado ? `
    <div class="cartao-flat" style="margin-top:16px; text-align:center; background:var(--cor-alerta-clara);">
      <p class="texto-sm" style="font-weight:700;">🔒 O prazo dessa missão acabou</p>
      <p class="texto-xs texto-suave" style="margin-top:4px;">Peça pro seu responsável falar com o profissional pra abrir mais um tempinho.</p>
    </div>` : jaMarcouHoje ? `
    <div class="cartao-flat" style="margin-top:16px; text-align:center;">
      <p class="texto-sm">✅ Você já marcou hoje! Volte amanhã pra continuar 😊</p>
    </div>` : `
    <button class="botao botao-acento" id="btn-concluir-dia-missao" style="width:100%; margin-top:24px; padding:16px; font-size:16px;">
      Marquei hoje! 🎉
    </button>`}`;
}

function mostrarCelebracao(gamificacao, aoFechar) {
    confetes();
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa" style="text-align:center;">
        <div style="font-size:60px;">🏆</div>
        <h2 class="fonte-display" style="margin:10px 0;">Muito bem!!</h2>
        <p class="texto-sm texto-suave">Você ganhou <strong>+${gamificacao.xp_ganho} ${escapeHtml(nomeMoeda())}</strong></p>
        <div class="linha" style="justify-content:center; gap:18px; margin:18px 0;">
          <div><div style="font-weight:700; font-size:20px;">${gamificacao.xp_total}</div><div class="texto-xs texto-suave">${escapeHtml(nomeMoeda())} total</div></div>
          <div><div style="font-weight:700; font-size:20px;">🔥 ${gamificacao.sequencia_dias}</div><div class="texto-xs texto-suave">sequência</div></div>
        </div>
        ${gamificacao.medalhas_novas && gamificacao.medalhas_novas.length ? `
          <div class="cartao-flat" style="margin-bottom:16px;">
            <p class="texto-sm" style="font-weight:700;">🎖️ Nova medalha desbloqueada!</p>
            <p class="texto-sm">${gamificacao.medalhas_novas.join(", ")}</p>
          </div>` : ""}
        <button class="botao botao-primario" id="btn-fechar-celebracao" style="width:100%;">Continuar</button>
      </div>
    </div>`);
    document.body.appendChild(modal);
    document.getElementById("btn-fechar-celebracao").addEventListener("click", () => { modal.remove(); aoFechar(); });
}

// ---------------------------------------------------------------- Medalhas / Baú (UX Pattern 11)

async function viewMedalhasCrianca(app) {
    const pacienteId = Sessao.pacienteAtivoId;
    const dados = await Api.get(`/gamificacao/paciente/${pacienteId}`);
    const paciente = (await Api.get(`/jornada/paciente/${pacienteId}`)).paciente;

    const conteudo = `
    ${topoCrianca(paciente)}
    <div style="padding: 16px 20px 100px; text-align:center;">
      <h1 class="fonte-display" style="font-size:20px; margin-bottom:4px;">🏅 Minhas medalhas</h1>
      <p class="texto-sm texto-suave" style="margin-bottom:24px;">${dados.medalhas_conquistadas.length} de ${dados.todas_medalhas.length} conquistadas</p>
      <div class="medalha-grade" style="text-align:center;">
        ${dados.todas_medalhas.map(m => `
          <div class="medalha-item ${m.conquistada ? "" : "bloqueada"}">
            <div class="medalha-icone">${m.icone_emoji}</div>
            <div class="medalha-nome">${escapeHtml(m.nome)}</div>
          </div>`).join("")}
      </div>

      ${dados.bau.length ? `
      <h3 class="fonte-display" style="margin: 28px 0 14px; font-size:17px;">🎁 Baú de recompensas</h3>
      <div class="medalha-grade">
        ${dados.bau.map(b => `
          <div class="medalha-item">
            <div class="medalha-icone" style="background:var(--cor-marca-clara); border-color:var(--cor-marca);">${b.icone_emoji}</div>
            <div class="medalha-nome">${escapeHtml(b.nome)}</div>
          </div>`).join("")}
      </div>` : ""}
    </div>`;

    app.innerHTML = `<div class="shell-crianca">${conteudo}</div>`;
    anexarSaidaMundoCrianca();
}
