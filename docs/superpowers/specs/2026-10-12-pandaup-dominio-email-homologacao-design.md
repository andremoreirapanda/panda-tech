# PandaUp: domínio novo, e-mail por SMTP e homologação — design

Data: 12/10/2026. Desenho aprovado pelo usuário na conversa (domínio
`pandaup.com.br`, sistema em `app.pandaup.com.br`, nome do produto vira
**PandaUp**, hospedagem continua no cPanel da Napoleon, Cloudflare em modo
só DNS agora e proxy depois, Supabase Pro, homologação em
`teste.pandaup.com.br`, e-mail pelo SMTP da hospedagem).

## Objetivo

Lançar o sistema com marca e endereço próprios, recuperação de senha e
convites por e-mail, e um ambiente de teste separado da produção — sem
interromper as clínicas que usam `pandatech.pandacriacao.com.br`.

## Fora do escopo

VPS própria e serviço de e-mail transacional (Brevo/SES): ficam para quando
chegarem os lembretes e o financeiro F2. Ligar o proxy da Cloudflare: depois do
lançamento (o código já fica pronto, item C).

---

## A. Nome PandaUp (código)

- Todo texto que o usuário vê troca "Panda Tech" por **PandaUp**: login e
  título da aba (`index.html`, `login.js`), menus e avisos (`shell.js`,
  `util.js`, telas), mensagens de erro e notificações do backend
  (`auth_bp`, `pandoo_bp`, `integracoes_bp`, `modulos_service`,
  `pagamento_*`, `calendar_sync_service`, `whatsapp_service`,
  `relatorio_service` — PDF), `/api/health` e o nome padrão do app no White
  Label (`identidade_service`: `app_nome` padrão = "PandaUp").
- Não mudam: nomes de arquivos, variáveis, tabelas, o repositório, os
  comentários de código e os valores que as clínicas gravaram no White Label.
- Teste: nenhum texto de interface com "Panda Tech" (busca automatizada nas
  strings de `frontend/js`, `frontend/index.html` e nas mensagens de resposta
  do backend), e o `app_nome` padrão é "PandaUp".

## B. E-mail por SMTP (código)

**Configuração** (variáveis de ambiente; sem `SMTP_HOST` o envio fica
desligado e tudo funciona como hoje):

| Variável | Exemplo | Uso |
|---|---|---|
| `SMTP_HOST` | `mail.pandaup.com.br` | servidor |
| `SMTP_PORTA` | `465` | 465 = SSL direto; 587 = STARTTLS |
| `SMTP_USUARIO` | `nao-responda@pandaup.com.br` | login |
| `SMTP_SENHA` | (segredo) | senha da caixa |
| `EMAIL_REMETENTE` | `PandaUp <nao-responda@pandaup.com.br>` | De: |
| `URL_APP` | `https://app.pandaup.com.br` | já existe; monta o link absoluto |

**Módulo** `backend/email_service.py`:
- `email_configurado() -> bool`.
- `enviar_email(para, assunto, texto, html=None) -> bool`: `smtplib`
  (`SMTP_SSL` na 465, `starttls` na 587), timeout de 10 s, nunca levanta
  exceção para quem chama — falha vira `log_evento` ("email_falhou") e
  `False`. Recusa destinatário vazio ou com quebra de linha (cabeçalho).
- `link_absoluto(link_relativo)`: `URL_APP` + `/` + `#/redefinir-senha?...`;
  sem `URL_APP`, não envia (link relativo não serve num e-mail).
- Modelos simples (texto + HTML com a marca PandaUp): **redefinição de
  senha** e **convite** (equipe, responsável, gestor da clínica). O HTML usa
  só estilo inline e escapa nome e clínica.

**Esqueci minha senha** (`POST /api/auth/esqueci-senha`):
- Com e-mail configurado: se o e-mail existir e a conta estiver ativa, gera o
  token de 1 h e envia o link. A resposta é **sempre a mesma**, exista ou não
  a conta: "Se este e-mail estiver cadastrado, enviamos um link para redefinir
  a senha." O link nunca vai na resposta em produção.
- Sem e-mail configurado: continua a mensagem atual (pedir ao gestor/admin),
  com o nome PandaUp.
- `FLASK_DEBUG=1` continua devolvendo o link na tela (desenvolvimento).
- Limite de tentativas atual mantido (5 a cada 10 min).

**Convites**: onde hoje o sistema gera `link_convite` (criar profissional,
secretária, responsável, gestor de clínica nova, e os "Reenviar link de
acesso"), também envia o convite por e-mail quando configurado. A resposta
ganha `enviado_email: true|false`; o link continua na resposta para copiar ou
mandar por WhatsApp. A tela mostra "Convite enviado para <e-mail>" quando
`enviado_email` for verdadeiro.

**Testes**: SMTP falso (monkeypatch de `smtplib`), cobrindo envio na 465 e na
587, falha de conexão sem erro 500, cabeçalho com quebra de linha recusado,
resposta idêntica para e-mail existente e inexistente, link absoluto com
`URL_APP`, nenhum envio sem `SMTP_HOST`, convites com `enviado_email`.

## C. IP real atrás da Cloudflare (código, desligado por padrão)

- Variável `ENCANTO_CLOUDFLARE=1` (padrão 0). Ligada, `rate_limit._ip_cliente`
  usa o cabeçalho `CF-Connecting-IP` **somente** quando `remote_addr` está
  numa das faixas oficiais de IP da Cloudflare (lista no código, com data e
  link da fonte); senão, `remote_addr` como hoje.
- Só será ligada quando o proxy (nuvem laranja) for ativado.
- Testes: com e sem a variável, cabeçalho falso vindo de IP fora da
  Cloudflare é ignorado.

## D. Homologação (código + servidor)

**Código**: variável `AMBIENTE=homologacao`.
- `_index_html` injeta `<meta name="ambiente" content="homologacao">`; um
  script mostra uma faixa fixa no topo "AMBIENTE DE TESTE — dados fictícios"
  (também no Mundo da Criança e no login).
- Toda resposta ganha `X-Robots-Tag: noindex, nofollow`.
- `/api/health` devolve `"ambiente"`.
- Em produção (variável ausente) nada muda.
- Testes: meta e cabeçalho presentes só com a variável.

**Servidor** (o usuário executa, com o passo a passo do plano):
- Supabase: projeto novo `pandaup-teste` numa **organização gratuita
  separada**, região `sa-east-1`; esquema com `schema_postgres.sql` e dados
  fictícios com o `seed.py` (nunca dados reais).
- cPanel: segundo app Python (Setup Python App) com raiz própria
  (`~/pandaup-teste`, clone do repositório) ligado a `teste.pandaup.com.br`;
  `.env` próprio: `DATABASE_URL` do projeto de teste, `ENCANTO_SECRET` e
  `ENCANTO_CRYPTO_KEY` diferentes da produção, `AMBIENTE=homologacao`,
  `URL_APP=https://teste.pandaup.com.br`, Mercado Pago sem credenciais (ou de
  teste), Google desligado, SMTP podendo usar a mesma caixa.
- Fluxo: para testar um PR antes do merge, no servidor:
  `cd ~/pandaup-teste && git fetch && git checkout <branch> && pip install -r backend/requirements.txt && touch tmp/restart.txt`.

## E. Troca de domínio (servidor)

Segue o roteiro do CLAUDE.md 7.1, com estes valores:
1. DNS na Cloudflare (só DNS): `pandaup.com.br`, `app`, `teste` → IP
   186.209.113.98; MX, SPF, DKIM e DMARC (`p=none`). Registro.br já delegado
   para a Cloudflare (em propagação em 12/10/2026).
2. cPanel: AutoSSL para `pandaup.com.br`, `app.` e `teste.`;
   `app.pandaup.com.br` servindo **o mesmo app** de produção (Passenger com a
   mesma raiz de aplicação — configuração no `.htaccess` da pasta do
   domínio); `pandaup.com.br` redireciona para `https://app.pandaup.com.br`.
3. `.env` da produção: `URL_APP=https://app.pandaup.com.br`,
   `ALLOWED_ORIGIN=https://app.pandaup.com.br`, webhooks
   `MP_NOTIFICATION_URL` / `MP_PLATAFORMA_NOTIFICATION_URL` para o domínio
   novo, `GOOGLE_OAUTH_REDIRECT_URI` (se usada) e as variáveis SMTP; depois
   `touch tmp/restart.txt`. `ALLOWED_ORIGIN` aceita só uma origem: durante a
   transição o domínio antigo continua funcionando porque o front e a API são
   servidos pela mesma origem (CORS não se aplica).
4. Mercado Pago (plataforma e clínicas): URL de webhook nova; Google Cloud:
   redirect URI novo (e reconectar a integração pela tela, se estiver gravada
   no banco).
5. Conferir: login, convite por e-mail chegando, senha esquecida, checkout do
   cartão voltando para o domínio novo, um PIX de teste com baixa pelo webhook.
6. Avisar as clínicas (novo endereço; entrar de novo). O domínio antigo
   continua servindo o mesmo app por **60 dias**; depois, só as páginas
   redirecionam (a `/api/` continua respondendo pelos webhooks antigos).
7. Atualizar o CLAUDE.md (seção 1, produção; 7.1 concluído).

## F. Supabase Pro (usuário)

Organização atual → Billing → Pro (US$ 25/mês). Sem mudança no sistema;
liga backup diário de 7 dias e acaba com a pausa por inatividade.

## Ordem

1. PR de código (A + B + C + D-código), com testes; deploy no endereço atual.
2. Supabase Pro (pode ser já).
3. Quando o DNS propagar: SSL, `app.pandaup.com.br`, `.env`, webhooks,
   conferência, aviso às clínicas (E).
4. Homologação no servidor (D-servidor).
5. Em 60 dias: redirecionar as páginas do domínio antigo.

## Passos manuais em produção

Variáveis novas no `.env`: `SMTP_HOST`, `SMTP_PORTA`, `SMTP_USUARIO`,
`SMTP_SENHA`, `EMAIL_REMETENTE` (e trocar `URL_APP`/`ALLOWED_ORIGIN`/webhooks
no passo E). Caixa `nao-responda@pandaup.com.br` e `dmarc@pandaup.com.br`
criadas no cPanel. Sem migração de banco.
