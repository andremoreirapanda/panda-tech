// ============================================================================
// views/financeiro_caixa.js — Fechamento de caixa (Financeiro, etapa 2 — 09/11/2026).
// Só gestor. Relatório de conferência sobre os pagamentos: o que entrou no
// período, os estornos (saída no dia do estorno) e o líquido, por forma de
// pagamento e por quem recebeu; PDF pelo servidor e Excel montado aqui
// (financeiro_util.planilhasCaixa + carregarBibliotecaExcel). Os horários de
// `pago_em`/`estornado_em` já são de Brasília: use formatarDataHoraLocal.
// ============================================================================

async function viewCaixaGestor(app) {
    const hoje = paraChaveDia(new Date());
    const filtros = { de: hoje, ate: hoje, recebido_por: "", forma: "" };

    const conteudo = `
    <div class="linha gap-3" style="margin-bottom:16px; flex-wrap:wrap; align-items:center;">
      <a class="botao botao-texto" href="#/gestor/financeiro">← Voltar às cobranças</a>
      <div style="flex:1;"></div>
      <button type="button" class="botao botao-secundario" id="cx-pdf">📄 Baixar PDF</button>
      <button type="button" class="botao botao-secundario" id="cx-excel">📊 Baixar Excel</button>
    </div>
    <div class="cartao" style="margin-bottom:20px;">
      <div class="linha gap-4" style="flex-wrap:wrap; align-items:flex-end;">
        <div class="campo" style="margin:0;"><label for="cx-de">De</label><input type="date" id="cx-de" value="${hoje}" max="${hoje}" /></div>
        <div class="campo" style="margin:0;"><label for="cx-ate">Até</label><input type="date" id="cx-ate" value="${hoje}" max="${hoje}" /></div>
        <div class="campo" style="margin:0;"><label for="cx-quem">Quem recebeu</label><select id="cx-quem"><option value="">Todos</option></select></div>
        <div class="campo" style="margin:0;"><label for="cx-forma">Forma</label><select id="cx-forma"><option value="">Todas</option></select></div>
        <div class="linha gap-2" style="flex-wrap:wrap;">
          <button type="button" class="botao botao-texto botao-sm cx-atalho" data-atalho="hoje">Hoje</button>
          <button type="button" class="botao botao-texto botao-sm cx-atalho" data-atalho="ontem">Ontem</button>
          <button type="button" class="botao botao-texto botao-sm cx-atalho" data-atalho="mes">Este mês</button>
        </div>
      </div>
    </div>
    <div class="kpi-grade" id="cx-kpis" style="margin-bottom:8px;"></div>
    <p class="texto-xs texto-suave" style="margin-bottom:20px;">Estorno conta como saída no dia em que foi feito; o pagamento continua no dia em que entrou, marcado como estornado.</p>
    <div class="linha gap-4" style="flex-wrap:wrap; align-items:flex-start; margin-bottom:20px;">
      <div class="cartao" id="cx-por-forma" style="flex:1; min-width:min(100%, 440px);"></div>
      <div class="cartao" id="cx-por-quem" style="flex:1; min-width:min(100%, 440px);"></div>
    </div>
    <div class="cartao" id="cx-recebimentos" style="margin-bottom:20px;"><p class="texto-sm texto-suave">Carregando…</p></div>
    <div class="cartao" id="cx-estornos" style="display:none;"></div>`;

    app.innerHTML = renderShellSidebar("#/gestor/financeiro", "Fechamento de caixa", conteudo);
    anexarEventosShell();

    const $ = (id) => document.getElementById(id);
    const viva = () => !!$("cx-recebimentos");
    let dados = null;
    let pedido = 0;

    const query = () => {
        const q = { de: filtros.de, ate: filtros.ate };
        if (filtros.recebido_por) q.recebido_por = filtros.recebido_por;
        if (filtros.forma) q.forma = filtros.forma;
        return new URLSearchParams(q).toString();
    };

    function preencherOpcoes(sel, valores, rotulo, todos) {
        const atual = sel.value;
        const lista = [...new Set([...valores, ...(atual ? [atual] : [])])];
        sel.innerHTML = `<option value="">${todos}</option>` +
            lista.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(rotulo(v))}</option>`).join("");
        sel.value = atual;
    }

    function tabelaGrupo(titulo, itens, rotulo) {
        if (!itens.length) return `<h3 style="margin-bottom:8px;">${titulo}</h3><p class="texto-sm texto-suave">Sem movimento no período.</p>`;
        return `<h3 style="margin-bottom:8px;">${titulo}</h3>
          <div class="tabela-wrap"><table class="tabela" style="min-width:0;">
            <thead><tr><th></th><th>Recebido</th><th>Estornado</th><th>Líquido</th></tr></thead>
            <tbody>${itens.map(i => `<tr><td>${escapeHtml(rotulo(i))}</td><td>${formatarMoeda(i.recebido_centavos)}</td>
              <td>${i.estornado_centavos ? `−${formatarMoeda(i.estornado_centavos)}` : formatarMoeda(0)}</td>
              <td><strong>${formatarMoeda(i.liquido_centavos)}</strong></td></tr>`).join("")}</tbody>
          </table></div>`;
    }

    function desenhar(d) {
        const t = d.totais;
        $("cx-kpis").innerHTML = `
          ${kpiCard("💰", formatarMoeda(t.recebido_centavos), `recebido (${t.quantidade} ${t.quantidade === 1 ? "pagamento" : "pagamentos"})`, "sucesso")}
          ${kpiCard("↩️", t.estornado_centavos ? `−${formatarMoeda(t.estornado_centavos)}` : formatarMoeda(0), "estornado", t.estornado_centavos ? "alerta" : "marca")}
          ${kpiCard("🧾", formatarMoeda(t.liquido_centavos), "líquido", t.liquido_centavos < 0 ? "alerta" : "marca")}`;
        $("cx-por-forma").innerHTML = tabelaGrupo("Por forma de pagamento", d.por_forma, i => rotuloForma(i.forma));
        $("cx-por-quem").innerHTML = tabelaGrupo("Por quem recebeu", d.por_quem, i => i.recebido_por);
        $("cx-recebimentos").innerHTML = !d.recebimentos.length
            ? `<div class="estado-vazio"><div class="emoji">🧾</div><p>Nenhum recebimento no período.</p></div>`
            : `<h3 style="margin-bottom:8px;">Recebimentos</h3>
              <div class="tabela-wrap"><table class="tabela">
                <thead><tr><th>Data/hora</th><th>Paciente</th><th>Cobrança</th><th>Forma</th><th>Quem recebeu</th><th>Valor</th></tr></thead>
                <tbody>${d.recebimentos.map(r => `<tr>
                  <td style="white-space:nowrap;">${formatarDataHoraLocal(r.pago_em)}</td>
                  <td>${escapeHtml(r.paciente_nome || "")}</td>
                  <td>${escapeHtml(r.cobranca_descricao || `#${r.cobranca_id}`)}</td>
                  <td>${escapeHtml(rotuloForma(r.forma))}${r.estornado ? ` <span class="badge badge-alerta">Estornado</span>` : ""}</td>
                  <td>${escapeHtml(r.recebido_por)}</td>
                  <td style="white-space:nowrap;">${r.estornado ? `<s>${formatarMoeda(r.valor_centavos)}</s>` : formatarMoeda(r.valor_centavos)}</td>
                </tr>`).join("")}</tbody>
              </table></div>`;
        const est = $("cx-estornos");
        est.style.display = d.estornos.length ? "" : "none";
        est.innerHTML = !d.estornos.length ? "" : `<h3 style="margin-bottom:8px;">Estornos</h3>
          <div class="tabela-wrap"><table class="tabela">
            <thead><tr><th>Data do estorno</th><th>Paciente</th><th>Cobrança</th><th>Forma</th><th>Motivo</th><th>Valor</th></tr></thead>
            <tbody>${d.estornos.map(r => `<tr>
              <td style="white-space:nowrap;">${formatarDataHoraLocal(r.estornado_em)}</td>
              <td>${escapeHtml(r.paciente_nome || "")}</td>
              <td>${escapeHtml(r.cobranca_descricao || `#${r.cobranca_id}`)}<div class="texto-xs texto-suave">pago em ${formatarDataHoraLocal(r.pago_em)}</div></td>
              <td>${escapeHtml(rotuloForma(r.forma))}</td>
              <td>${escapeHtml(r.motivo || "")}</td>
              <td style="white-space:nowrap;">−${formatarMoeda(r.valor_centavos)}</td>
            </tr>`).join("")}</tbody>
          </table></div>`;
        preencherOpcoes($("cx-quem"), d.opcoes.quem, v => v, "Todos");
        preencherOpcoes($("cx-forma"), d.opcoes.formas, rotuloForma, "Todas");
    }

    async function carregar() {
        const meu = ++pedido;
        try {
            const d = await Api.get(`/financeiro/caixa?${query()}`);
            if (meu !== pedido || !viva()) return;
            dados = d;
            desenhar(d);
        } catch (err) {
            if (meu === pedido && viva()) Toast.erro(err.message);
        }
    }

    function aplicarPeriodo(de, ate) {
        filtros.de = de; filtros.ate = ate;
        $("cx-de").value = de; $("cx-ate").value = ate;
        carregar();
    }

    $("cx-de").addEventListener("change", (e) => { filtros.de = e.target.value || hoje; carregar(); });
    $("cx-ate").addEventListener("change", (e) => { filtros.ate = e.target.value || hoje; carregar(); });
    $("cx-quem").addEventListener("change", (e) => { filtros.recebido_por = e.target.value; carregar(); });
    $("cx-forma").addEventListener("change", (e) => { filtros.forma = e.target.value; carregar(); });
    document.querySelectorAll(".cx-atalho").forEach(b => b.addEventListener("click", () => {
        const p = periodoAtalhoCaixa(b.dataset.atalho, hoje);
        aplicarPeriodo(p.de, p.ate);
    }));

    $("cx-pdf").addEventListener("click", async (ev) => {
        ev.target.disabled = true;
        try { await Api.baixarArquivo(`/financeiro/caixa/pdf?${query()}`, `caixa-${filtros.de}-a-${filtros.ate}.pdf`); }
        catch (err) { Toast.erro(err.message); }
        finally { ev.target.disabled = false; }
    });
    $("cx-excel").addEventListener("click", async (ev) => {
        if (!dados) return;
        ev.target.disabled = true;
        try {
            await carregarBibliotecaExcel();
            const wb = XLSX.utils.book_new();
            const planilhas = planilhasCaixa(dados);
            Object.keys(planilhas).forEach(nome => XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(planilhas[nome]), nome));
            XLSX.writeFile(wb, `caixa-${dados.de}-a-${dados.ate}.xlsx`);
        } catch (err) { Toast.erro(err.message); }
        finally { ev.target.disabled = false; }
    });

    carregar();
}
