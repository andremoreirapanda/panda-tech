// ============================================================================
// views/biblioteca.js — UX Pattern 04: Filtros → Categorias → Cards → Detalhes
// ============================================================================

const LIMITE_ARQUIVO_BIBLIOTECA_MB = 4;

async function viewBiblioteca(app) {
    const u = Sessao.usuario;
    const base = u.papel === "admin_master" ? "admin" : (u.papel === "gestor" ? "gestor" : "profissional");
    const apenasPlataforma = u.papel === "admin_master";
    const [categorias, exercicios] = await Promise.all([
        Api.get("/biblioteca/categorias"),
        Api.get(`/biblioteca/exercicios${apenasPlataforma ? "?apenas_plataforma=1" : ""}`),
    ]);
    const podeCriar = u.papel === "gestor" || u.papel === "profissional" || u.papel === "admin_master";

    const conteudo = `
    ${apenasPlataforma ? `
    <div class="cartao-flat" style="margin-bottom:20px; display:flex; gap:10px; align-items:flex-start;">
      <span style="font-size:18px;">🌐</span>
      <p class="texto-sm texto-suave">
        Este é o conteúdo da <strong>Biblioteca da Plataforma</strong> — visível automaticamente para
        <strong>todas as clínicas</strong>. Cada clínica também tem sua própria biblioteca privada, que só ela vê.
      </p>
    </div>` : ""}
    <div class="linha gap-3" style="margin-bottom:20px; flex-wrap:wrap;">
      <input type="text" id="busca-biblioteca" placeholder="🔍 Buscar exercícios..." style="flex:1; min-width:220px; padding:11px 16px; border-radius:999px; border:1.5px solid var(--cor-borda);" />
      ${categorias.length ? `
      <select id="filtro-categoria" style="padding:11px 14px; border-radius:999px; border:1.5px solid var(--cor-borda);">
        <option value="">Todas categorias</option>
        ${categorias.map(c => `<option value="${c.id}">${c.icone_emoji} ${escapeHtml(c.nome)}</option>`).join("")}
      </select>` : ""}
      <select id="filtro-dificuldade" style="padding:11px 14px; border-radius:999px; border:1.5px solid var(--cor-borda);">
        <option value="">Qualquer dificuldade</option>
        <option value="facil">Fácil</option><option value="medio">Médio</option><option value="dificil">Difícil</option>
      </select>
    </div>
    <div id="grade-exercicios" class="exercicio-grade">${exercicios.map(ex => renderExercicioCard(ex, u.papel)).join("")}</div>
    `;

    app.innerHTML = renderShellSidebar(`#/${base}/biblioteca`, apenasPlataforma ? "Biblioteca da Plataforma" : "Biblioteca Terapêutica", conteudo,
        `${(u.papel === "gestor" || u.papel === "profissional") ? `<button class="botao botao-secundario botao-sm" id="btn-gerenciar-categorias">🏷️ Categorias</button>` : ""}
         ${podeCriar ? `<button class="botao botao-primario botao-sm" id="btn-novo-exercicio">+ Novo Exercício</button>` : ""}`);
    anexarEventosShell();

    const btnCategorias = document.getElementById("btn-gerenciar-categorias");
    if (btnCategorias) btnCategorias.addEventListener("click", () => abrirModalCategorias(categorias, refazerBusca));

    async function refazerBusca() {
        const q = document.getElementById("busca-biblioteca").value;
        const cat = document.getElementById("filtro-categoria")?.value;
        const dif = document.getElementById("filtro-dificuldade").value;
        const params = new URLSearchParams();
        if (apenasPlataforma) params.set("apenas_plataforma", "1");
        if (q) params.set("q", q);
        if (cat) params.set("categoria_id", cat);
        if (dif) params.set("dificuldade", dif);
        const novos = await Api.get(`/biblioteca/exercicios?${params}`);
        const grade = document.getElementById("grade-exercicios");
        if (!grade) return; // usuário já navegou para outra tela antes da resposta chegar
        grade.innerHTML = novos.length
            ? novos.map(ex => renderExercicioCard(ex, u.papel)).join("")
            : `<div class="estado-vazio"><div class="emoji">🔍</div><p>Nenhum exercício encontrado.</p></div>`;
        anexarCliquesCard(categorias, refazerBusca, u.papel);
    }

    let debounce;
    document.getElementById("busca-biblioteca").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(refazerBusca, 300); });
    document.getElementById("filtro-categoria")?.addEventListener("change", refazerBusca);
    document.getElementById("filtro-dificuldade").addEventListener("change", refazerBusca);

    const btnNovo = document.getElementById("btn-novo-exercicio");
    if (btnNovo) btnNovo.addEventListener("click", () => abrirModalExercicio(categorias, null, refazerBusca));

    anexarCliquesCard(categorias, refazerBusca, u.papel);
}

function anexarCliquesCard(categorias, aoSalvar, papel) {
    document.querySelectorAll(".exercicio-card").forEach(card => card.addEventListener("click", async () => {
        const ex = await Api.get(`/biblioteca/exercicios/${card.dataset.id}`);
        if (ex.pode_editar) abrirModalExercicio(categorias, ex, aoSalvar);
        else abrirModalDetalheExercicio(ex, papel, aoSalvar);
    }));
}

function renderExercicioCard(ex, papel) {
    const difCor = { facil: "sucesso", medio: "aviso", dificil: "alerta" }[ex.dificuldade] || "neutro";
    const editavel = ex.escopo === "plataforma" ? papel === "admin_master" : true;
    return `
    <div class="exercicio-card" data-id="${ex.id}" style="cursor:pointer;">
      <div class="exercicio-icone-tipo">${ICONES_TIPO_EXERCICIO[ex.tipo] || "📝"}</div>
      <div class="exercicio-titulo">${escapeHtml(ex.titulo)}</div>
      <p class="texto-xs texto-suave">${escapeHtml(ex.descricao || "")}</p>
      <div class="exercicio-tags">
        ${ex.escopo === "plataforma" ? `<span class="badge badge-marca">🌐 Plataforma</span>` : `<span class="badge badge-neutro">${ex.categoria_icone || "📘"} ${escapeHtml(ex.categoria_nome || "Geral")}</span>`}
        <span class="badge badge-${difCor}">${ex.dificuldade}</span>
        <span class="badge badge-neutro">${ex.faixa_etaria_min}-${ex.faixa_etaria_max} anos</span>
        ${ex.tem_arquivo || ex.arquivo_nome ? `<span class="badge badge-marca">📎 arquivo</span>` : (ex.conteudo_url ? `<span class="badge badge-marca">🔗 link</span>` : "")}
      </div>
      <p class="texto-xs texto-suave" style="margin-top:auto; padding-top:6px;">${editavel ? "Clique para editar →" : "Clique para ver detalhes →"}</p>
    </div>`;
}

// ---------------------------------------------------------------- Detalhe (somente leitura)
function abrirModalDetalheExercicio(ex, papel, aoSalvar) {
    const podeAdotar = ex.escopo === "plataforma" && (papel === "gestor" || papel === "profissional");
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <div class="linha-entre" style="margin-bottom:8px;">
          <h3>${ICONES_TIPO_EXERCICIO[ex.tipo] || "📝"} ${escapeHtml(ex.titulo)}</h3>
          ${ex.escopo === "plataforma" ? `<span class="badge badge-marca">🌐 Plataforma</span>` : ""}
        </div>
        <p class="texto-sm texto-suave" style="margin-bottom:16px;">${escapeHtml(ex.descricao || "")}</p>
        ${ex.conteudo_url ? `<a href="${escapeHtml(ex.conteudo_url)}" target="_blank" class="botao botao-secundario botao-sm">🔗 Abrir link</a>` : ""}
        ${podeAdotar ? `<p class="texto-xs texto-suave" style="margin-top:14px;">Gostou deste conteúdo? Adicione uma cópia editável à biblioteca da sua clínica.</p>` : ""}
        <div class="linha gap-3" style="margin-top:16px;">
          ${podeAdotar ? `<button type="button" class="botao botao-primario" id="btn-adotar-exercicio">+ Adicionar à minha Biblioteca</button>` : ""}
          <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Fechar</button>
        </div>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    const btnAdotar = document.getElementById("btn-adotar-exercicio");
    if (btnAdotar) btnAdotar.addEventListener("click", async () => {
        try {
            await Api.post(`/biblioteca/exercicios/${ex.id}/duplicar`);
            Toast.sucesso("Adicionado à biblioteca da sua clínica! Já pode editar como quiser.");
            modal.remove();
            aoSalvar();
        } catch (err) { Toast.erro(err.message); }
    });
}

// ---------------------------------------------------------------- Criar / Editar

function abrirModalExercicio(categorias, exercicioExistente, aoSalvar) {
    const editando = !!exercicioExistente;
    const ex = exercicioExistente || {};
    let arquivoNovo = null; // { nome, base64 } — só preenchido se o usuário trocar o arquivo nesta sessão

    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:18px;">${editando ? "Editar exercício" : "Novo exercício"}</h3>
        <form id="form-exercicio">
          <div class="campo"><label>Título</label><input type="text" id="ex-titulo" value="${escapeHtml(ex.titulo || "")}" required /></div>
          <div class="campo"><label>Descrição</label><textarea id="ex-descricao" rows="2">${escapeHtml(ex.descricao || "")}</textarea></div>
          <div class="linha gap-4">
            ${categorias.length ? `
            <div class="campo" style="flex:1;"><label>Categoria</label>
              <select id="ex-categoria">${categorias.map(c => `<option value="${c.id}" ${ex.categoria_id === c.id ? "selected" : ""}>${c.nome}</option>`).join("")}</select>
            </div>` : ""}
            <div class="campo" style="flex:1;"><label>Tipo</label>
              <select id="ex-tipo">${Object.entries(ICONES_TIPO_EXERCICIO).map(([k, v]) => `<option value="${k}" ${ex.tipo === k ? "selected" : ""}>${v} ${k}</option>`).join("")}</select>
            </div>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Dificuldade</label>
              <select id="ex-dificuldade">
                <option value="facil" ${ex.dificuldade === "facil" ? "selected" : ""}>Fácil</option>
                <option value="medio" ${ex.dificuldade === "medio" ? "selected" : ""}>Médio</option>
                <option value="dificil" ${ex.dificuldade === "dificil" ? "selected" : ""}>Difícil</option>
              </select>
            </div>
            <div class="campo" style="flex:1;"><label>Faixa etária</label>
              <div class="linha gap-2">
                <input type="number" id="ex-idade-min" value="${ex.faixa_etaria_min ?? 2}" style="width:70px;" />
                <span>a</span>
                <input type="number" id="ex-idade-max" value="${ex.faixa_etaria_max ?? 10}" style="width:70px;" />
              </div>
            </div>
          </div>

          <div class="tabs" style="margin-bottom:14px;">
            <div class="tab-item ${!ex.conteudo_url ? "ativo" : ""}" data-tab="upload">📎 Enviar arquivo</div>
            <div class="tab-item ${ex.conteudo_url ? "ativo" : ""}" data-tab="link">🔗 Link externo</div>
          </div>

          <div id="painel-upload" class="campo" style="${ex.conteudo_url ? "display:none;" : ""}">
            <label>Arquivo (foto, PDF, áudio ou vídeo curto — até ${LIMITE_ARQUIVO_BIBLIOTECA_MB}MB)</label>
            <input type="file" id="ex-arquivo" accept="image/*,application/pdf,audio/*,video/*" />
            <div id="arquivo-atual" class="texto-sm texto-suave" style="margin-top:8px;">
              ${ex.arquivo_nome ? `📎 Arquivo atual: <strong>${escapeHtml(ex.arquivo_nome)}</strong> <button type="button" id="btn-remover-arquivo" class="botao-texto botao-sm" style="padding:2px 6px;">remover</button>` : "Nenhum arquivo enviado ainda."}
            </div>
          </div>
          <div id="painel-link" class="campo" style="${ex.conteudo_url ? "" : "display:none;"}">
            <label>URL do conteúdo</label>
            <input type="url" id="ex-url" value="${escapeHtml(ex.conteudo_url || "")}" placeholder="https://..." />
          </div>

          <div class="linha gap-3" style="margin-top:16px;">
            <button type="submit" class="botao botao-primario" id="btn-salvar-exercicio">Salvar exercício</button>
            ${editando ? `<button type="button" class="botao botao-perigo" id="btn-arquivar-exercicio">${ex.ativo === 0 ? "Reativar" : "Arquivar"}</button>` : ""}
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());

    let removerArquivo = false;
    let modoConteudo = ex.conteudo_url ? "link" : "upload";
    modal.querySelectorAll(".tab-item").forEach(tab => tab.addEventListener("click", () => {
        modal.querySelectorAll(".tab-item").forEach(t => t.classList.remove("ativo"));
        tab.classList.add("ativo");
        modoConteudo = tab.dataset.tab;
        document.getElementById("painel-upload").style.display = modoConteudo === "upload" ? "" : "none";
        document.getElementById("painel-link").style.display = modoConteudo === "link" ? "" : "none";
    }));

    document.getElementById("ex-arquivo").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        if (file.size > LIMITE_ARQUIVO_BIBLIOTECA_MB * 1024 * 1024) {
            Toast.erro(`"${file.name}" passa de ${LIMITE_ARQUIVO_BIBLIOTECA_MB}MB.`);
            e.target.value = "";
            return;
        }
        const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        arquivoNovo = { nome: file.name, base64 };
        removerArquivo = false;
        document.getElementById("arquivo-atual").innerHTML = `📎 Selecionado: <strong>${escapeHtml(file.name)}</strong>`;
    });

    const btnRemoverArquivo = document.getElementById("btn-remover-arquivo");
    if (btnRemoverArquivo) btnRemoverArquivo.addEventListener("click", () => {
        removerArquivo = true;
        arquivoNovo = null;
        document.getElementById("arquivo-atual").textContent = "Arquivo será removido ao salvar.";
    });

    const btnArquivar = document.getElementById("btn-arquivar-exercicio");
    if (btnArquivar) btnArquivar.addEventListener("click", async () => {
        if (!confirm(ex.ativo === 0 ? "Reativar este exercício na biblioteca?" : "Arquivar este exercício? Ele deixa de aparecer na Biblioteca, mas missões que já o usam continuam funcionando.")) return;
        const r = await Api.put(`/biblioteca/exercicios/${ex.id}/arquivar`);
        Toast.sucesso(r.ativo ? "Exercício reativado!" : "Exercício arquivado.");
        modal.remove();
        aoSalvar();
    });

    document.getElementById("form-exercicio").addEventListener("submit", async (e) => {
        e.preventDefault();
        const btnSalvar = document.getElementById("btn-salvar-exercicio");
        btnSalvar.disabled = true;
        try {
            const body = {
                titulo: document.getElementById("ex-titulo").value.trim(),
                descricao: document.getElementById("ex-descricao").value.trim(),
                categoria_id: document.getElementById("ex-categoria") ? parseInt(document.getElementById("ex-categoria").value) : null,
                tipo: document.getElementById("ex-tipo").value,
                dificuldade: document.getElementById("ex-dificuldade").value,
                faixa_etaria_min: parseInt(document.getElementById("ex-idade-min").value),
                faixa_etaria_max: parseInt(document.getElementById("ex-idade-max").value),
                conteudo_url: modoConteudo === "link" ? document.getElementById("ex-url").value.trim() : "",
            };
            if (modoConteudo === "upload" && arquivoNovo) {
                body.arquivo_nome = arquivoNovo.nome;
                body.arquivo_base64 = arquivoNovo.base64;
            }
            if (removerArquivo) body.remover_arquivo = true;

            if (editando) {
                await Api.put(`/biblioteca/exercicios/${ex.id}`, body);
                Toast.sucesso("Exercício atualizado!");
            } else {
                await Api.post("/biblioteca/exercicios", body);
                Toast.sucesso("Exercício adicionado à biblioteca!");
            }
            modal.remove();
            aoSalvar();
        } catch (err) {
            Toast.erro(err.message);
            btnSalvar.disabled = false;
        }
    });
}

// ---------------------------------------------------------------- Gerenciar categorias

function abrirModalCategorias(categoriasAtuais, aoAtualizar) {
    const EMOJIS_SUGERIDOS = ["📘", "🗣️", "🤸", "🧠", "🖐️", "🤝", "🎨", "🎵", "🧩", "❤️"];
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:6px;">🏷️ Categorias da Biblioteca</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:16px;">
          Organize os exercícios do jeito que faz sentido pra sua clínica — cada especialidade
          costuma ter suas próprias categorias.
        </p>
        <div id="lista-categorias-atual" class="coluna gap-2" style="margin-bottom:18px;">
          ${categoriasAtuais.length ? categoriasAtuais.map(c => `<div class="linha gap-2 cartao-flat" style="padding:8px 12px;"><span style="font-size:18px;">${c.icone_emoji}</span><span class="texto-sm" style="flex:1;">${escapeHtml(c.nome)}</span></div>`).join("") : `<p class="texto-sm texto-suave">Nenhuma categoria criada ainda.</p>`}
        </div>
        <hr style="border:none; border-top:1px solid var(--cor-borda); margin-bottom:16px;" />
        <p class="texto-sm" style="font-weight:700; margin-bottom:10px;">Nova categoria</p>
        <div class="linha gap-2" style="margin-bottom:10px; flex-wrap:wrap;">
          ${EMOJIS_SUGERIDOS.map((e, i) => `<button type="button" class="botao-icone btn-emoji-categoria ${i === 0 ? "ativo" : ""}" data-emoji="${e}" style="${i === 0 ? "border-color:var(--cor-marca);" : ""}">${e}</button>`).join("")}
        </div>
        <div class="linha gap-2">
          <input type="text" id="nova-categoria-nome" placeholder="Ex: Alimentação, Fala, Coordenação..." style="flex:1; padding:9px 12px; border-radius:8px; border:1.5px solid var(--cor-borda);" />
          <button type="button" class="botao botao-primario botao-sm" id="btn-adicionar-categoria">Adicionar</button>
        </div>
        <button type="button" class="botao botao-secundario" id="btn-cancelar-modal" style="width:100%; margin-top:18px;">Fechar</button>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => { modal.remove(); if (aoAtualizar) aoAtualizar(); despachar(); });

    let emojiEscolhido = EMOJIS_SUGERIDOS[0];
    modal.querySelectorAll(".btn-emoji-categoria").forEach(btn => btn.addEventListener("click", () => {
        modal.querySelectorAll(".btn-emoji-categoria").forEach(b => b.style.borderColor = "var(--cor-borda)");
        btn.style.borderColor = "var(--cor-marca)";
        emojiEscolhido = btn.dataset.emoji;
    }));

    document.getElementById("btn-adicionar-categoria").addEventListener("click", async () => {
        const nome = document.getElementById("nova-categoria-nome").value.trim();
        if (!nome) { Toast.erro("Dê um nome pra categoria."); return; }
        try {
            await Api.post("/biblioteca/categorias", { nome, icone_emoji: emojiEscolhido });
            Toast.sucesso("Categoria criada!");
            modal.remove();
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });
}
