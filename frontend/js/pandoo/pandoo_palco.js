// ============================================================================
// Pandoo (25/09/2026) — palco comum dos jogos (tela cheia).
//
// Todo jogo roda aqui dentro: cenário animado, marca, placar, som, botão
// "Finalizar jogo" e o resumo com troféu. O jogo (ex.: jogos/roleta.js) só
// recebe a `area` e chama palco.registrar(...) / palco.finalizar(...).
// Modo "previa" nunca salva; modo "missao" salva em /pandoo/resultados — se o
// envio falhar, o resumo mostra o erro e "Tentar de novo" (a criança nunca
// fica presa, e a missão só libera depois que salvar).
// ============================================================================

const PANDA_SVG_PANDOO = `<svg class="pd-panda" viewBox="0 0 64 64" aria-hidden="true"><circle cx="14" cy="14" r="10" fill="#2B2640"/><circle cx="50" cy="14" r="10" fill="#2B2640"/><circle cx="32" cy="34" r="26" fill="#fff" stroke="#2B2640" stroke-width="3"/><ellipse cx="22" cy="32" rx="7" ry="9" fill="#2B2640" transform="rotate(-20 22 32)"/><ellipse cx="42" cy="32" rx="7" ry="9" fill="#2B2640" transform="rotate(20 42 32)"/><circle cx="23" cy="31" r="2.5" fill="#fff"/><circle cx="41" cy="31" r="2.5" fill="#fff"/><ellipse cx="32" cy="43" rx="4" ry="3" fill="#2B2640"/><circle cx="17" cy="45" r="4" fill="#FF5C8A" opacity=".5"/><circle cx="47" cy="45" r="4" fill="#FF5C8A" opacity=".5"/></svg>`;

function _imgItemPandoo(item, classe = "") {
    const img = item && item.pergunta && item.pergunta.imagem;
    const b64 = typeof base64Seguro === "function" ? base64Seguro(img) : img;
    return b64 ? `<img class="${classe}" src="data:${mimeDaImagem(b64)};base64,${b64}" alt="${escapeHtml((item.pergunta && item.pergunta.texto) || "Figura")}" />` : "";
}

function abrirPalcoPandoo({ jogo, modo = "previa", contexto = null, aoFechar = () => {} }) {
    const def = jogoRegistrado(jogo && jogo.modelo);
    if (!def) { Toast.erro("Esse modelo de jogo ainda não está disponível."); return; }
    const conteudo = jogo.conteudo || { versao: 1, itens: [] };
    const regras = { ...(REGRAS_PADRAO_PANDOO[jogo.modelo] || {}), ...(jogo.regras || {}) };
    const iniciadoEm = new Date().toISOString();
    const detalhes = [];
    let finalizado = false;
    PandooSom.ligado = true;

    const raiz = document.createElement("div");
    raiz.className = "pandoo-palco";
    raiz.setAttribute("role", "dialog");
    raiz.setAttribute("aria-label", "Jogo Pandoo");
    raiz.innerHTML = `
      <div class="cenario-animado" id="pd-cenario"></div>
      <div class="pd-topo">
        <div class="pd-marca">${PANDA_SVG_PANDOO}<span><span class="o1">Pan</span><span class="o2">doo</span></span></div>
        <div class="pd-placar">
          <span id="pd-progresso"></span><span id="pd-estrelas">⭐ 0</span>
          <button type="button" class="pd-som" id="pd-som" title="Ligar/desligar o som">🔊</button>
        </div>
      </div>
      <div class="pd-titulo">${escapeHtml(jogo.titulo || "")}</div>
      <div class="pd-area" id="pd-area"></div>
      <button type="button" class="pd-fim-link" id="pd-finalizar">Finalizar jogo</button>`;
    document.body.appendChild(raiz);
    document.body.classList.add("pandoo-aberto");
    raiz.dataset.tom = montarCenarioAnimado(raiz.querySelector("#pd-cenario"), cenarioParaPalco(jogo.cenario_efetivo));

    function fechar(resultado) {
        palco.encerrado = true;
        PandooSom.parar();
        raiz.remove();
        document.body.classList.remove("pandoo-aberto");
        aoFechar(resultado);
    }

    const palco = {
        area: raiz.querySelector("#pd-area"),
        raiz,
        // true depois de "Finalizar"/fechar: o jogo não mostra mais nada
        // (ex.: o giro que ainda estava rodando quando a partida acabou).
        encerrado: false,
        regras,
        som: PandooSom,
        falarItem(item) { if (regras.voz) PandooSom.falarItem(item, { voz: true }); },
        repetirItem(item) { if (regras.voz) PandooSom.repetirItem(item); },
        registrar(item, resultado) {
            detalhes.push({ item_id: item.id, texto: (item.pergunta && item.pergunta.texto) || "", resultado });
            PandooSom.parar();
            if (resultado === "conseguiu") {
                if (regras.som) PandooSom.conseguiu();
                confetes();
            } else if (regras.som) {
                PandooSom.treinar();
            }
        },
        atualizarPlacar({ progresso, estrelas }) {
            if (progresso !== undefined) raiz.querySelector("#pd-progresso").textContent = progresso;
            if (estrelas !== undefined) raiz.querySelector("#pd-estrelas").textContent = `⭐ ${estrelas}`;
        },
        efeito(nome, ...args) { if (regras.som && typeof PandooSom[nome] === "function") PandooSom[nome](...args); },
        finalizar({ encerradoAntes = false } = {}) {
            if (finalizado) return;
            finalizado = true;
            palco.encerrado = true;
            mostrarResumo(encerradoAntes);
        },
    };

    raiz.querySelector("#pd-som").addEventListener("click", (e) => {
        e.currentTarget.textContent = PandooSom.alternar() ? "🔊" : "🔇";
    });
    raiz.querySelector("#pd-finalizar").addEventListener("click", () => palco.finalizar({ encerradoAntes: true }));

    function mostrarResumo(encerradoAntes) {
        PandooSom.parar();
        raiz.querySelector("#pd-finalizar").style.display = "none";
        const { conseguiu, treinar } = resumoPartida(detalhes);
        const porId = Object.fromEntries(conteudo.itens.map(i => [i.id, i]));
        const miniaturas = (res) => detalhes.filter(d => d.resultado === res)
            .map(d => _imgItemPandoo(porId[d.item_id])).join("");
        const sobreposto = document.createElement("div");
        sobreposto.className = "pd-sobreposto";
        sobreposto.innerHTML = `
          <div class="pd-cartao pd-resumo">
            <div class="pd-trofeu">🏆</div>
            <h2>Muito bem!</h2>
            <p>Você ganhou <strong>${conseguiu} ⭐</strong> em ${detalhes.length} ${detalhes.length === 1 ? "giro" : "giros"}.</p>
            ${conseguiu ? `<h4>Conseguiu ⭐</h4><div class="pd-lista-figs">${miniaturas("conseguiu")}</div>` : ""}
            ${treinar ? `<h4>Vamos treinar mais 💪</h4><div class="pd-lista-figs">${miniaturas("treinar")}</div>` : ""}
            <p class="pd-dica" id="pd-msg-final">${modo === "missao" ? "Salvando o resultado…" : "Prévia — nada foi salvo."}</p>
            <div id="pd-erro-salvar" class="pd-erro" style="display:none;"></div>
            <div class="pd-acoes"><button type="button" class="pd-b-ok" id="pd-resumo-btn">${modo === "missao" ? "Salvando…" : "Fechar"}</button></div>
            <button type="button" class="pd-link-sair" id="pd-sair-sem-salvar" style="display:none;">Sair sem salvar</button>
          </div>`;
        raiz.appendChild(sobreposto);
        if (regras.som) PandooSom.final();
        confetes();

        const botao = sobreposto.querySelector("#pd-resumo-btn");
        const erroEl = sobreposto.querySelector("#pd-erro-salvar");
        const mensagemFinal = sobreposto.querySelector("#pd-msg-final");
        const sair = sobreposto.querySelector("#pd-sair-sem-salvar");
        if (modo !== "missao") {
            botao.addEventListener("click", () => fechar(null));
            return;
        }
        let resposta = null;
        async function salvar() {
            botao.disabled = true;
            botao.textContent = "Salvando…";
            mensagemFinal.textContent = "Salvando o resultado…";
            erroEl.style.display = "none";
            sair.style.display = "none";
            try {
                resposta = await Api.post("/pandoo/resultados", {
                    paciente_id: contexto.paciente_id, exercicio_id: jogo.id,
                    missao_id: contexto.missao_id, atividade_id: contexto.atividade_id,
                    iniciado_em: iniciadoEm, encerrado_antes: encerradoAntes, detalhes,
                });
                botao.textContent = "Voltar para a missão";
                botao.disabled = false;
                mensagemFinal.textContent = "Prontinho! A equipe da clínica já vai ver como você foi 💚";
            } catch (err) {
                mensagemFinal.textContent = "";
                erroEl.textContent = `Não deu para salvar: ${err.message || "tente de novo"}.`;
                erroEl.style.display = "";
                botao.textContent = "Tentar de novo";
                botao.disabled = false;
                sair.style.display = "";
            }
        }
        botao.addEventListener("click", () => { if (resposta) fechar(resposta); else salvar(); });
        sair.addEventListener("click", () => fechar(null));
        salvar();
    }

    try {
        def.iniciar(palco, conteudo, regras);
    } catch (e) {
        console.error(e);
        Toast.erro("Não foi possível abrir o jogo.");
        fechar(null);
    }
    return palco;
}
