# Panda Tech — Contexto do projeto para o Claude Code

> Nasceu como handoff de uma sessão no Cowork; desde 23/09/2026 o trabalho
> continua no Claude Code, no clone local em
> `D:\Projeto Viva\Panda Tech\panda-tech-deploy\projeto` (Windows). Este
> arquivo é lido automaticamente em toda sessão — mantenha-o atualizado ao
> final de cada lote de mudanças (seções 5 e 7).

## 1. O projeto

**Panda Tech** — SaaS de desenvolvimento infantil para clínicas brasileiras
(fonoaudiologia, terapia ocupacional, psicopedagogia etc.).

- **Repositório**: `andremoreirapanda/panda-tech` no GitHub — **mantenha
  público** até eu dizer explicitamente que as "últimas rodadas" de mudanças
  terminaram.
- **Produção**: `https://pandatech.pandacriacao.com.br/`, hospedado via
  cPanel + Passenger.
- **Banco de dados**: Postgres no Supabase (produção). Localmente, o backend
  roda em SQLite (`backend/encanto.db`, recriado pelo `seed.py`).
- **Stack**: Flask (Python) no backend, SPA em JS puro (sem framework) no
  front-end, servido como estático pelo próprio Flask.

## 2. Regras fixas (não mudar sem eu pedir)

1. **Repositório público** até eu avisar que terminamos as últimas rodadas.
2. **Não implementar RLS** (Row Level Security) nem **criptografia em nível
   de campo** de dados clínicos/de pacientes — decisão de adiar
   indefinidamente, já tomada antes. Existe um rascunho
   `backend/habilitar_rls_encanto_em_casa.sql` (não versionado) que está
   **em standby** por decisão do usuário (23/09/2026): não rodar, não
   commitar e não apagar até ele pedir — a revisita fica para depois que
   terminarmos as atualizações do sistema.
3. Toda mensagem de commit deve terminar com a linha de coautoria do
   modelo que está rodando a sessão, por exemplo:
   ```
   Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
   ```
   (Commits antigos, feitos no Cowork, também têm uma linha
   `Claude-Session:` — ela não é mais usada.)

## 3. Fluxo de trabalho e deploy

**Git**: o clone local tem `git fetch`/`pull` funcionando via HTTPS com o
GitHub. Desde 14/09/2026 o fluxo é por **branch + pull request** (PRs #1 a
#5 já mesclados em `main`):

1. Atualizar o `main` (`git checkout main && git pull --ff-only`) e criar um
   branch com nome descritivo (ex.: `fix-link-autorizacao-assinatura-mp`).
2. Implementar e rodar a **suíte de testes completa** antes de commitar
   (ver seção 4).
3. Push do branch e abrir PR para `main`. O GitHub Actions
   (`.github/workflows/tests.yml`, Python 3.11) roda o `pytest` em todo PR
   e em todo push para `main`.
   **Merge automático** (autorizado pelo usuário em 23/09/2026): com os
   testes locais e o CI do PR verdes (`gh pr checks`), fazer o merge sem
   perguntar (`gh pr merge --merge --delete-branch`). Exceção: se o CI
   falhar ou a mudança for arriscada (schema, cobrança, dados de produção),
   perguntar antes. O `gh` fica em `/c/Program Files/GitHub CLI/gh.exe` (não
   está no PATH do Git Bash).
4. Depois do merge: `git checkout main && git pull`, rodar os testes de novo
   nesse estado exato (e um teste Playwright de fumaça quando a mudança for
   de tela).
5. O usuário faz o deploy manualmente no servidor cPanel: `git pull` +
   `touch tmp/restart.txt` (Passenger).
6. Se teve mudança de schema, o usuário roda a migração em produção — ou o
   `.sql` no SQL Editor do Supabase, ou o script `backend/migrar_*.py` no
   virtualenv do servidor.

**Sempre avisar** quando alguma mudança exigir um passo manual em produção
(migração SQL/script, restart do Passenger, variável de ambiente nova).

Histórico: no Cowork não havia `git push`, e o deploy era feito por upload
na UI web do GitHub, um commit por diretório. Esse fluxo não é mais
necessário.

## 4. Como rodar localmente (Windows)

O ambiente virtual fica em `backend/venv` (ignorado pelo git), criado com
`uv` em **Python 3.11** — a mesma versão do CI. O Python do sistema é 3.14,
novo demais para algumas dependências; não use ele direto.

```bash
cd backend

# criar/atualizar o ambiente (só na primeira vez ou se requirements mudar)
uv venv --python 3.11 venv
uv pip install --python venv/Scripts/python.exe -r requirements-dev.txt

# rodar os testes (~3 min)
PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q

# resetar e popular o banco local
rm -f encanto.db
PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe seed.py

# subir o servidor
PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe app.py   # http://localhost:5000
```

**`PYTHONUTF8=1` é obrigatório no Windows**: sem ele o Python abre
`schema.sql` em cp1252 e quebra com `UnicodeDecodeError` — todos os testes
dão erro no setup, embora o código esteja certo.

**Credenciais de demonstração** (criadas pelo `seed.py`; só existem no
banco local — o `seed_producao.py` pede a senha do admin na hora):
- Admin do SaaS: `admin@encantoemcasa.com` / `admin123`
- Gestor (clínica): `andre@clinicaencantar.com.br` / `gestor123`
- Profissional (Fono): `camila@clinicaencantar.com.br` / `prof123`
- Profissional (TO): `rafael@clinicaencantar.com.br` / `prof123`
- Profissional (Psicop.): `juliana@clinicaencantar.com.br` / `prof123`
- Responsável: `ana@familia.com` / `familia123` (demais responsáveis usam
  `familia123`)

**Gotchas do ambiente de teste**:
- O `encanto.db` local não acompanha as migrações. Se o login local der
  `KeyError` numa coluna, o banco está velho: recrie com o `seed.py`. Os
  testes não têm esse problema, porque cada um cria o próprio banco.
- O limite de login é por IP (10 a cada 5 min). Testar senha errada
  várias vezes bloqueia o seu próprio login local até reiniciar o servidor.
- O aviso `InsecureKeyLengthWarning` do JWT nos testes é esperado (a chave
  `teste-local` é curta de propósito); em produção o `ENCANTO_SECRET` é
  longo.
- Se testar vídeo/mídia com Playwright/Chromium, o Chromium empacotado pode
  **não ter decoder H.264** — um MP4 real falha com `readyState: 0` /
  `networkState: 3` mesmo com o app certo. Prefira vídeos de teste em
  **VP9/WebM** (`ffmpeg -c:v libvpx-vp9`).

## 5. O que já foi feito (mais recente por último)

### a) Correção de CSP — "vídeo não toca"
Achado do usuário: vídeo/áudio de exercício da Biblioteca não tocava (ficava
preto/mudo). **Não era bug de detecção de tipo** — o backend já identificava
corretamente via magic bytes. Era a `Content-Security-Policy` faltando
`media-src` (bloqueava `<video><source src="data:video/mp4;base64,...">`) e
`frame-src` (bloqueava `<iframe>` de embed do YouTube/Vimeo). Corrigido em
`backend/app.py`, com testes de regressão em
`backend/tests/test_security_headers.py`.

### b) Fase 4 — Seletor de exercícios em "Nova Missão"
Modal de escolher exercícios da Biblioteca dentro de "Nova Missão", reusando
a navegação por pastas/busca/filtros já existente na Biblioteca
(`abrirModalEscolherExercicios` em `frontend/js/views/biblioteca.js`,
integrado em `frontend/js/views/jornada.js`). Puramente aditivo — não alterou
nenhuma função existente da Biblioteca.

### c) Remoção do botão "Sugerir com IA"
Removido da modal "Nova Missão" (`jornada.js`) por repetir sempre a mesma
sugestão — baixo valor. Removido também o código morto que só ele usava
(`MAPA_PALAVRAS_CHAVE_IA`, `sugerirMissaoIA`).

### d) Miniaturas padronizadas em 290×250px
Antes, a miniatura gerada no navegador (canvas) só limitava o lado maior a
240px, preservando a proporção original — cards da grade saíam com alturas
diferentes. Agora `gerarThumbnailImagem` e `gerarThumbnailVideo` usam uma
função compartilhada (`desenharMiniaturaPadrao`) que sempre desenha num
canvas fixo de 290×250px, cortando o excesso pra cobrir o quadro inteiro sem
distorcer (mesma lógica do `object-fit:cover` já usado no `<img>` do card).
**Só vale para mídia nova/reenviada** — miniaturas de exercícios já
existentes não são regeneradas sozinhas (é preciso remover e adicionar a
mídia de novo se quiser o novo padrão).

### e) Pastas da Biblioteca — editar nome + emoji juntos
O botão "renomear" virou "editar" e agora abre a mesma paleta de emoji usada
em "Nova pasta" junto com o campo de nome — os dois são salvos numa
chamada só (`PUT /biblioteca/categorias/<id>`, que já aceitava
`icone_emoji`, só o front-end não deixava trocar).

### f) Arrastar-e-soltar exercícios entre pastas
Arrastar um card de exercício (com ou sem pasta) e soltar em cima de um card
de pasta move ele pra lá, em qualquer nível de navegação (raiz ou dentro de
uma pasta/subpasta). Só cards de exercício editáveis pelo usuário ficam
`draggable`; só pastas de verdade aceitam soltar (a ponte "🌐 Biblioteca da
Plataforma" não é uma pasta real).

**Detalhe técnico importante**: foi criada uma rota nova,
`PUT /biblioteca/exercicios/<id>/mover`, só pra trocar `categoria_id`. **Não
reusa** o `PUT /exercicios/<id>` normal porque esse último sempre
**substitui a lista de mídias inteira** (estratégia de "substituição total"
da Fase 3) — chamar ele só com `categoria_id` apagaria todas as mídias do
exercício por engano. A nova rota só mexe na coluna `categoria_id`, com a
mesma validação de escopo (`_resolver_categoria_id`/`_pode_editar`) usada em
criar/editar. 6 testes novos cobrindo isso em
`backend/tests/test_biblioteca.py`.

### g) Cobrança da plataforma: fim da duplicidade + assinatura recorrente no cartão (14–15/09/2026, PRs #1–#4)
Cobrança Plataforma → Clínicas (`backend/pagamento_plataforma_service.py`):
- **Duplicidade avulsa/mensal corrigida**: uma cobrança avulsa no mês não
  impede mais a mensalidade (e vice-versa). A tabela `cobrancas_planos`
  ganhou a coluna `descricao`.
- **Assinatura recorrente no cartão** ("preapproval" do Mercado Pago):
  tabela nova `assinaturas_cartao_recorrentes`; rotas
  `POST /api/admin/assinatura/recorrente/ativar` e `.../cancelar` (tela
  "Sua Assinatura" do Gestor, em `frontend/js/views/financeiro.js`);
  webhooks `processar_webhook_preapproval` e
  `processar_webhook_pagamento_recorrente` (idempotente; pagamento recusado
  gera uma cobrança PIX de fallback). Migração:
  `backend/migrar_assinatura_recorrente_cartao.py`.
- **Correções logo depois**: dá pra retomar uma assinatura "pendente"
  (botão "Continuar autorização") e cancelá-la; o parâmetro
  `&activation=true` é removido do link de autorização, porque o próprio
  Mercado Pago passou a devolver um link quebrado ("Esta página não
  existe"; bug mercadopago/sdk-nodejs#480, desde ~04/09/2026). Remover
  essa gambiarra quando o MP corrigir.

### h) Reenviar link de acesso na tela de Equipe (21/09/2026, PR #5)
Rotas `POST /api/pessoas/profissionais/<id>/reenviar-convite` e
`POST /api/pessoas/secretarias/<id>/reenviar-convite` (mesmo padrão da que
já existia para responsáveis), com botão na tela. Testes em
`backend/tests/test_reenviar_convite_equipe.py`.

### i) Revisão de segurança (23/09/2026)
Scanners (pip-audit, bandit, vulture) limpos. Três falhas corrigidas, com
14 testes em `backend/tests/test_auditoria_23_09_2026.py`:
- **Esqueci minha senha** devolvia o link de redefinição na resposta também
  em produção (tomada de qualquer conta). Agora o link só aparece com
  `FLASK_DEBUG=1`. Em produção, a recuperação é pelo "Reenviar link de
  acesso": o gestor gera para a equipe/responsáveis e o **admin para o
  gestor** (rota nova `POST /api/admin/clinicas/<id>/gestores/<id>/reenviar-convite`,
  botão no detalhe da clínica).
- **Rate limit do login** era contornável trocando o `X-Forwarded-For`.
  Agora usa `remote_addr` (a produção é LiteSpeed, sem proxy na frente) e
  soma um limite por e-mail. Variável opcional `ENCANTO_PROXIES_CONFIAVEIS`
  (padrão 0, ver `.env.example`).
- **Campos de emoji** (`logo_emoji`, `icone_emoji` de pasta, mascote na
  criação do paciente) aceitavam HTML: validados em
  `backend/validacao_campos.py` e escapados no front.
Também foi removido código morto do JS (`nomeIA`/`nomeMedalhaGenerico`
ficaram de propósito, para uso futuro).

### j) Limpeza: Docker/Fly.io e pasta de migrações (23/09/2026)
- Removidos `Dockerfile`, `fly.toml`, `.dockerignore` e o `gunicorn` do
  `requirements.txt`. A produção roda só via Passenger/LiteSpeed no cPanel
  (`passenger_wsgi.py`).
- Os `.sql` antigos foram para `backend/migracoes/`, e os workflows
  (`tests.yml`, `db-setup.yml`) e o `tests_postgres` usam o caminho novo.
  Os `migrar_*.py` **continuam em `backend/`** de propósito: eles fazem
  `import db` e só funcionam rodando de dentro dessa pasta.

### k) Código pronto para troca de domínio (24/09/2026)
O domínio não aparece mais fixo no código de produção: os avisos de pop-up
bloqueado em `financeiro.js` usam `location.host`, e o e-mail reserva do
`payer.email` (`_email_cobranca`) pode vir da variável opcional
`EMAIL_COBRANCA_PADRAO` (padrão `financeiro@pandacriacao.com.br`). O
roteiro da troca em si está na seção 7.1. Suíte: **247 testes passando**.

### l) Vínculo automático ao agendar (24/09/2026)
Agendar (consulta única ou recorrente) ou reatribuir uma consulta vincula o
profissional que atende ao paciente em `profissionais_pacientes`
(`_garantir_vinculo_profissional` em `agenda_bp.py`), dando acesso de
edição a plano, missões e diário. É permanente (cancelar não desfaz; o
gestor desvincula pela ficha); consulta marcada para gestor não cria
vínculo. Testes em `backend/tests/test_vinculo_automatico_agenda.py`.
Spec e plano da mudança da agenda em `docs/superpowers/`. Suíte: **257
testes passando**.

### m) Agenda numa tela só + horário de funcionamento (24/09/2026)
- **Horário da clínica**: colunas `organizacoes.agenda_hora_inicio/fim`
  ('HH:MM', qualquer minuto; NULL = automático), validadas em
  `validacao_campos.validar_horario_agenda`, editadas em Configurações e
  expostas no `/auth/me` (`CAMPOS_ORG`). Migração:
  `backend/migracoes/migracao_horario_agenda.sql` ou
  `backend/migrar_horario_agenda.py`.
- **Layout**: a agenda do gestor/profissional/secretária ocupa a tela
  (classe `.shell-agenda`), com lista lateral de profissionais (filtro) e
  a grade "Por Profissional" de segunda a sábado (domingo só com consulta),
  posicionada em % da faixa horária. Clique e arraste encaixam de 15 em
  15 min. O modo Geral mantém Lista/Semana/Mês.
- **Correções achadas no caminho**: `paraChaveDia` usava UTC (depois das
  21h marcava o dia seguinte como hoje); `formatarData` mostrava datas puras
  ("YYYY-MM-DD") um dia antes; consulta com hora sem zero ("9:00:00", do
  seed) sumia da grade nova.
- Testes de front-end com `node --test frontend/tests/*.test.js` (job `js`
  no CI): 17. Backend: **264 testes passando**.
- Pendência conhecida (não corrigida): `formatarDataHora` trata
  `consultas.data_hora` (horário local) como UTC, então a Lista do modo
  Geral mostra horários 3h adiantados.

**Estado atual (23/09/2026)**: PRs #7 a #9 mesclados em `main` e **em
produção** (deploy feito e conferido), **246 testes de backend passando**.
O app antigo do Fly.io (`pandatech1`), que estava no ar com código de
25/08 e ligado ao Supabase de produção, foi **apagado**, e a senha do banco
foi trocada (cPanel e secret `DATABASE_URL` do GitHub atualizados).

## 6. Conceitos-chave do código (pra não redescobrir)

- **CSP** (`backend/app.py`, dentro de `add_cors_headers`): `default-src
  'self'`, `script-src 'self'`, `style-src 'self' 'unsafe-inline'
  https://fonts.googleapis.com`, `font-src 'self' https://fonts.gstatic.com`,
  `img-src 'self' data:`, `media-src 'self' data:`, `connect-src 'self'
  https://viacep.com.br`, `frame-src https://www.youtube.com
  https://player.vimeo.com`, `object-src 'none'`, `base-uri 'self'`,
  `frame-ancestors 'none'`. Qualquer novo tipo de recurso carregado via
  `data:` ou de origem externa provavelmente vai exigir mexer aqui.

- **Fase 3 — múltiplas mídias por exercício**: tabela `midias_exercicio`,
  uma linha por mídia (`tipo`, `conteudo_url`, `arquivo_base64`,
  `arquivo_nome`, `arquivo_tamanho_bytes`, `thumbnail_base64`, `ordem`).
  Editar um exercício é sempre um **full-replace** das linhas de mídia — a
  lista completa é reenviada e a antiga é descartada. Isso é o motivo da
  rota `/mover` existir separada (ver seção 5f).

- **Geração de miniatura** (`frontend/js/views/biblioteca.js`): puramente
  client-side, via `<canvas>`. Só roda quando um arquivo NOVO é selecionado
  no `<input type="file">` do editor — editar outros campos sem tocar na
  mídia preserva o `thumbnail_base64` existente.

- **Pastas/categorias** (`categorias_exercicio`): até 2 níveis (pasta →
  subpasta), isoladas por `organizacao_id` (clínica) ou `NULL` (Biblioteca
  da Plataforma, mantida pelo Admin do SaaS). Toda operação que referencia
  `categoria_id` valida o escopo via `_resolver_categoria_id` pra impedir
  vincular um exercício/pasta de outra clínica.

- **Navegação por pastas estilo Google Drive**
  (`nivelDeNavegacao`/`renderModoPastas`/`pilha` em `biblioteca.js`): pilha
  vazia = raiz; cada nível mostra as subpastas + os exercícios soltos
  daquele nível. A "🌐 Biblioteca da Plataforma" é uma pasta-ponte
  (`ehPontePlataforma`/`viaPonte`) — não é uma categoria real, tem cuidado
  especial em qualquer código que trate `data-pasta-id`.

- **Grade da agenda** (`frontend/js/agenda_faixa.js`): funções puras, sem
  DOM, testadas em `frontend/tests/agenda_faixa.test.js`.
  `calcularFaixaAgenda` decide a faixa: o horário da clínica, ou
  08:00–18:00 no automático, esticada por consultas fora dela.
  `minutoNaFaixa` converte clique/soltar em horário, de 15 em 15 min.
  `agenda.js` posiciona tudo em % dessa faixa. Mudou a grade? Mexa aqui e
  nos testes.

- **Dois canais de cobrança não podem se sobrepor**: clínica com assinatura
  recorrente **ativa** é pulada pelo ciclo mensal comum
  (`gerar_cobrancas_mensais`, cron ou botão "Gerar cobranças agora") — é o
  próprio Mercado Pago que cobra, e o webhook registra a cobrança
  (`_tem_assinatura_recorrente_ativa`). Qualquer mudança no ciclo mensal
  precisa manter essa regra.

## 7. Pendências / próximos passos

- **Nada em andamento no código.** A próxima etapa é "finalizar as questões
  de atualização do sistema"; pergunte ao usuário qual é o próximo item.
- **Migração do horário da agenda (seção 5m)**: rodar em produção **antes**
  do `git pull` no servidor (o login lê as colunas novas). Use
  `backend/migracoes/migracao_horario_agenda.sql` no SQL Editor do Supabase
  ou o `migrar_horario_agenda.py` (conferindo `(Postgres)`). Remova este
  item quando o usuário confirmar.
- **Diário Terapêutico ligado à consulta**: adiado pelo usuário (24/09/2026),
  que vai fazer uma alteração maior. A coluna `diarios_terapeuticos.consulta_id`
  já existe e não é usada.
- **Recuperação de senha por e-mail** (futuro): hoje não há envio de
  e-mail, então "Esqueci minha senha" em produção só orienta a pedir um
  link ao gestor/admin. Quando houver um provedor de e-mail, o link volta a
  ser gerado, mas enviado por e-mail e nunca na resposta da API.
- **RLS em standby** (ver regra 2): `backend/habilitar_rls_encanto_em_casa.sql`
  fica parado até o usuário retomar o assunto.
- Migração da assinatura recorrente: **já aplicada em produção** (conferido
  no Supabase em 23/09/2026 — a tabela `assinaturas_cartao_recorrentes` e
  a coluna `cobrancas_planos.descricao` existem, iguais ao script).
- **Troca de domínio** (futuro próximo; domínio novo ainda não definido em
  24/09/2026): roteiro na seção 7.1.

## 7.1. Roteiro para trocar o domínio de produção

O código já está pronto (seção 5k); a troca é só configuração. Levantado
em 24/09/2026.

**Regra de ouro**: manter o domínio antigo **servindo o mesmo app** (alias,
não só redirect 301) por algumas semanas. Cobranças PIX/checkout e
assinaturas recorrentes já criadas no Mercado Pago guardam a
`notification_url`/`back_url` antigas; webhook chega por POST e um 301
costuma perdê-lo, ou seja, pagamento feito sem baixa no sistema. Depois
disso, dá pra redirecionar só as páginas (não `/api/`).

Ordem sugerida:
1. **DNS + SSL**: apontar o domínio novo e emitir o certificado (AutoSSL no
   cPanel) **antes** de trocar qualquer coisa.
2. **cPanel**: domínio adicional/alias para a mesma raiz do app
   (Passenger), mantendo o antigo no ar.
3. **`.env` do servidor** e depois `touch tmp/restart.txt`:
   - `URL_APP`: back_url do Checkout Pro e da assinatura recorrente e link
     de convite por WhatsApp.
   - `ALLOWED_ORIGIN`: CORS e redirect padrão do Google.
   - `MP_NOTIFICATION_URL` / `MP_PLATAFORMA_NOTIFICATION_URL`: webhooks.
   - `GOOGLE_OAUTH_REDIRECT_URI`, se estiver definida.
   - `EMAIL_COBRANCA_PADRAO`, só se o domínio de e-mail também mudar.
4. **Mercado Pago**: atualizar a URL de webhook no painel das aplicações
   (plataforma e clínicas).
5. **Google Calendar**: incluir o redirect URI novo no Google Cloud Console.
   Atenção: se o Admin salvou a integração pela tela, o `redirect_uri` está
   **gravado no banco** e tem prioridade sobre o `.env`
   (`calendar_sync_service.config_oauth_app`); reconectar pela tela ou
   atualizar o registro.
6. **Conferir**: login, abrir o checkout do cartão (volta para o domínio
   novo?) e um pagamento de teste chegando pelo webhook.
7. **Avisar as clínicas**: todos precisarão **entrar de novo** (token no
   `localStorage`, que é por domínio; modo criança e paciente ativo também
   voltam ao padrão, sem perda de dados). Links de convite já enviados
   continuam funcionando enquanto o domínio antigo estiver no ar.
8. Atualizar este arquivo (seção 1, "Produção").

## 7.2. Cuidado com os scripts `migrar_*.py` em produção

Eles fazem `import db` **sem** carregar o `backend/.env` (quem chama
`load_dotenv()` é só o `app.py`). Se `DATABASE_URL` não estiver no ambiente
do terminal, o script **não dá erro**: grava no SQLite local
(`encanto.db`) e imprime `(SQLite)` no fim. Em produção, confira que a
saída termina com **`(Postgres)`**. Quando for possível, prefira conferir
ou aplicar a mudança direto no Supabase.

## 8. Onde estão as coisas (para localizar rápido)

| O quê | Onde |
|---|---|
| CSP e headers de segurança | `backend/app.py` |
| Rotas da Biblioteca (exercícios, categorias, mover) | `backend/blueprints/biblioteca_bp.py` |
| Testes da Biblioteca | `backend/tests/test_biblioteca.py` |
| Testes de headers de segurança | `backend/tests/test_security_headers.py` |
| Tela da Biblioteca (grid, pastas, editor, miniaturas, drag-and-drop) | `frontend/js/views/biblioteca.js` |
| Tela de Jornada / Nova Missão | `frontend/js/views/jornada.js` |
| CSS de componentes (cards, drag-and-drop) | `frontend/css/components.css` |
| Seed de dados de demonstração | `backend/seed.py` |
| Cobrança da plataforma (mensal, avulsa, recorrente, webhooks MP) | `backend/pagamento_plataforma_service.py` |
| Rotas do Admin/Gestor (assinatura, webhook da plataforma) | `backend/blueprints/admin_bp.py` |
| Tela financeira / "Sua Assinatura" | `frontend/js/views/financeiro.js` |
| Rotas de pessoas (pacientes, equipe, reenviar convite) | `backend/blueprints/pessoas_bp.py` |
| Testes da assinatura recorrente | `backend/tests/test_assinatura_recorrente_cartao.py` |
| Tela da Agenda (lista lateral, grade semanal, arrastar) | `frontend/js/views/agenda.js` |
| Faixa horária da grade (funções puras) + testes Node | `frontend/js/agenda_faixa.js`, `frontend/tests/` |
| Horário de funcionamento (validação) | `backend/validacao_campos.py` |
| CI (pytest e node --test em PR/push) e setup do banco | `.github/workflows/` |
