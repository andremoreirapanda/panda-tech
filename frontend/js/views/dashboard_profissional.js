// ============================================================================
// views/dashboard_profissional.js — Documento 11, Jornada 02
// ============================================================================

async function viewDashboardProfissional(app) {
    const d = await Api.get("/indicadores/profissional");

    const conteudo = `
    <div class="kpi-grade" style="margin-bottom:32px;">
      ${kpiCard("🧒", d.total_pacientes, "pacientes sob meus cuidados", "marca")}
      ${kpiCard("✅", d.dentro_planejado.length, "dentro do planejado", "sucesso")}
      ${kpiCard("🟡", d.baixa_adesao.length, "com baixa adesão", d.baixa_adesao.length > 0 ? "acento" : "sucesso")}
      ${kpiCard("🔴", d.precisa_atencao.length, "precisam de atenção", d.precisa_atencao.length > 0 ? "alerta" : "sucesso")}
    </div>

    ${gruposPacientes("🔴 Precisam de atenção", d.precisa_atencao, "Missões em atraso — vale uma mensagem para a família.")}
    ${gruposPacientes("🟡 Baixa adesão", d.baixa_adesao, "Menos de 60% das missões da semana concluídas.")}
    ${gruposPacientes("✅ Dentro do planejado", d.dentro_planejado, "Seguindo bem o plano terapêutico.")}
    `;

    app.innerHTML = renderShellSidebar("#/profissional/dashboard", "Bom te ver por aqui 👋", conteudo);
    anexarEventosShell();
}

function gruposPacientes(titulo, lista, legenda) {
    if (!lista.length) return "";
    return `
    <div style="margin-bottom:28px;">
      <h3 style="margin-bottom:4px;">${titulo}</h3>
      <p class="texto-sm texto-suave" style="margin-bottom:14px;">${legenda}</p>
      <div class="grade" style="grid-template-columns: repeat(auto-fill, minmax(240px,1fr));">
        ${lista.map(p => `
          <a href="#/profissional/paciente/${p.id}" class="cartao" style="display:flex; align-items:center; gap:12px;">
            <div style="font-size:30px;">${p.avatar_mascote}</div>
            <div style="flex:1;">
              <div style="font-weight:700; font-size:14px;">${escapeHtml(p.nome)}</div>
              <div class="progresso-barra" style="margin-top:6px;"><div class="progresso-preenchimento" style="width:${p.progresso_pct}%"></div></div>
            </div>
            <span class="texto-xs texto-suave">${p.progresso_pct}%</span>
          </a>`).join("")}
      </div>
    </div>`;
}
