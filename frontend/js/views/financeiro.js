// ============================================================================
// views/financeiro.js — Financeiro (Gestor) + Indicadores
// ============================================================================

// ---------------------------------------------------------------- Financeiro (Gestor e Secretária)
// Cobranças da clínica (07/11/2026): KPIs, filtros, "Para conferir", lista com
// Receber/Pix/detalhes e, só para o gestor, o cartão "Pendências".

function financeiroHabilitado() {
    const org = Sessao.usuario && Sessao.usuario.organizacao;
    return !!(org && (org.modulos_habilitados || []).includes("financeiro"));
}

function _finHojeChave() { return paraChaveDia(new Date()); }

function _finMesAtual() {
    const h = _finHojeChave();
    const [a, m] = h.split("-").map(Number);
    const ultimo = new Date(a, m, 0).getDate();
    return { de: `${a}-${String(m).padStart(2, "0")}-01`, ate: `${a}-${String(m).padStart(2, "0")}-${String(ultimo).padStart(2, "0")}` };
}

function _finBadgeStatus(c) {
    const cor = c.status === "pago" ? "sucesso" : c.status === "vencido" ? "alerta"
        : c.status === "cancelado" ? "neutro" : c.status === "rascunho" ? "marca" : "aviso";
    return `<span class="badge badge-${cor}">${escapeHtml(rotuloStatusCobranca(c.status, c.aberta))}</span>`;
}

function _finReais(centavos) {
    return (centavos / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Pop-up simples de motivo (estorno, cancelamento, "não cobrar").
function finPedirMotivo({ titulo, texto, botao, aoConfirmar }) {
    const modal = el(`
    <div class="modal-fundo" data-modal-preparado="1">
      <div class="modal-caixa">
        <h3 style="margin-bottom:6px;">${escapeHtml(titulo)}</h3>
        ${texto ? `<p class="texto-sm texto-suave" style="margin-bottom:12px;">${escapeHtml(texto)}</p>` : ""}
        <div class="campo"><label>Motivo ${ASTERISCO_OBRIGATORIO}</label><textarea id="fin-motivo" rows="3" maxlength="200" style="width:100%;"></textarea></div>
        <div class="linha gap-3" style="justify-content:flex-end; margin-top:12px;">
          <button type="button" class="botao botao-secundario" data-fechar>Voltar</button>
          <button type="button" class="botao botao-primario" id="fin-motivo-ok">${escapeHtml(botao)}</button>
        </div>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.querySelector("[data-fechar]").addEventListener("click", () => modal.remove());
    modal.querySelector("#fin-motivo-ok").addEventListener("click", async (ev) => {
        const motivo = modal.querySelector("#fin-motivo").value.trim();
        if (!motivo) { Toast.erro("Informe o motivo."); return; }
        ev.target.disabled = true;
        try {
            await aoConfirmar(motivo);
            modal.remove();
        } catch (err) {
            ev.target.disabled = false;
            Toast.erro(err.message);
        }
    });
}

// Pop-up "Receber": valor (padrão: o saldo), forma e data.
function finAbrirReceber(c, aoSalvar) {
    // Fora do rascunho automático: o título é igual para toda cobrança e restauraria valor errado.
    const modal = el(`
    <div class="modal-fundo" data-modal-preparado="1" data-modal-formulario="1">
      <div class="modal-caixa">
        <h3 style="margin-bottom:4px;">Receber pagamento</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:14px;">${escapeHtml(c.paciente_nome)} · ${escapeHtml(c.descricao || "")}<br />Saldo: <strong>${formatarMoeda(c.saldo_centavos)}</strong></p>
        <div class="campo"><label>Valor recebido (R$)</label><input type="text" id="fin-rec-valor" inputmode="decimal" value="${_finReais(c.saldo_centavos)}" /></div>
        <div class="campo"><label>Forma de pagamento</label>
          <select id="fin-rec-forma">
            ${["pix", "dinheiro", "cartao_credito", "cartao_debito", "transferencia"].map(f => `<option value="${f}">${escapeHtml(rotuloForma(f))}</option>`).join("")}
          </select>
        </div>
        <div class="campo"><label>Data do pagamento</label><input type="date" id="fin-rec-data" value="${_finHojeChave()}" max="${_finHojeChave()}" /></div>
        <div class="linha gap-3" style="justify-content:flex-end; margin-top:12px;">
          <button type="button" class="botao botao-secundario" data-fechar>Voltar</button>
          <button type="button" class="botao botao-primario" id="fin-rec-ok">Registrar</button>
        </div>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.querySelector("[data-fechar]").addEventListener("click", () => modal.remove());
    modal.querySelector("#fin-rec-ok").addEventListener("click", async (ev) => {
        const valor = lerValorReais(modal.querySelector("#fin-rec-valor").value);
        if (!valor || valor <= 0) { Toast.erro("Informe um valor maior que zero."); return; }
        if (valor > c.saldo_centavos) { Toast.erro("O valor é maior que o saldo da cobrança."); return; }
        const corpo = { valor_centavos: valor, forma: modal.querySelector("#fin-rec-forma").value };
        const data = modal.querySelector("#fin-rec-data").value;
        if (data) corpo.data = data;
        ev.target.disabled = true;
        try {
            const r = await Api.post(`/financeiro/cobranca/${c.id}/pagar`, corpo);
            modal.remove();
            Toast.sucesso(r.status === "pago" ? "Pagamento registrado: cobrança paga!" : "Pagamento parcial registrado.");
            aoSalvar();
        } catch (err) {
            ev.target.disabled = false;
            Toast.erro(err.message);
        }
    });
}

// Detalhes: itens, pagamentos e (gestor) estornar / cancelar / resolver revisão.
function finAbrirDetalhes(c, ehGestor, aoMudar) {
    const itens = (c.itens || []).map(i => `
        <tr><td>${formatarDataHoraLocal(i.data_hora)}</td><td>${escapeHtml(i.procedimento_nome || "Sessão")}</td><td>${formatarMoeda(i.valor_centavos)}</td></tr>`).join("");
    const pagtos = (c.pagamentos || []).map(p => `
        <tr>
          <td>${formatarData(String(p.pago_em || "").slice(0, 10))}</td>
          <td>${escapeHtml(rotuloForma(p.forma))}</td>
          <td>${formatarMoeda(p.valor_centavos)}${p.estornado_em ? ` <span class="badge badge-neutro">Estornado</span>` : ""}</td>
          <td class="texto-xs texto-suave">${escapeHtml(p.recebido_por_nome || "")}${p.estorno_motivo ? ` · ${escapeHtml(p.estorno_motivo)}` : ""}</td>
          <td>${ehGestor && !p.estornado_em ? `<button type="button" class="botao botao-texto botao-sm fin-estornar" data-id="${p.id}">Estornar</button>` : ""}</td>
        </tr>`).join("");
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa modal-grande">
        <div class="linha-entre" style="margin-bottom:6px;">
          <h3>${escapeHtml(c.paciente_nome)} · ${escapeHtml(c.descricao || "")}</h3>
          ${_finBadgeStatus(c)}
        </div>
        <p class="texto-sm texto-suave" style="margin-bottom:12px;">
          Vencimento ${formatarData(String(c.vencimento || "").slice(0, 10))} · Valor ${formatarMoeda(c.valor_centavos)}
          ${c.desconto_centavos ? ` · Desconto ${formatarMoeda(c.desconto_centavos)}${c.desconto_motivo ? ` (${escapeHtml(c.desconto_motivo)})` : ""}` : ""}
          · A pagar ${formatarMoeda(c.a_pagar_centavos)} · Pago ${formatarMoeda(c.pago_centavos)}
        </p>
        ${c.revisar ? `<div class="cartao-flat" style="margin-bottom:12px;"><strong>⚠️ Revisar:</strong> ${escapeHtml(c.revisar_motivo || "uma sessão mudou depois da cobrança.")}
            ${ehGestor ? `<button type="button" class="botao botao-secundario botao-sm" id="fin-resolver" style="margin-left:8px;">Marcar como resolvido</button>` : ""}</div>` : ""}
        <h4 style="margin:8px 0;">Sessões</h4>
        ${itens ? `<div class="tabela-wrap"><table class="tabela"><thead><tr><th>Data</th><th>Procedimento</th><th>Valor</th></tr></thead><tbody>${itens}</tbody></table></div>`
            : `<p class="texto-sm texto-suave">Sem sessões ligadas a esta cobrança.</p>`}
        <h4 style="margin:14px 0 8px;">Pagamentos</h4>
        ${pagtos ? `<div class="tabela-wrap"><table class="tabela"><thead><tr><th>Data</th><th>Forma</th><th>Valor</th><th>Recebido por</th><th></th></tr></thead><tbody>${pagtos}</tbody></table></div>`
            : `<p class="texto-sm texto-suave">Nenhum pagamento registrado.</p>`}
        <div class="linha gap-3" style="justify-content:space-between; margin-top:16px;">
          <div>${ehGestor && c.status !== "cancelado" ? `<button type="button" class="botao botao-texto" id="fin-cancelar" style="color:var(--cor-alerta);">Cancelar cobrança</button>` : ""}</div>
          <button type="button" class="botao botao-secundario" data-fechar>Fechar</button>
        </div>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.querySelector("[data-fechar]").addEventListener("click", () => modal.remove());
    modal.querySelectorAll(".fin-estornar").forEach(btn => btn.addEventListener("click", () => {
        finPedirMotivo({
            titulo: "Estornar pagamento", texto: "O valor volta para o saldo da cobrança.", botao: "Estornar",
            aoConfirmar: async (motivo) => {
                await Api.post(`/financeiro/pagamento/${btn.dataset.id}/estornar`, { motivo });
                Toast.sucesso("Pagamento estornado.");
                modal.remove();
                aoMudar();
            },
        });
    }));
    const cancelar = modal.querySelector("#fin-cancelar");
    if (cancelar) cancelar.addEventListener("click", () => {
        finPedirMotivo({
            titulo: "Cancelar cobrança", texto: "As sessões dela não serão cobradas.", botao: "Cancelar cobrança",
            aoConfirmar: async (motivo) => {
                await Api.post(`/financeiro/cobranca/${c.id}/cancelar`, { motivo });
                Toast.sucesso("Cobrança cancelada.");
                modal.remove();
                aoMudar();
            },
        });
    });
    const resolver = modal.querySelector("#fin-resolver");
    if (resolver) resolver.addEventListener("click", async () => {
        try {
            await Api.post(`/financeiro/cobranca/${c.id}/resolver-revisao`, {});
            Toast.sucesso("Marcada como resolvida.");
            modal.remove();
            aoMudar();
        } catch (err) { Toast.erro(err.message); }
    });
}

// "Criar acordo" das Pendências: abre o pop-up do acordo (financeiro_ficha.js) e atualiza a tela ao salvar.
function abrirCriarAcordo(pacienteId, especialidade, aoSalvar) {
    abrirModalAcordo(parseInt(pacienteId, 10), { especialidade, aoSalvar });
}

// Informar o valor de uma sessão sem preço (decisão "valor").
function finInformarValor(consultaId, aoSalvar) {
    const modal = el(`
    <div class="modal-fundo" data-modal-preparado="1" data-modal-formulario="1">
      <div class="modal-caixa">
        <h3 style="margin-bottom:12px;">Informar valor da sessão</h3>
        <div class="campo"><label>Valor (R$)</label><input type="text" id="fin-val" inputmode="decimal" placeholder="0,00" /></div>
        <div class="linha gap-3" style="justify-content:flex-end; margin-top:12px;">
          <button type="button" class="botao botao-secundario" data-fechar>Voltar</button>
          <button type="button" class="botao botao-primario" id="fin-val-ok">Salvar</button>
        </div>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.querySelector("[data-fechar]").addEventListener("click", () => modal.remove());
    modal.querySelector("#fin-val-ok").addEventListener("click", async (ev) => {
        const v = lerValorReais(modal.querySelector("#fin-val").value);
        if (!v || v <= 0) { Toast.erro("Informe um valor maior que zero."); return; }
        ev.target.disabled = true;
        try {
            await Api.post(`/financeiro/sessoes/${consultaId}/decisao`, { decisao: "valor", valor_centavos: v });
            modal.remove();
            Toast.sucesso("Valor informado.");
            aoSalvar();
        } catch (err) { ev.target.disabled = false; Toast.erro(err.message); }
    });
}

function _finLinhaSessao(s, acoes) {
    return `
      <div class="linha-entre" style="padding:8px 0; border-top:1px solid var(--cor-borda); gap:10px; flex-wrap:wrap;">
        <div>
          <strong>${escapeHtml(s.paciente_nome)}</strong>
          <span class="texto-sm texto-suave"> · ${formatarDataHoraLocal(s.data_hora)} · ${escapeHtml(s.especialidade || "Geral")}${s.profissional_nome ? ` · ${escapeHtml(s.profissional_nome)}` : ""}${s.procedimento_valor_centavos ? ` · ${formatarMoeda(s.procedimento_valor_centavos)}` : ""}</span>
        </div>
        <div class="linha gap-2" style="flex-wrap:wrap;">${acoes}</div>
      </div>`;
}

function finRenderPendencias(p) {
    const secao = (titulo, qtd, corpo) => `
      <details class="fin-pend-secao" ${qtd ? "open" : ""} style="margin-bottom:10px;">
        <summary style="cursor:pointer; font-weight:700;">${titulo} (${qtd})</summary>
        ${qtd ? corpo : `<p class="texto-sm texto-suave" style="margin:6px 0;">Nada por aqui.</p>`}
      </details>`;
    const semAcordo = p.sem_acordo.map(s => _finLinhaSessao(s, `
        <button type="button" class="botao botao-secundario botao-sm fin-criar-acordo" data-paciente="${s.paciente_id}" data-esp="${escapeHtml(s.especialidade || "Geral")}">Criar acordo</button>
        <button type="button" class="botao botao-secundario botao-sm fin-cobrar-avulsa" data-paciente="${s.paciente_id}" data-consulta="${s.consulta_id}">Cobrar como avulsa</button>
        <button type="button" class="botao botao-secundario botao-sm fin-informar-valor" data-consulta="${s.consulta_id}">Informar valor</button>
        <button type="button" class="botao botao-texto botao-sm fin-nao-cobrar" data-consulta="${s.consulta_id}">Não cobrar</button>`)).join("");
    const semValor = p.sem_valor.map(s => _finLinhaSessao(s, `
        <button type="button" class="botao botao-secundario botao-sm fin-informar-valor" data-consulta="${s.consulta_id}">Informar valor</button>
        <button type="button" class="botao botao-texto botao-sm fin-nao-cobrar" data-consulta="${s.consulta_id}">Não cobrar</button>`)).join("");
    const pacotes = p.pacotes_acabando.map(a => `
      <div class="linha-entre" style="padding:8px 0; border-top:1px solid var(--cor-borda); gap:10px; flex-wrap:wrap;">
        <span><strong>${escapeHtml(a.paciente_nome)}</strong> <span class="texto-sm texto-suave">· ${escapeHtml(a.especialidade)} · ${a.sessoes_usadas} de ${a.sessoes_total} sessões${a.restantes === 0 ? " (acabou)" : ` (restam ${a.restantes})`}</span></span>
        <button type="button" class="botao botao-secundario botao-sm fin-criar-acordo" data-paciente="${a.paciente_id}" data-esp="${escapeHtml(a.especialidade)}">Criar acordo</button>
      </div>`).join("");
    const mens = p.mensalidades_terminando.map(a => `
      <div style="padding:8px 0; border-top:1px solid var(--cor-borda);"><strong>${escapeHtml(a.paciente_nome)}</strong>
        <span class="texto-sm texto-suave"> · ${escapeHtml(a.especialidade)} · ${formatarMoeda(a.valor_centavos)} · termina em ${formatarData(String(a.fim).slice(0, 10))}</span></div>`).join("");
    const venc = p.vencidas.map(c => `
      <div style="padding:8px 0; border-top:1px solid var(--cor-borda);"><strong>${escapeHtml(c.paciente_nome)}</strong>
        <span class="texto-sm texto-suave"> · ${escapeHtml(c.descricao || "")} · venceu em ${formatarData(String(c.vencimento).slice(0, 10))} · saldo ${formatarMoeda(c.saldo_centavos)}</span></div>`).join("");
    const rev = p.revisar.map(c => `
      <div class="linha-entre" style="padding:8px 0; border-top:1px solid var(--cor-borda); gap:10px; flex-wrap:wrap;">
        <span><strong>${escapeHtml(c.paciente_nome)}</strong> <span class="texto-sm texto-suave">· ${escapeHtml(c.descricao || "")} · ${escapeHtml(c.revisar_motivo || "revisar")}</span></span>
        <button type="button" class="botao botao-secundario botao-sm fin-resolver" data-id="${c.id}">Marcar como resolvido</button>
      </div>`).join("");
    return `
      <h3 style="margin-bottom:12px;">Pendências</h3>
      ${secao("Sessões sem acordo", p.sem_acordo.length, semAcordo)}
      ${secao("Sessões sem valor", p.sem_valor.length, semValor)}
      ${secao("Pacotes acabando", p.pacotes_acabando.length, pacotes)}
      ${secao("Mensalidades terminando este mês", p.mensalidades_terminando.length, mens)}
      ${secao("Cobranças vencidas", p.vencidas.length, venc)}
      ${secao("Cobranças a revisar", p.revisar.length, rev)}`;
}

async function viewFinanceiroGestor(app) {
    const papel = Sessao.usuario.papel;
    const ehGestor = papel === "gestor" || papel === "admin_master";
    const rotaAtiva = papel === "secretaria" ? "#/secretaria/financeiro" : "#/gestor/financeiro";
    const [pacientes, orgInfo] = await Promise.all([
        Api.get("/pessoas/pacientes"), Api.get("/pessoas/organizacao").catch(() => ({})),
    ]);
    const especialidades = orgInfo.especialidades || [];
    const filtros = { ..._finMesAtual(), status: "", paciente_id: "", especialidade: "" };

    const conteudo = `
    <div class="kpi-grade" id="fin-kpis" style="margin-bottom:20px;"></div>
    <div class="cartao" style="margin-bottom:20px;">
      <div class="linha gap-4" style="flex-wrap:wrap; align-items:flex-end;">
        <div class="campo" style="margin:0;"><label>De (vencimento)</label><input type="date" id="fin-de" value="${filtros.de}" /></div>
        <div class="campo" style="margin:0;"><label>Até</label><input type="date" id="fin-ate" value="${filtros.ate}" /></div>
        <div class="campo" style="margin:0;"><label>Situação</label>
          <select id="fin-status">
            <option value="">Todas</option>
            <option value="rascunho">Em andamento</option>
            <option value="pendente">Em aberto</option>
            <option value="parcial">Pago em parte</option>
            <option value="vencido">Vencido</option>
            <option value="pago">Pago</option>
            <option value="cancelado">Cancelado</option>
          </select>
        </div>
        <div class="campo" style="margin:0;"><label>Especialidade</label>
          <select id="fin-esp">
            <option value="">Todas</option>
            ${especialidades.map(e => `<option value="${escapeHtml(e)}">${escapeHtml(e)}</option>`).join("")}
          </select>
        </div>
        <div id="fin-busca" style="flex:1; min-width:220px;">${renderBuscaPaciente("fin-paciente")}</div>
      </div>
    </div>
    <div id="fin-conferir"></div>
    ${ehGestor ? `<div class="cartao" id="fin-pendencias" style="margin-bottom:20px;"><p class="texto-sm texto-suave">Carregando pendências…</p></div>` : ""}
    <div class="cartao" id="fin-lista"><p class="texto-sm texto-suave">Carregando…</p></div>`;

    app.innerHTML = renderShellSidebar(rotaAtiva, "Financeiro", conteudo);
    anexarEventosShell();

    const rotuloBusca = document.querySelector("#fin-busca label");
    if (rotuloBusca) rotuloBusca.textContent = "Paciente";
    ligarBuscaPaciente(document.getElementById("fin-busca"), "fin-paciente", pacientes);

    // Vindo da ficha ("Ver em Cobranças"): filtra pelo paciente e mostra todo o período.
    const pacienteDaUrl = parseInt(new URLSearchParams(location.hash.split("?")[1] || "").get("paciente"), 10);
    const pacienteFiltrado = pacienteDaUrl ? pacientes.find(p => p.id === pacienteDaUrl) : null;
    if (pacienteFiltrado) {
        filtros.paciente_id = String(pacienteFiltrado.id);
        filtros.de = ""; filtros.ate = "";
        document.getElementById("fin-de").value = ""; document.getElementById("fin-ate").value = "";
        document.getElementById("fin-paciente").value = String(pacienteFiltrado.id);
        document.getElementById("fin-paciente-busca").value = pacienteFiltrado.nome;
    }

    const consulta = (extra) => Api.get(`/financeiro/cobrancas?${new URLSearchParams(extra).toString()}`);
    const viva = () => !!document.getElementById("fin-lista");   // usuário pode ter saído da tela

    async function carregarCobrancas() {
        const q = {};
        if (filtros.de) q.de = filtros.de;
        if (filtros.ate) q.ate = filtros.ate;
        if (filtros.status) q.status = filtros.status;
        if (filtros.paciente_id) q.paciente_id = filtros.paciente_id;
        if (filtros.especialidade) q.especialidade = filtros.especialidade;
        const [dados, rascunhos] = await Promise.all([consulta(q), consulta({ status: "rascunho" })]);
        if (!viva()) return;
        const t = dados.totais;
        document.getElementById("fin-kpis").innerHTML = `
          ${kpiCard("💰", formatarMoeda(t.recebido_centavos), "recebido no período", "sucesso")}
          ${kpiCard("⏳", formatarMoeda(t.em_aberto_centavos), "em aberto", "acento")}
          ${kpiCard("🔴", formatarMoeda(t.vencido_centavos), "vencido", t.vencido_centavos > 0 ? "alerta" : "sucesso")}`;
        // Clínica sem especialidades cadastradas: oferece as que aparecem nas cobranças.
        const selEsp = document.getElementById("fin-esp");
        if (selEsp && !filtros.especialidade) {
            const tem = new Set([...selEsp.options].map(o => o.value.toLowerCase()));
            [...dados.cobrancas, ...rascunhos.cobrancas].forEach(c => {
                if (c.especialidade && !tem.has(c.especialidade.toLowerCase())) {
                    tem.add(c.especialidade.toLowerCase());
                    selEsp.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(c.especialidade)}">${escapeHtml(c.especialidade)}</option>`);
                }
            });
        }
        desenharConferir(rascunhos.cobrancas.filter(c => c.status === "rascunho" && !c.aberta));
        desenharLista(dados.cobrancas.filter(c => !(c.status === "rascunho" && !c.aberta)));
    }

    async function carregarPendencias() {
        if (!ehGestor) return;
        try {
            const p = await Api.get("/financeiro/pendencias");
            const alvo = document.getElementById("fin-pendencias");
            if (!alvo) return;
            alvo.innerHTML = finRenderPendencias(p);
            ligarPendencias(alvo);
        } catch (err) {
            const alvo = document.getElementById("fin-pendencias");
            if (alvo) alvo.innerHTML = `<p class="texto-sm texto-suave">Não foi possível carregar as pendências.</p>`;
        }
    }

    async function recarregar() {
        try { await Promise.all([carregarCobrancas(), carregarPendencias()]); }
        catch (err) { if (viva()) Toast.erro(err.message); }
    }

    function desenharConferir(lista) {
        const alvo = document.getElementById("fin-conferir");
        if (!lista.length) { alvo.innerHTML = ""; return; }
        alvo.innerHTML = `
        <div class="cartao" style="margin-bottom:20px; border-color:var(--cor-marca);">
          <h3 style="margin-bottom:4px;">Para conferir (${lista.length})</h3>
          <p class="texto-xs texto-suave" style="margin-bottom:12px;">O período terminou. Confira as sessões, aplique desconto se precisar e libere para a família.</p>
          ${lista.map(c => `
            <div class="cartao-flat fin-conferir-item" data-id="${c.id}" style="margin-bottom:12px;">
              <div class="linha-entre" style="flex-wrap:wrap; gap:8px;">
                <strong>${escapeHtml(c.paciente_nome)} · ${escapeHtml(c.descricao || "")}</strong>
                <span class="texto-sm texto-suave">Valor ${formatarMoeda(c.valor_centavos)}</span>
              </div>
              ${(c.itens || []).map(i => `
                <label class="linha gap-2" style="padding:4px 0; align-items:center;">
                  <input type="checkbox" class="fin-tirar" value="${i.id}" />
                  <span class="texto-sm">${formatarDataHoraLocal(i.data_hora)} · ${escapeHtml(i.procedimento_nome || "Sessão")} · ${formatarMoeda(i.valor_centavos)}</span>
                  <span class="texto-xs texto-suave">(marque para tirar)</span>
                </label>`).join("")}
              <div class="linha gap-3" style="flex-wrap:wrap; align-items:flex-end; margin-top:8px;">
                <div class="campo" style="margin:0;"><label>Desconto (R$)</label><input type="text" class="fin-desc" inputmode="decimal" value="${c.desconto_centavos ? _finReais(c.desconto_centavos) : ""}" placeholder="0,00" style="max-width:130px;" /></div>
                <div class="campo" style="margin:0; flex:1; min-width:180px;"><label>Motivo do desconto</label><input type="text" class="fin-desc-motivo" maxlength="200" value="${escapeHtml(c.desconto_motivo || "")}" /></div>
                <button type="button" class="botao botao-primario botao-sm fin-liberar">Liberar</button>
              </div>
            </div>`).join("")}
        </div>`;
        alvo.querySelectorAll(".fin-conferir-item").forEach(box => {
            box.querySelector(".fin-liberar").addEventListener("click", async (ev) => {
                const btn = ev.target;
                const descTxt = box.querySelector(".fin-desc").value.trim();
                const desconto = descTxt ? lerValorReais(descTxt) : 0;
                if (desconto === null) { Toast.erro("Desconto inválido."); return; }
                const motivo = box.querySelector(".fin-desc-motivo").value.trim();
                if (desconto > 0 && !motivo) { Toast.erro("Informe o motivo do desconto."); return; }
                const tirar = [...box.querySelectorAll(".fin-tirar:checked")].map(x => parseInt(x.value, 10));
                btn.disabled = true;
                try {
                    const r = await Api.put(`/financeiro/cobranca/${box.dataset.id}/conferir`,
                        { desconto_centavos: desconto, desconto_motivo: motivo, remover_itens: tirar });
                    if (r.status === "cancelado") {
                        Toast.info("Todas as sessões foram retiradas: a cobrança foi cancelada.");
                    } else {
                        const l = await Api.post(`/financeiro/cobranca/${box.dataset.id}/liberar`, {});
                        Toast.sucesso(l.status === "pago" ? "Liberada (desconto total: já está paga)." : "Cobrança liberada para a família.");
                    }
                    recarregar();
                } catch (err) {
                    btn.disabled = false;
                    Toast.erro(err.message);
                }
            });
        });
    }

    function desenharLista(lista) {
        const alvo = document.getElementById("fin-lista");
        if (!lista.length) {
            alvo.innerHTML = `<div class="estado-vazio"><div class="emoji">💳</div><p>Nenhuma cobrança neste período.</p></div>`;
            return;
        }
        alvo.innerHTML = `
        <div class="tabela-wrap"><table class="tabela">
          <thead><tr><th>Paciente</th><th>Cobrança</th><th>Vencimento</th><th>A pagar</th><th>Pago</th><th>Situação</th><th></th></tr></thead>
          <tbody>
            ${lista.map(c => {
                const recebivel = ["pendente", "parcial", "vencido"].includes(c.status);
                return `
              <tr>
                <td>${escapeHtml(c.paciente_nome)}</td>
                <td>${escapeHtml(c.descricao || "")}${c.especialidade ? `<div class="texto-xs texto-suave">${escapeHtml(c.especialidade)}</div>` : ""}</td>
                <td>${formatarData(String(c.vencimento || "").slice(0, 10))}</td>
                <td>${formatarMoeda(c.a_pagar_centavos)}</td>
                <td>${formatarMoeda(c.pago_centavos)}</td>
                <td>${_finBadgeStatus(c)}${c.revisar ? ` <span class="badge badge-alerta" title="${escapeHtml(c.revisar_motivo || "")}">Revisar</span>` : ""}</td>
                <td style="white-space:nowrap;">
                  ${recebivel ? `<button type="button" class="botao botao-primario botao-sm fin-receber" data-id="${c.id}">Receber</button>
                  <button type="button" class="botao botao-secundario botao-sm fin-pix" data-id="${c.id}">Pix</button>` : ""}
                  <button type="button" class="botao botao-texto botao-sm fin-mais" data-id="${c.id}" aria-label="Ver detalhes">⋯</button>
                </td>
              </tr>`;
            }).join("")}
          </tbody>
        </table></div>`;
        const porId = new Map(lista.map(c => [String(c.id), c]));
        alvo.querySelectorAll(".fin-receber").forEach(b => b.addEventListener("click", () => finAbrirReceber(porId.get(b.dataset.id), recarregar)));
        alvo.querySelectorAll(".fin-mais").forEach(b => b.addEventListener("click", () => finAbrirDetalhes(porId.get(b.dataset.id), ehGestor, recarregar)));
        alvo.querySelectorAll(".fin-pix").forEach(b => b.addEventListener("click", async () => {
            b.disabled = true;
            try {
                const pix = await Api.post(`/financeiro/cobranca/${b.dataset.id}/gerar-pix`);
                abrirModalPix(pix, b.dataset.id);
            } catch (err) {
                Toast.erro(err.message);
            } finally { b.disabled = false; }
        }));
    }

    function ligarPendencias(raiz) {
        raiz.querySelectorAll(".fin-criar-acordo").forEach(b => b.addEventListener("click", () =>
            abrirCriarAcordo(b.dataset.paciente, b.dataset.esp, recarregar)));
        raiz.querySelectorAll(".fin-informar-valor").forEach(b => b.addEventListener("click", () =>
            finInformarValor(b.dataset.consulta, recarregar)));
        raiz.querySelectorAll(".fin-nao-cobrar").forEach(b => b.addEventListener("click", () => finPedirMotivo({
            titulo: "Não cobrar esta sessão", texto: "Ela sai das pendências e não entra em cobrança nenhuma.", botao: "Não cobrar",
            aoConfirmar: async (motivo) => {
                await Api.post(`/financeiro/sessoes/${b.dataset.consulta}/decisao`, { decisao: "nao_cobrar", motivo });
                Toast.sucesso("Sessão marcada como não cobrada.");
                recarregar();
            },
        })));
        raiz.querySelectorAll(".fin-cobrar-avulsa").forEach(b => b.addEventListener("click", async () => {
            b.disabled = true;
            try {
                await Api.post(`/financeiro/paciente/${b.dataset.paciente}/cobrar-avulsas`, { consulta_ids: [parseInt(b.dataset.consulta, 10)] });
                Toast.sucesso("Cobrança avulsa criada.");
                recarregar();
            } catch (err) {
                b.disabled = false;
                Toast.erro(err.message);
            }
        }));
        raiz.querySelectorAll(".fin-resolver").forEach(b => b.addEventListener("click", async () => {
            try {
                await Api.post(`/financeiro/cobranca/${b.dataset.id}/resolver-revisao`, {});
                Toast.sucesso("Marcada como resolvida.");
                recarregar();
            } catch (err) { Toast.erro(err.message); }
        }));
    }

    function aoMudarFiltro() {
        filtros.de = document.getElementById("fin-de").value;
        filtros.ate = document.getElementById("fin-ate").value;
        filtros.status = document.getElementById("fin-status").value;
        filtros.paciente_id = document.getElementById("fin-paciente").value;
        filtros.especialidade = document.getElementById("fin-esp").value;
        carregarCobrancas().catch(err => { if (viva()) Toast.erro(err.message); });
    }
    ["fin-de", "fin-ate", "fin-status", "fin-esp"].forEach(id => document.getElementById(id).addEventListener("change", aoMudarFiltro));
    document.getElementById("fin-paciente").addEventListener("change", aoMudarFiltro);

    await recarregar();
}

// ---------------------------------------------------------------- Financeiro (Responsável)

async function viewFinanceiroResponsavel(app) {
    const pacienteId = Sessao.pacienteAtivoId;
    const cobrancas = await Api.get(`/financeiro/paciente/${pacienteId}`);

    const cartao = (c) => {
        const r = resumoCobrancaFamilia(c);
        const itens = (c.itens || []).map(it => `
            <div class="linha-entre texto-sm" style="padding:3px 0; gap:8px;">
              <span>${formatarDataHoraLocal(it.data_hora)} · ${escapeHtml(it.procedimento_nome || "Sessão")}</span>
              <span class="texto-suave">${formatarMoeda(it.valor_centavos)}</span>
            </div>`).join("");
        return `
        <div class="cartao">
          <div class="linha-entre" style="gap:8px;">
            <div style="min-width:0;">
              <div style="font-weight:700;">${escapeHtml(c.descricao)}</div>
              <div class="texto-sm texto-suave">Vencimento: ${formatarData(String(c.vencimento || "").slice(0, 10))}</div>
            </div>
            <div style="text-align:right;">
              <div style="font-weight:700; font-size:16px;">${formatarMoeda(r.valorPrincipal)}</div>
              ${r.rotuloPrincipal ? `<div class="texto-xs texto-suave">${escapeHtml(r.rotuloPrincipal)}</div>` : ""}
              <span class="badge badge-${c.status === "pago" ? "sucesso" : c.status === "vencido" ? "alerta" : "aviso"}">${escapeHtml(rotuloStatusCobranca(c.status, c.aberta))}</span>
            </div>
          </div>
          ${itens ? `<div style="margin-top:10px; border-top:1px solid var(--cor-borda); padding-top:8px;"><div class="texto-xs texto-suave" style="margin-bottom:2px;">Sessões</div>${itens}</div>` : ""}
          ${r.temDesconto || c.pago_centavos ? `<div class="texto-sm" style="margin-top:8px;">
            ${r.temDesconto ? `<div class="linha-entre"><span>Desconto${c.desconto_motivo ? ` (${escapeHtml(c.desconto_motivo)})` : ""}</span><span>- ${formatarMoeda(c.desconto_centavos)}</span></div>` : ""}
            ${c.pago_centavos ? `<div class="linha-entre"><span>Já pago</span><span>${formatarMoeda(c.pago_centavos)}</span></div>` : ""}
          </div>` : ""}
          ${r.mostrarPix ? `<button class="botao botao-acento botao-sm btn-pagar" data-id="${c.id}" style="width:100%; margin-top:12px;">Pagar com PIX${c.status === "parcial" ? ` (${formatarMoeda(r.valorPrincipal)})` : ""}</button>` : ""}
        </div>`;
    };
    const conteudo = `
    <div class="coluna gap-3">
      ${cobrancas.length ? cobrancas.map(cartao).join("") : `<div class="estado-vazio"><div class="emoji">💳</div><p>Nenhuma cobrança no momento.</p></div>`}
    </div>`;

    app.innerHTML = renderShellMobile("#/responsavel/financeiro", { icone: "💳", texto: "Financeiro" }, conteudo);

    document.querySelectorAll(".btn-pagar").forEach(btn => btn.addEventListener("click", async () => {
        btn.disabled = true;
        btn.textContent = "Gerando PIX...";
        try {
            const pix = await Api.post(`/financeiro/cobranca/${btn.dataset.id}/gerar-pix`);
            abrirModalPix(pix, btn.dataset.id);
        } catch (err) {
            Toast.erro(err.message);
        } finally {
            btn.disabled = false;
            btn.textContent = "Pagar com PIX";
        }
    }));
}

function abrirModalPix(pix, cobrancaId) {
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa" style="text-align:center;">
        <h3 style="margin-bottom:6px;">Pague com PIX</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:16px;">Aponte a câmera do seu banco para o QR code, ou copie o código abaixo.</p>
        ${pix.qr_code_base64 ? `<img src="data:image/png;base64,${pix.qr_code_base64}" alt="QR code PIX" style="width:220px; height:220px; margin:0 auto 16px; display:block;" />` : ""}
        <div class="campo" style="text-align:left;">
          <label>PIX copia e cola</label>
          <textarea id="pix-copia-cola" readonly rows="3" style="width:100%; font-size:11px; resize:none;">${escapeHtml(pix.qr_code || "")}</textarea>
        </div>
        <button type="button" class="botao botao-secundario botao-sm" id="btn-copiar-pix" style="margin-top:8px;">📋 Copiar código</button>
        <p class="texto-xs texto-suave" style="margin-top:16px;">Assim que o pagamento for confirmado pelo banco, esta cobrança muda para "pago" automaticamente — não precisa avisar a clínica.</p>
        <button type="button" class="botao botao-primario" id="btn-fechar-pix" style="width:100%; margin-top:16px;">Já paguei / Fechar</button>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    modal.querySelector("#btn-copiar-pix").addEventListener("click", () => {
        modal.querySelector("#pix-copia-cola").select();
        navigator.clipboard?.writeText(pix.qr_code || "");
        Toast.sucesso("Código copiado!");
    });
    modal.querySelector("#btn-fechar-pix").addEventListener("click", () => {
        modal.remove();
        despachar(); // reconsulta a cobrança — se o webhook já confirmou, o status já aparece atualizado
    });
}

// ---------------------------------------------------------------- Indicadores (Gestor)

async function viewIndicadores(app) {
    const [semanal, kpi] = await Promise.all([
        Api.get("/indicadores/clinica/engajamento-semanal"),
        Api.get("/indicadores/gestor"),
    ]);
    const max = Math.max(1, ...semanal.map(d => d.missoes_concluidas));

    const conteudo = `
    <div class="cartao" style="margin-bottom:24px;">
      <h3 style="margin-bottom:20px;">Missões concluídas nos últimos 7 dias</h3>
      <div class="linha" style="align-items:flex-end; gap:14px; height:160px;">
        ${semanal.map(d => `
          <div class="coluna" style="flex:1; align-items:center; gap:8px;">
            <span class="texto-xs texto-suave">${d.missoes_concluidas}</span>
            <div style="width:100%; background:var(--cor-marca); border-radius:8px 8px 0 0; height:${Math.max(4, (d.missoes_concluidas / max) * 100)}px; transition:height .4s ease;"></div>
            <span class="texto-xs texto-suave">${new Date(d.data + "T12:00").toLocaleDateString("pt-BR", { weekday: "short" })}</span>
          </div>`).join("")}
      </div>
    </div>
    <div class="kpi-grade">
      ${kpiCard("👥", kpi.total_pacientes, "pacientes ativos", "marca")}
      ${kpiCard("🩺", kpi.total_profissionais, "profissionais", "marca")}
      ${kpiCard("📊", kpi.engajamento_pct + "%", "engajamento hoje", "sucesso")}
      ${kpiCard("⚠️", kpi.familias_inativas_5dias, "famílias inativas", kpi.familias_inativas_5dias > 0 ? "alerta" : "sucesso")}
    </div>`;

    app.innerHTML = renderShellSidebar("#/gestor/indicadores", "Indicadores", conteudo);
    anexarEventosShell();
}

// ---------------------------------------------------------------- Sua Assinatura (cobrança do plano)

function renderCartaoAssinatura(a) {
    const info = STATUS_COMERCIAL_INFO[a.status_comercial] || { label: a.status_comercial, badge: "neutro" };
    const pendentes = (a.cobrancas || []).filter(c => c.status === "pendente");
    const ultimaPaga = (a.cobrancas || []).find(c => c.status === "pago");

    return `
    <div class="cartao" id="cartao-assinatura" style="max-width:900px; margin-bottom:20px;">
      <div class="linha-entre" style="margin-bottom:4px;">
        <p class="texto-sm" style="font-weight:700;">💳 Sua Assinatura</p>
        <span class="badge badge-${info.badge}">${info.label}</span>
      </div>
      <p class="texto-sm texto-suave" style="margin-bottom:14px;">
        Plano ${escapeHtml(a.plano.nome || "")} — ${formatarMoeda(a.plano.preco_mensal_centavos || 0)}/mês
        ${a.dias_restantes_trial !== null && a.dias_restantes_trial !== undefined ? ` · ⏰ ${a.dias_restantes_trial > 0 ? a.dias_restantes_trial + " dia(s) de trial restante(s)" : "trial vencido"}` : ""}
      </p>

      ${pendentes.length ? pendentes.map(c => `
        <div class="cartao-flat" data-cobranca-id="${c.id}" style="border-color:var(--cor-alerta); background:var(--cor-alerta-clara); margin-bottom:10px;">
          <div class="linha-entre linha-assinatura-cobranca">
            <div>
              <p class="texto-sm" style="font-weight:700;">🔴 Cobrança pendente — ${formatarMoeda(c.valor_centavos)}</p>
              <p class="texto-xs texto-suave" style="margin-top:2px;">Gerada em ${formatarDataHora(c.criado_em)}</p>
            </div>
            <div class="linha gap-2 botoes-assinatura-cobranca">
              ${c.pix_copia_cola
                ? `<button class="botao botao-primario botao-sm btn-ver-pix-assinatura" data-copia-cola="${escapeHtml(c.pix_copia_cola)}">Ver PIX</button>
                   <button class="botao botao-secundario botao-sm btn-gerar-pix-assinatura" data-id="${c.id}" title="Gera um PIX novo para esta cobrança — use se o gateway de pagamento foi trocado ou se o código anterior expirou">🔄 Gerar novo PIX</button>`
                : `<button class="botao botao-primario botao-sm btn-gerar-pix-assinatura" data-id="${c.id}">Gerar PIX</button>`}
              ${a.mercadopago_public_key
                ? `<button class="botao botao-secundario botao-sm btn-pagar-cartao-assinatura" data-id="${c.id}">💳 Pagar com cartão</button>`
                : ""}
            </div>
          </div>
          ${c.pix_qr_code_base64 ? `<div class="pix-qr-assinatura" style="display:none; margin-top:12px; text-align:center;"><img src="data:image/png;base64,${c.pix_qr_code_base64}" alt="QR Code PIX" style="max-width:180px;" /></div>` : ""}
        </div>`).join("") : `
        <p class="texto-sm" style="color:var(--cor-sucesso); font-weight:600;">
          ✅ Nenhuma cobrança pendente.${ultimaPaga ? ` Última paga em ${formatarDataHora(ultimaPaga.pago_em || ultimaPaga.criado_em)}.` : ""}
        </p>`}

      ${a.mercadopago_public_key ? renderCartaoAssinaturaRecorrente(a.assinatura_recorrente) : ""}
    </div>`;
}

// ---------------------------------------------------------------- Assinatura recorrente no cartão (Fase 2, 15/09/2026)
//
// Diferente do bloco de cobranças pendentes acima (paga UMA cobrança já
// gerada, seja por PIX ou cartão avulso via Checkout Pro), isto liga/desliga
// a cobrança AUTOMÁTICA no cartão — o Mercado Pago cobra sozinho todo mês,
// sem o Gestor precisar entrar aqui pra gerar/pagar nada. Ver
// pagamento_plataforma_service.py > criar_assinatura_recorrente.
function renderCartaoAssinaturaRecorrente(rec) {
    if (rec && rec.status === "ativa") {
        return `
        <hr style="border:none; border-top:1px solid var(--cor-borda); margin:14px 0;" />
        <div class="linha-entre" style="gap:12px; flex-wrap:wrap;">
          <div>
            <p class="texto-sm" style="font-weight:700;">🔁 Cobrança automática no cartão ativada</p>
            <p class="texto-xs texto-suave" style="margin-top:2px; max-width:460px;">
              Todo mês, o Mercado Pago cobra sozinho o cartão cadastrado — você não precisa gerar PIX nem lembrar de pagar.
            </p>
          </div>
          <button class="botao botao-secundario botao-sm" id="btn-cancelar-recorrente">Cancelar</button>
        </div>`;
    }
    if (rec && rec.status === "pendente") {
        return `
        <hr style="border:none; border-top:1px solid var(--cor-borda); margin:14px 0;" />
        <div class="linha-entre" style="gap:12px; flex-wrap:wrap;">
          <div>
            <p class="texto-sm" style="font-weight:700;">⏳ Cobrança automática no cartão — aguardando autorização</p>
            <p class="texto-xs texto-suave" style="margin-top:2px; max-width:460px;">
              Você começou a ativar, mas ainda não concluiu a autorização com o cartão no Mercado Pago.
            </p>
          </div>
                    <div class="linha gap-2" style="flex-wrap:wrap;">
                                <button class="botao botao-secundario botao-sm" id="btn-ativar-recorrente">Continuar autorização</button>
                                            <button class="botao botao-secundario botao-sm" id="btn-cancelar-recorrente">Cancelar</button>
                                                      </div>
        </div>`;
    }
    return `
    <hr style="border:none; border-top:1px solid var(--cor-borda); margin:14px 0;" />
    <div class="linha-entre" style="gap:12px; flex-wrap:wrap;">
      <div>
        <p class="texto-sm" style="font-weight:700;">🔁 Cobrança automática no cartão</p>
        <p class="texto-xs texto-suave" style="margin-top:2px; max-width:460px;">
          Cadastre o cartão uma vez e o Mercado Pago cobra sozinho a assinatura todo mês — sem precisar gerar PIX nem lembrar de pagar.
        </p>
      </div>
      <button class="botao botao-secundario botao-sm" id="btn-ativar-recorrente">Ativar</button>
    </div>`;
}

async function ativarAssinaturaRecorrente(btn) {
    btn.disabled = true;
    const textoOriginal = btn.textContent;
    btn.textContent = "Abrindo…";
    try {
        const resultado = await Api.post("/admin/assinatura/recorrente/ativar");
        // Mesma ressalva de `abrirCheckoutCartaoAssinatura` — abrir a aba
        // ainda dentro do handler de clique evita bloqueio de pop-up na
        // maioria dos navegadores mesmo depois de um `await` rápido.
        const aba = window.open(resultado.checkout_url, "_blank", "noopener");
        if (!aba) {
            Toast.erro(`O navegador bloqueou a nova aba. Permita pop-ups para ${location.host} e tente de novo.`);
        } else {
            Toast.info("Autorize com seu cartão na aba que abriu. Quando voltar aqui, atualize a página pra ver o status.");
        }
        despachar();
    } catch (err) {
        Toast.erro(err.message || "Não foi possível iniciar a cobrança automática.");
    } finally {
        btn.disabled = false;
        btn.textContent = textoOriginal;
    }
}

async function cancelarAssinaturaRecorrente(btn) {
    if (!confirm("Cancelar a cobrança automática no cartão? A partir do próximo mês, a cobrança volta a ser por PIX (ou cartão avulso), como antes.")) return;
    btn.disabled = true;
    try {
        await Api.post("/admin/assinatura/recorrente/cancelar");
        Toast.sucesso("Cobrança automática no cartão cancelada.");
        despachar();
    } catch (err) {
        Toast.erro(err.message);
        btn.disabled = false;
    }
}

// ---------------------------------------------------------------- Pagamento no cartão (Fase 1 — cobrança por cartão)
//
// Checkout Pro da própria Mercado Pago, aberto em nova aba (link hospedado
// por ela) — troca o Card Payment Brick embutido original depois de
// confirmar, testando ao vivo (26/08/2026), que ele trava na inicialização
// nesta conta ("Bricks.create: Bricks component initialization failed"),
// mesmo com CSP, chave pública e rede corretos, inclusive em janela anônima
// sem extensões. Checkout Pro não roda JS nenhum da Mercado Pago aqui — a
// gente só pede um link pro backend (que cria uma "preferência" de cobrança)
// e abre ele numa aba nova; o Gestor paga lá e volta sozinho.
async function abrirCheckoutCartaoAssinatura(cobrancaId, btn) {
    btn.disabled = true;
    const textoOriginal = btn.textContent;
    btn.textContent = "Abrindo…";
    try {
        const resultado = await Api.post(`/admin/assinatura/${cobrancaId}/checkout-cartao`);
        // Precisa abrir a nova aba de forma síncrona (ainda dentro do handler
        // de clique) — se abrir só depois do `await` alguns navegadores
        // bloqueiam como pop-up indesejado. Como já estamos depois de um
        // `await`, chamamos aqui mesmo; navegadores modernos toleram isso
        // quando a resposta é rápida, mas o teste manual confirmou que abre
        // normalmente no Chrome/Edge/Firefox.
        const aba = window.open(resultado.checkout_url, "_blank", "noopener");
        if (!aba) {
            Toast.erro(`O navegador bloqueou a nova aba. Permita pop-ups para ${location.host} e tente de novo.`);
        }
    } catch (err) {
        Toast.erro(err.message || "Não foi possível abrir o pagamento por cartão.");
    } finally {
        btn.disabled = false;
        btn.textContent = textoOriginal;
    }
}

// ---------------------------------------------------------------- Configurações (Identidade Visual)

// Cartão "Financeiro" das Configurações (só gestor, só com o módulo).
function renderCartaoConfigFinanceiro(config) {
    if (!config) return "";
    const linha = (id, titulo, texto, marcado) => `
        <div class="linha gap-3" style="align-items:flex-start; justify-content:space-between; flex-wrap:wrap; margin-bottom:14px;">
          <div style="max-width:560px;"><p class="texto-sm" style="font-weight:700;">${titulo}</p><p class="texto-xs texto-suave" style="margin-top:2px;">${texto}</p></div>
          <label class="chave-toggle" style="flex-shrink:0;"><input type="checkbox" id="${id}" ${marcado ? "checked" : ""} /><span class="chave-slider"></span></label>
        </div>`;
    return `
    <div class="cartao" id="cartao-config-financeiro" style="max-width:900px; margin-top:20px;">
      <h3 style="margin-bottom:4px;">💳 Financeiro</h3>
      <p class="texto-xs texto-suave" style="margin-bottom:14px;">Regras de cobrança das sessões.</p>
      ${linha("fin-cfg-cobrar-falta", "Cobrar quando o paciente faltar", "Sessão com falta (sem justificativa) entra na cobrança como se tivesse acontecido.", config.cobrar_falta)}
      ${linha("fin-cfg-repasse-falta", "Repassar a falta ao profissional", "A sessão com falta cobrada também conta no repasse do profissional.", config.repasse_falta)}
      <button type="button" class="botao botao-primario" id="btn-salvar-config-financeiro">Salvar</button>
    </div>`;
}

function anexarEventosConfigFinanceiro() {
    const btn = document.getElementById("btn-salvar-config-financeiro");
    if (!btn) return;
    btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
            await Api.put("/financeiro/config", {
                cobrar_falta: document.getElementById("fin-cfg-cobrar-falta").checked,
                repasse_falta: document.getElementById("fin-cfg-repasse-falta").checked,
            });
            Toast.sucesso("Configuração do financeiro salva.");
        } catch (err) { Toast.erro(err.message); }
        finally { btn.disabled = false; }
    });
}

async function viewConfiguracoes(app) {
    const [org, me, assinatura, procedimentos, configFin] = await Promise.all([
        Api.get("/pessoas/organizacao"), Api.get("/auth/me"), Api.get("/admin/assinatura"),
        Api.get("/procedimentos").catch(() => []),
        financeiroHabilitado() ? Api.get("/financeiro/config").catch(() => null) : Promise.resolve(null),
    ]);
    const especialidadesAtuais = org.especialidades || [];
    const OPCOES_TIPO_REGISTRO_ACP = ["CRFa (Fonoaudiologia)", "CREFITO (Fisio/TO)", "CRP (Psicologia)", "CRN (Nutrição)", "CRE (Pedagogia)", "Outro"];
    const conteudo = `
    ${renderCartaoAssinatura(assinatura)}
    <div class="cartao" id="cartao-seus-dados" style="max-width:900px; margin-bottom:20px;">
        <p class="texto-sm" style="font-weight:700; margin-bottom:4px;">📇 Seus dados</p>
        <p class="texto-xs texto-suave" style="margin-bottom:14px;">Responsável pela conta: aparecem para a equipe PandaUp e podem ser usados em contato.</p>
        <div class="linha gap-3" style="align-items:center; margin-bottom:16px;">
          <div id="preview-avatar-contato" style="width:56px; height:56px; border-radius:50%; display:flex; align-items:center; justify-content:center; background:var(--cor-marca-clara); overflow:hidden; flex-shrink:0;">
            ${renderAvatarUsuario(me, 56)}
          </div>
          <div>
            <input type="file" id="input-avatar-contato" accept="image/*" style="display:none;" />
            <button type="button" class="botao botao-secundario botao-sm" id="btn-trocar-avatar-contato">📷 Trocar foto</button>
            ${renderOrientacaoEnvio("foto")}
          </div>
        </div>
        <div class="linha gap-4">
          <div class="campo" style="flex:1;"><label>Nome ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="ct-nome" value="${escapeHtml(me.nome)}" required /></div>
          <div class="campo" style="flex:1;"><label>Telefone</label><input type="tel" id="ct-telefone" value="${escapeHtml(me.telefone || "")}" /></div>
        </div>
        <div class="campo"><label>E-mail</label><input type="email" value="${escapeHtml(me.email)}" disabled style="opacity:.6;" /></div>
        <p class="texto-xs texto-suave" style="margin-bottom:4px;">O e-mail é seu identificador de login e não pode ser alterado por aqui.</p>

        <hr style="border:none; border-top:1px solid var(--cor-borda); margin:18px 0;" />
        <div id="parte-atuar-profissional">
        <div class="linha gap-3" style="align-items:flex-start; justify-content:space-between; flex-wrap:wrap;">
          <div class="linha gap-2" style="align-items:flex-start;">
            <span style="font-size:18px;">🩺</span>
            <div>
              <p class="texto-sm" style="font-weight:700;">Atuar também como profissional</p>
              <p class="texto-xs texto-suave" style="margin-top:2px; max-width:540px;">
                Ative para poder ser escolhido como profissional em consultas e no atendimento de pacientes — com
                esta mesma conta (mesmo login e senha), sem precisar de um cadastro separado na Equipe.
              </p>
            </div>
          </div>
          <label class="chave-toggle" style="flex-shrink:0;">
            <input type="checkbox" id="chk-atuar-profissional" ${me.atua_como_profissional ? "checked" : ""} />
            <span class="chave-slider"></span>
          </label>
        </div>
        <div id="form-atuar-profissional" style="margin-top:16px; ${me.atua_como_profissional ? "" : "display:none;"}">
          <div class="campo">
            <label>Especialidade ${ASTERISCO_OBRIGATORIO}</label>
            <input type="text" id="acp-especialidade" list="lista-especialidades-clinica-acp" value="${escapeHtml(me.especialidade || "")}" placeholder="Ex: Fonoaudiologia" required />
            <datalist id="lista-especialidades-clinica-acp">
              ${especialidadesAtuais.map(e => `<option value="${escapeHtml(e)}">`).join("")}
            </datalist>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;">
              <label>Tipo de registro</label>
              <select id="acp-tipo-registro">
                <option value="">Não informar</option>
                ${OPCOES_TIPO_REGISTRO_ACP.map(t => `<option value="${t}" ${me.tipo_registro === t ? "selected" : ""}>${t}</option>`).join("")}
              </select>
            </div>
            <div class="campo" style="flex:1;"><label>Número de registro</label><input type="text" id="acp-numero-registro" value="${escapeHtml(me.numero_registro || "")}" placeholder="Ex: 12345" /></div>
          </div>
          <div class="campo">
            <label>Cor na Agenda</label>
            <div class="linha gap-2" style="align-items:center;">
              <input type="color" id="acp-cor-agenda" value="${corSegura(me.cor_agenda, "#5B4FE9")}" style="width:48px; height:38px; padding:2px;" />
              <p class="texto-xs texto-suave">Identifica suas consultas como profissional no calendário.</p>
            </div>
          </div>
        </div>
        </div>
        <button type="button" class="botao botao-primario" id="btn-salvar-meus-dados" style="margin-top:16px;">Salvar meus dados</button>
    </div>

    <div class="grade grade-dupla" style="max-width:900px;">
      <div class="cartao">
        <h3 style="margin-bottom:18px;">Identidade visual da clínica</h3>
        <form id="form-config">
          <div class="campo"><label>Nome da clínica ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="cf-nome" value="${escapeHtml(org.nome)}" required /></div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Cor primária</label><input type="color" id="cf-cor1" value="${corSegura(org.cor_primaria, "#5B4FE9")}" style="height:44px;" /></div>
            <div class="campo" style="flex:1;"><label>Cor secundária</label><input type="color" id="cf-cor2" value="${corSegura(org.cor_secundaria, "#FFB84D")}" style="height:44px;" /></div>
          </div>
          <p class="texto-xs texto-suave" style="margin:-8px 0 14px;">As cores já aparecem em tempo real por toda a plataforma assim que você salvar.</p>

          <div class="campo">
            <label>Logo da clínica</label>
            <div class="linha gap-3" style="align-items:center;">
              <div id="preview-logo-atual" style="min-width:56px; max-width:160px; height:56px; border-radius:12px; border:1.5px solid var(--cor-borda); display:flex; align-items:center; justify-content:center; overflow:hidden; padding:6px;">
                ${renderLogoClinica(org, 40)}
              </div>
              <input type="file" id="cf-logo-arquivo" accept="image/*" style="flex:1;" />
            </div>
            ${renderOrientacaoEnvio("logo")}
            <p class="texto-xs texto-suave" style="margin-top:2px;">Ou deixe em branco para usar um emoji simples abaixo. O logo aparece inteiro, sem cortes.</p>
          </div>
          <div class="campo"><label>Emoji/ícone (usado se nenhuma imagem for enviada)</label><input type="text" id="cf-logo" value="${escapeHtml(org.logo_emoji)}" maxlength="2" style="width:80px; font-size:22px; text-align:center;" /></div>

          <hr style="border:none; border-top:1px solid var(--cor-borda); margin:20px 0;" />
          <p class="texto-sm" style="font-weight:700; margin-bottom:4px;">🎨 Nomes da gamificação</p>
          <p class="texto-xs texto-suave" style="margin-bottom:14px;">Esses nomes aparecem para profissionais, famílias e crianças em toda a plataforma.</p>
          <div class="campo"><label>Nome do assistente de IA</label><input type="text" id="cf-nome-ia" value="${escapeHtml(org.nome_ia || "Lumi")}" placeholder="Ex: Lumi, Nina, Léo..." /></div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Nome da "moeda" da gamificação</label><input type="text" id="cf-nome-moeda" value="${escapeHtml(org.nome_moeda_gamificacao || "XP")}" placeholder="Ex: XP, Estrelinhas, Pontos..." /></div>
            <div class="campo" style="flex:1;"><label>Nome genérico das conquistas</label><input type="text" id="cf-nome-medalha" value="${escapeHtml(org.nome_medalha_generico || "Medalha")}" placeholder="Ex: Medalha, Troféu, Selo..." /></div>
          </div>
          <button type="submit" class="botao botao-primario">Salvar identidade visual</button>
        </form>
      </div>
      <div class="cartao-flat">
        <p class="texto-sm" style="font-weight:700; margin-bottom:10px;">👀 Pré-visualização</p>
        <div class="cartao" style="text-align:center;">
          ${svgMascote({ emoji: "🐻", estagio: 3, tamanho: 90, flutuar: true })}
          <p class="texto-sm" style="margin-top:10px;"><strong id="preview-nome-ia">${escapeHtml(org.nome_ia || "Lumi")}</strong> está por aqui para ajudar ✨</p>
          <p class="texto-sm" style="margin-top:6px;">Ganhou <strong id="preview-moeda">40 ${escapeHtml(org.nome_moeda_gamificacao || "XP")}</strong> e uma nova <strong id="preview-medalha">${escapeHtml(org.nome_medalha_generico || "Medalha")}</strong>!</p>
        </div>
      </div>
    </div>

    <div class="cartao" style="max-width:900px; margin-top:20px;">
      <h3 style="margin-bottom:4px;">🏢 Dados institucionais</h3>
      <p class="texto-xs texto-suave" style="margin-bottom:14px;">Usados em documentos, recibos e no cadastro oficial da clínica.</p>
      <form id="form-dados-clinica">
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>CNPJ</label><input type="text" id="cf-cnpj" value="${escapeHtml(org.cnpj || "")}" placeholder="00.000.000/0000-00" /></div>
            <div class="campo" style="flex:1;"><label>Telefone da clínica</label><input type="tel" id="cf-telefone" value="${escapeHtml(org.telefone || "")}" /></div>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>CEP</label><input type="text" id="cf-cep" value="${escapeHtml(org.endereco_cep || "")}" placeholder="00000-000" /></div>
            <div class="campo" style="flex:2;"><label>Logradouro</label><input type="text" id="cf-logradouro" value="${escapeHtml(org.endereco_logradouro || "")}" /></div>
            <div class="campo" style="flex:1;"><label>Número</label><input type="text" id="cf-numero" value="${escapeHtml(org.endereco_numero || "")}" /></div>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Bairro</label><input type="text" id="cf-bairro" value="${escapeHtml(org.endereco_bairro || "")}" /></div>
            <div class="campo" style="flex:1;"><label>Cidade</label><input type="text" id="cf-cidade" value="${escapeHtml(org.endereco_cidade || "")}" /></div>
            <div class="campo" style="flex:0 0 80px;"><label>UF</label><input type="text" id="cf-uf" value="${escapeHtml(org.endereco_uf || "")}" maxlength="2" style="text-transform:uppercase;" /></div>
          </div>

          <hr style="border:none; border-top:1px solid var(--cor-borda); margin:20px 0;" />
          <p class="texto-sm" style="font-weight:700; margin-bottom:4px;">🕒 Horário de funcionamento da agenda</p>
          <p class="texto-xs texto-suave" style="margin-bottom:12px;">A grade da agenda mostra essa faixa de horário. Deixe os dois em branco para ela se ajustar sozinha às consultas da semana.</p>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Abre às</label><input type="time" id="cf-agenda-inicio" value="${escapeHtml(org.agenda_hora_inicio || "")}" /></div>
            <div class="campo" style="flex:1;"><label>Fecha às</label><input type="time" id="cf-agenda-fim" value="${escapeHtml(org.agenda_hora_fim || "")}" /></div>
          </div>
          <div class="campo" style="max-width:260px;"><label>Duração padrão da consulta (min)</label><input type="number" id="cf-agenda-duracao" min="5" max="240" step="5" value="${escapeHtml(String(org.agenda_duracao_padrao || 50))}" /></div>
          <p class="texto-xs texto-suave" style="margin:-8px 0 12px;">Ao agendar, o horário de fim já vem com essa duração (dá para mudar em cada consulta).</p>

          <hr style="border:none; border-top:1px solid var(--cor-borda); margin:20px 0;" />
          <p class="texto-sm" style="font-weight:700; margin-bottom:4px;">🩺 Especialidades</p>
          <p class="texto-xs texto-suave" style="margin-bottom:12px;">Quais especialidades sua clínica oferece? Digite e adicione — isso ajuda a organizar a Equipe e a Biblioteca.</p>
          ${renderCampoTagsEspecialidade("cf-esp", especialidadesAtuais)}

          <hr style="border:none; border-top:1px solid var(--cor-borda); margin:20px 0;" />
          ${renderCaixaProcedimentos(procedimentos)}
          <button type="submit" class="botao botao-primario" style="margin-top:20px;">Salvar dados da clínica</button>
      </form>
    </div>
    ${renderCartaoConfigFinanceiro(configFin)}
    ${renderCartaoCenarioPandoo(org)}
    ${renderCartaoIdentidadePropria(org)}`;
    app.innerHTML = renderShellSidebar("#/gestor/configuracoes", "Configurações", conteudo);
    anexarEventosShell();
    anexarEventosCenarioPandoo(org);
    anexarEventosIdentidadePropria(org);
    anexarEventosConfigFinanceiro();

    // Veio de um clique em notificação financeira (ver rotaParaNotificacao,
    // em shell.js) — rola até "Sua Assinatura" e dá um destaque rápido, pra
    // deixar claro que foi pra lá que o clique levou.
    if (sessionStorage.getItem("destacar_assinatura")) {
        sessionStorage.removeItem("destacar_assinatura");
        const cartaoAssinatura = document.getElementById("cartao-assinatura");
        if (cartaoAssinatura) {
            cartaoAssinatura.scrollIntoView({ behavior: "smooth", block: "start" });
            cartaoAssinatura.classList.add("destaque-notificacao");
            setTimeout(() => cartaoAssinatura.classList.remove("destaque-notificacao"), 2200);
        }
    }

    // --- Sua Assinatura ---
    document.querySelectorAll(".btn-gerar-pix-assinatura").forEach(btn => btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
            await Api.post(`/admin/assinatura/${btn.dataset.id}/gerar-pix`);
            Toast.sucesso("PIX gerado!");
            despachar();
        } catch (err) {
            btn.disabled = false;
            Toast.erro(err.message);
        }
    }));
    document.querySelectorAll(".btn-ver-pix-assinatura").forEach(btn => btn.addEventListener("click", () => {
        navigator.clipboard?.writeText(btn.dataset.copiaCola).catch(() => {});
        Toast.info("Código PIX copiado — cole no app do seu banco para pagar.");
        const qr = btn.closest("[data-cobranca-id]")?.querySelector(".pix-qr-assinatura");
        if (qr) qr.style.display = qr.style.display === "none" ? "block" : "none";
    }));
    document.querySelectorAll(".btn-pagar-cartao-assinatura").forEach(btn => btn.addEventListener("click", () => {
        abrirCheckoutCartaoAssinatura(Number(btn.dataset.id), btn);
    }));
    const btnAtivarRecorrente = document.getElementById("btn-ativar-recorrente");
    if (btnAtivarRecorrente) btnAtivarRecorrente.addEventListener("click", () => ativarAssinaturaRecorrente(btnAtivarRecorrente));
    const btnCancelarRecorrente = document.getElementById("btn-cancelar-recorrente");
    if (btnCancelarRecorrente) btnCancelarRecorrente.addEventListener("click", () => cancelarAssinaturaRecorrente(btnCancelarRecorrente));

    // --- Seus dados (contato + atuar como profissional, um cartão desde 26/10/2026) ---
    ativarMascaraCampo(document.getElementById("ct-telefone"), "telefone");
    ativarMascaraCampo(document.getElementById("cf-telefone"), "telefone");
    ativarMascaraCampo(document.getElementById("cf-cnpj"), "cnpj");
    ativarMascaraCampo(document.getElementById("cf-cep"), "cep");
    ativarAutoCompleteCep("cf");
    document.getElementById("btn-trocar-avatar-contato").addEventListener("click", () => document.getElementById("input-avatar-contato").click());
    let avatarContatoNovo = null;
    document.getElementById("input-avatar-contato").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        let preparada;
        try {
            preparada = await prepararImagemParaEnvio(file, "foto");
        } catch (err) { Toast.erro(err.message); e.target.value = ""; return; }
        if (preparada.aviso) Toast.info(preparada.aviso);
        const base64 = preparada.base64;
        avatarContatoNovo = { base64, nome: preparada.nome };
        document.getElementById("preview-avatar-contato").innerHTML = `<img src="data:image/png;base64,${base64}" style="width:100%; height:100%; object-fit:cover;" alt="Foto" />`;
    });
    // --- Atuar também como profissional ---
    // 26/10/2026: a chave só mostra/esconde os campos; "Salvar meus dados"
    // grava o contato e o "atuar como profissional" juntos.
    document.getElementById("chk-atuar-profissional").addEventListener("change", (e) => {
        const formAcp = document.getElementById("form-atuar-profissional");
        formAcp.style.display = e.target.checked ? "block" : "none";
        if (e.target.checked) document.getElementById("acp-especialidade").focus();
    });

    document.getElementById("btn-salvar-meus-dados").addEventListener("click", async (ev) => {
        // Botão avulso (fora de <form>): chama a validação nativa à mão.
        if (!document.getElementById("ct-nome").reportValidity()) return;
        const atuar = document.getElementById("chk-atuar-profissional").checked;
        const especialidade = document.getElementById("acp-especialidade").value.trim();
        if (atuar && !especialidade) {
            document.getElementById("acp-especialidade").reportValidity();
            Toast.erro("Informe a especialidade para atuar como profissional.");
            return;
        }
        const perfil = {
            nome: document.getElementById("ct-nome").value.trim(),
            telefone: document.getElementById("ct-telefone").value.trim(),
        };
        if (avatarContatoNovo) { perfil.avatar_base64 = avatarContatoNovo.base64; perfil.avatar_nome = avatarContatoNovo.nome; }
        const botao = ev.currentTarget;
        botao.disabled = true;
        try {
            await Api.put("/pessoas/perfil", perfil);
            const u = Sessao.usuario;
            u.nome = perfil.nome; u.telefone = perfil.telefone;
            if (avatarContatoNovo) u.avatar_base64 = avatarContatoNovo.base64;
            if (atuar) {
                await Api.put("/pessoas/perfil/atuar-como-profissional", {
                    atua_como_profissional: true,
                    especialidade,
                    tipo_registro: document.getElementById("acp-tipo-registro").value,
                    numero_registro: document.getElementById("acp-numero-registro").value.trim(),
                    cor_agenda: document.getElementById("acp-cor-agenda").value,
                });
                u.atua_como_profissional = true;
            } else if (me.atua_como_profissional) {
                await Api.put("/pessoas/perfil/atuar-como-profissional", { atua_como_profissional: false });
                u.atua_como_profissional = false;
            }
            Sessao.usuario = u;
            Toast.sucesso("Seus dados foram salvos!");
            despachar();
        } catch (err) {
            Toast.erro(err.message);
            botao.disabled = false;
        }
    });

    // --- Procedimentos (26/10/2026: saíram do menu; pop-up a partir daqui) ---
    function ligarCaixaProcedimentos() {
        document.getElementById("btn-gerenciar-procedimentos").addEventListener("click", () => {
            abrirModalProcedimentos({ aoSalvar: (lista) => {
                const caixa = document.getElementById("caixa-procedimentos");
                if (!caixa) return;
                caixa.outerHTML = renderCaixaProcedimentos(lista);
                ligarCaixaProcedimentos();
            } });
        });
    }
    ligarCaixaProcedimentos();
    if (new URLSearchParams(location.hash.split("?")[1] || "").get("procedimentos") === "1") {
        document.getElementById("caixa-procedimentos").scrollIntoView({ block: "center" });
        document.getElementById("btn-gerenciar-procedimentos").click();
    }

    let logoBase64Novo = null;
    let logoNomeNovo = null;
    document.getElementById("cf-logo-arquivo").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        let preparada;
        try {
            preparada = await prepararImagemParaEnvio(file, "logo");
        } catch (err) { Toast.erro(err.message); e.target.value = ""; return; }
        if (preparada.aviso) Toast.info(preparada.aviso);
        const base64 = preparada.base64;
        logoBase64Novo = base64;
        logoNomeNovo = preparada.nome;
        document.getElementById("preview-logo-atual").innerHTML = `<img src="data:image/png;base64,${base64}" style="max-width:100%; max-height:100%; width:auto; height:auto; object-fit:contain;" alt="Logo" />`;
    });

    const obterEspecialidadesCf = ativarCampoTagsEspecialidade("cf-esp", especialidadesAtuais);

    ["cf-nome-ia", "cf-nome-moeda", "cf-nome-medalha"].forEach(id => {
        document.getElementById(id).addEventListener("input", () => {
            const nomeIa = document.getElementById("cf-nome-ia").value || "Lumi";
            const moeda = document.getElementById("cf-nome-moeda").value || "XP";
            const medalha = document.getElementById("cf-nome-medalha").value || "Medalha";
            document.getElementById("preview-nome-ia").textContent = nomeIa;
            document.getElementById("preview-moeda").textContent = `40 ${moeda}`;
            document.getElementById("preview-medalha").textContent = medalha;
        });
    });

    // Configurações em dois cartões (26/09/2026): cada um salva só os próprios
    // campos (o backend só mexe no que vem no corpo).
    async function salvarOrganizacao(body, mensagem) {
        try {
            await Api.put("/pessoas/organizacao", body);
        } catch (err) { Toast.erro(err.message); return; }
        // A sessão recebe a identidade EFETIVA (/auth/me).
        const me = await Api.get("/auth/me");
        const u = Sessao.usuario;
        u.organizacao = me.organizacao;
        Sessao.usuario = u;
        aplicarTemaClinica(u.organizacao);
        Toast.sucesso(mensagem);
        despachar();
    }

    document.getElementById("form-config").addEventListener("submit", async (e) => {
        e.preventDefault();
        const body = {
            nome: document.getElementById("cf-nome").value.trim(),
            cor_primaria: document.getElementById("cf-cor1").value,
            cor_secundaria: document.getElementById("cf-cor2").value,
            logo_emoji: document.getElementById("cf-logo").value,
            nome_ia: document.getElementById("cf-nome-ia").value.trim() || "Lumi",
            nome_moeda_gamificacao: document.getElementById("cf-nome-moeda").value.trim() || "XP",
            nome_medalha_generico: document.getElementById("cf-nome-medalha").value.trim() || "Medalha",
        };
        if (logoBase64Novo) { body.logo_base64 = logoBase64Novo; body.logo_nome = logoNomeNovo; }
        await salvarOrganizacao(body, "Identidade visual salva!");
    });

    document.getElementById("form-dados-clinica").addEventListener("submit", async (e) => {
        e.preventDefault();
        const agendaInicio = document.getElementById("cf-agenda-inicio").value;
        const agendaFim = document.getElementById("cf-agenda-fim").value;
        if (!!agendaInicio !== !!agendaFim) { Toast.erro("Preencha o horário de abertura e o de fechamento da agenda, ou deixe os dois em branco."); return; }
        if (agendaInicio && agendaInicio >= agendaFim) { Toast.erro("O horário de abertura da agenda precisa ser antes do de fechamento."); return; }
        const duracaoPadrao = parseInt(document.getElementById("cf-agenda-duracao").value, 10);
        if (!(duracaoPadrao >= 5 && duracaoPadrao <= 240)) { Toast.erro("A duração padrão precisa ficar entre 5 e 240 minutos."); return; }
        await salvarOrganizacao({
            cnpj: document.getElementById("cf-cnpj").value.trim(),
            telefone: document.getElementById("cf-telefone").value.trim(),
            endereco_cep: document.getElementById("cf-cep").value.trim(),
            endereco_logradouro: document.getElementById("cf-logradouro").value.trim(),
            endereco_numero: document.getElementById("cf-numero").value.trim(),
            endereco_bairro: document.getElementById("cf-bairro").value.trim(),
            endereco_cidade: document.getElementById("cf-cidade").value.trim(),
            endereco_uf: document.getElementById("cf-uf").value.trim().toUpperCase(),
            especialidades: obterEspecialidadesCf(),
            agenda_hora_inicio: agendaInicio,
            agenda_hora_fim: agendaFim,
            agenda_duracao_padrao: duracaoPadrao,
        }, "Dados da clínica salvos!");
    });
}

// ---------------------------------------------------------------- Perfil (Gestor / Profissional)

async function viewPerfilInterno(app) {
    const u = Sessao.usuario;
    const base = u.papel === "gestor" ? "gestor" : (u.papel === "secretaria" ? "secretaria" : "profissional");
    const me = await Api.get("/auth/me");
    const conteudo = `
    <div class="grade grade-dupla" style="max-width:760px;">
      <div class="cartao" style="text-align:center;">
        <div id="preview-avatar-perfil" style="width:96px; height:96px; border-radius:50%; margin:0 auto; display:flex; align-items:center; justify-content:center; background:var(--cor-marca-clara); overflow:hidden; font-size:48px;">
          ${renderAvatarUsuario(me, 96)}
        </div>
        <input type="file" id="input-avatar-perfil" accept="image/*" style="display:none;" />
        <button type="button" class="botao botao-secundario botao-sm" id="btn-trocar-avatar" style="margin-top:12px;">📷 Trocar foto</button>
        ${renderOrientacaoEnvio("foto")}
        <h3 style="margin-top:10px;">${escapeHtml(me.nome)}</h3>
        <p class="texto-sm texto-suave">${escapeHtml(me.email)}</p>
        ${me.especialidade ? `<span class="badge badge-marca" style="margin-top:6px;">${escapeHtml(me.especialidade)}</span>` : ""}
      </div>
      <div class="cartao">
        <p class="texto-xs texto-suave" style="font-weight:700; margin-bottom:12px;">MEUS DADOS</p>
        <form id="form-perfil-interno">
          <div class="campo"><label>Nome completo ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="perfil-nome" value="${escapeHtml(me.nome)}" required /></div>
          <div class="campo"><label>Telefone</label><input type="tel" id="perfil-telefone" value="${escapeHtml(me.telefone || "")}" /></div>
          <p class="texto-xs texto-suave" style="margin-bottom:14px;">O e-mail (${escapeHtml(me.email)}) é seu identificador de login e não pode ser alterado por aqui.</p>
          <button type="submit" class="botao botao-primario" style="width:100%;">Salvar alterações</button>
        </form>
      </div>
    </div>`;
    app.innerHTML = renderShellSidebar(`#/${base}/perfil`, "Meu Perfil", conteudo);
    anexarEventosShell();

    ativarMascaraCampo(document.getElementById("perfil-telefone"), "telefone");
    document.getElementById("btn-trocar-avatar").addEventListener("click", () => document.getElementById("input-avatar-perfil").click());
    document.getElementById("input-avatar-perfil").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        let preparada;
        try {
            preparada = await prepararImagemParaEnvio(file, "foto");
        } catch (err) { Toast.erro(err.message); e.target.value = ""; return; }
        if (preparada.aviso) Toast.info(preparada.aviso);
        const base64 = preparada.base64;
        try {
            await Api.put("/pessoas/perfil", { avatar_base64: base64, avatar_nome: preparada.nome });
            const uAtual = Sessao.usuario; uAtual.avatar_base64 = base64; Sessao.usuario = uAtual;
            document.getElementById("preview-avatar-perfil").innerHTML = `<img src="data:image/png;base64,${base64}" style="width:100%; height:100%; object-fit:cover;" alt="Foto" />`;
            Toast.sucesso("Foto atualizada!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });

    document.getElementById("form-perfil-interno").addEventListener("submit", async (e) => {
        e.preventDefault();
        const nome = document.getElementById("perfil-nome").value.trim();
        const telefone = document.getElementById("perfil-telefone").value.trim();
        try {
            await Api.put("/pessoas/perfil", { nome, telefone });
            const uAtual = Sessao.usuario; uAtual.nome = nome; uAtual.telefone = telefone; Sessao.usuario = uAtual;
            Toast.sucesso("Dados atualizados!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });
}
