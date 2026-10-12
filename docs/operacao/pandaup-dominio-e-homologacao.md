# PandaUp — roteiro do domínio novo, e-mail e homologação

Passo a passo para executar no servidor (cPanel da Napoleon, conta
`mimosart`) depois que o PR "PandaUp: domínio, e-mail por SMTP e
homologação" estiver no `main`. Desenho em
`docs/superpowers/specs/2026-10-12-pandaup-dominio-email-homologacao-design.md`.

Valores usados abaixo:

| O quê | Valor |
|---|---|
| IP do servidor | `186.209.113.98` |
| Pasta do app de produção | `~/panda-tech` |
| Virtualenv de produção | `/home/mimosart/virtualenv/panda-tech/3.11/bin/activate` |
| Sistema | `https://app.pandaup.com.br` |
| Homologação | `https://teste.pandaup.com.br` (pasta `~/pandaup-teste`) |
| Domínio antigo (fica no ar por 60 dias) | `https://pandatech.pandacriacao.com.br` |

A ordem importa: o domínio antigo **continua servindo o mesmo app** o tempo
todo. Cobranças e assinaturas já criadas no Mercado Pago guardam o endereço
antigo do webhook, e um redirecionamento perderia essas notificações.

---

## 1. Supabase Pro (painel)

supabase.com → organização atual → **Billing** → **Change plan** → **Pro**
(US$ 25/mês). Não muda nada no sistema. Liga o backup diário (7 dias) e
acaba com a pausa por inatividade.

## 2. Caixas de e-mail (cPanel → Contas de e-mail)

1. Crie `nao-responda@pandaup.com.br` com uma senha forte (vai no `.env`,
   passo 6). Cota pequena basta (50 MB).
2. Crie `dmarc@pandaup.com.br`, que recebe os relatórios do DMARC.
3. Em **Conectar dispositivos** da caixa `nao-responda`, anote o "Servidor
   de saída" (normalmente `mail.pandaup.com.br`) e a porta **SMTP 465
   (SSL)**.

## 3. DNS e certificado

1. Cloudflare → `pandaup.com.br` → DNS. Confira se existem estes registros,
   todos com a **nuvem cinza** ("Somente DNS"):
   - `A` para `pandaup.com.br`, `app` e `teste` → `186.209.113.98`;
   - `MX`, `SPF` (`v=spf1 +ip4:186.209.113.98 -all`) e `DKIM` (copiados do
     cPanel → Email Deliverability);
   - `TXT` `_dmarc` → `v=DMARC1; p=none; rua=mailto:dmarc@pandaup.com.br; adkim=r; aspf=r`.
   Apague o registro `PTR` importado, se ele ainda existir.
2. Espere a propagação. Para conferir: `nslookup app.pandaup.com.br 1.1.1.1`
   tem que responder `186.209.113.98`.
3. cPanel → **Domínios**: crie `app.pandaup.com.br` e `teste.pandaup.com.br`
   como domínios separados, cada um com **sua própria raiz de documentos**
   (desmarque "compartilhar a raiz com public_html").
4. cPanel → **SSL/TLS Status** → marque `pandaup.com.br`, `app.` e `teste.`
   → **Run AutoSSL**. Espere todos ficarem com o cadeado verde.
5. Cloudflare → SSL/TLS → modo **Full (strict)**. Com a nuvem cinza esse
   modo ainda não faz diferença, mas já deixa pronto para quando o proxy
   for ligado.

## 4. `app.pandaup.com.br` servindo o mesmo app

O Passenger serve o app pela configuração no `.htaccess` da raiz do domínio.
A ideia é copiar o mesmo bloco do domínio atual para o novo.

No Terminal do cPanel:

```bash
# 1. Achar o .htaccess do domínio atual (o que tem o bloco do Passenger)
grep -l PassengerAppRoot ~/*/.htaccess ~/public_html/*/.htaccess 2>/dev/null

# 2. Ver o bloco (troque o caminho pelo que apareceu acima)
sed -n '/PASSENGER CONFIGURATION BEGIN/,/PASSENGER CONFIGURATION END/p' ~/CAMINHO/DO/DOMINIO/ATUAL/.htaccess
```

O bloco é parecido com este:

```apache
# DO NOT REMOVE. CLOUDLINUX PASSENGER CONFIGURATION BEGIN
PassengerAppRoot "/home/mimosart/panda-tech"
PassengerBaseURI "/"
PassengerPython "/home/mimosart/virtualenv/panda-tech/3.11/bin/python"
# DO NOT REMOVE. CLOUDLINUX PASSENGER CONFIGURATION END
```

```bash
# 3. Copiar o bloco para a raiz do app.pandaup.com.br
#    (a pasta é a raiz de documentos que o cPanel criou no passo 3.3)
sed -n '/PASSENGER CONFIGURATION BEGIN/,/PASSENGER CONFIGURATION END/p' \
    ~/CAMINHO/DO/DOMINIO/ATUAL/.htaccess >> ~/app.pandaup.com.br/.htaccess

# 4. Conferir
curl -s https://app.pandaup.com.br/api/health
```

A resposta tem que ser `{"ambiente":"producao","produto":"PandaUp","status":"ok"}`.

Não use o "Setup Python App" para criar um segundo app de produção: ele
abriria outro processo com outro `.env`. São dois endereços para **o mesmo**
app.

## 5. `pandaup.com.br` → `app.pandaup.com.br`

cPanel → **Redirecionamentos**: tipo **Permanente (301)**, domínio
`pandaup.com.br`, caminho `/`, redirecionar para
`https://app.pandaup.com.br`, opção **"Redirecionar com ou sem www"**.
Conferir: `curl -sI https://pandaup.com.br | grep -i location`.

## 6. `.env` da produção

Edite `~/panda-tech/backend/.env` (Gerenciador de arquivos ou `nano`). Troque
ou acrescente:

```ini
URL_APP=https://app.pandaup.com.br
ALLOWED_ORIGIN=https://app.pandaup.com.br
MP_NOTIFICATION_URL=https://app.pandaup.com.br/api/integracoes/pagamento/webhook
MP_PLATAFORMA_NOTIFICATION_URL=https://app.pandaup.com.br/api/admin/integracoes/pagamento/webhook
# só se esta variável já existir no arquivo:
GOOGLE_OAUTH_REDIRECT_URI=https://app.pandaup.com.br/api/integracoes/google_calendar/callback

SMTP_HOST=mail.pandaup.com.br
SMTP_PORTA=465
SMTP_USUARIO=nao-responda@pandaup.com.br
SMTP_SENHA=a-senha-criada-no-passo-2
EMAIL_REMETENTE=PandaUp <nao-responda@pandaup.com.br>
```

Depois:

```bash
cd ~/panda-tech && touch tmp/restart.txt
```

`ALLOWED_ORIGIN` aceita uma origem só. O domínio antigo continua
funcionando, porque nele a tela e a API vêm do mesmo endereço (o CORS não
entra em jogo).

## 7. Mercado Pago e Google

- **Mercado Pago da plataforma** (mercadopago.com.br/developers/panel → sua
  aplicação → Webhooks): URL nova
  `https://app.pandaup.com.br/api/admin/integracoes/pagamento/webhook`.
- **Clínicas com Mercado Pago próprio**: no painel de cada uma, a URL
  `https://app.pandaup.com.br/api/integracoes/pagamento/webhook`.
- **Google Cloud Console** → Credenciais → o cliente OAuth → **URIs de
  redirecionamento autorizados**: acrescente
  `https://app.pandaup.com.br/api/integracoes/google_calendar/callback` e
  mantenha o antigo. Se a integração foi salva pela tela do Admin, o endereço
  antigo está gravado no banco e vale mais que o `.env`: em Admin →
  Integrações → Google Agenda, salve de novo com o endereço novo.

## 8. Conferência

Em `https://app.pandaup.com.br`:

1. Entrar com a sua conta de admin.
2. "Esqueci minha senha" com o seu e-mail: o e-mail chega? (Veja também o
   spam.) O link abre a tela de nova senha?
3. Reenviar o link de acesso para um gestor de teste: a tela mostra
   "📧 Convite enviado para …" e o e-mail chega?
4. "Sua Assinatura" de uma clínica de teste: o checkout do cartão volta para
   `app.pandaup.com.br`?
5. Um PIX de valor baixo: a cobrança fica paga sozinha (webhook)?
6. Se um e-mail não chegar, veja no SQL Editor do Supabase:
   `select * from eventos where tipo = 'email_falhou' order by id desc limit 5;`
   (a coluna `payload_json` traz o tipo do erro).

Teste de entrega (nota de spam): mande um convite para o endereço que o site
mail-tester.com mostra e confira a nota (meta: 9/10 ou mais).

## 9. Aviso às clínicas (texto pronto)

> **O Panda Tech agora é PandaUp** 🐼
>
> A partir de hoje, o sistema fica em **https://app.pandaup.com.br**.
> Salve o novo endereço nos favoritos (e, no celular, adicione de novo à
> tela inicial).
>
> No primeiro acesso pelo endereço novo, é preciso **entrar de novo** com o
> mesmo e-mail e senha. Nenhum dado muda.
>
> O endereço antigo continua funcionando por 60 dias.
>
> Novidade: o "Esqueci minha senha" agora manda o link por e-mail, e os
> convites para a equipe e as famílias também chegam por e-mail.

## 10. Homologação (`teste.pandaup.com.br`)

Só dados fictícios. **Nunca** copie dados de produção para cá.

1. **Banco**: em supabase.com, crie uma **organização nova, gratuita**
   (por exemplo, "PandaUp Teste"; fora da organização Pro, para não
   cobrar) e nela o projeto `pandaup-teste`, região `sa-east-1`. Anote a
   senha do banco.
2. **Schema**: no SQL Editor do projeto de teste, cole o conteúdo de
   `backend/schema_postgres.sql` e rode.
3. **Código**:
   ```bash
   cd ~ && git clone https://github.com/andremoreirapanda/panda-tech.git pandaup-teste
   ```
4. **App Python**: cPanel → **Setup Python App** → **Create Application**:
   Python 3.11, Application root `pandaup-teste`, Application URL
   `teste.pandaup.com.br`, Application startup file `passenger_wsgi.py`,
   Entry point `application`. Depois de criar, copie o comando
   `source …/activate` que aparece no topo da página.
5. **Dependências**:
   ```bash
   source /home/mimosart/virtualenv/pandaup-teste/3.11/bin/activate
   cd ~/pandaup-teste && pip install -r backend/requirements.txt
   ```
6. **`.env` de teste** em `~/pandaup-teste/backend/.env`. Gere segredos
   **novos** (nunca os da produção):
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"            # ENCANTO_SECRET
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # ENCANTO_CRYPTO_KEY
   ```
   ```ini
   DATABASE_URL=postgresql://...  (Supabase de TESTE → Connect → Session pooler)
   ENCANTO_SECRET=...
   ENCANTO_CRYPTO_KEY=...
   AMBIENTE=homologacao
   URL_APP=https://teste.pandaup.com.br
   ALLOWED_ORIGIN=https://teste.pandaup.com.br
   FLASK_DEBUG=0
   # e-mail: pode usar a mesma caixa nao-responda
   SMTP_HOST=mail.pandaup.com.br
   SMTP_PORTA=465
   SMTP_USUARIO=nao-responda@pandaup.com.br
   SMTP_SENHA=...
   EMAIL_REMETENTE=PandaUp Teste <nao-responda@pandaup.com.br>
   ```
   Mercado Pago: deixe sem credenciais ou use as **de teste** do MP. Google:
   deixe desligado.
7. **Planos e admin**: o `seed_producao.py` não lê o `.env` sozinho, então
   passe o banco pela linha de comando:
   ```bash
   cd ~/pandaup-teste/backend
   DATABASE_URL='postgresql://...teste...' python seed_producao.py
   ```
   A primeira linha tem que dizer **Postgres (DATABASE_URL)**. Se disser
   SQLite, o `DATABASE_URL` não foi passado.
8. `touch ~/pandaup-teste/tmp/restart.txt` e abra
   `https://teste.pandaup.com.br`. A faixa vermelha **"AMBIENTE DE TESTE —
   dados fictícios"** tem que aparecer no topo, e
   `curl -s https://teste.pandaup.com.br/api/health` traz `"ambiente":"homologacao"`.
9. Pela tela do admin, crie uma clínica fictícia (por exemplo, "Clínica
   Demonstração") com gestor, profissionais, pacientes e famílias inventados.

**Para testar um branch antes do merge:**

```bash
source /home/mimosart/virtualenv/pandaup-teste/3.11/bin/activate
cd ~/pandaup-teste && git fetch && git checkout NOME-DO-BRANCH && git pull \
  && pip install -r backend/requirements.txt && touch tmp/restart.txt
```

Se o branch tiver migração, rode o `.sql` no SQL Editor do projeto
**de teste** antes. Para voltar ao `main`: `git checkout main && git pull`
e o mesmo `touch`.

## 11. Daqui a 60 dias: só as páginas do domínio antigo

No `.htaccess` da raiz do domínio antigo, **acima** do bloco do Passenger:

```apache
RewriteEngine On
RewriteCond %{REQUEST_URI} !^/api/
RewriteRule ^ https://app.pandaup.com.br%{REQUEST_URI} [R=301,L]
```

As páginas passam a ir para o endereço novo, e a `/api/` continua
respondendo no antigo (webhooks de cobranças antigas). Depois disso,
atualize o CLAUDE.md (seção 1, "Produção").
