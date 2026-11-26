// ============================================================================
// views/admin_ia.js — Consumo de IA (ditado por voz) por clínica (Admin)
// ============================================================================

async function viewAdminConsumoIA(app) {
    const mesPedido = (new URLSearchParams((location.hash.split("?")[1] || ""))).get("mes");
    const dados = await Api.get("/admin/ia/uso" + (mesPedido ? `?mes=${encodeURIComponent(mesPedido)}` : ""));
    const meses = ultimosMeses(dados.mes);
    if (!meses.includes(dados.mes)) meses.unshift(dados.mes);
    const t = dados.total;
    const conteudo = `
    <div class="cartao" style="margin-bottom:16px;">
      <div class="linha gap-3" style="align-items:flex-end; flex-wrap:wrap;">
        <div class="campo" style="margin:0; min-width:200px;">
          <label for="ia-mes">Mês</label>
          <select id="ia-mes">
            ${meses.map(m => `<option value="${m}" ${m === dados.mes ? "selected" : ""}>${nomeDoMes(m)}</option>`).join("")}
          </select>
        </div>
        <p class="texto-xs texto-suave" style="margin:0; flex:1; min-width:200px;">Custo estimado pelo preço da transcrição por minuto; confira o valor real no painel da OpenAI.</p>
      </div>
    </div>
    <div class="cartao">
      ${dados.clinicas.length ? `
      <div class="tabela-wrap"><table class="tabela" style="min-width:640px;">
        <thead><tr><th>Clínica</th><th>Plano</th><th>Minutos usados</th><th>Ditados</th><th>Falhas</th><th>Custo estimado</th></tr></thead>
        <tbody>
          ${dados.clinicas.map(c => `
          <tr>
            <td>${escapeHtml(c.nome)}</td>
            <td class="texto-sm">${escapeHtml(c.plano_nome)}</td>
            <td class="texto-sm">${c.minutos_usados} de ${c.minutos_cota}</td>
            <td class="texto-sm">${c.ditados}</td>
            <td class="texto-sm">${c.falhas}</td>
            <td class="texto-sm">${formatarUsd(c.custo_estimado_usd)}</td>
          </tr>`).join("")}
          <tr style="font-weight:700;">
            <td colspan="2">Total</td>
            <td class="texto-sm">${t.minutos_usados}</td>
            <td class="texto-sm">${t.ditados}</td>
            <td class="texto-sm">${t.falhas}</td>
            <td class="texto-sm">${formatarUsd(t.custo_estimado_usd)}</td>
          </tr>
        </tbody>
      </table></div>` : `<p class="texto-sm texto-suave">Nenhum uso de IA neste mês.</p>`}
    </div>`;
    app.innerHTML = renderShellSidebar("#/admin/ia", "Consumo de IA", conteudo);
    anexarEventosShell();
    document.getElementById("ia-mes").addEventListener("change", (e) => {
        location.hash = `#/admin/ia?mes=${e.target.value}`;
    });
}
