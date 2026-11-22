// ============================================================================
// views/financeiro_repasse.js — Repasse aos profissionais (Financeiro, etapa 3 — 12/11/2026).
// Só gestor. Duas telas: o relatório (#/gestor/financeiro/repasse: o que cada
// profissional tem a receber, ajustes, PDF, Excel, "Marcar como pago" e os
// fechamentos pagos) e as regras (#/gestor/financeiro/repasse/regras: padrão e
// exceções por procedimento e/ou tipo de acordo). Funções puras em financeiro_util.js.
// `data_hora` das sessões é horário local: use formatarDataHoraLocal.
// ============================================================================

function _repMesAnterior() {
    const h = new Date();
    const de = new Date(h.getFullYear(), h.getMonth() - 1, 1);
    const ate = new Date(h.getFullYear(), h.getMonth(), 0);
    return { de: paraChaveDia(de), ate: paraChaveDia(ate) };
}

const _REP_TIPOS = { avulsa: "Avulsa (por sessão)", mensalidade: "Mensalidade", pacote: "Pacote" };

// ------------------------------------------------------------------ relatório

async function viewRepasseGestor(app) {
    const padrao = _repMesAnterior();
    const filtros = { de: padrao.de, ate: padrao.ate, profissional_id: "", especialidade: "" };
    const hoje = paraChaveDia(new Date());

    let opcoes = { profissionais: [] };
    let especialidades = [];
    try {
        const [regras, org] = await Promise.all([
            Api.get("/financeiro/repasse/regras"), Api.get("/pessoas/organizacao").catch(() => ({}))]);
        opcoes = regras;
        especialidades = org.especialidades || [];
    } catch (err) { Toast.erro(err.message); }

    const conteudo = `
    <div class="linha gap-3" style="margin-bottom:16px; flex-wrap:wrap; align-items:center;">
      <a class="botao botao-texto" href="#/gestor/financeiro">← Voltar às cobranças</a>
      <div style="flex:1;"></div>
      <a class="botao botao-secundario" href="#/gestor/financeiro/repasse/regras">⚙️ Regras do repasse</a>
    </div>
    <div class="cartao" style="margin-bottom:20px;">
      <div class="linha gap-4" style="flex-wrap:wrap; align-items:flex-end;">
        <div class="campo" style="margin:0;"><label for="rp-de">De</label><input type="date" id="rp-de" value="${filtros.de}" max="${hoje}" /></div>
        <div class="campo" style="margin:0;"><label for="rp-ate">Até</label><input type="date" id="rp-ate" value="${filtros.ate}" max="${hoje}" /></div>
        <div class="campo" style="margin:0;"><label for="rp-prof">Profissional</label>
          <select id="rp-prof"><option value="">Todos</option>${(opcoes.profissionais || []).map(p => `<option value="${p.id}">${escapeHtml(p.nome)}</option>`).join("")}</select></div>
        <div class="campo" style="margin:0;"><label for="rp-esp">Especialidade</label>
          <select id="rp-esp"><option value="">Todas</option>${especialidades.map(e => `<option value="${escapeHtml(e)}">${escapeHtml(e)}</option>`).join("")}</select></div>
      </div>
      <p class="texto-xs texto-suave" style="margin-top:10px;">Entram as sessões já pagas pela família e ainda não repassadas, com data até o fim do período (inclusive de meses anteriores). Mudar uma regra depois não altera um repasse já pago.</p>
    </div>
    <div id="rp-cartoes"><div class="cartao"><p class="texto-sm texto-suave">Carregando…</p></div></div>
    <div id="rp-aguardando"></div>
    <div id="rp-ja-pagas"></div>
    <div class="cartao" id="rp-fechamentos" style="margin-top:20px;"><h3 style="margin-bottom:8px;">Fechamentos pagos</h3><p class="texto-sm texto-suave">Carregando…</p></div>`;

    app.innerHTML = renderShellSidebar("#/gestor/financeiro", "Repasse aos profissionais", conteudo);
    anexarEventosShell();

    const $ = (id) => document.getElementById(id);
    const viva = () => !!$("rp-cartoes");
    let dados = null;
    let pedido = 0;

    const query = (extra) => {
        const q = { de: filtros.de, ate: filtros.ate, ...(extra || {}) };
        if (filtros.profissional_id) q.profissional_id = filtros.profissional_id;
        if (filtros.especialidade) q.especialidade = filtros.especialidade;
        return new URLSearchParams(q).toString();
    };

    function linhaSessao(s) {
        return `<tr>
          <td style="white-space:nowrap;">${formatarDataHoraLocal(s.data_hora)}</td>
          <td>${escapeHtml(s.paciente_nome || "")}</td>
          <td>${escapeHtml(s.descricao || "")}</td>
          <td>${s.sessao_numero ? `${s.sessao_numero} de ${s.sessao_total}` : ""}</td>
          <td>${escapeHtml(s.especialidade || "")}</td>
          <td style="white-space:nowrap;">${formatarMoeda(s.base_centavos)}</td>
          <td>${s.profissional_centavos == null ? `<span class="badge badge-alerta">a definir</span>` : escapeHtml(s.regra_rotulo || "")}</td>
          <td style="white-space:nowrap;">${s.profissional_centavos == null ? "—" : `<strong>${formatarMoeda(s.profissional_centavos)}</strong>`}</td>
          <td style="white-space:nowrap;">${s.clinica_centavos == null ? "—" : formatarMoeda(s.clinica_centavos)}</td>
        </tr>`;
    }

    function cartaoProfissional(p) {
        const filtrandoEsp = !!filtros.especialidade;
        const semRegra = !!p.sem_regra;
        const nada = !p.sessoes.length && !p.ajustes.length;
        const bloqueio = semRegra ? "Defina a regra do profissional antes de marcar como pago."
            : filtrandoEsp ? "Tire o filtro de especialidade para marcar como pago (o repasse fecha todas as especialidades do profissional)."
            : nada ? "Nada a pagar." : "";
        return `
      <div class="cartao rp-cartao" data-prof="${p.profissional_id}" style="margin-bottom:16px;">
        <div class="linha-entre" style="gap:12px; flex-wrap:wrap; margin-bottom:8px;">
          <div><h3 style="margin:0;">${escapeHtml(p.nome || "Profissional")}</h3>
            ${p.registro ? `<div class="texto-xs texto-suave">${escapeHtml(p.registro)}</div>` : ""}</div>
          <div style="text-align:right;"><div class="texto-xs texto-suave">A pagar</div>
            <div style="font-size:1.5rem; font-weight:800;">${formatarMoeda(p.a_pagar_centavos)}</div></div>
        </div>
        ${semRegra ? `<p class="texto-sm" style="margin-bottom:8px;"><span class="badge badge-alerta">a definir</span> Algumas sessões estão sem regra de repasse. <a href="#/gestor/financeiro/repasse/regras?prof=${p.profissional_id}">Definir a regra</a></p>` : ""}
        ${p.sessoes.length ? `
        <div class="tabela-wrap" style="margin-bottom:10px;"><table class="tabela" style="min-width:0;">
          <thead><tr><th>Especialidade</th><th>Sessões</th><th>Base</th><th>Profissional</th></tr></thead>
          <tbody>${p.por_especialidade.map(e => `<tr><td>${escapeHtml(e.especialidade || "")}</td><td>${e.quantidade}</td>
            <td>${formatarMoeda(e.base_centavos)}</td><td>${formatarMoeda(e.profissional_centavos)}</td></tr>`).join("")}</tbody>
        </table></div>
        <details open style="margin-bottom:10px;"><summary class="texto-sm" style="cursor:pointer; font-weight:700;">${p.sessoes.length} ${p.sessoes.length === 1 ? "sessão" : "sessões"}</summary>
          <div class="tabela-wrap"><table class="tabela">
            <thead><tr><th>Data/hora</th><th>Paciente</th><th>Procedimento/Acordo</th><th>Sessão</th><th>Especialidade</th><th>Base</th><th>Regra</th><th>Profissional</th><th>Clínica</th></tr></thead>
            <tbody>${p.sessoes.map(linhaSessao).join("")}</tbody>
          </table></div></details>` : `<p class="texto-sm texto-suave" style="margin-bottom:10px;">Nenhuma sessão paga a repassar no período.</p>`}
        <div style="margin-bottom:10px;">
          <div class="linha-entre" style="gap:8px; margin-bottom:4px;">
            <span class="texto-sm" style="font-weight:700;">Ajustes</span>
            <button type="button" class="botao botao-texto botao-sm rp-novo-ajuste" data-prof="${p.profissional_id}" data-nome="${escapeHtml(p.nome || "")}">+ Ajuste</button>
          </div>
          ${p.ajustes.length ? p.ajustes.map(a => `
            <div class="linha-entre" style="padding:6px 0; border-top:1px solid var(--cor-borda); gap:8px;">
              <div class="texto-sm">${escapeHtml(a.descricao)}${a.origem && a.origem !== "manual" ? ` <span class="badge badge-alerta">${escapeHtml(rotuloOrigemAjuste(a.origem))}</span>` : ""}</div>
              <div class="linha gap-2"><strong style="white-space:nowrap;">${a.valor_centavos < 0 ? "−" : "+"}${formatarMoeda(Math.abs(a.valor_centavos))}</strong>
                <button type="button" class="botao-icone rp-del-ajuste" data-id="${a.id}" data-origem="${escapeHtml(a.origem)}" title="${a.origem === "manual" ? "Excluir" : "Dispensar"}" aria-label="${a.origem === "manual" ? "Excluir" : "Dispensar"}" style="width:28px; height:28px; font-size:12px;">🗑️</button></div>
            </div>`).join("") : `<p class="texto-xs texto-suave">Nenhum ajuste pendente.</p>`}
        </div>
        <div class="linha gap-2" style="flex-wrap:wrap; justify-content:flex-end;">
          <button type="button" class="botao botao-secundario rp-pdf" data-prof="${p.profissional_id}">📄 PDF</button>
          <button type="button" class="botao botao-secundario rp-excel" data-prof="${p.profissional_id}">📊 Excel</button>
          <button type="button" class="botao botao-primario rp-pagar" data-prof="${p.profissional_id}" ${bloqueio ? `disabled title="${escapeHtml(bloqueio)}"` : ""}>Marcar como pago</button>
        </div>
        ${bloqueio && !nada ? `<p class="texto-xs texto-suave" style="text-align:right; margin-top:6px;">${escapeHtml(bloqueio)}</p>` : ""}
      </div>`;
    }

    function desenhar(d) {
        const cartoes = $("rp-cartoes");
        cartoes.innerHTML = d.profissionais.length ? d.profissionais.map(cartaoProfissional).join("")
            : `<div class="cartao"><div class="estado-vazio"><div class="emoji">💼</div><p>Nenhum repasse a pagar neste período.</p></div></div>`;

        $("rp-aguardando").innerHTML = !d.aguardando.length ? "" : `
          <details class="cartao" style="margin-bottom:16px;"><summary style="cursor:pointer; font-weight:700;">Aguardando pagamento da família (${d.aguardando.length})</summary>
            <p class="texto-xs texto-suave" style="margin:6px 0;">Sessões do período que a família ainda não pagou (ou só em parte). Entram no repasse quando forem pagas.</p>
            <div class="tabela-wrap"><table class="tabela" style="min-width:0;">
              <thead><tr><th>Data/hora</th><th>Paciente</th><th>Profissional</th><th>Situação</th></tr></thead>
              <tbody>${d.aguardando.map(a => `<tr><td style="white-space:nowrap;">${formatarDataHoraLocal(a.data_hora)}</td>
                <td>${escapeHtml(a.paciente_nome || "")}</td><td>${escapeHtml(a.profissional_nome || "")}</td><td>${escapeHtml(a.motivo || "")}</td></tr>`).join("")}</tbody>
            </table></div></details>`;

        const grupos = new Map();
        d.ja_pagas.forEach(j => {
            const g = grupos.get(j.repasse_id) || { repasse_id: j.repasse_id, pago_em: j.pago_em, quantidade: 0 };
            g.quantidade += 1;
            grupos.set(j.repasse_id, g);
        });
        $("rp-ja-pagas").innerHTML = !grupos.size ? "" : `
          <details class="cartao" style="margin-bottom:16px;"><summary style="cursor:pointer; font-weight:700;">Já pagas (${d.ja_pagas.length})</summary>
            <p class="texto-xs texto-suave" style="margin:6px 0;">Sessões do período que já foram repassadas.</p>
            ${[...grupos.values()].map(g => `<div class="texto-sm" style="padding:4px 0;">${g.quantidade} ${g.quantidade === 1 ? "sessão" : "sessões"} · fechamento #${g.repasse_id} · pago em ${formatarDataHoraLocal(g.pago_em)}</div>`).join("")}
          </details>`;
        ligarCartoes();
    }

    function profDoBotao(b) { return dados.profissionais.find(p => String(p.profissional_id) === b.dataset.prof); }

    function ligarCartoes() {
        document.querySelectorAll(".rp-pdf").forEach(b => b.addEventListener("click", async () => {
            b.disabled = true;
            try { await Api.baixarArquivo(`/financeiro/repasse/pdf?${query({ profissional_id: b.dataset.prof })}`, `repasse-${filtros.de}-a-${filtros.ate}.pdf`); }
            catch (err) { Toast.erro(err.message); }
            finally { b.disabled = false; }
        }));
        document.querySelectorAll(".rp-excel").forEach(b => b.addEventListener("click", async () => {
            const p = profDoBotao(b);
            if (!p) return;
            b.disabled = true;
            try {
                await carregarBibliotecaExcel();
                const wb = XLSX.utils.book_new();
                XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(planilhaRepasse(p, dados.de, dados.ate)), "Repasse");
                const nome = String(p.nome || "profissional").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "").toLowerCase();
                XLSX.writeFile(wb, `repasse-${nome}-${dados.de}-a-${dados.ate}.xlsx`);
            } catch (err) { Toast.erro(err.message); }
            finally { b.disabled = false; }
        }));
        document.querySelectorAll(".rp-novo-ajuste").forEach(b => b.addEventListener("click", () =>
            abrirModalAjusteRepasse(parseInt(b.dataset.prof, 10), b.dataset.nome, carregar)));
        document.querySelectorAll(".rp-del-ajuste").forEach(b => b.addEventListener("click", async () => {
            const automatico = b.dataset.origem !== "manual";
            if (!confirm(automatico ? "Dispensar este ajuste automático? Ele deixa de contar no valor a pagar e não volta." : "Excluir este ajuste?")) return;
            b.disabled = true;
            try { await Api.del(`/financeiro/repasse/ajustes/${b.dataset.id}`); Toast.sucesso(automatico ? "Ajuste dispensado." : "Ajuste excluído."); carregar(); }
            catch (err) { b.disabled = false; Toast.erro(err.message); }
        }));
        document.querySelectorAll(".rp-pagar").forEach(b => b.addEventListener("click", () => {
            const p = profDoBotao(b);
            if (p) abrirConfirmarRepasse(p, dados.de, dados.ate, carregar);
        }));
    }

    async function carregarFechamentos() {
        const alvo = $("rp-fechamentos");
        try {
            const lista = await Api.get(`/financeiro/repasse/fechamentos${filtros.profissional_id ? `?profissional_id=${encodeURIComponent(filtros.profissional_id)}` : ""}`);
            if (!viva()) return;
            alvo.innerHTML = `<h3 style="margin-bottom:8px;">Fechamentos pagos</h3>` + (!lista.length
                ? `<p class="texto-sm texto-suave">Nenhum repasse pago ainda.</p>`
                : `<div class="tabela-wrap"><table class="tabela">
                  <thead><tr><th>Pago em</th><th>Profissional</th><th>Período</th><th>Sessões</th><th>Valor pago</th><th></th></tr></thead>
                  <tbody>${lista.map(r => `<tr>
                    <td style="white-space:nowrap;">${formatarDataHoraLocal(r.pago_em)}</td>
                    <td>${escapeHtml(r.profissional_nome || "")}</td>
                    <td style="white-space:nowrap;">${formatarData(String(r.periodo_de).slice(0, 10))} a ${formatarData(String(r.periodo_ate).slice(0, 10))}</td>
                    <td>${r.quantidade}</td>
                    <td><strong>${formatarMoeda(r.a_pagar_centavos)}</strong></td>
                    <td><div class="linha gap-1" style="justify-content:flex-end;">
                      <button type="button" class="botao botao-texto botao-sm rp-fech-pdf" data-id="${r.id}">📄 PDF</button>
                      <button type="button" class="botao botao-texto botao-sm rp-fech-desfazer" data-id="${r.id}" data-nome="${escapeHtml(r.profissional_nome || "")}" data-valor="${r.a_pagar_centavos}">Desfazer</button>
                    </div></td></tr>`).join("")}</tbody></table></div>`);
            alvo.querySelectorAll(".rp-fech-pdf").forEach(b => b.addEventListener("click", async () => {
                b.disabled = true;
                try { await Api.baixarArquivo(`/financeiro/repasse/fechamentos/${b.dataset.id}/pdf`, `repasse-fechamento-${b.dataset.id}.pdf`); }
                catch (err) { Toast.erro(err.message); }
                finally { b.disabled = false; }
            }));
            alvo.querySelectorAll(".rp-fech-desfazer").forEach(b => b.addEventListener("click", () =>
                abrirDesfazerRepasse(b.dataset.id, b.dataset.nome, parseInt(b.dataset.valor, 10), carregar)));
        } catch (err) { if (viva()) alvo.innerHTML = `<h3 style="margin-bottom:8px;">Fechamentos pagos</h3><p class="texto-sm texto-suave">${escapeHtml(err.message)}</p>`; }
    }

    async function carregar() {
        const meu = ++pedido;
        try {
            const d = await Api.get(`/financeiro/repasse?${query()}`);
            if (meu !== pedido || !viva()) return;
            dados = d;
            desenhar(d);
        } catch (err) {
            if (meu === pedido && viva()) {
                $("rp-cartoes").innerHTML = `<div class="cartao"><p class="texto-sm">Não foi possível carregar o relatório: ${escapeHtml(err.message)}</p></div>`;
                Toast.erro(err.message);
            }
        }
        carregarFechamentos();
    }

    $("rp-de").addEventListener("change", (e) => { filtros.de = e.target.value || padrao.de; carregar(); });
    $("rp-ate").addEventListener("change", (e) => { filtros.ate = e.target.value || padrao.ate; carregar(); });
    $("rp-prof").addEventListener("change", (e) => { filtros.profissional_id = e.target.value; carregar(); });
    $("rp-esp").addEventListener("change", (e) => { filtros.especialidade = e.target.value; carregar(); });
    carregar();
}

// ------------------------------------------------------------------ pop-ups de dinheiro

function abrirModalAjusteRepasse(profissionalId, nome, aoSalvar) {
    const modal = el(`
    <div class="modal-fundo" data-modal-preparado="1" data-modal-formulario="1">
      <div class="modal-caixa">
        <h3 style="margin-bottom:6px;">Ajuste no repasse</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:12px;">${escapeHtml(nome)} · entra no próximo repasse pago. Use valor negativo para descontar.</p>
        <div class="campo"><label for="rp-aj-desc">Descrição</label><input type="text" id="rp-aj-desc" maxlength="200" placeholder="Ex.: Bônus, adiantamento, desconto" /></div>
        <div class="campo"><label for="rp-aj-valor">Valor (R$)</label><input type="text" id="rp-aj-valor" inputmode="decimal" placeholder="0,00 (ex.: -50,00 para descontar)" /></div>
        <div class="linha gap-3" style="justify-content:flex-end; margin-top:12px;">
          <button type="button" class="botao botao-secundario" data-fechar>Voltar</button>
          <button type="button" class="botao botao-primario" id="rp-aj-ok">Salvar ajuste</button>
        </div>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.querySelector("[data-fechar]").addEventListener("click", () => modal.remove());
    modal.querySelector("#rp-aj-ok").addEventListener("click", async (ev) => {
        const descricao = modal.querySelector("#rp-aj-desc").value.trim();
        const bruto = modal.querySelector("#rp-aj-valor").value.trim();
        const negativo = /^[-−]/.test(bruto);
        const v = lerValorReais(bruto.replace(/^[-−+]\s*/, ""));
        if (!descricao) { Toast.erro("Informe a descrição do ajuste."); return; }
        if (!v) { Toast.erro("Informe um valor diferente de zero."); return; }
        ev.target.disabled = true;
        try {
            await Api.post("/financeiro/repasse/ajustes", { profissional_id: profissionalId, descricao, valor_centavos: negativo ? -v : v });
            modal.remove();
            Toast.sucesso("Ajuste salvo.");
            aoSalvar();
        } catch (err) { ev.target.disabled = false; Toast.erro(err.message); }
    });
}

function abrirConfirmarRepasse(p, de, ate, aoSalvar) {
    const modal = el(`
    <div class="modal-fundo" data-modal-preparado="1" data-modal-formulario="1">
      <div class="modal-caixa">
        <h3 style="margin-bottom:6px;">Marcar repasse como pago</h3>
        <p class="texto-sm" style="margin-bottom:6px;">${escapeHtml(p.nome || "")} · ${formatarData(de)} a ${formatarData(ate)}</p>
        <p style="font-size:1.6rem; font-weight:800; margin:8px 0;">${formatarMoeda(p.a_pagar_centavos)}</p>
        <p class="texto-sm texto-suave">${p.sessoes.length} ${p.sessoes.length === 1 ? "sessão" : "sessões"} (${formatarMoeda(p.total_profissional_centavos)}) e ${p.ajustes.length} ${p.ajustes.length === 1 ? "ajuste" : "ajustes"} (${p.total_ajustes_centavos < 0 ? "−" : ""}${formatarMoeda(Math.abs(p.total_ajustes_centavos))}). As sessões saem do relatório e os valores ficam gravados; mudar a regra depois não altera este repasse.</p>
        <div class="linha gap-3" style="justify-content:flex-end; margin-top:12px;">
          <button type="button" class="botao botao-secundario" data-fechar>Voltar</button>
          <button type="button" class="botao botao-primario" id="rp-pg-ok">Confirmar pagamento</button>
        </div>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.querySelector("[data-fechar]").addEventListener("click", () => modal.remove());
    modal.querySelector("#rp-pg-ok").addEventListener("click", async (ev) => {
        ev.target.disabled = true;
        try {
            await Api.post("/financeiro/repasse/fechar", {
                profissional_id: p.profissional_id, de, ate, consulta_ids: p.sessoes.map(s => s.consulta_id),
                // O servidor confere que grava exatamente o valor e os ajustes desta tela.
                a_pagar_centavos: p.a_pagar_centavos, ajuste_ids: p.ajustes.map(a => a.id) });
            modal.remove();
            Toast.sucesso("Repasse marcado como pago.");
            aoSalvar();
        } catch (err) {
            ev.target.disabled = false;
            Toast.erro(err.message);
            if (err.status === 409) { modal.remove(); aoSalvar(); }
        }
    });
}

function abrirDesfazerRepasse(id, nome, valorCentavos, aoSalvar) {
    const modal = el(`
    <div class="modal-fundo" data-modal-preparado="1" data-modal-formulario="1">
      <div class="modal-caixa">
        <h3 style="margin-bottom:6px;">Desfazer fechamento</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:12px;">${escapeHtml(nome)} · ${formatarMoeda(valorCentavos)}. As sessões voltam ao relatório e os ajustes voltam a pendentes. Use para corrigir um engano.</p>
        <div class="campo"><label for="rp-des-motivo">Motivo</label><input type="text" id="rp-des-motivo" maxlength="300" /></div>
        <div class="linha gap-3" style="justify-content:flex-end; margin-top:12px;">
          <button type="button" class="botao botao-secundario" data-fechar>Voltar</button>
          <button type="button" class="botao botao-perigo" id="rp-des-ok">Desfazer fechamento</button>
        </div>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.querySelector("[data-fechar]").addEventListener("click", () => modal.remove());
    modal.querySelector("#rp-des-ok").addEventListener("click", async (ev) => {
        const motivo = modal.querySelector("#rp-des-motivo").value.trim();
        if (!motivo) { Toast.erro("Informe o motivo."); return; }
        ev.target.disabled = true;
        try {
            await Api.post(`/financeiro/repasse/fechamentos/${id}/desfazer`, { motivo });
            modal.remove();
            Toast.sucesso("Fechamento desfeito.");
            aoSalvar();
        } catch (err) { ev.target.disabled = false; Toast.erro(err.message); }
    });
}

// ------------------------------------------------------------------ regras

function _repPctTexto(centesimos) {
    return rotuloRegraRepasse({ modo: "percentual", percentual_centesimos: centesimos }).replace("%", "");
}

function _repValorTexto(centavos) {
    return (centavos / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Linha de regra (padrão ou exceção): modo + valor; a exceção ainda tem procedimento e tipo.
function _repLinhaRegra(regra, procedimentos, excecao) {
    const modo = regra ? regra.modo : "";
    const valor = !regra ? "" : regra.modo === "fixo" ? _repValorTexto(regra.valor_centavos) : _repPctTexto(regra.percentual_centesimos);
    return `
      <div class="linha gap-2 rp-regra" ${excecao ? 'data-excecao="1"' : 'data-padrao="1"'} style="flex-wrap:wrap; align-items:flex-end; padding:6px 0; border-top:1px solid var(--cor-borda);">
        ${excecao ? `
        <div class="campo" style="margin:0;"><label>Procedimento</label>
          <select class="rg-proc"><option value="">Qualquer</option>${procedimentos.map(p => `<option value="${p.id}" ${regra && regra.procedimento_id === p.id ? "selected" : ""}>${escapeHtml(p.nome)}</option>`).join("")}</select></div>
        <div class="campo" style="margin:0;"><label>Tipo de acordo</label>
          <select class="rg-tipo"><option value="">Qualquer</option>${Object.entries(_REP_TIPOS).map(([k, v]) => `<option value="${k}" ${regra && regra.tipo_acordo === k ? "selected" : ""}>${v}</option>`).join("")}</select></div>` : ""}
        <div class="campo" style="margin:0;"><label>${excecao ? "Repasse" : "Regra padrão"}</label>
          <select class="rg-modo">
            ${excecao ? "" : `<option value="" ${!modo ? "selected" : ""}>A definir (sem regra)</option>`}
            <option value="percentual" ${modo === "percentual" ? "selected" : ""}>Percentual (%)</option>
            <option value="fixo" ${modo === "fixo" ? "selected" : ""}>Valor fixo por sessão (R$)</option>
          </select></div>
        <div class="campo" style="margin:0;"><label>Valor</label>
          <input type="text" class="rg-valor" inputmode="decimal" value="${escapeHtml(valor)}" placeholder="0" style="max-width:130px;" ${!modo ? "disabled" : ""} /></div>
        ${excecao ? `<button type="button" class="botao-icone rg-remover" title="Remover exceção" style="width:34px; height:34px;">🗑️</button>` : ""}
      </div>`;
}

async function viewRegrasRepasse(app) {
    const conteudo = `
    <div class="linha gap-3" style="margin-bottom:16px; flex-wrap:wrap; align-items:center;">
      <a class="botao botao-texto" href="#/gestor/financeiro/repasse">← Voltar ao repasse</a>
    </div>
    <p class="texto-sm texto-suave" style="margin-bottom:16px; max-width:760px;">Defina quanto cada profissional recebe por sessão: um percentual do valor da sessão ou um valor fixo. Use "0%" ou "R$ 0,00" para quem atende e não recebe repasse. As exceções valem para um procedimento e/ou um tipo de acordo e vencem a regra padrão (procedimento + tipo, depois procedimento, depois tipo). A base do cálculo (valor do procedimento ou rateio) fica em Configurações &gt; Financeiro.</p>
    <div id="rg-lista"><div class="cartao"><p class="texto-sm texto-suave">Carregando…</p></div></div>`;
    app.innerHTML = renderShellSidebar("#/gestor/financeiro", "Regras do repasse", conteudo);
    anexarEventosShell();

    let dados;
    try { dados = await Api.get("/financeiro/repasse/regras"); }
    catch (err) {
        const alvo = document.getElementById("rg-lista");
        if (alvo) alvo.innerHTML = `<div class="cartao"><p class="texto-sm">Não foi possível carregar as regras: ${escapeHtml(err.message)}</p></div>`;
        Toast.erro(err.message);
        return;
    }
    const lista = document.getElementById("rg-lista");
    if (!lista) return;
    const procs = dados.procedimentos || [];
    if (!dados.profissionais.length) { lista.innerHTML = `<div class="cartao"><div class="estado-vazio"><div class="emoji">💼</div><p>Nenhum profissional ativo.</p></div></div>`; return; }

    lista.innerHTML = dados.profissionais.map(p => {
        const padrao = p.regras.find(r => r.procedimento_id == null && r.tipo_acordo == null) || null;
        const excecoes = p.regras.filter(r => !(r.procedimento_id == null && r.tipo_acordo == null));
        return `
      <div class="cartao rg-cartao" data-prof="${p.id}" style="margin-bottom:16px; max-width:900px;">
        <h3 style="margin-bottom:2px;">${escapeHtml(p.nome)}</h3>
        <p class="texto-xs texto-suave" style="margin-bottom:8px;">${escapeHtml(p.especialidade || "Sem especialidade")} · regra atual: ${escapeHtml(rotuloRegraRepasse(padrao))}</p>
        ${_repLinhaRegra(padrao, procs, false)}
        <div class="rg-excecoes">${excecoes.map(r => _repLinhaRegra(r, procs, true)).join("")}</div>
        <div class="linha-entre" style="margin-top:10px; gap:8px; flex-wrap:wrap;">
          <button type="button" class="botao botao-texto botao-sm rg-nova-excecao">+ Exceção (procedimento ou tipo de acordo)</button>
          <button type="button" class="botao botao-primario rg-salvar">Salvar regras de ${escapeHtml(p.nome)}</button>
        </div>
      </div>`;
    }).join("");

    function ligarLinha(linha) {
        const modo = linha.querySelector(".rg-modo"), valor = linha.querySelector(".rg-valor");
        modo.addEventListener("change", () => {
            valor.disabled = !modo.value;
            valor.placeholder = modo.value === "fixo" ? "0,00" : "0";
            if (!modo.value) valor.value = "";
        });
        const rem = linha.querySelector(".rg-remover");
        if (rem) rem.addEventListener("click", () => linha.remove());
    }
    lista.querySelectorAll(".rp-regra").forEach(ligarLinha);

    lista.querySelectorAll(".rg-cartao").forEach(cartao => {
        cartao.querySelector(".rg-nova-excecao").addEventListener("click", () => {
            const caixa = cartao.querySelector(".rg-excecoes");
            const nova = el(_repLinhaRegra({ modo: "percentual", percentual_centesimos: 0 }, procs, true).trim());
            nova.querySelector(".rg-valor").value = "";
            caixa.appendChild(nova);
            ligarLinha(nova);
        });
        cartao.querySelector(".rg-salvar").addEventListener("click", async (ev) => {
            const regras = [];
            const ler = (linha, excecao) => {
                const modo = linha.querySelector(".rg-modo").value;
                if (!modo) return null;   // padrão "a definir": não grava regra
                const texto = linha.querySelector(".rg-valor").value;
                const regra = { procedimento_id: null, tipo_acordo: null, modo };
                if (excecao) {
                    const proc = linha.querySelector(".rg-proc").value, tipo = linha.querySelector(".rg-tipo").value;
                    if (!proc && !tipo) throw new Error("Escolha o procedimento ou o tipo de acordo de cada exceção.");
                    regra.procedimento_id = proc ? parseInt(proc, 10) : null;
                    regra.tipo_acordo = tipo || null;
                }
                if (modo === "percentual") {
                    const c = lerPercentual(texto);
                    if (c == null) throw new Error("Informe um percentual entre 0 e 100, com até 2 casas.");
                    regra.percentual = c / 100;
                } else {
                    const v = texto.trim() === "0" ? 0 : lerValorReais(texto);
                    if (v == null) throw new Error("Informe o valor fixo em reais.");
                    regra.valor_centavos = v;
                }
                return regra;
            };
            try {
                const padrao = ler(cartao.querySelector("[data-padrao]"), false);
                if (padrao) regras.push(padrao);
                cartao.querySelectorAll("[data-excecao]").forEach(l => regras.push(ler(l, true)));
            } catch (err) { Toast.erro(err.message); return; }
            ev.target.disabled = true;
            try {
                await Api.put(`/financeiro/repasse/regras/${cartao.dataset.prof}`, { regras });
                Toast.sucesso("Regras salvas.");
            } catch (err) { Toast.erro(err.message); }
            finally { ev.target.disabled = false; }
        });
    });

    const alvo = new URLSearchParams((location.hash.split("?")[1]) || "").get("prof");
    const cartaoAlvo = alvo && lista.querySelector(`.rg-cartao[data-prof="${CSS.escape(alvo)}"]`);
    if (cartaoAlvo) { cartaoAlvo.scrollIntoView({ block: "center" }); cartaoAlvo.style.outline = "2px solid var(--cor-marca)"; }
}
