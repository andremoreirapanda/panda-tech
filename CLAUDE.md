# Panda Tech — Contexto do projeto para o Claude Code

> Nasceu como handoff de uma sessão no Cowork; desde 23/09/2026 o trabalho
> continua no Claude Code, no clone local em
> `D:\Projeto Viva\Panda Tech\panda-tech-deploy\projeto` (Windows). Este
> arquivo é lido automaticamente em toda sessão — mantenha-o atualizado ao
> final de cada lote de mudanças (seções 5 e 7).

## 1. O projeto

**PandaUp** (antes "Panda Tech"; nome trocado em 12/10/2026 — os nomes de
arquivos, variáveis e do repositório continuam com o nome antigo) — SaaS de desenvolvimento infantil para clínicas brasileiras
(fonoaudiologia, terapia ocupacional, psicopedagogia etc.).

- **Repositório**: `andremoreirapanda/panda-tech` no GitHub — **mantenha
  público** até eu dizer explicitamente que as "últimas rodadas" de mudanças
  terminaram.
- **Produção**: `https://pandatech.pandacriacao.com.br/`, hospedado via
  cPanel + Passenger. Endereço novo em preparação (12/10/2026):
  `https://app.pandaup.com.br` (mesmo app, mesmo servidor) e homologação em
  `https://teste.pandaup.com.br` — roteiro em
  `docs/operacao/pandaup-dominio-e-homologacao.md`.
- **Homologação no ar** (30/10/2026): `https://teste.pandaup.com.br`, app
  `pandaup-teste` no cPanel (pasta `~/pandaup-teste`, clone do repositório),
  banco no projeto Supabase **PandaUp-Teste** (organização gratuita "PandaUp
  Teste", id `pmoaxraulmrgrectgiht`), `AMBIENTE=homologacao`, sem SMTP, Mercado
  Pago e Google. Só dados fictícios. Admin: o e-mail do usuário. O conector do
  Supabase do Claude enxerga uma organização por vez: confira o nome do
  projeto antes de qualquer SQL (`encanto-em-casa` = **produção**). Ao mexer
  no app pela tela do cPanel, devolver o `passenger_wsgi.py` com
  `git checkout -- passenger_wsgi.py` (o cPanel sobrescreve).
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
  no CI): 18. Backend: **265 testes passando**.
- ~~Pendência: a Lista do modo Geral mostrava horários 3h adiantados~~ —
  corrigido em 01/10/2026: `consultas.data_hora` é horário LOCAL; use
  `formatarDataHoraLocal`/`formatarHoraLocal` (util.js), nunca
  `formatarDataHora` (que converte de UTC, certo só para `criado_em`).

### n) Padronização dos envios de arquivo (25/09/2026)
Todo campo de envio mostra formato, dimensão ideal e tamanho máximo antes
do envio, e imagens são reduzidas no navegador (antes, foto de celular
acima de 2 MB era recusada). Tudo em `frontend/js/envio_arquivos.js`:
perfis `PERFIS_ENVIO` (`foto` 400 px/até 15 MB, `logo` 1024 px mantendo
transparência/até 15 MB, `midia` e `anexo` imagem 1920 px/até 15 MB e
vídeo/áudio/PDF até 4 MB, `planilha`), `prepararImagemParaEnvio`,
`prepararArquivoParaEnvio` e `renderOrientacaoEnvio`. HEIC é recusado com
dica do iPhone; imagem pequena só gera aviso. Backend não mudou (os limites
de lá sobram). Detalhe: a CSP bloqueia `blob:`, por isso a imagem é
decodificada com `createImageBitmap` (sem `URL.createObjectURL`).
GIF é aceito na Biblioteca, no Diário e no chat sem redução (o canvas
congelaria a animação), até 4 MB. Testes: `frontend/tests/envio_arquivos.test.js` (Node, 32 no total).

### o) Pandoo fase 1 — backend (25/09/2026, PR A)
Criador de jogos educativos (spec `docs/superpowers/specs/2026-09-25-pandoo-fase1-design.md`).
Só backend neste PR; a tela vem no PR B.
- **Jogo = exercício** `tipo='jogo'` + linha 1:1 em `pandoo_jogos`
  (conteúdo no formato único v1, regras, cenário). Aparece na Biblioteca e no
  seletor da missão; a Biblioteca **não edita nem duplica** jogo (409).
- **Módulo `pandoo`** (desde o item q, é um módulo comum: entra em plano ou
  como extra da clínica — `modulos_clinica.liberado_admin`); o Admin libera em
  `PUT /api/admin/clinicas/<id>/modulos/pandoo`. Sem o módulo, criar/editar/
  listar dá 403 e os jogos somem da Biblioteca, mas os já colocados em
  missões continuam jogáveis.
- **Rotas** (`blueprints/pandoo_bp.py`): `GET/POST /api/pandoo/jogos`,
  `GET/PUT /api/pandoo/jogos/<id>`, `POST/GET /api/pandoo/resultados`.
  Validação em `pandoo_service.py` (2–24 itens, imagem ≤ 300 KB, áudio ≤
  600 KB incluindo WebM, conteúdo ≤ 10 MB).
- **Missão**: concluir (diária) e "marquei hoje" (semanal) dão 409 enquanto
  houver jogo sem partida (semanal: partida do dia). As atividades passam a
  trazer `exercicio_tipo` e `jogo_jogado`.
- **Cenário padrão** da clínica em `PUT /pessoas/organizacao`
  (`pandoo_cenario_padrao/imagem/tom`).
- Migração: `backend/migracoes/migracao_pandoo.sql` ou `migrar_pandoo.py`.
  `pandoo_jogos` não tem coluna `id` (está em `db._TABELAS_SEM_ID_AUTO`).
- "É jogo" = tem linha em `pandoo_jogos` (não `exercicios.tipo`: o editor
  antigo, até 09/09, deixava marcar "jogo" à mão; a migração normaliza).
  Responsável só lê jogo que está numa missão publicada de um filho.
- Backend: **326 testes passando**.

### q) Planos configuráveis + módulos extras (25/09/2026)
Spec `docs/superpowers/specs/2026-09-25-planos-configuraveis-design.md`.
- **Módulos por plano saíram do código**: tabela `planos_modulos` (módulos
  marcados no próprio plano) + `planos.plano_base_id` (**herança viva**: o
  plano tem tudo o que a base tem, recursivamente; o filho só acrescenta).
  `modulos_service.modulos_do_plano` lê do banco (protege contra ciclo).
  `planos_padrao.py` guarda só o ponto de partida (migração/seeds/testes).
- **Admin → Planos**: criar do zero, editar, "começar a partir do plano…",
  caixas de módulos (herdados travados), **"Disponível até"** (promoção:
  depois da data não dá para atribuir; quem já está nela continua), ativo.
  Não dá para desativar um plano que é base de outro ativo.
- **Módulos extras por clínica**: detalhe da clínica → "Módulos da clínica"
  (qualquer módulo opcional, fora do plano; `modulos_clinica.liberado_admin`).
  O Pandoo deixou de ser caso especial ("só-Admin").
- **Pacientes ilimitados** em todos os planos (limite removido do cadastro e
  da importação; migração zera `limite_pacientes`). O "upsell" do Painel
  Comercial passou a olhar o limite de **profissionais**.
- Gestor → Módulos: extras aparecem como "Liberado pela Panda Tech".
- Migração: `backend/migracoes/migracao_planos_configuraveis.sql` ou
  `migrar_planos_configuraveis.py`. Backend: **354 testes passando**.
- **Recursos do plano automáticos** (25/09/2026): a lista exibida no plano é
  gerada dos campos (`admin_bp._recursos_automaticos`: base, pacientes,
  profissionais, secretárias, módulos próprios); o texto livre virou "Outros
  benefícios". Migração de dados `migracoes/migracao_recursos_planos.sql`
  (limpa os 3 planos originais só se ainda tiverem o texto antigo).
- **Módulo "Assistente de IA" escondido** até existir (`"oculto": True` em
  `MODULOS_OPCIONAIS`; `MODULOS_VISIVEIS`/`CODIGOS_OPCIONAIS` o ignoram; desde 26/11/2026 é visível, ver 5bc). As
  descrições dos módulos foram reescritas (o que faz + o que melhora).

### r) White Label completo (25/09/2026)
Spec `docs/superpowers/specs/2026-09-25-white-label-completo-design.md`.
- **Trava real do módulo `white_label`**: `identidade_service.identidade_efetiva`
  decide o que vale — com o módulo, os valores da clínica (NULL = padrão);
  sem ele, os padrões Panda Tech (cores `#5B4FE9`/`#FFB84D`, "Lumi"/"XP"/
  "Medalha"), com os valores guardados. Logo e nome da clínica nunca travam.
  O `/auth/me` (e o login) já devolvem a identidade efetiva, sem as imagens
  grandes (só `tem_icone`/`tem_mascote_imagem`/`tem_cenario_imagem` e
  `versao_imagens`). `GET /pessoas/organizacao` devolve os valores guardados
  + `white_label_ativo`. **Atenção**: clínicas que tinham cores/nomes próprios
  sem o módulo voltaram ao padrão — o Admin libera o módulo como extra.
- **Colunas novas** em `organizacoes`: `endereco_login` (único), `app_nome`,
  `app_icone_base64`, `login_mensagem`, `mundo_fonte`, `mundo_fundo`,
  `mundo_mascote`, `mundo_mascote_imagem`, `mundo_comemoracao`. Migração
  `backend/migracoes/migracao_white_label.sql` ou `migrar_white_label.py`.
- **Rotas públicas** (`blueprints/publico_bp.py`, sem login):
  `/api/publico/clinica/<endereco>` (+ `/icone`, `/mascote`, `/cenario`,
  `/manifest.webmanifest`). 404 sem o módulo, clínica inativa ou cancelada.
- **Tela de login da clínica** `#/entrar/<endereco>` (`viewLoginClinica`); o
  endereço fica no `localStorage` e o "Sair" volta para ela
  (`urlLoginPosSaida`).
- **Mundo da Criança**: fundo animado (`frontend/js/cenarios_animados.js`,
  **compartilhado com o Pandoo PR B**), fonte (`--fonte-crianca`, fontes extras
  carregadas sob demanda), texto da comemoração, mascote padrão para
  pacientes novos (`mascote_padrao_clinica`); `avatar_mascote = "clinica"` =
  imagem da clínica — em listas, sempre `emojiMascote(...)`.
- **Configurações**: cartão "Identidade Visual Própria"
  (`frontend/js/views/identidade_clinica.js`).
- **Ajuste de 26/09/2026** (pedido do usuário): **cores e nomes da
  gamificação voltaram a ser livres** para todos os planos
  (`identidade_service.CAMPOS_LIVRES`); Configurações ficou em cartões
  separados ("Identidade visual da clínica" e "Dados institucionais", cada um
  com Salvar próprio), e o cartão "Identidade Visual Própria" **só aparece com
  o módulo**. Novo, só com o módulo: **Fundo da clínica** atrás das telas da
  equipe e das famílias (padrão, colorido — paleta `PALETA_FUNDO` ou
  `#RRGGBB` —, Bambuzal, Fundo do mar, Espaço ou a imagem de cenário), com
  as cores vivas (`#fundo-clinica`, `cenarios_animados.atualizarFundoClinica`).
  As linhas das listas (`.pessoa-linha`) viram cartões brancos e o título da
  página troca de cor pelo tom do fundo (`body[data-tom-fundo]`, calculado em
  `fundoDoApp`: tom do cenário, brilho YIQ da cor ou tom da imagem). Véu e
  painel claro foram testados e descartados pelo usuário (apagavam o fundo).
- **ERP escondido** (26/09/2026): o cartão "ERP / Sistema financeiro" da
  Central de Integrações só guardava a "intenção"; saiu da tela e da API
  (`integracoes_bp.TIPOS_OCULTOS`) até existir de verdade, como o Assistente
  de IA.
  Colunas `app_fundo`/`app_fundo_cor`; migração
  `migracoes/migracao_fundo_clinica.sql` ou `migrar_fundo_clinica.py`.
- Backend: **397 testes passando**; front (Node): 42. Imagens da identidade
  são lidas "resumidas" no SQL (`IMAGENS_RESUMIDAS_SQL`) — não carregue as
  colunas `*_base64` em rotas frequentes.

### s) Pandoo fase 1 — tela (26/09/2026, PR B)
Plano `docs/superpowers/plans/2026-09-25-pandoo-fase1-tela.md` (revisado
para os planos configuráveis e o White Label antes da execução).
- **Menu "🎮 Pandoo"** (gestor e profissional, só com o módulo): lista de
  jogos e editor (`frontend/js/views/pandoo.js`) — figuras com imagem
  (perfil `figura`), palavra e voz (gravada no navegador com `MediaRecorder`
  ou arquivo, perfil `voz`, até 30 s/600 KB), regras (todas as figuras ou N
  giros; palavra, som, voz), cenário e pasta da Biblioteca; pré-visualizar.
- **Palco comum** (`frontend/js/pandoo/pandoo_palco.js`): tela cheia com o
  cenário animado (`cenarios_animados.js`, via `cenarioParaPalco`), placar,
  som (`pandoo_som.js`: Web Audio + voz pt-BR 2 s depois da figura),
  "Finalizar jogo" e resumo. Modo `previa` nunca salva; modo `missao` salva
  em `/pandoo/resultados` com "Tentar de novo" se falhar.
- **Roleta** (`frontend/js/pandoo/jogos/roleta.js`), regras puras em
  `pandoo_core.js` (testadas em `frontend/tests/pandoo_core.test.js`).
- **Integrações**: Biblioteca (selo 🎮, abre o editor ou a prévia), seletor
  da missão, Mundo da Criança (botão "Jogar", missão só libera depois de
  jogar — na semanal, jogar hoje), prévia da missão do responsável, ficha do
  paciente (partidas e desempenho por figura) e Configurações ("Cenário do
  Pandoo", mesma imagem do fundo da clínica).
- Sem mudança de schema. Liberação: Admin → Clínicas → "Módulos da
  clínica" → Pandoo (ou por plano).
- **Ajustes de 26/09/2026** (pedido do usuário): a missão só libera com
  **pelo menos um giro** (`jornada_bp._jogo_jogado` exige `total_rodadas > 0`;
  no palco, "Finalizar jogo" sem girar não salva e avisa); a voz entra **1 s**
  depois da figura; botão "Girar" clicável inteiro (a roda girada cobria o
  meio dele); "por figura" da ficha agrupa pelo `item_id` (figura sem palavra
  aparece como "(sem palavra)"); gravar duas vezes não abre dois microfones;
  erro de rede com mensagem amigável; aviso de 10 MB antes de enviar; em
  Configurações, com White Label ligado, a imagem de cenário é enviada só no
  cartão dele; textos soltos da tela do Pandoo em cartões (legíveis com
  qualquer fundo da clínica).
- **Um jogo por dia na missão** (19/10/2026, pedido do usuário): depois de uma
  partida com pelo menos uma jogada, o jogo daquela missão fica "🔒 encerrado
  por hoje" no Mundo da Criança (diária e semanal; `jornada_bp.jogou_hoje` →
  `jogou_hoje` nas atividades) e o `POST /pandoo/resultados` do responsável
  dá 409 no mesmo dia. "Finalizar jogo" **sem jogada** fecha o palco direto
  (sem resumo, nada salvo) e o cartão do jogo mostra "Você está encerrando
  sem jogar" + o `avisoSemRodada` do jogo. O prazo da missão não muda.
- **"Finalizar jogo" no topo** (03/11/2026, pedido do usuário): saiu do pé
  do palco (a criança fechava sem querer) para a linha do logo, à direita
  (`.pd-fim-topo` em `pandoo_palco.js`; no celular o placar desce para a 2ª
  linha). O do cartão da figura na Roleta (uso do adulto) ficou.

### t) Ficha do paciente, pop-ups e notificações (30/09/2026)
Pedidos do usuário:
- **Ficha do paciente**: o Diário Terapêutico fica acima do plano; o cartão do
  plano mostra só as **3 missões mais recentes** (as anteriores atrás de
  "▸ Mostrar N missões anteriores" — `renderListaMissoesFicha` em `jornada.js`).
- **Pop-ups de preenchimento** (`frontend/js/modais.js`, vale para todo
  `.modal-fundo` com campos, sem mexer em cada tela): clicar fora não fecha;
  todo pop-up com campos ganha um **X**; fechado pelo X, o que foi digitado vira
  **rascunho** e volta ao reabrir o mesmo pop-up na mesma tela (aviso
  "Rascunho recuperado"); Salvar/Cancelar descartam. Rascunho só em memória
  (some com F5). Pop-up novo não precisa fazer nada — o `MutationObserver` cuida.
  **Desde 09/11/2026, todo pop-up ganha o X** (com ou sem campos, inclusive os com
  `data-modal-preparado`): se já tem Cancelar/Fechar/Voltar/Agora não ou `[data-fechar]`, o X
  aperta esse botão (`modais.ehTextoDeFechar`); senão, só fecha. `.modal-x + *` ganha margem à direita.
- **Notificações**: o sino mostra só as **5 últimas** e as mais antigas são
  **apagadas** (`db.manter_ultimas_notificacoes`, chamada ao criar e ao listar).
- **Missões vencidas escondidas** (PR #30): na tela da criança e do
  responsável só aparecem missões pendentes/iniciadas dentro do prazo
  (`missaoAtivaVisivel` em `util.js`).

### u) Pandoo fase 2 — Quiz (30/09/2026)
Spec `docs/superpowers/specs/2026-09-30-pandoo-quiz-design.md`, plano em
`docs/superpowers/plans/2026-09-30-pandoo-quiz.md`. Sem migração.
- **Modelo `quiz`** (`pandoo_service.MODELOS`): regras `modo` (`ouvir` = a voz
  diz a palavra e a criança toca na figura; `ver` = aparece a figura e ela toca
  na palavra), `opcoes` 2/3/4, `fim` `todas`/`perguntas` + `perguntas`, `som`,
  `voz`. Imagem sempre obrigatória; `ver` exige a palavra; `ouvir` exige palavra
  ou voz. Até 3 **opções erradas próprias** por figura (`distratores`, usadas só
  no `ver`); as demais saem das outras figuras, sem repetir palavra (ignora
  acento e caixa — `normalizarPalavra`).
- **Errou, tenta de novo**: a opção errada balança e apaga; a pergunta conta
  "conseguiu" só se acertou **de primeira**. Toda resposta certa comemora
  (`palco.registrar(item, resultado, {comemorar})`).
- Regras puras em `pandoo_core.js` (`opcoesDaPergunta`, `estadoInicialQuiz`,
  `proximaPerguntaQuiz`, `registrarRespostaQuiz`, `quizTerminou`); jogo em
  `frontend/js/pandoo/jogos/quiz.js`. O palco usa `rotuloRodada` ("em N
  perguntas") e `avisoSemRodada` de cada jogo.
- **Editor**: os cartões de modelo são botões (trocar mantém as figuras e volta
  as regras ao padrão do modelo, guardando som/voz); painel de regras por modelo
  (`renderRegras`/`lerRegras` em `views/pandoo.js`).
- Ajustes de 01/10/2026: o backend descarta opções erradas vazias/não-texto
  antes do limite e só guarda opções erradas no Quiz (`MAX_DISTRATORES`,
  padrão 0); cartões de regra com contorno de foco pelo teclado.
- Backend: **421 testes passando**; front (Node): 71. Toda pergunta precisa de
  uma opção errada com palavra diferente (`_checar_opcoes_quiz`); no `ouvir` sem
  leitura em voz alta, a palavra é obrigatória.

### v) Pandoo fase 2 — Memória (01/10/2026)
Spec `docs/superpowers/specs/2026-10-01-pandoo-memoria-design.md`, plano em
`docs/superpowers/plans/2026-10-01-pandoo-memoria.md`. Sem migração.
- **Modelo `memoria`**: regras `pares` (`figura` = figura + figura igual;
  `palavra` = figura + palavra escrita), `quantidade` 3/4/6/8/10 (sorteia as
  figuras quando há mais), `som`, `voz`. Imagem sempre obrigatória; no tipo
  `palavra`, palavra obrigatória e sem repetir (sem acento/caixa). Não guarda
  opções erradas.
- **⭐ do par = "lembrou onde estava"**: o par vira "treinar" se, numa jogada,
  a 1ª carta virada era dele, a outra carta do par já tinha aparecido e a 2ª
  carta foi errada (`jogadaMemoria` em `pandoo_core.js`).
- Regras puras em `pandoo_core.js` (`montarCartasMemoria`, `jogadaMemoria`,
  `memoriaTerminou`, `layoutMesaMemoria` — a mesa cabe na tela, cartas de 56 a
  150 px); jogo em `frontend/js/pandoo/jogos/memoria.js`. Erro: as cartas
  balançam (`pdmBalanca`, que mantém a frente virada) e voltam em 1,2 s, com a
  mesa travada.
- **Palco, todos os jogos**: o título do jogo virou pílula branca com texto
  escuro (legível em qualquer cenário). `PandooSom.pararVoz()` +
  `falarItem(item, {cortarSom: false})`: a palavra é dita depois do som de
  acerto sem cortá-lo.
- Ajustes de 01/10/2026: `palco.aoEncerrar(fn)` (o jogo solta recursos ao
  acabar — a Memória tira o listener de resize); a mesa mede o espaço real
  dentro do palco; última linha de cartas centralizada (flex); leitor de tela
  não anuncia carta virada para baixo (`aria-hidden` na frente + rótulo).
- Backend: **426 testes passando**; front (Node): 75.
- Ajuste de 08/10/2026 (pedido do usuário): a palavra da carta não quebra mais
  no meio ("NUBLAD/O"). A fonte começa no máximo (20% da carta) e
  `memoria.js: caberPalavras` mede e reduz só o necessário (também ao
  redimensionar e quando a Fredoka termina de carregar); o texto só quebra
  entre palavras ou no hífen. `pandoo_core.fatorFontePalavraCarta` é a
  estimativa inicial. Margem e borda da carta proporcionais ao tamanho
  (`pandoo.css`). Front (Node): 87.
- Regra nova de 16/10/2026 (pedido do usuário): **"Falar a palavra quando
  virar o cartão"** (`voz_virar`, desligada por padrão). Quem decide quando
  falar é `pandoo_core.falaDaJogadaMemoria`: fala a cada carta virada; ao achar
  o par, fala **uma vez só** depois do som de acerto (não repete a da 2ª
  carta), com `voz` ou `voz_virar`; ao errar, fala a 2ª carta depois do som de
  "quase". Sem migração (a regra vai no JSON do jogo).
- Ajuste de 21/10/2026 (pedido do usuário): o verso das cartas mostra o
  **número da carta na mesa** (1, 2, 3…, em ordem de leitura) no círculo
  branco, para a criança dizer qual quer virar; a patinha 🐾 virou enfeite
  branco no canto superior esquerdo (`.pdm-num`, `.pdm-patinha`). O leitor de
  tela diz "Carta N, virada para baixo".
- Ajuste de 21/10/2026 (pedido do usuário, testado com medição no Chrome):
  **a voz começa em até 1 s** depois de a figura aparecer em todos os jogos.
  A espera padrão (`pandoo_som.js: ATRASO_VOZ_MS`) caiu de 1 s para **0,6 s**,
  porque a voz do navegador leva mais 0,2–0,35 s para começar (com 1 s, o início
  real dava 1,2–1,35 s); o par da Memória usa a mesma espera (era 0,8 s).
  **Frases longas**: a Memória mede também a altura da carta ao encolher a fonte
  (`memoria.js: passaDaCarta`; antes só a largura, e a frase estourava o pé da
  carta), e a Roleta encolhe a palavra embaixo da figura acima de 20/45 letras
  (`pandoo_core.tamanhoPalavraRoleta`, classes `.longa`/`.muito-longa`).

### w) Excluir da Equipe + pacientes sem vínculo (01/10/2026)
Pedidos do usuário:
- **Excluir alguém da Equipe** (profissional ou secretária, só gestor):
  `DELETE /api/pessoas/profissionais/<id>` e `/secretarias/<id>`
  (`pessoas_bp._excluir_da_equipe`). Sem histórico, apaga de vez. Com
  histórico (`_TABELAS_HISTORICO`: consultas, planos, diários, mensagens,
  avisos, ficha clínica, partidas do Pandoo, feedbacks), marca
  `usuarios.excluido_em`, desativa, troca o e-mail para
  `excluido-<id>@removido.invalid` (libera o original) e a senha; o nome fica
  nos registros antigos. A lista da Equipe nunca mostra excluídos. Vínculos,
  notificações, disponibilidade e tokens saem sempre. Na tela, 📦 = arquivar
  (reversível) e 🗑️ = excluir. Migração `migracoes/migracao_excluir_equipe.sql`
  ou `migrar_excluir_equipe.py`.
- **Pacientes sem vínculo**: `auth.paciente_editavel` libera gestor **e
  profissional** da clínica do paciente (o diário usa o mesmo critério). O
  cartão "Equipe" e o "Vincular profissional" saíram da ficha.
  `profissionais_pacientes` continua sendo preenchida pela agenda ("quem
  atende"), só para avisos de mensagem e o "N pacientes" da Equipe.
- **Revisão do PR #35** (01/10/2026, PR seguinte): quem foi excluído não volta
  por editar/arquivar-reativar/reenviar convite (todas as buscas filtram
  `excluido_em IS NULL` → 404); a exclusão é **bloqueada (409)** enquanto o
  profissional tiver consultas não canceladas de hoje em diante (remarcar ou
  cancelar antes); a agenda não aceita consulta para profissional arquivado
  ou excluído (`agenda_bp._profissional_da_mesma_clinica`); exclusão
  definitiva que esbarra num registro novo cai para a que mantém histórico;
  contagens do Admin e da cor da agenda ignoram excluídos.
- Backend: **442 testes passando**; front (Node): 77.

### x) Agenda como tela inicial (07/10/2026)
Pedido do usuário, inspirado na Clínica Ágil: no menu do gestor, do
profissional e da secretária a **📅 Agenda** vem em primeiro e é a tela
depois do login (`router.paginaInicialPara`); o antigo "Início" virou
**📊 Dashboard**, logo abaixo (mesma rota `#/…/dashboard`, título
"Dashboard"). Responsável e admin não mudaram. Próximos passos da comparação
com a Clínica Ágil na seção 7.

### y) Agenda: hora de fim, Ausência e visão Dia (07/10/2026)
Spec `docs/superpowers/specs/2026-10-07-agenda-ausencia-fim-dia-design.md`,
plano em `docs/superpowers/plans/2026-10-07-agenda-ausencia-fim-dia.md`.
- **Hora de fim livre**: pop-ups de agendar/editar têm Início e Fim (mudar o
  início leva o fim junto). Fim padrão = `organizacoes.agenda_duracao_padrao`
  (5–240, começa em 50; Configurações, cartão do horário da agenda).
  `consultas.duracao_min` passa a ser validada (5–480); sem ela no corpo, vale
  o padrão da clínica.
- **Ausência** (`ausencias_profissional`): uma linha = uma REGRA (período,
  `data_fim` NULL = sem fim; dia inteiro ou horário; `dias_semana` "0".."6",
  0 = domingo; motivo até 120). As ocorrências são calculadas na hora
  (`ausencias_service.py`). **Bloqueia**: criar/editar/arrastar/reatribuir
  consulta por cima → 409 "Fulano está ausente nesse horário (motivo)";
  encostar não conflita; editar só observação não checa. Série recorrente
  pula as datas bloqueadas (`datas_puladas` na resposta; tudo bloqueado → 409
  sem criar nada). Lançar ausência por cima de consultas é permitido e a
  resposta lista `consultas_no_periodo` para remarcar.
- **Permissão**: profissional lança/edita só as dele; gestor e secretária
  para qualquer profissional da clínica; quem tem `agenda_permissao_total`
  vê todas, mas só edita as dele; responsável não vê. Rotas
  `GET/POST /api/agenda/ausencias`, `PUT/DELETE /api/agenda/ausencias/<id>`
  (GET até 62 dias).
- **Tela**: "+ Agendar" tem "📅 Consulta | ⛔ Ausência"
  (`views/agenda_ausencia_modal.js`); a ausência aparece como bloco cinza
  listrado na grade (clique edita/apaga a regra inteira). Funções puras em
  `frontend/js/agenda_ausencias.js`. A grade virou genérica
  (`renderGradeHoraria`: colunas = dias de um profissional ou profissionais
  de um dia). **Visão Dia**: no "Por Profissional", botões Dia | Semana; no
  "Geral", Dia | Lista | Semana | Mês, e o Dia mostra uma coluna por
  profissional (a lista lateral vira filtro; arrastar entre colunas troca o
  profissional).
- Correção no caminho: o pop-up de editar mostrava a hora vazia para
  consulta gravada sem zero ("9:00:00").
- Migração: `backend/migracoes/migracao_ausencias_agenda.sql` ou
  `migrar_ausencias_agenda.py`. Backend: **480 testes passando**; front
  (Node): 82.

### z) Diário por paciente e Iniciar jornada num pop-up (08/10/2026, parte 3a)
Spec `docs/superpowers/specs/2026-10-08-jornada-diario-por-paciente-design.md`,
plano `docs/superpowers/plans/2026-10-08-jornada-diario-por-paciente.md`
(prévia aprovada antes: artifact "Prévia Jornada e Diário").
- **O Diário é do paciente**: `diarios_terapeuticos.paciente_id` (preenchida a
  partir da jornada nos antigos) e `jornada_id` opcional (grava a jornada
  ativa quando houver). Quem resolve "de qual paciente é" é
  `diario_bp._paciente_do_diario` (coluna nova, com a jornada como reserva);
  listagens usam `WHERE_DO_PACIENTE`. Rotas `GET/POST /api/diario/paciente/<id>`;
  as antigas `/diario/jornada/<id>` viram atalhos. `consulta_id` só de
  consulta do mesmo paciente (400). A ficha traz `diarios_recentes` mesmo sem
  jornada, e a família também vê o Diário antes de a jornada começar. O ICT
  conta diários por paciente.
- **A jornada fica só para planejar**: "Iniciar jornada terapêutica" abre um
  pop-up (objetivo principal + título do plano + objetivos) →
  `POST /api/jornada/paciente/<id>/iniciar` (cria jornada + 1º plano; valida
  tudo antes; 409 com jornada ativa). O `prompt()` saiu. O objetivo
  principal tem ✏️ → `PUT /api/jornada/jornada/<id>` (até 300 caracteres).
- Migração: `backend/migracoes/migracao_diario_por_paciente.sql` ou
  `migrar_diario_por_paciente.py` (no SQLite o NOT NULL antigo de
  `jornada_id` só some recriando o banco com o `seed.py`).
- Backend: **496 testes passando**; front (Node): 82. O relatório em PDF também mostra o Diário de quem ainda não tem jornada.

### aa) Planos terapêuticos por especialidade (08/10/2026, parte 3c)
Spec `docs/superpowers/specs/2026-10-08-planos-por-especialidade-design.md`,
plano `docs/superpowers/plans/2026-10-08-planos-por-especialidade.md`
(prévia aprovada: artifact "Prévia Planos por Especialidade").
- `planos_terapeuticos.especialidade` (obrigatória, até 60). **Um plano ativo
  por (jornada, especialidade)**: criar plano encerra só o da mesma
  especialidade (ignorando caixa e espaços nas pontas desde 08/10/2026). Planos antigos ganharam a especialidade
  de quem criou, ou "Geral".
- **Bundle da ficha**: `planos_ativos` (cada um com `objetivos`, `missoes`,
  `progresso_pct`, `missoes_concluidas`, `missoes_total`) e `missoes` = todas,
  com `plano_id`/`plano_titulo`/`plano_especialidade`; progresso somado;
  `especialidades_disponiveis` (clínica + equipe ativa, ou "Geral").
  **`plano_ativo` e `objetivos` não existem mais.**
- Somam todos os planos ativos: medalha "Semana Completa"
  (`gamificacao_service.PLANOS_ATIVOS_DO_PACIENTE`), painel do profissional,
  ICT (adesão e feedback) e PDF (uma seção por plano).
- Tela: um cartão por plano na ficha, "+ Novo plano" com **select** de
  especialidade e aviso de encerramento; "Iniciar jornada" pede a
  especialidade do 1º plano; etiquetas nas missões da criança (curta: "🗣️
  Fono") e da família (completa). `frontend/js/especialidades.js`
  (`ICONES_ESPECIALIDADE` mudou para lá, `etiquetaEspecialidade`,
  `opcoesEspecialidade`). Permissão continua livre para a equipe.
- Migração: `backend/migracoes/migracao_planos_especialidade.sql` ou
  `migrar_planos_especialidade.py`. Backend: **512 testes**; front (Node): 84. O select também oferece as especialidades dos planos ativos (um "Geral" migrado pode ser substituído) e `missoes` vem na ordem de criação.

### ab) Correção das pendências menores das partes 2, 3a e 3c (08/10/2026)
Pedido do usuário antes da 3b. Sem migração. Testes em
`backend/tests/test_correcoes_pendencias.py`.
- Agenda: editar só a observação compara a hora normalizada
  (`separar_data_hora`) e só valida a duração se ela mudou;
  `ausencias_service.hoje_brasilia()` (UTC−3) nas "consultas no período";
  navegação de semana só por `btn-periodo-*`; ausências só pedidas por
  gestor/profissional/secretária; sessão expirada não quebra a agenda.
- Equipe: a exclusão definitiva que falha faz `get_db().rollback()` antes de
  cair na que mantém histórico (no Postgres a transação ficava abortada).
- Diário: `consulta_id` convertido para inteiro (400 se inválido); a rota
  antiga `/diario/jornada/<id>` grava a jornada do endereço; diários recentes
  filtrados e com `LIMIT 5` no SQL; ICT usa `WHERE_DO_PACIENTE`.
- Jornada/planos: `_validar_objetivos` (lista, até 300 cada), título até 120,
  especialidade validada primeiro; "Iniciar jornada" apaga o que criou se
  falhar no meio; ficha sem jornada já vem com `planos_ativos`/`missoes`/
  progresso; especialidades que só diferem por caixa/espaços viram uma
  (prefere a grafia da clínica; na ficha, a dos planos ativos vence); "Criar
  plano" encerra o ativo da mesma especialidade ignorando caixa/espaços;
  objetivos que não são texto são ignorados; `consulta_id` fracionado dá 400;
  falha na limpeza do "Iniciar jornada" não esconde o erro original.
- Fica anotado (organização, sem efeito): `ict_service` importa
  `WHERE_DO_PACIENTE` de um blueprint — mover para um módulo neutro.
- Backend: **534 testes**; front (Node): 84.

### ac) Rodada rápida antes da 3b (08/10/2026)
Grupo 1 da lista de pontos fora do escopo. Testes em
`backend/tests/test_rodada_rapida.py`.
- **Encaixe**: agendar, repetir, editar/arrastar ou reativar uma consulta num
  horário que já tem consulta (não cancelada) do mesmo profissional devolve
  409 com `pode_encaixar: true` (`agenda_bp._conflito_consulta`); a tela
  pergunta "Marcar como encaixe?" e reenvia com `encaixe: true`
  (`agenda.js: comEncaixe`, `mudarStatusConsulta`). Encostar não conta.
  Ausência continua bloqueando sem exceção. `Api` agora anexa
  `err.status`/`err.dados` aos erros.
- "Semana Completa" ignora missão em rascunho.
- "+ Novo Diário" só aparece para profissional e gestor.
- **Um plano ativo por especialidade no banco**: índice único parcial
  `idx_plano_ativo_especialidade` (jornada, LOWER(TRIM(especialidade)))
  WHERE status = 'ativo'; corrida em "Criar plano" vira 409. Migração
  `backend/migracoes/migracao_plano_unico_especialidade.sql` ou
  `migrar_plano_unico_especialidade.py` (encerra duplicados, fica o mais novo). **Aplicada em produção** (confirmado em 08/10/2026).
- Backend: **546 testes**; front (Node): 84. A corrida em "Criar plano" vira 409 também no Postgres (UniqueViolation é subclasse de IntegrityError).

### ad) Atender / Evoluir a partir da consulta (08/10/2026, parte 3b)
Spec `docs/superpowers/specs/2026-10-08-atender-evoluir-design.md`, plano
`docs/superpowers/plans/2026-10-08-atender-evoluir.md` (prévia aprovada:
artifact "Prévia Atender e Evoluir").
- **Status novos** da consulta: `falta_justificada` e
  `desmarcada_profissional` (CHECK refeito). Liberam o horário junto com
  `cancelada` (`ausencias_service.STATUS_LIBERAM_HORARIO`: encaixe, ausência,
  "consultas no período"). Rótulos: Finalizado, Não compareceu, Falta
  justificada, Desmarcado pelo profissional, Sessão desmarcada. **Secretária
  não marca `realizada`** (403).
- **Atender**: `GET/PUT /api/agenda/<id>/atendimento` (só o profissional da
  consulta e o gestor; outra clínica → 404). GET traz paciente, profissional
  (com registro), `sessao_numero` (finalizadas na mesma especialidade, antes
  desta, + 1), `diario`, `atraso_dias` (>1 dia sem desfecho, data de
  Brasília) e `historico` (desfechos, até 200). PUT grava o desfecho e cria
  ou atualiza **um** registro do Diário por consulta (índice único
  `idx_diario_por_consulta`), com `observacao` (coluna nova; a família nunca
  vê); descrição obrigatória só em `realizada`; falta sem texto não cria
  registro; família notificada só na criação; edição vai para a auditoria.
  `GET /api/agenda` traz `diario_id`.
- Tela: pop-up da consulta com "▶ Atender"/"✏️ Ver/editar evolução" e a faixa
  de atraso (`atendimento_util.diasDeAtraso`); página
  `#/<gestor|profissional>/atender/<id>` (`views/atendimento.js`).
- Migração: `backend/migracoes/migracao_atender.sql` ou `migrar_atender.py`
  (no SQLite o CHECK novo só vale recriando o banco com o `seed.py`).
- Revisão final: status que liberam o horário aparecem como desmarcados na
  grade e na lista (`atendimento_util.statusLiberaHorario`); o ✓ da lista
  virou ▶ Atender (só para quem atende; a secretária não vê); a secretária
  não muda o status de uma sessão já Finalizada (403).
- Backend: **569 testes**; front (Node): 89.

### ae) Procedimentos com valor no agendamento (09/10/2026, parte A)
Spec `docs/superpowers/specs/2026-10-09-procedimentos-repeticao-ausencias-design.md`,
plano `docs/superpowers/plans/2026-10-09-procedimentos-repeticao-ausencias.md`
(prévia aprovada: artifact "Prévia Procedimentos"). Inspirado em Cadastros →
Procedimentos da Clínica Ágil.
- Tabela `procedimentos` (nome único por clínica ignorando caixa/espaços —
  `idx_procedimento_nome`; `valor_centavos` até R$ 100.000; código até 30;
  `ativo`; `ordem`). Na consulta: `procedimento_id` e
  `procedimento_valor_centavos` = valor **no dia em que foi marcada** (ou em
  que o procedimento foi trocado); mudar o preço não mexe nas já marcadas.
- `GET /api/procedimentos`: gestor recebe tudo (com `valor_centavos` e
  `em_uso`); profissional e secretária só os ativos, **sem valor**.
  `PUT /api/procedimentos` (só gestor) salva a lista inteira; valida tudo
  antes de gravar; remover procedimento usado → 409 sem gravar nada; nomes
  trocados entre linhas passam por um nome provisório.
- Agendar/série/editar aceitam `procedimento_id`
  (`agenda_bp._procedimento_do_corpo`): **obrigatório se a clínica tem algum
  ativo**; no `PUT /agenda/<id>` só se a chave vier (arrastar e status não
  pedem); manter o mesmo mantém o valor, mesmo desativado depois.
  `GET /api/agenda` traz `procedimento_nome`; o valor só vai para o gestor;
  o responsável não recebe procedimento.
- Tela: menu do gestor "💲 Procedimentos" (`views/procedimentos.js`,
  conversões em `procedimentos_util.js`); select nos pop-ups de agendar e de
  editar (só nomes; o desativado da própria consulta aparece como
  "(desativado)").
- Migração: `backend/migracoes/migracao_procedimentos.sql` ou
  `migrar_procedimentos.py`. Backend: **606 testes**; front (Node): 92.

### af) Repetição avançada do agendamento (09/10/2026, parte B)
Mesmas opções do "Repetir Agendamento" da Clínica Ágil (spec e plano do item ae).
- `recorrencia_service.gerar_datas(regra, inicio)` (função pura, testada):
  semanal, quinzenal, a cada N semanas (1–12; vários dias, cada um com
  início/fim próprios; semanas de domingo a sábado; nada antes da 1ª data),
  mensal pelo dia do mês (31 → último dia) ou pelo dia da semana (2ª terça;
  5ª → última), meses escolhidos, data limite ou quantidade; sem fim = 12
  meses; teto de 12 meses e 300 consultas (passou → 400 com a explicação,
  não corta sozinho).
- `POST /api/agenda/recorrente` aceita `repeticao` (regra) e `previa: true`
  (devolve as datas com `ausente`/`ocupada`, sem criar e sem exigir o
  procedimento). O corpo antigo (`frequencia` + `repeticoes`) continua valendo.
- Tela: painel no pop-up de agendar (`ligarPainelRepeticao` em `agenda.js`,
  regra montada por `repeticao_util.js`) com a prévia "Serão criadas N
  consultas, de … a …" e as datas puladas/ocupadas. O botão "Agendar" trava
  enquanto a série é gravada.
- Sem migração. Backend: **636 testes**; front (Node): 98. Cada dia da série tem de 5 min a 8 h; mudar a data/hora com "Repetir" aberto leva os dias junto (`sincronizarDiasRepeticao`).

### ag) Ausências nas visões Lista/Semana/Mês do modo Geral (09/10/2026, parte C)
Só front, sem migração (spec e plano do item ae).
- `carregarAusencias` pede o período da visão (`agenda_ausencias.periodoDaVisao`:
  semana no "Por Profissional"; no Geral, o dia, a semana, as 42 células do
  mês ou hoje + 29 dias da Lista — dentro dos 62 dias da API); trocar de modo
  recarrega.
- Semana: chip cinza listrado "⛔ Camila · 08:00–12:00" / "dia inteiro" antes
  das consultas. Mês: "⛔ N ausente(s)" (profissionais distintos) e o pop-up
  do dia lista as ausências no topo. Lista: cartão "Ausências dos próximos 30
  dias". Clique abre o pop-up de editar ausência (mesmas permissões).
  Agrupamento/rótulo em `ausenciasPorDia`/`rotuloAusencia`.
- Como as consultas dessas visões, mostram todos os profissionais (clicar
  num profissional da lista lateral abre o "Por Profissional").
- Backend: **636 testes**; front (Node): 101.

### ah) Pontos menores das revisões + verificação geral (09/10/2026)
Pedido do usuário. Testes em `backend/tests/test_pontos_menores.py`.
- **Série recorrente em lote**: `db.em_lote()` (contexto: os `execute` dentro
  não dão commit; um commit no fim; erro → rollback de tudo). A série lê
  ausências (`ausencias_service.ausencias_do_profissional_no_periodo` +
  `conflito_em_regras`) e consultas (`agenda_bp._consultas_ocupando`) do
  período uma vez só; Google só se a integração estiver ativa. 300 consultas:
  de ~110 s para ~1,5 s no servidor local.
- **Excluir consulta**: com registro no Diário → 409 (o Diário tem FK para a
  consulta; antes dava 500); "esta e as futuras" mantém as que têm Diário;
  exclusão avisa o Google Agenda.
- **Atender**: status que liberam o horário apagam o evento do Google; o PUT
  sincroniza; consulta cancelada → 409; finalizar/dar falta antes do dia → 409
  (desmarcar continua livre); editar a evolução = autor do registro ou gestor
  (o autor continua acessando depois de reatribuir a consulta); gravação
  simultânea vira edição; família avisada quando o registro passa a ser
  compartilhado; número da sessão compara a hora normalizada.
- **Diário**: o aviso à família nunca leva o texto clínico; `consulta_id` já
  registrado → 409.
- **Procedimentos**: NaN/Infinito, id booleano, `ativo` 0/"0"/"false", nome
  reservado (`__provisorio__`), conflito ao gravar → 409 com rollback; admin
  da plataforma agenda sem procedimento; só a alça ⋮⋮ arrasta; aviso ao sair
  com alteração não salva (`window.SaidaProtegida`, guarda no `router.js` —
  qualquer tela pode usar).
- **Repetição/ausências/agenda**: prévia antiga não sobrescreve erro novo;
  "Todos os dias" acompanha as caixas; resposta de ausências de período antigo
  é ignorada; no celular (≤900px) o Mês mostra só ⛔ em dia só com ausência;
  a agenda no celular não rola mais para os lados; atalho ✏️ para a evolução
  de sessão finalizada na Lista.
- **Verificação**: pyflakes limpo no app (imports sem uso removidos), bandit
  sem achado real (B608 só interpola constantes), pip-audit → **PyJWT 2.15.0**
  (14 CVEs na 2.13.0), `node --check` em todo o JS, varredura das telas de
  gestor/profissional/secretária/responsável/admin + Mundo da Criança, PDF e
  um fluxo completo (procedimento → série → Atender → família).
- Fica como estava: o corpo antigo da série (`frequencia` + `repeticoes`)
  respeita o teto de 12 meses (quinzenal > 27 ou mensal > 13 dá 400).
- Revisão do lote: "Sair" pergunta antes de apagar a sessão e a sessão
  expirada (401) desarma o aviso; corrida no Atender só vira edição com a
  mesma regra de autor; desfecho (realizada/faltou) em consulta futura também
  é barrado na rota de status; Google da série apagado só depois do commit
  (`calendar_sync_service.apagar_evento_google`).
- **Produção**: PyJWT mudou — no servidor, `pip install -r requirements.txt`
  no virtualenv antes do restart.
- Backend: **667 testes**; front (Node): 101.

### ai) Busca de paciente no agendamento + planos anteriores na ficha (09/10/2026)
Pedidos do usuário. Sem migração.
- **Busca de paciente** (como na Clínica Ágil): no pop-up "Agendar", o select
  virou campo de busca — a partir de **3 letras** mostra até 8 pacientes,
  ignorando acentos e maiúsculas, quem começa com o termo primeiro; várias
  palavras = todas precisam aparecer. Teclado (setas/Enter/Esc), mouse e
  toque. Funções puras em `frontend/js/busca_paciente.js`
  (`filtrarPacientes`, `normalizarBusca`); tela em `agenda.js`
  (`renderBuscaPaciente`/`ligarBuscaPaciente`, o id escolhido fica no campo
  oculto `ag-paciente`). Sem paciente escolhido, "Agendar" avisa; a prévia da
  repetição pede o paciente antes.
- **Planos anteriores**: a ficha recebe `planos_encerrados` (só equipe; a
  família não) — `jornada_bp._planos_encerrados`, de todas as jornadas do
  paciente, mais recente primeiro, com objetivos, missões e progresso; aparece
  também sem jornada ativa. Seção recolhida "🗂️ Planos anteriores (N)" na
  ficha, só leitura (`renderPlanosAnteriores` em `jornada.js`). Encerrar um
  plano agora grava `data_fim` (os encerrados antes ficam sem a data).
- **Decisão do usuário (09/10/2026)**: a secretária continua **sem acesso ao
  Diário**.
- Backend: **671 testes**; front (Node): 106.

### aj) Cache do celular: versão nos endereços + aviso de nova versão (09/10/2026)
Pedido do usuário (celulares não pegavam a versão nova). Causa: em produção o
LiteSpeed entrega `/js` e `/css` com `Cache-Control: max-age=31536000` (1 ano)
e o `index.html` chamava os arquivos sempre pelo mesmo endereço.
- `backend/versao_front.py`: ao subir o app, calcula uma impressão (sha256,
  10 hex) de cada `.js`/`.css` de `frontend/js` e `frontend/css`; o
  `index.html` sai com `?v=<impressão>` em cada script/CSS local e com
  `<meta name="versao-app" content="<versão geral>">`, sempre com
  `Cache-Control: no-cache` (rotas `/` e o fallback da SPA no 404). Em
  `FLASK_DEBUG` recalcula a cada pedido. `GET /api/versao` (sem login,
  `no-store`) devolve a versão geral.
- `frontend/js/versao_app.js`: confere `/api/versao` a cada 5 min e quando o
  app volta a ficar visível/ganha foco (no máximo 1×/min); se mudou, mostra a
  faixa "Há uma nova versão do app — Atualizar" (nunca recarrega sozinho).
- **Arquivo novo em `frontend/js` ou `frontend/css`**: nada a fazer — entra na
  versão sozinho ao ser chamado pelo `index.html`. Script carregado à mão por
  JS (ex.: `vendor/xlsx`) não ganha `?v=`.
- Backend: **675 testes**; front (Node): 108. Sem migração; o deploy de sempre (`git pull` + `touch tmp/restart.txt`)
  já gera a versão nova.

### ak) Ajustes do teste de usabilidade da família e da criança (12/10/2026)
Achados do teste no celular (relatório "Panda Tech: lançamento e usabilidade").
- **Trava dos pais**: o "Voltar" do Mundo da Criança abre "Peça para um
  adulto" com uma conta simples e 3 opções (`frontend/js/trava_adulto.js`,
  `abrirTravaAdulto` em `views/crianca.js`); errou → nova conta. No modo
  criança, qualquer endereço proibido volta para `#/crianca/mundo` sem aviso
  (`router.js`).
- **Diário da família**: "EVOLUÇÃO CLÍNICA" só aparece com texto clínico;
  a mensagem vira "MENSAGEM DA EQUIPE" (família) / "MENSAGEM PARA A FAMÍLIA"
  (equipe); o selo "Compartilhado" some para a família.
- **Sequência e moeda**: `gamificacao_service.sequencia_efetiva` — sequência
  quebrada (última atividade antes de ontem) aparece como 0 ("Comece sua
  sequência!"); as "estrelas" saíram das telas: a criança, a família e a ficha
  mostram só a moeda da clínica (`xp_total` + `nomeMoeda()`).
- **Agenda da família**: `atendimento_util.rotuloStatusFamilia` — Aconteceu,
  Faltou, Falta justificada, Desmarcada, Marcada/Confirmada e "Aguardando
  registro" (dia já passou sem desfecho).
- Backend: **677 testes**; front (Node): 111.

### al) PandaUp: nome, e-mail por SMTP, Cloudflare e homologação (12/10/2026)
Spec `docs/superpowers/specs/2026-10-12-pandaup-dominio-email-homologacao-design.md`,
plano `docs/superpowers/plans/2026-10-12-pandaup-dominio-email-homologacao.md`,
roteiro do servidor `docs/operacao/pandaup-dominio-e-homologacao.md`.
- **Nome PandaUp** em todo texto que o usuário vê (front, mensagens do
  backend, PDF, cobranças, `/api/health`); `identidade_service` `app_nome`
  padrão = "PandaUp". Testes de varredura: `tests/test_nome_pandaup.py` (AST,
  strings que não são docstring) e `frontend/tests/nome_pandaup.test.js`
  (fora de comentários). Comentários e nomes de arquivo ficam.
- **E-mail** (`backend/email_service.py`): `enviar_email` por SMTP (465 SSL /
  587 STARTTLS, 10 s; nunca levanta exceção — falha vira evento
  `email_falhou`, sem a senha), `link_absoluto` (`URL_APP`), modelos
  `email_redefinicao`/`email_convite`, `enviar_convite(usuario_id, link)`.
  Sem `SMTP_HOST`, tudo como antes.
- **Esqueci minha senha**: com SMTP, manda o link por e-mail e responde
  **sempre a mesma mensagem** (conta inexistente, inativa ou excluída não
  recebe nada); sem SMTP, orienta a pedir o link à clínica; `FLASK_DEBUG`
  continua mostrando o link. Depois do envio, uma **tela de confirmação** (13/10/2026,
  `esqueci_senha_util.confirmacaoEsqueciSenha` + `views/login.js`) mostra o
  e-mail digitado, a validade e "Não chegou?", com "Enviar de novo" e "Usar
  outro e-mail"; a resposta traz `canal` (`email`/`clinica`) e
  `validade_minutos`, iguais para qualquer e-mail. Em 14/10/2026: logo do PandaUp
  (`logoPandaUp` em `views/login.js`, o panda do login) nessa tela e nas de
  link inválido/expirado, e **os dois links valem 24 horas**
  (`tokens_service.VALIDADE_*`; antes: redefinição 1 h, convite 3 dias) — os
  e-mails leem o prazo dessas constantes.
- **Convites** (criar profissional/secretária/responsável/gestor/admin e os
  "Reenviar link de acesso") devolvem `enviado_email`; a tela mostra "📧
  Convite enviado para …" (`mostrarModalConvite(link, nome, whatsapp, emailEnviado)`).
  A importação em lote não manda e-mail; clínica nova sem `gestor_email` também não.
- **Entrega dos e-mails (15/10/2026)**: os e-mails caíam no spam. Corrigido no
  código: cabeçalhos `Date` e `Message-ID` (`@<domínio do remetente>`), sem
  `Reply-To` repetido, texto puro + HTML em quoted-printable, sem emoji, assuntos
  sem "senha"/"acesso"/"convidado" ("Redefinição solicitada no PandaUp",
  "<Clínica> cadastrou você no PandaUp"; em 15/10 o usuário escolheu para o
  convite: assunto "Seu cadastro no App PandaUp foi solicitado pela <Clínica>" e
  título "Você foi cadastrado no App PandaUp!"; o topo do e-mail mostra o logo
  da plataforma, pelo endereço público, quando há logo e `URL_APP`). No DNS, o SPF publicado tinha o texto
  literal `<IP do servidor>` (inválido); o certo é
  `v=spf1 +a +mx +ip4:186.209.113.98 include:relay.mailbaby.net ~all`.
- **Cloudflare**: `ENCANTO_CLOUDFLARE=1` faz o limite de tentativas usar
  `CF-Connecting-IP`, só vindo das faixas oficiais (lista em `rate_limit.py`,
  copiada em 12/10/2026). Desligado até ligar o proxy (nuvem laranja).
- **Homologação**: `AMBIENTE=homologacao` → meta no `index.html`, faixa
  vermelha "AMBIENTE DE TESTE — dados fictícios" (`frontend/js/ambiente.js`),
  `X-Robots-Tag: noindex, nofollow` e `"ambiente"` no `/api/health`.
- **Produção**: variáveis novas (`SMTP_*`, `EMAIL_REMETENTE`, depois
  `URL_APP`/`ALLOWED_ORIGIN` no domínio novo) — passo a passo no roteiro. Sem
  migração.
- **Como o servidor está montado** (descoberto em 12/10/2026): na produção
  **não há `backend/.env`** — as variáveis ficam em cPanel → Setup Python App
  → app `panda-tech` → Variáveis de ambiente (sem aspas). Cada domínio tem a
  própria raiz (`~/pandatech.pandacriacao.com.br`, `~/app.pandaup.com.br`)
  com o bloco do Passenger no `.htaccess` apontando para `~/panda-tech` e
  **atalhos `js` e `css`** para `~/panda-tech/frontend/…` — sem eles o
  Passenger devolve 503 nos arquivos maiores que ~15 KB e a tela fica só no
  "carregando". O `index.html` passa pelo app (por causa do `?v=`).
  `app.pandaup.com.br` no ar e conferido em 12/10/2026.

### am) Logo da plataforma (14/10/2026)
- Admin → **Perfil da Plataforma** → cartão "Logo da plataforma" (prévia no
  fundo roxo do login e no fundo claro do menu; PNG/JPG/WebP, perfil de envio
  `logo`, até 2 MB no servidor). Aparece no **menu do Admin**, no **título do
  login comum** e nas **telas de recuperar acesso** (no lugar do panda). A tela
  de login própria da clínica (White Label) não muda.
- Tabela `plataforma_identidade` (linha única id = 1, `logo_base64`,
  `atualizado_em`); `plataforma_service` (`versao_logo`, `salvar_logo`,
  `remover_logo`; sem a tabela, tudo segue como sem logo). Rotas
  `PUT/DELETE /api/admin/plataforma/logo` (admin_master) e
  `GET /api/publico/plataforma/logo?v=` (cache de 1 ano; a versão muda com o
  logo). O `index.html` leva `<meta name="logo-plataforma" content="<versão>">`;
  o front lê com `marca_plataforma.js` (`versaoLogoPlataforma`,
  `htmlLogoPlataforma`).
- **Logo para o login** (15/10/2026): segundo envio no mesmo cartão, versão com
  letras brancas só para o fundo roxo do login (coluna `logo_login_base64`;
  tipos `principal`/`login` em `plataforma_service`; rotas
  `/api/admin/plataforma/logo-login` e `/api/publico/plataforma/logo-login`;
  meta `logo-plataforma-login`; `marca_plataforma.logoParaLogin`). Sem ele, o
  login usa o principal; o resto (menu, e-mails, recuperar acesso) sempre o
  principal.
- Migração: `backend/migracoes/migracao_logo_plataforma.sql` ou
  `migrar_logo_plataforma.py` (cria a tabela e a coluna do login; seguro rodar
  de novo). Backend: **764 testes**; front (Node): 121. **Aplicada em produção** e os dois
  logos enviados (conferido em 15/10/2026). Também em 15/10: o e-mail do
  responsável ficou sem a lista de sugestões (PR #63) e o Mercado Pago da
  plataforma foi salvo de novo com o "Testar conexão".

### an) Guia de Primeiros Passos + correções achadas nele (20/10/2026)
- **Guia em PDF para clínicas novas** (fora do repositório):
  `D:\Projeto Viva\Panda Tech\material de tutorial\PandaUp - Guia de Primeiros Passos.pdf`,
  gerado de `guia-primeiros-passos-pandaup\guia.html` (capturas numeradas;
  PDF pelo Chrome headless `--print-to-pdf`). Telas mudaram? Refaça as
  capturas afetadas e gere de novo.
- **"Dia N/7" fixo** no aviso do "Marquei hoje!" da criança: o
  `POST /jornada/missao/<id>/concluir-dia` devolve `dias_exigidos` e a tela
  usa esse número (`crianca.js`).
- **Telefone fixo aceito** em todo campo com máscara de telefone
  (`util.js: MASCARAS_CAMPO.telefone`): até 10 dígitos formata
  "(11) 3333-4444", no 11º vira "(11) 9 8888-7777". Antes só celular, e o
  "Telefone da clínica" em Configurações não salvava com fixo.
- `seed.py`: título dos planos com o mês em português (`MESES_PT`; o
  `strftime("%B")` saía "October" no Windows).
- Testes: `backend/tests/test_correcoes_guia_20_10_2026.py`,
  `frontend/tests/mascara_telefone.test.js`. Sem migração.

### ao) Levar quem criou a senha para a tela de entrar (26/10/2026)
Pedido do usuário: as famílias guardavam o link de convite (uso único) como se
fosse o endereço do app e caíam em "Link expirado ou já usado → Solicite um
novo link".
- `identidade_service.login_relativo_da_clinica` / `login_relativo_do_usuario`:
  `#/entrar/<endereco>` com White Label no ar (mesma regra das rotas
  públicas), senão `#/login`.
- `GET /api/auth/validar-token-redefinicao/<token>` devolve `login` sempre e,
  quando não vale, `motivo` (`usado`/`expirado`/`invalido`) — nunca dado da
  pessoa.
- Tela do link que não serve mais (`views/login.js: mostrarLinkIndisponivel`):
  "Sua senha já foi criada!" / "Este link venceu" / "Link inválido", com
  **[Entrar no PandaUp]** (login da clínica) e "Esqueci minha senha" como
  opção menor. Depois de criar/trocar a senha (`mostrarSenhaCriada`): "Pronto!
  Sua senha foi criada" + "Daqui para frente, entre sempre por …" (copiar) +
  [Entrar agora], que abre o login com o e-mail preenchido
  (`sessionStorage` `pandaup_email_entrar`).
- E-mails de convite e de nova senha ganham o bloco "Importante: este link
  serve só para criar a senha e funciona uma vez. Depois, entre sempre por …".
- Pop-up do convite: botão **"💬 Copiar mensagem para o WhatsApp"** (texto com
  os dois endereços). Funções puras em `frontend/js/acesso_util.js`.
- O modelo do WhatsApp automático (API da Meta) não mudou: o texto é aprovado
  pela Meta; mudar exige um modelo novo.
- Sem migração.

### ap) Configurações: "Seus dados" num cartão e Procedimentos dentro dela (26/10/2026)
Pedido do usuário (prévia aprovada: artifact "Prévia Configurações e Prontuário").
- **"📇 Seus dados"**: o antigo "Contato (decisor na clínica)" e o "Atuar
  também como profissional" viraram um cartão (`#cartao-seus-dados`), com um
  botão **"Salvar meus dados"** que grava o perfil e, conforme a chave, liga
  (com especialidade) ou desliga o "atuar como profissional". A chave só
  mostra/esconde os campos.
- **Procedimentos saíram do menu**: caixa resumida em "🏢 Dados
  institucionais", abaixo das Especialidades (`renderCaixaProcedimentos`), e a
  tabela de edição num pop-up (`abrirModalProcedimentos`, com Salvar próprio e
  aviso de alteração não salva; fica fora do rascunho automático de
  `modais.js` via `data-modal-preparado`). `#/gestor/procedimentos` leva para
  `#/gestor/configuracoes?procedimentos=1`, que abre o pop-up.
- **Importação do prontuário**: etapas 1 e 2 feitas no item 5aq; etapa 3 =
  documentos em PDF (área nova), depois. O sistema de origem das clínicas é
  desconhecido.
- Só front, sem migração.

### aq) Importação do prontuário: Ficha Clínica e histórico de evoluções (26/10/2026)
Spec `docs/superpowers/specs/2026-10-26-importacao-prontuario-design.md`,
plano `docs/superpowers/plans/2026-10-26-importacao-prontuario.md`.
- **Importar Pacientes** virou duas abas ("Pacientes e Ficha Clínica" e
  "Histórico de evoluções"), cada uma com modelo Excel/CSV e prévia.
- **Ficha na planilha de pacientes**: colunas opcionais `diagnostico`,
  `alergias`, `medicamentos_em_uso`, `profissionais_externos` (2.000 cada) e
  `observacoes_clinicas` → `fichas_clinicas.observacoes_equipe` (5.000); acima do
  limite = erro na linha (`importacao_bp.CAMPOS_FICHA`).
- **"🔒 Observações da equipe"** (pedido do usuário, 26/10/2026): campo novo
  da ficha (`fichas_clinicas.observacoes_equipe`), editável no pop-up da ficha
  e nunca enviado à família (`pessoas_bp.obter_ficha_clinica` tira o campo e
  calcula `preenchida` só com `CAMPOS_FICHA_FAMILIA`). PUT sem a chave mantém
  o valor. Antes da migração (`coluna_observacoes_equipe_existe`), a ficha
  funciona sem o campo e a coluna `observacoes_clinicas` da planilha dá erro
  na linha.
- **Paciente que já existe não duplica**: mesmo nome + nascimento, sem
  acento/maiúsculas/espaços extras (`importacao_service.normalizar_nome`),
  entre os pacientes da clínica **ativos ou arquivados** (o arquivado continua
  arquivado). Completa só os campos **vazios** da ficha (`_completar_ficha`).
  Homônimos (mais de um) → erro. Mesmo paciente duas vezes no lote: a 2ª linha
  vira "existente". Para o existente, o responsável é opcional e **e-mail
  diferente do cadastrado nunca é vinculado** (aviso; vincular pela ficha). O
  confirmar devolve `criados` (novos) e `atualizados` (existentes).
- **Evoluções → Diário**: `POST /api/importacao/evolucoes/preview|confirmar`
  (gestor/admin, módulo `importacao_pacientes`, até 1.000 linhas por envio — a
  tela divide arquivos maiores e mostra o progresso). Colunas `paciente_nome`,
  `paciente_nascimento`, `data_atendimento` (AAAA-MM-DD ou DD/MM/AAAA, não no
  futuro pela data de Brasília), `profissional_email`, `profissional_nome`,
  `evolucao` (10.000), `observacao` (5.000). Profissional pelo e-mail
  (profissional/gestor da clínica, arquivado sim, excluído não); sem achar, o
  autor é quem importa e o texto começa com "Profissional no sistema
  anterior: …". Grava `origem = 'importacao'`, `compartilhado_familia = 0`,
  sem notificação, num `db.em_lote()` (erro no meio → 500, nada gravado).
- **Sem duplicar**: `importacao_chave` = sha256(paciente + data + texto
  original), também quando o registro foi editado depois; repetida = "já
  importada". Selo "Importado · 🔒 Só a equipe vê" no Diário e na ficha
  (`importacao_util.seloDiarioImportado`). O **ICT ignora** importados.
- **Antes da migração** nada quebra: `importacao_service.colunas_diario_importacao_existem`
  (ICT e ficha só usam a coluna se ela existir); a aba de evoluções responde
  503 "precisa de uma atualização do banco".
- Auditoria: `importar` / `pacientes` | `evolucoes`, "<n> registros".
- Migração: `backend/migracoes/migracao_importacao_prontuario.sql` ou
  `migrar_importacao_prontuario.py`. Testes:
  `backend/tests/test_importacao_prontuario.py`,
  `frontend/tests/importacao_util.test.js`.

### ar) App instalável no celular (29/10/2026)
Pergunta do usuário: instalar o PandaUp como app (iPhone e Android) para
famílias e crianças. Resposta: **app web instalável (PWA)**, sem lojas — App
Store recusa site empacotado e a categoria infantil é rígida; Google Play
(TWA) fica para depois do piloto, se pedirem.
- **Manifest e ícones do PandaUp** servidos pelo app (`publico_bp`:
  `/api/publico/app/manifest.webmanifest` e `/api/publico/app/<ícone>.png`,
  arquivos em `backend/assets/app/`, gerados do panda quadrado enviado pelo
  usuário) — não como estático, porque o servidor só tem atalhos para `/js` e
  `/css`. `index.html` com `manifest`, `apple-touch-icon`, `theme-color` e
  metas `apple-mobile-web-app-*`. `util.linksIdentidade` agora sempre devolve
  um manifest (o da clínica com White Label, senão o do PandaUp) e
  `iconeApple`.
- **Botão "📲 Instalar o app"** (`frontend/js/instalar_app.js`): cartão no
  início da família (some com "Agora não", `localStorage`
  `pandaup_instalar_dispensado`, e quando já aberto pelo ícone) e botão fixo
  no Perfil. Android com `beforeinstallprompt` abre a instalação do Chrome;
  iPhone (e Android sem o evento) mostra o passo a passo
  (`comoInstalar`/`passosInstalar`, testados em
  `frontend/tests/instalar_app.test.js`). A criança usa o mesmo app, pelo modo
  criança.
- Sem service worker (o Chrome já instala sem ele; evita cache velho brigando
  com o `?v=`). No iPhone, o app instalado não herda o login do Safari: entra
  de novo uma vez.
- Sem migração. Testes: `backend/tests/test_app_instalavel.py`.

### as) Pandoo — Cruzadinha (29/10/2026)
Spec `docs/superpowers/specs/2026-10-29-pandoo-cruzadinha-design.md`, plano
`docs/superpowers/plans/2026-10-29-pandoo-cruzadinha.md` (prévia aprovada:
artifact "Prévia Cruzadinha Pandoo"). Sem migração.
- **Modelo `cruzadinha`**: de **2 a 10** figuras (`pandoo_service.LIMITES_ITENS`;
  os outros modelos seguem 2 a 24), palavra obrigatória com só letras, hífen e
  espaço, **2 a 12 letras** (hífen/espaço não contam), sem repetir. Regras:
  `formas` (`teclado`, `letras`, `figuras` — o profissional libera uma ou mais e
  a criança troca no palco, guardando as palavras feitas), `primeira_letra`,
  `voz` (ao tocar na figura), `voz_acertar`, `som` e **`grade`**.
- **A grade é montada no editor e guardada** em `regras.grade`
  (`{linhas, colunas, palavras: [{item_id, linha, coluna, direcao}]}`, até
  15×15); o backend confere (`_checar_grade`: cada item uma vez, mesma letra
  nos cruzamentos, nada cruza hífen/espaço) e grade velha dá 400 "arrumação
  desatualizada". O editor remonta sozinho quando as palavras mudam e tem
  "🔀 Sortear outra"; palavra sem letra em comum fica solta, com aviso.
- **Regras puras** em `frontend/js/pandoo/cruzadinha_core.js` (gerador,
  numeração, `palavraAoTocar` — número escolhe a palavra que começa nele —,
  colocar/apagar/conferir, banco de letras, opções de figura), testadas em
  `frontend/tests/pandoo_cruzadinha.test.js`; jogo em
  `frontend/js/pandoo/jogos/cruzadinha.js`. "conseguiu" = palavra sem erro
  antes; palavra completada errada por tabela (cruzada) não conta erro.
- **Teclado do celular**: `<input>` invisível no palco (16 px, sem
  autocorreção) com um espaço sentinela, para o "apagar" do Android chegar
  como `inputType` delete; a letra vem do `input`, não do `keydown`.
- **Editor**: contadores sempre à vista (pedido do usuário) — "N de 10
  palavras" (botão vira "Máximo de 10 palavras") e "N de 12 letras" em cada
  palavra, vermelhos quando passam. `limitesDoModelo(modelo)` em
  `pandoo_core.js` substitui o `PANDOO_LIMITES` fixo no editor.
- Revisão final: palavras não podem encostar (os dois validadores conferem que
  toda sequência de 2+ casas é uma palavra — "GATOS" + "PATO" não viram
  "GATOSPATO"); o seletor de figuras ignora toques nos primeiros 350 ms; a
  composição do teclado do Android é lida pela diferença do campo
  (`diferencaDoInput`) — **ainda não testada num Android de verdade**.
- Backend: **861 testes**; front (Node): 171.

### at) robots.txt contra robôs de IA (03/11/2026)
Pergunta do usuário: como impedir que uma ferramenta de IA copie o sistema.
`GET /robots.txt` (`app.py: ROBOS_DE_IA`, `_texto_robots`): em produção,
`Disallow: /` para os robôs de IA (GPTBot, ClaudeBot, Google-Extended, CCBot,
PerplexityBot, Bytespider etc.) e só `/api/` fechado para os buscadores
comuns; na homologação, `Disallow: /` para todos (mais o `X-Robots-Tag` que
já existia). É um **pedido**: robô mal-intencionado ignora. A exposição maior
continua sendo o **repositório público** (regra 1) — a recomendação dada foi
torná-lo privado quando o usuário liberar (o servidor passa a precisar de
chave para o `git pull`), ligar a proteção contra robôs da Cloudflare e
registrar software e marca no INPI, com termos de uso junto da LGPD. Testes:
`backend/tests/test_robots.py`. Sem migração.

### au) Pandoo — "Toque só no alvo" (05/11/2026)
Spec `docs/superpowers/specs/2026-11-05-pandoo-toque-no-alvo-design.md`, plano
`docs/superpowers/plans/2026-11-05-pandoo-toque-no-alvo.md` (prévia das fases
aprovada na conversa). Sem migração. Primeiro jogo pensado para **psicologia e
TO** (TDAH: controle do impulso e atenção) — pedido do usuário para ter modelos
prontos dessas áreas no período de teste; ele ainda vai mostrar aos
profissionais e ajustar.
- **Modelo `alvo`** (🎯): figuras aparecem e a criança toca só na figura-alvo.
  **3 fases**, uma evolução da outra: 1) uma de cada vez no meio; 2) saindo de
  6 tocas (até 2 juntas); 3) passando pela tela (até 3). Regras: `alvo_item_id`,
  `frase_inicio` (até 40, por causa do artigo: "Toque só **na** bola"),
  `fase_inicio`/`fase_fim`, `subir_sozinho` (passa quem toca ≥ 70% dos alvos com
  ≤ 3 toques errados; senão a partida termina ali), `figuras_por_fase` (10–60,
  ~1 alvo a cada 3), `velocidade` (lenta/media/rapida), `som`. **Sem `voz`**: o
  comando é sempre falado (abertura, troca de fase e toque no modelo do topo;
  `PandooSom.falarComando`: frase pela voz do navegador + gravação do alvo).
- **Resultado**: cada figura vira um detalhe com `alvo`, `tocou`, `fase`,
  `tempo_ms`; o servidor confere tudo pelo `alvo_item_id` do jogo
  (`calcular_resultado(detalhes, modelo, regras)`). **`total_rodadas` = figuras
  tocadas**: partida só com figuras passando não libera a missão nem trava o dia.
  `GET /pandoo/resultados` traz `medidas` (`medidas_alvo`) e o jogo fica fora do
  "por figura"; a ficha mostra fase, alvos, perdidos, toques errados e reação.
- **Palco, para todos os jogos**: `registrar(item, res, {silencioso, extra})`,
  `def.houveJogada(detalhes)` e `def.resumo(...)` opcionais; "Finalizar" sem
  jogada fecha direto **também na prévia**.
- Regras puras em `frontend/js/pandoo/alvo_core.js` (testes
  `frontend/tests/pandoo_alvo.test.js`); jogo em `jogos/alvo.js`; testes do
  backend em `backend/tests/test_pandoo_alvo.py`.
- Backend: **881 testes**; front (Node): 183.
- **Ajustes de 07/11/2026** (pedido do usuário, depois de testar na homologação):
  a frase do comando pode ter **voz gravada ou enviada** (`regras.frase_audio`,
  até 600 KB, validada como os áudios das figuras; no editor usa os mesmos
  botões das figuras com o id `__frase__`): toca no lugar da voz do aparelho e
  depois vem a voz ou a palavra do alvo (`falarComando(..., {fraseAudio})`);
  **X vermelho** em cima da figura tocada por engano (`.pda-x`, além do som);
  regra de subida passou de 80%/1 erro para **70%/3 erros**. Sem migração.

### av) Financeiro etapa 1 — cobrança das famílias (08/11/2026)
Spec `docs/superpowers/specs/2026-11-07-financeiro-clinica-design.md`, plano
`docs/superpowers/plans/2026-11-07-financeiro-etapa1-cobranca.md`. Etapas 2 e 3
na seção 7.
- **PASSO MANUAL ANTES DO DEPLOY**: rodar a migração
  `backend/migracoes/migracao_financeiro_cobranca.sql` (SQL Editor do Supabase)
  ou `backend/migrar_financeiro_cobranca.py` (conferir `(Postgres)` no fim, ver
  7.2) **antes** do `git pull` + restart: a agenda de todas as clínicas passa a
  depender das tabelas/colunas novas. **Rodar a migração de novo depois do
  restart**: consultas criadas entre a migração e o pull ficam sem especialidade
  (ela é segura para rodar de novo). Cron opcional:
  `backend/gerar_cobrancas_clinicas.py` (1×/dia; as telas já sincronizam sozinhas).
- **Acordo por paciente e especialidade** (`acordos_pagamento`,
  `acordos_service.py`): `'*'` = todas as especialidades; o específico vence o
  `'*'` (`cobranca_regras.escolher_acordo`). Três tipos: **avulsa** (por
  consulta, quinzenal ou mensal), **mensalidade** (proporcional aos dias do mês
  em que o acordo vale, `mensalidade_do_mes`) e **pacote** (N sessões por um
  valor, em parcelas; cada sessão aparece como "sessão N de M").
- **Sincronização** (`cobranca_service.sincronizar`): agenda → cobranças,
  **idempotente**, num `db.em_lote()` (tudo ou nada; corrida cai no índice único
  e a outra rodada vale). Roda ao abrir as telas do financeiro. **Nunca chamar
  `sincronizar` dentro de outro `em_lote`.** Sessões entram como itens
  (`cobranca_itens`); `realizada` cobra, `faltou` só com `fin_cobrar_falta`.
- **Rascunho → conferir → liberar** (só a cobrança de **período**, ou seja,
  avulsa quinzenal/mensal): nasce `rascunho` (na conferência dá para tirar sessões
  e dar desconto com motivo; o valor de cada sessão não se edita) e só vira
  cobrança de verdade ao **liberar** (depois que o período terminou). Avulsa **por
  consulta**, **mensalidade** e **parcelas de pacote** nascem direto `pendente`. O
  vencimento (`_vencimento_minimo`, `PRAZO_MINIMO_DIAS = 5`) vira hoje + 5 dias, se
  a data calculada já tiver passado, na geração da avulsa por consulta e da
  mensalidade **e ao liberar**. **Período liberado não reabre**: se a agenda muda
  depois, a cobrança fica com `revisar` + motivo e **o gestor resolve** (a rota de
  resolver é só do gestor/admin). **Sem acordo** ou **sem valor** não geram cobrança: viram
  **pendências** (`GET /financeiro/pendencias`, só gestor), onde se escolhe cobrar
  ou "não cobrar" (só gestor; `consulta_decisao_cobranca`).
- **Baixa**: manual (`/pagar`) com **baixa parcial**; **estorno só do gestor**,
  com motivo; `_travar_cobranca` trava a linha contra baixa dupla. O webhook do
  Mercado Pago grava o **valor recebido** e deduplica por
  `pagamentos.mp_payment_id`. Cobranças vencidas são marcadas sozinhas.
- **Quem vê o quê**: gestor e secretária têm a tela de cobranças, a baixa e os
  acordos; **configuração (`/financeiro/config`) e pendências só gestor**;
  profissional não vê dinheiro; responsável vê só as cobranças liberadas do
  filho (sem rascunho/cancelada). A secretária vê o extrato do paciente **só
  nessa rota** (`auth.paciente_acessivel` não mudou; o Diário segue fechado).
  Dívidas abertas anteriores ao período filtrado **sempre aparecem**.
- Telas: `frontend/js/views/financeiro.js` (cobranças, configuração, pendências),
  `views/financeiro_ficha.js` (acordos e extrato na ficha do paciente) e
  `financeiro_util.js` (funções puras). Os **pop-ups de dinheiro** usam
  `data-modal-preparado` e ficam **fora do rascunho automático** de `modais.js`.
- `cobranca_regras.ratear_desconto` e `organizacoes.fin_repasse_falta` já
  existem de olho na etapa 3 (repasse).
- **Decisões da revisão final (08/11/2026)**, testes em
  `test_financeiro_revisao_final.py` e `tests_postgres/test_smoke_financeiro.py`:
  - **Incluir sessões num acordo novo não recua o início**
    (`consulta_acordo_incluida`: `incluida = 1` entra, mesmo fora da vigência;
    `incluida = 0` foi desmarcada na vigência e continua "sem acordo"). No pop-up
    nada vem marcado e aparece quantas sessões e a soma. Sem `incluir_consultas` na
    API, vale só a vigência; `[]` deixa todas de fora. Mensalidade: a incluída fica
    coberta, sem gerar meses antes do início; avulsa: vira item; pacote: consome.
  - **`status_origem`** (em `cobranca_itens` e `acordo_pacote_consumo`) guarda o
    status que a cobrança reconhece. Realizada que virou falta com `fin_cobrar_falta`
    desligado deixa de contar (sai da avulsa/rascunho; paga ou liberada vira `revisar`;
    pacote devolve a sessão). Desligar a chave não desfaz falta já cobrada. Se o status
    novo ainda é cobrável, a origem acompanha.
  - **Fim da mensalidade** (encerrar ou Editar, `acordos_service._ajustar_mensalidades`):
    mês afetado sem pagamento recalcula (valor 0 cancela e volta se o fim for
    estendido; cancelada à mão não volta), com pagamento vira `revisar`. Encerrar
    recusa data futura e depois do fim atual (fim futuro é com Editar). A conta usa o
    preço com que o mês foi gerado (`cobrancas.mensalidade_preco_centavos`); mudar o
    preço do acordo só vale para os meses seguintes.
  - **Sessão "de fora"**: `consulta_acordo_incluida` guarda só a última decisão, então
    `incluida = 0` tira a sessão daquele acordo e de todos os anteriores a ele; só um
    acordo mais novo pode cobri-la. Efeito aceito: se um acordo anterior ganhar vigência
    depois (fim estendido) ou o pacote devolver uma vaga, a sessão continua nas
    pendências, sem cobrança automática, e o gestor resolve.
  - **Data de corte** (`organizacoes.fin_cobrar_desde`, Configurações → Financeiro, só
    gestor; NULL = todas): sessão antes dela não gera cobrança nem pendência e não entra
    em acordo (`acordos_service.sessoes_que_contam`). Cobrança já criada não muda. A
    mensalidade não olha o corte: gera os meses desde o início do acordo. A data começa
    em branco (o gestor escolhe), e as pendências lembram que ela existe.
  - **Reembolso ou contestação no Mercado Pago**: a baixa **não** é desfeita (decisão do
    usuário). `pagamento_service._alertar_reversao`, em transação própria depois da baixa,
    marca `revisar` e notifica os gestores (tipo `cobranca_familia`, leva ao Financeiro),
    uma vez por acontecimento (dedupe pela auditoria), só com baixa ativa daquele
    `mp_payment_id`. Reembolso parcial segue `approved` com `transaction_amount_refunded`.
    Falha no alerta nunca desfaz a baixa. O sino guarda só 5 notificações, mas o aviso na
    cobrança fica.
  - **Pacote encerrado antes do fim**: as parcelas seguem em aberto; depende do contrato
    (decisão do usuário), e o gestor cancela as não pagas se for o caso.
  - **Desconto em cobrança aberta**: `POST /financeiro/cobranca/<id>/desconto`, só
    gestor/admin, com motivo e nunca abaixo do que já foi pago; botão "Dar desconto"
    nos detalhes.
  - **Pacote esgotado não trava**: criar acordo na mesma especialidade encerra o
    pacote esgotado (fim = hoje); outro conflito dá 409 pedindo para encerrar na ficha.
  - **PIX**: `gerar-pix` para gestor/secretária/admin (outra clínica = 404) e
    responsável do filho com financeiro visível; profissional 403; saldo 0 = 409. A
    chave de idempotência leva o saldo. **QR anterior**: o webhook acha a clínica pela
    assinatura (`organizacao_id_por_assinatura`) e a cobrança pelo `external_reference`.
    Recebido acima do saldo registra e marca `revisar`. `pago_em` do webhook = data de
    Brasília da aprovação + ` 12:00:00`, como a baixa manual.
  - **Editar consulta já cobrada** (`aplicar_edicao_da_consulta`): a data vai para o
    item e renumera o pacote; trocar procedimento atualiza rascunho ou avulsa sem
    pagamento, senão vira `revisar`. Consulta `realizada` continua sem edição (409).
  - Na tela, aviso de que "Em aberto" e "Vencido" incluem dívidas anteriores ao período;
    "Recebido" respeita a especialidade; `/conferir` trava a cobrança; decisão recusa
    sessão futura ou já consumida; só avisa da liberação quem vê o financeiro; o
    indicador `pagamentos_hoje` ignora estornados.
- Testes: `test_cobranca_regras.py`, `test_cobranca_sincronizar.py`,
  `test_cobranca_baixa.py`, `test_cobranca_listagens.py`,
  `test_acordos_pagamento.py`, `test_financeiro_cobranca_schema.py`,
  `test_idor_financeiro.py`, `test_financeiro_revisao_final.py`,
  `frontend/tests/financeiro_util.test.js`.
  Backend: **1125 testes passando**; front (Node): 195.
- **Ajustes do teste na homologação (09/11/2026, PR #82)**: no pop-up do acordo, o cartão do
  tipo escolhido mostra a descrição em branco; Mensalidade e Pacote têm **"Calcular pelo
  procedimento"** (preço × sessões por mês ou sessões do pacote, `financeiro_util.valorPorProcedimento`;
  só aparece para quem recebe os preços, o gestor; o valor continua editável). Na Agenda, a prévia da
  repetição avisa quando os meses desmarcados fazem a série saltar
  (`repeticao_util.saltosDaSerie`; ex.: só "Nov" marcado e 4 consultas → a 4ª cai no ano seguinte —
  é a regra, não erro). Front (Node): 198. **Mesclado em `main` em 09/11/2026.**

### aw) Financeiro etapa 2 — fechamento de caixa (09–11/11/2026)
Spec `docs/superpowers/specs/2026-11-07-financeiro-clinica-design.md` (seção 5), plano
`docs/superpowers/plans/2026-11-09-financeiro-etapa2-caixa.md`. **Sem migração.**
- **Só gestor** (e admin): botão "🧾 Fechamento de caixa" no topo do Financeiro →
  `#/gestor/financeiro/caixa` (`views/financeiro_caixa.js`). Período (padrão hoje;
  atalhos Hoje/Ontem/Este mês; até 1 ano), filtros "Quem recebeu" e "Forma", KPIs
  Recebido/Estornado/Líquido, cartões por forma e por quem recebeu, lista dos
  recebimentos (estornado riscado, com selo) e dos estornos; **PDF** (servidor,
  `caixa_pdf.py`, com o logo da clínica — logo quebrado não derruba) e **Excel**
  (navegador, `financeiro_util.planilhasCaixa`: abas Resumo, Recebimentos e Estornos,
  valores em reais como número).
- Rotas `GET /api/financeiro/caixa` e `/caixa/pdf` (`?de&ate&recebido_por&forma`);
  regra em `caixa_service.fechamento` / `validar_periodo`. Só leitura, sem auditoria.
- **Estorno = saída no dia do estorno** (decisão aprovada pelo usuário): Recebido =
  pagamentos com `pago_em` no período (inclusive os estornados depois, marcados);
  Estornado = `estornado_em` no período, na forma e em "quem recebeu" do pagamento
  original; Líquido = Recebido − Estornado. O caixa de um dia passado não muda.
- **`pagamentos.pago_em` e `estornado_em` são horário de Brasília** desde esta etapa
  (`ausencias_service.agora_brasilia_iso()`): a baixa manual sem data caía no padrão
  UTC do banco (depois das 21h ia para o dia seguinte) e o estorno gravava UTC. Linhas
  antigas não foram convertidas. Na tela, use `formatarDataHoraLocal`.
- "Quem recebeu" vazio = "Não informado"; o Pix automático grava "Mercado Pago".
- O carregador do Excel virou compartilhado: `util.carregarBibliotecaExcel()` (a
  importação usa o mesmo).
- Testes: `backend/tests/test_financeiro_caixa.py`, `frontend/tests/financeiro_util.test.js`.

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

- **Pandoo**: jogo é exercício `tipo='jogo'` + `pandoo_jogos`; novo
  modelo de jogo = entrada em `pandoo_service.MODELOS` + validação própria
  no backend e um arquivo em `frontend/js/pandoo/jogos/` que chama
  `registrarJogo(codigo, {nome, icone, requisitos, iniciar(palco, conteudo, regras)})`.
  O jogo só desenha na `palco.area` e chama `palco.registrar(item, "conseguiu"|"treinar")`
  / `palco.finalizar({encerradoAntes})`; salvar, som, cenário e resumo são do
  palco. Módulo comum (plano ou extra da clínica); jogar numa missão não
  depende do módulo.

- **Identidade da clínica (White Label)**: quem decide o que vale é
  `identidade_service.identidade_efetiva`; o `/auth/me` já devolve a
  identidade efetiva, então tela nova só lê `Sessao.usuario.organizacao`
  (nunca checa o módulo por conta própria). Imagem da identidade vai por URL
  pública (`/api/publico/clinica/<endereco>/...?v=<versao_imagens>`).

- **Planos e módulos**: quem manda é o banco (`planos_modulos` +
  `plano_base_id`), não o código. Módulo novo = entrada em
  `modulos_service.MODULOS_OPCIONAIS` (aparece sozinho na tela de planos,
  desmarcado) + a trava nas rotas com `modulo_ativo_para_clinica`.

- **Envio de arquivo**: campo novo de upload usa `prepararArquivoParaEnvio`
  / `renderOrientacaoEnvio` com um perfil de `PERFIS_ENVIO` (crie um perfil
  se precisar) — nunca `FileReader` + limite solto. Não use
  `URL.createObjectURL` para mostrar imagens: a CSP bloqueia `blob:`.

- **Fundo escuro da clínica**: o texto sobre o fundo fica branco sozinho (`contraste_fundo.js`, item 5bb).
  Não crie regras de cor por seletor para isso; um elemento com fundo próprio (alfa ≥ 0,6) protege o que
  está dentro dele.

- **Cache do front-end**: produção guarda JS/CSS por 1 ano; quem garante a
  atualização é o `?v=` que `versao_front.py` põe no `index.html` (seção 5aj).
  Não sirva o `index.html` por outro caminho sem passar por `_index_html`.

- **Grade da agenda** (`frontend/js/agenda_faixa.js`): funções puras, sem
  DOM, testadas em `frontend/tests/agenda_faixa.test.js`.
  `calcularFaixaAgenda` decide a faixa: o horário da clínica, ou
  08:00–18:00 no automático, esticada por consultas fora dela.
  `minutoNaFaixa` converte clique/soltar em horário, de 15 em 15 min.
  `agenda.js` posiciona tudo em % dessa faixa. Mudou a grade? Mexa aqui e
  nos testes.

- **E-mail**: toda mensagem sai por `email_service` (`enviar_email` ou
  `enviar_convite`), que nunca derruba a rota — quem chama só olha o
  `True/False`. Link em e-mail sempre absoluto (`link_absoluto`, precisa de
  `URL_APP`). Texto do usuário no HTML do e-mail sempre com `html.escape`.

- **Dois canais de cobrança não podem se sobrepor**: clínica com assinatura
  recorrente **ativa** é pulada pelo ciclo mensal comum
  (`gerar_cobrancas_mensais`, cron ou botão "Gerar cobranças agora") — é o
  próprio Mercado Pago que cobra, e o webhook registra a cobrança
  (`_tem_assinatura_recorrente_ativa`). Qualquer mudança no ciclo mensal
  precisa manter essa regra.

- **IA**: `backend/ia_service.py` é o **único** lugar que fala com fornecedores de IA (cota do mês, registro
  em `ia_uso`, chamada de transcrição); rota e tela nunca chamam a OpenAI direto. Trocar de fornecedor ou
  modelo = mexer só nele. O áudio nunca é guardado (só passa pela memória do pedido) e o texto ditado nunca
  vai para log, auditoria nem mensagem de erro. Veja o item 5bc.

### ax) Financeiro etapa 3 — repasse aos profissionais (12–16/11/2026)
Spec `docs/superpowers/specs/2026-11-07-financeiro-clinica-design.md` (seção 6, itens 6.1 a 6.4), plano
`docs/superpowers/plans/2026-11-12-financeiro-etapa3-repasse.md`.
- **Migração `backend/migracoes/migracao_financeiro_repasse.sql` — já aplicada em produção (conferido em
  16/11/2026 no Supabase); nada a fazer.** Ela criou `regras_repasse`, `repasses`, `repasse_itens`,
  `repasse_ajustes` e `organizacoes.fin_repasse_base` (e as colunas `repasse_ajustes.dispensado_em`,
  `repasse_itens.acordo_id` e `repasse_itens.mes`); idempotente (`backend/migrar_financeiro_repasse.py` faz o
  mesmo, só para banco novo).
- **Só gestor** (e admin): regras, base, relatório, ajustes e fechamentos. Secretária, profissional e
  responsável recebem 403 (o profissional não vê nem o próprio repasse). Valores em centavos; percentual em
  centésimos de ponto (`6500` = 65%).
- **Regras** (`regras_repasse`, `repasse_regras.py`): por profissional, padrão + exceções por procedimento
  e/ou tipo de acordo (avulsa/mensalidade/pacote); vale procedimento+tipo > procedimento > tipo > padrão.
  Percentual ou valor fixo por sessão. **Base** em Configurações > Financeiro (`repasse_base`):
  `procedimento` (valor da sessão) ou `rateado` (pacote/mensalidade divididos entre as sessões).
- **Relatório** (`repasse_service.relatorio`, só leitura; `GET /api/financeiro/repasse`): sessões pagas pela
  família e ainda não repassadas, com PDF (`repasse_pdf.py`) e Excel (`financeiro_util.planilhaRepasse`).
  "Marcar como pago" (`fechar`) grava o fechamento com os valores do dia (mudar a regra depois não mexe);
  `UNIQUE(consulta_id)` impede pagar a mesma sessão duas vezes (409). Ajustes manuais entram no próximo
  fechamento. Telas: `frontend/js/views/financeiro_repasse.js` (`#/gestor/financeiro/repasse` e `.../regras`),
  botão "💼 Repasse aos profissionais" no Financeiro e "💼 Repasse" na linha do profissional da Equipe.
- **Decisões 1–7 (do construtor, para o usuário conferir)**: (1) 0% e R$ 0,00 são regras válidas ("sem
  repasse"), distintas de "a definir"; (2) profissional da sessão = `consultas.profissional_id`; (3) estorno
  depois do repasse pago cria um **ajuste negativo pendente** (origem `estorno`, uma vez por sessão);
  (4) **desfazer fechamento** (gestor, com motivo) devolve as sessões ao relatório e os ajustes a pendentes;
  (5) entram sessões pagas até o fim do período (inclusive meses anteriores), "aguardando" lista só as do
  período; (6) mensalidade sem cobrança do mês fica "aguardando"; (7) outros relatórios (6.5) ficam para depois.
- **Regras de borda decididas nas revisões**: base `rateado` de uma mensalidade espera o fim do mês e divide
  o que ainda não foi repassado do mês; sessão incluída antes do início da mensalidade vai para o 1º mês;
  o ajuste de estorno pode ser **dispensado** (`dispensado_em`, a linha fica e não é recriada) e o manual é
  apagado; **desfazer** apaga os ajustes de estorno pendentes daquele fechamento. Na tela, com filtro de especialidade ligado, "Marcar como pago"
  fica desligado (o fechamento é do profissional todo).
- **Revisão final (16/11/2026)** — o repasse nunca passa do que a família pagou:
  - `repasse_itens` guarda `acordo_id` (pacote/mensalidade) e `mes` (1º dia, mensalidade). **Pacote**: o pago
    libera N sessões; as já repassadas (itens daquele acordo) gastam as primeiras vagas e as que sobram vão para
    as não repassadas em ordem de data — a renumeração (sessão registrada atrasada, finalizada que virou falta)
    não libera vaga a mais. A soma das bases do pacote **nunca passa do valor líquido** (nas duas bases, também
    com desconto dado depois de um repasse). **Mensalidade rateada**: o "já repassado" do mês vem dos itens
    gravados (acordo + mês), qualquer que seja o status atual da sessão. Mensalidade com base `procedimento`
    agora **também tem teto** (ver conciliação abaixo). Estorno no pacote: a repassada perde o
    "pago" só se o pago liberar menos sessões do que as repassadas, e saem as mais recentes.
  - `fechar` recebe `a_pagar_centavos` e `ajuste_ids` (obrigatórios, 400) e dá 409 "O relatório mudou…" se o
    relatório de agora der outro valor ou outros ajustes (regra mudada, ajuste novo).
  - Excluir consulta que já está num repasse dá 409 ("Esta sessão já entrou num repasse pago…"); a exclusão
    da série pula essas. **Desfazer** um fechamento cujo ajuste de estorno já foi pago noutro dá 409 ("Desfaça
    primeiro o fechamento de DD/MM/AAAA…"). O aviso de estorno grava uma transação por sessão.
- **Conciliação automática do repasse (22/11/2026)** — plano `docs/superpowers/plans/2026-11-22-repasse-conciliacao.md`.
  As três "decisões pendentes" foram resolvidas **"sim"** pelo usuário em 22/11/2026.
  - **PASSO MANUAL PENDENTE — ainda NÃO aplicada em produção**: rodar `backend/migracoes/migracao_repasse_conciliacao.sql` (SQL Editor do
    Supabase) ou `backend/migrar_repasse_conciliacao.py` (conferir `(Postgres)` no fim) **antes** do
    `git pull` + restart (sem ela, o primeiro ajuste `status`/`recredito` falha no insert). Amplia as origens de
    `repasse_ajustes.origem`; idempotente. A homologação (PandaUp-Teste) também precisa deste SQL.
  - `repasse_service.conciliar(...)` reconcilia sessões **já repassadas** depois de estorno, baixa (manual e
    Mercado Pago), mudança de status da consulta (status na agenda, Atender, edição) e, por garantia, no início
    de `relatorio` e de `fechar`. A sessão repassada é julgada pelo vínculo gravado em `repasse_itens`
    (`acordo_id`/`mes`/item), não pelo estado atual da cobrança.
  - **Origens dos ajustes** (rótulo na tela e no PDF): `manual` = "Manual"; `estorno` = "Estorno";
    `status` = "Sessão desmarcada/falta" (a sessão repassada deixou de contar); `recredito` = "Recrédito"
    (a sessão voltou a contar, ajuste positivo). O JSON do relatório traz `origem` em cada ajuste.
  - Ajuste automático **pendente** que perde o motivo é apagado. Se já foi consumido num repasse pago, gera-se
    um ajuste oposto (positivo = `recredito`). Automático **dispensado** (`dispensado_em`) conta como aplicado:
    é apagado se o motivo acaba. `excluir_ajuste` **dispensa** todos os automáticos (botão "Dispensar") e
    **apaga** o manual (botão "Excluir").
  - Sessão repassada que deixa de contar **libera a vaga** do pacote / a cota da mensalidade (decisão 3).
    Efeito aceito: a vaga liberada depende do momento (falta antes ou depois do fechamento); se a falta volta a
    realizada, uma sessão **mais recente** do pacote pode receber um ajuste de "Estorno".
  - Mensalidade com base `procedimento` tem **teto**: a soma das bases nunca passa do líquido cobrado no mês.
  - **Sessão que volta a contar também tem teto** (`_excedentes`): se a parte dela no pacote/mês já foi para
    outra sessão repassada, o recrédito é parcial ou nenhum e o resto fica como desconto `status` ("Sessão voltou
    a contar, mas o pacote/mês já foi repassado em outra sessão"); avulsa e item antigo sem acordo, sem teto.
- Testes: `test_repasse_*.py` (inclusive `test_repasse_conservacao.py` e os da conciliação),
  `test_financeiro_repasse_schema.py` e `frontend/tests/financeiro_util.test.js`. Backend: **1262 testes passando**;
  front (Node): **206**.

### ay) Financeiro 6.5 — outros relatórios e extrato do paciente (23/11/2026)
Plano `docs/superpowers/plans/2026-11-23-financeiro-relatorios.md`. **Sem migração.** Decisões do usuário:
o extrato mostra as **sessões uma a uma** e a **secretária pode baixar** o PDF.
- **Extrato do paciente** (ficha → cartão Financeiro, gestor e secretária; período padrão últimos 3 meses):
  `GET /api/financeiro/paciente/<id>/extrato` e `/extrato/pdf` (`relatorios_service.extrato_paciente`,
  `extrato_pdf.py`) + Excel no navegador (`financeiro_util.planilhasExtrato`). Sessões realizadas e faltas
  cobradas do período, com a situação ("Cobrança: … (status)", "Pacote: sessão N de M", "Mensalidade MM/AAAA",
  "Não cobrada", "Aguardando cobrança", "Sem acordo"); cobranças por vencimento (sem rascunho/cancelada);
  pagamentos (estornado marcado, não soma). Totais: cobrado = soma das cobranças do período (não das
  sessões, para não dobrar pacote/mensalidade), pago no período e saldo em aberto hoje (de qualquer período).
  É documento para a família: nunca leva repasse, `revisar_motivo` nem texto clínico. Profissional e
  responsável → 403; paciente de outra clínica → 404.
- **Financeiro → 📑 Relatórios** (`#/gestor/financeiro/relatorios`, só gestor; `views/financeiro_relatorios.js`):
  cobranças em aberto e vencidas (saldo e dias de atraso; filtro de especialidade), pacotes com até N sessões
  restantes (0–5, padrão 2) e mensalidades terminando no período (padrão: hoje até o fim do mês seguinte),
  sessões sem acordo no período (padrão: mês atual; mesma regra das pendências). Rotas
  `GET /api/financeiro/relatorios/em-aberto|acabando|sem-acordo`; Excel por `financeiro_util.planilhaRelatorio`.
- Testes: `backend/tests/test_extrato_paciente.py`, `backend/tests/test_relatorios_financeiro.py`,
  `frontend/tests/financeiro_util.test.js`. Front (Node): **208**.

### az) Anexos no Atender e no "Editar registro" do Diário (25/11/2026)
Spec `docs/superpowers/specs/2026-11-25-anexos-atender-editar-diario-design.md`, plano
`docs/superpowers/plans/2026-11-25-anexos-atender-editar-diario.md`. **Sem migração.**
- Campo de anexos num componente só (`diario.js`: `renderCampoAnexos(prefixo)` /
  `ligarCampoAnexos(raiz, prefixo, {existentes, podeRemover})` → `{pendentes, enviar(diarioId)}`), usado no
  Novo Diário, no **Atender** (seção "Para a família"; o aviso "continuam pelo + Novo Diário" saiu) e no
  **Editar registro**. Os anexos do registro aparecem com ✕.
- `DELETE /api/diario/anexo/<id>`: autor do registro ou gestor da clínica do paciente; auditoria
  `excluir` / `diario_anexo`. `PUT /agenda/<id>/atendimento` devolve `diario_id` (null numa falta sem texto) e
  o `GET` traz `diario.anexos` (sem o conteúdo). Falta sem texto + arquivo → a tela pede um texto antes.
- Anexo que falha depois de salvar: o registro fica, os arquivos que faltam continuam na tela e o botão vira
  "Enviar anexos" (não duplica o registro). Acrescentar/remover anexo não avisa a família.
- Testes: `backend/tests/test_anexos_diario_edicao.py`.

### ba) Anexos do Diário no Supabase Storage, até 30 MB (25/11/2026)
Spec `docs/superpowers/specs/2026-11-25-anexos-diario-storage-design.md`, plano
`docs/superpowers/plans/2026-11-25-anexos-diario-storage.md`. Pedido do usuário: vídeos curtos de um momento da
terapia para a família ver no celular; 4 MB era pouco. Decisões do usuário: Storage do mesmo projeto Supabase
(não outro banco); **sem prazo de expiração** dos arquivos (hipótese descartada).
- **Produção: migração, variáveis e deploy feitos; envio de vídeo funcionando (conferido pelo usuário em
  25/11/2026, depois do PR #94).** Na homologação, ainda falta o mesmo passo manual: (1) rodar `backend/migracoes/migracao_anexos_storage.sql`
  (SQL Editor) ou `migrar_anexos_storage.py` — `storage_path`, `mime`, `conteudo_base64` aceita NULL; (2) só
  depois, no cPanel → Setup Python App → variáveis: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (service_role/secret
  key, só no servidor), `DIARIO_ANEXO_LIMITE_MB=30`; restart. O bucket privado `diario-anexos` é criado pelo app.
- **Mudar o limite** (ex.: no plano Pro): só a variável `DIARIO_ANEXO_LIMITE_MB` + restart; acima de 50 MB, subir
  também o limite global em Supabase → Storage → Settings (50 MB é o teto do plano gratuito, que tem 1 GB no total).
- `backend/armazenamento_service.py` é o único que fala com o Storage (REST via `requests`): link de envio de
  uso único, leitura dos primeiros bytes + tamanho por `Range`, link de leitura de 1 h, apagar. Trocar de
  fornecedor (ex.: Cloudflare R2) = mexer só nele.
- Rotas: `GET /api/diario/anexos/config` → `{storage, limite_mb}`; `POST /api/diario/<id>/anexo/envio` (permissão,
  tipo, tamanho → `{caminho, url_envio}`; caminho `clinica-<org>/diario-<id>/<uuid>.<ext>`); o navegador faz `PUT`
  direto no Storage (XHR com %); `POST .../anexo/confirmar` confere prefixo, tamanho real e assinatura
  (`validacao_arquivo.validar_bytes`), apaga o arquivo se não bater, grava a linha. `GET /diario/anexo/<id>` devolve
  `url` (link de 1 h) para os do Storage; remover apaga o arquivo também. Erro do Storage → 502 amigável.
- CSP: com o Storage configurado, a origem do `SUPABASE_URL` entra em `img-src`, `media-src` e `connect-src`.
- Front: perfil `anexo_diario` em `envio_arquivos.js` (`ajustarLimiteAnexoDiario(mb)`); o chat continua no perfil
  `anexo` (4 MB, banco). Sem as variáveis, o Diário volta ao base64 de 4 MB (local, CI).
- Testado localmente com um Storage simulado (rotas da API do Supabase, CORS e Range): envio de vídeo WebM de
  4,4 MB, vídeo tocando pelo link, foto reduzida, remover apagando no Storage.
- **PR #94 (25/11/2026)**: no Supabase real (Storage 1.98), o link de envio sem bucket responde "The related
  resource does not exist" (não "Bucket not found"); `_bucket_inexistente` aceita as duas e o app cria o bucket.
  Variáveis da produção: `SUPABASE_URL=https://fppcfkjhwqldsdblgnxh.supabase.co`; homologação:
  `https://pmoaxraulmrgrectgiht.supabase.co`. Chave = `service_role` (Legacy API Keys) de cada projeto.
- Testes: `backend/tests/test_anexos_storage.py`, `backend/tests/test_armazenamento_service.py`,
  `frontend/tests/envio_arquivos.test.js`. RLS (regra 2): o bucket é privado e só o servidor tem a chave.

### bb) Texto legível sobre o fundo escuro da clínica (25/11/2026)
Pedido do usuário (título "Missões desta semana" sumindo no Início da família com o Fundo do mar). Sem migração.
- **Causa**: a regra de 23/11 era uma lista de seletores presa à profundidade do HTML
  (`.shell-conteudo > .surgir > h3`); não pegava o topo da Agenda, blocos do Dashboard do profissional e
  nada da família, cuja tela fica em `.shell-mobile-conteudo` (fora do `.shell-conteudo`).
- **Agora** `frontend/js/contraste_fundo.js`: com `body[data-tom-fundo="escuro"]` e o `#fundo-clinica` na tela,
  desce a partir do `#app`, para em qualquer elemento com fundo próprio calculado (cor com alfa ≥ 0,6, degradê
  ou imagem — `superficieOpaca`) e marca com `.sobre-fundo-escuro` o que tem texto direto sobre o fundo
  (branco com sombra, `!important` para vencer `style="color:…"`; estilos no `layout.css`). Refaz quando o
  `#app` muda (MutationObserver + requestAnimationFrame) e quando o tom muda. **Tela nova não precisa fazer
  nada.** O estado vazio solto vira cartão branco também na tela da família.
- `.badge-acento` não existia no CSS: o "⭐ XP" do Mundo da Criança ficava sem pílula (sumia no Espaço).
- Verificado com varredura no navegador (todas as telas do menu de gestor, profissional, secretária e família,
  em 1366 px e 390 px, Fundo do mar; Mundo da Criança no Espaço): nenhum texto escuro direto no fundo e nenhum
  texto branco sobre superfície clara. Testes: `frontend/tests/contraste_fundo.test.js`.

### bc) IA fase 1 — ditado por voz (26/11/2026)
Spec `docs/superpowers/specs/2026-11-25-ia-ditado-design.md`; briefs e relatórios por tarefa em
`.superpowers/sdd/2026-11-25-ia-ditado/`. Primeiro recurso de IA do PandaUp e a **base comum** das próximas
(a fase 2 é o agente de suporte).
- **O que é**: botão 🎤 ao lado de cada campo de texto do prontuário. O profissional fala, o navegador grava
  (`MediaRecorder`), envia ao servidor, que confere a cota, transcreve e devolve o texto para o campo, que o
  profissional revisa. Campos: Atender (descrição, observação e mensagem para a família), Novo Diário e "Editar registro" (evolução
  clínica e mensagem para a família) e Ficha Clínica. O texto entra onde está o cursor, sem apagar o que já há.
  Componente `frontend/js/ditado.js` (`Ditado.ligar(raiz, seletores)`); só um campo grava por vez; "Tente de
  novo" reenvia o mesmo áudio (guardado só na memória da página).
- **Quem dita**: profissional e gestor (quem edita esses campos). Secretária e responsável não.
- **Módulo `ia` ("Assistente de IA")**: deixou de ser oculto. Entra em plano (com herança) ou como extra da
  clínica. A migração **remove `ia` de `planos_modulos` e `modulos_clinica`**: ninguém ganha no deploy. Como o
  módulo era oculto, nenhuma clínica o tinha antes da migração; a remoção é só garantia.
- **Cota** (decisão do usuário): minutos por plano (`planos.ia_minutos_mes`, herdado do plano base quando
  vazio; campo "Minutos de ditado por mês" no formulário do plano) **mais minutos extras só do mês**
  (`ia_creditos`, liberados pelo Admin no detalhe da clínica, com motivo; não acumulam). Mês civil em Brasília.
  Cota = plano + extras do mês; restante = cota − usado (`ia_uso`). Acabou a cota → mensagem amigável, sem
  chamar a OpenAI. Duas pessoas ditando ao mesmo tempo podem passar um pouco da cota (aceito).
- **Privacidade**: áudio nunca guardado; texto nunca em log/auditoria; **sem nome do paciente** em nenhum
  pedido ao fornecedor (só um vocabulário clínico geral). `ia_uso` guarda só clínica, usuário, segundos,
  modelo, custo estimado e sucesso/falha. Limite de **300 s e 15 MB** por gravação; a duração cobrada é a
  devolvida pela OpenAI ou, senão, a do navegador conferida pelo tamanho do arquivo.
- **Rotas** (`blueprints/ia_bp.py`): `GET /api/ia/ditado/config` (disponível, cota, usado, restante),
  `POST /api/ia/ditado` (multipart). Admin (`admin_bp.py`): `GET /api/admin/clinicas/<id>/ia`,
  `POST /api/admin/clinicas/<id>/ia/creditos`, `GET /api/admin/ia/uso?mes=AAAA-MM`.
- **Telas**: Admin → Planos (minutos), detalhe da clínica (cartão do ditado: uso e minutos extras), página nova
  **✨ Consumo de IA** (`#/admin/ia`, `views/admin_ia.js` + `admin_ia_util.js`: por clínica, cota, usado, falhas,
  custo estimado) e, para o gestor, uma linha "Ditado por voz: N de M minutos usados" em Módulos.
- **Modelo**: padrão **`gpt-transcribe`**, segundo a documentação da OpenAI consultada em 26/11/2026 (que também
  dizia que `whisper-1` e os `gpt-4o-*-transcribe` seriam desligados em 26/02/2027; conferir); a variável
  `OPENAI_MODELO_TRANSCRICAO` troca. **Nunca foi testado
  contra a API real** (só com o fornecedor falso: `FLASK_DEBUG=1` + `IA_FAKE=1`, usado nos testes e na varredura
  de navegador). Confira o nome do modelo e o preço (`ia_service.PRECO_MICRO_USD_POR_MINUTO`) no primeiro teste real.
- **Correções da revisão final (26/11/2026)**, testes em `backend/tests/test_ia_correcoes_finais.py`:
  - o áudio **nunca vai para o disco**: o Werkzeug grava em arquivo temporário todo envio acima de 500 KB; o
    `app.request_class = PedidoPandaUp` (`app.py`) deixa o arquivo na memória só em `/api/ia/ditado`
    (`ROTAS_ARQUIVO_SO_NA_MEMORIA`), e a rota barra o corpo grande pelo `Content-Length` antes de ler
    (`request.max_content_length` = 15 MB + 64 KB; sem `Content-Length`, o 413 vira 400 `audio_invalido`);
  - nome e tipo enviados à OpenAI saem do **conteúdo** (`ia_bp._tipo_do_audio`: MP4 do iPhone, OGG, WebM, MP3,
    WAV), não do que o navegador diz;
  - `config` traz `segundos_restantes` e `mes`; a gravação para no que sobra do mês (no máximo 5 min) e o 409
    "passa do que resta" recarrega a config em vez de travar todos os 🎤 (`ditado.js`: `limiteGravacao`,
    `cotaEsgotada`); 48 kbps; Módulos lê o mês do servidor (`nomeDoMes`);
  - falha ao gravar `ia_uso` depois de transcrever não perde o texto (nem troca o 502 por 500);
  - limite de 30 ditados a cada 10 min **por usuário** (`rate_limit.limitar(..., por_usuario=True)`), não por
    IP; o 429 oferece "Tentar de novo" com o mesmo áudio;
  - falha do fornecedor vira evento `ia_falhou` (`eventos`, só `{"causa": "HTTP 503"}` ou a classe do erro);
  - `criado_em` de `ia_uso`/`ia_creditos` é **TEXT** (horário de Brasília gravado pelo app); o cartão do Admin
    mostra com `formatarDataHoraLocal`.
- Migração: `backend/migracoes/migracao_ia_ditado.sql` ou `backend/migrar_ia_ditado.py` (tabelas `ia_uso` e
  `ia_creditos`, coluna `planos.ia_minutos_mes`, remoção do `ia` dos planos/extras; idempotente).
- **PASSOS MANUAIS ANTES DE LIGAR EM PRODUÇÃO** (nada disso foi feito ainda):
  1. **Migração antes do `git pull` + restart** (SQL Editor do Supabase ou `migrar_ia_ditado.py`; conferir
     `(Postgres)` no fim, ver 7.2). A homologação (PandaUp-Teste) também precisa dela.
  2. **`OPENAI_API_KEY`** (e, se quiser, `OPENAI_MODELO_TRANSCRICAO`) no cPanel → Setup Python App → variáveis,
     **chaves separadas** para homologação e produção, com **limite de gasto** configurado no painel da OpenAI.
     Sem a chave, o botão fica desligado (nada quebra).
  3. **Ligar o módulo "Assistente de IA"** no plano (ou como extra da clínica) e **definir os minutos por mês**
     pelo Admin; restart do Passenger.
  4. **Fora do código**: pedir **retenção zero** de dados na OpenAI e atualizar os termos de uso e a política de
     privacidade (LGPD) com o uso de IA para transcrição.
  5. **Testar primeiro na homologação** (migração + chave de teste), com um ditado real em cada campo.
- Varredura de navegador (26/11/2026, 1366 e 390 px): Atender, Novo Diário, Editar registro (ditado de
  verdade, com microfone simulado), Ficha Clínica, Módulos e Admin (Planos, detalhe da clínica, Consumo de IA),
  sem erro no console. Backend: **1382 testes passando**; front (Node): **230** (depois das correções da revisão final).

## 7. Pendências / próximos passos

- **IA fase 1 (5bc)**: falta aplicar a migração, pôr a chave da OpenAI e ligar o módulo no plano (passos no item
  5bc), e testar o ditado contra a API real (modelo `gpt-transcribe` nunca testado). **Próxima fase: agente de
  suporte** (Claude), pensado para **todos os planos e sem gastar a cota de minutos** (a tabela `ia_uso` já tem
  `recurso` para isso; o `ia_service` é o ponto de entrada). **Anamnese por voz**: a ficha de anamnese ainda
  não existe no sistema; quando existir, ligar o ditado nela (`Ditado.ligar`). O ditado é por gravação
  inteira (sem texto aparecendo em tempo real).
- **Atender estoura em 390 px** (achado antigo, não é da IA): a tela `#/…/atender/<id>` ganhava rolagem
  horizontal no celular (scrollWidth ~434). Na varredura de 26/11/2026 não reapareceu com a consulta de teste
  (382 px); confira com uma consulta com diário/anexos antes de dar por resolvido.

- **Anexos do Diário no Storage (5ba)**: funcionando na produção (25/11/2026). Falta: migração + variáveis na
  homologação; conferir o vídeo tocando na tela da família no celular (Android e iPhone). Produção tinha 69 MB de banco e nenhum anexo de
  Diário em 25/11/2026; o Supabase está no plano gratuito até a virada do mês (vai para o Pro).

- **Financeiro da clínica** (spec
  `docs/superpowers/specs/2026-11-07-financeiro-clinica-design.md`): etapas 1 (5av), 2 (5aw) e
  **3, repasse aos profissionais (5ax)**, feitas, e o item **6.5, outros relatórios (5ay)**, feito. As pendências no
  dashboard do gestor já existem desde a etapa 1 (cartão "💳 Pendências do financeiro"). Depois (fora da spec):
  despesas e resultado do mês, lembrete de cobrança por WhatsApp (junto com o projeto de mensagens).
  **Guia do Financeiro** em PDF (23/11/2026, fora do repositório):
  `D:\Projeto Viva\Panda Tech\material de tutorial\PandaUp - Guia do Financeiro.pdf`, gerado de
  `guia-financeiro-pandaup\guia.html` (mesmo processo do Guia de Primeiros Passos, item 5an).
- **Pontos deixados fora do escopo nas revisões (08/10/2026)** — não
  esquecer; sugestão de ordem combinada com o usuário na conversa:
  - (Grupo 1 resolvido em 08/10/2026, item 5ac: encaixe, medalha sem
    rascunho, botão do Diário, índice único de plano.)
  - Agenda: (ausências no modo Geral feitas em 5ag); soltar consulta em coluna não
    editável (o backend já barra); consulta que passa da meia-noite só é
    checada no dia em que começa; busca de ausências limitada a 62 dias.
  - Diário: secretária sem acesso ao Diário — **decidido pelo usuário em
    09/10/2026: continua assim**; rotas por paciente respondem 404 antes de
    403 (revela se o id existe).
  - Planos: `jornadas.status` não é filtrado nas
    contas; (lista de planos encerrados feita em 5ai); sem filtros por
    especialidade em relatórios; a API aceita especialidade fora da lista.
  - RLS: incluir `ausencias_profissional` quando o assunto voltar (regra 2).

- **Agenda no estilo Clínica Ágil** (pedido do usuário, 07/10/2026), em
  partes, cada uma com spec → plano → execução: (1) menu com Agenda em
  primeiro — feito (5x); (2) hora de fim livre, Ausência/bloqueio de
  horário e visão Dia — feito (5y; migração aplicada em produção, confirmado
  em 08/10/2026); (3) dividida (08/10/2026): **(3a) Diário por
  paciente** — feito (5z; migração aplicada em produção, confirmado em
  08/10/2026); **(3c) planos por especialidade** — feito (5aa; migração aplicada em
  produção, confirmado em 08/10/2026); (3b) **Atender/Evoluir** — feito (5ad; migração aplicada em produção,
  confirmado em 09/10/2026). **Procedimentos** — feito (5ae; migração
  aplicada em produção, confirmado em 09/10/2026). Repetição avançada — feita (5af); ausências nas visões do modo Geral —
  feitas (5ag) (sai da jornada; "Iniciar jornada" num pop-up com objetivo
  principal + plano; objetivo principal editável — spec
  `docs/superpowers/specs/2026-10-08-jornada-diario-por-paciente-design.md`) e
  **(3b) Atender/Evoluir** a partir do pop-up da consulta (tela enxuta:
  descrição, observação e status Finalizado/Não compareceu/Falta
  justificada/Desmarcado pelo profissional — os dois últimos são status
  novos, descrição obrigatória só em Finalizado; seção recolhida "Para a
  família" com o resto do Diário; histórico de atendimentos do paciente),
  gravando um registro do Diário com `consulta_id`. **Ordem combinada:
  3a → 3c → 3b**, sendo (3c) **planos terapêuticos por especialidade** (vários
  planos ativos ao mesmo tempo — pedido do usuário, porque as clínicas
  clientes têm várias especialidades; afeta missões, progresso, Mundo da
  Criança, família, ICT e PDF). Depois:
  status novos, repetição personalizada, WhatsApp/histórico no pop-up,
  Visão Geral colorida, Lista de Espera, horário por profissional.
- **Guia de Integrações para as clínicas (Mercado Pago + Google Agenda)** —
  adiado pelo usuário em 13/10/2026 até existir o **financeiro das famílias
  na tela**: hoje `viewFinanceiroGestor` só mostra o extrato (sem lançar
  cobrança nem marcar como paga; `POST /financeiro/cobranca` existe, mas sem
  tela), então conectar o Mercado Pago da clínica não muda nada para ela.
  Rascunho (HTML + capturas numeradas, mesmo estilo do "Guia de Configurações")
  em `D:\Projeto Viva\Panda Tech\material de tutorial
ascunho-guia-integracoes-pandaup\`
  (PDF: Chromium headless `--print-to-pdf`). Antes de liberar o Google Agenda
  às clínicas: o Admin configura o app OAuth (Google Cloud: Calendar API, tela
  de consentimento, credenciais, redirect
  `https://app.pandaup.com.br/api/integracoes/google_calendar/callback`) e pede
  a verificação do Google (escopo sensível `calendar.events`; até lá, aviso de
  "app não verificado" e limite de 100 contas). Também trocar o texto técnico
  do cartão do Google em `views/integracoes.js` ("O SaaS ainda não configurou…
  SETUP_INTEGRACOES.md") por um aviso amigável.
- **Testar a credencial do Mercado Pago da plataforma (14/10/2026)**: em
  14/10 a Public Key estava salva no campo do Access Token e o Mercado Pago
  recusava PIX e cartão. Agora `pagamento_plataforma_service.testar_credencial`
  (formato: parece Public Key / `TEST-` / sem `APP_USR-`; depois `GET /users/me`)
  roda **antes de salvar** (token errado → 400, nada gravado) e no botão
  **"Testar conexão"** do Admin (`POST /api/admin/integracoes/mercadopago/testar`,
  mostra nome e ID da conta, nunca o token). Nos testes, simule
  `pps._consultar_conta`.
- **Webhook da plataforma (13/10/2026)**: a chave secreta salva em Admin →
  Integrações estava vazia ou diferente da do Mercado Pago (simulação dava 401);
  corrigida com uma assinatura nova. Conferir em Admin → Cobranças se alguma
  cobrança paga ficou pendente antes disso.
- **Pandoo fase 2, um jogo por vez** (pedido do usuário, 30/09/2026): o
  Quiz (5u), a Memória (5v), a Cruzadinha (5as) e o "Toque só no alvo" (5au)
  estão prontos. **Leva para psicologia/TO** (combinada em 05/11/2026, passa na
  frente): **Sequência de memória** (memória de curto prazo) e **Caça-figura**
  (atenção seletiva/percepção visual; "Qual é a sombra?" pode virar opção dele).
  Depois, cada um com brainstorm/prévia → spec → plano → execução:
  **Associação** (arrastar com toque) junto com **Separar por grupo**
  (flexibilidade, troca de regra no meio), **Quebra-cabeça** e, por último,
  **Flashcards** — a criança fala a palavra e só passa para o próximo cartão se
  a pronúncia estiver correta (reconhecimento de voz). Inspiração pedida pelo
  usuário: tipos de desafio do LogicLike — só a mecânica, nunca o conteúdo.
- **Migrações de produção**: todas aplicadas (horário da agenda, Pandoo,
  planos configuráveis, recursos dos planos, White Label e fundo da clínica
  — confirmado pelo usuário em 26/09/2026) e `migracao_excluir_equipe.sql`
  (coluna `usuarios.excluido_em`, item 5w — aplicada e com deploy, confirmado
  em 01/10/2026). Os jogos (Quiz, Memória) também estão em produção.
- **Novo modelo do Pandoo** = arquivo em `frontend/js/pandoo/jogos/`
  + `registrarJogo` + entrada em `pandoo_service.MODELOS`/`REGRAS_PADRAO` +
  painel em `renderRegras` do editor + `pronto: true` em `MODELOS_PANDOO_EDITOR`.
  Regras puras grandes ganham arquivo próprio ao lado de `pandoo_core.js` (como
  `cruzadinha_core.js`, chamado no `index.html` logo depois dele); limite de
  figuras diferente vai em `LIMITES_ITENS` (backend) e `limitesDoModelo` (front).
- **Diário Terapêutico ligado à consulta**: adiado pelo usuário (24/09/2026;
  em 01/10 ainda "aguardando entender melhor o fluxo"), que vai fazer uma
  alteração maior. A coluna `diarios_terapeuticos.consulta_id`
  já existe e não é usada.
- **Recuperação de senha por e-mail**: feita (5al); passa a valer em
  produção quando as variáveis `SMTP_*` estiverem no `.env`. Depois: trocar a
  caixa do cPanel por um serviço transacional (Brevo/SES) quando vierem os
  lembretes.
- **RLS em standby** (ver regra 2): `backend/habilitar_rls_encanto_em_casa.sql`
  fica parado até o usuário retomar o assunto. **Incluir `pandoo_jogos` e
  `pandoo_resultados`** quando retomar: o SQL Editor do Supabase avisou
  que elas nasceram sem RLS e o usuário escolheu "Run without RLS" (25/09),
  igual a todas as outras tabelas. Incluir também as do Financeiro:
  `acordos_pagamento`, `cobranca_itens`, `consulta_decisao_cobranca`,
  `acordo_pacote_consumo` e `consulta_acordo_incluida`. E as do repasse: `regras_repasse`, `repasses`,
  `repasse_itens` e `repasse_ajustes`. E as da IA: `ia_uso` e `ia_creditos`.
- Migração do Pandoo fase 1 (PR #16): **aplicada em produção** e deploy
  feito (confirmado pelo usuário em 25/09/2026).
- Migração da assinatura recorrente: **já aplicada em produção** (conferido
  no Supabase em 23/09/2026 — a tabela `assinaturas_cartao_recorrentes` e
  a coluna `cobrancas_planos.descricao` existem, iguais ao script).
- **Troca de domínio** (futuro próximo; domínio novo ainda não definido em
  24/09/2026): roteiro na seção 7.1.

## 7.1. Roteiro para trocar o domínio de produção

**Domínio escolhido: `pandaup.com.br`** (12/10/2026). O passo a passo com os
valores e comandos prontos está em
`docs/operacao/pandaup-dominio-e-homologacao.md`; o texto abaixo é o
levantamento geral de 24/09/2026.

O código já está pronto (seção 5k); a troca é só configuração.

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
| Envio de arquivos (orientação, redução de imagem) | `frontend/js/envio_arquivos.js` |
| Planos: módulos por plano, herança, extras | `backend/modulos_service.py`, `backend/planos_padrao.py` |
| Planos: telas do Admin (planos, módulos da clínica) | `frontend/js/views/admin.js` |
| Pandoo — regras e validação dos jogos | `backend/pandoo_service.py` |
| Pandoo — rotas (jogos, resultados) | `backend/blueprints/pandoo_bp.py` |
| Pandoo — testes | `backend/tests/test_pandoo_*.py` |
| Pandoo — Cruzadinha (gerador da grade, estado da partida) + testes Node | `frontend/js/pandoo/cruzadinha_core.js`, `frontend/tests/pandoo_cruzadinha.test.js` |
| Pandoo — "Toque só no alvo" (sorteio, fases, medidas) + testes Node | `frontend/js/pandoo/alvo_core.js`, `frontend/tests/pandoo_alvo.test.js` |
| Pandoo — tela (lista/editor, palco, roleta, quiz, memória, cruzadinha, alvo, sons) | `frontend/js/views/pandoo.js`, `frontend/js/pandoo/`, `frontend/css/pandoo.css` |
| White Label — regra da identidade efetiva | `backend/identidade_service.py` |
| White Label — rotas públicas (login da clínica, imagens) | `backend/blueprints/publico_bp.py` |
| White Label — tela de Configurações / cenários animados | `frontend/js/views/identidade_clinica.js`, `frontend/js/cenarios_animados.js` |
| Agenda — ausências (regras, rotas) | `backend/ausencias_service.py`, `backend/blueprints/agenda_bp.py` |
| Agenda — ausências na tela (pop-up, funções puras) | `frontend/js/views/agenda_ausencia_modal.js`, `frontend/js/agenda_ausencias.js` |
| Procedimentos (regras, rotas, tela) | `backend/procedimentos_service.py`, `backend/blueprints/procedimentos_bp.py`, `frontend/js/views/procedimentos.js` |
| E-mail (SMTP, modelos, convites) | `backend/email_service.py` |
| Logo da plataforma | `backend/plataforma_service.py`, `frontend/js/marca_plataforma.js` |
| Importação (pacientes + ficha, evoluções → Diário) | `backend/blueprints/importacao_bp.py`, `backend/importacao_service.py`, `frontend/js/views/importacao.js`, `frontend/js/importacao_util.js` |
| App instalável (manifest, ícones, botão Instalar) | `backend/blueprints/publico_bp.py`, `backend/assets/app/`, `frontend/js/instalar_app.js` |
| Financeiro — cobrança das famílias (regras puras, acordos, sincronização, rotas) | `backend/cobranca_regras.py`, `backend/acordos_service.py`, `backend/cobranca_service.py`, `backend/blueprints/financeiro_bp.py` |
| Financeiro — migração e cron opcional | `backend/migracoes/migracao_financeiro_cobranca.sql`, `backend/migrar_financeiro_cobranca.py`, `backend/gerar_cobrancas_clinicas.py` |
| Financeiro — telas (cobranças, ficha) e funções puras + testes Node | `frontend/js/views/financeiro.js`, `frontend/js/views/financeiro_ficha.js`, `frontend/js/financeiro_util.js`, `frontend/tests/financeiro_util.test.js` |
| Financeiro — fechamento de caixa (regra, PDF, tela) | `backend/caixa_service.py`, `backend/caixa_pdf.py`, `frontend/js/views/financeiro_caixa.js` |
| Financeiro — relatórios e extrato do paciente | `backend/relatorios_service.py`, `backend/extrato_pdf.py`, `frontend/js/views/financeiro_relatorios.js`, `frontend/js/views/financeiro_ficha.js` |
| Financeiro — repasse aos profissionais (regras puras, serviço, PDF, tela) | `backend/repasse_regras.py`, `backend/repasse_service.py`, `backend/repasse_pdf.py`, `frontend/js/views/financeiro_repasse.js`, migração `backend/migracoes/migracao_financeiro_repasse.sql` |
| Anexos do Diário (Storage, campo de anexos compartilhado) | `backend/armazenamento_service.py`, `backend/blueprints/diario_bp.py`, `frontend/js/views/diario.js` (`renderCampoAnexos`/`ligarCampoAnexos`) |
| IA — serviço único (cota, uso, transcrição, fornecedor falso) | `backend/ia_service.py`, migração `backend/migracoes/migracao_ia_ditado.sql` |
| IA — rotas do ditado (config e transcrição) | `backend/blueprints/ia_bp.py`; rotas do Admin (cota, créditos, consumo) em `backend/blueprints/admin_bp.py` |
| IA — ditado no navegador (botão 🎤, gravação) | `frontend/js/ditado.js` |
| IA — telas do Admin (Consumo de IA) | `frontend/js/views/admin_ia.js`, `frontend/js/admin_ia_util.js`, `frontend/js/views/admin.js` |
| Roteiro do servidor (domínio PandaUp, homologação) | `docs/operacao/pandaup-dominio-e-homologacao.md` |
| CI (pytest e node --test em PR/push) e setup do banco | `.github/workflows/` |
