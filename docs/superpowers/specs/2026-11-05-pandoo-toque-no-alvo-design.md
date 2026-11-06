# Pandoo — "Toque só no alvo"

Data: 05/11/2026 · Status: rascunho para aprovação do usuário. Prévia das três
fases em `.superpowers/brainstorm/1456-1793832549/content/alvo-layout.html`
(não versionada).

## Por que existe

Até agora o Pandoo foi pensado para a fonoaudiologia (palavra, som, voz). As
clínicas que entram no período de teste incluem **psicologia** e **terapia
ocupacional** infantil, muitas atendendo crianças com **TDAH**. O usuário quer
deixar modelos de jogo prontos para essas áreas desde o lançamento e ajustar
com os profissionais durante o teste (ele ainda não apresentou o sistema a
eles; "vou ter certeza assim que tivermos o modelo para visualizar e testar").

Pesquisa feita na conversa (04/11/2026): o trabalho com TDAH gira em torno de
atenção, memória de curto prazo, controle do impulso, flexibilidade e
planejamento; os estudos de treino no computador mostram ganho no que foi
treinado e melhora relatada pelos pais, com efeito menor na escola. O Pandoo
é **ferramenta da sessão e da tarefa de casa, não tratamento** — nenhum texto
da tela deve prometer melhora de sintomas.

Primeira leva combinada com o usuário, um jogo por vez, **na frente** da
Associação, do Quebra-cabeça e dos Flashcards:
1. **Toque só no alvo** (esta spec) — controle do impulso e atenção mantida.
2. Sequência de memória — memória de curto prazo.
3. Caça-figura — atenção seletiva e percepção visual (psicologia e TO).
Depois: "Separar por grupo" (flexibilidade, troca de regra) junto com a
Associação, que usa o mesmo arrastar com toque; "Qual é a sombra?" como opção
do Caça-figura.

O jogo é de gênero comum (tarefa do tipo "vai/não vai" usada em clínica), com
as figuras da própria clínica — não copia nenhum jogo existente.

## Como funciona (decisões do usuário)

- **Figuras aparecem, a criança toca só na figura-alvo** e segura nas outras.
- **Três fases, uma evolução da outra** (o usuário pediu as três, "como se
  fosse uma evolução do outro"):
  1. **Uma de cada vez** — uma figura grande no meio da tela, some sozinha.
  2. **Saindo das tocas** — grade de tocas (3×2); figuras surgem e voltam a
     se esconder, até 2 ao mesmo tempo.
  3. **Passando pela tela** — figuras atravessam a área de jogo, várias ao
     mesmo tempo.
  (Ordem por dificuldade proposta por Claude e não contestada: lugar fixo é
  mais fácil de vigiar que figura em movimento.)
- **Passagem de fase: as duas opções** (pedido do usuário). No editor:
  "Começar na fase" (1–3), "Ir até a fase" (≥ início) e "Subir de fase
  sozinho" (liga/desliga).
- **Fim por quantidade de figuras** (escolha do usuário, contra "por tempo"):
  cada fase mostra um número fixo de figuras; a partida acaba ao terminar a
  última fase que a criança jogar, ou em "Finalizar jogo".
- **Ao abrir, a voz diz o alvo** (pedido do usuário: "para que a criança
  entenda melhor"): antes da primeira figura, o modelo aparece grande no
  meio e a voz diz a frase de comando ("Toque só no cachorro!").
- **Na ficha, por partida**: alvos tocados, alvos perdidos (distração),
  toques errados (impulso), tempo médio para reagir e a fase alcançada.
  O usuário aceitou "por enquanto" — revisar com os profissionais no teste.

## 1. Conteúdo e regras (backend, `pandoo_service.py`)

Código do modelo: **`alvo`**. Nome na tela: **"Toque só no alvo"**, ícone 🎯.
Sem migração (resultado vai em `detalhes_json`, como os outros jogos).

**Itens**: de 2 a 24 figuras (limite padrão). `pergunta.imagem` obrigatória em
todas. Uma delas é o alvo; as outras são as "pegadinhas".

`REGRAS_PADRAO["alvo"]`:
```json
{"alvo_item_id": null, "frase_inicio": "Toque só no", "fase_inicio": 1,
 "fase_fim": 3, "subir_sozinho": true, "figuras_por_fase": 20,
 "velocidade": "media", "som": true}
```
**Sem a chave `voz`** (decisão de Claude): o comando falado é o pedido central
do usuário, então é **sempre** falado (abertura, troca de fase e toque no
modelo). Por isso o alvo sempre precisa de palavra ou gravação. Se o navegador
não tiver voz, a frase escrita e o botão "Começar" bastam. `som` continua
ligando/desligando os sons de acerto e "quase".
- `alvo_item_id`: id de um item do jogo — obrigatório; inexistente → 400
  ("Escolha qual figura é o alvo.").
- O **alvo** precisa de palavra (`pergunta.texto`) ou voz gravada
  (`pergunta.audio`), porque ela é dita no comando. As pegadinhas não precisam.
- `frase_inicio`: texto até 40 caracteres, antes da palavra do alvo. Existe
  por causa do artigo ("Toque só **na** bola"); vazio volta ao padrão.
- `fase_inicio` e `fase_fim` ∈ {1, 2, 3}, com `fase_fim ≥ fase_inicio`
  (senão `fase_fim = fase_inicio`).
- `figuras_por_fase` entre 10 e 60.
- `velocidade` ∈ {`lenta`, `media`, `rapida`}.
- Inválidos voltam ao padrão, como nos outros modelos. Entra em `MODELOS`,
  `REGRAS_PADRAO`, `NOME_MODELO` ("o toque só no alvo" ou equivalente legível
  nas mensagens).

**Resultado** — mesmo `POST /pandoo/resultados`. Cada figura que apareceu é
um detalhe:
```json
{"item_id": "...", "texto": "...", "resultado": "conseguiu|treinar",
 "alvo": true, "tocou": true, "fase": 1, "tempo_ms": 640}
```
Mapeamento (mantém `calcular_resultado`, a regra da missão e o "um jogo por
dia" funcionando sem mudança de conceito):
| | tocou | não tocou |
|---|---|---|
| alvo | conseguiu (acerto) | treinar (alvo perdido) |
| pegadinha | treinar (toque errado) | conseguiu (segurou) |

`calcular_resultado` passa a aceitar, **só para o modelo `alvo`**, os campos
`alvo` (bool), `tocou` (bool), `fase` (1–3) e `tempo_ms` (inteiro 0–10000,
só quando alvo tocado), descartando o resto como hoje; e confere que
`resultado` bate com a tabela acima (o navegador não decide). Hoje ele não
recebe o modelo: passar o modelo do jogo (já conhecido na rota).
`MAX_RODADAS` (500) já cobre 3 × 60.

**O que conta como "jogou"** (decisão de Claude, seguindo a regra do usuário
de 26/09 — "missão só libera com pelo menos um giro", ou seja, uma ação da
criança): no `alvo`, figuras passando sem nenhum toque **não** contam. A
partida conta como jogada só com **pelo menos um toque** (em alvo ou
pegadinha). Consequências:
- `calcular_resultado` devolve, para o `alvo`, `total_rodadas` = número de
  figuras **tocadas** (os detalhes continuam guardando todas as figuras, para
  as medidas); assim `_jogo_jogado`, `jogou_hoje` e o 409 do "um jogo por dia"
  continuam olhando `total_rodadas > 0` sem mudança.
- No palco, "Finalizar jogo" sem nenhum toque (inclusive durante a abertura,
  antes da primeira figura) fecha direto, sem resumo e sem salvar, com o
  `avisoSemRodada` do jogo — o mesmo caminho de hoje. Precisa de um jeito de o
  jogo dizer ao palco que "ainda não houve jogada" mesmo com detalhes
  registrados (ex.: o palco perguntar ao jogo, ou o jogo só entregar os
  detalhes no fim) — escolha do construtor.

O servidor confere `alvo` de cada detalhe pelo `alvo_item_id` das regras do
jogo (não confia no navegador).

`GET /pandoo/resultados` devolve, para partidas do `alvo`, um bloco
`medidas` calculado dos detalhes: `alvos_tocados`, `alvos_total`,
`alvos_perdidos`, `toques_errados`, `tempo_medio_ms` (média dos alvos
tocados; nulo se nenhum), `fase_alcancada` (maior `fase` nos detalhes).

## 2. Regras puras (front, testadas em Node)

Arquivo próprio ao lado de `pandoo_core.js` (como `cruzadinha_core.js`):
`frontend/js/pandoo/alvo_core.js`, carregado no `index.html` depois do core.

- `sortearFiguras(itens, alvoId, quantidade, aleatorio)`: lista da fase com
  **cerca de 1 alvo a cada 3** (arredondado; pelo menos 1), pegadinhas
  sorteadas das outras figuras, sem 3 alvos seguidos e sem começar por
  alvo. Recebe o gerador de aleatório para teste.
- `avaliarFase(detalhesDaFase)`: passou se tocou ≥ 80% dos alvos **e** teve
  no máximo 1 toque errado.
- `proximaFase(estado)`: com `subir_sozinho` desligado, joga todas as fases de
  `fase_inicio` a `fase_fim`, em ordem, independentemente do desempenho; com
  ele ligado, só avança se `avaliarFase` passar — senão a partida termina ali
  (duração previsível; não repete fase).
- `medidasDaPartida(detalhes)`: mesmas medidas do backend (o resumo da tela e
  a ficha usam).
- Tempos por velocidade (sugestão, ajustar no teste): fase 1 — figura na tela
  2,0 / 1,5 / 1,0 s, intervalo 0,6 s; fase 2 — figura fora da toca 2,2 / 1,7 /
  1,2 s; fase 3 — travessia 4,5 / 3,5 / 2,5 s.

## 3. Jogo (`frontend/js/pandoo/jogos/alvo.js`)

`registrarJogo("alvo", {nome: "Toque só no alvo", icone: "🎯", ...})`.

- **Abertura**: alvo grande no centro + frase escrita
  ("Toque só no 🐶" com a imagem); a voz fala `frase_inicio` pelo navegador e
  em seguida a palavra — a gravação do alvo se houver, senão a palavra pelo
  navegador. Botão "Começar" (ou começa sozinho depois da fala) — decisão do
  construtor, desde que a criança não perca as primeiras figuras.
- **Modelo fixo no topo** da área de jogo ("Toque só no 🐶"); tocar nele
  repete a fala. Barra de progresso da fase (figuras que faltam).
- **Toque no alvo**: som de acerto + figura "estoura". **Toque na pegadinha**:
  balanço curto + som de "quase"; nada de placar negativo à vista. **Alvo que
  some sem toque**: só contado, sem som. Uma figura só conta o primeiro toque.
- **Troca de fase**: aviso "Fase 2!" e a fala do comando de novo.
- Placar do palco: ⭐ = alvos tocados.
- Respeitar `prefers-reduced-motion` na fase 3 é desejável, não obrigatório.

## 4. Palco, resumo e ficha

- **Resumo do fim**: o resumo atual conta "conseguiu" e mostra miniaturas por
  figura — aqui não faz sentido (pegadinha segurada viraria ⭐). O jogo
  fornece um resumo próprio: "Você pegou 14 de 18 🐶!" e a fase alcançada.
  Pode exigir um gancho novo no palco (ex.: `def.resumo(detalhes)`).
- `rotuloRodada`: ["figura", "figuras"]; `avisoSemRodada` próprio.
- **Ficha do paciente**: para jogos `alvo`, em vez do desempenho "por
  figura", uma linha por partida com data, fase alcançada, alvos tocados /
  total, alvos perdidos, toques errados e tempo médio (em segundos, 1 casa).
- **Editor** (`views/pandoo.js`): cartão do modelo com `pronto: true`; painel
  de regras com: qual figura é o alvo (escolher entre as figuras cadastradas),
  frase do comando, começar na fase / ir até a fase, subir sozinho, figuras
  por fase, velocidade e som. Pré-visualizar usa o palco em modo `previa`.

## Fora do escopo

- Trocar o alvo no meio da partida (é o "Separar por grupo").
- Relatório/gráfico de evolução além da lista de partidas na ficha.
- Ajuste automático de velocidade dentro da fase.
- Textos de marketing sobre TDAH.

## Decisões tomadas por Claude (o usuário pode revisar)

- Ordem das fases 1 → tocas → passando.
- Regra de subida (≥ 80% dos alvos e ≤ 1 toque errado) e, com subida
  automática, a partida termina na fase em que a criança não passou.
- 1 alvo a cada ~3 figuras; 20 figuras por fase como padrão; 3 velocidades.
- Alvo fixo na partida inteira.
- Toque errado sem castigo visível; alvo perdido sem som.
- `frase_inicio` editável por causa do artigo (no/na).
- Mapeamento conseguiu/treinar da tabela da seção 1.
- Partida sem nenhum toque não conta como jogada (não libera a missão, não
  trava o dia).
- O comando é sempre falado; o jogo não tem a chave "voz".
