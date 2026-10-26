# Importação do prontuário (etapas 1 e 2) — design

Data: 26/10/2026. Desenho aprovado pelo usuário na prévia "Prévia
Configurações e Prontuário" (artifact, 26/10/2026), parte 3, e em
"pode sim, seguir com as etapas 1 e 2".

## Por quê

Clínicas que chegam ao PandaUp trazem uma base de pacientes de outro sistema.
A importação em lote (`Importar Pacientes`, módulo `importacao_pacientes`)
hoje só traz os dados pessoais e o responsável. O prontuário (o que já se sabe
de cada criança e o histórico de atendimentos) fica para trás, e a equipe
recomeça do zero ou recopia à mão.

**Não dá para saber de qual sistema as clínicas vão exportar** (o usuário não
consegue prever). Por isso a entrada é uma **planilha modelo do PandaUp**
(Excel/CSV): qualquer sistema que exporte para planilha serve, e a clínica
cola os dados nas colunas do modelo. PDF fica para a etapa 3 (fora deste
trabalho).

## O que é o prontuário no PandaUp

- **Ficha Clínica** (`fichas_clinicas`, uma por paciente): diagnóstico,
  alergias, medicamentos em uso, profissionais externos, observações.
- **Diário** (`diarios_terapeuticos`): um registro por atendimento, com data,
  profissional, evolução clínica (texto técnico) e observação interna.

## Metas

1. **Etapa 1 — Ficha Clínica na planilha de pacientes.** Cinco colunas novas,
   todas opcionais, na planilha que já existe: `diagnostico`, `alergias`,
   `medicamentos_em_uso`, `profissionais_externos`, `observacoes_clinicas`.
2. **Paciente que já existe não é duplicado.** Hoje, importar a mesma linha
   duas vezes cria o paciente duas vezes. Passa a reconhecer o paciente da
   clínica com o mesmo **nome e data de nascimento** (comparação sem acento,
   sem diferença de maiúsculas e espaços) e só completar a ficha dele (e o
   vínculo do responsável, que já é idempotente).
3. **Etapa 2 — Histórico de evoluções numa segunda planilha.** Uma linha por
   atendimento antigo, que vira um registro no Diário do paciente.
4. **Prévia antes de gravar**, como na importação de hoje: cada linha com o
   que vai acontecer e os problemas apontados.

## Não metas

- Documentos em PDF / anexos (etapa 3, depois).
- Integrar direto com outro sistema (API).
- Importar jornada, planos, missões, agenda ou financeiro.
- Mudar o formato das colunas que já existem na planilha de pacientes.

## Antimetas (falhar mesmo "funcionando")

- **Dado clínico importado aparecer para a família.** Nada importado é
  compartilhado nem gera aviso à família.
- **Apagar ou sobrescrever o que a clínica já escreveu no PandaUp.**
- **Duplicar** pacientes ou evoluções ao importar a mesma planilha de novo.
- Uma linha ruim derrubar o lote inteiro.
- O ICT (Continuidade Terapêutica) "subir" porque centenas de evoluções antigas
  foram importadas hoje.

## Restrições

- Mesmo acesso de hoje: **só o gestor** (e o admin da plataforma), com o
  módulo `importacao_pacientes` liberado. Sem o módulo, 403 com a mensagem atual.
- Mesmo fluxo de hoje: o navegador lê o arquivo (CSV/XLSX via a biblioteca já
  usada em `views/importacao.js`) e manda as linhas em JSON; o servidor
  **revalida tudo** no confirmar (nunca confia no preview).
- Dados de saúde de crianças (LGPD): cada importação confirmada registra uma
  linha na **Auditoria** (quem, quando, quantos registros, de que tipo).
- Sem RLS nem criptografia de campo (regra 2 do CLAUDE.md).

## Etapa 1 — detalhes

### Colunas novas (planilha de pacientes)

| Coluna | Vai para | Limite |
|---|---|---|
| `diagnostico` | `fichas_clinicas.diagnostico` | 2.000 caracteres |
| `alergias` | `fichas_clinicas.alergias` | 2.000 |
| `medicamentos_em_uso` | `fichas_clinicas.medicamentos_em_uso` | 2.000 |
| `profissionais_externos` | `fichas_clinicas.profissionais_externos` | 2.000 |
| `observacoes_clinicas` | `fichas_clinicas.observacoes_equipe` (só a equipe vê — decisão do usuário em 26/10/2026, depois da revisão) | 5.000 |

Todas opcionais. Texto acima do limite → erro na linha (não corta sozinho).
O modelo CSV para baixar ganha as colunas novas no fim, e os exemplos ganham
valores fictícios.

### Paciente novo × existente

- **Novo** (nenhum paciente da clínica, ativo ou arquivado, com o mesmo nome +
  nascimento normalizados): cria como hoje e grava a ficha se alguma coluna
  clínica veio preenchida (`atualizado_por` = quem importou). Responsável
  continua obrigatório, como hoje.
- **Existente** (exatamente um paciente da clínica casa, **ativo ou
  arquivado** — *decisão do Claude*: arquivado também conta, para nunca criar
  um segundo cadastro da mesma criança; o arquivado continua arquivado e a
  prévia avisa "paciente arquivado"): não cria outro e completa a ficha **só
  nos campos que estão vazios** no PandaUp; campo já preenchido fica como
  está, e a prévia avisa "N campos da ficha já estavam preenchidos e foram
  mantidos".
- **Responsável numa linha de paciente existente** (*decisão do Claude*, por
  segurança de acesso aos dados da criança): as colunas do responsável passam
  a ser **opcionais**. Se vierem com o e-mail de um responsável que já é do
  paciente, nada muda. Se vierem com **outro e-mail**, o sistema **não
  vincula** automaticamente (um erro de digitação daria acesso à criança a
  uma conta errada): a linha recebe o aviso "responsável diferente do
  cadastrado — não vinculado; se for o caso, vincule pela ficha do paciente".
- **Mais de um** paciente da clínica casa com nome + nascimento: erro na
  linha ("há mais de um paciente com esse nome e nascimento").
- Duas linhas do **mesmo lote** com o mesmo paciente: a segunda vira aviso e é
  tratada como existente (a partir da primeira).

A prévia mostra o status por linha (`novo` / `existente`) e quantos campos
clínicos entram.

## Etapa 2 — detalhes

### Planilha de evoluções

| Coluna | Obrigatória | Regra |
|---|---|---|
| `paciente_nome` | sim | junto com o nascimento, acha o paciente |
| `paciente_nascimento` | sim | `AAAA-MM-DD` ou `DD/MM/AAAA` |
| `data_atendimento` | sim | `AAAA-MM-DD` ou `DD/MM/AAAA`; não pode ser no futuro (data de Brasília) |
| `profissional_email` | não | e-mail de alguém da Equipe da clínica |
| `profissional_nome` | não | usado só no texto quando o e-mail não acha ninguém |
| `evolucao` | sim | até 10.000 caracteres |
| `observacao` | não | nota interna da equipe, até 5.000 |

### Como cada linha é resolvida

- **Paciente**: nome + nascimento normalizados (mesma regra da etapa 1), só
  pacientes da clínica (ativos ou arquivados — histórico vale para os dois;
  como a etapa 1 também reconhece arquivados, não surgem cadastros duplos).
  Nenhum → erro "paciente não encontrado"; mais de um → erro "há mais de um".
  Recomendação na tela: importar os pacientes antes das evoluções.
- **Profissional**: `profissional_email` casa (sem diferença de maiúsculas)
  com um usuário da clínica de papel `profissional` ou `gestor` (incluindo
  arquivados; não os excluídos). Não casou ou veio vazio → o registro fica com
  **quem está importando** como autor, e o texto da evolução começa com
  "Profissional no sistema anterior: <nome ou e-mail informado>." (se nenhum
  dos dois veio, sem essa frase). A prévia mostra isso como aviso, não erro.
- **Duplicata**: cada registro importado guarda uma **impressão da linha de
  origem** (coluna `diarios_terapeuticos.importacao_chave` = sha256 de
  paciente_id + data + texto original da evolução, antes de qualquer prefixo).
  Se a mesma impressão já existe, a linha é marcada "já importada" e pulada,
  **mesmo que a equipe tenha editado o registro depois** (*decisão do Claude*:
  a impressão é do original, então editar não abre caminho para duplicar; os
  importados continuam editáveis como qualquer registro). Dentro do mesmo
  lote, linhas idênticas também contam como duplicata.

### Como o registro fica no Diário

- `paciente_id`, `profissional_id` (resolvido acima), `data_atendimento`,
  `evolucao_clinica`, `observacao`; `jornada_id` = jornada ativa do paciente,
  se houver (mesma regra do Diário hoje), senão NULL; `consulta_id` NULL.
- `compartilhado_familia = 0`, `mensagem_familia` NULL, sem pontos/objetivo.
- **Nada de notificação** (nem família nem equipe).
- Marcado como importado: coluna nova `diarios_terapeuticos.origem`
  (`NULL` = criado no PandaUp; `'importacao'` = importado). A tela do Diário
  mostra o selo **"Importado"** e "🔒 Só a equipe vê" nesses registros.
- O ICT **não conta** registros com `origem = 'importacao'`.

### Limites do lote

- Até **1.000 linhas** de evolução por envio (a tela divide arquivos maiores
  em envios de 1.000, um depois do outro, com uma barra de progresso — ou
  pede para dividir o arquivo; ver "Deixado ao construtor").
- Corpo do pedido limitado pelo tamanho dos textos acima.

## Tela (Importar Pacientes)

A página atual ganha duas abas no topo: **"Pacientes e Ficha Clínica"** (a
de hoje, com as colunas novas) e **"Histórico de evoluções"** (nova). Cada
aba tem: baixar o modelo (CSV com BOM, como hoje), escolher o arquivo, prévia
com contadores (prontas / avisos / erros) e a lista linha a linha, e o botão
"Importar N …". Depois de importar, um resumo ("N evoluções importadas, M
puladas") com o link para a lista de pacientes.

Na aba de evoluções, um aviso fixo: "As evoluções importadas ficam só para a
equipe. Nada aparece para as famílias."

## Rotas (backend)

- `POST /api/importacao/pacientes/preview` e `/confirmar`: as de hoje, com as
  colunas da ficha e o status novo/existente.
- `POST /api/importacao/evolucoes/preview` e `/confirmar`: novas, mesmo
  padrão (gestor/admin, módulo, revalida no confirmar, uma linha ruim não
  derruba o lote).
- Confirmar das duas grava uma linha de Auditoria
  (`log_auditoria(org, usuario, "importar", "pacientes"|"evolucoes", None, "<n> registros")`).
- O confirmar das evoluções roda num lote só no banco (`db.em_lote()`), para
  um erro no meio não deixar meio arquivo gravado.

## Banco

- Colunas novas `diarios_terapeuticos.origem TEXT` (NULL padrão) e
  `diarios_terapeuticos.importacao_chave TEXT` (impressão da linha
  importada), com índice em `(paciente_id, importacao_chave)`.
- Migração: `backend/migracoes/migracao_importacao_prontuario.sql` e
  `backend/migrar_importacao_prontuario.py` (mesmo padrão dos outros);
  `schema.sql` e `schema_postgres.sql` atualizados.
- Sem a coluna (deploy antes da migração), a importação de evoluções responde
  com erro claro e o resto do sistema segue normal.

## Testes esperados

- Ficha: colunas gravadas em paciente novo; paciente existente não duplica e
  só completa campos vazios; mais de um homônimo → erro; limite de tamanho.
- Evoluções: acha paciente com acento/maiúsculas diferentes e data
  `DD/MM/AAAA`; data futura → erro; profissional por e-mail; profissional não
  achado → autor = quem importa + frase no texto; duplicata pulada (no banco
  e no lote); `compartilhado_familia = 0`, sem notificação; selo/`origem`;
  responsável não vê a evolução; ICT ignora importados; só gestor; sem módulo
  → 403; Auditoria registrada; erro no meio → nada gravado.
- Front (Node): normalização de nome, conversão de datas e montagem das linhas
  (funções puras).

## Deixado ao construtor

- Como a tela lida com mais de 1.000 evoluções (envios sequenciais com
  progresso é o preferido; pedir para dividir o arquivo é aceitável).
- Onde exatamente o selo "Importado" aparece no Diário (ficha do paciente e
  página do Diário), seguindo o visual atual.
- Nomes de funções e organização do código, seguindo `importacao_bp.py` e
  `views/importacao.js`.
