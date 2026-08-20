// ============================================================================
// views/diario.js — Módulo 07: Diário Terapêutico
//
// "Ao invés de apenas ver um gráfico, os responsáveis passam a entender o
// que realmente está acontecendo com o filho." Registro estruturado de
// evolução clínica, com pontos positivos/atenção, objetivo da semana,
// mensagem em linguagem acessível para a família e anexos opcionais.
// ============================================================================

const LIMITE_ANEXO_MB = 4;

function renderListaDinamica(idContainer, itens, placeholder) {
    return `
    <div id="${idContainer}" class="coluna gap-2">
      ${itens.map((item, i) => `
        <div class="linha gap-2 item-lista-dinamica" data-idx="${i}">
          <span class="texto-sm" style="flex:1;">${escapeHtml(item)}</span>
          <button type="button" class="botao-icone btn-remover-item" style="width:28px; height:28px; font-size:12px;">✕</button>
        </div>`).join("")}
    </div>
    <div class="linha gap-2" style="margin-top:8px;">
      <input type="text" class="input-novo-item" placeholder="${placeholder}" style="flex:1; padding:9px 12px; border-radius:8px; border:1.5px solid var(--cor-borda); font-size:13.5px;" />
      <button type="button" class="botao botao-secundario botao-sm btn-adicionar-item">+ Adicionar</button>
    </div>`;
}

function ativarListaDinamica(container, estadoArray) {
    const inputNovo = container.querySelector(".input-novo-item");
    const btnAdicionar = container.querySelector(".btn-adicionar-item");
    const listaEl = container.querySelector('[id^="lista-"]') || container.querySelector(".coluna");

    function rerenderizar() {
        listaEl.innerHTML = estadoArray.map((item, i) => `
          <div class="linha gap-2 item-lista-dinamica" data-idx="${i}">
            <span class="texto-sm" style="flex:1;">${escapeHtml(item)}</span>
            <button type="button" class="botao-icone btn-remover-item" style="width:28px; height:28px; font-size:12px;">✕</button>
          </div>`).join("");
        listaEl.querySelectorAll(".btn-remover-item").forEach((btn, i) => btn.addEventListener("click", () => {
            estadoArray.splice(i, 1);
            rerenderizar();
        }));
    }
    function adicionar() {
        const valor = inputNovo.value.trim();
        if (!valor) return;
        estadoArray.push(valor);
        inputNovo.value = "";
        rerenderizar();
    }
    btnAdicionar.addEventListener("click", adicionar);
    inputNovo.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); adicionar(); } });
    rerenderizar();
}

// ---------------------------------------------------------------- Novo Diário

function abrirModalNovoDiario(jornadaId, paciente) {
    const positivos = [];
    const atencao = [];
    const anexosPendentes = []; // { tipo, nome_arquivo, conteudo_base64 }

    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa modal-grande">
        <h3 style="margin-bottom:4px;">📔 Novo Diário Terapêutico</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:18px;">${paciente.avatar_mascote} ${escapeHtml(paciente.nome)} — registre a sessão em linguagem clara, a família vai receber isso.</p>
        <form id="form-novo-diario">
          <div class="campo"><label>Data do atendimento</label><input type="date" id="di-data" value="${hojeInputDate()}" required /></div>

          <div class="campo">
            <label>Evolução clínica</label>
            <textarea id="di-evolucao" rows="3" required placeholder="Ex: João apresentou melhora significativa na produção dos fonemas /P/ e /B/..."></textarea>
            <p class="texto-xs texto-suave" style="margin-top:4px;">Fica guardado no histórico clínico — a família nunca vê este campo, mesmo quando o registro é compartilhado.</p>
          </div>

          <div class="campo">
            <label>💛 Mensagem para a família</label>
            <textarea id="di-mensagem" rows="2" placeholder="Escreva em linguagem simples e acolhedora — é isso que a família vai ler."></textarea>
          </div>

          <div class="campo">
            <label>✔️ Pontos positivos</label>
            <div id="wrap-positivos">${renderListaDinamica("lista-positivos", [], "Ex: Participou bem da sessão")}</div>
          </div>

          <div class="campo">
            <label>⚠️ Pontos de atenção</label>
            <div id="wrap-atencao">${renderListaDinamica("lista-atencao", [], "Ex: Continuar estimulando frases completas")}</div>
          </div>

          <div class="campo"><label>🎯 Objetivo da próxima semana</label><input type="text" id="di-objetivo" placeholder="Ex: Incentivar frases com três palavras durante atividades em casa" /></div>

          <div class="campo">
            <label>📎 Anexos (opcional — foto, áudio ou vídeo curto da sessão, até ${LIMITE_ANEXO_MB}MB cada)</label>
            <input type="file" id="di-anexos" accept="image/*,audio/*,video/*" multiple />
            <div id="lista-anexos-pendentes" class="coluna gap-2" style="margin-top:8px;"></div>
          </div>

          <label class="linha gap-2" style="margin:14px 0; font-size:13.5px;">
            <input type="checkbox" id="di-compartilhar" checked /> Compartilhar automaticamente com a família (recomendado)
          </label>

          <div class="linha gap-3" style="margin-top:10px;">
            <button type="submit" class="botao botao-primario" id="btn-salvar-diario">Salvar diário</button>
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());

    ativarListaDinamica(document.getElementById("wrap-positivos"), positivos);
    ativarListaDinamica(document.getElementById("wrap-atencao"), atencao);

    const listaAnexosEl = document.getElementById("lista-anexos-pendentes");
    function renderizarAnexosPendentes() {
        listaAnexosEl.innerHTML = anexosPendentes.map((a, i) => `
          <div class="linha gap-2 cartao-flat" style="padding:8px 10px;">
            <span>${{ foto: "🖼️", audio: "🎙️", video: "🎬" }[a.tipo]}</span>
            <span class="texto-sm" style="flex:1;">${escapeHtml(a.nome_arquivo)}</span>
            <button type="button" class="botao-icone btn-remover-anexo" data-idx="${i}" style="width:26px; height:26px; font-size:11px;">✕</button>
          </div>`).join("");
        listaAnexosEl.querySelectorAll(".btn-remover-anexo").forEach(btn => btn.addEventListener("click", () => {
            anexosPendentes.splice(Number(btn.dataset.idx), 1);
            renderizarAnexosPendentes();
        }));
    }

    document.getElementById("di-anexos").addEventListener("change", async (e) => {
        for (const file of Array.from(e.target.files)) {
            if (file.size > LIMITE_ANEXO_MB * 1024 * 1024) {
                Toast.erro(`"${file.name}" passa de ${LIMITE_ANEXO_MB}MB e não foi adicionado.`);
                continue;
            }
            const tipo = file.type.startsWith("image/") ? "foto" : file.type.startsWith("audio/") ? "audio" : file.type.startsWith("video/") ? "video" : null;
            if (!tipo) { Toast.erro(`"${file.name}" não é foto, áudio ou vídeo.`); continue; }
            const base64 = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result.split(",")[1]);
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
            anexosPendentes.push({ tipo, nome_arquivo: file.name, conteudo_base64: base64 });
        }
        renderizarAnexosPendentes();
        e.target.value = "";
    });

    document.getElementById("form-novo-diario").addEventListener("submit", async (e) => {
        e.preventDefault();
        const btnSalvar = document.getElementById("btn-salvar-diario");
        btnSalvar.disabled = true;
        btnSalvar.textContent = "Salvando...";
        try {
            const r = await Api.post(`/diario/jornada/${jornadaId}`, {
                data_atendimento: document.getElementById("di-data").value,
                evolucao_clinica: document.getElementById("di-evolucao").value.trim(),
                pontos_positivos: positivos,
                pontos_atencao: atencao,
                objetivo_semana: document.getElementById("di-objetivo").value.trim(),
                mensagem_familia: document.getElementById("di-mensagem").value.trim(),
                compartilhado_familia: document.getElementById("di-compartilhar").checked,
            });
            for (const anexo of anexosPendentes) {
                await Api.post(`/diario/${r.id}/anexo`, anexo);
            }
            Toast.sucesso("Diário salvo" + (document.getElementById("di-compartilhar").checked ? " e compartilhado com a família! 💛" : "!"));
            modal.remove();
            despachar();
        } catch (err) {
            Toast.erro(err.message);
            btnSalvar.disabled = false;
            btnSalvar.textContent = "Salvar diário";
        }
    });
}

function hojeInputDate() {
    return new Date().toISOString().slice(0, 10);
}

// ---------------------------------------------------------------- Histórico completo

async function abrirModalHistoricoDiario(jornadaId) {
    const diarios = await Api.get(`/diario/jornada/${jornadaId}`);
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa modal-grande">
        <h3 style="margin-bottom:18px;">📔 Histórico completo do Diário Terapêutico</h3>
        <div class="timeline" style="max-height:64vh; overflow-y:auto;">
          ${diarios.length ? diarios.map(d => `
            <div class="timeline-item">
              <div class="timeline-data">${formatarData(d.data_atendimento)} · ${escapeHtml(d.profissional_nome)} ${d.compartilhado_familia ? "" : `<span class="badge badge-neutro texto-xs">não compartilhado</span>`}</div>
              <div class="timeline-texto">${escapeHtml(d.evolucao_clinica)}</div>
              <button type="button" class="botao-texto botao-sm btn-ver-diario-historico" data-id="${d.id}" style="padding:4px 0;">Ver registro completo →</button>
            </div>`).join("") : `<p class="texto-sm texto-suave">Nenhum registro ainda.</p>`}
        </div>
        <button type="button" class="botao botao-secundario" id="btn-cancelar-modal" style="margin-top:16px;">Fechar</button>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    modal.querySelectorAll(".btn-ver-diario-historico").forEach(btn => btn.addEventListener("click", () => {
        modal.remove(); // fecha o histórico antes de abrir o detalhe — evita 2 modais com o mesmo id empilhados (bug: botão Fechar não funcionava)
        abrirModalDetalheDiario(btn.dataset.id);
    }));
}

// ---------------------------------------------------------------- Detalhe de um registro

async function abrirModalDetalheDiario(diarioId) {
    const d = await Api.get(`/diario/${diarioId}`);
    const u = Sessao.usuario;
    const podeEditar = u.papel === "gestor" || (u.papel === "profissional" && d.profissional_id === u.id);
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa modal-grande">
        <div class="linha-entre" style="margin-bottom:4px;">
          <h3>📔 Registro de ${formatarData(d.data_atendimento)}</h3>
          ${d.compartilhado_familia ? `<span class="badge badge-sucesso">Compartilhado com a família</span>` : `<span class="badge badge-neutro">Interno</span>`}
        </div>
        <p class="texto-xs texto-suave" style="margin-bottom:18px;">Registrado por ${escapeHtml(d.profissional_nome)}</p>

        <div id="visualizacao-diario">
        <p class="texto-xs texto-suave" style="font-weight:700;">EVOLUÇÃO CLÍNICA</p>
        <p class="texto-sm" style="margin-bottom:16px;">${escapeHtml(d.evolucao_clinica)}</p>

        ${d.pontos_positivos.length ? `
        <p class="texto-xs texto-suave" style="font-weight:700;">PONTOS POSITIVOS</p>
        <ul style="margin:6px 0 16px; padding-left:20px;">${d.pontos_positivos.map(p => `<li class="texto-sm">✔️ ${escapeHtml(p)}</li>`).join("")}</ul>` : ""}

        ${d.pontos_atencao.length ? `
        <p class="texto-xs texto-suave" style="font-weight:700;">PONTOS DE ATENÇÃO</p>
        <ul style="margin:6px 0 16px; padding-left:20px;">${d.pontos_atencao.map(p => `<li class="texto-sm">⚠️ ${escapeHtml(p)}</li>`).join("")}</ul>` : ""}

        ${d.objetivo_semana ? `<div class="cartao-flat" style="margin-bottom:12px;"><p class="texto-sm">🎯 <strong>Objetivo da semana:</strong> ${escapeHtml(d.objetivo_semana)}</p></div>` : ""}
        ${d.mensagem_familia ? `<div class="cartao-flat" style="margin-bottom:12px; background:var(--cor-marca-clara);"><p class="texto-sm">💛 ${escapeHtml(d.mensagem_familia)}</p></div>` : ""}

        ${d.anexos.length ? `
        <p class="texto-xs texto-suave" style="font-weight:700; margin-top:8px;">ANEXOS</p>
        <div id="wrap-anexos-detalhe" class="grade" style="grid-template-columns:repeat(auto-fill,minmax(140px,1fr)); margin-top:8px;">
          ${d.anexos.map(a => `<div class="cartao-flat texto-xs" data-anexo-id="${a.id}" data-anexo-tipo="${a.tipo}" style="text-align:center;">Carregando ${a.tipo}...</div>`).join("")}
        </div>` : ""}
        </div>

        <div id="edicao-diario" style="display:none;"></div>

        <div class="linha gap-3" style="margin-top:18px;">
          ${podeEditar ? `<button type="button" class="botao botao-secundario" id="btn-editar-diario">✏️ Editar registro</button>` : ""}
          <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Fechar</button>
        </div>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    modal.querySelector("#btn-cancelar-modal").addEventListener("click", () => modal.remove());

    const btnEditar = modal.querySelector("#btn-editar-diario");
    if (btnEditar) btnEditar.addEventListener("click", () => ativarEdicaoDiario(modal, d));

    // Carrega o conteúdo dos anexos sob demanda (evita pesar a listagem principal)
    modal.querySelectorAll("[data-anexo-id]").forEach(async (elAnexo) => {
        try {
            const anexo = await Api.get(`/diario/anexo/${elAnexo.dataset.anexoId}`);
            const src = `data:${anexo.tipo === "foto" ? "image/png" : anexo.tipo === "audio" ? "audio/mpeg" : "video/mp4"};base64,${anexo.conteudo_base64}`;
            if (anexo.tipo === "foto") elAnexo.innerHTML = `<img src="${src}" style="width:100%; border-radius:8px;" alt="${escapeHtml(anexo.nome_arquivo || "anexo")}" />`;
            else if (anexo.tipo === "audio") elAnexo.innerHTML = `<audio controls style="width:100%;"><source src="${src}"></audio>`;
            else elAnexo.innerHTML = `<video controls style="width:100%; border-radius:8px;"><source src="${src}"></video>`;
        } catch (err) {
            elAnexo.textContent = "Não foi possível carregar este anexo.";
        }
    });
}

function ativarEdicaoDiario(modal, d) {
    // Troca a visualização pelo formulário de edição, dentro do mesmo modal
    // (evita empilhar mais um modal por cima e reabrir o mesmo bug de antes).
    modal.querySelector("#visualizacao-diario").style.display = "none";
    modal.querySelectorAll(".linha.gap-3").forEach(el => { if (el.querySelector("#btn-editar-diario")) el.style.display = "none"; });

    const wrapEdicao = modal.querySelector("#edicao-diario");
    wrapEdicao.style.display = "block";
    wrapEdicao.innerHTML = `
      <div class="campo">
        <label>Evolução clínica</label>
        <textarea id="ed-evolucao" rows="3">${escapeHtml(d.evolucao_clinica)}</textarea>
        <p class="texto-xs texto-suave" style="margin-top:4px;">A família nunca vê este campo, mesmo compartilhado.</p>
      </div>
      <div class="campo">
        <label>💛 Mensagem para a família</label>
        <textarea id="ed-mensagem" rows="2">${escapeHtml(d.mensagem_familia || "")}</textarea>
      </div>
      <div class="campo"><label>🎯 Objetivo da próxima semana</label><input type="text" id="ed-objetivo" value="${escapeHtml(d.objetivo_semana || "")}" /></div>
      <div class="linha gap-3" style="margin-top:14px;">
        <button type="button" class="botao botao-primario" id="btn-salvar-edicao-diario">Salvar alterações</button>
        <button type="button" class="botao botao-secundario" id="btn-cancelar-edicao-diario">Cancelar</button>
      </div>`;

    wrapEdicao.querySelector("#btn-cancelar-edicao-diario").addEventListener("click", () => modal.remove());
    wrapEdicao.querySelector("#btn-salvar-edicao-diario").addEventListener("click", async () => {
        try {
            await Api.put(`/diario/${d.id}`, {
                evolucao_clinica: modal.querySelector("#ed-evolucao").value.trim(),
                mensagem_familia: modal.querySelector("#ed-mensagem").value.trim(),
                objetivo_semana: modal.querySelector("#ed-objetivo").value.trim(),
            });
            Toast.sucesso("Registro atualizado!");
            modal.remove();
        } catch (err) { Toast.erro(err.message); }
    });
}
