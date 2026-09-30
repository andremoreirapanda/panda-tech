// ============================================================================
// Pandoo fase 2 (30/09/2026) — Quiz.
// "ouvir": a voz diz a palavra e a criança toca na figura certa.
// "ver": aparece a figura e a criança toca na palavra certa.
// Errou: a opção balança, fica apagada e ela tenta outra. A pergunta conta
// "conseguiu" só se acertou de primeira. Regras puras (opções, ordem, fim) em
// pandoo_core.js; salvar, som, cenário e resumo são do palco.
// ============================================================================

registrarJogo("quiz", {
    nome: "Quiz",
    icone: "❓",
    rotuloRodada: ["pergunta", "perguntas"],
    avisoSemRodada: "Você ainda não respondeu nenhuma pergunta. Responda pelo menos uma para liberar a missão ❓",
    requisitos: (c, regras) => problemasDoConteudo("quiz", c, regras),
    iniciar(palco, conteudo, regras) {
        const itens = conteudo.itens;
        const ver = regras.modo === "ver";
        const total = regras.fim === "perguntas" ? regras.perguntas : itens.length;
        let estado = estadoInicialQuiz(conteudo);
        let estrelas = 0;

        function placar() {
            palco.atualizarPlacar({ progresso: `❓ ${estado.rodadas} de ${total}`, estrelas });
        }
        placar();

        function rodada() {
            if (palco.encerrado) return;
            const item = proximaPerguntaQuiz(estado, conteudo);
            const opcoes = opcoesDaPergunta(item, conteudo, regras);
            const pg = item.pergunta || {};
            const temVoz = regras.voz && (pg.texto || pg.audio);
            let tentativas = 0;
            let respondida = false;

            const botaoOpcao = (o, i) => ver
                ? `<button type="button" class="pdq-op" data-i="${i}">${escapeHtml(o.texto)}</button>`
                : `<button type="button" class="pdq-op" data-i="${i}" aria-label="${escapeHtml(o.texto || "Figura")}">${_imgItemPandoo({ pergunta: { imagem: o.imagem, texto: o.texto } })}</button>`;
            palco.area.innerHTML = `
              <div class="pdq">
                <div class="pdq-pergunta">
                  ${ver
                    ? `${_imgItemPandoo(item, "pdq-fig")}<div class="pdq-rotulo">Qual é o nome?</div>`
                    : `<div class="pdq-rotulo">Onde está…</div><div class="pdq-alto">🔊</div>${pg.texto ? `<div class="pdq-palavra">${escapeHtml(pg.texto)}</div>` : ""}`}
                  ${temVoz ? `<button type="button" class="pdq-ouvir">🔊 Ouvir de novo</button>` : ""}
                </div>
                <div class="pdq-opcoes ${ver ? "palavras" : "figs"} n${opcoes.length}">${opcoes.map(botaoOpcao).join("")}</div>
                <div class="pdq-dica">Toque na resposta certa 💚</div>
              </div>`;
            const dica = palco.area.querySelector(".pdq-dica");
            const ouvir = palco.area.querySelector(".pdq-ouvir");
            if (ouvir) ouvir.addEventListener("click", () => palco.repetirItem(item));
            palco.falarItem(item);

            palco.area.querySelectorAll(".pdq-op").forEach(botao => {
                botao.addEventListener("click", () => {
                    if (respondida || palco.encerrado || botao.classList.contains("errada")) return;
                    const opcao = opcoes[Number(botao.dataset.i)];
                    if (!opcao.certa) {
                        tentativas += 1;
                        botao.classList.add("errada");
                        botao.disabled = true;
                        dica.textContent = "Quase! Tente outra 💚";
                        palco.efeito("treinar");
                        return;
                    }
                    respondida = true;
                    botao.classList.add("certa");
                    const resultado = tentativas === 0 ? "conseguiu" : "treinar";
                    palco.registrar(item, resultado, { comemorar: true });
                    estado = registrarRespostaQuiz(estado, item, tentativas, conteudo);
                    if (resultado === "conseguiu") estrelas += 1;
                    placar();
                    dica.textContent = resultado === "conseguiu" ? "Acertou de primeira! ⭐" : "Isso! Conseguiu 💪";
                    setTimeout(() => {
                        if (palco.encerrado) return;
                        if (quizTerminou(estado, regras, conteudo)) palco.finalizar({ encerradoAntes: false });
                        else rodada();
                    }, 1500);
                });
            });
        }
        rodada();
    },
});
