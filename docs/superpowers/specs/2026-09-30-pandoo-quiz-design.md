# Pandoo fase 2 — Quiz

Data: 30/09/2026 · Status: design aprovado pelo usuário, com prévia
(`.superpowers/brainstorm/1133-1790779903/content/pandoo-quiz-v1.html`, não
versionada).

## Objetivo

Segundo jogo do Pandoo, o **Quiz**. A criança vê ou ouve uma pergunta e
toca na resposta certa entre 2 e 4 opções. O Quiz reusa tudo o que a roleta
já tem: editor, palco (cenário, som, voz, placar, "Finalizar jogo", resumo),
resultado por figura na ficha, Biblioteca, missões e a regra "missão só
libera com pelo menos uma rodada".

A fase 2 sai **um jogo por vez** (decisão do usuário, 30/09/2026): Quiz,
depois Memória, Associação e **Quebra-cabeça** (novo), e por último
**Flashcards**, em que a criança fala a palavra e só passa para o próximo
cartão se a pronúncia estiver certa. Esta spec cobre só o Quiz.

## Decisões do usuário

- **Opções erradas automáticas, com opcionais por figura.** O profissional
  cadastra só as figuras com a resposta certa. As opções erradas saem das
  outras figuras do jogo. Em cada figura dá para escrever opções erradas
  próprias (ex.: Rato × Pato × Gato).
- **O profissional escolhe o formato** do jogo inteiro:
  - `ouvir`: "Ouvir e achar a figura". A voz diz a palavra e as opções são
    figuras. A palavra também aparece escrita na pergunta (o usuário pediu
    para manter como está na prévia).
  - `ver`: "Ver a figura e achar a palavra". Aparece a figura e as opções
    são palavras.
- **Errou, tenta de novo.** A opção errada balança, fica apagada e toca um
  som suave, e a criança tenta outra. No resultado, a pergunta conta
  "conseguiu" se ela acertou **de primeira** e "treinar" se precisou de
  mais tentativas.
- **Padrões propostos, aceitos com a prévia:**
  - 2, 3 ou 4 opções por pergunta (padrão 3);
  - fim quando todas as perguntas saírem, ou depois de N perguntas;
  - leitura da pergunta 1 s depois de ela aparecer, com "🔊 Ouvir de novo";
  - som de acerto e comemoração.

## 1. Conteúdo e regras (backend, `pandoo_service.py`)

Mesmo formato único v1, sem migração. Para o Quiz:

- `pergunta.imagem`: obrigatória. É a figura (vira opção no modo `ouvir`,
  pergunta no modo `ver`).
- `pergunta.texto`: a palavra e resposta certa. Obrigatória no modo `ver`.
  No modo `ouvir`, é obrigatória quando não houver `pergunta.audio` (a
  pergunta precisa ter algo a ser falado).
- `pergunta.audio`: voz gravada, opcional.
- `distratores`: até **3** opções erradas próprias (texto), só usadas no modo
  `ver`. No modo `ouvir` as opções são figuras e sempre vêm das outras
  figuras.

`MODELOS = {"roleta", "quiz"}`. `REGRAS_PADRAO["quiz"]`:
```json
{"modo": "ouvir", "opcoes": 3, "fim": "todas", "perguntas": 10, "som": true, "voz": true}
```
- `modo` ∈ {`ouvir`, `ver`};
- `opcoes` ∈ {2, 3, 4};
- `fim` ∈ {`todas`, `perguntas`};
- `perguntas` entre 1 e 100.

Valores inválidos voltam ao padrão, como já acontece na roleta.

A validação passa a ser por modelo:
- roleta: sem mudança;
- quiz: imagem em todo item. No modo `ver`, texto em todo item. No modo
  `ouvir`, texto ou áudio em todo item. Mensagens no estilo das atuais
  ("Item 3: o quiz precisa da palavra de cada figura no modo 'Ver a figura
  e achar a palavra'.").

**Resultado**: o mesmo `POST /pandoo/resultados`. Cada detalhe é
`{item_id, texto, resultado: "conseguiu" | "treinar"}`, e `total_rodadas` é
o número de perguntas respondidas. Nada muda em `calcular_resultado`, na
ficha nem nas missões.

## 2. Regras puras (front, `pandoo_core.js`, testadas em Node)

- `REGRAS_PADRAO_PANDOO.quiz` igual ao backend.
- `problemasDoConteudo("quiz", conteudo, regras)`: espelha a validação
  acima. Passa a receber `regras`, porque o que é obrigatório depende do
  modo. A roleta continua sem usar `regras`.
- `opcoesDaPergunta(item, conteudo, regras, aleatorio)`: devolve a lista
  embaralhada de opções `{item_id | null, texto, imagem, certa}`.
  - `ouvir`: a figura certa mais `opcoes - 1` figuras de outros itens,
    sorteadas.
  - `ver`: a palavra certa, depois os distratores próprios, depois palavras
    de outros itens até completar `opcoes`, sem repetir texto (comparação
    sem acento e sem diferenciar maiúsculas).
  - Se não houver opções suficientes (ex.: 2 itens com 4 opções), usa as
    que existem, com no mínimo 2.
- `estadoInicialQuiz(conteudo)`, `proximaPerguntaQuiz(estado, conteudo,
  aleatorio)`, `registrarRespostaQuiz(estado, item, tentativas)` e
  `quizTerminou(estado, regras, conteudo)`. A ordem das perguntas é
  sorteada sem repetir. No modo `perguntas` com N maior que o número de
  itens, repete só depois de todas saírem, como na roleta. Terminou quando
  todas saíram (`todas`) ou quando respondeu N (`perguntas`).

## 3. Tela

- **Jogo** `frontend/js/pandoo/jogos/quiz.js`:
  `registrarJogo("quiz", {nome: "Quiz", icone: "❓", ...})`, dentro do palco
  comum:
  - **cartão da pergunta:**
    - `ouvir`: "Onde está…", 🔊, a palavra escrita e "🔊 Ouvir de novo";
    - `ver`: a figura grande, "Qual é o nome?" e "🔊 Ouvir de novo";
  - **grade de opções:** figuras em 2 ou 3 colunas no modo `ouvir`, e
    botões de palavra grandes (uma coluna) no modo `ver`;
  - **placar** "❓ x de N" e ⭐ (acertos de primeira);
  - **opção errada:** balança, fica apagada e não pode ser tocada de novo;
    dica "Quase! Tente outra 💚";
  - **opção certa:** fica verde, confete e som; dica "Acertou de primeira!
    ⭐" ou "Isso! Conseguiu 💪"; depois de 1,5 s vem a próxima pergunta, ou
    o resumo se terminou;
  - a pergunta é lida 1 s depois de aparecer (`palco.falarItem`), quando
    `voz` está ligado;
  - "Finalizar jogo": mesma regra da roleta. Sem nenhuma resposta, na
    missão não salva e avisa.
- **Palco comum**: o resumo diz "em N perguntas" no Quiz ("em N giros" na
  roleta). O jogo informa a palavra da rodada pelo contrato
  (`registrarJogo(..., {rotuloRodada: ["pergunta", "perguntas"]})`).
- **Editor** (`views/pandoo.js`):
  - o cartão "Quiz" deixa de ser "em breve";
  - trocar de modelo mantém as figuras e ajusta as regras ao modelo novo;
  - o título da lista vira "2. Perguntas do quiz";
  - o painel de regras do Quiz tem: "Como a criança responde" (dois
    cartões: 👂 Ouvir e achar a figura / 👀 Ver a figura e achar a palavra),
    "Quantas opções em cada pergunta" (2/3/4), "Quando o jogo termina"
    (todas / depois de N perguntas), "Som de acerto e comemoração" e "Ler a
    pergunta em voz alta";
  - no modo `ver`, cada figura ganha "+ opções erradas próprias
    (opcional)", que abre até 3 campos de texto e mostra um resumo
    ("Opções erradas: Pato · Gato").
- **Biblioteca, seletor da missão, lista de jogos:** o ícone ❓ vem de
  `jogoRegistrado(modelo).icone`. O selo continua "🎮 Pandoo".

## 4. Testes

- **Backend (pytest):**
  - criar quiz nos dois modos;
  - recusas: sem imagem; modo `ver` sem texto; modo `ouvir` sem texto nem
    áudio;
  - regras normalizadas (opções fora de 2–4, modo inválido e `perguntas`
    fora da faixa voltam ao padrão);
  - distratores limitados a 3;
  - roleta sem mudança.
- **Node (`pandoo_core.test.js`):**
  - `opcoesDaPergunta` nos dois modos (quantidade, a certa sempre presente,
    sem repetição, distratores próprios primeiro, poucos itens);
  - ordem das perguntas e fim (`todas` / `perguntas` com N maior que os
    itens);
  - resultado "de primeira" versus "treinar";
  - `problemasDoConteudo` do quiz.
- **Navegador (Playwright):**
  - criar um quiz em cada modo e jogar a prévia (errar uma vez e acertar);
  - resumo com "perguntas";
  - missão com quiz: bloqueada, joga, libera;
  - ficha com o resultado por figura;
  - celular.

## 5. Entrega

Um PR, sem migração e sem passo manual além do deploy de sempre (`git pull`
+ restart). Merge automático com o CI verde. Depois do merge, o CLAUDE.md
ganha o Quiz e a pendência passa a ser "Memória".

Fora do escopo: Memória, Associação, Quebra-cabeça e Flashcards (próximos ciclos); voz de
IA; quiz com resposta em imagem no modo `ver`, ou texto livre.
