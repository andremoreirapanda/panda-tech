// ============================================================================
// views/admin.js — Administração do SaaS + Painel Comercial (Módulo 11)
// ============================================================================

const STATUS_COMERCIAL_INFO = {
    trial: { label: "Trial", badge: "marca" },
    ativa: { label: "Ativa", badge: "sucesso" },
    inadimplente: { label: "Inadimplente", badge: "alerta" },
    cancelada: { label: "Cancelada", badge: "neutro" },
};

async function viewAdminMonitoramento(app) {
    const m = await Api.get("/admin/monitoramento");

    const conteudo = `
    <div class="kpi-grade" style="margin-bottom:24px;">
      ${kpiCard("💰", formatarMoeda(m.mrr_total_centavos), "MRR (receita recorrente/mês)", "sucesso")}
      ${kpiCard("🏥", m.total_clinicas, "clínicas na plataforma", "marca")}
      ${kpiCard("⏳", m.qtd_trial, "em trial", "acento")}
      ${kpiCard("⚠️", m.qtd_inadimplentes, "inadimplentes", m.qtd_inadimplentes > 0 ? "alerta" : "sucesso")}
    </div>

    ${m.mrr_em_risco_centavos > 0 ? `
    <div class="cartao" style="margin-bottom:20px; border-color:var(--cor-alerta); background:var(--cor-alerta-clara);">
      <p class="texto-sm" style="font-weight:700; color:var(--cor-alerta);">
        🔴 ${formatarMoeda(m.mrr_em_risco_centavos)}/mês em risco — clínicas inadimplentes que podem cancelar.
      </p>
    </div>` : ""}

    <div class="grade grade-dupla" style="margin-bottom:24px;">
      <div class="cartao">
        <h3 style="margin-bottom:14px;">⏰ Trials vencendo em breve</h3>
        ${m.trials_vencendo.length ? `
        <div class="lista-pessoas">
          ${m.trials_vencendo.map(c => `
            <a href="#/admin/clinicas" class="pessoa-linha">
              <div class="pessoa-avatar">${escapeHtml(c.logo_emoji)}</div>
              <div class="pessoa-info"><div class="pessoa-nome">${escapeHtml(c.nome)}</div><div class="pessoa-sub">${escapeHtml(c.contato_nome || "")}</div></div>
              <span class="badge ${c.dias_restantes_trial <= 2 ? "badge-alerta" : "badge-aviso"}">${c.dias_restantes_trial <= 0 ? "vencido" : c.dias_restantes_trial + " dia(s)"}</span>
            </a>`).join("")}
        </div>` : `<p class="texto-sm texto-suave">Nenhum trial vencendo nos próximos 5 dias.</p>`}
      </div>
      <div class="cartao">
        <h3 style="margin-bottom:14px;">📈 Oportunidades de upsell</h3>
        ${m.oportunidades_upsell.length ? `
        <div class="lista-pessoas">
          ${m.oportunidades_upsell.map(c => `
            <a href="#/admin/clinicas" class="pessoa-linha">
              <div class="pessoa-avatar">${escapeHtml(c.logo_emoji)}</div>
              <div class="pessoa-info"><div class="pessoa-nome">${escapeHtml(c.nome)}</div><div class="pessoa-sub">Plano ${escapeHtml(c.plano_nome)}</div></div>
              <span class="badge badge-aviso">${c.uso_profissionais_pct}% do limite de profissionais</span>
            </a>`).join("")}
        </div>` : `<p class="texto-sm texto-suave">Nenhuma clínica perto do limite do plano no momento.</p>`}
      </div>
    </div>

    <div class="cartao">
      <h3 style="margin-bottom:14px;">Receita por plano</h3>
      <div class="lista-pessoas">
        ${m.clinicas_por_plano.map(p => `
          <div class="pessoa-linha">
            <div class="pessoa-info"><div class="pessoa-nome">${escapeHtml(p.plano_nome)}</div><div class="pessoa-sub">${p.total} clínica(s) pagante(s)</div></div>
            <span class="badge badge-sucesso">${formatarMoeda(p.mrr_centavos)}/mês</span>
          </div>`).join("")}
      </div>
      <div class="linha-entre" style="margin-top:16px; padding-top:16px; border-top:1px solid var(--cor-borda);">
        <span class="texto-sm texto-suave">${m.total_pacientes} pacientes atendidos · ${m.total_missoes_concluidas} missões concluídas (todas as clínicas)</span>
      </div>
    </div>`;

    app.innerHTML = renderShellSidebar("#/admin/monitoramento", "Painel Comercial", conteudo);
    anexarEventosShell();
}

async function viewAdminClinicas(app) {
    const [clinicas, planos, modulosDisponiveis] = await Promise.all([
        Api.get("/admin/clinicas"), Api.get("/admin/planos"), Api.get("/admin/modulos-disponiveis"),
    ]);
    const conteudo = `
    <div class="grade" style="grid-template-columns: repeat(auto-fill, minmax(260px,1fr));">
      ${clinicas.map(c => renderCartaoClinica(c)).join("")}
    </div>`;

    app.innerHTML = renderShellSidebar("#/admin/clinicas", "Clínicas na Plataforma", conteudo,
        `<button class="botao botao-primario botao-sm" id="btn-nova-clinica">+ Nova Clínica</button>`);
    anexarEventosShell();

    document.querySelectorAll(".btn-abrir-clinica").forEach(btn => btn.addEventListener("click", () => {
        const clinica = clinicas.find(c => c.id === Number(btn.dataset.id));
        abrirModalDetalheClinica(clinica, planos, modulosDisponiveis);
    }));

    document.getElementById("btn-nova-clinica").addEventListener("click", () => abrirModalNovaClinica(planos));
}

function renderCartaoClinica(c) {
    const info = STATUS_COMERCIAL_INFO[c.status_comercial] || { label: c.status_comercial, badge: "neutro" };
    return `
    <div class="cartao">
      <div class="linha-entre" style="margin-bottom:10px;">
        <span style="font-size:28px;">${escapeHtml(c.logo_emoji)}</span>
        <div class="linha gap-2">
          <span class="badge badge-${info.badge}">${info.label}</span>
          <span class="badge" style="background:${corSegura(c.plano_cor, "#6A6280")}22; color:${corSegura(c.plano_cor, "#6A6280")};">${escapeHtml(c.plano_nome)}</span>
        </div>
      </div>
      <h3 style="font-size:16px;">${escapeHtml(c.nome)}</h3>
      <p class="texto-xs texto-suave" style="margin-top:2px;">${escapeHtml(c.contato_nome || "Sem contato cadastrado")}</p>

      <div class="linha-entre" style="margin-top:14px;">
        <span class="texto-sm texto-suave">${c.total_profissionais} profissionais · ${c.total_pacientes} pacientes</span>
        <strong class="texto-sm">${c.mrr_centavos ? formatarMoeda(c.mrr_centavos) + "/mês" : "—"}</strong>
      </div>

      ${c.uso_profissionais_pct !== null && c.uso_profissionais_pct !== undefined ? `
      <div class="progresso-barra" style="margin-top:10px;">
        <div class="progresso-preenchimento" style="width:${Math.min(100, c.uso_profissionais_pct)}%; ${c.uso_profissionais_pct >= 80 ? "background:var(--cor-aviso);" : ""}"></div>
      </div>
      <p class="texto-xs texto-suave" style="margin-top:4px;">${c.uso_profissionais_pct}% do limite de profissionais do plano</p>` : ""}

      ${c.dias_restantes_trial !== null ? `<p class="texto-xs" style="margin-top:8px; color:var(--cor-marca-escura); font-weight:700;">⏰ Trial: ${c.dias_restantes_trial} dia(s) restante(s)</p>` : ""}

      <button class="botao botao-secundario botao-sm btn-abrir-clinica" data-id="${c.id}" style="width:100%; margin-top:14px;">Ver detalhes comerciais</button>
    </div>`;
}

// Planos configuráveis (25/09/2026): só planos ativos e dentro da validade
// podem ser atribuídos; o plano atual da clínica aparece mesmo se vencido.
function planosAtribuiveis(planos, codigoAtual) {
    return planos.filter(p => (p.ativo && !p.promocao_encerrada) || p.codigo === codigoAtual);
}

function renderModulosDaClinica(c, modulosDisponiveis) {
    const doPlano = new Set((c.modulos && c.modulos.do_plano) || []);
    const extras = new Set((c.modulos && c.modulos.extras) || []);
    return `
    <div class="cartao-flat" style="margin-bottom:18px;">
      <p class="texto-sm" style="font-weight:700; margin-bottom:4px;">🧩 Módulos da clínica</p>
      <p class="texto-xs texto-suave" style="margin-bottom:10px;">Os do plano vêm marcados. "Extra" libera um módulo só para esta clínica, fora do plano.</p>
      ${modulosDisponiveis.map(m => `
      <div class="linha-entre" style="gap:8px; padding:6px 0; border-top:1px solid var(--cor-borda);">
        <span class="texto-sm">${m.icone} ${escapeHtml(m.nome)}</span>
        ${doPlano.has(m.codigo)
            ? `<span class="badge badge-sucesso">✓ do plano</span>`
            : `<label class="linha gap-2" style="align-items:center;"><span class="texto-xs texto-suave">Extra</span>
                 <span class="chave-toggle"><input type="checkbox" class="chk-modulo-extra" data-codigo="${m.codigo}" ${extras.has(m.codigo) ? "checked" : ""} /><span class="chave-slider"></span></span>
               </label>`}
      </div>`).join("")}
    </div>`;
}

function abrirModalDetalheClinica(c, planos = [], modulosDisponiveis = []) {
    const info = STATUS_COMERCIAL_INFO[c.status_comercial] || { label: c.status_comercial, badge: "neutro" };
    const especialidadesAtuais = c.especialidades || [];
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa modal-grande">
        <div class="linha-entre" style="margin-bottom:6px;">
          <h3>${escapeHtml(c.logo_emoji)} ${escapeHtml(c.nome)}</h3>
          <span class="badge badge-${info.badge}">${info.label}</span>
        </div>
        <p class="texto-sm texto-suave" style="margin-bottom:18px;">
          Plano ${escapeHtml(c.plano_nome)} · ${c.total_pacientes} pacientes · ${c.total_profissionais} profissionais
          ${c.mrr_centavos ? " · " + formatarMoeda(c.mrr_centavos) + "/mês" : ""}
        </p>
        ${(c.gestores || []).length ? `
        <div class="cartao-flat" style="margin-bottom:18px;">
          <p class="texto-sm" style="font-weight:700; margin-bottom:8px;">👤 Acesso do gestor</p>
          ${c.gestores.map(gst => `
          <div class="linha-entre" style="gap:8px; margin-bottom:6px;">
            <span class="texto-sm">${escapeHtml(gst.nome)} <span class="texto-xs texto-suave">${escapeHtml(gst.email)}</span></span>
            <button type="button" class="botao botao-secundario botao-sm btn-reenviar-convite-gestor" data-id="${gst.id}">🔗 Reenviar link de acesso</button>
          </div>`).join("")}
          <p class="texto-xs texto-suave" style="margin-top:4px;">Gera um novo link para o gestor ativar a conta ou redefinir a senha.</p>
        </div>` : ""}
        ${modulosDisponiveis.length ? renderModulosDaClinica(c, modulosDisponiveis) : ""}
        <form id="form-comercial">
          <p class="texto-sm" style="font-weight:700; margin-bottom:10px;">📊 Dados comerciais</p>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Status comercial</label>
              <select id="cm-status">
                ${Object.entries(STATUS_COMERCIAL_INFO).map(([v, i]) => `<option value="${v}" ${c.status_comercial === v ? "selected" : ""}>${i.label}</option>`).join("")}
              </select>
            </div>
            <div class="campo" style="flex:1;"><label>Origem do lead</label>
              <select id="cm-origem">
                ${["indicação", "inbound", "outbound", "evento"].map(o => `<option value="${o}" ${c.origem_lead === o ? "selected" : ""}>${o}</option>`).join("")}
              </select>
            </div>
          </div>
          <div class="campo">
            <label>Plano comercial</label>
            <select id="cm-plano">
              ${planosAtribuiveis(planos, c.plano).map(p => `<option value="${p.codigo}" ${c.plano === p.codigo ? "selected" : ""}>${escapeHtml(p.nome)} — ${formatarMoeda(p.preco_mensal_centavos)}/mês${p.promocao_encerrada ? " (promoção encerrada)" : ""}</option>`).join("")}
            </select>
            <p class="texto-xs texto-suave" style="margin-top:4px;">Muda o valor da próxima cobrança automática (MRR já reflete na hora).</p>
          </div>
          <div class="campo"><label>Contato (decisor na clínica)</label><input type="text" id="cm-contato-nome" value="${escapeHtml(c.contato_nome || "")}" /></div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>E-mail do contato</label><input type="email" id="cm-contato-email" value="${escapeHtml(c.contato_email || "")}" /></div>
            <div class="campo" style="flex:1;"><label>Telefone</label><input type="tel" id="cm-contato-telefone" value="${escapeHtml(c.contato_telefone || "")}" /></div>
          </div>
          <div class="campo"><label>Observações do time comercial</label><textarea id="cm-observacoes" rows="2">${escapeHtml(c.observacoes_comerciais || "")}</textarea></div>

          <hr style="border:none; border-top:1px solid var(--cor-borda); margin:18px 0;" />
          <p class="texto-sm" style="font-weight:700; margin-bottom:10px;">🏢 Dados institucionais</p>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>CNPJ</label><input type="text" id="in-cnpj" value="${escapeHtml(c.cnpj || "")}" placeholder="00.000.000/0000-00" /></div>
            <div class="campo" style="flex:1;"><label>Telefone da clínica</label><input type="tel" id="in-telefone" value="${escapeHtml(c.telefone || "")}" /></div>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>CEP</label><input type="text" id="in-cep" value="${escapeHtml(c.endereco_cep || "")}" /></div>
            <div class="campo" style="flex:2;"><label>Logradouro</label><input type="text" id="in-logradouro" value="${escapeHtml(c.endereco_logradouro || "")}" /></div>
            <div class="campo" style="flex:1;"><label>Número</label><input type="text" id="in-numero" value="${escapeHtml(c.endereco_numero || "")}" /></div>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Bairro</label><input type="text" id="in-bairro" value="${escapeHtml(c.endereco_bairro || "")}" /></div>
            <div class="campo" style="flex:1;"><label>Cidade</label><input type="text" id="in-cidade" value="${escapeHtml(c.endereco_cidade || "")}" /></div>
            <div class="campo" style="flex:0 0 80px;"><label>UF</label><input type="text" id="in-uf" value="${escapeHtml(c.endereco_uf || "")}" maxlength="2" style="text-transform:uppercase;" /></div>
          </div>
          <p class="texto-sm" style="font-weight:700; margin:14px 0 8px;">Especialidades</p>
          <p class="texto-xs texto-suave" style="margin-bottom:8px;">Digite e adicione — sem lista fixa, cada clínica tem seu próprio nicho.</p>
          ${renderCampoTagsEspecialidade("in-esp", especialidadesAtuais)}

          <div class="linha gap-3" style="margin-top:16px;">
            <button type="submit" class="botao botao-primario">Salvar</button>
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Fechar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    modal.querySelectorAll(".btn-reenviar-convite-gestor").forEach(btn => btn.addEventListener("click", async () => {
        const gestor = c.gestores.find(gst => gst.id === Number(btn.dataset.id));
        btn.disabled = true;
        try {
            const r = await Api.post(`/admin/clinicas/${c.id}/gestores/${gestor.id}/reenviar-convite`);
            modal.remove();
            mostrarModalConvite(r.link_convite, gestor.nome);
        } catch (err) { Toast.erro(err.message); btn.disabled = false; }
    }));
    modal.querySelectorAll(".chk-modulo-extra").forEach(chk => chk.addEventListener("change", async () => {
        const codigo = chk.dataset.codigo;
        try {
            await Api.put(`/admin/clinicas/${c.id}/modulos/${codigo}`, { liberado: chk.checked });
            c.modulos = c.modulos || { do_plano: [], extras: [] };
            c.modulos.extras = chk.checked ? [...new Set([...c.modulos.extras, codigo])] : c.modulos.extras.filter(x => x !== codigo);
            Toast.sucesso(chk.checked ? "Módulo liberado como extra." : "Extra removido.");
        } catch (err) {
            chk.checked = !chk.checked;
            Toast.erro(err.message);
        }
    }));
    ativarMascaraCampo(document.getElementById("cm-contato-telefone"), "telefone");
    ativarMascaraCampo(document.getElementById("in-telefone"), "telefone");
    ativarMascaraCampo(document.getElementById("in-cnpj"), "cnpj");
    ativarMascaraCampo(document.getElementById("in-cep"), "cep");
    ativarAutoCompleteCep("in");
    const obterEspecialidades = ativarCampoTagsEspecialidade("in-esp", especialidadesAtuais);
    document.getElementById("form-comercial").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            const novoPlano = document.getElementById("cm-plano").value;
            await Promise.all([
                Api.put(`/admin/clinicas/${c.id}/comercial`, {
                    status_comercial: document.getElementById("cm-status").value,
                    origem_lead: document.getElementById("cm-origem").value,
                    contato_nome: document.getElementById("cm-contato-nome").value.trim(),
                    contato_email: document.getElementById("cm-contato-email").value.trim(),
                    contato_telefone: document.getElementById("cm-contato-telefone").value.trim(),
                    observacoes_comerciais: document.getElementById("cm-observacoes").value.trim(),
                }),
                ...(novoPlano !== c.plano ? [Api.put(`/admin/clinicas/${c.id}/plano`, { plano: novoPlano })] : []),
                Api.put(`/admin/clinicas/${c.id}/institucional`, {
                    cnpj: document.getElementById("in-cnpj").value.trim(),
                    telefone: document.getElementById("in-telefone").value.trim(),
                    endereco_cep: document.getElementById("in-cep").value.trim(),
                    endereco_logradouro: document.getElementById("in-logradouro").value.trim(),
                    endereco_numero: document.getElementById("in-numero").value.trim(),
                    endereco_bairro: document.getElementById("in-bairro").value.trim(),
                    endereco_cidade: document.getElementById("in-cidade").value.trim(),
                    endereco_uf: document.getElementById("in-uf").value.trim().toUpperCase(),
                    especialidades: obterEspecialidades(),
                }),
            ]);
            Toast.sucesso("Dados atualizados!");
            modal.remove();
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });
}

function abrirModalNovaClinica(planos = []) {
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa" style="max-width:600px;">
        <h3 style="margin-bottom:18px;">Cadastrar nova clínica</h3>
        <form id="form-nova-clinica">
          <div class="campo"><label>Nome da clínica ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="nc-nome" required /></div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Plano ${ASTERISCO_OBRIGATORIO}</label>
              <select id="nc-plano" required>
                ${planosAtribuiveis(planos, null).map(p => `<option value="${p.codigo}">${escapeHtml(p.nome)} — ${formatarMoeda(p.preco_mensal_centavos)}/mês</option>`).join("")}
              </select>
            </div>
            <div class="campo" style="flex:1;"><label>Dias de trial</label><input type="number" id="nc-dias-trial" value="14" min="0" max="90" /></div>
          </div>

          <hr style="border:none; border-top:1px solid var(--cor-borda); margin:16px 0;" />
          <p class="texto-sm" style="font-weight:700; margin-bottom:10px;">Dados institucionais (opcional agora, dá pra completar depois)</p>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>CNPJ</label><input type="text" id="nc-cnpj" placeholder="00.000.000/0000-00" /></div>
            <div class="campo" style="flex:1;"><label>Telefone da clínica</label><input type="tel" id="nc-telefone" /></div>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>CEP</label><input type="text" id="nc-cep" placeholder="00000-000" /></div>
            <div class="campo" style="flex:2;"><label>Logradouro</label><input type="text" id="nc-logradouro" placeholder="Rua, Av..." /></div>
            <div class="campo" style="flex:1;"><label>Número</label><input type="text" id="nc-numero" /></div>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Bairro</label><input type="text" id="nc-bairro" /></div>
            <div class="campo" style="flex:1;"><label>Cidade</label><input type="text" id="nc-cidade" /></div>
            <div class="campo" style="flex:0 0 80px;"><label>UF</label><input type="text" id="nc-uf" maxlength="2" style="text-transform:uppercase;" /></div>
          </div>

          <p class="texto-sm" style="font-weight:700; margin:12px 0 10px;">Especialidades</p>
          <p class="texto-xs texto-suave" style="margin-bottom:8px;">Digite e adicione — sem lista fixa, qualquer nicho é aceito.</p>
          ${renderCampoTagsEspecialidade("nc-esp", [])}

          <hr style="border:none; border-top:1px solid var(--cor-borda); margin:16px 0;" />
          <p class="texto-sm" style="font-weight:700; margin-bottom:10px;">Conta do gestor responsável</p>
          <div class="campo"><label>Nome ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="nc-gestor-nome" required /></div>
          <div class="campo"><label>E-mail ${ASTERISCO_OBRIGATORIO}</label><input type="email" id="nc-gestor-email" required /></div>
          <div class="campo"><label>Origem do lead</label>
            <select id="nc-origem">${["indicação", "inbound", "outbound", "evento"].map(o => `<option value="${o}">${o}</option>`).join("")}</select>
          </div>
          <div class="linha gap-3" style="margin-top:16px;">
            <button type="submit" class="botao botao-primario">Criar clínica</button>
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    ativarMascaraCampo(document.getElementById("nc-telefone"), "telefone");
    ativarMascaraCampo(document.getElementById("nc-cnpj"), "cnpj");
    ativarMascaraCampo(document.getElementById("nc-cep"), "cep");
    ativarAutoCompleteCep("nc");
    const obterEspecialidadesNc = ativarCampoTagsEspecialidade("nc-esp", []);
    document.getElementById("form-nova-clinica").addEventListener("submit", async (e) => {
        e.preventDefault();
        const gestorNome = document.getElementById("nc-gestor-nome").value.trim();
        const especialidades = obterEspecialidadesNc();
        const r = await Api.post("/admin/clinicas", {
            nome: document.getElementById("nc-nome").value.trim(),
            plano: document.getElementById("nc-plano").value,
            dias_trial: parseInt(document.getElementById("nc-dias-trial").value) || 14,
            cnpj: document.getElementById("nc-cnpj").value.trim(),
            telefone: document.getElementById("nc-telefone").value.trim(),
            endereco_cep: document.getElementById("nc-cep").value.trim(),
            endereco_logradouro: document.getElementById("nc-logradouro").value.trim(),
            endereco_numero: document.getElementById("nc-numero").value.trim(),
            endereco_bairro: document.getElementById("nc-bairro").value.trim(),
            endereco_cidade: document.getElementById("nc-cidade").value.trim(),
            endereco_uf: document.getElementById("nc-uf").value.trim().toUpperCase(),
            especialidades,
            gestor_nome: gestorNome,
            gestor_email: document.getElementById("nc-gestor-email").value.trim(),
            origem_lead: document.getElementById("nc-origem").value,
        });
        modal.remove();
        Toast.sucesso("Clínica criada!");
        mostrarModalConvite(r.link_convite, gestorNome);
    });
}

// ---------------------------------------------------------------- Planos comerciais

async function viewAdminPlanos(app) {
    // Planos configuráveis (25/09/2026): o Admin cria/edita planos e escolhe
    // os módulos com caixas de seleção; um plano pode herdar de outro.
    const [planos, modulos] = await Promise.all([Api.get("/admin/planos?incluir_inativos=1"), Api.get("/admin/modulos-disponiveis")]);
    const nomeModulo = (codigo) => { const m = modulos.find(x => x.codigo === codigo); return m ? `${m.icone} ${m.nome}` : codigo; };
    const textoLimite = (v, rotulo, zero) => v === null || v === undefined ? `${rotulo} ilimitados` : (v === 0 && zero ? zero : `${v} ${rotulo.toLowerCase()}`);
    const conteudo = `
    <div class="grade" style="grid-template-columns: repeat(auto-fit, minmax(280px,1fr));">
      ${planos.map(p => `
        <div class="cartao" style="border-top:4px solid ${corSegura(p.cor, "#5B4FE9")}; ${p.ativo ? "" : "opacity:.6;"}">
          <div class="linha-entre" style="margin-bottom:4px;">
            <h3 style="font-size:18px;">${escapeHtml(p.nome)}</h3>
            <button class="botao-icone btn-editar-plano" data-codigo="${escapeHtml(p.codigo)}" title="Editar plano">✏️</button>
          </div>
          <div class="linha gap-2" style="flex-wrap:wrap; margin-bottom:6px;">
            ${p.plano_base_nome ? `<span class="badge badge-neutro">herda de ${escapeHtml(p.plano_base_nome)}</span>` : ""}
            ${p.disponivel_ate ? `<span class="badge ${p.promocao_encerrada ? "badge-alerta" : "badge-aviso"}">${p.promocao_encerrada ? "Promoção encerrada" : "Promoção até " + formatarData(p.disponivel_ate)}</span>` : ""}
            ${p.ativo ? "" : `<span class="badge badge-neutro">Inativo</span>`}
          </div>
          <p style="font-size:26px; font-weight:700; font-family:var(--fonte-display); margin:8px 0;">
            ${formatarMoeda(p.preco_mensal_centavos)}<span class="texto-sm texto-suave" style="font-weight:500;">/mês</span>
          </p>
          <p class="texto-sm texto-suave" style="margin-bottom:10px;">
            Pacientes ilimitados · ${textoLimite(p.limite_profissionais, "Profissionais")} · ${textoLimite(p.limite_secretarias, "Secretárias", "Sem secretária")}
          </p>
          <p class="texto-xs texto-suave" style="margin-bottom:8px;">${p.total_clinicas} clínica(s) neste plano</p>
          <div class="linha gap-1" style="flex-wrap:wrap; margin-bottom:12px;">
            ${p.modulos_efetivos.length ? p.modulos_efetivos.map(c => `<span class="badge badge-marca">${escapeHtml(nomeModulo(c))}</span>`).join("") : `<span class="texto-xs texto-suave">Sem módulos opcionais</span>`}
          </div>
          <ul style="list-style:none; padding:0; margin:0; display:flex; flex-direction:column; gap:8px;">
            ${p.recursos.map(r => `<li class="texto-sm linha gap-2"><span style="color:${corSegura(p.cor, "#5B4FE9")};">✓</span> ${escapeHtml(r)}</li>`).join("")}
          </ul>
        </div>`).join("")}
    </div>`;

    app.innerHTML = renderShellSidebar("#/admin/planos", "Planos Comerciais", conteudo,
        `<button class="botao botao-primario botao-sm" id="btn-novo-plano">+ Novo plano</button>`);
    anexarEventosShell();

    document.getElementById("btn-novo-plano").addEventListener("click", () => abrirModalPlano(null, planos, modulos));
    document.querySelectorAll(".btn-editar-plano").forEach(btn => btn.addEventListener("click", () => {
        abrirModalPlano(planos.find(p => p.codigo === btn.dataset.codigo), planos, modulos);
    }));
}

// Ids dos planos que herdam (direta ou indiretamente) de `planoId` — não podem virar base dele (ciclo).
function _descendentesDoPlano(planoId, planos) {
    const filhos = planos.filter(p => p.plano_base_id === planoId).map(p => p.id);
    return filhos.reduce((acc, id) => acc.concat(id, _descendentesDoPlano(id, planos)), []);
}

function abrirModalPlano(p, planos, modulos) {
    const editando = !!p;
    p = p || { nome: "", preco_mensal_centavos: 0, limite_profissionais: null, limite_secretarias: 0, cor: "#5B4FE9",
               recursos: [], ativo: 1, plano_base_id: null, disponivel_ate: null, modulos_proprios: [] };
    const proibidos = editando ? new Set([p.id, ..._descendentesDoPlano(p.id, planos)]) : new Set();
    const basesPossiveis = planos.filter(x => x.ativo && !proibidos.has(x.id));
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa modal-grande">
        <h3 style="margin-bottom:18px;">${editando ? "Editar plano — " + escapeHtml(p.nome) : "Novo plano"}</h3>
        <form id="form-plano">
          <div class="linha gap-4">
            <div class="campo" style="flex:2;"><label>Nome do plano ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="pl-nome" value="${escapeHtml(p.nome)}" required /></div>
            <div class="campo" style="flex:1;"><label>Preço mensal (R$) ${ASTERISCO_OBRIGATORIO}</label><input type="number" id="pl-preco" value="${(p.preco_mensal_centavos / 100).toFixed(2)}" step="0.01" min="0" required /></div>
            <div class="campo" style="flex:0 0 90px;"><label>Cor</label><input type="color" id="pl-cor" value="${escapeHtml(corSegura(p.cor, "#5B4FE9"))}" /></div>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Limite de profissionais (vazio = ilimitado)</label><input type="number" id="pl-limite-prof" value="${p.limite_profissionais ?? ""}" min="1" /></div>
            <div class="campo" style="flex:1;"><label>Limite de secretárias (vazio = ilimitado, 0 = sem secretária)</label><input type="number" id="pl-limite-sec" value="${p.limite_secretarias ?? ""}" min="0" /></div>
          </div>
          <p class="texto-xs texto-suave" style="margin:-6px 0 12px;">Pacientes são ilimitados em todos os planos.</p>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Começar a partir do plano…</label>
              <select id="pl-base">
                <option value="">Nenhum (plano base)</option>
                ${basesPossiveis.map(b => `<option value="${b.id}" ${p.plano_base_id === b.id ? "selected" : ""}>${escapeHtml(b.nome)}</option>`).join("")}
              </select>
              <p class="texto-xs texto-suave" style="margin-top:4px;">Herda os módulos do plano escolhido (e o que for marcado lá depois).</p>
            </div>
            <div class="campo" style="flex:1;"><label>Disponível até</label>
              <input type="date" id="pl-validade" value="${escapeHtml(p.disponivel_ate || "")}" />
              <p class="texto-xs texto-suave" style="margin-top:4px;">Para promoções: depois dessa data não dá para escolher este plano para novas clínicas.</p>
            </div>
          </div>
          <p class="texto-sm" style="font-weight:700; margin:6px 0 8px;">🧩 Módulos</p>
          <div id="pl-modulos" class="coluna gap-1" style="margin-bottom:12px;"></div>
          <div class="campo">
            <label>Recursos exibidos no plano (um por linha)</label>
            <textarea id="pl-recursos" rows="5">${escapeHtml((p.recursos || []).join("\n"))}</textarea>
          </div>
          ${editando ? `<label class="linha gap-2" style="align-items:center; margin-bottom:12px;"><input type="checkbox" id="pl-ativo" ${p.ativo ? "checked" : ""} /> <span class="texto-sm">Plano ativo</span></label>` : ""}
          <div class="linha gap-3" style="margin-top:8px;">
            <button type="submit" class="botao botao-primario">${editando ? "Salvar plano" : "Criar plano"}</button>
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());

    const proprios = new Set(p.modulos_proprios || []);
    function renderModulos() {
        const baseId = parseInt(document.getElementById("pl-base").value) || null;
        const base = planos.find(x => x.id === baseId);
        const herdados = new Set(base ? base.modulos_efetivos : []);
        document.getElementById("pl-modulos").innerHTML = modulos.map(m => {
            const herdado = herdados.has(m.codigo);
            return `
            <label class="linha gap-2" style="align-items:flex-start; padding:6px 0; border-top:1px solid var(--cor-borda); ${herdado ? "opacity:.75;" : ""}">
              <input type="checkbox" class="chk-modulo-plano" data-codigo="${m.codigo}" ${herdado || proprios.has(m.codigo) ? "checked" : ""} ${herdado ? "disabled" : ""} style="margin-top:3px;" />
              <span><span class="texto-sm" style="font-weight:600;">${m.icone} ${escapeHtml(m.nome)}</span>
                ${herdado ? `<span class="badge badge-neutro" style="margin-left:6px;">vem do plano ${escapeHtml(base.nome)}</span>` : ""}
                <br><span class="texto-xs texto-suave">${escapeHtml(m.descricao)}</span></span>
            </label>`;
        }).join("");
        document.querySelectorAll(".chk-modulo-plano:not([disabled])").forEach(chk => chk.addEventListener("change", () => {
            chk.checked ? proprios.add(chk.dataset.codigo) : proprios.delete(chk.dataset.codigo);
        }));
    }
    renderModulos();
    document.getElementById("pl-base").addEventListener("change", renderModulos);

    document.getElementById("form-plano").addEventListener("submit", async (e) => {
        e.preventDefault();
        const limiteProf = document.getElementById("pl-limite-prof").value;
        const limiteSec = document.getElementById("pl-limite-sec").value;
        const baseId = parseInt(document.getElementById("pl-base").value) || null;
        const base = planos.find(x => x.id === baseId);
        const herdados = new Set(base ? base.modulos_efetivos : []);
        const body = {
            nome: document.getElementById("pl-nome").value.trim(),
            preco_mensal_centavos: Math.round(parseFloat(document.getElementById("pl-preco").value || "0") * 100),
            limite_profissionais: limiteProf ? parseInt(limiteProf) : null,
            limite_secretarias: limiteSec !== "" ? parseInt(limiteSec) : null,
            cor: document.getElementById("pl-cor").value,
            recursos: document.getElementById("pl-recursos").value.split("\n").map(x => x.trim()).filter(Boolean),
            plano_base_id: baseId,
            disponivel_ate: document.getElementById("pl-validade").value || null,
            modulos: [...proprios].filter(c => !herdados.has(c)),
        };
        if (editando) body.ativo = document.getElementById("pl-ativo").checked;
        try {
            if (editando) await Api.put(`/admin/planos/${p.codigo}`, body);
            else await Api.post("/admin/planos", body);
            Toast.sucesso(editando ? "Plano atualizado!" : "Plano criado!");
            modal.remove();
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });
}

// ---------------------------------------------------------------- Cobrança das clínicas pelo plano

const STATUS_COBRANCA_PLANO_INFO = {
    pendente: { label: "Pendente", badge: "aviso" },
    pago: { label: "Pago", badge: "sucesso" },
    cancelada: { label: "Cancelada", badge: "neutro" },
};

async function viewAdminCobrancasPlanos(app) {
    const [cobrancas, integracoes] = await Promise.all([Api.get("/admin/cobrancas-planos"), Api.get("/admin/integracoes")]);
    const mp = integracoes.find(i => i.tipo === "mercadopago") || {};

    const conteudo = `
    <div class="cartao" style="margin-bottom:20px; ${mp.cobranca_automatica_ativa ? "border-color:var(--cor-sucesso);" : ""}">
      <div class="linha-entre">
        <div>
          <p class="texto-sm" style="font-weight:700;">
            ${mp.cobranca_automatica_ativa ? "✅ Cobrança automática ligada" : "⏸️ Cobrança automática desligada"}
          </p>
          <p class="texto-xs texto-suave" style="margin-top:2px;">
            ${mp.cobranca_automatica_ativa
              ? "Toda clínica ativa/inadimplente recebe um PIX de assinatura automaticamente, uma vez por mês."
              : "Ligue em Integrações > Gateway de pagamento pra começar a cobrar as clínicas pelo plano."}
          </p>
        </div>
        <div class="linha gap-2">
          <a href="#/admin/integracoes" class="botao botao-secundario botao-sm">⚙️ Configurar</a>
          <button class="botao botao-secundario botao-sm" id="btn-cobranca-avulsa">+ Cobrança avulsa</button>
          <button class="botao botao-primario botao-sm" id="btn-gerar-cobrancas">Gerar cobranças agora</button>
        </div>
      </div>
    </div>

    <div class="cartao">
      <div class="tabela-wrap"><table class="tabela">
        <thead><tr><th>Clínica</th><th>Plano</th><th>Valor</th><th>Status</th><th>Gerada em</th><th>Ações</th></tr></thead>
        <tbody>
          ${cobrancas.length ? cobrancas.map(c => {
            const info = STATUS_COBRANCA_PLANO_INFO[c.status] || { label: c.status, badge: "neutro" };
            return `
            <tr>
              <td>${c.logo_emoji || "🏥"} ${escapeHtml(c.organizacao_nome)}</td>
              <td class="texto-sm">${c.descricao ? `${escapeHtml(c.descricao)} <span class="texto-xs texto-suave">(avulsa)</span>` : escapeHtml(c.plano_nome || c.plano_codigo)}</td>
              <td class="texto-sm">${formatarMoeda(c.valor_centavos)}</td>
              <td><span class="badge badge-${info.badge}">${info.label}</span></td>
              <td class="texto-sm texto-suave">${formatarDataHora(c.criado_em)}</td>
              <td>
                ${c.status === "pendente" ? `
                  ${c.pix_copia_cola ? `<button class="botao botao-secundario botao-sm btn-ver-pix" data-copia-cola="${escapeHtml(c.pix_copia_cola)}">Ver PIX</button> <button class="botao botao-secundario botao-sm btn-gerar-pix-plano" data-id="${c.id}" title="Gera um PIX novo para esta cobrança — use se o gateway de pagamento foi trocado ou se o código anterior expirou">🔄 Gerar novo PIX</button>` : `<button class="botao botao-secundario botao-sm btn-gerar-pix-plano" data-id="${c.id}">Gerar PIX</button>`}
                  <button class="botao botao-secundario botao-sm btn-marcar-pago-plano" data-id="${c.id}">Marcar pago</button>
                ` : ""}
              </td>
            </tr>`;
          }).join("") : `<tr><td colspan="6" class="texto-sm texto-suave">Nenhuma cobrança gerada ainda.</td></tr>`}
        </tbody>
      </table></div>
    </div>`;

    app.innerHTML = renderShellSidebar("#/admin/cobrancas-planos", "Cobranças das Clínicas", conteudo);
    anexarEventosShell();

    document.getElementById("btn-gerar-cobrancas").addEventListener("click", async (e) => {
        e.target.disabled = true;
        e.target.textContent = "Gerando...";
        try {
            const r = await Api.post("/admin/cobrancas-planos/gerar", {});
            if (!r.executado) {
                Toast.info(r.motivo);
            } else {
                Toast.sucesso(`${r.geradas} cobrança(s) gerada(s)${r.erros.length ? ` — ${r.erros.length} com erro ao gerar o PIX (veja o console)` : ""}.`);
                if (r.erros.length) console.warn("Erros ao gerar PIX de plano:", r.erros);
            }
            despachar();
        } catch (err) {
            Toast.erro(err.message);
            e.target.disabled = false;
            e.target.textContent = "Gerar cobranças agora";
        }
    });

    document.getElementById("btn-cobranca-avulsa").addEventListener("click", async () => {
        const clinicas = await Api.get("/admin/clinicas");
        abrirModalCobrancaAvulsa(clinicas);
    });

    document.querySelectorAll(".btn-gerar-pix-plano").forEach(btn => btn.addEventListener("click", async () => {
        try {
            await Api.post(`/admin/cobrancas-planos/${btn.dataset.id}/gerar-pix`);
            Toast.sucesso("PIX gerado!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    }));

    document.querySelectorAll(".btn-ver-pix").forEach(btn => btn.addEventListener("click", () => {
        navigator.clipboard?.writeText(btn.dataset.copiaCola).catch(() => {});
        Toast.info("Código PIX copiado pra área de transferência (copia e cola).");
    }));

    document.querySelectorAll(".btn-marcar-pago-plano").forEach(btn => btn.addEventListener("click", async () => {
        if (!confirm("Confirmar que esta clínica pagou a assinatura fora do app (dinheiro/transferência)?")) return;
        try {
            await Api.post(`/admin/cobrancas-planos/${btn.dataset.id}/marcar-pago`);
            Toast.sucesso("Pagamento confirmado!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    }));
}

function abrirModalCobrancaAvulsa(clinicas = []) {
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa" style="max-width:480px;">
        <h3 style="margin-bottom:6px;">Cobrança avulsa</h3>
        <p class="texto-xs texto-suave" style="margin-bottom:18px;">
          Para uma clínica específica, fora do ciclo mensal normal — ex: taxa de setup, ajuste retroativo.
        </p>
        <form id="form-cobranca-avulsa">
          <div class="campo"><label>Clínica ${ASTERISCO_OBRIGATORIO}</label>
            <select id="ca-clinica" required>
              <option value="">Selecione...</option>
              ${clinicas.map(c => `<option value="${c.id}">${escapeHtml(c.nome)}</option>`).join("")}
            </select>
          </div>
          <div class="campo"><label>Descrição ${ASTERISCO_OBRIGATORIO}</label>
            <input type="text" id="ca-descricao" placeholder="Ex: Taxa de setup" required maxlength="120" />
          </div>
          <div class="campo"><label>Valor (R$) ${ASTERISCO_OBRIGATORIO}</label>
            <input type="number" id="ca-valor" min="0.01" step="0.01" placeholder="0,00" required />
          </div>
          <label class="linha gap-2 texto-sm" style="margin:4px 0 16px;">
            <input type="checkbox" id="ca-gerar-pix" checked /> Gerar o PIX já na hora
          </label>
          <div class="linha gap-3">
            <button type="submit" class="botao botao-primario">Criar cobrança</button>
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    document.getElementById("form-cobranca-avulsa").addEventListener("submit", async (e) => {
        e.preventDefault();
        const valorReais = parseFloat(document.getElementById("ca-valor").value);
        if (!valorReais || valorReais <= 0) { Toast.erro("Informe um valor válido."); return; }
        const botaoSubmit = e.target.querySelector("button[type=submit]");
        botaoSubmit.disabled = true;
        botaoSubmit.textContent = "Criando...";
        try {
            const r = await Api.post("/admin/cobrancas-planos/avulsa", {
                organizacao_id: Number(document.getElementById("ca-clinica").value),
                valor_centavos: Math.round(valorReais * 100),
                descricao: document.getElementById("ca-descricao").value.trim(),
                gerar_pix_agora: document.getElementById("ca-gerar-pix").checked,
            });
            modal.remove();
            Toast.sucesso(r.erro_pix ? `Cobrança criada — PIX não gerado ainda (${r.erro_pix}). Use "Gerar PIX" na lista.` : "Cobrança avulsa criada!");
            despachar();
        } catch (err) {
            Toast.erro(err.message);
            botaoSubmit.disabled = false;
            botaoSubmit.textContent = "Criar cobrança";
        }
    });
}

// ---------------------------------------------------------------- Auditoria

async function viewAdminAuditoria(app) {
    const registros = await Api.get("/admin/auditoria");
    const conteudo = `
    <div class="cartao">
      <div class="tabela-wrap"><table class="tabela">
        <thead><tr><th>Quando</th><th>Ação</th><th>Entidade</th><th>Detalhes</th></tr></thead>
        <tbody>
          ${registros.length ? registros.map(r => `
            <tr>
              <td class="texto-sm">${formatarDataHora(r.criado_em)}</td>
              <td><span class="badge badge-marca">${r.acao}</span></td>
              <td class="texto-sm">${r.entidade} #${r.entidade_id ?? ""}</td>
              <td class="texto-sm texto-suave">${escapeHtml(r.detalhes || "")}</td>
            </tr>`).join("") : `<tr><td colspan="4" class="texto-sm texto-suave">Nenhum registro ainda.</td></tr>`}
        </tbody>
      </table></div>
    </div>`;
    app.innerHTML = renderShellSidebar("#/admin/auditoria", "Auditoria Global", conteudo);
    anexarEventosShell();
}

// ---------------------------------------------------------------- Perfil da Plataforma
//
// Insight do usuário (04/09/2026): faltava, no Painel do Administrador da
// Plataforma, uma tela pra trocar os próprios dados de acesso e pra incluir
// novos admin_master — hoje o único jeito era editar direto no seed.py.
// Reaproveita o mesmo padrão de "Meus Dados" das outras telas de Perfil
// (ver viewPerfilInterno em financeiro.js) e o mesmo padrão de convite por
// link já usado em Equipe (ver abrirModalSecretaria em pacientes.js).

async function viewAdminPerfil(app) {
    const me = await Api.get("/auth/me");
    const administradores = await Api.get("/admin/administradores");

    const conteudo = `
    <div class="grade grade-dupla" style="max-width:820px; margin-bottom:24px;">
      <div class="cartao" style="text-align:center;">
        <div id="preview-avatar-plat" style="width:96px; height:96px; border-radius:50%; margin:0 auto; display:flex; align-items:center; justify-content:center; background:var(--cor-marca-clara); overflow:hidden; font-size:48px;">
          ${renderAvatarUsuario(me, 96)}
        </div>
        <input type="file" id="input-avatar-plat" accept="image/*" style="display:none;" />
        <button type="button" class="botao botao-secundario botao-sm" id="btn-trocar-avatar-plat" style="margin-top:12px;">📷 Trocar foto</button>
        ${renderOrientacaoEnvio("foto")}
        <h3 style="margin-top:10px;">${escapeHtml(me.nome)}</h3>
        <p class="texto-sm texto-suave">${escapeHtml(me.email)}</p>
        <span class="badge badge-marca" style="margin-top:6px;">🛠️ Administrador da Plataforma</span>
      </div>
      <div class="cartao">
        <p class="texto-xs texto-suave" style="font-weight:700; margin-bottom:12px;">MEUS DADOS</p>
        <form id="form-perfil-plataforma">
          <div class="campo"><label>Nome completo ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="plat-nome" value="${escapeHtml(me.nome)}" required /></div>
          <div class="campo"><label>Telefone</label><input type="tel" id="plat-telefone" value="${escapeHtml(me.telefone || "")}" /></div>
          <p class="texto-xs texto-suave" style="margin-bottom:14px;">O e-mail (${escapeHtml(me.email)}) é seu identificador de login e não pode ser alterado por aqui.</p>
          <button type="submit" class="botao botao-primario" style="width:100%;">Salvar alterações</button>
        </form>
      </div>
    </div>

    <div class="cartao" style="max-width:820px; margin-bottom:24px;">
      <p class="texto-xs texto-suave" style="font-weight:700; margin-bottom:12px;">ALTERAR SENHA</p>
      <form id="form-trocar-senha-plataforma">
        <div class="grade grade-dupla">
          <div class="campo"><label>Senha atual ${ASTERISCO_OBRIGATORIO}</label><input type="password" id="senha-atual" required /></div>
          <div></div>
          <div class="campo"><label>Nova senha ${ASTERISCO_OBRIGATORIO}</label><input type="password" id="senha-nova" minlength="8" required /></div>
          <div class="campo"><label>Confirmar nova senha ${ASTERISCO_OBRIGATORIO}</label><input type="password" id="senha-confirmar" minlength="8" required /></div>
        </div>
        <p class="texto-xs texto-suave" style="margin:4px 0 14px;">Mínimo de 8 caracteres. Ao trocar, sua sessão atual é encerrada e você precisa entrar de novo com a nova senha.</p>
        <button type="submit" class="botao botao-primario">Trocar senha</button>
      </form>
    </div>

    <div class="cartao" style="max-width:820px;">
      <p class="texto-xs texto-suave" style="font-weight:700; margin-bottom:12px;">ADMINISTRADORES DA PLATAFORMA</p>
      <div class="lista-pessoas">
        ${administradores.map(a => `
        <div class="pessoa-linha cartao" style="margin-bottom:10px; ${!a.ativo ? "opacity:.55;" : ""}">
          <div class="pessoa-avatar" style="font-size:24px; overflow:hidden;">${renderAvatarUsuario(a, 40)}</div>
          <div class="pessoa-info">
            <div class="pessoa-nome">${escapeHtml(a.nome)}${a.id === me.id ? ` <span class="texto-xs texto-suave">(você)</span>` : ""}</div>
            <div class="pessoa-sub">${escapeHtml(a.email)}${a.telefone ? " · " + escapeHtml(a.telefone) : ""}</div>
          </div>
          <span class="badge ${a.ativo ? "badge-sucesso" : "badge-neutro"}">${a.ativo ? "Ativo" : "Arquivado"}</span>
          <div class="linha gap-1">
            <button class="botao-icone btn-editar-admin" data-id="${a.id}" title="Editar" style="width:34px; height:34px; font-size:14px;">✏️</button>
            ${a.id === me.id ? "" : `<button class="botao-icone btn-arquivar-admin" data-id="${a.id}" data-ativo="${a.ativo}" title="${a.ativo ? "Arquivar" : "Reativar"}" style="width:34px; height:34px; font-size:14px;">${a.ativo ? "🗑️" : "♻️"}</button>`}
          </div>
        </div>`).join("")}
      </div>
    </div>`;

    const acoesTopo = `<button class="botao botao-primario" id="btn-novo-admin">+ Novo Administrador</button>`;
    app.innerHTML = renderShellSidebar("#/admin/perfil", "Perfil da Plataforma", conteudo, acoesTopo);
    anexarEventosShell();

    ativarMascaraCampo(document.getElementById("plat-telefone"), "telefone");
    document.getElementById("btn-trocar-avatar-plat").addEventListener("click", () => document.getElementById("input-avatar-plat").click());
    document.getElementById("input-avatar-plat").addEventListener("change", async (e) => {
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
            document.getElementById("preview-avatar-plat").innerHTML = `<img src="data:image/png;base64,${base64}" style="width:100%; height:100%; object-fit:cover;" alt="Foto" />`;
            Toast.sucesso("Foto atualizada!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });

    document.getElementById("form-perfil-plataforma").addEventListener("submit", async (e) => {
        e.preventDefault();
        const nome = document.getElementById("plat-nome").value.trim();
        const telefone = document.getElementById("plat-telefone").value.trim();
        try {
            await Api.put("/pessoas/perfil", { nome, telefone });
            const uAtual = Sessao.usuario; uAtual.nome = nome; uAtual.telefone = telefone; Sessao.usuario = uAtual;
            Toast.sucesso("Dados atualizados!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });

    document.getElementById("form-trocar-senha-plataforma").addEventListener("submit", async (e) => {
        e.preventDefault();
        const senhaAtual = document.getElementById("senha-atual").value;
        const novaSenha = document.getElementById("senha-nova").value;
        const confirmar = document.getElementById("senha-confirmar").value;
        if (novaSenha !== confirmar) { Toast.erro("A nova senha e a confirmação não são iguais."); return; }
        const botaoSubmit = e.target.querySelector("button[type=submit]");
        botaoSubmit.disabled = true;
        try {
            await Api.put("/pessoas/perfil/senha", { senha_atual: senhaAtual, nova_senha: novaSenha });
            Toast.sucesso("Senha alterada! Entre novamente com a nova senha.");
            Sessao.limpar();
            location.hash = "#/login";
        } catch (err) {
            Toast.erro(err.message);
            botaoSubmit.disabled = false;
        }
    });

    document.getElementById("btn-novo-admin").addEventListener("click", () => abrirModalAdministrador(null));

    document.querySelectorAll(".btn-editar-admin").forEach(btn => btn.addEventListener("click", () => {
        const admin = administradores.find(a => a.id === Number(btn.dataset.id));
        abrirModalAdministrador(admin);
    }));

    document.querySelectorAll(".btn-arquivar-admin").forEach(btn => btn.addEventListener("click", async () => {
        const ativo = btn.dataset.ativo === "1" || btn.dataset.ativo === "true";
        const msg = ativo
            ? "Arquivar este administrador? Ele deixa de conseguir entrar no Painel da Plataforma."
            : "Reativar este administrador? Ele volta a ter acesso ao Painel da Plataforma.";
        if (!confirm(msg)) return;
        try {
            const r = await Api.put(`/admin/administradores/${btn.dataset.id}/arquivar`);
            Toast.sucesso(r.ativo ? "Administrador reativado!" : "Administrador arquivado.");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    }));
}

function abrirModalAdministrador(adminExistente) {
    const editando = !!adminExistente;
    const a = adminExistente || {};
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:18px;">${editando ? "Editar administrador" : "Novo administrador da plataforma"}</h3>
        <form id="form-administrador">
          <div class="campo"><label>Nome completo ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="af-nome" value="${escapeHtml(a.nome || "")}" required /></div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>E-mail ${ASTERISCO_OBRIGATORIO}</label><input type="email" id="af-email" value="${escapeHtml(a.email || "")}" ${editando ? "readonly" : "required"} /></div>
            <div class="campo" style="flex:1;"><label>Telefone</label><input type="tel" id="af-telefone" value="${escapeHtml(a.telefone || "")}" /></div>
          </div>
          ${editando ? `<p class="texto-xs texto-suave" style="margin: 4px 0 16px;">O e-mail não pode ser alterado por aqui.</p>` : `
          <p class="texto-xs texto-suave" style="margin: 4px 0 16px;">
            Terá acesso total ao Painel da Plataforma — gestão de clínicas, planos, cobranças e configurações do SaaS.
            A senha inicial é definida pela própria pessoa, ao abrir o link de convite gerado após o cadastro.
          </p>`}
          <div class="linha gap-3" style="margin-top:20px;">
            <button type="submit" class="botao botao-primario">${editando ? "Salvar alterações" : "Cadastrar"}</button>
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    ativarMascaraCampo(document.getElementById("af-telefone"), "telefone");

    document.getElementById("form-administrador").addEventListener("submit", async (e) => {
        e.preventDefault();
        const body = {
            nome: document.getElementById("af-nome").value.trim(),
            telefone: document.getElementById("af-telefone").value.trim(),
        };
        try {
            if (editando) {
                await Api.put(`/admin/administradores/${a.id}`, body);
                modal.remove();
                Toast.sucesso("Administrador atualizado!");
                despachar();
            } else {
                body.email = document.getElementById("af-email").value.trim();
                const r = await Api.post("/admin/administradores", body);
                modal.remove();
                Toast.sucesso("Administrador cadastrado!");
                mostrarModalConvite(r.link_convite, body.nome);
            }
        } catch (err) { Toast.erro(err.message); }
    });
}
