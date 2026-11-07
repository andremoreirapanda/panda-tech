// ============================================================================
// Pandoo (05/11/2026) — "Toque só no alvo".
// A criança toca só na figura-alvo e segura o toque nas outras. Três fases, uma
// evolução da outra: 1) uma figura de cada vez no meio; 2) figuras saindo das
// tocas; 3) figuras passando pela tela. Regras puras em ../alvo_core.js.
// Cada figura que aparece vira um detalhe (alvo, tocou, fase, tempo); figura
// que só passou é registrada em silêncio (sem som, sem bronca).
// ============================================================================

registrarJogo("alvo", {
    nome: "Toque só no alvo",
    icone: "🎯",
    rotuloRodada: ["figura", "figuras"],
    avisoSemRodada: AVISO_SEM_TOQUE_ALVO,
    requisitos: (c, regras) => problemasDoConteudo("alvo", c, regras),
    houveJogada: houveToqueAlvo,
    resumo(detalhes, conteudo, regras) {
        const m = medidasAlvo(detalhes);
        const t = textoResumoAlvo(m);
        const alvo = conteudo.itens.find(i => i.id === regras.alvo_item_id);
        return `
          ${t.pegou ? `<p class="pda-resumo">Você pegou <strong>${t.pegou}</strong> ${_imgItemPandoo(alvo, "pda-resumo-fig")}</p>` : ""}
          ${t.segurou ? `<p>E segurou todas as pegadinhas! 💪</p>` : ""}
          <p class="pd-dica">Chegou até a fase ${m.fase_alcancada}: ${escapeHtml(NOMES_FASES_ALVO[m.fase_alcancada] || "")}</p>`;
    },
    iniciar(palco, conteudo, regras) {
        const itens = conteudo.itens;
        const alvo = itens.find(i => i.id === regras.alvo_item_id) || itens[0];
        const velocidadeBase = regras.velocidade in TEMPOS_ALVO[1] ? regras.velocidade : "media";
        const poucoMovimento = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const timers = new Set();
        const animacoes = new Set();
        let estrelas = 0;

        const esperar = (fn, ms) => {
            const t = setTimeout(() => { timers.delete(t); if (!palco.encerrado) fn(); }, ms);
            timers.add(t);
        };
        palco.aoEncerrar(() => {
            timers.forEach(clearTimeout);
            timers.clear();
            animacoes.forEach(a => { try { a.cancel(); } catch (e) { /* já acabou */ } });
            animacoes.clear();
        });
        const falarComando = () => PandooSom.falarComando(String(regras.frase_inicio || "Toque só no"), alvo,
            { fraseAudio: regras.frase_audio || null });
        const frase = escapeHtml(fraseComandoAlvo(regras, alvo).replace(/!$/, ""));

        // --- abertura: o alvo grande no meio e a voz dizendo o comando -------
        palco.area.innerHTML = `
          <div class="pda-abertura">
            ${_imgItemPandoo(alvo, "pda-abertura-fig")}
            <div class="pda-abertura-frase">${frase}!</div>
            <button type="button" class="pd-b-ok pda-comecar">Começar</button>
          </div>`;
        palco.atualizarPlacar({ progresso: "🎯", estrelas: 0 });
        falarComando();
        palco.area.querySelector(".pda-comecar").addEventListener("click", () => fase(Number(regras.fase_inicio) || 1));

        // --- uma fase --------------------------------------------------------
        function fase(numero) {
            if (palco.encerrado) return;
            const velocidade = numero === 3 && poucoMovimento ? "lenta" : velocidadeBase;
            const tempo = TEMPOS_ALVO[numero][velocidade];
            const fila = sortearFigurasAlvo(itens, alvo.id, Number(regras.figuras_por_fase) || 20);
            const detalhesFase = [];
            let lancadas = 0;
            let terminadas = 0;

            palco.area.innerHTML = `
              <button type="button" class="pda-modelo" title="Ouvir de novo">${frase} ${_imgItemPandoo(alvo, "pda-modelo-fig")} 🔊</button>
              <div class="pda-barra"><i></i></div>
              <div class="pda-campo fase${numero}">
                ${numero === 2 ? Array.from({ length: 6 }, (_, i) => `<div class="pda-toca" data-toca="${i}"></div>`).join("") : ""}
              </div>
              <div class="pda-aviso">Fase ${numero}! ${escapeHtml(NOMES_FASES_ALVO[numero])}</div>`;
            const campo = palco.area.querySelector(".pda-campo");
            const barra = palco.area.querySelector(".pda-barra i");
            const aviso = palco.area.querySelector(".pda-aviso");
            palco.area.querySelector(".pda-modelo").addEventListener("click", falarComando);
            const placar = () => palco.atualizarPlacar({ progresso: `Fase ${numero} · ${terminadas}/${fila.length}`, estrelas });
            placar();
            falarComando();

            // Uma figura na tela: o 1º toque conta; se sair sem toque, anota em silêncio.
            function mostrar(item, colocar) {
                const el = document.createElement("button");
                el.type = "button";
                el.className = "pda-fig";
                el.setAttribute("aria-label", (item.pergunta && item.pergunta.texto) || "Figura");
                el.innerHTML = _imgItemPandoo(item);
                let decidida = false;
                let inicio = null;
                const sair = colocar(el, (atrasoMs = 0) => {
                    inicio = performance.now() + atrasoMs;
                }, () => {
                    if (!decidida) {
                        decidida = true;
                        const d = detalheAlvo(item, alvo.id, false, numero);
                        detalhesFase.push(d);
                        palco.registrar(item, d.resultado, { silencioso: true, extra: d });
                    }
                    el.remove();
                    terminou();
                });
                el.addEventListener("pointerdown", (ev) => {
                    ev.preventDefault();
                    if (decidida || palco.encerrado || inicio === null) return;
                    decidida = true;
                    const d = detalheAlvo(item, alvo.id, true, numero, Math.max(0, performance.now() - inicio));
                    detalhesFase.push(d);
                    if (d.alvo) {
                        estrelas += 1;
                        el.classList.add("certa");
                        palco.registrar(item, "conseguiu", { extra: d });
                    } else {
                        // 07/11/2026: X vermelho em cima da figura, além do som.
                        el.classList.add("errada");
                        el.insertAdjacentHTML("beforeend", `<span class="pda-x" aria-hidden="true"></span>`);
                        palco.registrar(item, "treinar", { comemorar: false, extra: d });
                    }
                    placar();
                    sair(d.alvo ? 350 : 800);
                });
            }

            function terminou() {
                terminadas += 1;
                barra.style.width = `${Math.round(100 * terminadas / fila.length)}%`;
                placar();
                if (terminadas < fila.length) return;
                const proxima = proximaFaseAlvo(regras, numero, detalhesFase);
                esperar(() => (proxima ? fase(proxima) : palco.finalizar({ encerradoAntes: false })), 700);
            }

            // Fase 1: uma figura de cada vez, no meio.
            function colocarNoMeio(el, aoAparecer, aoSair) {
                campo.appendChild(el);
                aoAparecer();
                let saiu = false;
                const fim = () => { if (saiu) return; saiu = true; aoSair(); };
                esperar(fim, tempo);
                return (ms) => esperar(fim, ms);
            }

            // Fase 2: sai de uma toca livre e volta a se esconder.
            function colocarNaToca(el, aoAparecer, aoSair) {
                const livres = [...campo.querySelectorAll(".pda-toca")].filter(t => !t.firstChild);
                const toca = livres[Math.floor(Math.random() * livres.length)];
                toca.appendChild(el);
                aoAparecer(atrasoVisivelAlvo(2, tempo, 0, 0));
                let saiu = false;
                const fim = () => { if (saiu) return; saiu = true; aoSair(); };
                esperar(fim, tempo);
                return (ms) => esperar(fim, ms);
            }

            // Fase 3: atravessa a tela da direita para a esquerda, numa de 3 faixas.
            function colocarPassando(el, aoAparecer, aoSair) {
                const faixa = lancadas % 3;
                el.style.top = `${8 + faixa * 31}%`;
                campo.appendChild(el);
                const largura = campo.clientWidth + el.offsetWidth;
                const anim = el.animate([{ transform: "translateX(0)" }, { transform: `translateX(-${largura}px)` }],
                    { duration: tempo, easing: "linear", fill: "forwards" });
                animacoes.add(anim);
                aoAparecer(atrasoVisivelAlvo(3, tempo, el.offsetWidth, campo.clientWidth));
                let saiu = false;
                const fim = () => { if (saiu) return; saiu = true; animacoes.delete(anim); aoSair(); };
                anim.onfinish = fim;
                // A animação domina o transform: o "estouro" e o balanço vão na imagem.
                return (ms) => { anim.pause(); esperar(fim, ms); };
            }

            const colocar = numero === 1 ? colocarNoMeio : numero === 2 ? colocarNaToca : colocarPassando;
            const maxNaTela = numero === 1 ? 1 : numero === 2 ? 2 : 3;
            const intervalo = numero === 1 ? tempo + INTERVALO_FASE1_MS : numero === 2 ? Math.round(tempo * 0.6) : Math.round(tempo / 3);

            function lancar() {
                if (palco.encerrado || lancadas >= fila.length) return;
                const naTela = campo.querySelectorAll(".pda-fig").length;
                if (naTela < maxNaTela) {
                    mostrar(fila[lancadas], colocar);
                    lancadas += 1;
                }
                if (lancadas < fila.length) esperar(lancar, naTela < maxNaTela ? intervalo : 250);
            }
            // Dá tempo de ouvir o comando e ler "Fase N!" antes da 1ª figura.
            esperar(() => { aviso.classList.add("some"); lancar(); }, 2200);
        }
    },
});
