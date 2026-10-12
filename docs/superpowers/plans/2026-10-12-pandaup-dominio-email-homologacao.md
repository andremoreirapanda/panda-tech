# PandaUp: domínio, e-mail e homologação — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nome PandaUp nas telas, recuperação de senha e convites por e-mail (SMTP), IP real atrás da Cloudflare (desligado) e marcação do ambiente de homologação — mais o passo a passo do servidor para a troca de domínio e a homologação.

**Architecture:** Módulo novo `email_service.py` (smtplib, configurado por variáveis de ambiente, nunca levanta exceção); `auth_bp.esqueci_senha` e as rotas que geram `link_convite` passam a enviar e-mail quando configurado; `rate_limit._ip_cliente` aceita `CF-Connecting-IP` só de IPs da Cloudflare com `ENCANTO_CLOUDFLARE=1`; `AMBIENTE=homologacao` injeta uma `<meta>` + faixa no front e `X-Robots-Tag`. Troca de textos "Panda Tech" → "PandaUp". O roteiro do servidor vira `docs/operacao/pandaup-dominio-e-homologacao.md`.

**Tech Stack:** Flask + smtplib (stdlib); JS puro; pytest; node --test.

**Spec:** `docs/superpowers/specs/2026-10-12-pandaup-dominio-email-homologacao-design.md`

## Global Constraints

- Windows: em `backend/`, `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q <arquivo>`; na raiz, `node --test frontend/tests/*.test.js`.
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Sem `SMTP_HOST`: envio desligado e comportamento atual mantido. `enviar_email` nunca levanta exceção para quem chama.
- Variáveis: `SMTP_HOST`, `SMTP_PORTA` (465 SSL / 587 STARTTLS), `SMTP_USUARIO`, `SMTP_SENHA`, `EMAIL_REMETENTE`, `URL_APP` (link absoluto); `ENCANTO_CLOUDFLARE` (padrão 0); `AMBIENTE` (`homologacao` ou ausente).
- Esqueci minha senha: resposta **idêntica** com ou sem conta; link nunca na resposta fora de `FLASK_DEBUG`.
- Nome: "PandaUp" em tudo o que o usuário vê; não mudam identificadores, tabelas, comentários nem valores gravados pelas clínicas no White Label.
- Sem migração de banco.

## Review Focus

1. **Destinatário ou nome com quebra de linha** (injeção de cabeçalho) → e-mail recusado, sem erro 500. Teste na Task 1.
2. **SMTP fora do ar ou senha errada** ao criar profissional/responsável → o cadastro acontece mesmo assim, com `enviado_email: false`. Teste na Task 3.
3. **Esqueci minha senha com e-mail inexistente, conta desativada ou excluída** → mesma resposta, nenhum e-mail. Teste na Task 2.
4. **Clínica com `app_nome` próprio no White Label** continua com o nome dela; só o padrão vira PandaUp. Teste na Task 4.
5. **`CF-Connecting-IP` falso** vindo de IP que não é da Cloudflare, ou com a variável desligada → ignorado. Teste na Task 5.

---

### Task 1: Módulo de e-mail
Files: create `backend/email_service.py`, test `backend/tests/test_email_service.py`.

Produces:
- `email_configurado() -> bool`
- `enviar_email(para: str, assunto: str, texto: str, html: str | None = None) -> bool`
- `link_absoluto(link_relativo: str) -> str | None` (None sem `URL_APP`)
- `email_redefinicao(nome: str, link: str) -> tuple[str, str, str]` (assunto, texto, html)
- `email_convite(nome: str, clinica: str, papel: str, link: str) -> tuple[str, str, str]`

- [ ] Testes (falham primeiro), com `smtplib.SMTP`/`SMTP_SSL` trocados por um falso que guarda as chamadas:
  - sem `SMTP_HOST` → `email_configurado()` False e `enviar_email` devolve False sem abrir conexão;
  - porta 465 usa `SMTP_SSL` + login + `send_message`; porta 587 usa `SMTP` + `starttls` + login;
  - mensagem tem `From` = `EMAIL_REMETENTE`, `To`, `Subject`, parte texto e parte HTML (multipart/alternative);
  - falha (exceção no `login`/`connect`) → False e `log_evento` com tipo `email_falhou` (sem a senha no payload);
  - `para` vazio, sem "@" ou com `\r`/`\n` → False sem conectar; assunto com quebra de linha é limpo (quebras viram espaço);
  - `link_absoluto("#/redefinir-senha?token=x")` com `URL_APP=https://app.pandaup.com.br/` → `https://app.pandaup.com.br/#/redefinir-senha?token=x`; sem `URL_APP` → None;
  - modelos: `email_convite` escapa `<script>` no nome/clínica no HTML; ambos contêm o link e "PandaUp".
- [ ] Implementar (`email.message.EmailMessage`, `set_content` + `add_alternative`, timeout 10 s, `ssl.create_default_context()`). Commit.

### Task 2: Esqueci minha senha por e-mail
Files: `backend/blueprints/auth_bp.py`, test `backend/tests/test_email_senha.py`.

Consumes: `email_configurado`, `enviar_email`, `link_absoluto`, `email_redefinicao`.

- [ ] Testes (falham primeiro), com `FLASK_DEBUG` desligado para o app do teste (`auth._DEV_MODE = False` via monkeypatch) e e-mail configurado (monkeypatch das variáveis + falso de `enviar_email`):
  - e-mail cadastrado e ativo → 200, mensagem "Se este e-mail estiver cadastrado, enviamos um link para redefinir a senha.", um envio com link absoluto que valida em `/api/auth/validar-token-redefinicao/<token>`; resposta **sem** `link_redefinicao`;
  - e-mail inexistente, conta `ativo = 0` e conta com `excluido_em` → resposta igual (mesmo JSON) e nenhum envio;
  - e-mail com maiúsculas e espaços acha a conta;
  - sem e-mail configurado → mensagem atual (pedir ao gestor), com "PandaUp", sem envio;
  - `FLASK_DEBUG` ligado continua devolvendo o link (comportamento de desenvolvimento).
- [ ] Implementar. Commit.

### Task 3: Convites por e-mail
Files: `backend/blueprints/pessoas_bp.py` (criar profissional, secretária, responsável/`vincular_responsavel_core`, reenviar convite de profissional/secretária/responsável), `backend/blueprints/admin_bp.py` (gestor da clínica nova, reenviar ao gestor, criar usuário admin se gerar link), `frontend/js/views/*` que mostram o link do convite, test `backend/tests/test_email_convites.py`.

Consumes: `enviar_email`, `link_absoluto`, `email_convite`. Produces: helper `convites_email.enviar_convite(usuario_id, link_relativo) -> bool` em `backend/email_service.py` (lê nome, e-mail, papel e nome da clínica do banco).

- [ ] Testes (falham primeiro): cada rota que devolve `link_convite` passa a devolver `enviado_email` (True com envio falso bem-sucedido; False sem SMTP); o envio usa o e-mail e o nome do convidado e o nome da clínica; **SMTP falhando** → a rota responde 201/200 normalmente e o usuário existe, com `enviado_email: false`; importação de pacientes não manda e-mail em massa (continua como hoje — confirmar no teste que `enviar_email` não é chamado pela importação).
- [ ] Implementar. No front, onde o link do convite aparece, quando `enviado_email` for true mostrar "Convite enviado para <e-mail>" (além do link para copiar/WhatsApp). Commit.

### Task 4: Nome PandaUp
Files: `frontend/index.html`, `frontend/js/shell.js`, `frontend/js/util.js`, `frontend/js/views/login.js`, `admin_integracoes.js`, `identidade_clinica.js`, `modulos.js`, `pandoo.js`, e mensagens (não comentários) em `backend/app.py`, `blueprints/auth_bp.py`, `admin_bp.py`, `integracoes_bp.py`, `modulos_bp.py`, `pandoo_bp.py`, `calendar_sync_service.py`, `identidade_service.py`, `modulos_service.py`, `pagamento_plataforma_service.py`, `pagamento_service.py`, `relatorio_service.py`, `whatsapp_service.py`; test `backend/tests/test_nome_pandaup.py` e `frontend/tests/nome_pandaup.test.js`.

- [ ] Testes (falham primeiro):
  - Node: nenhum arquivo de `frontend/js/**` (fora de `vendor/`) nem `frontend/index.html` contém "Panda Tech" fora de comentários (`//`, `/* */`, `<!-- -->`);
  - Python: varrer os `.py` de `backend/` (fora de `tests/`, `venv/`, `seed*.py`, `migrar_*.py`) com `ast`, pegando só **strings que não são docstrings**, e exigir que nenhuma contenha "Panda Tech";
  - `identidade_service.identidade_efetiva` de uma clínica sem `app_nome` devolve "PandaUp"; com `app_nome = "Clínica Sol"` e White Label ativo, devolve "Clínica Sol";
  - `/api/health` devolve `"produto": "PandaUp"`.
- [ ] Trocar as strings. Commit.

### Task 5: IP real atrás da Cloudflare (desligado)
Files: `backend/rate_limit.py`, `backend/.env.example`, test `backend/tests/test_ip_cloudflare.py`.

- [ ] Testes (falham primeiro) chamando `_ip_cliente()` dentro de `app.test_request_context(environ_base={"REMOTE_ADDR": ...}, headers={...})`:
  - variável ausente → `remote_addr`, mesmo com `CF-Connecting-IP`;
  - `ENCANTO_CLOUDFLARE=1` e `REMOTE_ADDR` numa faixa da Cloudflare (ex.: `173.245.48.10`, IPv6 `2400:cb00::1`) → valor de `CF-Connecting-IP`;
  - `ENCANTO_CLOUDFLARE=1` e `REMOTE_ADDR` fora das faixas → `remote_addr`;
  - `CF-Connecting-IP` inválido (texto) → `remote_addr`.
- [ ] Implementar com `ipaddress` e a lista oficial (IPv4 e IPv6 de https://www.cloudflare.com/ips/, com a data da cópia no comentário); a leitura da variável no momento da chamada (para o teste trocar). Documentar no `.env.example`. Commit.

### Task 6: Marca do ambiente de homologação
Files: `backend/app.py` (`_index_html`, cabeçalhos, `/api/health`), `backend/versao_front.py` ou `app.py` (meta), `frontend/js/ambiente.js` (novo), `frontend/index.html`, `frontend/css/components.css`, test `backend/tests/test_ambiente.py`.

- [ ] Testes (falham primeiro): com `AMBIENTE=homologacao` → `index.html` tem `<meta name="ambiente" content="homologacao">`, toda resposta (página e `/api/...`) tem `X-Robots-Tag: noindex, nofollow`, `/api/health` tem `"ambiente": "homologacao"`; sem a variável → nada disso (e `ambiente` = "producao").
- [ ] Implementar. `ambiente.js` lê a meta e, se for homologação, insere no `body` uma faixa fixa "AMBIENTE DE TESTE — dados fictícios" (CSS `.faixa-ambiente`, sem cobrir o conteúdo: `body` ganha `padding-top` e a faixa respeita `env(safe-area-inset-top)`). Browser: faixa visível no login, na agenda e no Mundo da Criança. Commit.

### Task 7: Roteiro do servidor e fechamento
Files: create `docs/operacao/pandaup-dominio-e-homologacao.md`; `backend/.env.example`; `CLAUDE.md`.

- [ ] Roteiro em português, para o usuário executar, com comandos prontos:
  1. Supabase Pro (painel).
  2. Caixas `nao-responda@pandaup.com.br` e `dmarc@pandaup.com.br` no cPanel; dados do SMTP (servidor, porta 465).
  3. Conferir DNS (Cloudflare só DNS) e rodar o AutoSSL.
  4. `app.pandaup.com.br` servindo o mesmo app: linhas do `.htaccess` do Passenger copiadas da pasta do domínio atual para `~/app.pandaup.com.br/.htaccess` (`PassengerAppRoot`, `PassengerBaseURI /`, `PassengerPython` do virtualenv), conferir com `curl -I https://app.pandaup.com.br/api/health`.
  5. `pandaup.com.br` → redirecionamento 301 para `https://app.pandaup.com.br` (Redirecionamentos do cPanel).
  6. `.env` da produção: variáveis SMTP, `URL_APP`, `ALLOWED_ORIGIN`, webhooks do Mercado Pago, `GOOGLE_OAUTH_REDIRECT_URI`; `touch tmp/restart.txt`.
  7. Mercado Pago e Google Cloud.
  8. Conferência (login, senha esquecida, convite, checkout, PIX).
  9. Texto pronto para avisar as clínicas.
  10. Homologação: projeto Supabase gratuito em outra organização, `psql` com `schema_postgres.sql`, `seed.py` com `DATABASE_URL` de teste, segundo app Python no cPanel em `~/pandaup-teste` ligado a `teste.pandaup.com.br`, `.env` de teste, e o comando para testar um branch.
  11. Daqui a 60 dias: redirecionar só as páginas do domínio antigo (regra que deixa `/api/` passar).
- [ ] `.env.example` com as variáveis novas comentadas. CLAUDE.md: item `al)` na seção 5, conceito de e-mail na seção 6, seção 7.1 apontando para o roteiro, seção 8 com `email_service.py` e o roteiro.
- [ ] Suítes completas; revisão final (revisor novo, model fable); correções; PR. Sem schema → merge automático com CI verde. Avisar o usuário dos passos manuais do roteiro.
