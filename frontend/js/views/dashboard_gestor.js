// ============================================================================
// views/dashboard_gestor.js — "4 perguntas em 30 segundos" (Documento 11)
// ============================================================================

async function viewDashboardGestor(app) {
    const [kpi, avisos, semanal] = await Promise.all([
        Api.get("/indicadores/gestor"),
        Api.get("/comunicacao/avisos"),
        Api.get("/indicadores/clinica/engajamento-semanal"),
    ]);
    const maxSemanal = Math.max(1, ...semanal.map(d => d.missoes_concluidas));

    const conteudo = `
    <div id="dash-financeiro"></div>
    ${kpi.ict_medio_pct !== null && kpi.ict_medio_pct !== undefined ? `
    <div class="cartao" style="margin-bottom:20px; display:flex; align-items:center; gap:24px; flex-wrap:wrap; background:linear-gradient(160deg, var(--cor-marca-clara), var(--cor-superficie)); border-color:var(--cor-marca);">
      ${circuloProgresso({ pct: kpi.ict_medio_pct, tamanho: 108, espessura: 11, cor: "var(--cor-marca)", label: "ICT médio" })}
      <div style="flex:1; min-width:220px;">
        <h3 style="margin-bottom:6px;">🔗 Índice de Continuidade Terapêutica</h3>
        <p class="texto-sm texto-suave">
          Mede se as crianças seguem engajadas com o tratamento entre as consultas — adesão às missões, sequência
          de prática, participação da família e acompanhamento do profissional na última semana. É uma métrica de
          <strong>engajamento com a plataforma</strong>, não uma avaliação clínica.
        </p>
      </div>
    </div>` : ""}

    <div class="cartao" style="margin-bottom:20px;">
      <h3 style="margin-bottom:20px;">📊 Missões concluídas nos últimos 7 dias</h3>
      <div class="linha" style="align-items:flex-end; gap:14px; height:160px;">
        ${semanal.map(d => `
          <div class="coluna" style="flex:1; align-items:center; gap:8px;">
            <span class="texto-xs texto-suave">${d.missoes_concluidas}</span>
            <div style="width:100%; background:var(--cor-marca); border-radius:8px 8px 0 0; height:${Math.max(4, (d.missoes_concluidas / maxSemanal) * 100)}px; transition:height .4s ease;"></div>
            <span class="texto-xs texto-suave">${new Date(d.data + "T12:00").toLocaleDateString("pt-BR", { weekday: "short" })}</span>
          </div>`).join("")}
      </div>
    </div>

    <div class="kpi-grade" style="margin-bottom:32px;">
      ${kpiCard("🧒", kpi.criancas_ativas_hoje, "crianças ativas hoje", "sucesso")}
      ${kpiCard("📅", kpi.consultas_hoje, "consultas hoje", "marca")}
      ${kpiCard("💳", kpi.pagamentos_hoje, "pagamentos recebidos hoje", "acento")}
      ${kpiCard("⚠️", kpi.familias_inativas_5dias, "famílias há +5 dias inativas", kpi.familias_inativas_5dias > 0 ? "alerta" : "sucesso")}
    </div>
    <div class="grade grade-principal">
      <div class="cartao">
        <div class="linha-entre" style="margin-bottom:18px;">
          <h3>Engajamento geral da clínica</h3>
          <span class="badge badge-marca">${kpi.engajamento_pct}%</span>
        </div>
        <div class="progresso-barra" style="margin-bottom:20px;">
          <div class="progresso-preenchimento" style="width:${kpi.engajamento_pct}%"></div>
        </div>
        <p class="texto-suave texto-sm">Proporção de crianças ativas com pelo menos uma missão concluída hoje, sobre o total de ${kpi.total_pacientes} pacientes ativos.</p>

        <h3 style="margin-top:28px; margin-bottom:14px;">Equipe (${kpi.total_profissionais})</h3>
        <div class="lista-pessoas">
          ${kpi.equipe.map(p => `
            <a href="#/gestor/equipe?abrir=${p.id}" class="pessoa-linha" style="text-decoration:none; color:inherit; cursor:pointer;">
              <div class="pessoa-avatar">${ICONES_ESPECIALIDADE[p.especialidade] || "🩺"}</div>
              <div class="pessoa-info">
                <div class="pessoa-nome">${escapeHtml(p.nome)}</div>
                <div class="pessoa-sub">${escapeHtml(p.especialidade || "")}</div>
              </div>
              <span class="badge badge-neutro">${p.total_pacientes} pacientes</span>
            </a>`).join("")}
        </div>
      </div>

      <div class="cartao">
        <h3 style="margin-bottom:14px;">📣 Mural da clínica</h3>
        <div class="coluna gap-4">
          ${avisos.length ? avisos.slice(0, 4).map(a => `
            <div class="cartao-flat">
              <div class="linha-entre" style="margin-bottom:4px;">
                <strong style="font-size:13.5px;">${escapeHtml(a.titulo)}</strong>
              </div>
              <p class="texto-sm texto-suave">${escapeHtml(a.conteudo)}</p>
              <p class="texto-xs texto-suave" style="margin-top:6px;">${tempoRelativo(a.criado_em)} · ${escapeHtml(a.autor_nome)}</p>
            </div>`).join("") : `<p class="texto-sm texto-suave">Nenhum aviso publicado ainda.</p>`}
        </div>
        <a href="#/gestor/mural" class="botao botao-texto botao-sm" style="margin-top:10px;">Ver mural completo →</a>
      </div>
    </div>`;

    app.innerHTML = renderShellSidebar("#/gestor/dashboard", "Dashboard", conteudo);
    anexarEventosShell();
    carregarCartaoFinanceiroDashboard();
}

// Cartão "Pendências do financeiro" (07/11/2026): só com o módulo, carregado à
// parte (não atrasa o dashboard) e some se a chamada falhar.
async function carregarCartaoFinanceiroDashboard() {
    if (typeof financeiroHabilitado !== "function" || !financeiroHabilitado()) return;
    try {
        const [p, c] = await Promise.all([
            Api.get("/financeiro/pendencias"),
            Api.get("/financeiro/cobrancas?status=rascunho"),
        ]);
        const alvo = document.getElementById("dash-financeiro");
        if (!alvo) return;
        const itens = [
            ["Sessões sem acordo", p.sem_acordo.length], ["Sessões sem valor", p.sem_valor.length],
            ["Pacotes acabando", p.pacotes_acabando.length], ["Cobranças vencidas", p.vencidas.length],
            ["A revisar", p.revisar.length], ["Para conferir", c.para_conferir],
        ];
        alvo.innerHTML = `
        <div class="cartao" style="margin-bottom:20px;">
          <div class="linha-entre" style="margin-bottom:12px; flex-wrap:wrap; gap:8px;">
            <h3>💳 Pendências do financeiro</h3>
            <a href="#/gestor/financeiro" class="botao botao-texto botao-sm">Abrir Financeiro →</a>
          </div>
          <div class="linha gap-4" style="flex-wrap:wrap;">
            ${itens.map(([nome, n]) => `<div style="min-width:120px;"><div style="font-size:22px; font-weight:700; color:${n > 0 ? "var(--cor-alerta)" : "var(--cor-sucesso)"};">${n}</div><div class="texto-xs texto-suave">${nome}</div></div>`).join("")}
          </div>
        </div>`;
    } catch (err) { /* sem o cartão se falhar */ }
}

function kpiCard(icone, valor, label, cor) {
    const cores = { sucesso: "var(--cor-sucesso)", marca: "var(--cor-marca)", acento: "var(--cor-acento-escuro)", alerta: "var(--cor-alerta)" };
    return `
    <div class="kpi-card">
      <div class="kpi-icone">${icone}</div>
      <div class="kpi-valor" style="color:${cores[cor] || "var(--cor-tinta)"}">${valor}</div>
      <div class="kpi-label">${label}</div>
    </div>`;
}
