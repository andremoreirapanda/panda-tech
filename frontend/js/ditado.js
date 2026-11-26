// ============================================================================
// ditado.js — Ditado por voz (IA fase 1)
// Botão 🎤 ao lado do rótulo de campos de texto longo: grava no navegador,
// manda o áudio para /api/ia/ditado e insere o texto na posição do cursor.
// Só uma gravação/transcrição por vez na página. O áudio fica só na memória.
// ============================================================================

// ---------- Funções puras (testadas em frontend/tests/ditado.test.js) ----------

// Põe `trecho` entre `inicio` e `fim` (seleção atual), com espaço antes se o
// caractere anterior não for espaço/quebra e espaço depois se o seguinte não
// for espaço nem pontuação. `inicio/fim` devolvidos = seleção do trecho novo.
function inserirNoCursor(valor, inicio, fim, trecho) {
    valor = String(valor || "");
    let a = Math.max(0, Math.min(Number(inicio) || 0, valor.length));
    let b = Math.max(0, Math.min(Number(fim) || 0, valor.length));
    if (b < a) { const t = a; a = b; b = t; }
    const antes = valor.slice(0, a);
    const depois = valor.slice(b);
    const prefixo = antes && !/\s$/.test(antes) ? " " : "";
    const sufixo = depois && !/^[\s.,;:!?)\]]/.test(depois) ? " " : "";
    const novoInicio = antes.length + prefixo.length;
    return {
        valor: antes + prefixo + trecho + sufixo + depois,
        inicio: novoInicio,
        fim: novoInicio + trecho.length,
    };
}

function formatarTempo(seg) {
    const s = Math.max(0, Math.floor(Number(seg) || 0));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function textoMinutos(n) {
    return n === 1 ? "1 minuto" : `${n} minutos`;
}

// A config (e o estado "acabou") valem para uma sessão só: troca de token = recomeça.
function cacheValido(chaveGuardada, tokenAtual) {
    return chaveGuardada === (tokenAtual || "");
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { inserirNoCursor, formatarTempo, textoMinutos, cacheValido };
}

// ---------- Componente (só no navegador) ----------

const Ditado = (typeof window !== "undefined" && typeof document !== "undefined") ? (() => {
    const LIMITE_S = 300;
    const AVISO_S = 270;
    const CHAVE_AVISO = "pandaup_ditado_aviso_visto";
    const TITULO_ACABOU = "Os minutos de ditado deste mês acabaram. Fale com o PandaUp para liberar mais.";
    const AVISO_PRIMEIRO_USO = "O áudio é enviado para transcrição automática e apagado em seguida. Revise o texto antes de salvar.";

    let configPromessa = null;
    let chaveCache = null;
    let config = null;
    let esgotado = false;
    let ativo = null;                 // { ta, fase, stream, recorder, partes, inicio, relogio, limite, avisou }
    const campos = new Set();         // { ta, btn, aviso }
    let observador = null;

    // Config por carregamento da página; null se 403, 503 ou erro (sem aviso).
    function carregarConfig(forcar) {
        const token = (typeof Sessao !== "undefined" && Sessao.token) || "";
        if (!cacheValido(chaveCache, token)) {   // outra sessão (logout/login): não herda nada
            chaveCache = token;
            configPromessa = null; config = null; esgotado = false;
        }
        if (forcar || !configPromessa) {
            const meuToken = token;
            configPromessa = Api.get("/ia/ditado/config").then(c => {
                if (meuToken !== chaveCache) return null;   // resposta de uma sessão que já acabou
                config = c || null;
                esgotado = !!(config && config.disponivel && config.minutos_restantes <= 0);
                return config;
            }).catch(() => { if (meuToken === chaveCache) config = null; return null; });
        }
        return configPromessa;
    }

    function achar(ta) {
        for (const c of campos) if (c.ta === ta) return c;
        return null;
    }

    function limparDesconectados() {
        for (const c of Array.from(campos)) if (!c.ta.isConnected) campos.delete(c);
    }

    function mostrarAviso(c, texto, acao) {
        c.aviso.innerHTML = "";
        if (!texto) { c.aviso.hidden = true; return; }
        const span = document.createElement("span");
        span.textContent = texto;
        c.aviso.appendChild(span);
        if (acao) {
            const b = document.createElement("button");
            b.type = "button";
            b.className = "ditado-tentar";
            b.textContent = acao.rotulo;
            b.addEventListener("click", acao.fazer);
            c.aviso.appendChild(b);
        }
        c.aviso.hidden = false;
    }

    // Só escreve se mudou: cada escrita no DOM dispara os observadores do #app.
    function escrever(el, prop, valor) {
        if (el[prop] !== valor) el[prop] = valor;
    }

    function pintar() {
        limparDesconectados();
        for (const c of campos) {
            const meu = ativo && ativo.ta === c.ta;
            const fase = meu ? ativo.fase : null;
            const rotuloAria = fase === "gravando" ? `Parar gravação, ${formatarTempo(ativo.segundos || 0)}`
                : (fase === "transcrevendo" || fase === "iniciando") ? "Transcrevendo" : "Ditar";
            if (c.btn.getAttribute("aria-label") !== rotuloAria) c.btn.setAttribute("aria-label", rotuloAria);
            c.btn.classList.toggle("gravando", fase === "gravando");
            c.btn.classList.toggle("transcrevendo", fase === "transcrevendo");
            if (fase === "gravando") {
                c.btn.disabled = false;
                escrever(c.btn, "textContent", `⏹ ${formatarTempo(ativo.segundos || 0)} ●`);
                escrever(c.btn, "title", "Parar e transcrever");
            } else if (fase === "transcrevendo" || fase === "iniciando") {
                c.btn.disabled = true;
                escrever(c.btn, "textContent", fase === "iniciando" ? "🎤" : "⏳ Transcrevendo…");
                escrever(c.btn, "title", "");
            } else {
                escrever(c.btn, "textContent", "🎤");
                if (esgotado) {
                    c.btn.disabled = true;
                    escrever(c.btn, "title", TITULO_ACABOU);
                } else {
                    c.btn.disabled = !!ativo;   // outro campo em uso
                    const m = config && typeof config.minutos_restantes === "number" ? config.minutos_restantes : null;
                    escrever(c.btn, "title", m === null ? "Ditar" : `Ditar (${textoMinutos(m)} restantes)`);
                }
            }
        }
    }

    function encerrar() {
        if (ativo) {
            clearInterval(ativo.relogio);
            clearTimeout(ativo.limite);
            if (ativo.stream) ativo.stream.getTracks().forEach(t => t.stop());
        }
        ativo = null;
        if (observador) { observador.disconnect(); observador = null; }
        pintar();
    }

    // Campo saiu da tela (pop-up fechado, troca de rota): para e descarta.
    function vigiar() {
        if (observador) return;
        observador = new MutationObserver(() => {
            if (ativo && !ativo.ta.isConnected) descartar();
        });
        observador.observe(document.body, { childList: true, subtree: true });
    }

    function descartar() {
        if (!ativo) return;
        ativo.descartado = true;
        if (ativo.recorder && ativo.recorder.state !== "inactive") { try { ativo.recorder.stop(); } catch (e) { /* já parou */ } }
        encerrar();
    }

    function avisoPrimeiroUso() {
        try {
            if (localStorage.getItem(CHAVE_AVISO)) return;
            localStorage.setItem(CHAVE_AVISO, "1");
        } catch (e) { /* armazenamento bloqueado: o aviso aparece de novo, sem problema */ }
        Toast.info(AVISO_PRIMEIRO_USO);
    }

    async function iniciar(c) {
        if (ativo || esgotado) return;
        mostrarAviso(c, "");
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === "undefined") {
            mostrarAviso(c, "Seu navegador não permite gravar áudio aqui. Tente o Chrome ou o Safari atualizado.");
            return;
        }
        ativo = { ta: c.ta, fase: "iniciando" };   // bloqueia um segundo clique enquanto pede permissão
        const a = ativo;
        pintar();
        let stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (err) {
            if (ativo === a) { ativo = null; pintar(); }
            mostrarAviso(c, err && err.name === "NotAllowedError"
                ? "Sem permissão para usar o microfone. Toque no cadeado ao lado do endereço (ou nas configurações do navegador do celular) e libere o microfone."
                : "Não foi possível usar o microfone.");
            return;
        }
        if (ativo !== a || a.descartado || !c.ta.isConnected) {
            stream.getTracks().forEach(t => t.stop());
            if (ativo === a) encerrar();
            return;
        }
        avisoPrimeiroUso();
        let tipo, recorder;
        const partes = [];
        const falhouGravar = () => {
            if (a.descartado) return;
            a.descartado = true;   // o "stop" que o navegador dispara depois do erro não envia nada
            if (recorder && recorder.state !== "inactive") { try { recorder.stop(); } catch (e) { /* já parou */ } }
            stream.getTracks().forEach(t => t.stop());
            clearInterval(a.relogio); clearTimeout(a.limite);
            if (ativo === a) encerrar();
            mostrarAviso(c, "Não foi possível gravar.");
        };
        try {
        tipo = MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
        recorder = tipo ? new MediaRecorder(stream, { mimeType: tipo }) : new MediaRecorder(stream);
        } catch (e) { falhouGravar(); return; }
        recorder.onerror = falhouGravar;
        a.fase = "gravando"; a.stream = stream; a.recorder = recorder;
        a.inicio = Date.now(); a.segundos = 0; a.avisou = false;
        recorder.ondataavailable = (ev) => { if (ev.data && ev.data.size) partes.push(ev.data); };
        recorder.onstop = () => {
            stream.getTracks().forEach(t => t.stop());
            clearInterval(a.relogio); clearTimeout(a.limite);
            if (a.descartado) return;
            const segundos = Math.min(LIMITE_S, Math.max(1, Math.round((Date.now() - a.inicio) / 1000)));
            const blob = new Blob(partes, { type: recorder.mimeType || tipo || "audio/webm" });
            if (!c.ta.isConnected) { encerrar(); return; }
            if (!blob.size) { encerrar(); mostrarAviso(c, "Não captei nenhum áudio. Tente de novo."); return; }
            a.fase = "transcrevendo";
            pintar();
            enviar(c, a, blob, segundos);
        };
        a.relogio = setInterval(() => {
            if (!c.ta.isConnected) { descartar(); return; }
            a.segundos = Math.floor((Date.now() - a.inicio) / 1000);
            if (a.segundos >= AVISO_S && !a.avisou) {
                a.avisou = true;
                mostrarAviso(c, `Faltam ${LIMITE_S - AVISO_S} s para o limite de ${formatarTempo(LIMITE_S)}.`);
            }
            pintar();
        }, 1000);
        a.limite = setTimeout(parar, LIMITE_S * 1000);
        try { recorder.start(); } catch (e) { clearInterval(a.relogio); clearTimeout(a.limite); falhouGravar(); return; }
        vigiar();
        pintar();
    }

    function parar() {
        if (ativo && ativo.fase === "gravando" && ativo.recorder.state !== "inactive") ativo.recorder.stop();
    }

    async function enviar(c, a, blob, segundos) {
        const ext = /mp4/.test(blob.type) ? "mp4" : /ogg/.test(blob.type) ? "ogg" : "webm";
        const form = new FormData();
        form.append("audio", blob, `ditado.${ext}`);
        form.append("duracao_segundos", String(segundos));
        mostrarAviso(c, "");
        try {
            const r = await Api.enviarFormulario("/ia/ditado", form);
            if (config && r && typeof r.minutos_restantes === "number") {
                config.minutos_restantes = r.minutos_restantes;
                if (r.minutos_restantes <= 0) esgotado = true;
            }
            // Saiu da tela durante a transcrição: descarta o texto.
            if (a.descartado || !c.ta.isConnected) { if (ativo === a) encerrar(); else pintar(); return; }
            const texto = String((r && r.texto) || "").trim();
            encerrar();
            if (!texto) { mostrarAviso(c, "Não entendi nada nessa gravação. Tente falar mais perto do microfone."); return; }
            const ta = c.ta;
            const novo = inserirNoCursor(ta.value, ta.selectionStart, ta.selectionEnd, texto);
            ta.value = novo.valor;
            ta.dispatchEvent(new Event("input", { bubbles: true }));
            ta.focus();
            try { ta.setSelectionRange(novo.inicio, novo.fim); } catch (e) { /* sem seleção */ }
        } catch (err) {
            if (a.descartado || !c.ta.isConnected) { if (ativo === a) encerrar(); return; }
            encerrar();
            if (err && err.status === 409) {
                esgotado = true;
                if (config) config.minutos_restantes = 0;
                pintar();
                mostrarAviso(c, err.message);
            } else if (err && (err.status === undefined || err.status === 502)) {
                // Rede ou falha na transcrição: reenvia o mesmo áudio guardado na memória.
                mostrarAviso(c, (err.status === 502 && err.message) || "Não foi possível enviar o áudio.", {
                    rotulo: "Tentar de novo",
                    fazer: () => {
                        if (ativo || esgotado || !c.ta.isConnected) return;
                        const b = { ta: c.ta, fase: "transcrevendo" };
                        ativo = b; vigiar(); pintar();
                        enviar(c, b, blob, segundos);
                    },
                });
            } else if (err && err.message !== "401") {
                mostrarAviso(c, err.message || "Não foi possível transcrever.");
            }
        }
    }

    function ligarCampo(ta) {
        if (achar(ta)) return;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "ditado-botao";
        btn.setAttribute("aria-label", "Ditar");
        btn.textContent = "🎤";
        const aviso = document.createElement("div");
        aviso.className = "ditado-aviso";
        aviso.setAttribute("role", "status");
        aviso.hidden = true;
        const c = { ta, btn, aviso };
        campos.add(c);
        btn.addEventListener("click", () => {
            if (ativo && ativo.ta === ta && ativo.fase === "gravando") parar();
            else iniciar(c);
        });
        if (ta.id) btn.setAttribute("aria-controls", ta.id);
        // O botão fica AO LADO do rótulo (não dentro): senão o nome acessível do campo
        // viraria "Diagnóstico Ditar". Rótulo = label[for] ou o label logo antes da textarea.
        const pai = ta.parentElement;
        let rotulo = ta.id && pai ? pai.querySelector(`label[for="${ta.id}"]`) : null;
        if (!rotulo) {
            const antes = ta.previousElementSibling;
            if (antes && antes.tagName === "LABEL") rotulo = antes;
        }
        if (rotulo && rotulo.parentElement) {
            let linha = rotulo.parentElement;
            if (!linha.classList.contains("ditado-linha")) {
                linha = document.createElement("div");
                linha.className = "ditado-linha";
                rotulo.parentElement.insertBefore(linha, rotulo);
                linha.appendChild(rotulo);
            }
            linha.appendChild(btn);
        } else {
            ta.insertAdjacentElement("beforebegin", btn);
        }
        ta.insertAdjacentElement("afterend", aviso);
    }

    // Liga o 🎤 nas textareas achadas por `seletores` dentro de `raiz`. Pode ser
    // chamado de novo após re-render (não duplica botão; campo novo ganha o seu).
    async function ligar(raiz, seletores) {
        if (!raiz) return;
        const cfg = await carregarConfig();
        if (!cfg || cfg.disponivel === false) return;
        for (const sel of seletores || []) {
            raiz.querySelectorAll(sel).forEach(el => { if (el.tagName === "TEXTAREA" && el.isConnected) ligarCampo(el); });
        }
        pintar();
    }

    return { carregarConfig, ligar };
})() : null;
if (typeof window !== "undefined") window.Ditado = Ditado;
