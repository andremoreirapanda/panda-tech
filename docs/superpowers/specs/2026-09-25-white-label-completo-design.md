# White Label completo (módulo "Identidade Visual Própria")

Data: 25/09/2026 · Status: design aprovado pelo usuário por prévias
(`.superpowers/brainstorm/490-1790374652/content/white-label-v1..v3.html`, não
versionadas).

## Objetivo

Transformar o módulo `white_label` (hoje só um nome na lista, sem trava
nenhuma) em uma personalização de verdade. A clínica com o módulo muda:
cores e nomes da gamificação (como hoje, só que agora travados pelo módulo),
**nome e ícone do app**, uma **tela de login própria** e o **Mundo da
Criança** (fonte, fundo animado, mascote padrão e texto da comemoração).

## Decisões do usuário

- **Com o módulo**, valem os valores da clínica. **Sem o módulo**, valem os
  padrões Panda Tech, mas o que a clínica salvou fica guardado e volta se o
  módulo for ligado de novo.
- **Travados pelo módulo**: cor primária e secundária; nomes do assistente,
  da moeda e da medalha; nome e ícone do app; tela de login própria; Mundo da
  Criança.
- **Livres para todas as clínicas**: logo e nome da clínica, como hoje.
- **Tela de login da clínica** em `#/entrar/<endereço>`, com logo, cores,
  mascote e uma mensagem de boas-vindas. O rodapé "tecnologia Panda Tech"
  continua.
- **Mundo da Criança**:
  - fonte dos títulos: 4 opções em cartões (Fredoka, Baloo, Nunito, Escolar);
  - fundo: os cenários animados do Pandoo, mais o fundo atual de estrelinhas
    e a opção "Igual ao Pandoo";
  - mascote padrão: emoji da lista ou imagem da clínica;
  - texto da comemoração: até 40 caracteres.
  - As animações de hoje continuam (mascote flutuando e confete).
- Tudo é escolhido por controles (cartões, amostras, envio de imagem). Não há
  texto livre para fonte ou cor.

## Efeito nas clínicas em produção (atenção)

Hoje qualquer clínica troca as cores e os nomes em Configurações. Com a trava,
**clínicas sem o módulo voltam a ver as cores e os nomes padrão** (roxo
`#5B4FE9`/laranja `#FFB84D`, "Lumi", "XP", "Medalha"). Os valores delas ficam
guardados. O Admin pode liberar o módulo como extra (detalhe da clínica →
"Módulos da clínica") para qualquer clínica que já personalizou.

## 1. Dados

Novas colunas em `organizacoes`, todas opcionais. NULL significa padrão.

| Coluna | Valor | Padrão |
|---|---|---|
| `endereco_login` | slug `[a-z0-9-]`, 3–40 caracteres, único | gerado do nome da clínica |
| `app_nome` | texto ≤ 30 | "Panda Tech" |
| `app_icone_base64` | PNG/JPG/WebP quadrado, ≤ 500 KB | 🐼 |
| `login_mensagem` | texto ≤ 120 | "Entre com sua conta para continuar a jornada." |
| `mundo_fonte` | `fredoka` \| `baloo` \| `nunito` \| `escolar` | `fredoka` |
| `mundo_fundo` | `estrelas` \| `bambu` \| `mar` \| `espaco` \| `clinica` \| `pandoo` | `estrelas` |
| `mundo_mascote` | emoji de `MASCOTES_VALIDOS` ou `clinica` | 🐻 |
| `mundo_mascote_imagem` | PNG/JPG/WebP quadrado, ≤ 500 KB | — |
| `mundo_comemoracao` | texto ≤ 40 | "Muito bem!!" |

- **Imagem do fundo "clinica"**: é a mesma imagem de cenário do Pandoo
  (`pandoo_cenario_imagem` e `pandoo_cenario_tom`, que já existem). Assim a
  clínica envia uma foto só, que serve para as duas telas. O envio aparece
  nas duas configurações.
- **`mundo_fundo = pandoo`** usa o cenário padrão dos jogos da clínica
  (`pandoo_cenario_padrao`, e a imagem se esse cenário for `clinica`).
- **`endereco_login`**:
  - clínica nova: gerado na criação;
  - clínica existente: gerado na primeira leitura de `GET /pessoas/organizacao`.
  - O slug sai do nome da clínica, sem acento, com sufixo `-2`, `-3`… se
    repetir. É a mesma lógica do `_slug_plano`, que passa para um helper
    comum.
  - O gestor pode editar; o backend valida o formato e a unicidade.
- Migração: `backend/migracoes/migracao_white_label.sql` e
  `backend/migrar_white_label.py`. Só `ADD COLUMN`, idempotente, com índice
  único parcial em `endereco_login`. Os seeds preenchem a clínica de
  demonstração, que já está no plano Enterprise e, portanto, tem o módulo.

## 2. Regras (backend)

Arquivo novo **`backend/identidade_service.py`**, com uma só fonte da regra:

- `PADROES`: os valores padrão da tabela acima, mais cores e nomes.
- `identidade_efetiva(org, modulo_ativo) -> dict`: com o módulo, os valores
  da clínica, com NULL virando o padrão; sem o módulo, os `PADROES`. `nome`,
  `logo_emoji` e `logo_base64` passam sempre.
- Validações: `validar_endereco_login`, `validar_textos_identidade`
  (tamanhos, sem `<`/`>`), `validar_opcao` (fonte e fundo) e
  `validar_imagem_quadrada_pequena` (assinatura de imagem, ≤ 500 KB).

Onde a regra entra:

- **`/auth/me` e login** (`_org_com_modulos`): a `organizacao` devolvida
  passa a ser a identidade efetiva. Todo o front-end (tema, `nomeMoeda()`,
  Mundo da Criança) passa a respeitar a trava sem mudar cada tela.
- **`GET /pessoas/organizacao`** (tela de Configurações): devolve os valores
  **guardados** (para editar), mais `white_label_ativo: bool` e
  `endereco_login`. As imagens grandes continuam só aqui.
- **`PUT /pessoas/organizacao`**:
  - aceita os campos novos, validados;
  - só mexe no que vier no corpo, como já é feito com horário e cenário;
  - salva mesmo sem o módulo: fica guardado, mas não vale;
  - erros de validação → 400, inclusive `mundo_fundo = clinica` sem imagem de
    cenário e `mundo_mascote = clinica` sem imagem de mascote;
  - `endereco_login` repetido → 409.
- **Público, sem login** (`blueprints/publico_bp.py`, prefixo
  `/api/publico`):
  - `GET /clinica/<endereco>`: nome, logo, cores, `app_nome`,
    `login_mensagem`, mascote (emoji ou `tem_mascote_imagem`) e
    `tem_icone`. Devolve **404** se o endereço não existir, se a clínica
    estiver inativa ou cancelada, ou se o White Label estiver desligado.
    Nunca devolve dado comercial ou de pacientes.
  - `GET /clinica/<endereco>/icone`: o PNG/JPG/WebP do ícone, com o
    `Content-Type` certo e cache de 1 dia. Serve para favicon,
    `apple-touch-icon` e manifest. Mesmas regras de 404.
  - `GET /clinica/<endereco>/mascote`: a imagem do mascote da clínica. Mesmas
    regras de 404.
  - `GET /clinica/<endereco>/manifest.webmanifest`: `name` e `short_name`
    iguais a `app_nome`, ícone da rota acima, `start_url`
    `/#/entrar/<endereco>`, `display: standalone`, `theme_color` igual à cor
    primária.
- **Mascote padrão**:
  - O `criar_paciente_core` usa o mascote da clínica quando o cadastro não
    escolhe um, em vez do 🐻 fixo, se o White Label estiver ativo. O cadastro
    de paciente já vem com o mascote da clínica pré-selecionado.
  - `avatar_mascote = "clinica"` significa "imagem da clínica". Só é aceito
    se a clínica tiver a imagem e o módulo. Sem o módulo, o front mostra 🐻.
  - O responsável troca o mascote do filho como hoje; `clinica` entra na
    lista dele quando existir.
  - Pacientes já cadastrados não mudam.
- **Módulo**: `modulo_ativo_para_clinica(org_id, "white_label")`, a checagem
  que já existe. A descrição do módulo em `MODULOS_OPCIONAIS` é atualizada
  para citar app, login e Mundo da Criança.

## 3. Front-end

Arquivo novo **`frontend/js/cenarios_animados.js`**, com as funções que
desenham os cenários (vindas da prévia do Pandoo):

- `montarCenarioAnimado(elemento, {tipo, imagem, tom}) -> tom`;
- `cenarioDoMundo(org) -> {tipo, imagem, tom}` (resolve `pandoo` e
  `clinica`), uma função pura testada em Node.

**Esta entrega cria o arquivo; o PR B do Pandoo passa a reusá-lo.** O plano
do PR B troca o `pandoo_cenarios.js` próprio por este.

- **Tema** (`util.js`):
  - `aplicarTemaClinica` também aplica `--fonte-crianca`;
  - `document.title`, favicon, `apple-touch-icon`,
    `apple-mobile-web-app-title` e `<link rel="manifest">` passam a apontar
    para as rotas públicas quando `app_nome` ou o ícone existem; senão, voltam
    ao padrão.
  - As fontes Baloo 2, Nunito e Patrick Hand são carregadas **sob demanda**,
    por um `<link>` do Google Fonts injetado só quando a clínica usa. A CSP já
    permite.
- **Mundo da Criança** (`crianca.js` + `layout.css`):
  - o `.shell-crianca` ganha a camada de cenário por trás do conteúdo;
  - "estrelas" é o fundo atual, sem mudança visual;
  - nos cenários escuros, o texto que fica direto sobre o fundo (saudação,
    subtítulo, títulos de seção) usa branco com pílula translúcida; os
    cartões continuam brancos;
  - títulos com `var(--fonte-crianca)`;
  - `mostrarCelebracao` usa `mundo_comemoracao`;
  - o `svgMascote` aceita a imagem da clínica quando `avatar_mascote ===
    "clinica"`;
  - `prefers-reduced-motion` desliga as animações do cenário.
- **Login da clínica** (`login.js` + `router.js`):
  - rota pública `#/entrar/<endereco>`;
  - busca `/api/publico/clinica/<endereco>`; com 404, cai no login normal,
    sem mensagem de erro;
  - mesmo formulário, com o painel da esquerda nas cores da clínica: logo,
    mascote, nome e mensagem, e o rodapé "tecnologia Panda Tech";
  - depois do login, o endereço fica guardado no `localStorage`
    (try/catch), e o "Sair" volta para `#/entrar/<endereco>`.
- **Configurações** (`financeiro.js`, card de identidade atual):
  - cores e nomes continuam onde estão e ganham a trava;
  - entram três grupos: **Aplicativo** (nome e ícone), **Tela de login**
    (endereço com botão "Copiar link", mensagem e prévia) e **Mundo da
    Criança** (cartões de fonte, cartões de fundo, grade de mascotes com
    envio de imagem, texto da comemoração);
  - **sem o módulo**: os grupos aparecem desabilitados, com o selo "Identidade
    Visual Própria" e o aviso "Disponível com o módulo… fale com a Panda Tech".
- **Onboarding**: o passo de identidade só mostra as cores se o módulo estiver
  ativo.
- **Envios**: perfil novo `icone` em `PERFIS_ENVIO` (512 px quadrado, mantém
  transparência, ≤ 500 KB, "📐 PNG com fundo transparente, JPG ou WebP ·
  ideal 512 × 512 px · até 15 MB"), usado no ícone e no mascote. A imagem de
  cenário usa o perfil de cenário (1600 px); se o PR B ainda não existir, o
  perfil `cenario` nasce aqui.

## 4. Testes

**Backend (pytest)**:
- identidade efetiva com e sem o módulo, e ligar/desligar sem perder os
  valores;
- `/auth/me` devolve os padrões sem o módulo;
- PUT valida cada campo (tamanhos, opções, imagem, slug inválido → 400, slug
  repetido → 409);
- slug gerado na criação e na primeira leitura, sem repetir;
- rotas públicas:
  - 404 sem módulo, inativa, cancelada ou endereço inexistente;
  - não vazam campos comerciais;
  - ícone e mascote com `Content-Type` certo;
  - manifest válido;
- mascote padrão em paciente novo, e `clinica` recusado sem imagem ou sem
  módulo;
- a migração é idempotente.

**Node**: `cenarioDoMundo` (todos os tipos, `pandoo` seguindo o padrão dos
jogos, `clinica` sem imagem caindo para estrelas) e o perfil `icone`.

**Playwright**:
- gestor com o módulo personaliza e vê o Mundo mudar;
- gestor sem o módulo vê os campos travados e as cores padrão;
- `#/entrar/<endereco>` mostra a clínica e, depois do "Sair", volta para lá;
- título e favicon trocados.

## 5. Entrega

Um PR com migração: **no Supabase, antes do `git pull`**, porque o login lê
as colunas novas. Como mexe em schema e muda o visual de clínicas em
produção, **perguntar ao usuário antes do merge**. Depois do merge: atualizar
o plano do Pandoo PR B para reusar `cenarios_animados.js`, e atualizar o
CLAUDE.md.

Fora do escopo: domínio próprio por clínica, e-mails com a marca da clínica,
link de convite apontando para `#/entrar/<endereco>`.
