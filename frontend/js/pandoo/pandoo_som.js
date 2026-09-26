// ============================================================================
// Pandoo (25/09/2026) — sons (Web Audio, nenhum arquivo) e voz das figuras.
// Voz: o áudio gravado pelo profissional tem prioridade; sem ele, a voz do
// navegador em pt-BR. A voz começa 2 s depois que a figura aparece (tempo de a
// criança olhar primeiro — pedido do usuário). O som pode ser desligado no palco.
// ============================================================================

const PandooSom = (() => {
    let ac = null;
    let temporizador = null;
    let audioAtual = null;
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

    function vozDoNavegador(texto) {
        if (!("speechSynthesis" in window) || !texto) return;
        speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(texto);
        u.lang = "pt-BR";
        u.rate = 0.85;
        u.pitch = 1.15;
        const voz = speechSynthesis.getVoices().find(v => v.lang && v.lang.toLowerCase().startsWith("pt-br"));
        if (voz) u.voice = voz;
        speechSynthesis.speak(u);
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
        falarItem(item, { atrasoMs = 2000, voz = true } = {}) {
            som.parar();
            const pergunta = (item && item.pergunta) || {};
            if (!som.ligado || !voz || (!pergunta.texto && !pergunta.audio)) return;
            temporizador = setTimeout(() => { temporizador = null; falarAgora(item); }, atrasoMs);
        },
        repetirItem(item) { som.falarItem(item, { atrasoMs: 0 }); },
        parar() {
            if (temporizador) { clearTimeout(temporizador); temporizador = null; }
            notasAgendadas.forEach(o => { try { o.stop(); } catch (e) { /* já terminou */ } });
            notasAgendadas = [];
            if ("speechSynthesis" in window) speechSynthesis.cancel();
            if (audioAtual) { try { audioAtual.pause(); } catch (e) { /* já parado */ } audioAtual = null; }
        },
    };
    // Carrega a lista de vozes cedo (no Chrome ela chega assíncrona).
    if (typeof window !== "undefined" && "speechSynthesis" in window) speechSynthesis.getVoices();
    return som;
})();
