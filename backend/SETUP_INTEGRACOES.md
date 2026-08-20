# Guia de configuração — Integrações reais

Esta rodada trocou os 3 "andaimes" (Google Agenda, Pagamento, WhatsApp) por
integrações de verdade. O código já está pronto — falta só criar as contas
e colar as credenciais. Nenhuma delas exige cartão de crédito para o modo
de teste/piloto.

---

## 1. Google Agenda (OAuth2) — ~15 minutos, grátis

Isso é configurado **uma vez pelo SaaS** (você), não por clínica — cada
clínica só clica em "Conectar" depois.

1. Acesse [console.cloud.google.com](https://console.cloud.google.com/) e crie um projeto novo.
2. Menu "APIs e serviços" → **Tela de consentimento OAuth**: tipo **Externo**.
   Preencha nome do app ("Panda Tech") e e-mail de contato. Em
   "Usuários de teste", adicione os e-mails do Gmail que vão testar (o seu
   e o das clínicas-piloto) — enquanto o app não passar pela verificação do
   Google, só esses e-mails conseguem autorizar.
3. "APIs e serviços" → **Biblioteca** → ative **Google Calendar API**.
4. "Credenciais" → **Criar credenciais** → **ID do cliente OAuth** → tipo
   **Aplicativo da Web**. Em "URIs de redirecionamento autorizados", adicione:
   `https://SEU-DOMINIO/api/integracoes/google_calendar/callback`
   (em teste local: `http://localhost:5000/api/integracoes/google_calendar/callback`)
5. Copie o **Client ID** e o **Client Secret** para o `.env` do backend
   (ver `.env.example`): `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
   `GOOGLE_OAUTH_REDIRECT_URI`.
6. Reinicie o backend. Na Central de Integrações, o gestor da clínica clica
   em "Conectar com o Google" e autoriza — pronto, a agenda passa a
   sincronizar de verdade.

**Limite do modo de teste:** só os e-mails cadastrados como "usuário de
teste" conseguem autorizar (até 100). Para abrir para qualquer clínica,
submeta o app para verificação do Google (leva alguns dias, só necessário
quando sair do piloto).

---

## 2. Pagamento — PIX via Mercado Pago — ~10 minutos, grátis

Cada clínica configura o **próprio** Access Token (não é uma conta
centralizada do SaaS) — o dinheiro cai direto na conta da clínica.

1. A clínica cria (ou já tem) uma conta em [mercadopago.com.br](https://www.mercadopago.com.br/).
2. Acessa [mercadopago.com.br/developers/panel](https://www.mercadopago.com.br/developers/panel/) → cria uma aplicação.
3. Em "Credenciais de teste" (sandbox, sem dinheiro real) ou "Credenciais de
   produção" (dinheiro real), copia o **Access Token**.
4. Na tela Central de Integrações do app, cola o Access Token em
   "Gateway de pagamento" → Salvar.
5. (Opcional, mas recomendado antes de ir para clientes reais) Em
   "Webhooks" no painel do Mercado Pago, copie a **Chave secreta** e
   configure `MP_WEBHOOK_SECRET` no `.env` do servidor — isso garante que
   só o Mercado Pago consegue confirmar pagamentos.
6. Configure também `MP_NOTIFICATION_URL` no `.env` do servidor, apontando
   para `https://SEU-DOMINIO/api/integracoes/pagamento/webhook` — é para lá
   que o Mercado Pago avisa quando um PIX é pago.

**Testar sem dinheiro real:** use as credenciais de teste do Mercado Pago —
elas geram PIX de teste que você "paga" com um usuário comprador fake do
próprio painel deles.

---

## 3. WhatsApp — Cloud API oficial da Meta — ~20 min a algumas horas, grátis

Pesquisei duas opções antes de decidir: o **sandbox da Twilio** é rotulado
pela própria documentação como "só para desenvolvimento" (um único número
compartilhado, não dá pra validar com famílias reais). A **Cloud API direto
da Meta** já nasce pronta para um piloto real: as primeiras 1.000 conversas
de serviço por mês são grátis, e dá pra testar com até 5 números de
verdade sem esperar a verificação completa da empresa.

1. Crie uma conta em [developers.facebook.com](https://developers.facebook.com/) → **Meus Apps** → **Criar app** → tipo "Empresa".
2. Adicione o produto **WhatsApp** ao app.
3. Em "WhatsApp → Introdução", a Meta já dá um **número de teste** grátis.
   Em "Para", adicione os números de telefone que vão testar (até 5, sem
   verificação de empresa) — cada um recebe um código de confirmação por
   WhatsApp.
4. Copie o **Temporary access token** (válido por 24h — para produção,
   crie um token permanente via um "System User", em Configurações do
   Business) e o **Phone number ID** (aparece na mesma tela).
5. Na Central de Integrações do app, cole os dois campos em "WhatsApp
   Business" → Salvar. Use o botão "Enviar teste" para confirmar.
6. **Crie os templates de mensagem** usados pelos lembretes automáticos —
   em "WhatsApp → Gerenciador de mensagens" → Templates → Nova:
   - `lembrete_consulta` (categoria Utilidade): "Olá! Consulta de
     {{1}} agendada para {{2}}. Qualquer dúvida, fale com a clínica."
   - `lembrete_missao` (categoria Utilidade): "Nova atividade disponível
     para {{1}}: {{2}}. Abra o app para conferir! 🌟"
   A aprovação de um template novo costuma sair em minutos a poucas horas.

**Para produção real (depois do piloto):** troque o número de teste por um
número comercial de verdade (linha de telefone da clínica ou um número
dedicado) e passe pela verificação de empresa da Meta.

---

## Variáveis de ambiente — resumo

Ver `.env.example` para a lista completa. Nenhuma integração exige reiniciar
o banco de dados — só o processo do backend, para carregar o `.env` de novo.
