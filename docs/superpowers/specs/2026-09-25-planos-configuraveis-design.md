# Planos configuráveis pelo Admin + módulos extras por clínica

Data: 25/09/2026 · Status: design aprovado pelo usuário em conversa

## Objetivo

O Admin do SaaS cria e edita planos pela tela, escolhendo com caixas de
seleção quais módulos cada plano libera — sem mexer no código. Um plano pode
herdar os módulos de outro ("herança viva"), e planos promocionais podem ter
data de validade. Além do plano, o Admin pode liberar módulos avulsos para
uma clínica específica ("módulos extras").

Vem antes do PR B do Pandoo: o interruptor do Pandoo no painel do Admin vira
a seção "Módulos extras da clínica" desta entrega.

## Decisões do usuário

- Planos criados do zero e editados a qualquer momento pelo Admin.
- **Herança viva** dos módulos: plano com base tem tudo o que a base tem
  (recursivamente) + o que for marcado nele; mudar a base muda os filhos na
  hora. O filho só acrescenta (não remove módulo herdado).
- **Módulos extras por clínica**: o Admin libera qualquer módulo opcional para
  uma clínica, fora do plano dela.
- **Validade** para promoções: depois da data, o plano não pode mais ser
  atribuído; clínicas que já estão nele continuam normalmente.
- **Pacientes ilimitados** em todos os planos: o limite de pacientes sai do
  formulário e deixa de ser aplicado. Limites de profissionais e secretárias
  continuam.
- Um módulo **novo** continua exigindo código (é funcionalidade nova); o que
  deixa de exigir código é decidir em quais planos ele entra. Módulos novos
  aparecem automaticamente na tela de planos, desmarcados.

## 1. Dados

- Tabela nova `planos_modulos (plano_id → planos.id, modulo_codigo TEXT,
  UNIQUE(plano_id, modulo_codigo))` — módulos **marcados no próprio plano**
  (sem os herdados).
- `planos` ganha:
  - `plano_base_id INTEGER NULL REFERENCES planos(id)` — base da herança;
  - `disponivel_ate TEXT NULL` — `YYYY-MM-DD`; depois disso não pode ser
    atribuído.
- `planos.limite_pacientes` fica no banco (compatibilidade), mas a migração
  zera para NULL em todos os planos e nada mais o lê para bloquear.
- `modulos_clinica.liberado_admin` (criada no Pandoo PR A) passa a significar
  "extra liberado pelo Admin" para **qualquer** módulo opcional.

Migração (`backend/migracoes/migracao_planos_configuraveis.sql` +
`backend/migrar_planos_configuraveis.py`, idempotentes):
- cria `planos_modulos`, colunas novas;
- preenche `planos_modulos` a partir do que o código tem hoje, **mantendo o
  resultado final idêntico**: `pro` recebe `financeiro, ia,
  analytics_avancado, integracoes, importacao_pacientes`; `enterprise` herda
  de `pro` (`plano_base_id`) e recebe `white_label`; `starter` nenhum. Só
  insere se o plano ainda não tiver linhas (não sobrescreve ajustes do Admin
  numa segunda execução);
- `UPDATE planos SET limite_pacientes = NULL`.

`seed.py`/`seed_producao.py` passam a gravar o mesmo em `planos_modulos` e
`plano_base_id` (e `limite_pacientes` NULL).

## 2. Regras (backend)

`modulos_service.py`:
- `MODULOS_POR_PLANO` sai do código; `modulos_do_plano(codigo_plano)` passa a
  ler do banco: módulos do plano + módulos da cadeia de bases (recursivo, com
  proteção contra ciclo e profundidade máxima 10).
- `MODULOS_SO_ADMIN` sai: o Pandoo vira módulo opcional comum.
- `modulos_habilitados_clinica(org, plano)` = (módulos do plano, respeitando o
  `habilitado` do gestor) ∪ (extras com `liberado_admin = 1`). Extras não
  podem ser desligados pelo gestor.
- `definir_liberacao_admin` passa a aceitar qualquer código de
  `MODULOS_OPCIONAIS`.

Admin (`admin_bp.py`):
- `GET /admin/planos` → além dos campos atuais: `plano_base_id`,
  `plano_base_nome`, `disponivel_ate`, `promocao_encerrada` (bool),
  `modulos_proprios` (lista), `modulos_herdados` (lista), `modulos_efetivos`
  (lista), `total_clinicas`. Admin vê também os inativos
  (`?incluir_inativos=1`); o gestor continua vendo só os ativos.
- `POST /admin/planos` (novo) — cria plano: `nome` (obrigatório, único),
  `preco_mensal_centavos`, `limite_profissionais`, `limite_secretarias`,
  `cor`, `recursos`, `plano_base_id`, `disponivel_ate`, `modulos` (lista de
  códigos próprios). `codigo` gerado a partir do nome (slug, sem acento,
  único — sufixo `-2`, `-3`… se repetir). `ordem` = maior + 1.
- `PUT /admin/planos/<codigo>` — passa a aceitar também `plano_base_id`,
  `disponivel_ate`, `modulos`, `ativo`; ignora `limite_pacientes`.
  Validações:
  - base não pode ser o próprio plano nem um descendente (ciclo) → 400;
  - códigos de módulo desconhecidos → 400;
  - `disponivel_ate` em `YYYY-MM-DD` ou vazio;
  - desativar (`ativo=false`) um plano que é base de outro plano ativo → 409
    ("troque a base dos planos X, Y antes");
  - desativar plano com clínicas nele é permitido (elas continuam; não pode
    mais ser atribuído).
- `_plano_valido(codigo)` (usado ao criar clínica e ao trocar o plano) passa a
  exigir também `disponivel_ate` vazio ou ≥ hoje.
- `GET /admin/clinicas` (e `/monitoramento`): `modulos_so_admin` sai; entra
  `modulos: {do_plano: [...], extras: [...], opcionais: [{codigo, nome,
  icone}]}` para a tela montar as caixas. `limite_pacientes` e
  `uso_pacientes_pct` saem (sempre ilimitado).
- `PUT /admin/clinicas/<id>/modulos/<codigo>` (do Pandoo PR A) passa a aceitar
  qualquer módulo opcional; módulo que já vem do plano → 400 ("já incluído no
  plano").

Limites:
- `pessoas_bp` (cadastro de paciente) e `importacao_bp` (importação em lote)
  deixam de checar limite de pacientes. Profissionais e secretárias seguem
  como hoje.

Gestor (`modulos_bp.py`): `GET /modulos` lista também `origem`: `"plano"`,
`"extra"` ou `null` (não liberado); o toggle continua só para os do plano.

Cobrança: nenhuma mudança (usa `planos.preco_mensal_centavos` da clínica).

## 3. Tela

Admin → **Planos** (tela existente em `admin.js`, ~l.344):
- lista de cartões: nome, cor, preço, "herda de X", validade ("Promoção até
  dd/mm" / "Promoção encerrada"), inativo, nº de clínicas, módulos efetivos
  como selos;
- botão "+ Novo plano" e "Editar" abrem o mesmo formulário:
  - nome, preço (R$), limites de profissionais e secretárias (vazio =
    ilimitado; secretárias aceita 0), cor, recursos (bullets), ativo;
  - "Começar a partir do plano…" (select, opcional) = plano base;
  - **Módulos** — uma caixa por módulo opcional (lista vinda do backend):
    herdados marcados e travados com "vem do plano X"; próprios editáveis;
  - "Disponível até" (date, opcional) com dica "para promoções".
- sem "limite de pacientes" em lugar nenhum.

Admin → detalhe da clínica (`abrirModalDetalheClinica`):
- seção **"Módulos da clínica"**: para cada módulo opcional, uma linha com
  estado: "✓ do plano" (travado), caixa "Extra" (liga/desliga via
  `PUT /admin/clinicas/<id>/modulos/<codigo>`), ou nada.
- sai o "uso de pacientes (x de y)".
- ao trocar o plano da clínica, o select só mostra planos ativos e dentro da
  validade.

Gestor → **Módulos** (`modulos.js`): módulo `origem = "extra"` aparece com o
selo "Liberado pela Panda Tech" (sem toggle); fora do plano e sem extra: como
hoje ("Fora do plano"), mas sem a frase fixa "a partir do plano Pro" (vira
"Fale com a Panda Tech").

## 4. Testes

Backend (pytest): herança (filho herda, mudança na base propaga, cadeia de 3,
ciclo recusado), criar plano (slug único, módulos inválidos), validade (plano
vencido não é atribuível, clínica que já está nele mantém módulos), desativar
base com filhos ativos → 409, extras (qualquer módulo, só Admin, gestor não
desliga extra, módulo do plano não vira extra), migração (resultado idêntico
ao `MODULOS_POR_PLANO` antigo; idempotente), pacientes ilimitados (cadastro e
importação acima do antigo limite passam), gestor continua sem acesso às
rotas de Admin. Testes existentes que dependiam de `MODULOS_POR_PLANO` ou do
limite de pacientes são ajustados à regra nova.

Front: Playwright — criar plano a partir de outro, ver herdados travados,
mudar a base e ver o filho mudar, promoção vencida some do select da clínica,
liberar extra na clínica e ver o menu do gestor mudar, tela Módulos do
gestor.

## 5. Entrega

Um PR, com migração (Supabase **antes** do `git pull`) e mexendo em planos
→ **perguntar ao usuário antes do merge**. Depois, o plano do Pandoo PR B
troca a Tarefa 9 (interruptor) por usar a seção "Módulos da clínica".
