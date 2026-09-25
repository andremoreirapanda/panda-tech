# Agenda: novo layout, horário da clínica e vínculo automático ao agendar

Data: 24/09/2026 · Status: design aprovado pelo usuário (revisado após a revisão da spec)

## Objetivo

1. A agenda de cada profissional deve caber inteira numa tela, sem rolar a
   página, com a lista de profissionais numa coluna lateral — no modelo da
   agenda do Clínica Ágil que o usuário mostrou.
2. A clínica pode definir o horário de funcionamento, e a grade se enquadra
   nele.
3. Quem atende um paciente precisa ter acesso completo a ele: agendar um
   paciente na agenda de um profissional o vincula a esse paciente.

Fora do escopo (decisão do usuário): ligar o Diário Terapêutico à consulta —
virá numa alteração maior feita por ele. Horário por profissional e dias de
funcionamento configuráveis também ficam de fora.

## Parte 1 — Vínculo automático ao agendar (PR 1, sem schema)

Hoje um profissional **vê** qualquer paciente da clínica
(`auth.paciente_acessivel`), mas só **edita** (plano, missões, diário) quem
tem linha em `profissionais_pacientes` (`auth.paciente_editavel`).

Regra nova: toda vez que uma consulta passa a ter um `profissional_id` cujo
usuário tem `papel = 'profissional'`, o sistema garante a linha
`profissionais_pacientes (usuario_id, paciente_id)`:

- `POST /api/agenda` (consulta única);
- `POST /api/agenda/recorrente` (uma vez para a série);
- `PUT /api/agenda/<id>` quando o `profissional_id` muda (reatribuição).

Detalhes:

- Vale para qualquer papel que agende (profissional, gestor, secretária,
  admin): quem atende passa a ter acesso.
- Se o destino é um gestor (a lista da agenda inclui gestores via
  `incluir_gestor=1`), nada é criado — o gestor já tem acesso total.
- `principal = 1` só se o paciente ainda não tem nenhum profissional
  principal (mesma regra de `pessoas_bp.vincular_profissional`); senão 0.
- Idempotente: se o vínculo já existe, não faz nada (sem erro 409).
- O vínculo é permanente: cancelar/excluir a consulta não o remove. O
  gestor continua podendo desvincular pela ficha, como hoje.
- Registrar em `log_auditoria` ("vincular", "profissional_paciente") só
  quando o vínculo é de fato criado.
- Implementação: um helper único (ex.: `_garantir_vinculo_profissional` em
  `agenda_bp.py`) chamado nos três pontos.

Testes (`backend/tests/`): vínculo criado ao agendar (única, recorrente,
reatribuição); não duplica; não cria para gestor; `principal` correto; o
profissional passa a conseguir editar o paciente (ex.: criar diário/missão)
depois de agendar.

## Parte 2 — Horário de funcionamento da clínica (PR 2, com schema)

Schema: duas colunas novas em `organizacoes`, nulas por padrão, formato
`HH:MM`:

- `agenda_hora_inicio TEXT`
- `agenda_hora_fim TEXT`

Arquivos: `schema.sql`, `schema_postgres.sql`,
`backend/migracoes/migracao_horario_agenda.sql` e
`backend/migrar_horario_agenda.py` (padrão dos `migrar_*.py` existentes,
idempotente). Incluir o `.sql` novo nos workflows que aplicam migrações
(`tests.yml`/`db-setup.yml`) se for o padrão dos anteriores.

Backend:

- O `UPDATE organizacoes` de Configurações (`pessoas_bp.py`, ~l.1191) passa
  a aceitar os dois campos. Validação: ambos vazios (limpa) ou ambos
  `HH:MM` válidos (00:00–23:59, qualquer minuto — horário "picado" como
  19:15 é permitido), com início < fim. Erro 400 com mensagem clara caso
  contrário.
- Os campos entram em `CAMPOS_ORG` (`auth_bp.py`) para o front recebê-los
  junto com os outros dados da clínica.

Front-end: em Configurações da clínica (gestor), campo "Horário de
funcionamento da agenda" com início e fim (`<input type="time">`, qualquer
minuto) e opção de deixar em branco ("automático").

Testes: salvar, limpar, rejeitar formato inválido e início ≥ fim; campos
devolvidos no `/auth/me` (ou onde a org é carregada).

**Passo manual em produção**: rodar a migração no Supabase (SQL Editor ou
`migrar_horario_agenda.py`, conferindo a saída `(Postgres)`).

## Parte 3 — Layout da agenda (PR 2, junto com a Parte 2)

Referência visual: prévia aprovada
(`.superpowers/brainstorm/.../agenda-layout.html`, não versionada).

Arquivos: `frontend/js/views/agenda.js`, `frontend/css/components.css`.
Só gestor, profissional e secretária; a agenda do responsável (lista no
shell mobile) não muda.

### Estrutura

- **Barra única no topo** (uma linha, quebra em telas estreitas): título
  "Agenda", alternância Geral da Clínica / Por Profissional, ← Hoje →
  com o período, seletor Lista/Semana/Mês (só no modo Geral, como hoje) e
  "+ Agendar" à direita.
- **Corpo em duas colunas**: lista de profissionais (~230px) + área da
  agenda. O corpo ocupa a altura restante da janela
  (`height: calc(100vh - topo)`, via flex), sem rolagem da página.
- **Lista lateral de profissionais** (substitui as pílulas
  `.agenda-pills-profissionais`): bolinha/avatar na cor do profissional,
  nome, especialidade; campo "Filtrar" que filtra por nome no cliente; o
  selecionado fica destacado. Rola internamente se houver muitos.
  - Modo **Por Profissional**: clicar troca a agenda exibida.
  - Modo **Geral**: item "Todos" no topo (selecionado); clicar num
    profissional muda para o modo Por Profissional já com ele selecionado.
- **Telas ≤ 900px**: a lista lateral vira uma faixa horizontal rolável acima
  da agenda, e a página volta a poder rolar (o "caber numa tela" é para
  desktop/notebook).

### Grade semanal (modo Por Profissional)

- Colunas: segunda a sábado; domingo só aparece se houver consulta do
  profissional naquele domingo da semana exibida.
- Faixa horária (em minutos). Com horário picado, a grade começa e termina
  no minuto exato configurado (ex.: 08:00–19:15); as linhas de hora cheia
  e meia hora ficam nos seus lugares dentro da faixa:
  1. se a clínica definiu `agenda_hora_inicio/fim`, usa essa faixa;
  2. senão, automática: do menor início ao maior fim das consultas da
     semana exibida, arredondado para a hora cheia, com mínimo
     08:00–18:00;
  3. em ambos os casos, se alguma consulta da semana cair fora, a faixa
     estica para incluí-la (só naquela semana).
- Altura: a grade preenche a altura disponível; posições e alturas dos
  blocos e linhas em **porcentagem** da faixa (não mais em px fixos —
  `AGENDA_ALTURA_SLOT`, `AGENDA_HORA_INICIO/FIM` deixam de ser constantes
  e passam a vir da faixa calculada).
- Linhas de hora cheia contínuas, de meia hora tracejadas; rótulos de hora
  na coluna da esquerda.
- Blocos de consulta: fundo claro, borda esquerda grossa (4px) e borda fina
  na cor do status (`STATUS_CONSULTA_INFO`); horário em negrito e nome do
  paciente em uma linha com reticências. "Desmarcada" mantém o riscado.
  Detalhe completo no `title`/clique, como hoje.
- Continuam funcionando, recalculados sobre a faixa nova: clicar em horário
  livre para agendar e arrastar para remarcar. O horário resultante é
  arredondado para múltiplos de 15 min (hoje é meia hora), para combinar
  com horários picados, e fica sempre dentro da faixa exibida.
- Dia de hoje destacado no cabeçalho e na coluna.
- Legenda de status em uma linha, abaixo da grade.

### Modo Geral da Clínica

Mantém Lista/Semana/Mês com o conteúdo atual; ganha a barra única e a lista
lateral. As visões Semana/Mês passam a usar a altura disponível (as colunas
rolam por dentro em vez de esticar a página).

### Testes

Sem testes de JS na suíte; verificação com Playwright no servidor local
(seed): gestor e profissional, semana com e sem horário configurado,
consulta fora da faixa, clicar em horário livre, arrastar consulta, janela
de 1366×768 sem barra de rolagem vertical na página, e largura de celular.

## Entregas

1. **PR 1** — Parte 1. Sem schema: merge automático após testes + CI.
2. **PR 2** — Partes 2 e 3. Tem schema: **perguntar ao usuário antes do
   merge** e avisar do passo manual de migração.

Ao final de cada PR, atualizar o `CLAUDE.md` (seções 5 e 7).
