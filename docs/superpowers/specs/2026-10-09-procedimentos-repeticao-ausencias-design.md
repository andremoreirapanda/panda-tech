# Procedimentos, repetição avançada e ausências no modo Geral — design

Data: 09/10/2026. Pedido do usuário, a partir da Clínica Ágil (telas
"Cadastros → Procedimentos" e "Novo Agendamento"). Prévia aprovada: artifact
"Prévia Procedimentos" (https://claude.ai/artifact/UadLAhGeLkax8FaLAfoY4W).

São três partes independentes, entregues em **três PRs, nesta ordem**:

- **A. Procedimentos**: cadastro com valor (só gestor) + campo no agendamento. Tem migração.
- **B. Repetição avançada do agendamento**: sem migração.
- **C. Ausências nas visões Lista, Semana e Mês do modo Geral**: sem migração, só front.

---

## A. Procedimentos

### Objetivo

O gestor cadastra os procedimentos da clínica (ex.: "Sessão Divinópolis",
R$ 230,00) e todo agendamento passa a dizer qual procedimento é. Nesta
entrega o valor **só fica guardado**: faturamento e relatórios vêm depois e
vão ler o que fica gravado aqui.

### Decisões do usuário

- O valor só é guardado (sem cobrança automática nem relatório agora).
- O campo é **obrigatório quando a clínica tem pelo menos um procedimento
  ativo**; sem cadastro, o campo nem aparece.
- Mudar o valor de um procedimento **não muda** as consultas já marcadas:
  cada consulta guarda o valor do dia em que foi marcada.
- "Gerar XLS/PDF" da Clínica Ágil fica para a entrega dos relatórios.

### Dados

Tabela nova `procedimentos`:

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | inteiro | chave |
| `organizacao_id` | inteiro | clínica (obrigatória) |
| `codigo` | texto | opcional, até 30 caracteres |
| `nome` | texto | obrigatório, até 120; único na clínica ignorando caixa e espaços nas pontas |
| `valor_centavos` | inteiro | obrigatório, de 0 a 10.000.000 (R$ 100.000,00) |
| `ativo` | inteiro 0/1 | padrão 1 |
| `ordem` | inteiro | posição na lista (0, 1, 2…) |
| `criado_em`, `atualizado_em` | texto | datas |

Índice único `idx_procedimento_nome` em `(organizacao_id, LOWER(TRIM(nome)))`.

Colunas novas em `consultas`:

- `procedimento_id` (referencia `procedimentos.id`, pode ser NULL);
- `procedimento_valor_centavos` (inteiro, pode ser NULL): o valor do
  procedimento **no momento em que a consulta foi marcada** ou em que o
  procedimento dela foi trocado.

Migração: `backend/migracoes/migracao_procedimentos.sql` e
`backend/migrar_procedimentos.py` (cria a tabela, o índice e as duas colunas;
idempotente). Consultas antigas ficam com as duas colunas NULL.

### API

`GET /api/procedimentos` (gestor, profissional, secretária)
- Gestor: todos os procedimentos da clínica, na `ordem`, com `valor_centavos`,
  `ativo` e `em_uso` (quantas consultas usam).
- Profissional e secretária: só os **ativos**, só `id`, `nome` e `codigo`
  (**sem valor**).
- Responsável e admin: 403.

`PUT /api/procedimentos` (só gestor): salva a **lista inteira** de uma vez,
como na tela.
- Corpo: `{"procedimentos": [{"id"?, "codigo", "nome", "valor", "ativo"}, …]}`.
  A posição na lista vira a `ordem`. `valor` aceita número (230 ou 230.5) ou
  texto em reais ("230,00", "1.230,50"); o backend converte para centavos.
- Item sem `id` = novo. Item com `id` = atualiza (só se for da clínica; senão 400).
- Procedimento da clínica que **não veio** na lista = remover:
  - se nunca foi usado em consulta, é apagado;
  - se já foi usado, a gravação inteira é recusada com **409**
    ("'Sessão Equipe' já foi usado em consultas: desative em vez de remover"),
    sem salvar nada.
- Validação de tudo antes de gravar qualquer coisa: nome vazio, nome repetido
  na lista ou na clínica (ignorando caixa e espaços), valor inválido ou
  negativo, código acima de 30 → 400 com a linha e o motivo.
- Mudar o nome não toca nas consultas (elas guardam só o `procedimento_id`;
  o nome é sempre lido do cadastro).
- Grava `log_auditoria` (entidade "procedimentos").

Consultas (`agenda_bp`):
- `POST /api/agenda`, `POST /api/agenda/recorrente` e `PUT /api/agenda/<id>`
  aceitam `procedimento_id`.
- O procedimento precisa ser **da clínica e ativo** (senão 400). Na edição, a
  consulta pode manter o procedimento que já tinha mesmo que ele tenha sido
  desativado depois.
- **Obrigatoriedade**: se a clínica tem pelo menos um procedimento ativo,
  criar consulta (avulsa ou série) sem `procedimento_id` → 400
  "Escolha o procedimento". No `PUT`, a regra só vale se o corpo trouxer a
  chave `procedimento_id` (o pop-up de editar sempre manda); arrastar na
  grade e mudar status não mandam e não exigem nada.
- Ao gravar um procedimento novo ou trocado, `procedimento_valor_centavos`
  recebe o valor atual do cadastro. Manter o mesmo procedimento não mexe no
  valor guardado.
- `GET /api/agenda` passa a trazer `procedimento_id` e `procedimento_nome`
  para todos que já veem a consulta, **exceto o responsável** (a família não
  vê procedimento). `procedimento_valor_centavos` **só vai para o gestor**.

### Tela do gestor: menu "💲 Procedimentos"

- Novo item no menu do gestor, logo antes de "Configurações"
  (`#/gestor/procedimentos`, `views/procedimentos.js`).
- Igual à prévia: aviso "Como funciona"; tabela com arrastar (⋮⋮), Desativar,
  Código, Procedimento, Valor (R$) e Remover; "+ Nova linha" e "Salvar".
- Procedimento já usado mostra "usado em N consultas" e um 🔒 no lugar do
  remover (dica: "Já usado: só dá para desativar"). Linha desativada fica
  riscada com "desativado · não aparece no agendamento".
- Valor digitado no formato brasileiro ("230,00"); ao sair do campo, é
  reformatado. Funções puras de conversão em `frontend/js/procedimentos_util.js`
  (`reaisParaCentavos`, `centavosParaReais`), testadas com Node.
- Sem procedimentos: estado vazio explicando para que servem, com "+ Nova linha".
- Na largura de celular, a tabela rola dentro do próprio cartão.

### Agendamento

- Pop-ups de **agendar** (consulta única e série) e de **editar consulta**:
  select "Procedimento" com os ativos (só nomes, sem valor), logo depois do
  profissional.
- Só aparece se a clínica tiver pelo menos um procedimento ativo; então é
  obrigatório (asterisco e mensagem "Escolha o procedimento").
- No editar, vem selecionado o procedimento da consulta. Se ele foi
  desativado depois, aparece como "(desativado)" e continua selecionável só
  para essa consulta.
- O nome do procedimento aparece no pop-up da consulta; os blocos da grade
  não mudam.

### Quem vê o quê

| | Cadastro | Nome no agendamento | Valor |
|---|---|---|---|
| Gestor | edita | vê e escolhe | vê |
| Profissional | não | vê e escolhe | nunca (nem na API) |
| Secretária | não | vê e escolhe | nunca (nem na API) |
| Responsável | não | não vê | nunca |

### Testes (A)

Backend: permissões do GET/PUT (valor só para o gestor); criar, editar,
reordenar, desativar; nome repetido (caixa/espaços) → 400 sem gravar nada;
remover usado → 409 sem gravar nada; remover não usado apaga; id de outra
clínica → 400; valores "230,00", "1.230,50", 230.5, negativo, texto
inválido; agendar sem procedimento com cadastro → 400, sem cadastro → ok;
procedimento desativado ou de outra clínica → 400; valor guardado não muda
depois de mudar o preço; trocar o procedimento atualiza o valor guardado;
série recorrente leva o procedimento em todas; arrastar/status não exigem;
`GET /api/agenda` sem valor para profissional/secretária e sem procedimento
para responsável. Node: conversão de reais para centavos e volta.

---

## B. Repetição avançada do agendamento

### Objetivo

As mesmas opções do "Repetir Agendamento" da Clínica Ágil, para marcar de
uma vez séries como "toda segunda e quarta, de fevereiro a junho e de agosto
a novembro".

### Opções (pop-up de agendar, ao ligar "Repetir")

1. **Frequência**: Semanal, Quinzenal, Mensal ou "A cada N semanas"
   (N de 1 a 12; Semanal = 1, Quinzenal = 2).
2. **Dias da semana** (Semanal, Quinzenal e "A cada N semanas"): caixas de
   segunda a sábado (+ domingo) e "Todos os dias". Começa marcado o dia da
   data escolhida. **Cada dia marcado tem início e fim próprios**, que começam
   iguais aos do agendamento.
3. **Mensal**: "No mesmo dia do mês" (ex.: todo dia 15; se o mês não tem o
   dia, usa o último dia) ou "No mesmo dia da semana" (ex.: 2ª terça-feira do
   mês; se a data é a 5ª ocorrência, usa a última do mês).
4. **Meses**: caixas de janeiro a dezembro e "Todos os meses" (padrão: todos).
   Datas em meses desmarcados são puladas (ex.: férias de julho).
5. **Até quando**: "Data limite" **ou** "Quantidade de consultas". Sem nenhum
   dos dois, a série vai **até 12 meses depois da primeira data**.

Limites: a série nunca passa de 12 meses depois da primeira data nem de 300
consultas; acima disso, 400 com a explicação.

### Regras

- Datas geradas por uma função pura no backend
  (`recorrencia_service.gerar_datas(regra, inicio)`), com testes próprios.
- A "Quantidade" conta as datas da série antes de tirar as ausências; as
  puladas por ausência continuam aparecendo no aviso "datas puladas", como
  hoje.
- Ausência, encaixe, procedimento e vínculo profissional–paciente seguem as
  regras atuais para cada data.
- O corpo antigo (`frequencia` + `repeticoes`) continua aceito.
- **Prévia antes de salvar**: `POST /api/agenda/recorrente` com
  `"previa": true` devolve as datas (e quais caem em ausência ou já estão
  ocupadas) sem criar nada. O pop-up mostra "Serão criadas N consultas, de
  dd/mm a dd/mm" e, se houver, as datas puladas.
- "Excluir esta e as futuras" continua funcionando (mesmo
  `serie_recorrencia_id` para todas as datas, inclusive dias diferentes).

### Testes (B)

Função de datas: semanal com 2 dias e horários diferentes; quinzenal; a cada
3 semanas; mensal pelo dia do mês (31 → último dia); mensal pelo dia da
semana (2ª terça; 5ª → última); meses desmarcados; data limite; quantidade;
sem fim = 12 meses; limite de 300. Rota: prévia não cria nada; série com
dois dias cria tudo com a mesma série; corpo antigo continua valendo;
ausência pula a data; encaixe pede confirmação.

---

## C. Ausências nas visões Lista, Semana e Mês do modo Geral

Hoje as ausências só aparecem nas grades horárias (Dia e "Por
Profissional").

- **Semana**: em cada dia, antes das consultas, um chip cinza listrado
  "⛔ Camila · 08:00–12:00" ou "⛔ Camila · dia inteiro", com o motivo na dica.
- **Mês**: em cada dia com ausência, uma linha "⛔ N ausente(s)"; clicar no dia
  abre a lista do dia com as ausências no topo.
- **Lista**: cartão "Ausências dos próximos 30 dias" acima de "Próximas
  consultas", uma linha por ocorrência (data, profissional, horário, motivo).
- Respeitam o filtro de profissionais da lista lateral.
- Clicar numa ausência abre o mesmo pop-up de editar ausência da grade
  (`agenda_ausencia_modal.js`), com as mesmas permissões; quem não pode
  editar só vê os dados.
- O carregamento passa a pedir o período da visão (semana; as 6 semanas do
  mês; 30 dias na Lista), dentro do limite de 62 dias da API.
- Responsável continua sem ver ausências.
- Funções puras de agrupamento em `agenda_ausencias.js` (ex.:
  `ausenciasPorDia`), com testes Node.

---

## Fora do escopo

Cobrança automática por procedimento, relatório de faturamento, XLS/PDF de
procedimentos, convênios (a Clínica Ágil tem "Particular" + convênios),
pacotes/tratamentos, "Hora extra" e "Necessidades especiais".

## Passos manuais em produção

- **PR A**: rodar `migracao_procedimentos.sql` no Supabase (ou
  `migrar_procedimentos.py`) antes do `git pull`; depois `touch tmp/restart.txt`.
- **PR B e C**: só `git pull` + `touch tmp/restart.txt`.
