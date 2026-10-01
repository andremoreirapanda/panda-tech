// ============================================================================
// Pandoo fase 2 (01/10/2026) — Memória.
// As cartas ficam viradas para baixo; a criança vira duas por vez procurando
// os pares ("figura + figura igual" ou "figura + palavra"). Errou: as cartas
// balançam, ficam à mostra 1,2 s e viram. ⭐ do par só quando ela lembrou onde
// estava (regra em jogadaMemoria). Regras puras em pandoo_core.js; salvar,
// som, cenário e resumo são do palco.
// ============================================================================

const ESPERA_MEMORIA_MS = 1200;
const ESPERA_MAX_VOZ_MS = 10000;   // o resumo espera a palavra do último par terminar

registrarJogo("memoria", {
    nome: "Memória",
    icone: "🧠",
    rotuloRodada: ["par", "pares"],
    avisoSemRodada: "Você ainda não achou nenhum par. Ache pelo menos um para liberar a missão 🧠",
    requisitos: (c, regras) => problemasDoConteudo("memoria", c, regras),
    iniciar(palco, conteudo, regras) {
        const cartas = montarCartasMemoria(conteudo, regras);
        const porItem = Object.fromEntries(conteudo.itens.map(i => [i.id, i]));
        const totalPares = cartas.length / 2;
        let estado = estadoInicialMemoria();
        let aberta = null;      // id da 1ª carta virada da jogada
        let travado = false;    // duas cartas à mostra esperando virar

        const conteudoCarta = (c) => {
            const item = porItem[c.item_id];
            return (item.pergunta && item.pergunta.texto) || "Figura";
        };
        // Leitor de tela: carta para baixo não anuncia a figura escondida.
        const rotular = (b, estadoCarta) => {
            const c = cartas.find(x => x.id === b.dataset.id);
            b.querySelector(".pdm-frente").setAttribute("aria-hidden", estadoCarta === "baixo" ? "true" : "false");
            b.setAttribute("aria-label", estadoCarta === "baixo" ? "Carta virada para baixo"
                : estadoCarta === "par" ? `Par encontrado: ${conteudoCarta(c)}` : `Carta: ${conteudoCarta(c)}`);
        };
        const frente = (c) => {
            const item = porItem[c.item_id];
            return c.face === "palavra"
                ? `<span class="pdm-palavra">${escapeHtml((item.pergunta && item.pergunta.texto) || "")}</span>`
                : _imgItemPandoo(item, "pdm-img");
        };
        palco.area.innerHTML = `
          <div class="pdm">
            <div class="pdm-mesa">${cartas.map(c => `
              <button type="button" class="pdm-carta" data-id="${c.id}" aria-label="Carta virada para baixo">
                <span class="pdm-face pdm-verso" aria-hidden="true"><b>🐾</b></span>
                <span class="pdm-face pdm-frente" aria-hidden="true">${frente(c)}</span>
              </button>`).join("")}</div>
            <div class="pdm-dica">Vire duas cartas e ache o par 💚</div>
          </div>`;
        const mesa = palco.area.querySelector(".pdm-mesa");
        const dica = palco.area.querySelector(".pdm-dica");
        const botao = (id) => mesa.querySelector(`[data-id="${id}"]`);

        // Espaço de verdade dentro do palco (que rola): posição da mesa no
        // conteúdo do palco, sem depender da rolagem, menos o que vem abaixo
        // dela (dica, "Finalizar jogo" e a margem de baixo) — medido, não chutado.
        function ajustar() {
            if (palco.encerrado || !mesa.isConnected) return;
            const raiz = palco.raiz;
            const estilo = getComputedStyle(raiz);
            const topoNoPalco = mesa.getBoundingClientRect().top - raiz.getBoundingClientRect().top + raiz.scrollTop;
            const fimLink = raiz.querySelector(".pd-fim-link");
            const reserva = 12 + dica.offsetHeight
                + (fimLink ? fimLink.offsetHeight + parseFloat(getComputedStyle(fimLink).marginTop || 0) : 0)
                + parseFloat(estilo.paddingBottom || 0) + 4;
            const altura = Math.max(200, raiz.clientHeight - topoNoPalco - reserva);
            const { colunas, tamanho } = layoutMesaMemoria(cartas.length, palco.area.clientWidth || window.innerWidth, altura);
            mesa.style.setProperty("--pdm-col", colunas);
            mesa.style.setProperty("--pdm-tam", `${tamanho}px`);
        }
        ajustar();
        window.addEventListener("resize", ajustar);
        palco.aoEncerrar(() => window.removeEventListener("resize", ajustar));

        function placar() {
            const estrelas = estado.detalhes.filter(d => d.resultado === "conseguiu").length;
            palco.atualizarPlacar({ progresso: `🧠 ${estado.achados.length} de ${totalPares} pares`, estrelas });
        }
        placar();

        mesa.addEventListener("click", (e) => {
            const b = e.target.closest(".pdm-carta");
            if (!b || travado || palco.encerrado || b.classList.contains("virada") || b.classList.contains("par")) return;
            b.classList.add("virada");
            rotular(b, "cima");
            if (!aberta) { aberta = b.dataset.id; return; }
            const primeira = aberta;
            aberta = null;
            const r = jogadaMemoria(estado, cartas, primeira, b.dataset.id, conteudo);
            estado = r.estado;
            const pares = [botao(primeira), b];
            if (r.acertou) {
                pares.forEach(x => { x.classList.remove("virada"); x.classList.add("par"); rotular(x, "par"); });
                const item = porItem[r.item_id];
                palco.registrar(item, r.resultado, { comemorar: true });
                palco.falarItem(item, { atrasoMs: 800, cortarSom: false });
                dica.textContent = r.resultado === "conseguiu" ? "Isso! Achou o par ⭐" : "Achou! Vamos treinar mais 💪";
                placar();
                if (memoriaTerminou(estado, cartas)) {
                    // Revisão final (01/10/2026): o resumo para o som; se viesse
                    // antes, cortaria a palavra do último par.
                    const limite = Date.now() + ESPERA_MAX_VOZ_MS;
                    const fim = () => {
                        if (palco.encerrado) return;
                        if (PandooSom.falando() && Date.now() < limite) { setTimeout(fim, 250); return; }
                        palco.finalizar({ encerradoAntes: false });
                    };
                    setTimeout(fim, ESPERA_MEMORIA_MS);
                }
                return;
            }
            travado = true;
            pares.forEach(x => x.classList.add("erro"));
            palco.efeito("treinar");
            dica.textContent = "Quase! Lembre onde estavam 💚";
            setTimeout(() => {
                if (palco.encerrado) return;
                pares.forEach(x => { x.classList.remove("virada", "erro"); rotular(x, "baixo"); });
                travado = false;
            }, ESPERA_MEMORIA_MS);
        });
    },
});
