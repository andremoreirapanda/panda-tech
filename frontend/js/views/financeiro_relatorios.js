// ============================================================================
// views/financeiro_relatorios.js — Relatórios do Financeiro (seção 6.5, 23/11/2026). Só gestor.
// Três cartões: cobranças em aberto e vencidas, pacotes e mensalidades acabando, sessões sem acordo.
// Cada um com filtros, tabela, totais e Excel (financeiro_util.planilhaRelatorio).
// ============================================================================

async function viewRelatoriosFinanceiro(app) {
    const hoje = paraChaveDia(new Date());
    const conteudo = `
    <div class="linha gap-3" style="margin-bottom:16px;">
      <a class="botao botao-texto" href="#/gestor/financeiro">← Voltar às cobranças</a>
    </div>
    <div class="cartao" style="margin-bottom:20px;" id="rl-aberto">
      <div class="linha-entre" style="flex-wrap:wrap; gap:8px; margin-bottom:10px;">
        <h3>Cobranças em aberto e vencidas</h3>
        <button type="button" class="botao botao-secundario botao-sm" data-excel="em-aberto">📊 Excel</button>
      </div>
      <div class="linha gap-3" style="flex-wrap:wrap; align-items:flex-end; margin-bottom:10px;">
        <div class="campo" style="margin:0;"><label for="rl-ab-esp">Especialidade</label><input type="text" id="rl-ab-esp" placeholder="Todas" /></div>
      </div>
      <div class="rl-corpo"><p class="texto-sm texto-suave">Carregando…</p></div>
    </div>
    <div class="cartao" style="margin-bottom:20px;" id="rl-acabando">
      <div class="linha-entre" style="flex-wrap:wrap; gap:8px; margin-bottom:10px;">
        <h3>Pacotes e mensalidades acabando</h3>
        <div class="linha gap-2"><button type="button" class="botao botao-secundario botao-sm" data-excel="pacotes">📊 Pacotes</button>
        <button type="button" class="botao botao-secundario botao-sm" data-excel="mensalidades">📊 Mensalidades</button></div>
      </div>
      <div class="linha gap-3" style="flex-wrap:wrap; align-items:flex-end; margin-bottom:10px;">
        <div class="campo" style="margin:0;"><label for="rl-ac-rest">Pacotes com até</label>
          <select id="rl-ac-rest">${[0, 1, 2, 3, 4, 5].map(n => `<option value="${n}" ${n === 2 ? "selected" : ""}>${n} ${n === 1 ? "sessão restante" : "sessões restantes"}</option>`).join("")}</select></div>
        <div class="campo" style="margin:0;"><label for="rl-ac-de">Mensalidades terminando de</label><input type="date" id="rl-ac-de" /></div>
        <div class="campo" style="margin:0;"><label for="rl-ac-ate">até</label><input type="date" id="rl-ac-ate" /></div>
      </div>
      <div class="rl-corpo"><p class="texto-sm texto-suave">Carregando…</p></div>
    </div>
    <div class="cartao" id="rl-sem-acordo">
      <div class="linha-entre" style="flex-wrap:wrap; gap:8px; margin-bottom:10px;">
        <h3>Sessões sem acordo</h3>
        <button type="button" class="botao botao-secundario botao-sm" data-excel="sem-acordo">📊 Excel</button>
      </div>
      <div class="linha gap-3" style="flex-wrap:wrap; align-items:flex-end; margin-bottom:10px;">
        <div class="campo" style="margin:0;"><label for="rl-sa-de">De</label><input type="date" id="rl-sa-de" value="${hoje.slice(0, 8)}01" max="${hoje}" /></div>
        <div class="campo" style="margin:0;"><label for="rl-sa-ate">Até</label><input type="date" id="rl-sa-ate" value="${hoje}" max="${hoje}" /></div>
        <div class="campo" style="margin:0;"><label for="rl-sa-esp">Especialidade</label><input type="text" id="rl-sa-esp" placeholder="Todas" /></div>
      </div>
      <div class="rl-corpo"><p class="texto-sm texto-suave">Carregando…</p></div>
    </div>`;
    app.innerHTML = renderShellSidebar("#/gestor/financeiro", "Relatórios do Financeiro", conteudo);
    anexarEventosShell();

    const $ = (id) => document.getElementById(id);
    const dados = {};
    const pedidos = {};
    const base = "/financeiro/relatorios";
    const linkFicha = (id, nome) => `<a href="#/gestor/paciente/${encodeURIComponent(id)}">${escapeHtml(nome || "")}</a>`;
    const vazio = (txt) => `<p class="texto-sm texto-suave">${txt}</p>`;
    const erro = (msg) => `<p class="texto-sm">Não foi possível carregar: ${escapeHtml(msg)}</p>`;

    async function buscar(chave, caminho, desenhar) {
        const meu = (pedidos[chave] = (pedidos[chave] || 0) + 1);
        const corpo = document.querySelector(`#${chave} .rl-corpo`);
        try {
            const d = await Api.get(caminho);
            if (meu !== pedidos[chave] || !corpo || !corpo.isConnected) return;
            dados[chave] = d;
            corpo.innerHTML = desenhar(d);
        } catch (err) {
            if (meu === pedidos[chave] && corpo && corpo.isConnected) corpo.innerHTML = erro(err.message);
        }
    }

    function carregarAberto() {
        const q = new URLSearchParams();
        if ($("rl-ab-esp").value.trim()) q.set("especialidade", $("rl-ab-esp").value.trim());
        buscar("rl-aberto", `${base}/em-aberto?${q}`, (d) => {
            if (!d.cobrancas.length) return vazio("Nenhuma cobrança em aberto.");
            const t = d.totais;
            return `<p class="texto-sm" style="margin-bottom:8px;"><strong>${formatarMoeda(t.em_aberto_centavos)}</strong> em aberto
                (${t.quantidade} ${t.quantidade === 1 ? "cobrança" : "cobranças"}) · <strong>${formatarMoeda(t.vencido_centavos)}</strong> vencido</p>
              <div class="tabela-wrap"><table class="tabela">
                <thead><tr><th>Paciente</th><th>Cobrança</th><th>Vencimento</th><th>Situação</th><th>Saldo</th><th>Atraso</th></tr></thead>
                <tbody>${d.cobrancas.map(c => `<tr>
                  <td>${linkFicha(c.paciente_id, c.paciente_nome)}</td><td>${escapeHtml(c.descricao || "")}</td>
                  <td>${formatarData(String(c.vencimento || "").slice(0, 10))}</td><td>${escapeHtml(rotuloStatusCobranca(c.status))}</td>
                  <td style="white-space:nowrap;">${formatarMoeda(c.saldo_centavos)}</td>
                  <td>${c.dias_atraso ? `${c.dias_atraso} ${c.dias_atraso === 1 ? "dia" : "dias"}` : "—"}</td></tr>`).join("")}</tbody>
              </table></div>`;
        });
    }

    function carregarAcabando() {
        const q = new URLSearchParams({ restantes: $("rl-ac-rest").value });
        if ($("rl-ac-de").value) q.set("de", $("rl-ac-de").value);
        if ($("rl-ac-ate").value) q.set("ate", $("rl-ac-ate").value);
        buscar("rl-acabando", `${base}/acabando?${q}`, (d) => {
            if (!$("rl-ac-de").value) $("rl-ac-de").value = d.de;
            if (!$("rl-ac-ate").value) $("rl-ac-ate").value = d.ate;
            const pacotes = !d.pacotes.length ? vazio("Nenhum pacote acabando.") : `
              <div class="tabela-wrap"><table class="tabela">
                <thead><tr><th>Paciente</th><th>Especialidade</th><th>Usadas</th><th>Restantes</th></tr></thead>
                <tbody>${d.pacotes.map(p => `<tr><td>${linkFicha(p.paciente_id, p.paciente_nome)}</td>
                  <td>${escapeHtml(p.especialidade || "")}</td><td>${p.sessoes_usadas} de ${p.sessoes_total}</td>
                  <td><strong>${p.restantes}</strong></td></tr>`).join("")}</tbody></table></div>`;
            const mensalidades = !d.mensalidades.length ? vazio("Nenhuma mensalidade terminando no período.") : `
              <div class="tabela-wrap"><table class="tabela">
                <thead><tr><th>Paciente</th><th>Especialidade</th><th>Valor</th><th>Termina em</th></tr></thead>
                <tbody>${d.mensalidades.map(m => `<tr><td>${linkFicha(m.paciente_id, m.paciente_nome)}</td>
                  <td>${escapeHtml(m.especialidade || "")}</td><td>${formatarMoeda(m.valor_centavos)}</td>
                  <td>${formatarData(String(m.fim || "").slice(0, 10))}</td></tr>`).join("")}</tbody></table></div>`;
            return `<h4 style="margin-bottom:6px;">Pacotes</h4>${pacotes}<h4 style="margin:14px 0 6px;">Mensalidades</h4>${mensalidades}`;
        });
    }

    function carregarSemAcordo() {
        const q = new URLSearchParams({ de: $("rl-sa-de").value || hoje, ate: $("rl-sa-ate").value || hoje });
        if ($("rl-sa-esp").value.trim()) q.set("especialidade", $("rl-sa-esp").value.trim());
        buscar("rl-sem-acordo", `${base}/sem-acordo?${q}`, (d) => {
            if (!d.sessoes.length) return vazio("Nenhuma sessão sem acordo no período.");
            return `<p class="texto-sm" style="margin-bottom:8px;"><strong>${d.totais.quantidade}</strong>
                ${d.totais.quantidade === 1 ? "sessão" : "sessões"} · ${formatarMoeda(d.totais.valor_centavos)} pelo valor dos procedimentos</p>
              <div class="tabela-wrap"><table class="tabela">
                <thead><tr><th>Data/hora</th><th>Paciente</th><th>Profissional</th><th>Especialidade</th><th>Procedimento</th><th>Valor</th></tr></thead>
                <tbody>${d.sessoes.map(s => `<tr><td style="white-space:nowrap;">${formatarDataHoraLocal(s.data_hora)}</td>
                  <td>${linkFicha(s.paciente_id, s.paciente_nome)}</td><td>${escapeHtml(s.profissional_nome || "")}</td>
                  <td>${escapeHtml(s.especialidade || "")}</td><td>${escapeHtml(s.procedimento_nome || "")}</td>
                  <td style="white-space:nowrap;">${formatarMoeda(s.valor_centavos)}</td></tr>`).join("")}</tbody></table></div>`;
        });
    }

    const NOMES = { "em-aberto": ["rl-aberto", "cobrancas-em-aberto"], pacotes: ["rl-acabando", "pacotes-acabando"],
                    mensalidades: ["rl-acabando", "mensalidades-terminando"], "sem-acordo": ["rl-sem-acordo", "sessoes-sem-acordo"] };
    document.querySelectorAll("[data-excel]").forEach(b => b.addEventListener("click", async () => {
        const tipo = b.dataset.excel;
        const d = dados[NOMES[tipo][0]];
        if (!d) return;
        b.disabled = true;
        try {
            await carregarBibliotecaExcel();
            const wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(planilhaRelatorio(tipo, d)), "Relatório");
            XLSX.writeFile(wb, `${NOMES[tipo][1]}-${hoje}.xlsx`);
        } catch (err) { Toast.erro(err.message); }
        finally { b.disabled = false; }
    }));

    let atraso = null;
    const depois = (fn) => () => { clearTimeout(atraso); atraso = setTimeout(fn, 350); };
    $("rl-ab-esp").addEventListener("input", depois(carregarAberto));
    $("rl-sa-esp").addEventListener("input", depois(carregarSemAcordo));
    ["rl-ac-rest", "rl-ac-de", "rl-ac-ate"].forEach(id => $(id).addEventListener("change", carregarAcabando));
    ["rl-sa-de", "rl-sa-ate"].forEach(id => $(id).addEventListener("change", carregarSemAcordo));

    carregarAberto();
    carregarAcabando();
    carregarSemAcordo();
}
