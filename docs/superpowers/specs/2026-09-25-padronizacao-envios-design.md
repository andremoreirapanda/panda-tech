# Padronização dos envios de arquivo

Data: 25/09/2026 · Status: aprovado pelo usuário em conversa (tabela abaixo)

## Objetivo

Em todo campo de envio de arquivo do sistema, mostrar **antes do envio** o
formato, a dimensão ideal e o tamanho máximo, e evitar erros: imagens são
**reduzidas automaticamente no navegador** (hoje fotos acima de 2 MB são
recusadas — o caso comum de foto de celular). Formatos: os padrões dos
navegadores (JPG, PNG, WebP; MP4/WebM; MP3/M4A; PDF).

Vem antes do Pandoo (`2026-09-25-pandoo-fase1-design.md`) porque cria as
peças que ele reusa: a função que reduz imagens e a que mostra a orientação
do campo.

## Campos e textos

| Campo | Onde | Texto exibido | Comportamento |
|---|---|---|---|
| Foto de perfil | `financeiro.js` (perfil interno), `responsavel.js` (perfil), `admin.js` (perfil da plataforma), `pacientes.js` (foto do profissional no cadastro da equipe) | 📐 JPG, PNG ou WebP · ideal 400 × 400 px (quadrada) · até 5 MB | reduz para lado maior 400 px, JPEG/WebP ≤ 300 KB |
| Foto do paciente | `responsavel.js` (foto do filho) | idem | idem |
| Foto do contato comercial | `financeiro.js` (Configurações) | idem | idem |
| Logo da clínica | `financeiro.js` (Configurações) | 📐 PNG com fundo transparente (ou JPG/WebP) · ideal 512 × 512 px (quadrado) ou 1024 × 512 px (horizontal) · até 5 MB | reduz para lado maior 1024 px **mantendo a transparência**, ≤ 1,5 MB |
| Mídia da Biblioteca | `biblioteca.js` | 📐 Imagem: JPG, PNG ou WebP · ideal 1280 × 720 px · 🎬 Vídeo: MP4 ou WebM · 🎧 Áudio: MP3 ou M4A · 📄 PDF · até 4 MB (vídeos maiores: use link do YouTube) | imagem reduzida para lado maior 1920 px, ≤ 3,5 MB; vídeo/áudio/PDF com limite de 4 MB como hoje |
| Anexos do Diário | `diario.js` | igual à Biblioteca, sem PDF e sem a dica de link | igual à Biblioteca |
| Anexo do chat | `comunicacao.js` | igual ao Diário, como dica (`title`) do botão de anexo e nas mensagens de erro | igual ao Diário |
| Importar pacientes | `importacao.js` | 📄 Planilha XLSX ou CSV · use o modelo desta tela | só o texto |

Regras comuns:
- O texto fica embaixo do botão/campo de envio (no chat, que só tem um
  ícone, vira a dica do botão).
- Foto HEIC (iPhone) é recusada com dica: "Essa foto está em HEIC (formato do
  iPhone). Envie em JPG, PNG ou WebP — no iPhone, Compartilhar → Salvar como
  JPEG resolve."
- Imagem menor que o mínimo do campo (foto 200 px, logo 128 px, mídia 256 px
  no lado menor) gera aviso **não bloqueante** ("…pode ficar borrada").
- Mensagens de erro repetem a orientação do campo.
- O `accept` dos campos continua amplo onde já era (ex.: `image/*`), para a
  foto HEIC ainda poder ser escolhida e receber a dica, em vez de sumir da
  lista sem explicação.
- Backend não muda: os limites de lá (2 MB fotos/logo, 4 MB mídias) ficam
  como estão e passam a ser folgados, porque o navegador já reduz antes.

## Arquitetura

Arquivo novo `frontend/js/envio_arquivos.js`, carregado depois de `util.js`:
- `PERFIS_ENVIO` — um perfil por tipo de campo (`foto`, `logo`, `midia`,
  `anexo`, `planilha`) com texto, formatos, limites e dimensões.
- Funções puras (testadas com `node --test`): identificar formato do
  arquivo, validar entrada, calcular dimensões reduzidas, escolher formato
  de saída, aviso de imagem pequena.
- `prepararImagemParaEnvio(arquivo, perfil)` e
  `prepararArquivoParaEnvio(arquivo, perfil)` (canvas; testadas no
  navegador).
- `renderOrientacaoEnvio(perfil)` — o parágrafo com o texto.

As 11 telas trocam o bloco repetido (limite de 2 MB + `FileReader`) por
essas funções.

## Entrega

Um PR, sem schema e sem passo manual em produção (só `git pull` +
restart). Merge automático após testes e CI verdes.
