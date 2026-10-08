# Planos terapêuticos por especialidade — design (parte 3c)

Data: 08/10/2026. Prévia aprovada pelo usuário: artifact "Prévia Planos por
Especialidade" (https://claude.ai/artifact/GFak8abAAuGDLg6MG2uev9, versão 2 —
especialidade como select).

## Objetivo

Uma criança atendida por várias especialidades tem **um plano ativo por
especialidade** ao mesmo tempo (Fono, TO, Psicologia…), cada um com as próprias
missões. Motivo do usuário: as clínicas clientes têm várias especialidades.

## Decisões do usuário (08/10/2026)

| Pergunta | Decisão |
|---|---|
| O que identifica o plano | **A especialidade** — um plano ativo por especialidade dentro da jornada. |
| Como criança e família veem | **Lista única**, cada missão com etiqueta da especialidade; "% da semana", sequência e "Semana Completa" contam todos os planos. |
| Quem edita | **Livre** — qualquer profissional da clínica e o gestor (regra de hoje, `paciente_editavel`). |
| Campo especialidade | **Select** (sem digitar): especialidades da clínica (Configurações) ∪ especialidades dos profissionais ativos da clínica, sem repetir, em ordem alfabética; sem nenhuma, só "Geral". Vem marcada a de quem está criando (se estiver na lista; senão a primeira). |

Fora do escopo: lista de planos encerrados na ficha; filtros por especialidade
em relatórios/indicadores.

## Dados

- `planos_terapeuticos.especialidade TEXT` (até 60 caracteres).
- Migração (`migracoes/migracao_planos_especialidade.sql` + `migrar_planos_especialidade.py`):
  coluna nova; planos existentes recebem a especialidade de quem criou
  (`usuarios.especialidade`), ou **"Geral"** se vazia.
- Regra: **um plano ativo por (jornada, especialidade)**. Criar plano encerra só
  o ativo da mesma especialidade (comparação exata do texto).

## Backend

- `especialidades_disponiveis(organizacao_id) -> list[str]` (novo, em
  `jornada_bp` ou serviço): lista da clínica ∪ especialidades dos profissionais
  ativos não excluídos da clínica; vazia → `["Geral"]`.
- **Bundle da ficha** (`_montar_bundle_jornada`):
  - `planos_ativos`: lista (ordem de criação) de
    `{...plano, objetivos, missoes, progresso_pct, missoes_concluidas, missoes_total}`.
  - `missoes`: **todas** as missões dos planos ativos, cada uma com
    `plano_id`, `plano_titulo` e `plano_especialidade` (a criança e a família
    usam essa lista).
  - `progresso_pct`, `missoes_concluidas`, `missoes_total`: somando todos os planos.
  - `feedbacks`: de missões de qualquer plano ativo.
  - `especialidades_disponiveis` (também no caso sem jornada).
  - `plano_ativo` e `objetivos` (formato antigo) **saem**; todos os
    consumidores são atualizados.
- **Criar plano** (`POST /jornada/jornada/<id>/criar-plano`) e **Iniciar
  jornada** (`POST /jornada/paciente/<id>/iniciar`): `especialidade`
  obrigatória (texto não vazio, até 60) → 400 sem ela. Criar plano encerra só o
  ativo da mesma especialidade.
- **Gamificação** ("Semana Completa"): todas as missões de **todos** os planos
  ativos concluídas (e pelo menos uma missão).
- **Painel do profissional** (`indicadores_bp`, dentro do planejado/baixa
  adesão): soma as missões de todos os planos ativos do paciente.
- **ICT**: adesão usa as missões de todos os planos ativos.
- **PDF**: uma seção por plano ativo (título · especialidade, progresso,
  tabela de missões).

## Front-end

- **Ficha** (`jornada.js`): um cartão por plano (título, etiqueta
  `ICONES_ESPECIALIDADE` + especialidade, progresso, missões, "+ Nova missão"
  daquele plano); abaixo, "+ Novo plano" (para quem pode editar). Sem plano
  ativo, o cartão vazio de hoje com "+ Criar plano terapêutico".
- **Pop-up "Novo plano"**: select Especialidade (opções do bundle), título,
  objetivos. Ao escolher uma especialidade que já tem plano ativo, aviso: "O
  plano atual de <esp> ("<título>") será encerrado e guardado. Os planos das
  outras especialidades continuam."
- **Pop-up "Iniciar jornada"**: select "Especialidade do primeiro plano".
- **Mundo da Criança** (`crianca.js`) e **família** (`responsavel.js`): etiqueta
  pequena na missão — ícone + nome curto na criança, ícone + nome completo na
  família (`etiquetaEspecialidade(esp, curta)` em `util.js`; curto = primeira
  palavra, "Terapia Ocupacional" → "TO", "Fonoaudiologia" → "Fono").

## Testes

Backend: migração (preenche com especialidade do criador / "Geral",
idempotente); dois planos ativos convivem; novo plano encerra só a mesma
especialidade; especialidade obrigatória/limite; bundle (`planos_ativos`,
`missoes` com especialidade, progresso somado, família sem rascunho);
`especialidades_disponiveis`; Semana Completa com dois planos; indicadores e
ICT somando planos; PDF com seções por plano; isolamento entre clínicas.
Front (Node): `etiquetaEspecialidade`. Playwright: ficha com dois planos,
pop-ups com select e aviso, criança e família com etiquetas.

## Produção

Rodar `migracoes/migracao_planos_especialidade.sql` no Supabase (ou
`migrar_planos_especialidade.py`, conferindo `(Postgres)`) **antes** do
`git pull` + `touch tmp/restart.txt`.
