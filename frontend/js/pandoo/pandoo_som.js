// ============================================================================
// Pandoo (25/09/2026) — sons (Web Audio, nenhum arquivo) e voz das figuras.
// Voz: o áudio gravado pelo profissional tem prioridade; sem ele, a voz do
// navegador em pt-BR. A voz começa em até 1 s depois que a figura aparece (tempo
// de a criança olhar primeiro — pedido do usuário; era 2 s até 26/09/2026). Desde
// 21/10/2026 a espera é de 0,6 s: medido no Chrome, a voz do navegador leva mais
// 0,2–0,35 s para começar, e com 1 s de espera o início real passava de 1,2 s.
// O som pode ser desligado no palco.
// ============================================================================

const ATRASO_VOZ_MS = 600;

const PandooSom = (() => {
    let ac = null;
    let temporizador = null;
    let audioAtual = null;
    let falaAtual = null;     // mantém a fala viva até o fim (Chrome)
    let comandoAtual = 0;     // fala de comando em andamento (cancelada por pararVoz)
    let notasAgendadas = [];   // para "parar" também cortar o tique-tique da roleta

    function contexto() {
        if (!ac) ac = new (window.AudioContext || window.webkitAudioContext)();
        if (ac.state === "suspended") ac.resume();
        return ac;
    }

    function nota(freq, ini, dur, tipo = "sine", vol = 0.25) {
        if (!som.ligado) return;
        try {
            const a = contexto(), o = a.createOscillator(), g = a.createGain();
            o.type = tipo;
            o.frequency.value = freq;
            g.gain.setValueAtTime(0, a.currentTime + ini);
            g.gain.linearRampToValueAtTime(vol, a.currentTime + ini + 0.01);
            g.gain.exponentialRampToValueAtTime(0.001, a.currentTime + ini + dur);
            o.connect(g).connect(a.destination);
            o.start(a.currentTime + ini);
            o.stop(a.currentTime + ini + dur + 0.05);
            notasAgendadas.push(o);
            o.onended = () => { notasAgendadas = notasAgendadas.filter(x => x !== o); };
        } catch (e) { /* navegador sem Web Audio: segue sem som */ }
    }

    // `aoTerminar` (05/11/2026): o "Toque só no alvo" fala a frase do comando
    // e, depois dela, a voz gravada da figura.
    function vozDoNavegador(texto, aoTerminar = null) {
        if (!("speechSynthesis" in window) || !texto) { if (aoTerminar) aoTerminar(); return; }
        speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(texto);
        if (aoTerminar) {
            // Revisão final (05/11/2026): alguns motores de voz não disparam
            // onend; a gravação vem mesmo assim, uma vez só. `u` fica guardado
            // para o Chrome não recolher a fala antes do fim.
            let feito = false;
            const uma = () => { if (feito) return; feito = true; clearTimeout(seguranca); aoTerminar(); };
            const seguranca = setTimeout(uma, 1000 + 120 * texto.length);
            u.onend = uma;
            u.onerror = uma;
        }
        falaAtual = u;
        u.lang = "pt-BR";
        u.rate = 0.85;
        u.pitch = 1.15;
        const voz = speechSynthesis.getVoices().find(v => v.lang && v.lang.toLowerCase().startsWith("pt-br"));
        if (voz) u.voice = voz;
        speechSynthesis.speak(u);
    }

    // Toca um áudio gravado e chama `aoTerminar` uma vez (fim, erro ou o
    // navegador recusando tocar). Parado por `pararVoz`, não chama.
    function tocarAudio(b64, aoTerminar) {
        let feito = false;
        const uma = () => { if (feito) return; feito = true; aoTerminar(); };
        const audio = new Audio(`data:${mimeDoAudio(b64)};base64,${b64}`);
        audioAtual = audio;
        audio.onended = uma;
        audio.onerror = uma;
        audio.play().catch(uma);
    }

    function falarAgora(item) {
        const pergunta = (item && item.pergunta) || {};
        if (pergunta.audio) {
            // data: e não blob: — a CSP (media-src 'self' data:) bloqueia blob:.
            audioAtual = new Audio(`data:${mimeDoAudio(pergunta.audio)};base64,${pergunta.audio}`);
            audioAtual.play().catch(() => vozDoNavegador(pergunta.texto));
        } else {
            vozDoNavegador(pergunta.texto);
        }
    }

    const som = {
        ligado: true,
        alternar() {
            som.ligado = !som.ligado;
            if (!som.ligado) som.parar();
            return som.ligado;
        },
        // "tique-tique" que desacelera, acompanhando a roleta
        giro(ms) {
            let t = 0, intervalo = 0.045;
            while (t < ms / 1000 - 0.2) { nota(1200, t, 0.03, "square", 0.08); t += intervalo; intervalo *= 1.07; }
        },
        conseguiu() { [523, 659, 784, 1047].forEach((f, i) => nota(f, i * 0.11, 0.35, "triangle", 0.3)); },
        treinar() { nota(392, 0, 0.25, "sine", 0.25); nota(523, 0.18, 0.4, "sine", 0.25); },
        final() { [523, 659, 784, 659, 784, 1047].forEach((f, i) => nota(f, i * 0.13, 0.4, "triangle", 0.3)); },
        // cortarSom=false (Memória, 01/10/2026): a fala espera sem cortar as
        // notas da comemoração que já estão tocando.
        falarItem(item, { atrasoMs = ATRASO_VOZ_MS, voz = true, cortarSom = true } = {}) {
            if (cortarSom) som.parar(); else som.pararVoz();
            const pergunta = (item && item.pergunta) || {};
            if (!som.ligado || !voz || (!pergunta.texto && !pergunta.audio)) return;
            temporizador = setTimeout(() => { temporizador = null; falarAgora(item); }, atrasoMs);
        },
        repetirItem(item) { som.falarItem(item, { atrasoMs: 0 }); },
        // "Toque só no alvo" (05/11/2026): "Toque só no" + a palavra do alvo.
        // Com voz gravada, a frase sai pela voz do navegador e a gravação vem
        // em seguida; sem ela, tudo numa fala só. `pararVoz` cancela as duas.
        // `fraseAudio` (07/11/2026): a frase gravada pelo profissional toca no
        // lugar da voz do navegador; depois vem a voz gravada ou a palavra do alvo.
        falarComando(inicio, item, { atrasoMs = 0, fraseAudio = null } = {}) {
            som.parar();
            const pergunta = (item && item.pergunta) || {};
            if (!som.ligado) return;
            const vez = ++comandoAtual;
            temporizador = setTimeout(() => {
                temporizador = null;
                if (fraseAudio) {
                    tocarAudio(fraseAudio, () => {
                        if (vez !== comandoAtual) return;
                        if (pergunta.audio) falarAgora(item); else vozDoNavegador(pergunta.texto);
                    });
                } else if (pergunta.audio) {
                    vozDoNavegador(inicio, () => { if (vez === comandoAtual) falarAgora(item); });
                } else {
                    vozDoNavegador([inicio, pergunta.texto].filter(Boolean).join(" "));
                }
            }, atrasoMs);
        },
        // true enquanto há fala agendada ou tocando (voz gravada ou do navegador).
        falando() {
            if (temporizador) return true;
            if (audioAtual && !audioAtual.paused && !audioAtual.ended) return true;
            return "speechSynthesis" in window && (speechSynthesis.speaking || speechSynthesis.pending);
        },
        pararVoz() {
            comandoAtual++;
            if (temporizador) { clearTimeout(temporizador); temporizador = null; }
            if ("speechSynthesis" in window) speechSynthesis.cancel();
            if (audioAtual) { try { audioAtual.pause(); } catch (e) { /* já parado */ } audioAtual = null; }
        },
        parar() {
            som.pararVoz();
            notasAgendadas.forEach(o => { try { o.stop(); } catch (e) { /* já terminou */ } });
            notasAgendadas = [];
        },
    };
    // Carrega a lista de vozes cedo (no Chrome ela chega assíncrona).
    if (typeof window !== "undefined" && "speechSynthesis" in window) speechSynthesis.getVoices();
    return som;
})();
