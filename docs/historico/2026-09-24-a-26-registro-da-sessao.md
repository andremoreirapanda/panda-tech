# Registro da sessão — 24 a 26/09/2026

Sessão longa no Claude Code (Opus 5.5) com o André, do dia 24 ao dia 26 de
setembro de 2026. Foram os PRs **#11 a #27** e o **Guia de Configurações em
PDF**. Este arquivo guarda **o que foi pedido, o que foi decidido e o que foi
entregue**, na ordem em que aconteceu, para consulta futura. Os detalhes
técnicos de cada entrega estão no `CLAUDE.md` (seções 5k a 5s) e nas
specs/planos em `docs/superpowers/`.

## Como trabalhamos

- Para mudanças grandes: conversa (brainstorming), **prévias visuais**
  quando o assunto era de tela, spec, plano de implementação e execução
  "nativa" (o Claude implementa tarefa por tarefa, com testes antes do
  código). No fim, um **revisor independente** revisa o branch inteiro e o
  que ele acha de importante é corrigido com teste.
- Para ajustes pequenos: desenho curto no chat, o ok do André e a
  implementação.
- Sempre em branch + PR. Com o CI verde, **merge automático**, exceto quando
  há migração de banco, cobrança ou dados de produção (nesses casos, o
  Claude pergunta antes).
- Todo passo manual de produção (SQL no Supabase, `git pull`, restart) é
  avisado na hora, com o SQL pronto para colar.
- Verificação no navegador (Playwright) em toda mudança de tela.

## Linha do tempo

### 24/09 — Domínio, vínculo automático e agenda

- **Estudo da troca de domínio (PR #11)**: o domínio ainda não existe, era
  só para planejar. O domínio fixo foi removido do código e o **roteiro da
  troca** foi registrado no CLAUDE.md (seção 7.1): manter o domínio antigo
  no ar por causa dos webhooks do Mercado Pago, ajustar variáveis, Google
  e avisar as clínicas.
- **Vínculo automático (PR #12)**: ao agendar, o profissional passa a ter
  acesso ao paciente. Decisão: o vínculo é permanente, e o gestor
  desvincula pela ficha.
- **Agenda numa tela só + horário da clínica (PR #13)**: lista lateral de
  profissionais e semana inteira na tela, no estilo "clinicaagil".
  Horário de funcionamento editável por clínica, aceitando horário
  quebrado (ex.: 07:30).
- **Adiado pelo André**: ligar o Diário Terapêutico à consulta ("vou fazer
  uma alteração maior").

### 25/09 — Envios, Pandoo (backend), planos e White Label

- **Padronização dos envios (PR #14)**: todo campo de arquivo mostra
  formato, tamanho ideal e limite. As imagens são reduzidas no navegador.
  Fotos e logo aceitam **até 15 MB**. Em seguida o **GIF voltou (PR #15)**
  para Biblioteca, Diário e chat.
- **Pandoo — backend (PR #16)**: criador de jogos no estilo Wordwall.
  Decisões do André:
  - nome "Pandoo";
  - módulo pago;
  - roleta de figuras como primeiro jogo;
  - o profissional escolhe como o jogo termina;
  - a missão só libera depois de jogar;
  - sons e voz em todos os jogos;
  - cenários editáveis por clínica;
  - contraste de texto automático conforme o cenário.
- **Planos configuráveis (PR #18)**: o Admin cria e edita planos pela tela.
  Decisões do André:
  - "herança viva" entre planos;
  - módulos extras liberados por clínica;
  - data "disponível até" para promoções;
  - **pacientes ilimitados** em todos os planos.
- **PR #19**: os recursos do plano passaram a ser gerados dos campos, as
  descrições dos módulos foram reescritas e o módulo **"Assistente de IA"
  ficou escondido** até existir.
- **White Label completo (PR #20)**: foi desenhado por prévias (v1 a v3) e
  inclui nome e ícone do app, **tela de login da clínica**
  (`#/entrar/<endereço>`) e Mundo da Criança personalizado (fonte, fundo
  animado igual ao do Pandoo, mascote padrão, texto da comemoração).
- **PR #21**: erro "Módulo desconhecido: ia" ao salvar o plano Pro. O `ia`
  escondido continua gravado no plano e volta quando o assistente existir.

### 26/09 — Ajustes do White Label, fundo da clínica e Pandoo (tela)

- **PR #22**, a pedido do André:
  - **cores e nomes da gamificação voltaram a ser livres** para todos os
    planos;
  - Configurações ficou em cartões separados ("Identidade visual" e "Dados
    institucionais");
  - o cartão "Identidade Visual Própria" só aparece com o módulo;
  - novo **Fundo da clínica**, só com o White Label: colorido, animado ou
    imagem, atrás das telas da equipe e das famílias.
- **PR #23 / #24**: o véu claro, e depois o painel claro, apagavam o fundo.
  O André pediu **fundo vivo, linhas em cartões brancos e título da página
  que muda de cor pelo contraste** (branco em fundo escuro). O **ERP**, que
  não fazia nada, ficou escondido.
- **Pandoo — tela (PR #26)**:
  - menu 🎮 Pandoo, com lista e editor (figuras, palavra, voz gravada ou
    arquivo, regras, cenário);
  - palco em tela cheia com a roleta;
  - Biblioteca, seletor da missão, Mundo da Criança (botão "Jogar"), ficha
    do paciente (resultados por figura) e cenário em Configurações.
  - O revisor achou 5 pontos, todos corrigidos.
- **PR #27**, ajustes do André depois de testar:
  - legibilidade da tela do Pandoo;
  - botão "Girar" clicável inteiro;
  - espaço no resumo;
  - **voz 1 s** depois da figura;
  - **missão exige pelo menos um giro**;
  - os pequenos pontos que tinham ficado para depois.

## Produção (situação em 26/09)

- **Todas as migrações foram aplicadas** pelo André (horário da agenda,
  Pandoo, planos configuráveis, recursos dos planos, White Label e fundo da
  clínica). Confirmado em 26/09.
- Deploy: no servidor, `git pull` + `touch tmp/restart.txt`. No navegador,
  **Ctrl+F5**.
- Para liberar um módulo (Pandoo, Identidade Visual Própria etc.) a uma
  clínica: **Admin → Clínicas → abrir a clínica → Módulos da clínica →
  "Extra"**. Também dá para incluir o módulo num plano.

## Guia para Admin e gestores

`D:\Projeto Viva\Panda Tech\Guia de Configurações - Panda Tech.pdf` (fora do
repositório). São 23 páginas, com telas numeradas e comentadas:

- Parte 1, Admin: planos e módulos da clínica.
- Parte 2, gestor:
  - módulos, identidade visual e envio de imagens;
  - horário e agenda;
  - Identidade Visual Própria, fundo da clínica, tela de login e Mundo da
    Criança.
- Parte 3, Pandoo:
  - liberar o módulo;
  - criar o jogo;
  - como a criança joga;
  - colocar numa missão;
  - resultados na ficha;
  - cenário.

Os HTML e as capturas que geram o PDF ficaram na pasta temporária da
sessão. Para atualizar o guia, é preciso regerar as capturas.

## Preferências do André (vale para as próximas sessões)

- Quer **ver antes** quando a mudança é visual (prévias ou capturas) e
  responde por prints marcados.
- Prefere **controles** (cartões, paletas, seletores) a campos de texto
  livre para escolhas visuais.
- Legibilidade vem primeiro: texto sobre fundo precisa de contraste
  garantido. Véus que "apagam" o fundo não agradaram.
- Explicações em português simples, com o passo a passo de produção pronto
  para copiar.
- "Executar do mesmo jeito dos anteriores" significa: plano, execução
  nativa e revisor no fim.

## O que ficou para depois

- **Pandoo fase 2**: quiz, memória, associação e flashcards.
- **Diário ligado à consulta**: adiado pelo André.
- **Recuperação de senha por e-mail**: quando houver provedor de e-mail.
- **RLS em standby**: não rodar, não commitar e não apagar
  `habilitar_rls_encanto_em_casa.sql`. Quando for retomado, incluir as
  tabelas do Pandoo.
- **Troca de domínio**: roteiro no CLAUDE.md, seção 7.1.
- **Repositório público** até o André avisar que terminaram as "últimas
  rodadas".
