# Pandoo — fase 1: fundação + roleta de figuras

Data: 25/09/2026 · Status: design aprovado pelo usuário em conversa
(prévias em `.superpowers/brainstorm/230-1790306451/content/pandoo-v1..v4.html`,
não versionadas)

## Objetivo

Criar o **Pandoo**, um criador de jogos educativos dentro do Panda Tech. O
profissional digita o conteúdo uma vez; o mesmo conteúdo pode alimentar
vários modelos de jogo. O jogo vira um exercício da Biblioteca e entra nas
missões do paciente; a criança joga no Mundo da Criança e o resultado vai
para a ficha do paciente.

A fase 1 entrega a fundação (formato de conteúdo, editor, catálogo de jogos
plugáveis, palco comum com sons/voz/cenário, resultados, integração com a
missão) e o primeiro modelo: **roleta de figuras**.

Inspiração: mecânicas genéricas de jogos educativos (quiz, roleta, memória).
Nome, identidade visual, arte e layout próprios — nada de marca, layout ou
imagens de terceiros.

## Decisões do usuário

- Nome: **Pandoo**.
- **Módulo pago que não entra em nenhum plano**: o Admin do SaaS libera
  clínica por clínica.
- Sem Biblioteca da Plataforma para jogos (só jogos da própria clínica).
- Sem links públicos de compartilhamento.
- Menu próprio "🎮 Pandoo" + os jogos também aparecem na Biblioteca e no
  seletor de exercícios da "Nova Missão".
- Roleta: depois de cada giro, um adulto toca em **"Conseguiu ⭐"**, **"Vamos
  treinar mais 💪"** ou **"Finalizar jogo"** (encerra a partida).
- Fim da partida escolhido pelo profissional: **"até sair todas as figuras"**
  (padrão, sem repetir) ou **"N giros"**; "Finalizar jogo" encerra antes.
- Missão com jogo: o botão de concluir **só libera depois de jogar** cada jogo
  da missão (na semanal, a cada dia).
- Sons e voz: **recurso comum a todos os jogos**. Voz em camadas: gravação do
  próprio profissional (se houver) > voz do navegador. A leitura começa
  **5 segundos** depois de a figura aparecer; botão "🔊 Ouvir de novo". Voz de
  IA fica para depois.
- **Cenários animados**: 3 prontos (🎋 Bambuzal, 🐠 Fundo do mar, 🚀 Espaço)
  + 🖼️ imagem da clínica com brilhos animados. O gestor escolhe o **padrão da
  clínica** em Configurações; cada jogo pode trocar.
- **Texto legível em qualquer cenário**: textos sobre o cenário (título,
  marca, "Finalizar jogo") ficam sobre uma faixa translúcida, com cor escura
  em cenário claro e branca em cenário escuro. Cenários prontos declaram o
  tom; na imagem da clínica o tom é calculado pelo brilho médio da foto no
  envio.
- Textos da tela: após o giro — "Depois que a criança tentar, é só tocar em
  como foi 💚"; no resumo — "Prontinho! A equipe da clínica já vai ver como
  você foi 💚".

Fora do escopo da fase 1: quiz, memória, associação, flashcards (fase 2,
com motor de arrastar por toque); classificação, complete a frase,
desembaralhar, anagrama (fase 3); voz de IA; relatórios de evolução
gráficos.

## 1. Dados

### Exercício do tipo jogo
Um jogo Pandoo é uma linha em `exercicios` com `tipo = 'jogo'` (valor já
aceito pelo CHECK), mesmos campos de sempre (título, descrição, pasta,
faixa etária, especialidade, tags, `organizacao_id` da clínica — nunca
NULL). Aparece na Biblioteca com selo "🎮 Pandoo", nas pastas, na busca e no
seletor de exercícios da missão. Exercício do tipo jogo **não tem linhas em
`midias_exercicio`** (a exigência de ≥1 mídia vale só para os outros tipos).
Editar/excluir um jogo pela Biblioteca leva ao editor do Pandoo.

### Tabela nova `pandoo_jogos`
| coluna | tipo | nota |
|---|---|---|
| `exercicio_id` | INTEGER PK, FK `exercicios(id)` | 1:1 com o exercício |
| `modelo` | TEXT | `roleta` na fase 1 (lista validada no backend) |
| `conteudo_json` | TEXT | formato único, abaixo |
| `regras_json` | TEXT | regras do modelo |
| `cenario` | TEXT NULL | `bambu`/`mar`/`espaco`/`clinica`; NULL = padrão da clínica |
| `atualizado_em` | TEXT | |

**Formato único do conteúdo (versão 1)**:
```json
{ "versao": 1,
  "itens": [
    { "id": "i1",
      "pergunta":   { "texto": "Rato", "imagem": "<base64>", "audio": "<base64>" },
      "resposta":   { "texto": "", "imagem": null, "audio": null },
      "distratores": [],
      "grupo": null }
  ] }
```
- `id` estável por item (gerado no editor) — é a chave dos resultados.
- A roleta usa `pergunta.imagem` (obrigatória), `pergunta.texto` (palavra,
  opcional) e `pergunta.audio` (voz gravada, opcional). Os outros campos
  existem para os próximos modelos.
- Limites: 2–24 itens; texto ≤ 80 caracteres; imagem ≤ 300 KB depois de
  reduzida no navegador (lado maior 512 px); áudio ≤ 600 KB (≈ 30 s). Tipo
  real conferido por magic bytes (`validacao_arquivo`), só imagem/áudio.

**Regras da roleta** (`regras_json`): `{"fim": "todas" | "giros",
"giros": 10, "mostrar_palavra": true, "som": true, "voz": true}`.

### Tabela nova `pandoo_resultados` (uma linha por partida)
`id`, `organizacao_id`, `paciente_id`, `exercicio_id`, `missao_id` NULL,
`atividade_id` NULL, `modelo`, `iniciado_em`, `finalizado_em`,
`encerrado_antes` (0/1 — "Finalizar jogo"), `total_rodadas`, `acertos`
(conseguiu), `a_treinar`, `detalhes_json` (lista `{item_id, texto,
resultado: "conseguiu"|"treinar"}` na ordem sorteada), `usuario_id` (quem
estava logado), `data_local` (YYYY-MM-DD do dia da partida, para a missão
semanal). Índices por `paciente_id` e por `missao_id, data_local`.

### Clínica
Em `organizacoes`: `pandoo_cenario_padrao TEXT DEFAULT 'bambu'`,
`pandoo_cenario_imagem TEXT` (base64, ≤ 800 KB), `pandoo_cenario_tom TEXT`
(`claro`/`escuro`, calculado no navegador no envio e validado no backend).

### Módulo liberado pelo Admin
- `pandoo` entra em `MODULOS_OPCIONAIS` e **em nenhum** `MODULOS_POR_PLANO`.
- `modulos_clinica` ganha `liberado_admin INTEGER DEFAULT 0`.
- `modulos_habilitados_clinica` passa a incluir módulos de uma lista
  `MODULOS_SO_ADMIN = {"pandoo"}` quando a linha da clínica tem
  `liberado_admin = 1` e `habilitado = 1` — independente do plano.
- Rota nova do Admin: `PUT /api/admin/clinicas/<id>/modulos/pandoo`
  `{liberado: true|false}` + interruptor no detalhe da clínica (tela do
  Admin). O gestor **não** consegue ligar o Pandoo sozinho (a rota de
  módulos da clínica recusa módulos `MODULOS_SO_ADMIN` sem
  `liberado_admin`).
- Módulo desligado: menu Pandoo, editor e rotas de criação/edição somem (403).
  **Jogos já colocados em missões continuam jogáveis** e salvando resultado,
  para não quebrar a rotina do paciente.

### Migração
`backend/migracoes/migracao_pandoo.sql` (idempotente: `CREATE TABLE IF NOT
EXISTS`, `ADD COLUMN IF NOT EXISTS`) + `backend/migrar_pandoo.py`, `schema.sql`
e `schema_postgres.sql`, passo no `db-setup.yml` e no smoke Postgres do
`tests.yml`.

## 2. API (backend)

Blueprint novo `pandoo_bp.py` (`/api/pandoo`), com checagem de módulo nas
rotas de criação/edição:
- `GET /jogos` — jogos da clínica (para a lista do menu Pandoo).
- `GET /jogos/<exercicio_id>` — jogo completo (conteúdo, regras, cenário
  efetivo). Acesso: quem pode ver o exercício na Biblioteca **ou** o
  responsável de um paciente que tem esse jogo numa missão (mesma regra de
  hoje para exercícios de missão).
- `POST /jogos` — cria exercício (`tipo='jogo'`) + `pandoo_jogos`, numa
  transação lógica. `PUT /jogos/<id>` — edita. Validação do conteúdo pelo
  modelo (requisitos da roleta: 2–24 itens, cada um com imagem).
- `POST /resultados` — salva partida. Checa que o paciente é acessível ao
  usuário (responsável do paciente, ou profissional/gestor da clínica), que
  o exercício é da mesma clínica, e — se vier `missao_id`/`atividade_id` —
  que a atividade é daquela missão, daquele paciente, com aquele exercício.
  Números recalculados no backend a partir de `detalhes_json`.
- `GET /resultados?paciente_id=` — partidas do paciente (profissional/gestor
  da clínica), com resumo por item.
- Configurações da clínica: `PUT /pessoas/organizacao` passa a aceitar
  `pandoo_cenario_padrao`, `pandoo_cenario_imagem`, `pandoo_cenario_tom`.

Missão:
- `POST /jornada/missao/<id>/concluir` e `/concluir-dia` recusam (409, com
  mensagem amigável) se alguma atividade da missão é um jogo sem partida
  salva **naquela missão** (diária: desde `iniciada_em`; semanal: com
  `data_local` = hoje).
- `GET /jornada/...` que alimenta o Mundo da Criança informa, por atividade
  de jogo, se já foi jogada hoje/nesta missão.

## 3. Front-end

Pasta nova `frontend/js/pandoo/` (scripts comuns, carregados no
`index.html` antes das views):
- `pandoo_core.js` — `registrarJogo(codigo, {nome, icone, requisitos,
  iniciar})`, catálogo, `validarConteudo`, helpers puros (ex.: sorteio sem
  repetição, fim de partida, montagem do resultado).
- `pandoo_som.js` — sons sintetizados (Web Audio: giro, conseguiu, treinar,
  final), voz: gravação do item > `speechSynthesis` pt-BR (velocidade 0,85),
  atraso de 5 s, "Ouvir de novo", botão liga/desliga. Comum a todos os jogos.
- `pandoo_cenarios.js` — os 4 cenários animados (CSS puro) e o tom
  claro/escuro; cálculo de brilho médio de imagem (canvas) para o envio.
- `pandoo_palco.js` — tela cheia comum a todos os modelos: cenário, marca,
  título, placar, som, "Finalizar jogo", resumo com troféu e confete, envio
  do resultado. Modo **prévia** (editor) não salva resultado.
- `jogos/roleta.js` — a roleta (SVG com as imagens nas fatias, giro com
  desaceleração, figura em destaque, três botões).
- Contrato de um jogo: `iniciar(palco, conteudo, regras)`; o palco oferece
  `palco.area`, `palco.som`, `palco.voz.falar(item)`,
  `palco.registrar(itemId, resultado)`, `palco.finalizar({encerradoAntes})`.
  Novo modelo = novo arquivo em `jogos/` + `registrarJogo`.
- CSS em `frontend/css/pandoo.css`. Cores próprias (bambu `#34B36B`, amora
  `#FF5C8A`, sol `#FFC93C`, céu `#4DB8FF`, uva `#8B5FBF`, laranja `#FF8A3D`),
  fonte Fredoka, panda próprio em SVG.

Telas:
- **Menu "🎮 Pandoo"** (gestor e profissional, com módulo ativo): lista de
  jogos da clínica + "Novo jogo".
- **Editor** (`views/pandoo.js`): título; modelo (roleta ativa, os outros
  "em breve"); lista de figuras (imagem, palavra, gravar voz / enviar áudio,
  remover, reordenar); regras; cenário (padrão da clínica ou outro); pasta
  da Biblioteca; "Pré-visualizar" (joga de verdade, sem salvar) e "Salvar".
- **Biblioteca**: cartão com selo "🎮 Pandoo"; abrir → detalhe com "Jogar
  (prévia)" e "Editar no Pandoo".
- **Configurações (gestor)**: card "Cenário do Pandoo" — escolher padrão ou
  enviar imagem própria (reduzida no navegador; tom calculado).
- **Admin**: interruptor "Pandoo" no detalhe da clínica.
- **Mundo da Criança**: atividade de jogo vira cartão "🎮 Jogar <título>";
  abre o palco em tela cheia; ao terminar, volta à missão com a atividade
  marcada como jogada. Botão de concluir (diária) / "Marquei hoje!"
  (semanal) desabilitado com a dica "Jogue o jogo para liberar 🎮" até todas
  as atividades de jogo terem partida. Depois de marcado, o jogo continua
  disponível ("Jogar de novo") e as partidas extras também são salvas.
- **Prévia da missão do responsável**: mostra "🎮 <título do jogo>".
- **Ficha do paciente**: seção "🎮 Pandoo" — últimas partidas (data, jogo,
  ⭐ conseguiu, 💪 treinar, "encerrado antes") e, por jogo, resumo por figura
  ("Rato 4 de 5").

## 4. Segurança e privacidade

- Todo texto do conteúdo é escapado ao renderizar; imagens/áudios só como
  `data:` validados por magic bytes (CSP já permite `img-src`/`media-src
  data:`); nenhum script externo.
- Isolamento por clínica em todas as rotas (jogo, resultado, missão).
- Gravação de voz usa `MediaRecorder` (exige HTTPS — produção já tem;
  localhost também funciona).
- Resultado só guarda o que a criança fez no jogo; nenhum dado novo do
  paciente.

## 5. Testes

- Backend (pytest): módulo só-Admin (gestor não liga; Admin liga/desliga;
  plano não interfere); CRUD de jogo com validação do conteúdo e limites;
  isolamento entre clínicas (jogo, resultados); salvar resultado com
  missão/atividade coerentes e recálculo dos números; bloqueio de concluir
  missão diária/semanal sem partida e liberação depois; jogo segue jogável
  com módulo desligado; Configurações do cenário.
- Front-end (`node --test`): `validarConteudo`, sorteio sem repetição, fim
  por "todas"/"N giros"/"Finalizar", montagem do resultado, cálculo de tom.
- Navegador (Playwright): criar jogo com imagens, prévia, colocar em missão
  diária e semanal, jogar como responsável/criança, bloqueio e liberação do
  botão, ficha do paciente, cenário da clínica claro/escuro, celular.

## 6. Entrega

Dois PRs, ambos com mudança de schema (perguntar antes do merge; migração
no Supabase antes do `git pull`):
- **PR A — backend**: schema/migração, módulo só-Admin, `pandoo_bp`, regras
  na missão, Configurações, testes.
- **PR B — front-end**: pasta `pandoo/`, editor, palco, roleta, Biblioteca,
  Mundo da Criança, ficha, Configurações, Admin, testes Node e Playwright.
