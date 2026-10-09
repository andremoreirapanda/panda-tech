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
  `MODULOS_OPCIONAIS`; `MODULOS_VISIVEIS`/`CODIGOS_OPCIONAIS` o ignoram). As
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

- **Pontos deixados fora do escopo nas revisões (08/10/2026)** — não
  esquecer; sugestão de ordem combinada com o usuário na conversa:
  - (Grupo 1 resolvido em 08/10/2026, item 5ac: encaixe, medalha sem
    rascunho, botão do Diário, índice único de plano.)
  - Agenda: mostrar ausências nas
    visões Lista/Semana/Mês do modo Geral; soltar consulta em coluna não
    editável (o backend já barra); consulta que passa da meia-noite só é
    checada no dia em que começa; busca de ausências limitada a 62 dias.
  - Diário: secretária não tem acesso ao Diário (decidir a regra); rotas por
    paciente respondem 404 antes de 403 (revela se o id existe).
  - Planos: `jornadas.status` não é filtrado nas
    contas; não há lista de planos encerrados na ficha; sem filtros por
    especialidade em relatórios; a API aceita especialidade fora da lista.
  - RLS: incluir `ausencias_profissional` quando o assunto voltar (regra 2).

- **Agenda no estilo Clínica Ágil** (pedido do usuário, 07/10/2026), em
  partes, cada uma com spec → plano → execução: (1) menu com Agenda em
  primeiro — feito (5x); (2) hora de fim livre, Ausência/bloqueio de
  horário e visão Dia — feito (5y; migração aplicada em produção, confirmado
  em 08/10/2026); (3) dividida (08/10/2026): **(3a) Diário por
  paciente** — feito (5z; migração aplicada em produção, confirmado em
  08/10/2026); **(3c) planos por especialidade** — feito (5aa; migração aplicada em
  produção, confirmado em 08/10/2026); (3b) **Atender/Evoluir** — feito (5ad; **migração `migracao_atender.sql`
  pendente em produção** até o usuário confirmar). Próximos PRs pequenos:
  **repetição avançada do agendamento** (semanal/quinzenal/mensal/
  personalizado por semana, dias da semana, meses, data limite ou quantidade;
  sem limite = próximos 12 meses) e **ausências nas visões do modo Geral** (sai da jornada; "Iniciar jornada" num pop-up com objetivo
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
- **Pandoo fase 2, um jogo por vez** (pedido do usuário, 30/09/2026): o
  Quiz (5u) e a Memória (5v) estão prontos; próximos, nesta ordem, cada um com brainstorm/prévia →
  spec → plano → execução: **Associação** (arrastar com toque),
  **Quebra-cabeça** e, por último, **Flashcards** — a criança fala a palavra e
  só passa para o próximo cartão se a pronúncia estiver correta
  (reconhecimento de voz).
- **Migrações de produção**: todas aplicadas (horário da agenda, Pandoo,
  planos configuráveis, recursos dos planos, White Label e fundo da clínica
  — confirmado pelo usuário em 26/09/2026) e `migracao_excluir_equipe.sql`
  (coluna `usuarios.excluido_em`, item 5w — aplicada e com deploy, confirmado
  em 01/10/2026). Os jogos (Quiz, Memória) também estão em produção.
- **Novo modelo do Pandoo** = arquivo em `frontend/js/pandoo/jogos/`
  + `registrarJogo` + entrada em `pandoo_service.MODELOS`/`REGRAS_PADRAO` +
  painel em `renderRegras` do editor + `pronto: true` em `MODELOS_PANDOO_EDITOR`.
- **Diário Terapêutico ligado à consulta**: adiado pelo usuário (24/09/2026;
  em 01/10 ainda "aguardando entender melhor o fluxo"), que vai fazer uma
  alteração maior. A coluna `diarios_terapeuticos.consulta_id`
  já existe e não é usada.
- **Recuperação de senha por e-mail** (futuro): hoje não há envio de
  e-mail, então "Esqueci minha senha" em produção só orienta a pedir um
  link ao gestor/admin. Quando houver um provedor de e-mail, o link volta a
  ser gerado, mas enviado por e-mail e nunca na resposta da API.
- **RLS em standby** (ver regra 2): `backend/habilitar_rls_encanto_em_casa.sql`
  fica parado até o usuário retomar o assunto. **Incluir `pandoo_jogos` e
  `pandoo_resultados`** quando retomar: o SQL Editor do Supabase avisou
  que elas nasceram sem RLS e o usuário escolheu "Run without RLS" (25/09),
  igual a todas as outras tabelas.
- Migração do Pandoo fase 1 (PR #16): **aplicada em produção** e deploy
  feito (confirmado pelo usuário em 25/09/2026).
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
| Envio de arquivos (orientação, redução de imagem) | `frontend/js/envio_arquivos.js` |
| Planos: módulos por plano, herança, extras | `backend/modulos_service.py`, `backend/planos_padrao.py` |
| Planos: telas do Admin (planos, módulos da clínica) | `frontend/js/views/admin.js` |
| Pandoo — regras e validação dos jogos | `backend/pandoo_service.py` |
| Pandoo — rotas (jogos, resultados) | `backend/blueprints/pandoo_bp.py` |
| Pandoo — testes | `backend/tests/test_pandoo_*.py` |
| Pandoo — tela (lista/editor, palco, roleta, quiz, memória, sons) | `frontend/js/views/pandoo.js`, `frontend/js/pandoo/`, `frontend/css/pandoo.css` |
| White Label — regra da identidade efetiva | `backend/identidade_service.py` |
| White Label — rotas públicas (login da clínica, imagens) | `backend/blueprints/publico_bp.py` |
| White Label — tela de Configurações / cenários animados | `frontend/js/views/identidade_clinica.js`, `frontend/js/cenarios_animados.js` |
| Agenda — ausências (regras, rotas) | `backend/ausencias_service.py`, `backend/blueprints/agenda_bp.py` |
| Agenda — ausências na tela (pop-up, funções puras) | `frontend/js/views/agenda_ausencia_modal.js`, `frontend/js/agenda_ausencias.js` |
| CI (pytest e node --test em PR/push) e setup do banco | `.github/workflows/` |
