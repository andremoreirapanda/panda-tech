// ============================================================================
// views/financeiro_ficha.js — Acordos e extrato na ficha do paciente (Financeiro,
// 08/11/2026). Só gestor e secretária, e só com o módulo Financeiro ativo — o
// profissional nunca chama as rotas /financeiro daqui.
// ============================================================================

function _ficReais(centavos) {
    return (centavos / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function podeVerFinanceiroFicha() { return _ficPodeVer(); }

function _ficPodeVer() {
    const papel = Sessao.usuario && Sessao.usuario.papel;
    return (papel === "gestor" || papel === "secretaria") && financeiroHabilitado();
}

function _ficLinhaAcordo(a) {
    const esp = rotuloEspecialidadeAcordo(a.especialidade);
    const usadas = a.tipo === "pacote" && a.sessoes_usadas != null
        ? ` · ${a.sessoes_usadas} de ${a.sessoes_total} sessões usadas` : "";
    const inicio = a.inicio ? `desde ${formatarData(String(a.inicio).slice(0, 10))}` : "";
    const fim = a.fim ? ` · até ${formatarData(String(a.fim).slice(0, 10))}` : "";
    const ativo = a.status === "ativo";
    return `
      <div class="fic-acordo" data-id="${a.id}" style="padding:10px 0; border-top:1px solid var(--cor-borda);">
        <div class="linha-entre" style="gap:8px; flex-wrap:wrap;">
          <div style="min-width:0;">
            <div style="font-weight:700;">${escapeHtml(esp)}${ativo ? "" : ` <span class="badge badge-neutro">Encerrado</span>`}</div>
            <div class="texto-sm texto-suave">${escapeHtml(rotuloAcordo(a))}${escapeHtml(usadas)}</div>
            <div class="texto-xs texto-suave">${escapeHtml(inicio)}${escapeHtml(fim)}</div>
          </div>
          ${ativo ? `<div class="linha gap-1" style="flex-shrink:0;">
            <button type="button" class="botao botao-texto botao-sm fic-editar" data-id="${a.id}">Editar</button>
            <button type="button" class="botao botao-texto botao-sm fic-encerrar" data-id="${a.id}">Encerrar</button>
          </div>` : ""}
        </div>
      </div>`;
}

async function renderCartaoFinanceiroFicha(pacienteId, alvo) {
    if (!alvo) return;
    if (!_ficPodeVer()) { alvo.hidden = true; alvo.innerHTML = ""; return; }
    const base = Sessao.usuario.papel === "gestor" ? "gestor" : "secretaria";
    let acordos, cobrancas;
    try {
        [acordos, cobrancas] = await Promise.all([
            Api.get(`/financeiro/paciente/${pacienteId}/acordos`),
            Api.get(`/financeiro/paciente/${pacienteId}`),
        ]);
    } catch (err) {
        alvo.hidden = false;
        alvo.innerHTML = `<div class="cartao"><h4 style="margin-bottom:6px;">💳 Financeiro</h4><p class="texto-sm texto-suave">Não foi possível carregar o financeiro agora.</p></div>`;
        return;
    }
    if (!alvo.isConnected) return;   // saiu da tela enquanto carregava
    const ativos = acordos.filter(a => a.status === "ativo");
    const encerrados = acordos.filter(a => a.status !== "ativo");
    const recentes = cobrancas.filter(c => c.status !== "cancelado").slice(0, 6);
    alvo.hidden = false;
    alvo.innerHTML = `
      <div class="cartao" id="cartao-financeiro-ficha">
        <div class="linha-entre" style="margin-bottom:8px; gap:8px;">
          <h4>💳 Financeiro</h4>
          <button type="button" class="botao botao-secundario botao-sm" id="fic-novo-acordo">+ Novo acordo</button>
        </div>
        <p class="texto-xs texto-suave" style="margin-bottom:4px;">Acordos de pagamento</p>
        ${ativos.length ? ativos.map(_ficLinhaAcordo).join("") : `<p class="texto-sm texto-suave" style="padding:6px 0;">Nenhum acordo ativo. Sessões feitas sem acordo ficam nas pendências do Financeiro.</p>`}
        ${encerrados.length ? `<details style="margin-top:6px;"><summary class="texto-xs texto-suave" style="cursor:pointer;">Acordos encerrados (${encerrados.length})</summary>${encerrados.map(_ficLinhaAcordo).join("")}</details>` : ""}
        <p class="texto-xs texto-suave" style="margin:14px 0 4px;">Últimas cobranças</p>
        ${recentes.length ? recentes.map(c => `
          <div class="linha-entre" style="padding:6px 0; border-top:1px solid var(--cor-borda); gap:8px; flex-wrap:wrap;">
            <div style="min-width:0;">
              <div class="texto-sm">${escapeHtml(c.descricao || "")}</div>
              <div class="texto-xs texto-suave">Vence ${formatarData(String(c.vencimento || "").slice(0, 10))} · ${formatarMoeda(c.a_pagar_centavos)}</div>
            </div>
            ${_finBadgeStatus(c)}
          </div>`).join("") : `<p class="texto-sm texto-suave" style="padding:6px 0;">Nenhuma cobrança ainda.</p>`}
        <a class="botao botao-texto botao-sm" style="margin-top:8px;" href="#/${base}/financeiro?paciente=${encodeURIComponent(pacienteId)}">Ver em Cobranças →</a>
      </div>`;

    const recarregar = () => renderCartaoFinanceiroFicha(pacienteId, alvo);
    const porId = new Map(acordos.map(a => [String(a.id), a]));
    alvo.querySelector("#fic-novo-acordo").addEventListener("click", () => abrirModalAcordo(pacienteId, { aoSalvar: recarregar }));
    alvo.querySelectorAll(".fic-editar").forEach(b => b.addEventListener("click", () =>
        abrirModalAcordo(pacienteId, { acordo: porId.get(b.dataset.id), aoSalvar: recarregar })));
    alvo.querySelectorAll(".fic-encerrar").forEach(b => b.addEventListener("click", () =>
        abrirEncerrarAcordo(porId.get(b.dataset.id), recarregar)));
}

function abrirEncerrarAcordo(acordo, aoSalvar) {
    const limite = limiteEncerrarAcordo(paraChaveDia(new Date()), acordo.fim);
    const aviso = acordo.tipo === "mensalidade"
        ? "A cobrança do mês acompanha a data: sem pagamento, é recalculada; com pagamento, fica um aviso para revisar."
        : "O que já virou cobrança não muda.";
    const modal = el(`
    <div class="modal-fundo" data-modal-preparado="1" data-modal-formulario="1">
      <div class="modal-caixa">
        <h3 style="margin-bottom:6px;">Encerrar acordo</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:12px;">${escapeHtml(rotuloEspecialidadeAcordo(acordo.especialidade))} · ${escapeHtml(rotuloAcordo(acordo))}<br />
          ${escapeHtml(aviso)} As sessões depois da data ficam sem acordo. Para um fim no futuro, use Editar.</p>
        <div class="campo"><label for="fic-enc-fim">Último dia do acordo</label><input type="date" id="fic-enc-fim" value="${limite}" max="${limite}" /></div>
        <div class="linha gap-3" style="justify-content:flex-end; margin-top:12px;">
          <button type="button" class="botao botao-secundario" data-fechar>Voltar</button>
          <button type="button" class="botao botao-primario" id="fic-enc-ok">Encerrar acordo</button>
        </div>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.querySelector("[data-fechar]").addEventListener("click", () => modal.remove());
    modal.querySelector("#fic-enc-ok").addEventListener("click", async (ev) => {
        const fim = modal.querySelector("#fic-enc-fim").value;
        if (!fim) { Toast.erro("Informe o último dia do acordo."); return; }
        ev.target.disabled = true;
        try {
            await Api.post(`/financeiro/acordos/${acordo.id}/encerrar`, { fim });
            modal.remove();
            Toast.sucesso("Acordo encerrado.");
            aoSalvar();
        } catch (err) { ev.target.disabled = false; Toast.erro(err.message); }
    });
}

const _FIC_TIPOS = [
    { tipo: "avulsa", icone: "🧾", nome: "Por sessão", texto: "Cobra cada consulta, a cada 15 dias ou por mês." },
    { tipo: "mensalidade", icone: "📅", nome: "Mensalidade", texto: "Valor fixo por mês, com dia de vencimento." },
    { tipo: "pacote", icone: "🎟️", nome: "Pacote", texto: "Quantidade de sessões por um valor, em parcelas." },
];

// Criar (sem `acordo`) ou editar (com `acordo`) um acordo do paciente.
// opcoes: { especialidade?, acordo?, aoSalvar? }
function abrirModalAcordo(pacienteId, opcoes) {
    const op = opcoes || {};
    const editando = !!op.acordo;
    const hoje = paraChaveDia(new Date());
    const org = (Sessao.usuario && Sessao.usuario.organizacao) || {};
    let especialidades = (org.especialidades || []).slice();
    if (!especialidades.length) especialidades = ["Geral"];
    if (op.especialidade && op.especialidade !== "*" && !especialidades.includes(op.especialidade)) especialidades.push(op.especialidade);
    const espInicial = op.especialidade || especialidades[0];

    const estado = { tipo: editando ? op.acordo.tipo : "avulsa" };
    const modal = el(`
    <div class="modal-fundo" data-modal-preparado="1" data-modal-formulario="1">
      <div class="modal-caixa modal-grande">
        <h3 style="margin-bottom:12px;">${editando ? "Editar acordo" : "Novo acordo de pagamento"}</h3>
        ${editando ? `<p class="texto-sm texto-suave" style="margin-bottom:12px;">${escapeHtml(rotuloEspecialidadeAcordo(op.acordo.especialidade))} · ${escapeHtml(rotuloAcordo(op.acordo))}<br />A mudança vale dali para frente; o que já virou cobrança não muda${op.acordo.tipo === "mensalidade" ? " (só o fim: a cobrança do mês afetado acompanha a data)" : ""}.</p>` : `
        <div class="linha gap-2" id="fic-tipos" style="flex-wrap:wrap; margin-bottom:14px;">
          ${_FIC_TIPOS.map(t => `
            <button type="button" class="botao botao-secundario fic-tipo" data-tipo="${t.tipo}" aria-pressed="false" style="flex:1; min-width:150px; text-align:left; white-space:normal; display:block;">
              <div style="font-weight:700;">${t.icone} ${escapeHtml(t.nome)}</div>
              <div class="texto-xs texto-suave" style="font-weight:400;">${escapeHtml(t.texto)}</div>
            </button>`).join("")}
        </div>
        <div class="campo"><label for="fic-esp">Especialidade</label>
          <select id="fic-esp">
            ${especialidades.map(e => `<option value="${escapeHtml(e)}" ${e === espInicial ? "selected" : ""}>${escapeHtml(e)}</option>`).join("")}
            <option value="*" ${espInicial === "*" ? "selected" : ""}>Todas as especialidades</option>
          </select></div>
        <div class="linha gap-3" style="flex-wrap:wrap;">
          <div class="campo" style="flex:1; min-width:150px;"><label for="fic-inicio">Início</label><input type="date" id="fic-inicio" value="${hoje}" /></div>
          <div class="campo" style="flex:1; min-width:150px;"><label for="fic-fim">Fim (opcional)</label><input type="date" id="fic-fim" /></div>
        </div>`}
        ${editando ? `<div class="campo"><label for="fic-fim">Fim (opcional)</label><input type="date" id="fic-fim" value="${op.acordo.fim ? escapeHtml(String(op.acordo.fim).slice(0, 10)) : ""}" /></div>` : ""}
        <div id="fic-campos-tipo"></div>
        <div class="campo"><label for="fic-vence">Dias para vencer depois do fim do período</label>
          <input type="number" id="fic-vence" min="0" max="60" value="${editando ? (op.acordo.vence_dias != null ? op.acordo.vence_dias : 5) : 5}" style="max-width:120px;" /></div>
        <div id="fic-sem-acordo"></div>
        <div class="linha gap-3" style="justify-content:flex-end; margin-top:14px;">
          <button type="button" class="botao botao-secundario" data-fechar>Cancelar</button>
          <button type="button" class="botao botao-primario" id="fic-salvar">${editando ? "Salvar" : "Criar acordo"}</button>
        </div>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.querySelector("[data-fechar]").addEventListener("click", () => modal.remove());

    const q = (id) => modal.querySelector(id);

    function desenharCamposTipo() {
        const a = editando ? op.acordo : {};
        let html = "";
        if (estado.tipo === "avulsa") {
            html = editando ? "" : `
              <div class="campo"><label for="fic-ciclo">Quando cobrar</label>
                <select id="fic-ciclo">
                  <option value="consulta">A cada consulta</option>
                  <option value="quinzenal">A cada 15 dias (quinzenal)</option>
                  <option value="mensal">Uma vez por mês</option>
                </select></div>`;
        } else if (estado.tipo === "mensalidade") {
            html = `
              <div class="linha gap-3" style="flex-wrap:wrap;">
                <div class="campo" style="flex:1; min-width:150px;"><label for="fic-valor">Valor da mensalidade (R$)</label>
                  <input type="text" id="fic-valor" inputmode="decimal" placeholder="0,00" value="${a.valor_centavos ? _ficReais(a.valor_centavos) : ""}" /></div>
                <div class="campo" style="flex:1; min-width:150px;"><label for="fic-dia">Dia do vencimento (1 a 28)</label>
                  <input type="number" id="fic-dia" min="1" max="28" value="${a.dia_vencimento || ""}" /></div>
              </div>
              ${editando ? "" : `<p class="texto-xs texto-suave" style="margin-bottom:8px;">Mês incompleto (início no meio do mês) paga o valor proporcional aos dias.</p>`}`;
        } else {
            html = `
              <div class="linha gap-3" style="flex-wrap:wrap;">
                <div class="campo" style="flex:1; min-width:120px;"><label for="fic-sessoes">Sessões</label><input type="number" id="fic-sessoes" min="1" max="200" /></div>
                <div class="campo" style="flex:1; min-width:140px;"><label for="fic-valor">Valor do pacote (R$)</label><input type="text" id="fic-valor" inputmode="decimal" placeholder="0,00" /></div>
                <div class="campo" style="flex:1; min-width:100px;"><label for="fic-parcelas">Parcelas</label><input type="number" id="fic-parcelas" min="1" max="24" value="1" /></div>
                <div class="campo" style="flex:1; min-width:150px;"><label for="fic-primeiro">Primeiro vencimento</label><input type="date" id="fic-primeiro" /></div>
              </div>`;
        }
        q("#fic-campos-tipo").innerHTML = html;
        if (!editando) {
            modal.querySelectorAll(".fic-tipo").forEach(b => {
                const sel = b.dataset.tipo === estado.tipo;
                b.classList.toggle("botao-primario", sel);
                b.classList.toggle("botao-secundario", !sel);
                b.setAttribute("aria-pressed", sel ? "true" : "false");
            });
        }
    }

    // Sessões sem acordo (só ao criar): nada marcado por padrão. Só entra no acordo novo o que
    // a pessoa marcar, vendo quantas sessões e quanto somam; a desmarcada continua nas pendências.
    let tokenBusca = 0;
    async function carregarSemAcordo() {
        if (editando) return;
        const alvo = q("#fic-sem-acordo");
        const esp = q("#fic-esp").value;
        const meu = ++tokenBusca;
        alvo.innerHTML = `<p class="texto-xs texto-suave">Procurando sessões sem acordo…</p>`;
        let lista;
        try {
            const sufixo = esp && esp !== "*" ? `?especialidade=${encodeURIComponent(esp)}` : "";
            lista = await Api.get(`/financeiro/paciente/${pacienteId}/sem-acordo${sufixo}`);
        } catch (err) {
            if (meu === tokenBusca) alvo.innerHTML = "";
            return;
        }
        if (meu !== tokenBusca || !alvo.isConnected) return;
        if (!lista.length) { alvo.innerHTML = `<p class="texto-xs texto-suave">Nenhuma sessão feita sem acordo para esta especialidade.</p>`; return; }
        alvo.innerHTML = `
          <div class="cartao-flat" style="margin-top:6px;">
            <p class="texto-sm" style="font-weight:700; margin-bottom:2px;">Sessões já feitas, sem acordo (${lista.length})</p>
            <p class="texto-xs texto-suave" style="margin-bottom:6px;">Marque as que devem entrar neste acordo. As outras continuam sem acordo, nas pendências. Na mensalidade, a marcada fica coberta; no pacote, usa uma sessão; por sessão, entra numa cobrança.</p>
            ${lista.map(s => `
              <label class="linha gap-2" style="padding:3px 0; align-items:center;">
                <input type="checkbox" class="fic-incluir" value="${s.consulta_id}" />
                <span class="texto-sm">${formatarDataHoraLocal(s.data_hora)} · ${escapeHtml(s.especialidade || "Geral")}${s.procedimento_nome ? ` · ${escapeHtml(s.procedimento_nome)}` : ""}${s.valor_centavos ? ` · ${formatarMoeda(s.valor_centavos)}` : ""}</span>
              </label>`).join("")}
            <p class="texto-sm" id="fic-incluir-resumo" aria-live="polite" style="font-weight:700; margin-top:8px;"></p>
          </div>`;
        const resumo = alvo.querySelector("#fic-incluir-resumo");
        const atualizar = () => {
            const marcados = [...alvo.querySelectorAll(".fic-incluir:checked")].map(x => parseInt(x.value, 10));
            resumo.textContent = textoSessoesMarcadas(resumoSessoesMarcadas(lista, marcados));
        };
        alvo.querySelectorAll(".fic-incluir").forEach(x => x.addEventListener("change", atualizar));
        atualizar();
    }

    desenharCamposTipo();
    if (!editando) {
        modal.querySelectorAll(".fic-tipo").forEach(b => b.addEventListener("click", () => { estado.tipo = b.dataset.tipo; desenharCamposTipo(); }));
        q("#fic-esp").addEventListener("change", carregarSemAcordo);
        carregarSemAcordo();
    }

    q("#fic-salvar").addEventListener("click", async (ev) => {
        const valorTxt = q("#fic-valor") ? q("#fic-valor").value.trim() : "";
        const valor = valorTxt ? lerValorReais(valorTxt) : null;
        if (valorTxt && valor === null) { Toast.erro("Valor inválido. Use o formato 150,00."); return; }
        const vence = q("#fic-vence").value;
        const fim = q("#fic-fim").value;
        const num = (id) => (q(id) && q(id).value !== "" ? Number(q(id).value) : null);
        if (editando) {
            const corpo = { fim: fim || null };
            if (vence !== "") corpo.vence_dias = Number(vence);
            if (estado.tipo === "mensalidade") {
                if (valor === null) { Toast.erro("Informe o valor da mensalidade."); return; }
                corpo.valor_centavos = valor;
                corpo.dia_vencimento = num("#fic-dia");
            }
            ev.target.disabled = true;
            try {
                await Api.put(`/financeiro/acordos/${op.acordo.id}`, corpo);
                modal.remove();
                Toast.sucesso("Acordo atualizado.");
                if (op.aoSalvar) op.aoSalvar();
            } catch (err) { ev.target.disabled = false; Toast.erro(err.message); }
            return;
        }
        const form = { tipo: estado.tipo, especialidade: q("#fic-esp").value, inicio: q("#fic-inicio").value, fim };
        if (vence !== "") form.vence_dias = Number(vence);
        if (estado.tipo === "avulsa") form.ciclo = q("#fic-ciclo").value;
        else if (estado.tipo === "mensalidade") { form.valor_centavos = valor; form.dia_vencimento = num("#fic-dia"); }
        else {
            form.sessoes_total = num("#fic-sessoes"); form.valor_centavos = valor;
            form.parcelas = num("#fic-parcelas"); form.primeiro_vencimento = q("#fic-primeiro").value;
        }
        const msg = validarAcordo(form);
        if (msg) { Toast.erro(msg); return; }
        const corpo = { ...form };
        if (!corpo.fim) delete corpo.fim;
        if (!corpo.inicio) delete corpo.inicio;
        corpo.incluir_consultas = [...modal.querySelectorAll(".fic-incluir:checked")].map(x => parseInt(x.value, 10));
        ev.target.disabled = true;
        try {
            await Api.post(`/financeiro/paciente/${pacienteId}/acordos`, corpo);
            modal.remove();
            Toast.sucesso("Acordo criado.");
            if (op.aoSalvar) op.aoSalvar();
        } catch (err) { ev.target.disabled = false; Toast.erro(err.message); }
    });
}
