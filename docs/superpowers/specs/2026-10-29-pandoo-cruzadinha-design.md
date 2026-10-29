# Pandoo fase 2 — Cruzadinha

Data: 29/10/2026 · Status: design aprovado pelo usuário, com prévia jogável
(artifact "Prévia Cruzadinha Pandoo",
https://claude.ai/artifact/TJymr2usZ2s9acUbNe31EK, versão 2).

## Objetivo

Novo jogo do Pandoo, a **Cruzadinha**. O profissional cadastra figuras com
palavra e voz, como nos outros jogos. O PandaUp monta a cruzadinha sozinho,
e a criança descobre as palavras pelas figuras. Ela pode preencher de três
jeitos: digitando no teclado do celular, tocando em letras ou escolhendo a
figura certa (para quem ainda não lê).

Como o Quiz e a Memória, a Cruzadinha reaproveita o que já existe:
- o editor e o palco (cenário, som, voz, placar, "Finalizar jogo" e resumo);
- o resultado por figura na ficha do paciente;
- a Biblioteca e as missões;
- a regra de que a missão só libera com pelo menos uma jogada (aqui, uma
  palavra completa);
- a regra de um jogo por dia na missão (item 5s do CLAUDE.md).

A Cruzadinha não estava na lista da fase 2. Ela entra agora, por pedido do
usuário em 29/10/2026, e a ordem dos outros jogos (Associação,
Quebra-cabeça, Flashcards) não muda.

**Escolhas do Claude, não do usuário**, para conferir:
- até 12 letras por palavra e grade até 15×15;
- a arrumação é guardada no jogo, não sorteada a cada partida;
- na forma `figuras`, a 1ª letra aparece sempre;
- os critérios do gerador da grade (seção 2);
- a 1ª letra (`primeira_letra` e na forma `figuras`) é **só uma pista**
  desenhada bem clarinha. A criança ainda precisa preencher essa casa, que
  entra no banco de letras e no "N letras";
- tocar numa casa que é de outra palavra aberta escolhe essa palavra.
  Tocar numa casa de palavra já feita escolhe a palavra aberta que cruza
  ali; se não houver nenhuma, só fala a palavra feita;
- uma letra pode completar, por tabela, uma palavra cruzada que a criança
  não estava fazendo. Se essa palavra ficar errada, ela **não** balança e
  não leva erro: as letras ficam até a criança escolher essa palavra.
  Quando escolher e mexer numa letra dela, a palavra é conferida
  normalmente. Se ficar certa por tabela, conta como feita;
- ao trocar de forma, as palavras feitas ficam; as letras soltas de
  palavras ainda não feitas são limpas, para cada forma começar a palavra
  do zero;
- se o gerador não conseguir pôr todas as palavras em 15×15, o editor não
  deixa salvar e avisa: "Não deu para montar a cruzadinha com essas
  palavras. Use palavras menores ou tire alguma figura." Nesse caso
  `montarGradeCruzadinha` devolve `null`. O teste de 10 palavras usa
  palavras comuns de até 8 letras.

## Decisões do usuário

- **Três formas de preencher**, e o profissional **libera uma ou mais**:
  - `teclado`: abre o teclado do celular (ou do computador). A criança
    digita, e o cursor anda sozinho pela palavra. Acento e caixa não
    contam: "é" vale "E", "ç" vale "C".
  - `letras`: abaixo da grade aparece um banco com as letras que faltam na
    palavra escolhida e mais 2 letras que não estão nela, embaralhadas. Ao
    tocar na letra certa para o quadradinho da vez, ela entra. Letra errada
    balança e não entra.
  - `figuras`: as figuras das dicas ficam escondidas (❓). A criança toca na
    palavra e escolhe entre 3 figuras (a certa e mais 2 do jogo). Se errar,
    a figura escolhida balança e apaga, e ela escolhe de novo. Se acertar, a
    palavra se escreve sozinha, letra por letra, e é falada.
- Com **mais de uma forma liberada**, a criança troca de forma no alto do
  palco, no meio da partida, **sem perder** as palavras que já fez.
- **De 2 a 10 palavras** por cruzadinha.
- **Palavras com espaço ou hífen entram** ("guarda-chuva", "arco íris"). O
  hífen aparece já escrito num quadradinho próprio. O espaço vira um
  quadradinho vazio, que não se preenche. A criança escreve só as letras.
- **Tocar num quadradinho com número escolhe a palavra que começa nele.** A
  prévia escolhia a palavra anterior, e o usuário apontou como erro. No
  quadradinho em que começam duas palavras (uma deitada e uma em pé), cada
  toque troca entre as duas.
- **Resultado por palavra:** "conseguiu" ⭐ quando sai certa sem nenhum erro
  antes; "treinar" quando teve erro antes. Contam como erro: a palavra
  completa digitada errada, uma letra errada tocada no banco ou uma figura
  errada escolhida.
- **Missão e jogo por dia:** iguais aos outros jogos. A missão só libera com
  pelo menos uma palavra feita, e vale um jogo por dia.
- **Prévia aceita** (o visual a seguir):
  - quadradinhos brancos com o número no canto;
  - a palavra escolhida fica amarelo-clara, e o quadradinho da vez tem borda
    amarela;
  - palavra certa fica verde, com um pulinho, o som de acerto e a voz
    dizendo a palavra;
  - palavra errada: os quadradinhos balançam, as letras erradas saem e as
    certas ficam;
  - as dicas ficam embaixo da grade, como botões com a figura, o número, a
    seta (→ deitada, ↓ em pé) e "N letras". Tocar numa dica escolhe a
    palavra e fala a palavra (exceto na forma `figuras`, em que falar
    entregaria a resposta).

## 1. Conteúdo e regras (backend, `pandoo_service.py`)

Mesmo formato único v1, sem migração. Para a Cruzadinha:

- `pergunta.imagem`: obrigatória, em toda figura.
- `pergunta.texto`: a palavra, obrigatória.
  - Só letras (com acento e ç), hífen e espaço. Espaços repetidos viram um.
  - De 2 a 12 letras, sem contar hífen e espaço. Com 12, a grade ainda cabe
    no celular.
  - Não pode começar nem terminar com hífen ou espaço.
  - As palavras precisam ser **diferentes entre si**, comparadas sem acento
    e sem caixa (`_normalizar_palavra`).
- `pergunta.audio`: voz gravada, opcional. Sem ela, vale a voz do navegador,
  como nos outros jogos.
- `distratores`: não usados, e a Cruzadinha não os guarda.
- **Mínimo e máximo de figuras:** de 2 a 10 (os outros jogos vão até 24).
  `validar_jogo` passa a aceitar um limite por modelo.

`MODELOS` ganha `"cruzadinha"`, `NOME_MODELO["cruzadinha"] = "a cruzadinha"` e
`REGRAS_PADRAO["cruzadinha"]`:

```json
{"formas": ["teclado", "letras"], "primeira_letra": false,
 "som": true, "voz": true, "voz_acertar": true, "grade": null}
```

- `formas`: lista não vazia, sem repetição, só com `teclado`, `letras` e
  `figuras`. É guardada sempre nessa ordem. Valor inválido ou lista vazia
  volta ao padrão.
- `primeira_letra`: mostra a 1ª letra de cada palavra, bem clarinha, no
  primeiro quadradinho. Na forma `figuras` ela aparece sempre, porque é a
  pista para escolher a figura. Ver a seção 2.
- `voz`: falar a palavra ao tocar na dica. `voz_acertar`: falar a palavra ao
  acertar. `som`: som de acerto e de erro.
- `grade`: a arrumação da cruzadinha, gerada no editor e **guardada**, para
  que o jogo não mude de arrumação sozinho de uma partida para outra:

  ```json
  {"linhas": 6, "colunas": 4,
   "palavras": [{"item_id": "a1", "linha": 0, "coluna": 1, "direcao": "v"}]}
  ```

  O backend confere a grade:
  - cada item aparece **exatamente uma vez**;
  - `direcao` é `h` (deitada) ou `v` (em pé);
  - a palavra cabe dentro de `linhas`×`colunas`, com no máximo 15×15;
  - onde duas palavras se cruzam, a letra é a mesma, comparada sem acento e
    sem caixa;
  - nenhum cruzamento cai num hífen ou num espaço.

  Grade ausente, inválida ou que não bate com os itens dá erro: "A
  arrumação da cruzadinha está desatualizada. Toque em 'Montar a
  cruzadinha' de novo." O editor sempre manda a grade, e o jogo nunca a
  inventa na hora.

Mensagens de erro, no padrão das que já existem:
- `Item N: a cruzadinha precisa de uma imagem em cada figura.`
- `Item N: a cruzadinha precisa da palavra de cada figura.`
- `Item N: use só letras, hífen e espaço na palavra da cruzadinha.`
- `Item N: a palavra da cruzadinha precisa ter de 2 a 12 letras.`
- `Item N: a palavra repete a de outra figura.`
- `A cruzadinha precisa ter de 2 a 10 figuras.`

## 2. Regras puras (front, `pandoo_core.js`, testadas em Node)

- `REGRAS_PADRAO_PANDOO.cruzadinha` e `PANDOO_LIMITES` por modelo (2 a 10
  na cruzadinha), espelhos do backend.
- `problemasDoConteudo("cruzadinha", conteudo, regras)`: as mesmas
  checagens do backend, com as mensagens "Figura N: …".
- `casasDaPalavra(texto)`: divide a palavra em casas `{letra, fixa}`, em
  maiúsculas e sem acento. O hífen é casa fixa com "-", e o espaço é casa
  fixa vazia.
- `montarGradeCruzadinha(itens, aleatorio)` devolve a `grade` no formato
  da seção 1.
  - Coloca primeiro as palavras mais longas e tenta cruzar cada nova
    palavra com uma letra igual de uma já colocada.
  - Uma palavra não pode encostar de lado noutra paralela, nem logo antes
    do começo ou depois do fim de outra na mesma direção (regra comum de
    cruzadinha).
  - Entre as arrumações possíveis, prefere a mais compacta e mais perto de
    quadrada, porque é a que fica maior no celular.
  - **Palavra sem letra em comum com as outras** fica solta na grade, num
    canto livre e sem encostar. Ela não some, e o editor avisa: "A palavra
    X não cruza com nenhuma outra; ela vai aparecer separada."
  - Cada chamada com outro `aleatorio` pode dar outra arrumação (botão
    "Sortear outra").
- `numerarGrade(grade, itens)`: o número de cada palavra, em ordem de
  leitura do começo dela (de cima para baixo, da esquerda para a direita).
  Duas palavras que começam no mesmo quadradinho têm o mesmo número.
- `conferirGrade(grade, itens)`: as mesmas checagens do backend. O editor
  usa para saber se a grade guardada ainda vale depois de editar as
  palavras.
- `palavraAoTocar(estado, casa)`: devolve qual palavra fica escolhida ao
  tocar num quadradinho, pela regra das Decisões. Se alguma palavra
  aberta, diferente da escolhida, começa nesse quadradinho, ela é a
  escolhida. Senão, se a escolhida passa pela casa, ela continua. Se não
  passa, vale a palavra aberta que passa pela casa. Tocar de novo na mesma
  casa troca para a outra palavra que passa por ela. Palavras já feitas
  não são escolhidas; a casa de uma palavra feita escolhe a palavra aberta
  que cruza ali, ou devolve "nenhuma", e a tela só fala a palavra feita.
- `estadoInicialCruzadinha(grade, itens)`, `colocarLetraCruzadinha`,
  `apagarLetraCruzadinha` e `conferirPalavrasCruzadinha`: as letras
  colocadas, as casas travadas (palavra certa), os erros por palavra e as
  palavras feitas.
  - Uma letra que completa outra palavra cruzada também a confere. Se ela
    ficar certa, conta como feita, com o resultado pelos erros dela.
  - Palavra errada: devolve as casas a limpar (as letras que não batem e
    não estão travadas) e soma um erro na palavra.
- `bancoDeLetras(palavra, estado, aleatorio)`: as letras das casas ainda
  abertas e mais 2 letras que não estão na palavra, embaralhadas.
- `opcoesFigurasCruzadinha(item, itens, aleatorio)`: a certa e mais 2 do
  jogo, de preferência das palavras ainda não feitas. Com 2 figuras no
  jogo, são 2 opções.
- `cruzadinhaTerminou(estado)`.

## 3. Tela

### O jogo, `frontend/js/pandoo/jogos/cruzadinha.js`

Registrado com
`registrarJogo("cruzadinha", {nome: "Cruzadinha", icone: "🧩", rotuloRodada: ["palavra", "palavras"], avisoSemRodada: "Você ainda não completou nenhuma palavra. Complete pelo menos uma para liberar a missão 🧩", ...})`.

- **Layout dentro de `palco.area`, de cima para baixo:**
  1. a troca de forma (só com mais de uma liberada);
  2. a grade;
  3. a instrução ("Escreva a palavra 🐱", "Toque nas letras de 🐱", "Qual
     figura cabe aqui?");
  4. o banco de letras (só na forma `letras`);
  5. as dicas.
- **Tamanho da grade:** as casas ficam do maior tamanho que cabe na largura
  da área, entre 30 e 64 px. Abaixo de 30, a grade rola dentro dela mesma, e
  a página não rola para os lados.
- **Teclado do celular:** um `<input>` invisível dentro do palco, com
  `autocapitalize="characters"`, `autocorrect="off"`, `autocomplete="off"`,
  `spellcheck="false"` e `font-size` 16 px (no iPhone, menos que isso dá
  zoom). Ele recebe o foco ao escolher uma palavra e ao tocar numa casa.
  - A letra vem do evento `input`; o teclado do Android nem sempre manda
    `keydown` com a letra. O valor é lido, normalizado e o campo esvazia.
  - "Apagar" (Backspace) limpa a casa da vez ou volta uma casa.
  - Quando o teclado abre, a grade e a palavra escolhida continuam à vista:
    acompanhar `visualViewport` e rolar a casa da vez para a área visível.
  - Funciona também com o teclado físico do computador.
- **Voz:** `palco.falarItem(item)` ao escolher uma palavra (se `voz` estiver
  ligada e a forma não for `figuras`). No acerto, a fala vem depois do som,
  sem cortá-lo (`falarItem(item, {cortarSom: false})`), como na Memória.
- **Placar:** "🧩 x de N palavras" e ⭐ (as palavras com "conseguiu").
- **Fim:**
  - Com a última palavra feita, o resumo aparece 1,2 s depois.
  - "Finalizar jogo" segue a regra comum: sem nenhuma palavra feita, fecha
    sem salvar e mostra o `avisoSemRodada`.
  - Só as palavras feitas entram em `palco.registrar`; as abertas não
    contam.
- **Acessibilidade:** casas e dicas são botões com rótulo ("Palavra 2,
  deitada, 4 letras", "Quadradinho vazio", "Letra G"), com contorno de foco
  pelo teclado, e `prefers-reduced-motion` desliga o balanço e o pulinho.

### O editor, `views/pandoo.js`

- Cartão "🧩 Cruzadinha" pronto em `MODELOS_PANDOO_EDITOR`.
- Lista "2. Palavras da cruzadinha", com a dica "De 2 a 10 palavras, cada
  uma com até 12 letras (hífen e espaço não contam). Para cada uma: a
  imagem, a palavra (só letras, hífen ou espaço) e, se quiser, a sua voz."
- **Limites sempre à vista** (pedido do usuário, 29/10/2026):
  - Ao lado do título da lista fica um contador "6 de 10 palavras".
    Chegando a 10, o botão "+ Adicionar figura" fica desativado, com o
    texto "Máximo de 10 palavras".
  - Em cada campo de palavra fica um contador "4 de 12 letras", que conta
    só as letras.
    - Passando de 12, o contador fica vermelho e aparece "Use até 12
      letras".
    - Caractere proibido aparece "Use só letras, hífen e espaço".
    - Em qualquer desses casos o jogo não salva. O campo não corta o
      texto sozinho, para não mudar a palavra sem a pessoa ver.
  - Ao abrir um jogo com mais de 10 figuras vindo de outro modelo, o
    contador fica vermelho ("12 de 10 palavras — tire 2 para salvar").
- Painel de regras (`renderRegras`/`lerRegras`):
  - "Formas de preencher": três caixas (⌨️ Teclado, 🔤 Letras, 🖼️
    Figuras), pelo menos uma marcada, com a nota "Com mais de uma, a
    criança escolhe no jogo.";
  - "Mostrar a 1ª letra de cada palavra";
  - "Falar a palavra ao tocar na figura";
  - "Falar a palavra ao acertar";
  - "Som de acerto e comemoração";
  - **"Arrumação da cruzadinha"**: uma miniatura da grade (só os
    quadradinhos e os números), com o botão "🔀 Sortear outra". A grade é
    montada sozinha quando as palavras mudam e não há grade que ainda valha
    (`conferirGrade`). Mexer só na imagem ou na voz mantém a arrumação. O
    aviso de palavra solta aparece aqui.
- "Pré-visualizar" e salvar usam a grade atual.
- Trocar de modelo continua como nos outros: as figuras ficam, as regras
  voltam ao padrão do modelo novo, guardando só `som` e `voz`. Entrar na
  Cruzadinha com mais de 10 figuras mostra o problema e não deixa salvar
  até tirar figuras.

## 4. Testes

- **Backend** (`tests/test_pandoo_cruzadinha.py`):
  - regras padrão e valores fora do permitido (`formas` vazia, repetida ou
    com valor desconhecido);
  - imagem e palavra obrigatórias;
  - caracteres proibidos, tamanho, hífen ou espaço nas pontas;
  - palavras repetidas (acento e caixa) recusadas;
  - 1 e 11 figuras recusadas;
  - grade: item faltando ou repetido, fora dos limites, cruzamento com
    letra diferente, cruzamento num hífen, grade ausente;
  - acento no cruzamento ("É" × "E") aceito;
  - distratores não guardados;
  - jogo salvo e partida registrada pelas rotas, como nos testes da
    Memória.
- **Node** (`pandoo_core.test.js`):
  - `casasDaPalavra` com hífen, espaço e acento;
  - `montarGradeCruzadinha`: com 2, 6 e 10 palavras, sempre passa em
    `conferirGrade`; palavras sem letra em comum ficam soltas e sem
    encostar; nenhuma palavra encosta de lado;
  - `numerarGrade` com duas palavras começando na mesma casa;
  - `palavraAoTocar`, incluindo o caso do usuário (palavra 2 escolhida,
    tocar no começo da 3 escolhe a 3) e a troca no começo compartilhado;
  - colocar/apagar/conferir: erro limpa só as letras erradas; letra que
    completa a palavra cruzada; "conseguiu" × "treinar";
  - `bancoDeLetras` e `opcoesFigurasCruzadinha`;
  - `problemasDoConteudo("cruzadinha", …)`.
- **Navegador** (Playwright):
  - o editor monta a cruzadinha, sorteia outra e salva;
  - na prévia, as três formas: digitar, errar e acertar; letra errada no
    banco; figura errada e certa;
  - trocar de forma no meio sem perder o que foi feito;
  - celular (390 px): a grade de 10 palavras cabe ou rola só dentro dela, e
    o teclado abre ao tocar numa casa;
  - a missão da criança: sem palavra (não libera), com uma (libera), e no
    mesmo dia fica "encerrado por hoje";
  - a ficha mostra a partida;
  - nenhum erro de JS.

## Fora do escopo

- Dica escrita (frase) em vez da figura.
- Cronômetro, fases e dois jogadores.
- Editar a arrumação à mão (arrastar palavras na grade); só "Sortear outra".
- Mais de 10 palavras.
- Banco de letras com o teclado inteiro (A–Z); são só as letras da palavra
  e mais 2.
