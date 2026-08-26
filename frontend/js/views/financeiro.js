// ============================================================================
// views/financeiro.js — Financeiro (Gestor) + Indicadores
// ============================================================================

async function viewFinanceiroGestor(app) {
    const [resumo, pacientes] = await Promise.all([
        Api.get("/financeiro/clinica/resumo"),
        Api.get("/pessoas/pacientes"),
    ]);

    const conteudo = `
    <div class="kpi-grade" style="margin-bottom:32px;">
      ${kpiCard("💰", formatarMoeda(resumo.receita_mes_centavos), "recebido este mês", "sucesso")}
      ${kpiCard("⏳", resumo.pendentes_qtd, "cobranças pendentes", "acento")}
      ${kpiCard("📌", formatarMoeda(resumo.pendentes_total_centavos), "valor em aberto", "marca")}
      ${kpiCard("🔴", resumo.vencidos_qtd, "cobranças vencidas", resumo.vencidos_qtd > 0 ? "alerta" : "sucesso")}
    </div>
    <div class="cartao">
      <h3 style="margin-bottom:16px;">Selecione um paciente para ver o extrato</h3>
      <select id="select-paciente-financeiro" style="width:100%; max-width:320px; padding:11px 14px; border-radius:10px; border:1.5px solid var(--cor-borda);">
        ${pacientes.map(p => `<option value="${p.id}">${p.avatar_mascote} ${escapeHtml(p.nome)}</option>`).join("")}
      </select>
      <div id="extrato-paciente" style="margin-top:20px;"></div>
    </div>`;

    app.innerHTML = renderShellSidebar("#/gestor/financeiro", "Financeiro", conteudo);
    anexarEventosShell();

    async function carregarExtrato(pacienteId) {
        const cobrancas = await Api.get(`/financeiro/paciente/${pacienteId}`);
        const alvo = document.getElementById("extrato-paciente");
        if (!alvo) return; // usuário já navegou para outra tela antes da resposta chegar
        alvo.innerHTML = cobrancas.length ? `
          <div class="tabela-wrap"><table class="tabela">
            <thead><tr><th>Descrição</th><th>Vencimento</th><th>Valor</th><th>Status</th></tr></thead>
            <tbody>
              ${cobrancas.map(c => `
                <tr>
                  <td>${escapeHtml(c.descricao)}</td>
                  <td>${formatarData(c.vencimento)}</td>
                  <td>${formatarMoeda(c.valor_centavos)}</td>
                  <td><span class="badge badge-${c.status === "pago" ? "sucesso" : c.status === "vencido" ? "alerta" : "aviso"}">${c.status}</span></td>
                </tr>`).join("")}
            </tbody>
          </table></div>` : `<p class="texto-sm texto-suave">Nenhuma cobrança registrada.</p>`;
    }

    const select = document.getElementById("select-paciente-financeiro");
    select.addEventListener("change", () => carregarExtrato(select.value));
    if (pacientes.length) carregarExtrato(pacientes[0].id);
}

// ---------------------------------------------------------------- Financeiro (Responsável)

async function viewFinanceiroResponsavel(app) {
    const pacienteId = Sessao.pacienteAtivoId;
    const cobrancas = await Api.get(`/financeiro/paciente/${pacienteId}`);

    const conteudo = `
    <div class="coluna gap-3">
      ${cobrancas.length ? cobrancas.map(c => `
        <div class="cartao">
          <div class="linha-entre">
            <div>
              <div style="font-weight:700;">${escapeHtml(c.descricao)}</div>
              <div class="texto-sm texto-suave">Vencimento: ${formatarData(c.vencimento)}</div>
            </div>
            <div style="text-align:right;">
              <div style="font-weight:700; font-size:16px;">${formatarMoeda(c.valor_centavos)}</div>
              <span class="badge badge-${c.status === "pago" ? "sucesso" : c.status === "vencido" ? "alerta" : "aviso"}">${c.status}</span>
            </div>
          </div>
          ${c.status !== "pago" ? `<button class="botao botao-acento botao-sm btn-pagar" data-id="${c.id}" style="width:100%; margin-top:12px;">Pagar com PIX</button>` : ""}
        </div>`).join("") : `<div class="estado-vazio"><div class="emoji">💳</div><p>Nenhuma cobrança no momento.</p></div>`}
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
          <div class="linha-entre">
            <div>
              <p class="texto-sm" style="font-weight:700;">🔴 Cobrança pendente — ${formatarMoeda(c.valor_centavos)}</p>
              <p class="texto-xs texto-suave" style="margin-top:2px;">Gerada em ${formatarDataHora(c.criado_em)}</p>
            </div>
            ${c.pix_copia_cola
              ? `<button class="botao botao-primario botao-sm btn-ver-pix-assinatura" data-copia-cola="${escapeHtml(c.pix_copia_cola)}">Ver PIX</button>`
              : `<button class="botao botao-primario botao-sm btn-gerar-pix-assinatura" data-id="${c.id}">Gerar PIX</button>`}
          </div>
          ${c.pix_qr_code_base64 ? `<div class="pix-qr-assinatura" style="display:none; margin-top:12px; text-align:center;"><img src="data:image/png;base64,${c.pix_qr_code_base64}" alt="QR Code PIX" style="max-width:180px;" /></div>` : ""}
        </div>`).join("") : `
        <p class="texto-sm" style="color:var(--cor-sucesso); font-weight:600;">
          ✅ Nenhuma cobrança pendente.${ultimaPaga ? ` Última paga em ${formatarDataHora(ultimaPaga.pago_em || ultimaPaga.criado_em)}.` : ""}
        </p>`}
    </div>`;
}

// ---------------------------------------------------------------- Configurações (Identidade Visual)

async function viewConfiguracoes(app) {
    const [org, me, assinatura] = await Promise.all([Api.get("/pessoas/organizacao"), Api.get("/auth/me"), Api.get("/admin/assinatura")]);
    const especialidadesAtuais = org.especialidades || [];
    const conteudo = `
    ${renderCartaoAssinatura(assinatura)}
    <div class="cartao" style="max-width:900px; margin-bottom:20px;">
        <p class="texto-sm" style="font-weight:700; margin-bottom:4px;">📇 Contato (decisor na clínica)</p>
        <p class="texto-xs texto-suave" style="margin-bottom:14px;">Seus próprios dados como responsável pela conta — aparecem pra equipe da plataforma e podem ser usados em contato.</p>
        <div class="linha gap-3" style="align-items:center; margin-bottom:16px;">
          <div id="preview-avatar-contato" style="width:56px; height:56px; border-radius:50%; display:flex; align-items:center; justify-content:center; background:var(--cor-marca-clara); overflow:hidden; flex-shrink:0;">
            ${renderAvatarUsuario(me, 56)}
          </div>
          <div>
            <input type="file" id="input-avatar-contato" accept="image/*" style="display:none;" />
            <button type="button" class="botao botao-secundario botao-sm" id="btn-trocar-avatar-contato">📷 Trocar foto</button>
          </div>
        </div>
        <div class="linha gap-4">
          <div class="campo" style="flex:1;"><label>Nome ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="ct-nome" value="${escapeHtml(me.nome)}" required /></div>
          <div class="campo" style="flex:1;"><label>Telefone</label><input type="tel" id="ct-telefone" value="${escapeHtml(me.telefone || "")}" /></div>
        </div>
        <div class="campo"><label>E-mail</label><input type="email" value="${escapeHtml(me.email)}" disabled style="opacity:.6;" /></div>
        <p class="texto-xs texto-suave" style="margin-bottom:14px;">O e-mail é seu identificador de login e não pode ser alterado por aqui.</p>
        <button type="button" class="botao botao-primario botao-sm" id="btn-salvar-contato">Salvar contato</button>
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
            <p class="texto-xs texto-suave" style="margin-top:6px;">Envie uma imagem (até 2MB) ou deixe em branco para usar um emoji simples abaixo. A imagem aparece em tamanho real, sem cortes — tamanho ideal: retangular, até 240×80px, fundo transparente (PNG).</p>
          </div>
          <div class="campo"><label>Emoji/ícone (usado se nenhuma imagem for enviada)</label><input type="text" id="cf-logo" value="${org.logo_emoji}" maxlength="2" style="width:80px; font-size:22px; text-align:center;" /></div>

          <hr style="border:none; border-top:1px solid var(--cor-borda); margin:20px 0;" />
          <p class="texto-sm" style="font-weight:700; margin-bottom:4px;">🏢 Dados institucionais</p>
          <p class="texto-xs texto-suave" style="margin-bottom:12px;">Usados em documentos, recibos e no cadastro oficial da clínica.</p>
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
          <p class="texto-sm" style="font-weight:700; margin-bottom:4px;">🩺 Especialidades</p>
          <p class="texto-xs texto-suave" style="margin-bottom:12px;">Quais especialidades sua clínica oferece? Digite e adicione — isso ajuda a organizar a Equipe e a Biblioteca.</p>
          ${renderCampoTagsEspecialidade("cf-esp", especialidadesAtuais)}

          <hr style="border:none; border-top:1px solid var(--cor-borda); margin:20px 0;" />
          <p class="texto-sm" style="font-weight:700; margin-bottom:4px;">🎨 Personalização (White Label leve)</p>
          <p class="texto-xs texto-suave" style="margin-bottom:14px;">Esses nomes aparecem para profissionais, famílias e crianças em toda a plataforma.</p>
          <div class="campo"><label>Nome do assistente de IA</label><input type="text" id="cf-nome-ia" value="${escapeHtml(org.nome_ia || "Lumi")}" placeholder="Ex: Lumi, Nina, Léo..." /></div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Nome da "moeda" da gamificação</label><input type="text" id="cf-nome-moeda" value="${escapeHtml(org.nome_moeda_gamificacao || "XP")}" placeholder="Ex: XP, Estrelinhas, Pontos..." /></div>
            <div class="campo" style="flex:1;"><label>Nome genérico das conquistas</label><input type="text" id="cf-nome-medalha" value="${escapeHtml(org.nome_medalha_generico || "Medalha")}" placeholder="Ex: Medalha, Troféu, Selo..." /></div>
          </div>
          <button type="submit" class="botao botao-primario">Salvar alterações</button>
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
    </div>`;
    app.innerHTML = renderShellSidebar("#/gestor/configuracoes", "Configurações", conteudo);
    anexarEventosShell();

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

    // --- Contato (decisor na clínica) ---
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
        if (file.size > 2 * 1024 * 1024) { Toast.erro("A foto precisa ter até 2MB."); e.target.value = ""; return; }
        const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        avatarContatoNovo = { base64, nome: file.name };
        document.getElementById("preview-avatar-contato").innerHTML = `<img src="data:image/png;base64,${base64}" style="width:100%; height:100%; object-fit:cover;" alt="Foto" />`;
    });
    document.getElementById("btn-salvar-contato").addEventListener("click", async () => {
        // Não está dentro de um <form> (é um botão avulso), então a validação
        // nativa do navegador (o "*"/required do campo Nome) não dispara
        // sozinha ao clicar — chamamos manualmente pra manter o mesmo
        // comportamento acessível de qualquer outro formulário da tela.
        if (!document.getElementById("ct-nome").reportValidity()) return;
        const body = {
            nome: document.getElementById("ct-nome").value.trim(),
            telefone: document.getElementById("ct-telefone").value.trim(),
        };
        if (avatarContatoNovo) { body.avatar_base64 = avatarContatoNovo.base64; body.avatar_nome = avatarContatoNovo.nome; }
        try {
            await Api.put("/pessoas/perfil", body);
            const u = Sessao.usuario;
            u.nome = body.nome; u.telefone = body.telefone;
            if (avatarContatoNovo) u.avatar_base64 = avatarContatoNovo.base64;
            Sessao.usuario = u;
            Toast.sucesso("Contato atualizado!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });

    let logoBase64Novo = null;
    let logoNomeNovo = null;
    document.getElementById("cf-logo-arquivo").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        if (file.size > 2 * 1024 * 1024) { Toast.erro("A imagem precisa ter até 2MB."); e.target.value = ""; return; }
        const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        logoBase64Novo = base64;
        logoNomeNovo = file.name;
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

    document.getElementById("form-config").addEventListener("submit", async (e) => {
        e.preventDefault();
        const especialidades = obterEspecialidadesCf();
        const corPrimaria = document.getElementById("cf-cor1").value;
        const corSecundaria = document.getElementById("cf-cor2").value;
        const body = {
            nome: document.getElementById("cf-nome").value.trim(),
            cor_primaria: corPrimaria,
            cor_secundaria: corSecundaria,
            logo_emoji: document.getElementById("cf-logo").value,
            cnpj: document.getElementById("cf-cnpj").value.trim(),
            telefone: document.getElementById("cf-telefone").value.trim(),
            endereco_cep: document.getElementById("cf-cep").value.trim(),
            endereco_logradouro: document.getElementById("cf-logradouro").value.trim(),
            endereco_numero: document.getElementById("cf-numero").value.trim(),
            endereco_bairro: document.getElementById("cf-bairro").value.trim(),
            endereco_cidade: document.getElementById("cf-cidade").value.trim(),
            endereco_uf: document.getElementById("cf-uf").value.trim().toUpperCase(),
            nome_ia: document.getElementById("cf-nome-ia").value.trim() || "Lumi",
            nome_moeda_gamificacao: document.getElementById("cf-nome-moeda").value.trim() || "XP",
            nome_medalha_generico: document.getElementById("cf-nome-medalha").value.trim() || "Medalha",
            especialidades,
        };
        if (logoBase64Novo) { body.logo_base64 = logoBase64Novo; body.logo_nome = logoNomeNovo; }
        await Api.put("/pessoas/organizacao", body);
        const u = Sessao.usuario;
        Object.assign(u.organizacao, body);
        Sessao.usuario = u;
        aplicarTemaClinica(u.organizacao);
        Toast.sucesso("Configurações salvas!");
        despachar();
    });
}

// ---------------------------------------------------------------- Perfil (Gestor / Profissional)

async function viewPerfilInterno(app) {
    const u = Sessao.usuario;
    const base = u.papel === "gestor" ? "gestor" : "profissional";
    const me = await Api.get("/auth/me");
    const conteudo = `
    <div class="grade grade-dupla" style="max-width:760px;">
      <div class="cartao" style="text-align:center;">
        <div id="preview-avatar-perfil" style="width:96px; height:96px; border-radius:50%; margin:0 auto; display:flex; align-items:center; justify-content:center; background:var(--cor-marca-clara); overflow:hidden; font-size:48px;">
          ${renderAvatarUsuario(me, 96)}
        </div>
        <input type="file" id="input-avatar-perfil" accept="image/*" style="display:none;" />
        <button type="button" class="botao botao-secundario botao-sm" id="btn-trocar-avatar" style="margin-top:12px;">📷 Trocar foto</button>
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
        if (file.size > 2 * 1024 * 1024) { Toast.erro("A foto precisa ter até 2MB."); e.target.value = ""; return; }
        const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        try {
            await Api.put("/pessoas/perfil", { avatar_base64: base64, avatar_nome: file.name });
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
