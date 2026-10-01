# Pandoo fase 2 — Memória

Data: 01/10/2026 · Status: design aprovado pelo usuário, com prévia jogável
(`.superpowers/brainstorm/1947-1790866078/content/memoria-v2.html`, não
versionada).

## Objetivo

Terceiro jogo do Pandoo, a **Memória**. As cartas ficam viradas para baixo e
a criança vira duas por vez procurando os pares. Como o Quiz, a Memória
reaproveita o que já existe: o editor; o palco (cenário, som, voz, placar,
"Finalizar jogo" e resumo); o resultado por figura na ficha; a Biblioteca; as
missões; e a regra de que a missão só libera com pelo menos uma rodada (aqui,
um par achado).

Ordem da fase 2, um jogo por vez:

1. Quiz (pronto, PR #31/#32).
2. **Memória** (esta spec).
3. Associação.
4. Quebra-cabeça.
5. Flashcards, com a pronúncia.

## Decisões do usuário

- **O profissional escolhe o tipo de par** do jogo inteiro:
  - `figura`, "Figura + figura igual": a memória clássica, em que as duas
    cartas têm a mesma imagem;
  - `palavra`, "Figura + palavra": uma carta tem a imagem e a outra, a palavra
    escrita.
- **⭐ quando a criança lembra onde estava.** Errar no começo é normal, porque
  ainda não se sabe onde estão as cartas.
  - O par conta "treinar" se, numa jogada, a **primeira** carta virada era
    desse par, a outra carta do par **já tinha aparecido** numa jogada
    anterior e a criança virou a segunda carta errada. Ou seja, ela já tinha
    visto a carta certa e não lembrou.
  - Em qualquer outro caso, o par conta "conseguiu" ⭐ quando for achado.
- **Quantos pares:** o profissional escolhe 3, 4, 6, 8 ou 10 pares por
  partida (padrão 6). Se o jogo tiver mais figuras, cada partida sorteia quais
  entram. Se tiver menos, entram todas.
- **Prévia aceita:**
  - o verso da carta é roxo com uma patinha 🐾;
  - o par achado fica virado, com borda verde, som de acerto, e a voz diz a
    palavra;
  - no erro, as cartas balançam, ficam à mostra por **1,2 s** e viram de
    novo, com a dica "Quase! Lembre onde estavam 💚".
- **Ajuste pedido na prévia, que vale para todos os jogos:** o **título do
  jogo** no palco fica numa pílula branca sólida com texto escuro, como o
  placar. Hoje ele é branco sobre uma pílula transparente, ilegível no
  Bambuzal, e o mesmo acontece no Quiz e na Roleta.

## 1. Conteúdo e regras (backend, `pandoo_service.py`)

Mesmo formato único v1, sem migração. Para a Memória:

- `pergunta.imagem`: obrigatória, em toda figura.
- `pergunta.texto`: a palavra. Obrigatória no tipo `palavra`, e as palavras
  precisam ser **diferentes entre si**, comparadas sem acento e sem caixa (com
  `_normalizar_palavra`). Duas cartas "Gato" iguais confundiriam a criança.
  No tipo `figura` é opcional; quando existe, é a palavra falada ao achar o
  par.
- `pergunta.audio`: voz gravada, opcional (falada ao achar o par).
- `distratores`: não usados, e a Memória não os guarda
  (`MAX_DISTRATORES` padrão 0).

`MODELOS = {"roleta", "quiz", "memoria"}` e
`REGRAS_PADRAO["memoria"]`:

```json
{"pares": "figura", "quantidade": 6, "som": true, "voz": true}
```

- `pares` ∈ {`figura`, `palavra`}; qualquer outro valor vira o padrão.
- `quantidade` ∈ {3, 4, 6, 8, 10}; qualquer outro valor vira o padrão.
- `som` e `voz` são booleanos.

Mensagens de erro, no padrão das que já existem:

- `Item N: a memória precisa de uma imagem em cada figura.`
- `Item N: a memória precisa da palavra de cada figura no tipo 'Figura + palavra'.`
- `Item N: a palavra repete a de outra figura — no tipo 'Figura + palavra' as palavras precisam ser diferentes.`

## 2. Regras puras (front, `pandoo_core.js`, testadas em Node)

- `REGRAS_PADRAO_PANDOO.memoria`, espelho do backend.
- `problemasDoConteudo("memoria", conteudo, regras)` faz as mesmas checagens
  do backend, com as mensagens "Figura N: …".
- `montarCartasMemoria(conteudo, regras, aleatorio)`:
  - sorteia `min(quantidade, itens)` figuras;
  - devolve as cartas embaralhadas, no formato
    `{id, item_id, face: "figura" | "palavra"}`;
  - no tipo `figura`, as duas cartas do par são `figura`; no tipo `palavra`,
    uma é `figura` e a outra é `palavra`.
- `estadoInicialMemoria(cartas)` guarda as cartas vistas, os pares achados,
  os pares marcados "treinar", as rodadas e os detalhes.
- `jogadaMemoria(estado, cartas, primeiraId, segundaId)` devolve
  `{estado, acertou, item_id, resultado}`:
  - `resultado` só vem quando `acertou`, e vale "conseguiu" ou "treinar";
  - no erro, aplica a regra do "lembrou onde estava" da seção "Decisões do
    usuário" à primeira carta.
- `memoriaTerminou(estado, cartas)` diz se todos os pares foram achados.
- `layoutMesaMemoria(nCartas, largura, altura)` devolve
  `{colunas, tamanho}`:
  - escolhe o maior tamanho de carta (proporção 3:4) em que todas cabem na
    área, sem rolar;
  - o tamanho fica entre 56 e 150 px de largura;
  - abaixo de 56 px, aceita rolar (só em telas muito pequenas).

## 3. Tela

### O jogo, `frontend/js/pandoo/jogos/memoria.js`

O jogo é registrado com
`registrarJogo("memoria", {nome: "Memória", icone: "🧠", rotuloRodada: ["par", "pares"], avisoSemRodada: "Você ainda não achou nenhum par. Ache pelo menos um para liberar a missão 🧠", ...})`.

- **Mesa:** uma grade de cartas com o tamanho dado por `layoutMesaMemoria`,
  recalculado quando a janela muda de tamanho.
  - O verso é a patinha.
  - A frente é a imagem, ou a palavra em letra grande, na fonte da criança.
  - A carta vira com animação 3D. Quem prefere menos movimento
    (`prefers-reduced-motion`) vê a troca sem animação.
- **Jogada:**
  - A criança vira a primeira carta, depois a segunda.
  - **Se acertou:** as duas ficam viradas e com borda verde. O palco chama
    `palco.registrar(item, resultado, {comemorar: true})`, e a voz diz a
    palavra (se `voz` estiver ligada) logo depois do som, **sem cortar o som
    de acerto**. A dica fica "Isso! Achou o par ⭐", ou "Achou! Vamos treinar
    mais 💪" quando o par conta "treinar".
  - **Se errou:** as cartas balançam, ficam à mostra por 1,2 s e viram. Toca
    o som suave (`palco.efeito("treinar")`), e a dica fica "Quase! Lembre onde
    estavam 💚".
  - Enquanto as duas cartas estão viradas, a mesa fica travada: um terceiro
    toque não faz nada. Tocar numa carta já virada ou num par já achado
    também não faz nada.
- **Placar e fim:**
  - O placar mostra "🧠 x de N pares" e ⭐ (pares com "conseguiu").
  - Quando o último par é achado, o resumo aparece 1,2 s depois.
  - "Finalizar jogo" segue a regra comum: sem nenhum par achado, a missão não
    salva e o palco avisa.
- O resumo diz "em N pares" (pelo `rotuloRodada`).

### O palco, para todos os jogos

- `.pd-titulo` passa a ser uma pílula branca sólida com texto escuro, sem
  sombra clara, no mesmo estilo do placar.
- Para a voz não cortar a comemoração, o jogo precisa conseguir falar a
  palavra **depois** do som de acerto. Hoje `PandooSom.falarItem` chama
  `parar()`, que também corta as notas. O plano decide como resolver; o
  requisito é: no acerto da Memória, o som toca inteiro e a palavra vem em
  seguida.

### O editor, `views/pandoo.js`

- O cartão "Memória" deixa de ser "em breve".
- O título da lista vira "2. Figuras da memória", com a dica "De 2 a 24
  figuras. Para cada uma: a imagem e, se quiser, a palavra e a sua voz (ditas
  quando a criança acha o par)."
- O painel de regras da Memória (em `renderRegras`/`lerRegras`) tem:
  - "Como são os pares", com dois cartões: "🖼️🖼️ Figura + figura igual" e
    "🖼️🔤 Figura + palavra";
  - "Quantos pares em cada partida": 3, 4, 6, 8 ou 10, com a nota "Se o jogo
    tiver mais figuras, cada partida sorteia quais entram.";
  - "Som de acerto e comemoração";
  - "Falar a palavra quando achar o par".
- Trocar de modelo continua como no Quiz: as figuras ficam, e as regras
  voltam ao padrão do modelo novo, guardando só `som` e `voz`.

## 4. Testes

- **Backend** (`tests/test_pandoo_memoria.py`):
  - regras padrão e valores fora do permitido;
  - imagem obrigatória;
  - palavra obrigatória no tipo `palavra`;
  - palavras repetidas (com acento ou caixa diferente) recusadas no tipo
    `palavra` e aceitas no tipo `figura`;
  - a Memória não guarda distratores.
- **Node** (`pandoo_core.test.js`):
  - `montarCartasMemoria`: o número de cartas, os pares completos, o sorteio
    quando há mais figuras e as faces de cada tipo;
  - `jogadaMemoria`: acerto de primeira = "conseguiu"; erro sem ter visto =
    o par continua "conseguiu"; primeira carta com o par já visto + segunda
    errada = "treinar"; jogar uma carta já achada não muda o estado;
  - `memoriaTerminou`;
  - `layoutMesaMemoria`: celular 390×600 com 12 e 20 cartas e computador
    1366×600 com 20 cartas cabem sem rolar, sempre com tamanho ≥ 56;
  - `problemasDoConteudo("memoria", …)`.
- **Navegador** (Playwright):
  - o editor troca para Memória e salva nos dois tipos;
  - na prévia: errar um par (as cartas voltam) e acertar (ficam verdes);
  - o placar e o resumo "em N pares";
  - a missão da criança no celular, sem nenhum par (não libera) e com um par
    (libera);
  - a ficha mostra a partida;
  - o título do palco fica legível;
  - nenhum erro de JS.

## Fora do escopo

- Fases crescentes.
- Cronômetro.
- Limite de tentativas.
- Dois jogadores.
- Figuras com a mesma imagem e palavras diferentes no tipo `figura`: as
  cartas ficariam iguais. Isso não é checado, porque comparar imagens está
  fora desta fase.
