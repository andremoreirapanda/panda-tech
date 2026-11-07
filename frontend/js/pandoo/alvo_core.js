// ============================================================================
// Pandoo (05/11/2026) — "Toque só no alvo": regras puras, sem DOM.
// Figuras aparecem em 3 fases; a criança toca só na figura-alvo. Este arquivo
// sorteia as figuras de cada fase, transforma cada figura em um detalhe do
// resultado, decide a próxima fase e calcula as medidas da ficha (espelho de
// pandoo_service.medidas_alvo). Testes: frontend/tests/pandoo_alvo.test.js
// ============================================================================

// Tempo (ms) que cada figura fica à vista, por fase e velocidade.
const TEMPOS_ALVO = {
    1: { lenta: 2000, media: 1500, rapida: 1000 },
    2: { lenta: 2200, media: 1700, rapida: 1200 },
    3: { lenta: 4500, media: 3500, rapida: 2500 },
};
const INTERVALO_FASE1_MS = 600;
const SUBIDA_TOCA_MS = 300;   // .pda-campo.fase2 .pda-fig (animação pdaSobe)
const AVISO_SEM_TOQUE_ALVO = "Você ainda não tocou em nenhuma figura. Toque nas figuras para liberar a missão 🎯";
const NOMES_FASES_ALVO = { 1: "Uma de cada vez", 2: "Saindo das tocas", 3: "Passando pela tela" };

function _tresSeguidos(posicoes) {
    const set = new Set(posicoes);
    return posicoes.some(p => set.has(p + 1) && set.has(p + 2));
}

// Lista das figuras de uma fase: ~1 alvo a cada 3, nunca começando pelo alvo
// e nunca com 3 alvos seguidos. As pegadinhas saem das outras figuras.
function sortearFigurasAlvo(itens, alvoId, quantidade, aleatorio = Math.random) {
    const alvo = itens.find(i => i.id === alvoId);
    const outros = itens.filter(i => i.id !== alvoId);
    const n = Math.max(1, quantidade);
    const k = Math.min(Math.max(1, Math.round(n / 3)), Math.max(0, n - 1));
    let posicoes = null;
    for (let tentativa = 0; tentativa < 50 && !posicoes; tentativa++) {
        const livres = Array.from({ length: n - 1 }, (_, i) => i + 1);
        for (let i = livres.length - 1; i > 0; i--) {
            const j = Math.floor(aleatorio() * (i + 1));
            [livres[i], livres[j]] = [livres[j], livres[i]];
        }
        const escolhidas = livres.slice(0, k).sort((x, y) => x - y);
        if (!_tresSeguidos(escolhidas)) posicoes = escolhidas;
    }
    if (!posicoes) posicoes = Array.from({ length: k }, (_, j) => 1 + Math.floor(j * (n - 1) / k));
    const ehAlvo = new Set(posicoes);
    return Array.from({ length: n }, (_, i) => {
        if (ehAlvo.has(i) && alvo) return alvo;
        return outros.length ? outros[Math.floor(aleatorio() * outros.length)] : alvo;
    });
}

// Alvo tocado = conseguiu; alvo perdido = treinar; pegadinha tocada = treinar;
// pegadinha que passou = conseguiu (a criança segurou o toque).
function detalheAlvo(item, alvoId, tocou, fase, tempoMs) {
    const alvo = item.id === alvoId;
    const detalhe = {
        item_id: item.id,
        texto: (item.pergunta && item.pergunta.texto) || "",
        resultado: alvo === tocou ? "conseguiu" : "treinar",
        alvo, tocou, fase,
    };
    if (alvo && tocou && Number.isFinite(tempoMs)) detalhe.tempo_ms = Math.max(0, Math.min(10000, Math.round(tempoMs)));
    return detalhe;
}

function avaliarFaseAlvo(detalhesDaFase) {
    const alvos = detalhesDaFase.filter(d => d.alvo);
    const tocados = alvos.filter(d => d.tocou).length;
    const erros = detalhesDaFase.filter(d => !d.alvo && d.tocou).length;
    // 07/11/2026 (pedido do usuário): era ≥ 80% e ≤ 1 toque errado.
    return (alvos.length === 0 || tocados / alvos.length >= 0.7) && erros <= 3;
}

// Próxima fase ou null quando a partida acaba. Com "subir sozinho", só avança
// quem passou na fase; quem não passou termina ali (não repete a fase).
function proximaFaseAlvo(regras, faseAtual, detalhesDaFase) {
    const fim = Number(regras.fase_fim) || 3;
    if (faseAtual >= fim) return null;
    if (regras.subir_sozinho && !avaliarFaseAlvo(detalhesDaFase)) return null;
    return faseAtual + 1;
}

function medidasAlvo(detalhes) {
    const alvos = detalhes.filter(d => d.alvo);
    const tocados = alvos.filter(d => d.tocou);
    const tempos = tocados.map(d => d.tempo_ms).filter(t => Number.isInteger(t));
    return {
        alvos_tocados: tocados.length,
        alvos_total: alvos.length,
        alvos_perdidos: alvos.length - tocados.length,
        toques_errados: detalhes.filter(d => !d.alvo && d.tocou).length,
        tempo_medio_ms: tempos.length ? Math.round(tempos.reduce((s, t) => s + t, 0) / tempos.length) : null,
        fase_alcancada: detalhes.reduce((m, d) => Math.max(m, d.fase || 1), 1),
    };
}

// Quanto tempo depois de entrar na tela a figura fica visível (revisão final,
// 05/11/2026): a reação conta daí. Fase 2 = subida da toca; fase 3 = a figura
// nasce fora da área e anda a própria largura antes de aparecer.
function atrasoVisivelAlvo(fase, tempoMs, larguraFig, larguraCampo) {
    if (fase === 2) return SUBIDA_TOCA_MS;
    if (fase === 3 && larguraFig > 0) return Math.round(tempoMs * larguraFig / (larguraCampo + larguraFig));
    return 0;
}

// Texto do resumo: sem nenhum alvo na partida não mostra "0 de 0".
function textoResumoAlvo(m) {
    if (!m.alvos_total) return { pegou: null, segurou: false };
    return { pegou: `${m.alvos_tocados} de ${m.alvos_total}`, segurou: m.toques_errados === 0 };
}

// Partida só conta como jogada com pelo menos um toque (alvo ou pegadinha).
function houveToqueAlvo(detalhes) {
    return detalhes.some(d => d.tocou);
}

function fraseComandoAlvo(regras, item) {
    const inicio = String((regras && regras.frase_inicio) || "").trim() || "Toque só no";
    const palavra = String((item && item.pergunta && item.pergunta.texto) || "").trim();
    return `${palavra ? `${inicio} ${palavra}` : inicio}!`;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        TEMPOS_ALVO, INTERVALO_FASE1_MS, NOMES_FASES_ALVO, SUBIDA_TOCA_MS, AVISO_SEM_TOQUE_ALVO,
        atrasoVisivelAlvo, textoResumoAlvo, sortearFigurasAlvo, detalheAlvo, avaliarFaseAlvo,
        proximaFaseAlvo, medidasAlvo, houveToqueAlvo, fraseComandoAlvo,
    };
}
