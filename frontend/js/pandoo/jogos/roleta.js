// ============================================================================
// Pandoo (25/09/2026) — Roleta de figuras (primeiro jogo).
// A criança gira, a figura sorteada aparece grande (com a palavra e a voz) e o
// adulto marca "Conseguiu ⭐" ou "Vamos treinar mais 💪". Termina quando saem
// todas as figuras ou depois de N giros (regra do profissional) — ou antes,
// em "Finalizar jogo". Regras puras (sorteio, fim) em pandoo_core.js.
// ============================================================================

const CORES_ROLETA_PANDOO = ["#34B36B", "#FF5C8A", "#FFC93C", "#4DB8FF", "#8B5FBF", "#FF8A3D"];

function _svgRoletaPandoo(itens, prefixo) {
    const n = itens.length, passo = 360 / n, raio = 96;
    const tamFig = Math.max(18, Math.min(52, 150 / n + 14));
    let defs = "", h = "";
    itens.forEach((item, i) => {
        const a0 = (i * passo - 90) * Math.PI / 180, a1 = ((i + 1) * passo - 90) * Math.PI / 180;
        const x0 = raio * Math.cos(a0), y0 = raio * Math.sin(a0), x1 = raio * Math.cos(a1), y1 = raio * Math.sin(a1);
        const grande = passo > 180 ? 1 : 0;
        h += `<path d="M0 0 L${x0.toFixed(2)} ${y0.toFixed(2)} A${raio} ${raio} 0 ${grande} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}Z" fill="${CORES_ROLETA_PANDOO[i % CORES_ROLETA_PANDOO.length]}" stroke="#fff" stroke-width="2"/>`;
        const am = ((i + 0.5) * passo - 90) * Math.PI / 180, r = raio * 0.66;
        const cx = r * Math.cos(am), cy = r * Math.sin(am), meio = tamFig / 2;
        const img = item.pergunta && item.pergunta.imagem;
        const b64 = typeof base64Seguro === "function" ? base64Seguro(img) : img;
        if (b64) {
            defs += `<clipPath id="${prefixo}-c${i}"><circle cx="${cx.toFixed(2)}" cy="${cy.toFixed(2)}" r="${meio.toFixed(2)}"/></clipPath>`;
            h += `<circle cx="${cx.toFixed(2)}" cy="${cy.toFixed(2)}" r="${(meio + 2).toFixed(2)}" fill="#fff"/>`;
            h += `<image href="data:${mimeDaImagem(b64)};base64,${b64}" x="${(cx - meio).toFixed(2)}" y="${(cy - meio).toFixed(2)}" width="${tamFig.toFixed(2)}" height="${tamFig.toFixed(2)}" preserveAspectRatio="xMidYMid slice" clip-path="url(#${prefixo}-c${i})" transform="rotate(${((i + 0.5) * passo).toFixed(2)} ${cx.toFixed(2)} ${cy.toFixed(2)})"/>`;
        }
    });
    h += `<circle r="${raio}" fill="none" stroke="#fff" stroke-width="5"/>`;
    return `<svg class="pd-roda" viewBox="-100 -100 200 200" aria-hidden="true"><defs>${defs}</defs>${h}</svg>`;
}

registrarJogo("roleta", {
    nome: "Roleta",
    icone: "🎡",
    requisitos: (c) => problemasDoConteudo("roleta", c),
    iniciar(palco, conteudo, regras) {
        const itens = conteudo.itens;
        let estado = estadoInicialRoleta(conteudo);
        let rotacao = 0;
        let estrelas = 0;
        const prefixo = "pdr" + Date.now().toString(36);

        palco.area.innerHTML = `
          <div class="pd-roda-wrap">
            <div class="pd-ponteiro"></div>
            ${_svgRoletaPandoo(itens, prefixo)}
            <div class="pd-miolo">${PANDA_SVG_PANDOO}</div>
          </div>
          <button type="button" class="pd-girar" id="pd-girar">Girar! 🎉</button>`;
        const roda = palco.area.querySelector(".pd-roda");
        const botao = palco.area.querySelector("#pd-girar");

        function placar() {
            const progresso = regras.fim === "giros"
                ? `🎡 ${estado.rodadas} de ${regras.giros}`
                : `🎡 ${estado.sorteados.length} de ${itens.length}`;
            palco.atualizarPlacar({ progresso, estrelas });
        }
        placar();

        botao.addEventListener("click", () => {
            const item = sortearItemRoleta(estado, conteudo);
            const idx = itens.findIndex(i => i.id === item.id);
            const passo = 360 / itens.length;
            const alvo = 360 - (idx + 0.5) * passo;
            rotacao += 360 * 5 + ((alvo - (rotacao % 360)) + 360) % 360;
            roda.style.transform = `rotate(${rotacao}deg)`;
            botao.disabled = true;
            palco.efeito("giro", 4000);
            setTimeout(() => { if (!palco.encerrado) mostrarFigura(item); }, 4100);
        });

        function mostrarFigura(item) {
            const sobreposto = document.createElement("div");
            sobreposto.className = "pd-sobreposto";
            const palavra = (item.pergunta && item.pergunta.texto) || "";
            sobreposto.innerHTML = `
              <div class="pd-cartao">
                ${_imgItemPandoo(item, "pd-fig")}
                ${regras.mostrar_palavra && palavra ? `<div class="pd-palavra">${escapeHtml(palavra)}</div>` : ""}
                ${regras.voz && (palavra || (item.pergunta && item.pergunta.audio)) ? `<button type="button" class="pd-ouvir">🔊 Ouvir de novo</button>` : ""}
                <div class="pd-acoes">
                  <button type="button" class="pd-b-ok">Conseguiu ⭐</button>
                  <button type="button" class="pd-b-treino">Vamos treinar mais 💪</button>
                  <button type="button" class="pd-b-fim">Finalizar jogo</button>
                </div>
                <p class="pd-dica">Depois que a criança tentar, é só tocar em como foi 💚</p>
              </div>`;
            palco.raiz.appendChild(sobreposto);
            palco.falarItem(item);
            const ouvir = sobreposto.querySelector(".pd-ouvir");
            if (ouvir) ouvir.addEventListener("click", () => palco.repetirItem(item));

            function responder(resultado) {
                palco.registrar(item, resultado);
                estado = registrarRodada(estado, item, resultado, conteudo);
                if (resultado === "conseguiu") estrelas += 1;
                placar();
                sobreposto.remove();
                botao.disabled = false;
                if (partidaTerminou(estado, regras, conteudo)) palco.finalizar({ encerradoAntes: false });
            }
            sobreposto.querySelector(".pd-b-ok").addEventListener("click", () => responder("conseguiu"));
            sobreposto.querySelector(".pd-b-treino").addEventListener("click", () => responder("treinar"));
            sobreposto.querySelector(".pd-b-fim").addEventListener("click", () => {
                sobreposto.remove();
                palco.finalizar({ encerradoAntes: true });
            });
        }
    },
});
