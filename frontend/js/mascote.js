// ============================================================================
// mascote.js — Mascote evolutivo (elemento-assinatura da marca)
//
// O mascote é um "blob" orgânico com a cor da marca, que ganha acessórios
// e brilho conforme o mascote_estagio (1 a 5) do paciente evolui — tornando
// visível, de forma lúdica, o progresso da jornada terapêutica.
// ============================================================================

const CORES_MASCOTE = ["#8B5FBF", "#5B4FE9", "#2E8FA3", "#2E9E6B", "#E8875E"];

function svgMascote({ emoji = "🐻", estagio = 1, tamanho = 120, flutuar = false } = {}) {
    const cor = CORES_MASCOTE[Math.min(estagio, 5) - 1] || CORES_MASCOTE[0];
    const corClara = cor + "26"; // transparência
    const temChapeu = estagio >= 2;
    const temEstrelas = estagio >= 3;
    const temCoroa = estagio >= 5;
    const numEstrelas = Math.min(estagio - 2, 3);

    let estrelasSvg = "";
    const posicoes = [[14, 20], [104, 30], [8, 85]];
    for (let i = 0; i < numEstrelas; i++) {
        const [x, y] = posicoes[i];
        estrelasSvg += `<text x="${x}" y="${y}" font-size="16" class="mascote-estrela-svg">⭐</text>`;
    }

    return `
    <div class="mascote-wrap ${flutuar ? "mascote-flutuante" : ""}" style="width:${tamanho}px;height:${tamanho}px;">
      <svg viewBox="0 0 120 120" width="${tamanho}" height="${tamanho}">
        <ellipse cx="60" cy="108" rx="34" ry="7" fill="${cor}" opacity="0.12"/>
        <circle cx="60" cy="62" r="46" fill="${corClara}"/>
        <path d="M60 20 C86 20 104 40 104 64 C104 90 84 104 60 104 C36 104 16 90 16 64 C16 40 34 20 60 20 Z"
              fill="${cor}"/>
        <circle cx="30" cy="72" r="6" fill="#ffffff40"/>
        <circle cx="90" cy="72" r="6" fill="#ffffff40"/>
        ${temChapeu ? `<path d="M60 8 L50 24 L70 24 Z" fill="#FFB84D"/><rect x="47" y="22" width="26" height="5" rx="2.5" fill="#E89B2A"/>` : ""}
        ${temCoroa ? `<path d="M45 14 L50 24 L60 12 L70 24 L75 14 L72 26 L48 26 Z" fill="#FFD700" stroke="#E89B2A" stroke-width="1"/>` : ""}
        <text x="60" y="66" font-size="30" text-anchor="middle" dominant-baseline="middle">${emoji}</text>
        ${estrelasSvg}
      </svg>
    </div>`;
}

function nivelParaTexto(nivel) {
    const nomes = ["Explorador Iniciante", "Aventureiro", "Desbravador", "Campeão", "Mestre da Jornada"];
    return nomes[Math.min(nivel, 5) - 1] || nomes[0];
}
