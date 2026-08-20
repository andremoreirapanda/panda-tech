// ============================================================================
// views/comunicacao.js — Chat (UX Pattern 05) e Mural de Avisos
// ============================================================================

async function viewMensagens(app, params, query) {
    const u = Sessao.usuario;
    const base = u.papel === "gestor" ? "gestor" : (u.papel === "profissional" ? "profissional" : "responsavel");
    const pacientes = await Api.get("/pessoas/pacientes");
    if (!pacientes.length) {
        const vazio = `<div class="estado-vazio"><div class="emoji">💬</div><h3>Nenhuma conversa disponível ainda</h3></div>`;
        app.innerHTML = base === "responsavel" ? renderShellMobile("#/responsavel/mensagens", { icone: "💬", texto: "Conversas" }, vazio)
            : renderShellSidebar(`#/${base}/mensagens`, "Mensagens", vazio);
        if (base !== "responsavel") anexarEventosShell();
        return;
    }
    const paramPaciente = query && query.get("paciente");
    const pacienteId = paramPaciente || pacientes[0].id;
    const pacienteAtual = pacientes.find(p => String(p.id) === String(pacienteId)) || pacientes[0];

    const { mensagens } = await Api.get(`/comunicacao/paciente/${pacienteAtual.id}/conversa`);

    const listaConversas = pacientes.length > 1 ? `
      <div class="chat-lista-conversas">
        ${pacientes.map(p => `
          <a href="#/${base}/mensagens?paciente=${p.id}" class="pessoa-linha ${String(p.id) === String(pacienteAtual.id) ? "ativo" : ""}"
             style="${String(p.id) === String(pacienteAtual.id) ? "background:var(--cor-marca-clara);" : ""}">
            <div class="pessoa-avatar">${p.avatar_mascote}</div>
            <div class="pessoa-info"><div class="pessoa-nome">${escapeHtml(p.nome)}</div></div>
          </a>`).join("")}
      </div>` : "";

    const chatHtml = `
      <div style="flex:1; display:flex; flex-direction:column; min-height:0; min-width:0;">
        <div id="lista-mensagens" class="chat-lista" style="flex:1; overflow-y:auto; max-height:${base === "responsavel" ? "60vh" : "50vh"};">
          ${mensagens.length ? mensagens.map(m => renderBolhaMensagem(m, u.id)).join("") : `<p class="texto-sm texto-suave" style="text-align:center; padding:30px;">Envie a primeira mensagem 👋</p>`}
        </div>
        <form id="form-mensagem" class="chat-input-barra">
          <input type="file" id="input-anexo-chat" accept="image/*,video/*,audio/*" style="display:none;" />
          <button type="button" class="botao-icone" id="btn-anexar-chat" title="Enviar foto, áudio ou vídeo" style="border-radius:50%; flex-shrink:0;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
          </button>
          <input type="text" id="input-mensagem" placeholder="Escreva uma mensagem..." autocomplete="off" />
          <button type="submit" class="botao botao-primario botao-icone" title="Enviar" style="border-radius:50%; flex-shrink:0;">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4l-8.5 8.5h5.5V20h6v-7.5h5.5z"/></svg>
          </button>
        </form>
      </div>`;

    const conteudo = `<div class="cartao chat-layout" style="min-height:400px;">${listaConversas}${chatHtml}</div>`;

    if (base === "responsavel") {
        app.innerHTML = renderShellMobile("#/responsavel/mensagens", { icone: "💬", texto: `Conversa · ${pacienteAtual.nome}` }, conteudo);
    } else {
        app.innerHTML = renderShellSidebar(`#/${base}/mensagens`, "Mensagens", conteudo);
        anexarEventosShell();
    }

    const listaEl = document.getElementById("lista-mensagens");
    if (listaEl) listaEl.scrollTop = listaEl.scrollHeight;
    anexarEventosReacao(pacienteAtual.id);
    anexarEventosMidia();

    document.getElementById("form-mensagem").addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = document.getElementById("input-mensagem");
        const texto = input.value.trim();
        if (!texto) return;
        input.value = "";
        await Api.post(`/comunicacao/paciente/${pacienteAtual.id}/mensagem`, { conteudo: texto });
        despachar();
    });

    document.getElementById("btn-anexar-chat").addEventListener("click", () => document.getElementById("input-anexo-chat").click());
    document.getElementById("input-anexo-chat").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        if (file.size > LIMITE_ANEXO_CHAT_MB * 1024 * 1024) {
            Toast.erro(`"${file.name}" passa de ${LIMITE_ANEXO_CHAT_MB}MB.`);
            e.target.value = "";
            return;
        }
        const tipo = file.type.startsWith("image/") ? "imagem" : file.type.startsWith("video/") ? "video" : file.type.startsWith("audio/") ? "audio" : null;
        if (!tipo) { Toast.erro("Envie apenas foto, áudio ou vídeo."); return; }
        const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        try {
            await Api.post(`/comunicacao/paciente/${pacienteAtual.id}/mensagem`, { tipo, anexo_base64: base64, anexo_nome: file.name });
            despachar();
        } catch (err) { Toast.erro(err.message); }
        e.target.value = "";
    });
}

const LIMITE_ANEXO_CHAT_MB = 4;

const REACOES_DISPONIVEIS = ["👍", "❤️", "⭐", "👏", "😊"];

function renderBolhaMensagem(m, meuId) {
    const propria = m.autor_id === meuId;
    const ehMidia = ["imagem", "audio", "video"].includes(m.tipo);
    return `
    <div class="chat-bolha-wrap ${propria ? "propria" : "alheia"}">
      ${!propria ? `<div class="chat-autor">${m.autor_avatar || "👤"} ${escapeHtml(m.autor_nome)}</div>` : ""}
      <div class="chat-bolha" data-msg-id="${m.id}">
        ${ehMidia && m.tem_anexo ? `<div class="chat-midia-wrap" data-midia-id="${m.id}" data-midia-tipo="${m.tipo}" style="min-width:160px; min-height:100px; display:flex; align-items:center; justify-content:center;"><span class="texto-xs">${{ imagem: "🖼️", audio: "🎙️", video: "🎬" }[m.tipo]} carregando...</span></div>` : escapeHtml(m.conteudo)}
      </div>
      <div class="linha gap-2" style="margin-top:2px;">
        <div class="chat-hora">${formatarHora(m.criado_em)}</div>
        <button type="button" class="btn-reacao-existente" data-id="${m.id}" data-reacao="${m.reacao || ""}"
                style="border:none; background:none; cursor:pointer; font-size:13px; padding:0;">
          ${m.reacao ? m.reacao : `<span class="btn-abrir-reacoes texto-xs texto-suave" data-id="${m.id}" style="cursor:pointer;">reagir</span>`}
        </button>
      </div>
      <div class="picker-reacoes" data-picker-para="${m.id}" style="display:none; gap:4px; margin-top:4px; background:var(--cor-superficie); border:1px solid var(--cor-borda); border-radius:999px; padding:4px 8px; width:fit-content;">
        ${REACOES_DISPONIVEIS.map(r => `<button type="button" class="btn-escolher-reacao" data-id="${m.id}" data-reacao="${r}" style="border:none; background:none; cursor:pointer; font-size:16px; padding:2px;">${r}</button>`).join("")}
      </div>
    </div>`;
}

function anexarEventosMidia() {
    document.querySelectorAll(".chat-midia-wrap").forEach(async (elMidia) => {
        try {
            const anexo = await Api.get(`/comunicacao/mensagem/${elMidia.dataset.midiaId}/anexo`);
            const mime = anexo.tipo === "imagem" ? "image/png" : anexo.tipo === "audio" ? "audio/mpeg" : "video/mp4";
            const src = `data:${mime};base64,${anexo.anexo_base64}`;
            if (anexo.tipo === "imagem") elMidia.innerHTML = `<img src="${src}" style="max-width:220px; border-radius:12px; display:block;" alt="${escapeHtml(anexo.anexo_nome || "imagem")}" />`;
            else if (anexo.tipo === "audio") elMidia.innerHTML = `<audio controls style="max-width:220px;"><source src="${src}"></audio>`;
            else elMidia.innerHTML = `<video controls style="max-width:220px; border-radius:12px;"><source src="${src}"></video>`;
        } catch (err) {
            elMidia.innerHTML = `<span class="texto-xs texto-suave">Não foi possível carregar este anexo.</span>`;
        }
    });
}

function anexarEventosReacao(pacienteId) {
    document.querySelectorAll(".btn-abrir-reacoes, .btn-reacao-existente").forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            const id = btn.dataset.id;
            const picker = document.querySelector(`.picker-reacoes[data-picker-para="${id}"]`);
            if (!picker) return;
            const abrindo = picker.style.display === "none";
            document.querySelectorAll(".picker-reacoes").forEach(p => p.style.display = "none");
            picker.style.display = abrindo ? "flex" : "none";
        });
    });
    document.querySelectorAll(".btn-escolher-reacao").forEach(btn => {
        btn.addEventListener("click", async (e) => {
            e.stopPropagation();
            try {
                await Api.post(`/comunicacao/mensagem/${btn.dataset.id}/reagir`, { reacao: btn.dataset.reacao });
                despachar();
            } catch (err) { Toast.erro(err.message); }
        });
    });
}

// ---------------------------------------------------------------- Mural

const RÓTULO_PUBLICO_AVISO = { todos: "", equipe: "🔒 Só equipe", familias: "👨‍👩‍👧 Só famílias" };

async function viewMural(app) {
    const u = Sessao.usuario;
    const base = u.papel === "gestor" ? "gestor" : (u.papel === "profissional" ? "profissional" : "responsavel");
    const avisos = await Api.get("/comunicacao/avisos");
    const podePublicar = u.papel === "gestor" || u.papel === "profissional";

    const conteudo = `
    <div class="coluna gap-4">
      ${avisos.length ? avisos.map(a => `
        <div class="cartao">
          <div class="linha-entre" style="margin-bottom:6px; flex-wrap:wrap; gap:6px;">
            <h3 style="font-size:16px;">${escapeHtml(a.titulo)}</h3>
            <div class="linha gap-2" style="align-items:center;">
              ${RÓTULO_PUBLICO_AVISO[a.publico] ? `<span class="badge badge-neutro texto-xs">${RÓTULO_PUBLICO_AVISO[a.publico]}</span>` : ""}
              <span class="texto-xs texto-suave">${tempoRelativo(a.criado_em)}</span>
            </div>
          </div>
          <p class="texto-sm">${escapeHtml(a.conteudo)}</p>
          <p class="texto-xs texto-suave" style="margin-top:8px;">Publicado por ${escapeHtml(a.autor_nome)}</p>
        </div>`).join("") : `<div class="estado-vazio"><div class="emoji">📣</div><p>Nenhum aviso publicado ainda.</p></div>`}
    </div>`;

    if (base === "responsavel") {
        app.innerHTML = renderShellMobile("#/responsavel/mural", { icone: "📣", texto: "Mural" }, conteudo);
    } else {
        app.innerHTML = renderShellSidebar(`#/${base}/mural`, "Mural da Clínica", conteudo,
            podePublicar ? `<button class="botao botao-primario botao-sm" id="btn-novo-aviso">+ Publicar aviso</button>` : "");
        anexarEventosShell();
    }

    const btn = document.getElementById("btn-novo-aviso");
    if (btn) btn.addEventListener("click", () => {
        const modal = el(`
        <div class="modal-fundo">
          <div class="modal-caixa">
            <h3 style="margin-bottom:18px;">Novo aviso</h3>
            <form id="form-novo-aviso">
              <div class="campo"><label>Título</label><input type="text" id="av-titulo" required /></div>
              <div class="campo"><label>Conteúdo</label><textarea id="av-conteudo" rows="4" required></textarea></div>
              <div class="campo">
                <label>Quem deve ver este aviso?</label>
                <select id="av-publico">
                  <option value="todos">Todos (equipe e famílias)</option>
                  <option value="equipe">Só equipe (gestor e profissionais)</option>
                  <option value="familias">Só famílias (responsáveis)</option>
                </select>
              </div>
              <div class="linha gap-3" style="margin-top:16px;">
                <button type="submit" class="botao botao-primario">Publicar</button>
                <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
              </div>
            </form>
          </div>
        </div>`);
        document.body.appendChild(modal);
        modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
        document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
        document.getElementById("form-novo-aviso").addEventListener("submit", async (e) => {
            e.preventDefault();
            await Api.post("/comunicacao/avisos", {
                titulo: document.getElementById("av-titulo").value.trim(),
                conteudo: document.getElementById("av-conteudo").value.trim(),
                publico: document.getElementById("av-publico").value,
            });
            Toast.sucesso("Aviso publicado!");
            modal.remove();
            despachar();
        });
    });
}


