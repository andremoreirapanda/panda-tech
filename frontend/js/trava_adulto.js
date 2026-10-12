// ============================================================================
// Trava dos pais (12/10/2026): para sair do Mundo da Criança, um adulto
// responde uma conta simples. Evita que a criança caia sozinha na área dos
// pais (chat, agenda, pagamento). Função pura testada em
// frontend/tests/trava_adulto.test.js; o pop-up fica em views/crianca.js.
// ============================================================================

// { pergunta: "Quanto é 7 + 5?", resposta: 12, opcoes: [3 números, embaralhados] }
function gerarDesafioAdulto(rand = Math.random) {
    const sortear = (min, max) => min + Math.floor(rand() * (max - min + 1));
    const x = sortear(3, 9);
    const y = sortear(3, 9);
    const resposta = x + y;
    const opcoes = new Set([resposta]);
    const desvios = [-2, -1, 1, 2, 3];
    let tentativa = 0;
    while (opcoes.size < 3) {
        const d = desvios[(sortear(0, desvios.length - 1) + tentativa) % desvios.length];
        opcoes.add(resposta + d);
        tentativa += 1;
    }
    const lista = [...opcoes];
    for (let i = lista.length - 1; i > 0; i--) {
        const j = sortear(0, i);
        [lista[i], lista[j]] = [lista[j], lista[i]];
    }
    return { pergunta: `Quanto é ${x} + ${y}?`, resposta, opcoes: lista };
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { gerarDesafioAdulto };
}
