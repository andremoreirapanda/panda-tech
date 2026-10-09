# Atender / Evoluir a partir da consulta — design (parte 3b)

Data: 08/10/2026. Prévia aprovada: artifact "Prévia Atender e Evoluir"
(https://claude.ai/artifact/QkD353KoSaFEFT7WmeGVvt, versão 2).

## Objetivo

Registrar o atendimento direto da agenda, como na Clínica Ágil: botão
**"▶ Atender"** no pop-up da consulta → página de evolução enxuta (descrição,
observação, status) com uma seção opcional "Para a família" e o **histórico de
todos os atendimentos** do paciente. O registro vira um item do **Diário
Terapêutico** ligado à consulta.

## Decisões do usuário (08/10/2026)

| Pergunta | Decisão |
|---|---|
| Tela | Enxuta + seção recolhida "💛 Para a família" (resto do Diário). |
| Status | Novos: **Falta justificada** e **Desmarcado pelo profissional**. Descrição obrigatória só em **Finalizado**. |
| Onde | **Página própria** com histórico embaixo. |
| Secretária | **Só presença/status e dados da consulta** (profissional, data, horário, observação); sem "Atender", sem Diário; não marca "Finalizado". |
| Sessão N | Atendimentos **finalizados** do paciente na **especialidade do profissional**, contando o atual. |
| Quem atende | **Profissional da consulta e gestor.** |
| Editar depois | **Sim**, autor ou gestor, com auditoria. |
| Evolução atrasada | Faixa amarela quando passou **mais de 1 dia** sem desfecho; **só avisa**. |
| Fora (PRs logo depois) | Repetição avançada (dias da semana, meses, data limite/quantidade; sem limite = 12 meses) e ausências no modo Geral. |

## Dados

- `consultas.status` aceita também `falta_justificada` e
  `desmarcada_profissional` (CHECK refeito; no Postgres:
  `DROP CONSTRAINT IF EXISTS consultas_status_check` + `ADD CONSTRAINT`).
- `diarios_terapeuticos.observacao TEXT` (nota da equipe; a família nunca vê).
- Índice único parcial `idx_diario_por_consulta ON diarios_terapeuticos(consulta_id) WHERE consulta_id IS NOT NULL`
  (um registro por consulta; a migração mantém o mais novo se houver duplicados — na prática não há).
- Migração: `migracoes/migracao_atender.sql` + `migrar_atender.py`.

Status que **liberam o horário** (não contam para encaixe, ausência de
"consultas no período" e exclusão da equipe): `cancelada`,
`desmarcada_profissional`, `falta_justificada`.

## Backend

### Status (`agenda_bp.atualizar_status`)

- Aceita os dois novos. **Secretária não marca `realizada`** (403 "Quem
  finaliza é o profissional, no Atender").
- Reativar (de um status que libera o horário para agendada/confirmada) passa
  pelas checagens de ausência e encaixe, como hoje com `cancelada`.
- `_conflito_consulta`, `consultas_no_periodo` e a checagem de consultas
  futuras na exclusão da equipe ignoram os status que liberam o horário.

### Atendimento (rotas novas em `agenda_bp`)

- `GET /api/agenda/<id>/atendimento` → `{consulta, paciente {id, nome, data_nascimento, avatar_mascote},
  profissional {id, nome, especialidade, tipo_registro, numero_registro}, sessao_numero,
  diario (ou null: evolucao_clinica, observacao, mensagem_familia, pontos_positivos,
  pontos_atencao, objetivo_semana, compartilhado_familia, id), atraso_dias, historico[]}`.
  - Acesso: gestor da clínica do paciente ou o profissional da consulta
    (`consulta.profissional_id == u.id`). Demais → 403; outra clínica → 404/403.
  - `historico`: consultas do paciente com status de desfecho (`realizada`,
    `faltou`, `falta_justificada`, `desmarcada_profissional`), mais recente
    primeiro, até 200: `{consulta_id, data_hora, especialidade, descricao, observacao, profissional_nome, status}`.
  - `sessao_numero`: realizadas do paciente com profissional da mesma
    especialidade e `data_hora` anterior + 1.
  - `atraso_dias`: dias desde a consulta se status ∈ (agendada, confirmada) e
    passou mais de 1 dia (data local de Brasília); senão 0.
- `PUT /api/agenda/<id>/atendimento` body `{status, descricao, observacao, familia: {mensagem, pontos_positivos,
  pontos_atencao, objetivo_semana, compartilhar}}`:
  - `status` ∈ (realizada, faltou, falta_justificada, desmarcada_profissional) → 400 senão.
  - `realizada` exige `descricao` não vazia (400).
  - Atualiza `consultas.status`; cria ou atualiza o registro do Diário da
    consulta (`consulta_id`) quando há descrição, observação ou conteúdo para a
    família (sem nada disso e sem registro existente, não cria). Autor do
    registro novo = quem salvou; `data_atendimento` = data da consulta;
    `paciente_id`, `jornada_id` (ativa) como no Diário.
  - Notifica a família só na **criação** e se compartilhado (como o Diário).
  - Edição posterior: `log_auditoria(..., "editar", "atendimento", consulta_id, ...)`.
  - Mesmas permissões do GET.

### Listagem da agenda

`GET /api/agenda` traz `diario_id` (registro do Diário da consulta, se houver).

## Front-end

- `STATUS_CONSULTA_INFO` ganha `falta_justificada` ("Falta justificada", âmbar)
  e `desmarcada_profissional` ("Desmarcado pelo profissional", roxo); tokens
  `--cor-status-justificada`/`--cor-status-desm-prof`. "Atendido e Evoluído" →
  "Finalizado"; "Não Compareceu e não Avisou" → "Não compareceu".
- Função pura `diasDeAtraso(consulta, hoje)` em `frontend/js/atendimento_util.js`
  (Node test).
- **Pop-up de editar consulta**:
  - Gestor e profissional da consulta: botão "▶ Atender" (ou "✏️ Ver/editar
    evolução" com `diario_id`) → `#/<base>/atender/<id>`.
  - Faixa amarela "⚠️ Esta evolução está em atraso (N dias). Finalize esta
    sessão no 'Atender'." para todos que abrem.
  - Secretária: sem "Atender"; o select de status não oferece "Finalizado".
- **Página Atender** (`frontend/js/views/atendimento.js`, rotas
  `/gestor/atender/:id` e `/profissional/atender/:id`): cabeçalho do paciente
  (avatar, nome, idade, data/horário, etiqueta da especialidade, "Sessão N de
  <especialidade>"), faixa de atraso, evolução (descrição, observação,
  profissional + registro, status em lista de opções), seção recolhida "💛 Para a
  família" (mensagem, pontos positivos/atenção, objetivo, compartilhar —
  anexos ficam no "Novo Diário" da ficha), "Salvar atendimento" → volta à
  agenda; histórico em tabela com rolagem horizontal no celular. "Ficha do
  paciente" leva à ficha.

## Testes

Backend: status novos aceitos/recusados; secretária não finaliza; status que
liberam horário não geram encaixe/consultas no período; GET atendimento
(permissões: profissional da consulta, gestor, outro profissional 403,
secretária 403, outra clínica); sessão N por especialidade; histórico;
atraso; PUT (descrição obrigatória só em realizada; cria diário com
consulta_id e observação; segunda gravação atualiza o mesmo registro e audita;
falta sem texto não cria diário; família notificada só na criação;
compartilhado/família não vê observação). Migração idempotente. Front (Node):
`diasDeAtraso`. Playwright: Atender do pop-up, salvar, histórico, faixa de
atraso, secretária sem Atender.

## Produção

Rodar `migracoes/migracao_atender.sql` no Supabase (ou `migrar_atender.py`,
conferindo `(Postgres)`) **antes** do `git pull` + `touch tmp/restart.txt`.
