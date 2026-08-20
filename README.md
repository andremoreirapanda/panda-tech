# 🌟 Encanto em Casa — Plataforma de Desenvolvimento Infantil

Aplicação full-stack (backend + frontend + banco de dados) construída a partir
dos 9 documentos de arquitetura do projeto (Overview, Arquitetura Funcional,
Arquitetura da Informação, Domain Map, Arquitetura Modular, Arquitetura das
Jornadas, UX Blueprint, Information Architecture e Screen Specification Book).

> Este projeto foi testado ponta a ponta durante a construção (API via
> `requests`, telas via Playwright) mas depende de você rodar `pip install`
> na sua máquina, já que o ambiente onde foi gerado não tinha acesso à
> internet para instalar pacotes.

---

## 🧱 Stack técnica

| Camada     | Tecnologia                                      |
|------------|--------------------------------------------------|
| Backend    | Python 3 + Flask + SQLite (SQL puro, sem ORM)    |
| Auth       | JWT (PyJWT) com controle de papéis (RBAC)        |
| Frontend   | HTML + CSS + JavaScript vanilla (SPA, sem build) |
| Banco      | SQLite (arquivo único, zero configuração)         |

Não escolhi um framework de frontend com etapa de build (React/Vue) de
propósito: assim você abre o projeto e roda sem precisar instalar Node,
webpack, etc. O código já está organizado em componentes/módulos JS
(`frontend/js/views/*.js`), então é direto migrar para React depois, se quiser.

---

## 🚀 Como rodar

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python seed.py                    # cria o banco encanto.db e popula dados de demonstração
python app.py                     # sobe o servidor em http://localhost:5000
```

Abra **http://localhost:5000** no navegador. O Flask já serve o front-end
(pasta `frontend/`) junto com a API — não precisa de um segundo servidor.

### Credenciais de demonstração

| Perfil                  | E-mail                              | Senha       |
|--------------------------|--------------------------------------|-------------|
| Admin da Plataforma (SaaS) | admin@encantoemcasa.com           | admin123    |
| Gestor (clínica)         | andre@clinicaencantar.com.br         | gestor123   |
| Profissional (Fono)      | camila@clinicaencantar.com.br        | prof123     |
| Profissional (T.O.)      | rafael@clinicaencantar.com.br        | prof123     |
| Profissional (Psicop.)   | juliana@clinicaencantar.com.br       | prof123     |
| Responsável               | ana@familia.com                     | familia123  |

A tela de login tem botões de atalho que preenchem essas contas automaticamente.

Para recomeçar do zero a qualquer momento: `python seed.py` (recria o banco).

---

## 🗂️ Estrutura do projeto

```
encanto-em-casa/
├── backend/
│   ├── app.py                 # Flask app + registro de blueprints
│   ├── db.py                  # acesso ao SQLite + log de eventos/auditoria
│   ├── auth.py                # JWT, hashing de senha, RBAC, isolamento multi-tenant
│   ├── schema.sql              # schema completo do banco (10 domínios)
│   ├── seed.py                 # popula dados de demonstração realistas
│   ├── gamificacao_service.py  # motor de XP/medalhas, consumidor de eventos
│   └── blueprints/              # 1 arquivo por domínio de negócio
│       ├── auth_bp.py, pessoas_bp.py, jornada_bp.py, biblioteca_bp.py,
│       ├── comunicacao_bp.py, agenda_bp.py, gamificacao_bp.py,
│       ├── financeiro_bp.py, indicadores_bp.py, notificacoes_bp.py, admin_bp.py
└── frontend/
    ├── index.html
    ├── css/  (tokens.css, layout.css, components.css)
    └── js/
        ├── api.js, router.js, shell.js, util.js, toast.js, mascote.js, app.js
        └── views/  (1-2 arquivos por experiência: login, dashboards, jornada,
                      biblioteca, agenda, comunicação, financeiro, responsável,
                      criança, admin)
```

---

## 🧭 Como o código reflete os documentos de arquitetura

- **Domain Map (Doc 09)** → cada tabela do `schema.sql` pertence a exatamente
  um dos 10 domínios, e cada blueprint do backend corresponde a um domínio.
  O domínio **Indicadores** não tem tabelas próprias — só lê eventos e outras
  tabelas, como especificado ("não cria dados, apenas interpreta eventos").
- **Arquitetura da Informação (Doc 08)** → o fluxo de exemplo do documento
  ("missão concluída → evento → gamificação → notificação → indicadores")
  está implementado literalmente em `jornada_bp.py::concluir_missao()` →
  `gamificacao_service.py::processar_missao_concluida()`.
- **Arquitetura Modular (Doc 10)** → o Financeiro foi construído com a
  postura "complementa, não substitui o ERP" (não há folha de pagamento,
  nota fiscal, DRE — só cobranças e confirmação de pagamento).
- **Arquitetura das Jornadas (Doc 11)** → os dashboards do Gestor
  ("4 perguntas em 30 segundos") e do Profissional ("dentro do planejado /
  baixa adesão / precisa de atenção") replicam os critérios de cálculo
  descritos no documento.
- **UX Blueprint / Screen Specification Book (Docs 12-13)** → os 18 UX
  Patterns do documento viraram as ~20 telas do frontend (login, dashboards,
  cadastro, listas, jornada terapêutica, biblioteca, chat, agenda, mundo da
  criança, execução de missão, medalhas, financeiro, indicadores, mural,
  configurações, admin do SaaS).

---

## ✅ Integrações reais (atualização desta rodada)

Google Agenda (OAuth2), Mercado Pago (PIX) e WhatsApp (Cloud API oficial da
Meta) saíram do "andaime" simulado e viraram integrações de verdade — ver
`backend/SETUP_INTEGRACOES.md` para o passo a passo de credenciais de cada
uma. Sem as credenciais configuradas, tudo continua funcionando normalmente
(cada integração cai de volta pro estado "desconectado", sem quebrar nada).

## ⚠️ Limitações conhecidas (honestidade sobre o escopo)

Este é um projeto **funcional e testado**, mas ainda não é um produto pronto
para produção em larga escala. Pontos que ficam de fora de propósito:

- **ERP** — continua só o toggle liga/desliga; sem saber qual ERP a
  clínica-piloto usa de verdade, não dá pra escolher um adapter específico.
- **Upload de arquivos reais** (vídeos, PDFs, imagens na Biblioteca) — os
  exercícios armazenam uma URL, mas não há upload de arquivo binário.
- **IA / geração de missões automática** — mencionada no roadmap dos
  documentos como Fase 3, não implementada.
- **Testes automatizados formais** (pytest) — a validação foi feita via
  scripts manuais de teste de API durante a construção; não há uma suíte de
  testes no repositório.
- **Produção**: o servidor Flask embutido (`python app.py`) é para
  desenvolvimento — em produção, rode com Gunicorn (já no
  `requirements.txt`) atrás de um proxy, e migre de SQLite para PostgreSQL
  (o `schema.sql` é quase todo compatível — os principais ajustes seriam
  tipos `SERIAL`/`TIMESTAMP` no lugar de `AUTOINCREMENT`/`TEXT`). Ver
  recomendação completa de banco e hospedagem no relatório desta rodada.
- **Segredos**: defina `ENCANTO_SECRET` e `ENCANTO_CRYPTO_KEY` (ver
  `backend/.env.example`) antes de expor o app publicamente — sem isso, o
  app usa uma chave padrão de desenvolvimento conhecida.

Se quiser, posso aprofundar qualquer um desses pontos, ou qualquer tela/fluxo
específico, na sequência.
