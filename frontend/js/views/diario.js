// ============================================================================
// views/diario.js — Módulo 07: Diário Terapêutico
//
// "Ao invés de apenas ver um gráfico, os responsáveis passam a entender o
// que realmente está acontecendo com o filho." Registro estruturado de
// evolução clínica, com pontos positivos/atenção, objetivo da semana,
// mensagem em linguagem acessível para a família e anexos opcionais.
// ============================================================================

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

// ---------------------------------------------------------------- Campo de anexos
// Um componente só para o Novo Diário, o Atender e o "Editar registro"
// (25/11/2026). Os arquivos escolhidos ficam pendentes e sobem com
// `enviar(diarioId)` depois que o registro existe; os que já estão no registro
// aparecem em cima, com ✕ (remove na hora, só autor ou gestor — o backend confere).

const ICONES_ANEXO = { foto: "🖼️", audio: "🎙️", video: "🎬" };

// Storage ligado? Qual o limite? (25/11/2026) Pedido uma vez por carregamento
// do app; o limite vem da variável DIARIO_ANEXO_LIMITE_MB do servidor.
let _configAnexosDiario = null;
function configAnexosDiario() {
    if (!_configAnexosDiario) {
        _configAnexosDiario = Api.get("/diario/anexos/config")
            .then(c => { ajustarLimiteAnexoDiario(c.limite_mb); return c; })
            .catch(() => { _configAnexosDiario = null; return { storage: false, limite_mb: 4 }; });
    }
    return _configAnexosDiario;
}

function _base64ParaBlob(base64, mime) {
    const bin = atob(base64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: mime });
}

const _MIME_POR_EXTENSAO = {
    mp4: "video/mp4", m4v: "video/mp4", mov: "video/quicktime", webm: "video/webm",
    mp3: "audio/mpeg", m4a: "audio/mp4", aac: "audio/aac", ogg: "audio/ogg", oga: "audio/ogg", wav: "audio/wav", opus: "audio/ogg",
    gif: "image/gif",
};

// PUT direto para o Supabase Storage (link de uso único do servidor), com a
// porcentagem para vídeos grandes no celular. Mesmo formato do supabase-js.
function enviarArquivoParaStorage(url, blob, aoProgresso) {
    return new Promise((resolve, reject) => {
        const corpo = new FormData();
        corpo.append("cacheControl", "3600");
        corpo.append("", blob);
        const xhr = new XMLHttpRequest();
        xhr.open("PUT", url);
        xhr.setRequestHeader("x-upsert", "false");
        xhr.upload.onprogress = (e) => { if (e.lengthComputable) aoProgresso(Math.round((e.loaded * 100) / e.total)); };
        xhr.onload = () => (xhr.status >= 200 && xhr.status < 300) ? resolve()
            : reject(new Error(`O armazenamento recusou o arquivo (erro ${xhr.status}). Tente de novo.`));
        xhr.onerror = () => reject(new Error("A conexão caiu durante o envio. Tente de novo."));
        xhr.send(corpo);
    });
}

function renderCampoAnexos(prefixo) {
    return `
    <div class="campo">
      <label for="${prefixo}-anexos">📎 Anexos (opcional — foto, áudio ou vídeo curto da sessão)</label>
      <div id="${prefixo}-anexos-existentes" class="coluna gap-2" style="margin-bottom:8px;"></div>
      <input type="file" id="${prefixo}-anexos" accept="image/*,audio/*,video/*" multiple />
      <div id="${prefixo}-anexos-orientacao">${renderOrientacaoEnvio("anexo_diario")}</div>
      <div id="${prefixo}-anexos-pendentes" class="coluna gap-2" style="margin-top:8px;"></div>
    </div>`;
}

function ligarCampoAnexos(raiz, prefixo, { existentes = [], podeRemover = false } = {}) {
    // Pendente: { tipo, nome_arquivo, mime, blob } (Storage) ou { tipo, nome_arquivo, conteudo_base64 } (banco).
    const pendentes = [];
    const atuais = existentes.slice();
    const elExistentes = raiz.querySelector(`#${prefixo}-anexos-existentes`);
    const elPendentes = raiz.querySelector(`#${prefixo}-anexos-pendentes`);
    const config = configAnexosDiario();
    config.then(() => {
        const el = raiz.querySelector(`#${prefixo}-anexos-orientacao`);
        if (el) el.innerHTML = renderOrientacaoEnvio("anexo_diario");
    });

    const linha = (a, i, classe, titulo, extra = "") => `
      <div class="linha gap-2 cartao-flat" style="padding:8px 10px;">
        <span>${ICONES_ANEXO[a.tipo] || "📎"}</span>
        <span class="texto-sm" style="flex:1; min-width:0; overflow-wrap:anywhere;">${escapeHtml(a.nome_arquivo || "anexo")}${extra}</span>
        ${classe ? `<button type="button" class="botao-icone ${classe}" data-idx="${i}" title="${titulo}" aria-label="${titulo}" style="width:26px; height:26px; font-size:11px;">✕</button>` : ""}
      </div>`;

    function renderExistentes() {
        elExistentes.innerHTML = atuais.map((a, i) =>
            linha(a, i, podeRemover ? "btn-remover-anexo-existente" : "", "Remover do registro",
                ` <span class="texto-xs texto-suave">· já no registro</span>`)).join("");
        elExistentes.querySelectorAll(".btn-remover-anexo-existente").forEach(btn => btn.addEventListener("click", async () => {
            const a = atuais[Number(btn.dataset.idx)];
            if (!confirm(`Remover "${a.nome_arquivo || "anexo"}" deste registro? Ele sai na hora, para a equipe e para a família.`)) return;
            btn.disabled = true;
            try {
                await Api.del(`/diario/anexo/${a.id}`);
                atuais.splice(atuais.indexOf(a), 1);
                renderExistentes();
                Toast.sucesso("Anexo removido.");
            } catch (err) { Toast.erro(err.message); btn.disabled = false; }
        }));
    }

    function renderPendentes() {
        elPendentes.innerHTML = pendentes.map((a, i) => linha(a, i, "btn-remover-anexo", "Tirar da lista",
            ` <span class="texto-xs texto-suave anexo-progresso" data-progresso="${i}">${a.blob ? `· ${(a.blob.size / 1048576).toFixed(1).replace(".", ",")} MB` : ""}</span>`)).join("");
        elPendentes.querySelectorAll(".btn-remover-anexo").forEach(btn => btn.addEventListener("click", () => {
            pendentes.splice(Number(btn.dataset.idx), 1);
            renderPendentes();
        }));
    }

    // Com o Storage: foto reduzida no navegador (vira Blob); vídeo/áudio/GIF vão como estão.
    async function prepararParaStorage(file) {
        const validacao = validarEntradaEnvio(file, "anexo_diario");
        if (!validacao.ok) throw new Error(validacao.erro);
        if (["jpeg", "png", "webp"].includes(validacao.formato)) {
            const r = await prepararImagemParaEnvio(file, "anexo_diario");
            if (r.aviso) Toast.info(r.aviso);
            return { tipo: "foto", nome_arquivo: r.nome, mime: r.mime, blob: _base64ParaBlob(r.base64, r.mime) };
        }
        const ext = String(file.name || "").split(".").pop().toLowerCase();
        const mime = file.type || _MIME_POR_EXTENSAO[ext] || "application/octet-stream";
        const tipo = categoriaEnvio(validacao.formato) === "imagem" ? "foto" : validacao.formato; // "video" | "audio"
        // Alguns Android mandam o arquivo sem tipo: o Storage guardaria como "octet-stream".
        return { tipo, nome_arquivo: file.name, mime, blob: file.type ? file : new Blob([file], { type: mime }) };
    }

    raiz.querySelector(`#${prefixo}-anexos`).addEventListener("change", async (e) => {
        const arquivos = Array.from(e.target.files);
        e.target.value = "";
        const { storage } = await config;
        // Um arquivo recusado não impede os outros (um aviso por arquivo).
        for (const file of arquivos) {
            try {
                if (storage) {
                    pendentes.push(await prepararParaStorage(file));
                    continue;
                }
                const preparado = await prepararArquivoParaEnvio(file, "anexo_diario");
                if (preparado.aviso) Toast.info(preparado.aviso);
                const tipo = preparado.formato === "imagem" ? "foto" : preparado.formato; // "video" | "audio"
                pendentes.push({ tipo, nome_arquivo: preparado.nome, conteudo_base64: preparado.base64 });
            } catch (err) { Toast.erro(err.message); }
        }
        renderPendentes();
    });

    async function enviarUm(diarioId, a) {
        if (!a.blob) return Api.post(`/diario/${diarioId}/anexo`, a);
        const { caminho, url_envio } = await Api.post(`/diario/${diarioId}/anexo/envio`,
            { tipo: a.tipo, nome_arquivo: a.nome_arquivo, mime: a.mime, tamanho_bytes: a.blob.size });
        const elProgresso = elPendentes.querySelector('[data-progresso="0"]');
        await enviarArquivoParaStorage(url_envio, a.blob, (pct) => {
            if (elProgresso) elProgresso.textContent = `· enviando… ${pct}%`;
        });
        if (elProgresso) elProgresso.textContent = "· conferindo…";
        return Api.post(`/diario/${diarioId}/anexo/confirmar`,
            { caminho, tipo: a.tipo, nome_arquivo: a.nome_arquivo, mime: a.mime });
    }

    renderExistentes();
    return {
        pendentes,
        // Envia um por um e tira da lista o que já subiu: se um falhar, o
        // erro sobe e os que faltam continuam na tela para tentar de novo.
        async enviar(diarioId) {
            while (pendentes.length) {
                const a = pendentes[0];
                const r = await enviarUm(diarioId, a);
                pendentes.shift();
                atuais.push({ id: r.id, tipo: a.tipo, nome_arquivo: a.nome_arquivo });
                renderPendentes();
                renderExistentes();
            }
        },
    };
}

// ---------------------------------------------------------------- Novo Diário

// Desde 08/10/2026 o Diário é do paciente (funciona sem jornada).
function abrirModalNovoDiario(paciente) {
    const positivos = [];
    const atencao = [];

    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa modal-grande">
        <h3 style="margin-bottom:4px;">📔 Novo Diário Terapêutico</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:18px;">${escapeHtml(emojiMascote(paciente.avatar_mascote, Sessao.usuario?.organizacao))} ${escapeHtml(paciente.nome)} — registre a sessão em linguagem clara, a família vai receber isso.</p>
        <form id="form-novo-diario">
          <div class="campo"><label>Data do atendimento ${ASTERISCO_OBRIGATORIO}</label><input type="date" id="di-data" value="${hojeInputDate()}" required /></div>

          <div class="campo">
            <label>Evolução clínica ${ASTERISCO_OBRIGATORIO}</label>
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

          ${renderCampoAnexos("di")}

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

    const campoAnexos = ligarCampoAnexos(modal, "di");
    let diarioCriado = null;

    document.getElementById("form-novo-diario").addEventListener("submit", async (e) => {
        e.preventDefault();
        const btnSalvar = document.getElementById("btn-salvar-diario");
        btnSalvar.disabled = true;
        btnSalvar.textContent = "Salvando...";
        try {
            // Se um anexo falhou depois de o registro ser criado, tentar de novo
            // só reenvia os anexos (não duplica o registro).
            const r = diarioCriado || await Api.post(`/diario/paciente/${paciente.id}`, {
                data_atendimento: document.getElementById("di-data").value,
                evolucao_clinica: document.getElementById("di-evolucao").value.trim(),
                pontos_positivos: positivos,
                pontos_atencao: atencao,
                objetivo_semana: document.getElementById("di-objetivo").value.trim(),
                mensagem_familia: document.getElementById("di-mensagem").value.trim(),
                compartilhado_familia: document.getElementById("di-compartilhar").checked,
            });
            diarioCriado = r;
            await campoAnexos.enviar(r.id);
            Toast.sucesso("Diário salvo" + (document.getElementById("di-compartilhar").checked ? " e compartilhado com a família! 💛" : "!"));
            modal.remove();
            despachar();
        } catch (err) {
            Toast.erro(diarioCriado ? `O registro foi salvo, mas um anexo não subiu: ${err.message} Clique em "Enviar anexos" para tentar de novo.` : err.message);
            btnSalvar.disabled = false;
            btnSalvar.textContent = diarioCriado ? "Enviar anexos" : "Salvar diário";
        }
    });
}

function hojeInputDate() {
    return new Date().toISOString().slice(0, 10);
}

// ---------------------------------------------------------------- Histórico completo

async function abrirModalHistoricoDiario(pacienteId) {
    const diarios = await Api.get(`/diario/paciente/${pacienteId}`);
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa modal-grande">
        <h3 style="margin-bottom:18px;">📔 Histórico completo do Diário Terapêutico</h3>
        <div class="timeline" style="max-height:64vh; overflow-y:auto;">
          ${diarios.length ? diarios.map(d => `
            <div class="timeline-item">
              <div class="timeline-data">${formatarData(d.data_atendimento)} · ${escapeHtml(d.profissional_nome)} ${d.origem === "importacao" ? seloDiarioImportado() : (d.compartilhado_familia ? "" : `<span class="badge badge-neutro texto-xs">não compartilhado</span>`)}</div>
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
          ${u.papel === "responsavel" ? "" : (d.origem === "importacao" ? seloDiarioImportado() : (d.compartilhado_familia ? `<span class="badge badge-sucesso">Compartilhado com a família</span>` : `<span class="badge badge-neutro">Interno</span>`))}
        </div>
        <p class="texto-xs texto-suave" style="margin-bottom:18px;">Registrado por ${escapeHtml(d.profissional_nome)}</p>

        <div id="visualizacao-diario">
        ${d.evolucao_clinica ? `
        <p class="texto-xs texto-suave" style="font-weight:700;">EVOLUÇÃO CLÍNICA</p>
        <p class="texto-sm" style="margin-bottom:16px;">${escapeHtml(d.evolucao_clinica)}</p>` : ""}

        ${d.pontos_positivos.length ? `
        <p class="texto-xs texto-suave" style="font-weight:700;">PONTOS POSITIVOS</p>
        <ul style="margin:6px 0 16px; padding-left:20px;">${d.pontos_positivos.map(p => `<li class="texto-sm">✔️ ${escapeHtml(p)}</li>`).join("")}</ul>` : ""}

        ${d.pontos_atencao.length ? `
        <p class="texto-xs texto-suave" style="font-weight:700;">PONTOS DE ATENÇÃO</p>
        <ul style="margin:6px 0 16px; padding-left:20px;">${d.pontos_atencao.map(p => `<li class="texto-sm">⚠️ ${escapeHtml(p)}</li>`).join("")}</ul>` : ""}

        ${d.objetivo_semana ? `<div class="cartao-flat" style="margin-bottom:12px;"><p class="texto-sm">🎯 <strong>Objetivo da semana:</strong> ${escapeHtml(d.objetivo_semana)}</p></div>` : ""}
        ${d.mensagem_familia ? `
        <p class="texto-xs texto-suave" style="font-weight:700;">${u.papel === "responsavel" ? "MENSAGEM DA EQUIPE" : "MENSAGEM PARA A FAMÍLIA"}</p>
        <div class="cartao-flat" style="margin:6px 0 12px; background:var(--cor-marca-clara);"><p class="texto-sm">💛 ${escapeHtml(d.mensagem_familia)}</p></div>` : ""}

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
            // Storage (25/11/2026): link temporário — o vídeo toca sem baixar tudo. Antigos: base64.
            const src = escapeHtml(anexo.url
                || `data:${anexo.tipo === "foto" ? "image/png" : anexo.tipo === "audio" ? "audio/mpeg" : "video/mp4"};base64,${anexo.conteudo_base64}`);
            if (anexo.tipo === "foto") elAnexo.innerHTML = `<img src="${src}" style="width:100%; border-radius:8px;" alt="${escapeHtml(anexo.nome_arquivo || "anexo")}" />`;
            else if (anexo.tipo === "audio") elAnexo.innerHTML = `<audio controls preload="metadata" style="width:100%;" src="${src}"></audio>`;
            else elAnexo.innerHTML = `<video controls preload="metadata" playsinline style="width:100%; border-radius:8px;" src="${src}"></video>`;
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
      ${renderCampoAnexos("ed")}
      <div class="linha gap-3" style="margin-top:14px;">
        <button type="button" class="botao botao-primario" id="btn-salvar-edicao-diario">Salvar alterações</button>
        <button type="button" class="botao botao-secundario" id="btn-cancelar-edicao-diario">Cancelar</button>
      </div>`;

    const campoAnexos = ligarCampoAnexos(wrapEdicao, "ed", { existentes: d.anexos || [], podeRemover: true });
    wrapEdicao.querySelector("#btn-cancelar-edicao-diario").addEventListener("click", () => modal.remove());
    const btnSalvar = wrapEdicao.querySelector("#btn-salvar-edicao-diario");
    btnSalvar.addEventListener("click", async () => {
        btnSalvar.disabled = true;
        try {
            await Api.put(`/diario/${d.id}`, {
                evolucao_clinica: modal.querySelector("#ed-evolucao").value.trim(),
                mensagem_familia: modal.querySelector("#ed-mensagem").value.trim(),
                objetivo_semana: modal.querySelector("#ed-objetivo").value.trim(),
            });
            await campoAnexos.enviar(d.id);
            Toast.sucesso("Registro atualizado!");
            modal.remove();
        } catch (err) { Toast.erro(err.message); btnSalvar.disabled = false; }
    });
}
