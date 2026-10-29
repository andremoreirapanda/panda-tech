// ============================================================================
// Pandoo (29/10/2026) — Cruzadinha.
// A grade vem pronta do editor (regras.grade). A criança escolhe a palavra
// pela dica (figura) ou tocando num quadradinho e preenche de uma das formas
// liberadas: teclado do celular, banco de letras ou escolhendo a figura.
// Palavra certa sem erro antes = ⭐ "conseguiu"; com erro = "treinar".
// Regras puras em cruzadinha_core.js; salvar, som, cenário e resumo são do palco.
// ============================================================================

const ESPERA_CRUZADINHA_MS = 1200;      // última palavra → resumo
const ESPERA_ERRO_CRUZADINHA_MS = 450;  // palavra errada balança antes de limpar
const PASSO_ESCREVER_MS = 220;          // forma figuras: uma letra por vez
const ESPERA_MAX_VOZ_CRUZADINHA_MS = 10000;
const SENTINELA_CRUZADINHA = " ";
const ROTULO_FORMA_CRUZADINHA = { teclado: "⌨️ Teclado", letras: "🔤 Letras", figuras: "🖼️ Figuras" };

registrarJogo("cruzadinha", {
    nome: "Cruzadinha",
    icone: "🧩",
    rotuloRodada: ["palavra", "palavras"],
    avisoSemRodada: "Você ainda não completou nenhuma palavra. Complete pelo menos uma para liberar a missão 🧩",
    requisitos: (c, regras) => problemasDoConteudo("cruzadinha", c, regras),
    iniciar(palco, conteudo, regras) {
        const grade = regras.grade;
        const palavras = palavrasDaGrade(grade, conteudo.itens);
        const numeros = numerarGrade(grade, conteudo.itens);
        const formas = (regras.formas && regras.formas.length) ? regras.formas : ["teclado"];
        let forma = formas[0];
        let estado = estadoInicialCruzadinha(palavras);
        let escolhida = null, ativa = null, ultimaChave = null, travado = false;
        let banco = [];          // forma letras: as letras à mostra, na ordem sorteada
        let estrelas = 0;

        const porChave = {};
        palavras.forEach(p => p.casas.forEach(cs => { porChave[cs.chave] = cs; }));
        const comecos = {};
        palavras.forEach(p => { comecos[p.casas[0].chave] = numeros[p.item_id]; });
        const palavra = (id) => palavras.find(p => p.item_id === id);
        const letrasDe = (p) => p.casas.filter(cs => !cs.fixa).length;
        const dicasEmOrdem = [...palavras].sort((a, b) => numeros[a.item_id] - numeros[b.item_id] || (a.direcao === "h" ? -1 : 1));

        let casasHtml = "";
        for (let l = 0; l < grade.linhas; l++) {
            for (let c = 0; c < grade.colunas; c++) {
                const ch = `${l},${c}`, cs = porChave[ch];
                if (!cs) casasHtml += `<span class="pdc-vazio"></span>`;
                else if (cs.fixa) casasHtml += `<span class="pdc-casa fixa" aria-hidden="true">${escapeHtml(cs.letra)}</span>`;
                else casasHtml += `<button type="button" class="pdc-casa" data-chave="${ch}">${comecos[ch] ? `<span class="pdc-num">${comecos[ch]}</span>` : ""}<span class="pdc-letra"></span></button>`;
            }
        }
        palco.area.innerHTML = `
          <div class="pdc">
            <div class="pdc-trocar" ${formas.length < 2 ? "hidden" : ""}>${formas.map(f => `<button type="button" data-forma="${f}">${ROTULO_FORMA_CRUZADINHA[f]}</button>`).join("")}</div>
            <div class="pdc-grade-caixa"><div class="pdc-grade" style="--pdc-col:${grade.colunas}">${casasHtml}</div></div>
            <div class="pdc-instrucao"></div>
            <div class="pdc-banco"></div>
            <div class="pdc-dicas"></div>
            <input class="pdc-entrada" type="text" autocomplete="off" autocorrect="off" autocapitalize="characters" spellcheck="false" aria-label="Digite a letra" />
          </div>`;
        const raiz = palco.area.querySelector(".pdc");
        const gradeEl = raiz.querySelector(".pdc-grade");
        const entrada = raiz.querySelector(".pdc-entrada");
        const casaEl = (ch) => gradeEl.querySelector(`[data-chave="${ch}"]`);

        function ajustar() {
            if (palco.encerrado || !gradeEl.isConnected) return;
            const largura = (raiz.querySelector(".pdc-grade-caixa").clientWidth || window.innerWidth) - 8;
            const tam = Math.floor((largura - 5 * (grade.colunas - 1)) / grade.colunas);
            gradeEl.style.setProperty("--pdc-tam", `${Math.max(30, Math.min(64, tam))}px`);
        }
        ajustar();
        window.addEventListener("resize", ajustar);
        // Teclado do celular aberto: a casa da vez continua à vista.
        const mostrarAtiva = () => { const el = ativa && casaEl(ativa); if (el) el.scrollIntoView({ block: "nearest", inline: "nearest" }); };
        if (window.visualViewport) window.visualViewport.addEventListener("resize", mostrarAtiva);
        palco.aoEncerrar(() => {
            window.removeEventListener("resize", ajustar);
            if (window.visualViewport) window.visualViewport.removeEventListener("resize", mostrarAtiva);
        });

        function placar() {
            palco.atualizarPlacar({ progresso: `🧩 ${estado.feitas.length} de ${palavras.length} palavras`, estrelas });
        }

        function desenhar(letras = estado.letras) {
            const pista = regras.primeira_letra || forma === "figuras";
            const daEscolhida = new Set(escolhida ? palavra(escolhida).casas.map(cs => cs.chave) : []);
            const comecoAberto = new Set(palavras.filter(p => !estado.feitas.includes(p.item_id)).map(p => p.casas[0].chave));
            gradeEl.querySelectorAll("button.pdc-casa").forEach(el => {
                const ch = el.dataset.chave, travada = !!estado.travadas[ch];
                el.classList.toggle("sel", daEscolhida.has(ch) && !travada);
                el.classList.toggle("ativa", ch === ativa && forma !== "figuras");
                el.classList.toggle("ok", travada);
                const span = el.querySelector(".pdc-letra");
                const mostrarPista = !letras[ch] && pista && comecoAberto.has(ch);
                span.textContent = letras[ch] || (mostrarPista ? porChave[ch].letra : "");
                span.classList.toggle("pista", mostrarPista);
                el.setAttribute("aria-label", letras[ch] ? `Letra ${letras[ch]}` : "Quadradinho vazio");
            });
            raiz.querySelectorAll(".pdc-trocar button").forEach(b => {
                b.classList.toggle("ativo", b.dataset.forma === forma);
                b.setAttribute("aria-pressed", String(b.dataset.forma === forma));
            });
            const atual = escolhida && palavra(escolhida);
            const fig = atual ? (_imgItemPandoo(atual.item, "pdc-fig-mini") || "") : "";
            raiz.querySelector(".pdc-instrucao").innerHTML = !atual
                ? (forma === "figuras" ? "Toque num ❓ para escolher a figura" : "Toque numa figura para começar")
                : forma === "teclado" ? `Escreva a palavra ${fig}`
                : forma === "letras" ? `Toque nas letras de ${fig}` : "Qual figura cabe aqui?";
            raiz.querySelector(".pdc-banco").innerHTML = forma === "letras" && atual
                ? banco.map((l, i) => `<button type="button" class="pdc-letra-btn" data-i="${i}" aria-label="Letra ${l}">${l}</button>`).join("") : "";
            raiz.querySelector(".pdc-dicas").innerHTML = dicasEmOrdem.map(p => {
                const feita = estado.feitas.includes(p.item_id), escondida = forma === "figuras" && !feita;
                const sentido = p.direcao === "h" ? "deitada" : "em pé";
                return `<button type="button" class="pdc-dica ${p.item_id === escolhida ? "sel" : ""} ${feita ? "feita" : ""}" data-id="${escapeHtml(p.item_id)}"
                    aria-label="Palavra ${numeros[p.item_id]}, ${sentido}, ${letrasDe(p)} letras">
                    <span class="pdc-dica-fig">${escondida ? "❓" : _imgItemPandoo(p.item, "pdc-fig")}</span>
                    <span class="pdc-dica-meta">${numeros[p.item_id]} ${p.direcao === "h" ? "→" : "↓"} · ${letrasDe(p)} letras</span></button>`;
            }).join("");
        }

        // Forma letras: a casa da vez é a primeira da palavra que ainda não tem a letra certa.
        function casaParaLetras(apartir) {
            const p = palavra(escolhida);
            const falta = (cs) => !estado.travadas[cs.chave] && estado.letras[cs.chave] !== cs.letra;
            const pos = p.casas.findIndex(cs => cs.chave === apartir);
            const depois = p.casas.slice(Math.max(pos, 0)).find(falta);
            return (depois || p.casas.find(falta) || {}).chave || null;
        }

        function focar() {
            if (forma !== "teclado" || palco.encerrado) return;
            entrada.value = SENTINELA_CRUZADINHA;
            entrada.focus({ preventScroll: true });
            mostrarAtiva();
        }

        function escolher(id, chave) {
            const p = palavra(id);
            escolhida = id;
            ativa = chave && !estado.travadas[chave] ? chave : primeiraCasaAberta(p, estado);
            if (forma === "letras") { banco = bancoDeLetras(p, estado); ativa = casaParaLetras(ativa); }
            if (forma !== "figuras") palco.falarItem(p.item);
            desenhar();
            focar();
            if (forma === "figuras") abrirEscolha(id);
        }

        function concluir(feitas) {
            if (!feitas.length) return;
            feitas.forEach(f => {
                palco.registrar(palavra(f.item_id).item, f.resultado, { comemorar: true });
                if (f.resultado === "conseguiu") estrelas++;
            });
            if (regras.voz_acertar) PandooSom.falarItem(palavra(feitas[0].item_id).item, { voz: true, atrasoMs: ATRASO_VOZ_MS, cortarSom: false });
            if (feitas.some(f => f.item_id === escolhida)) { escolhida = null; ativa = null; banco = []; entrada.blur(); }
            desenhar();
            feitas.forEach(f => palavra(f.item_id).casas.forEach(cs => {
                const el = casaEl(cs.chave);
                if (el) { el.classList.remove("pdc-pop"); void el.offsetWidth; el.classList.add("pdc-pop"); }
            }));
            placar();
            if (cruzadinhaTerminou(palavras, estado)) {
                travado = true;
                const limite = Date.now() + ESPERA_MAX_VOZ_CRUZADINHA_MS;
                const fim = () => {
                    if (palco.encerrado) return;
                    if (PandooSom.falando() && Date.now() < limite) { setTimeout(fim, 250); return; }
                    palco.finalizar({ encerradoAntes: false });
                };
                setTimeout(fim, ESPERA_CRUZADINHA_MS);
            }
        }

        function balancar(chaves) {
            chaves.forEach(ch => {
                const el = casaEl(ch);
                if (el) { el.classList.remove("pdc-balanca"); void el.offsetWidth; el.classList.add("pdc-balanca"); }
            });
        }

        function colocar(letra) {
            if (!escolhida || !ativa || travado || palco.encerrado) return;
            const r = colocarLetraCruzadinha(palavras, estado, escolhida, ativa, letra);
            if (r.errou) {
                travado = true;
                desenhar({ ...estado.letras, [ativa]: letra });
                balancar(palavra(escolhida).casas.map(cs => cs.chave));
                palco.efeito("treinar");
                setTimeout(() => {
                    if (palco.encerrado) return;
                    estado = r.estado; ativa = r.proxima; travado = false;
                    desenhar(); focar();
                }, ESPERA_ERRO_CRUZADINHA_MS);
                return;
            }
            estado = r.estado;
            if (r.proxima) ativa = r.proxima;
            if (forma === "letras" && escolhida && !estado.feitas.includes(escolhida)) ativa = casaParaLetras(ativa);
            if (r.feitas.length) concluir(r.feitas); else { desenhar(); mostrarAtiva(); }
        }

        function apagar() {
            if (!escolhida || travado) return;
            const r = apagarLetraCruzadinha(palavras, estado, escolhida, ativa);
            estado = r.estado; ativa = r.ativa;
            desenhar();
        }

        function tocarCasa(ch) {
            if (travado || palco.encerrado) return;
            const id = palavraAoTocar(palavras, estado, escolhida, ch, ultimaChave);
            ultimaChave = ch;
            if (!id) {
                const feita = palavras.find(p => p.casas.some(cs => cs.chave === ch));
                if (feita) palco.repetirItem(feita.item);
                return;
            }
            if (id === escolhida && forma !== "figuras") {
                ativa = estado.travadas[ch] ? primeiraCasaAberta(palavra(id), estado) : ch;
                if (forma === "letras") ativa = casaParaLetras(ativa);
                desenhar(); focar();
                return;
            }
            escolher(id, ch);
        }

        // ---- forma figuras ----
        function fecharEscolha() { const s = raiz.querySelector(".pdc-escolha"); if (s) s.remove(); }
        palco.aoEncerrar(fecharEscolha);

        function abrirEscolha(id) {
            fecharEscolha();
            const p = palavra(id);
            const opcoes = opcoesFigurasCruzadinha(id, palavras, estado);
            const caixa = document.createElement("div");
            caixa.className = "pdc-escolha";
            caixa.innerHTML = `
              <div class="pdc-escolha-cartao" role="dialog" aria-label="Escolha a figura">
                <h3>Palavra ${numeros[id]} ${p.direcao === "h" ? "→" : "↓"}</h3>
                <p>${letrasDe(p)} letras. Qual figura cabe?</p>
                <div class="pdc-ops">${opcoes.map((o, i) => `<button type="button" class="pdc-op" data-i="${i}" aria-label="Figura ${i + 1}">${_imgItemPandoo(o, "pdc-fig")}</button>`).join("")}</div>
                <button type="button" class="pdc-outra">Escolher outra palavra</button>
              </div>`;
            raiz.appendChild(caixa);
            caixa.querySelector(".pdc-outra").addEventListener("click", () => { fecharEscolha(); escolhida = null; desenhar(); });
            caixa.querySelectorAll(".pdc-op").forEach(b => b.addEventListener("click", () => {
                if (travado || palco.encerrado || b.classList.contains("errada")) return;
                if (opcoes[Number(b.dataset.i)].id !== id) {
                    estado = registrarErroCruzadinha(estado, id);
                    b.classList.add("errada");
                    palco.efeito("treinar");
                    return;
                }
                fecharEscolha();
                escreverSozinha(id);
            }));
            const primeira = caixa.querySelector(".pdc-op");
            if (primeira) primeira.focus({ preventScroll: true });
        }

        function escreverSozinha(id) {
            travado = true;
            const casas = palavra(id).casas;
            const parcial = { ...estado.letras };
            let k = 0;
            const passo = () => {
                if (palco.encerrado) return;
                if (k >= casas.length) {
                    const r = escreverPalavraCruzadinha(palavras, estado, id);
                    estado = r.estado; travado = false;
                    concluir(r.feitas);
                    return;
                }
                parcial[casas[k].chave] = casas[k].letra;
                k++;
                desenhar(parcial);
                setTimeout(passo, PASSO_ESCREVER_MS);
            };
            passo();
        }

        // ---- eventos ----
        gradeEl.addEventListener("click", (e) => {
            const b = e.target.closest("button.pdc-casa");
            if (b) tocarCasa(b.dataset.chave);
        });
        raiz.querySelector(".pdc-dicas").addEventListener("click", (e) => {
            const b = e.target.closest(".pdc-dica");
            if (!b || travado || palco.encerrado) return;
            const id = b.dataset.id;
            if (estado.feitas.includes(id)) { palco.repetirItem(palavra(id).item); return; }
            ultimaChave = null;
            escolher(id);
        });
        raiz.querySelector(".pdc-banco").addEventListener("click", (e) => {
            const b = e.target.closest(".pdc-letra-btn");
            if (!b || !escolhida || !ativa || travado || palco.encerrado) return;
            const letra = banco[Number(b.dataset.i)];
            if (letra === porChave[ativa].letra) {
                banco.splice(Number(b.dataset.i), 1);
                colocar(letra);
                return;
            }
            estado = registrarErroCruzadinha(estado, escolhida);
            b.classList.remove("pdc-balanca"); void b.offsetWidth; b.classList.add("pdc-balanca");
            palco.efeito("treinar");
        });
        raiz.querySelector(".pdc-trocar").addEventListener("click", (e) => {
            const b = e.target.closest("[data-forma]");
            if (!b || travado || b.dataset.forma === forma) return;
            forma = b.dataset.forma;
            estado = limparSoltasCruzadinha(estado);
            escolhida = null; ativa = null; banco = [];
            fecharEscolha(); entrada.blur();
            desenhar();
        });
        // A letra vem do `input`: o teclado do Android nem sempre manda keydown com ela.
        // Fica sempre um espaço no campo: com ele vazio, o "apagar" do teclado
        // do celular não gera evento nenhum.
        entrada.addEventListener("input", (e) => {
            const letras = letrasDoInput(entrada.value);
            entrada.value = SENTINELA_CRUZADINHA;
            if (forma !== "teclado") return;
            if (String(e.inputType || "").startsWith("delete")) { apagar(); return; }
            letras.forEach(colocar);
        });
        entrada.addEventListener("keydown", (e) => {
            if (e.key === "Backspace") { e.preventDefault(); apagar(); }
        });

        desenhar();
        placar();
    },
});
