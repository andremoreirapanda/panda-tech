// ============================================================================
// views/pandoo.js — Pandoo (25/09/2026): lista de jogos da clínica e editor.
//
// Só para gestor e profissional com o módulo "pandoo" liberado (plano ou
// extra da clínica). Jogar um jogo numa missão NÃO depende do módulo.
// O editor monta o conteúdo no formato único v1 (pandoo_core.js); quem valida
// de verdade é o backend (pandoo_service.py).
// ============================================================================

function _basePandoo() {
    return Sessao.usuario && Sessao.usuario.papel === "gestor" ? "gestor" : "profissional";
}

function _pandooLiberado() {
    const org = (Sessao.usuario && Sessao.usuario.organizacao) || {};
    return (org.modulos_habilitados || []).includes("pandoo");
}

function _marcaPandoo() {
    return `<span class="pd-marca-ed">${PANDA_SVG_PANDOO}<span><span class="o1">Pan</span><span class="o2">doo</span></span></span>`;
}

async function viewPandoo(app) {
    const base = _basePandoo();
    const rota = `#/${base}/pandoo`;
    if (!_pandooLiberado()) {
        app.innerHTML = renderShellSidebar(rota, "Pandoo", `
          <div class="cartao" style="max-width:640px; text-align:center;">
            ${_marcaPandoo()}
            <p style="margin-top:12px;">O Pandoo ainda não está liberado para a sua clínica. Fale com a Panda Tech para ativar.</p>
          </div>`);
        anexarEventosShell();
        return;
    }
    const jogos = await Api.get("/pandoo/jogos");
    const icone = (modelo) => (jogoRegistrado(modelo) || {}).icone || "🎮";
    const conteudo = jogos.length ? `
      <p class="texto-sm texto-suave" style="margin-bottom:16px;">Jogos criados pela equipe. Eles também aparecem na Biblioteca e podem ser colocados nas missões.</p>
      <div class="pd-lista-jogos">
        ${jogos.map(j => `
          <a class="pd-cartao-jogo" href="#/${base}/pandoo/${Number(j.id)}">
            <span class="pd-cartao-jogo-ico">${icone(j.modelo)}</span>
            <span class="pd-cartao-jogo-titulo">${escapeHtml(j.titulo)}</span>
            <span class="texto-xs texto-suave">${Number(j.total_itens) || 0} figuras${j.atualizado_em ? ` · atualizado em ${escapeHtml(formatarData(j.atualizado_em))}` : ""}</span>
          </a>`).join("")}
      </div>` : `
      <div class="estado-vazio">
        <div class="emoji">${PANDA_SVG_PANDOO}</div>
        <h3>Crie o primeiro jogo da clínica</h3>
        <p class="texto-suave">Monte uma roleta com as figuras e a voz de vocês e coloque nas missões das crianças.</p>
      </div>`;
    app.innerHTML = renderShellSidebar(rota, "Pandoo", conteudo,
        `<a class="botao botao-primario botao-sm" href="#/${base}/pandoo/novo">+ Novo jogo</a>`);
    anexarEventosShell();
}

// ---------------------------------------------------------------- Editor

const MODELOS_PANDOO_EDITOR = [
    { codigo: "roleta", nome: "Roleta", icone: "🎡", pronto: true },
    { codigo: "quiz", nome: "Quiz", icone: "❓", pronto: false },
    { codigo: "memoria", nome: "Memória", icone: "🧠", pronto: false },
    { codigo: "associacao", nome: "Associação", icone: "🔗", pronto: false },
    { codigo: "flashcards", nome: "Flashcards", icone: "🃏", pronto: false },
];
const CENARIOS_PANDOO_EDITOR = [
    { codigo: "bambu", nome: "🎋 Bambuzal" },
    { codigo: "mar", nome: "🐠 Fundo do mar" },
    { codigo: "espaco", nome: "🚀 Espaço" },
    { codigo: "clinica", nome: "🖼️ Imagem da clínica" },
];

async function viewPandooEditor(app, params) {
    const base = _basePandoo();
    const rotaLista = `#/${base}/pandoo`;
    if (!_pandooLiberado()) { location.hash = rotaLista; return; }
    const id = params && params.id ? Number(params.id) : null;

    let est;
    let categorias = [];
    let org = {};
    try {
        const [jogo, cats, organizacao] = await Promise.all([
            id ? Api.get(`/pandoo/jogos/${id}`) : Promise.resolve(null),
            Api.get("/biblioteca/categorias").catch(() => []),
            Api.get("/pessoas/organizacao").catch(() => ({})),
        ]);
        categorias = cats || [];
        org = organizacao || {};
        if (jogo && jogo.pode_editar === false) {
            Toast.erro("Só quem criou o jogo (ou o gestor) pode editá-lo.");
            location.hash = rotaLista;
            return;
        }
        est = jogo ? {
            id: jogo.id, titulo: jogo.titulo || "", descricao: jogo.descricao || "", categoria_id: jogo.categoria_id || null,
            modelo: jogo.modelo || "roleta", conteudo: jogo.conteudo, regras: { ...REGRAS_PADRAO_PANDOO.roleta, ...(jogo.regras || {}) },
            cenario: jogo.cenario || null,
        } : {
            id: null, titulo: "", descricao: "", categoria_id: null, modelo: "roleta",
            conteudo: conteudoVazioPandoo(), regras: { ...REGRAS_PADRAO_PANDOO.roleta }, cenario: null,
        };
    } catch (err) {
        Toast.erro(err.message);
        location.hash = rotaLista;
        return;
    }
    const nomePadrao = (CENARIOS_PANDOO_EDITOR.find(c => c.codigo === (org.pandoo_cenario_padrao || "bambu")) || CENARIOS_PANDOO_EDITOR[0]).nome;
    const pastas = categorias.filter(c => !c.pasta_pai_id);
    const opcoesPasta = pastas.map(p => [
        `<option value="${Number(p.id)}" ${Number(est.categoria_id) === Number(p.id) ? "selected" : ""}>${escapeHtml(p.nome)}</option>`,
        ...categorias.filter(s => Number(s.pasta_pai_id) === Number(p.id)).map(s =>
            `<option value="${Number(s.id)}" ${Number(est.categoria_id) === Number(s.id) ? "selected" : ""}>&nbsp;&nbsp;↳ ${escapeHtml(s.nome)}</option>`),
    ].join("")).join("");

    const conteudoHtml = `
    <div class="pd-ed">
      <div class="pd-ed-topo">
        ${_marcaPandoo()}
        <input type="text" id="pd-titulo" maxlength="120" placeholder="Nome do jogo (ex.: Roleta do /R/)" value="${escapeHtml(est.titulo)}" />
        <button type="button" class="botao botao-secundario" id="pd-previa">▶ Pré-visualizar</button>
        <button type="button" class="botao botao-primario" id="pd-salvar">Salvar jogo</button>
      </div>
      <div class="pd-ed-grade">
        <div class="cartao">
          <h3>1. Escolha o modelo</h3>
          <div class="pd-modelos">
            ${MODELOS_PANDOO_EDITOR.map(m => `<div class="pd-modelo ${m.codigo === est.modelo ? "ativo" : ""} ${m.pronto ? "" : "breve"}"><span class="ico">${m.icone}</span>${m.nome}</div>`).join("")}
          </div>
          <h3 style="margin-top:18px;">2. Figuras da roleta</h3>
          <p class="texto-xs texto-suave" style="margin-bottom:10px;">De 2 a 24 figuras. Para cada uma: a imagem, a palavra (opcional) e, se quiser, a sua voz dizendo a palavra.</p>
          <div id="pd-itens" class="pd-itens"></div>
          <button type="button" class="botao botao-secundario" id="pd-add" style="width:100%; margin-top:10px;">+ Adicionar figura</button>
          ${renderOrientacaoEnvio("figura")}
          ${renderOrientacaoEnvio("voz")}
          <input type="file" id="pd-arq-img" accept="image/*" style="display:none;" />
          <input type="file" id="pd-arq-audio" accept="audio/*" style="display:none;" />
        </div>
        <div class="coluna gap-3">
          <div class="cartao">
            <h3>3. Regras</h3>
            <p class="texto-sm" style="font-weight:600; margin:8px 0 4px;">Quando o jogo termina</p>
            <label class="pd-radio"><input type="radio" name="pd-fim" value="todas" ${est.regras.fim !== "giros" ? "checked" : ""} /> Quando sair todas as figuras (sem repetir)</label>
            <label class="pd-radio"><input type="radio" name="pd-fim" value="giros" ${est.regras.fim === "giros" ? "checked" : ""} /> Depois de <input type="number" id="pd-giros" min="1" max="100" value="${Number(est.regras.giros) || 10}" /> giros</label>
            <p class="texto-xs texto-suave">…ou antes, no botão "Finalizar jogo".</p>
            <label class="pd-check"><input type="checkbox" id="pd-palavra" ${est.regras.mostrar_palavra ? "checked" : ""} /> Mostrar a palavra embaixo da figura</label>
            <label class="pd-check"><input type="checkbox" id="pd-som-regra" ${est.regras.som ? "checked" : ""} /> Som de roleta e comemoração</label>
            <label class="pd-check"><input type="checkbox" id="pd-voz-regra" ${est.regras.voz ? "checked" : ""} /> Ler a palavra em voz alta quando a figura aparecer</label>
          </div>
          <div class="cartao">
            <h3>Cenário</h3>
            <select id="pd-cenario" style="width:100%; margin-top:8px;">
              <option value="">Padrão da clínica (${escapeHtml(nomePadrao)})</option>
              ${CENARIOS_PANDOO_EDITOR.map(c => `<option value="${c.codigo}" ${est.cenario === c.codigo ? "selected" : ""}>${c.nome}</option>`).join("")}
            </select>
            <p class="texto-xs texto-suave" style="margin-top:6px;">A imagem da clínica e o cenário padrão ficam em Configurações.</p>
          </div>
          <div class="cartao">
            <h3>Pasta da Biblioteca</h3>
            <select id="pd-pasta" style="width:100%; margin-top:8px;">
              <option value="">Sem pasta</option>${opcoesPasta}
            </select>
            <div class="campo" style="margin-top:12px;"><label>Descrição (opcional)</label>
              <textarea id="pd-descricao" rows="2" maxlength="500">${escapeHtml(est.descricao)}</textarea></div>
          </div>
        </div>
      </div>
    </div>`;
    app.innerHTML = renderShellSidebar(rotaLista, id ? "Editar jogo" : "Novo jogo", conteudoHtml,
        `<a class="botao botao-secundario botao-sm" href="${rotaLista}">← Jogos</a>`);
    anexarEventosShell();

    const lista = document.getElementById("pd-itens");
    let alvoArquivo = null;   // id do item que vai receber a imagem/áudio escolhido
    let gravacao = null;      // {itemId, recorder, stream, inicio, relogio, limite}

    function itemPorId(itemId) { return est.conteudo.itens.find(i => i.id === itemId); }

    function renderVoz(item) {
        if (gravacao && gravacao.itemId === item.id) {
            return `<button type="button" class="botao botao-perigo botao-sm" data-acao="parar">⏹ Parar (<span class="pd-relogio">0:00</span>)</button>`;
        }
        if (item.pergunta.audio) {
            return `<button type="button" class="botao botao-secundario botao-sm" data-acao="ouvir">▶ Ouvir</button>
                    <button type="button" class="botao botao-texto botao-sm" data-acao="apagar-voz">🗑 Apagar voz</button>`;
        }
        return `<button type="button" class="botao botao-secundario botao-sm" data-acao="gravar" ${gravacao ? "disabled" : ""}>🎙️ Gravar</button>
                <button type="button" class="botao botao-texto botao-sm" data-acao="enviar-audio">📎 Enviar áudio</button>`;
    }

    function renderItens() {
        const itens = est.conteudo.itens;
        lista.innerHTML = itens.map((item, i) => `
          <div class="pd-item" data-id="${escapeHtml(item.id)}">
            <span class="pd-item-n">${i + 1}</span>
            <button type="button" class="pd-item-img" data-acao="imagem" title="Escolher imagem">${_imgItemPandoo(item) || "🖼️<small>Escolher imagem</small>"}</button>
            <div class="pd-item-meio">
              <input type="text" class="pd-item-palavra" maxlength="80" placeholder="Palavra (ex.: Rato)" value="${escapeHtml(item.pergunta.texto || "")}" />
              <div class="pd-item-voz">${renderVoz(item)}</div>
            </div>
            <div class="pd-item-ordem">
              <button type="button" data-acao="subir" title="Subir" ${i === 0 ? "disabled" : ""}>↑</button>
              <button type="button" data-acao="descer" title="Descer" ${i === itens.length - 1 ? "disabled" : ""}>↓</button>
              <button type="button" data-acao="remover" title="Remover" ${itens.length <= PANDOO_LIMITES.minItens ? "disabled" : ""}>✕</button>
            </div>
          </div>`).join("");
        document.getElementById("pd-add").disabled = itens.length >= PANDOO_LIMITES.maxItens;
    }
    renderItens();

    lista.addEventListener("input", (e) => {
        if (!e.target.classList.contains("pd-item-palavra")) return;
        const item = itemPorId(e.target.closest(".pd-item").dataset.id);
        if (item) item.pergunta.texto = e.target.value;
    });

    lista.addEventListener("click", async (e) => {
        const botao = e.target.closest("[data-acao]");
        if (!botao) return;
        const linha = botao.closest(".pd-item");
        const item = itemPorId(linha.dataset.id);
        const itens = est.conteudo.itens;
        const idx = itens.indexOf(item);
        switch (botao.dataset.acao) {
            case "imagem": alvoArquivo = item.id; document.getElementById("pd-arq-img").click(); break;
            case "enviar-audio": alvoArquivo = item.id; document.getElementById("pd-arq-audio").click(); break;
            case "subir": if (idx > 0) { [itens[idx - 1], itens[idx]] = [itens[idx], itens[idx - 1]]; renderItens(); } break;
            case "descer": if (idx < itens.length - 1) { [itens[idx + 1], itens[idx]] = [itens[idx], itens[idx + 1]]; renderItens(); } break;
            case "remover": if (itens.length > PANDOO_LIMITES.minItens) { itens.splice(idx, 1); renderItens(); } break;
            case "ouvir": new Audio(`data:${mimeDoAudio(item.pergunta.audio)};base64,${item.pergunta.audio}`).play().catch(() => Toast.erro("Não foi possível tocar esse áudio.")); break;
            case "apagar-voz": item.pergunta.audio = null; renderItens(); break;
            case "gravar": await iniciarGravacao(item); break;
            case "parar": pararGravacao(); break;
        }
    });

    document.getElementById("pd-add").addEventListener("click", () => {
        if (est.conteudo.itens.length >= PANDOO_LIMITES.maxItens) return;
        est.conteudo.itens.push(novoItemPandoo());
        renderItens();
    });

    document.getElementById("pd-arq-img").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        e.target.value = "";
        const item = itemPorId(alvoArquivo);
        if (!file || !item) return;
        try {
            const r = await prepararImagemParaEnvio(file, "figura");
            if (r.aviso) Toast.info(r.aviso);
            item.pergunta.imagem = r.base64;
            renderItens();
        } catch (err) { Toast.erro(err.message); }
    });

    document.getElementById("pd-arq-audio").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        e.target.value = "";
        const item = itemPorId(alvoArquivo);
        if (!file || !item) return;
        try {
            const r = await prepararArquivoParaEnvio(file, "voz");
            item.pergunta.audio = r.base64;
            renderItens();
        } catch (err) { Toast.erro(err.message); }
    });

    async function iniciarGravacao(item) {
        if (gravacao) return;
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === "undefined") {
            Toast.erro("Seu navegador não permite gravar aqui — envie um arquivo de áudio.");
            return;
        }
        let stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (err) {
            Toast.erro(err && err.name === "NotAllowedError"
                ? "Sem permissão para usar o microfone. Libere o microfone no navegador ou envie um arquivo."
                : "Não foi possível usar o microfone — envie um arquivo de áudio.");
            return;
        }
        const tipo = MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
        const recorder = tipo ? new MediaRecorder(stream, { mimeType: tipo }) : new MediaRecorder(stream);
        const partes = [];
        recorder.ondataavailable = (ev) => { if (ev.data && ev.data.size) partes.push(ev.data); };
        recorder.onstop = async () => {
            stream.getTracks().forEach(t => t.stop());
            clearInterval(gravacao.relogio);
            clearTimeout(gravacao.limite);
            gravacao = null;
            const blob = new Blob(partes, { type: recorder.mimeType || "audio/webm" });
            if (blob.size > 600 * 1024) {
                Toast.erro("A gravação passou de 600 KB — grave uma frase mais curta.");
            } else if (blob.size) {
                item.pergunta.audio = await lerArquivoBase64(blob);
            }
            renderItens();
        };
        gravacao = { itemId: item.id, recorder, stream, inicio: Date.now() };
        recorder.start();
        renderItens();
        gravacao.relogio = setInterval(() => {
            const s = Math.floor((Date.now() - gravacao.inicio) / 1000);
            const el = lista.querySelector(".pd-relogio");
            if (el) el.textContent = `0:${String(s).padStart(2, "0")}`;
        }, 250);
        // Máximo de 30 segundos (orientação do campo de voz).
        gravacao.limite = setTimeout(pararGravacao, 30000);
    }

    function pararGravacao() {
        if (gravacao && gravacao.recorder.state !== "inactive") gravacao.recorder.stop();
    }

    function lerFormulario() {
        est.titulo = document.getElementById("pd-titulo").value.trim();
        est.descricao = document.getElementById("pd-descricao").value.trim();
        est.categoria_id = document.getElementById("pd-pasta").value ? Number(document.getElementById("pd-pasta").value) : null;
        est.cenario = document.getElementById("pd-cenario").value || null;
        const fim = document.querySelector('input[name="pd-fim"]:checked');
        est.regras = {
            fim: fim ? fim.value : "todas",
            giros: Math.max(1, Math.min(100, Number(document.getElementById("pd-giros").value) || 10)),
            mostrar_palavra: document.getElementById("pd-palavra").checked,
            som: document.getElementById("pd-som-regra").checked,
            voz: document.getElementById("pd-voz-regra").checked,
        };
    }

    document.getElementById("pd-previa").addEventListener("click", () => {
        pararGravacao();
        lerFormulario();
        const problemas = problemasDoConteudo(est.modelo, est.conteudo);
        if (problemas.length) { Toast.erro(problemas[0]); return; }
        abrirPalcoPandoo({
            jogo: { ...est, id: est.id || 0, cenario_efetivo: cenarioEfetivoPandoo(est.cenario, org) },
            modo: "previa",
        });
    });

    document.getElementById("pd-salvar").addEventListener("click", async (e) => {
        pararGravacao();
        lerFormulario();
        if (!est.titulo) { Toast.erro("Dê um nome ao jogo."); return; }
        const problemas = problemasDoConteudo(est.modelo, est.conteudo);
        if (problemas.length) { Toast.erro(problemas[0]); return; }
        const botao = e.currentTarget;
        botao.disabled = true;
        botao.textContent = "Salvando…";
        const corpo = {
            titulo: est.titulo, descricao: est.descricao, categoria_id: est.categoria_id, modelo: est.modelo,
            conteudo: est.conteudo, regras: est.regras, cenario: est.cenario,
        };
        try {
            if (est.id) await Api.put(`/pandoo/jogos/${est.id}`, corpo);
            else await Api.post("/pandoo/jogos", corpo);
            Toast.sucesso("Jogo salvo! Ele já aparece na Biblioteca.");
            location.hash = rotaLista;
        } catch (err) {
            Toast.erro(err.message);
            botao.disabled = false;
            botao.textContent = "Salvar jogo";
        }
    });
}
