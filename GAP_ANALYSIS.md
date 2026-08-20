# 🔍 Gap Analysis — Panda Tech

Levantamento do que falta ou está raso na implementação atual, organizado por
prioridade. Baseado em releitura dos 9 documentos originais + 20 documentos de
produto/arquitetura + 10 documentos operacionais mais recentes (MVP Scope,
Product Backlog & Epics, MVP Core/User Stories, Clinic Onboarding, UX/UI Flows,
Database Schema, API/Backend Contract, Auth/Security, Core User Journeys) +
uso real da demo.

---

## 🆕 Agenda — visão "Por Profissional" com grade horária + confirmação (entregue)

- **Duas visões agora**: "🏥 Geral da Clínica" (a que já existia: Lista,
  Semana, Mês) e a nova "👤 Por Profissional" — inspirada na referência
  enviada, com lista de profissionais na lateral e grade horária semanal
  (7h às 20h) mostrando os horários de cada um em blocos coloridos
  posicionados pelo horário real. Disponível pra Gestor e Profissional
- **Clique num horário livre** abre o modal de nova consulta já com
  profissional, data e hora preenchidos
- **Arrastar um bloco existente pra outro dia/horário** remarca a consulta
  de verdade (arredonda pra múltiplos de 15 min), sem precisar abrir modal
  nenhum — testado e confirmado que a mudança persiste e aparece
  refletida também na visão Geral
- **"Confirmar agendamento"** — resolvia o gap que você apontou: agora tem
  um botão explícito no modal de editar (e um ícone 📌 na lista) pra
  passar uma consulta de "agendada" pra "confirmada", já que o backend
  sempre aceitou esse status mas não existia como marcar
- Escrita continua respeitando a mesma regra de permissão já existente
  (Gestor sempre; Profissional só na própria agenda, a menos que tenha a
  permissão de "gerenciar qualquer paciente" ligada) — a visualização
  desta grade é aberta pra todo mundo, só a edição é restrita

Também investigamos a fundo um relato de bug (permissão expandida não
aparecendo na agenda do profissional) — não foi possível reproduzir após
testes extensivos; a causa mais provável era a tela já estar aberta antes
da permissão ser salva. Mesmo assim, aplicamos uma correção defensiva
que já buscava a sessão sempre atualizada.

Testado nos dois lados, bateria completa de regressão sem erros — inclusive
o fluxo completo de arrastar-e-soltar e confirmar, validados de ponta a
ponta com a mudança persistindo no backend.


## 🆕 Investigação da Agenda + reposicionamento do badge de papel (entregue)

- **Investigação da agenda com permissão expandida**: testei extensivamente
  (via API direta, e via navegador simulando o cenário exato — permissão
  concedida enquanto a sessão do profissional já estava ativa, com e sem
  F5) e **não consegui reproduzir o problema relatado**: em todos os
  testes, a lista de consultas retornada já reflete corretamente a
  permissão assim que a tela da Agenda é (re)carregada, porque o backend
  sempre recalcula a permissão a partir do banco a cada requisição (nunca
  confia em dado antigo do token). Ainda assim, apliquei uma correção
  defensiva: a Agenda agora também rebusca `/auth/me` toda vez que a tela
  é aberta, garantindo que a sessão local nunca fique presa com um valor
  de permissão desatualizado, mesmo em cenários extremos de sessão de
  longa duração
- **Badge de papel reposicionado**: "Gestor(a)" / "Profissional" /
  "Administrador da Plataforma" agora aparece logo abaixo do nome/logo da
  clínica no topo da barra lateral, em vez de só no rodapé — o rodapé
  ficou mais limpo (nome + especialidade, sem repetir o papel)

Testado nos 4 perfis, nos dois lados, bateria completa de regressão sem
erros.


## 🆕 Relatório exportável em PDF (entregue) — 1º item da nova fila

- **Projeto real**: novo endpoint `GET /jornada/paciente/<id>/relatorio-pdf`,
  gerado com `reportlab` (Python) — objetivo, plano ativo com tabela de
  missões, resumo do diário, gamificação. Baixa de verdade pelo navegador
  (testei com o mecanismo de download real do Playwright)
- **Proteção de dados replicada no PDF**: a evolução clínica só entra no
  documento quando quem baixa é Gestor ou Profissional — testei os dois
  casos e confirmei que o PDF do responsável não traz esse campo, igual ao
  resto do app
- **Bug real corrigido no caminho**: os emojis nos títulos de seção
  apareciam como quadrados pretos no PDF (a fonte padrão do reportlab não
  tem esses glifos) — removidos, ficou mais limpo e adequado a um
  documento formal
- **Demo interativa**: como não tem backend real, implementei geração do
  mesmo relatório no navegador com jsPDF (carregado via CDN, precisa de
  internet — igual as fontes do Google Fonts que a demo já usa). Meu
  ambiente de teste não consegue baixar esse CDN (rede restrita), então
  não dá pra confirmar visualmente aqui — mas testei a lógica de geração
  isoladamente com um mock da API do jsPDF (3 cenários: paciente com
  jornada, sem jornada, e como responsável) e todos passaram sem erro. O
  caminho de falha também foi testado e mostra uma mensagem clara ao
  usuário (não trava nem falha silenciosamente) caso o CDN não carregue
  por algum motivo no navegador de quem for usar

Bateria completa de regressão sem erros nos dois lados.


## 🔍 Revisão geral #2 — 3 bugs de overflow encontrados e corrigidos

Rodei uma bateria de **77 telas** (todos os perfis, várias larguras de
tela incluindo 320px — a mais estreita que existe em celular de verdade) e
os principais fluxos interativos (missão diária, cadastro de paciente
com equipe, CRUD de consulta, missão semanal). Resultado: **3 bugs reais
de overflow horizontal** encontrados, todos com causa raiz identificada e
corrigida:

1. **Lista de pacientes em mobile**: a linha (avatar + nome + badges +
   botão) não tinha `flex-wrap`, estourando a tela em 375px — corrigido
   adicionando `flex-wrap:wrap` na classe `.pessoa-linha` (usada em vários
   lugares do app, corrige todos de uma vez)
2. **Menu inferior do Responsável**: com 6 itens agora (desde que o Mural
   foi adicionado), o padding padrão não cabia em telas de 320px —
   adicionado um ajuste responsivo específico pra telas bem pequenas
3. **Barra de enviar mensagem do chat**: o `<input>` de texto não encolhia
   corretamente dentro do flexbox em telas estreitas (comportamento padrão
   de inputs em flexbox — não encolhem abaixo do próprio conteúdo sem
   `min-width:0` explícito), empurrando o botão de enviar pra fora da
   tela — corrigido

Depois das correções, rodei a bateria de novo: **77 telas, zero erros**,
mais os 4 fluxos interativos completos (missão diária, cadastro de
paciente, CRUD de consulta, missão semanal) — todos funcionando.


## 🆕 Lote de 10 ajustes de UX + disponibilidade de agenda (entregue)

1. **Lista de pacientes** trocada de cards por lista (avatar, nome, idade,
   status, botão ver/editar) com campo de busca por nome no topo
2. **Header duplicado removido** da tela do paciente (o card de identidade
   já mostra avatar+nome, não precisa repetir acima)
3. **Bug real corrigido**: abrir o detalhe de um registro do Diário a
   partir do histórico empilhava 2 modais com o mesmo `id`, fazendo o
   botão "Fechar" nunca funcionar direito no de cima — corrigido fechando
   o modal de trás antes de abrir o de detalhe, e escopando a busca do
   botão ao próprio modal (mais robusto contra o mesmo tipo de bug em
   qualquer lugar). Também adicionei o botão de **editar o registro**
   (só pro autor original ou o Gestor)
4. **Membros da equipe no dashboard do Gestor agora são clicáveis** —
   abre direto o modal de edição daquele profissional
5. **Consultas agora podem ser editadas de verdade** (não só cancelar/criar
   de novo) — troca de data, hora e **profissional**, com endpoint novo
   `PUT /agenda/<id>`
6. **Chips da visão semanal da Agenda agora são clicáveis**, abrindo o
   mesmo modal de edição
7. **Disponibilidade de agenda por profissional** (feature nova): modal
   com os 7 dias da semana, checkbox de "Ausente" e horário de início/fim
   — Domingo e Sábado já nascem marcados como ausentes por padrão. Gestor
   edita de qualquer profissional da clínica; o profissional edita a
   própria
8. **Aviso de indisponibilidade** ao agendar ou editar uma consulta —
   avisa se o profissional escolhido costuma estar ausente naquele dia da
   semana, sem bloquear (só alerta, a decisão final é de quem agenda)
9. **Agenda do Responsável simplificada** — só mostra a visão em Lista
   (Semana/Mês ficam ocultos, adequado ao uso no celular)

Mais uma vez, o mesmo bug de digitação recorrente (parâmetro trocado que
apaga conteúdo em vez de inserir) apareceu 3 vezes durante essa
implementação — todas detectadas por erro real ao testar e corrigidas
antes de prosseguir.

Testado nos dois lados, bateria completa de regressão sem erros.


## 🆕 Missões diárias vs semanais (entregue) — fecha o Grupo 3

- **Novo campo `missoes.tipo`** ('diaria' padrão, ou 'semanal') — escolhido
  no momento de criar a missão, travado depois (não dá pra trocar o tipo de
  uma missão já criada)
- **Diária**: continua exatamente como sempre foi — um botão, conclui de
  vez
- **Semanal**: precisa de **1 check por dia real**, 7 dias, pra fechar —
  implementado com uma tabela dedicada (`missao_dias_concluidos`) que só
  aceita a **data do servidor** no momento do clique (nunca a data que o
  cliente mandar), então não tem como "adiantar" ou marcar dois dias de
  uma vez só. Tentar marcar o mesmo dia duas vezes é bloqueado
- Na tela da criança, a missão semanal mostra 7 quadradinhos de progresso
  e um botão "Marquei hoje! 🎉" que só aparece se ainda não marcou hoje —
  depois de marcar, vira um aviso "Volte amanhã" até o dia seguinte
- Ao completar os 7 dias, dispara a mesma recompensa de gamificação
  (XP, sequência, notificação pros responsáveis) que a missão diária
  sempre teve
- Card do profissional/gestor mostra "🗓️ Semanal · X/7 dias" com o
  progresso em tempo real

**3 recorrências do mesmo bug de digitação** (parâmetro trocado que apaga
conteúdo sem inserir o novo) aconteceram durante essa implementação — todas
detectadas por erro 500 real ao testar ("did not return a valid response")
e corrigidas antes de prosseguir, sem deixar nada quebrado na entrega
final.

Testado nos dois lados — inclusive simulando os 7 dias no banco pra
confirmar o fechamento automático da missão, já que não dá pra esperar
dias reais passarem num teste. Bateria completa de regressão sem erros,
confirmando que missões diárias continuam funcionando normalmente.


## 🆕 Agendamento recorrente (entregue)

- Modal de "Agendar consulta" ganhou a opção "🔁 Repetir esta consulta" —
  escolhe frequência (semanal/quinzenal/mensal) e quantas vezes (2 a 52)
- Novo endpoint `POST /agenda/recorrente` gera todas as ocorrências de uma
  vez, todas ligadas por um `serie_recorrencia_id` (usa o id da primeira
  consulta da série)
- **Recorrência mensal trata a virada de mês de verdade**: agendar dia 31
  de janeiro gera 28 de fevereiro (não existe 31/fev) e depois volta pro
  dia 31 em março — testei esse caso específico
- Consultas de uma série aparecem com o ícone 🔁 na visão de lista
- Excluir uma consulta de série pergunta se é só aquela ou "esta e todas as
  futuras" (as passadas nunca são tocadas, viram histórico normalmente)

Testado nos dois lados (incluindo o caso de virada de mês no backend fake),
bateria completa de regressão sem erros.


## 🆕 Visualização ampla + edição restrita para profissionais (entregue)

- **`paciente_acessivel()`** (backend) agora significa "pode **ver**":
  qualquer profissional da clínica vê qualquer paciente, não só os que
  atende
- **`paciente_editavel()`** (nova função): "pode **editar**" — Gestor
  sempre; Profissional só se estiver de fato na equipe daquele paciente
- Frontend reflete isso em toda a tela do paciente: badge "👁️ Somente
  visualização" na lista, aviso na página, e todos os botões de edição
  (editar identidade, iniciar jornada, novo plano/missão,
  editar/excluir/publicar missão, novo diário, vincular
  responsável/profissional, editar ficha clínica) somem quando o
  profissional não tem permissão — só continua vendo tudo

**Encontrei e corrigi 9 gaps de segurança reais** enquanto implementava
isso: vários endpoints de escrita (criar jornada/plano/missão,
editar/excluir/publicar missão, marco terapêutico, vincular responsável)
não tinham **nenhuma** checagem de posse do paciente antes — só verificavam
o papel do usuário, então qualquer profissional de qualquer paciente podia
mexer na jornada de qualquer outro. Também apareceu um bug real de
comparação (`0 !== false` em JavaScript) que fazia o badge de visualização
não aparecer mesmo com os dados corretos vindo do backend.

Testado nos dois lados (incluindo o backend fake da demo, replicando as
mesmas regras) — confirmando que Gestor continua editando qualquer
paciente, Profissional continua editando quem atende, e agora também
**vê** (sem editar) o resto da clínica. Bateria completa de regressão sem
erros.


## 🆕 Seleção de profissionais no cadastro de paciente (entregue)

- **Gestor cadastrando**: modal ganhou um seletor com checkboxes de todos os
  profissionais da clínica (opcional) — o primeiro marcado vira o
  "principal" automaticamente, os outros entram como parte da equipe
- **Profissional cadastrando**: sem seletor (não faz sentido escolher
  outros pra si) — ele mesmo já é vinculado automaticamente como principal,
  e o paciente já aparece na lista dele assim que o modal fecha (esse
  comportamento, na verdade, já existia — a listagem já filtrava
  corretamente por vínculo; só faltava confirmar que funcionava de ponta a
  ponta, o que testei e confirmei)

Testado nos dois papéis, nos dois lados, bateria completa de regressão sem
erros.


## 🆕 Reestruturação da tela do Paciente — identidade sempre visível (entregue)

Corrigiu 2 bugs raiz reais encontrados ao investigar por que os cards
"Responsáveis" e "Equipe" pareciam não mostrar dados mesmo depois de
cadastrados:

1. **Bug de dados**: o endpoint que alimenta a tela do paciente nunca
   populava `responsaveis`/`profissionais` — mesmo existindo de verdade no
   banco, a tela sempre recebia array vazio
2. **Bug de estrutura**: quando o paciente ainda não tinha jornada
   iniciada, a tela inteira virava uma tela vazia — nenhum dado do
   paciente, nenhum card, nada

Reestruturei pra separar o que depende da jornada do que não depende:

- **Cabeçalho de identidade sempre visível** — foto/mascote, nome, idade
  no formato "6 anos e 5 meses", gênero — com botão de editar (✏️),
  disponível pra Gestor e Profissional, endpoint `PUT /pessoas/pacientes/<id>`
- **Cards Responsáveis e Equipe sempre visíveis**, com ou sem jornada
  ativa — agora mostram de verdade quem já foi vinculado
- **Equipe ganhou "+ Vincular profissional"** — endpoint novo
  `POST /pessoas/pacientes/<id>/vincular-profissional`, com modal que só
  lista quem ainda não atende o paciente
- Só o conteúdo específico da jornada (objetivo, plano, missões, diário,
  gamificação, ICT) continua condicional a ter uma jornada iniciada

Testado abrindo múltiplos pacientes diferentes (com e sem jornada) em
todos os perfis, nos dois lados, bateria completa de regressão sem erros.

---

## 🆕 Responsável obrigatório no cadastro de paciente (entregue)

Nome e e-mail do responsável agora são **obrigatórios** ao cadastrar um
paciente (telefone continua opcional) — antes dava pra cadastrar o
paciente sem vincular ninguém, "pra fazer depois". Também melhorei o
tratamento de erro: se o paciente for criado mas a vinculação do
responsável falhar por algum motivo (ex: e-mail já em uso por outro
responsável em conflito), o usuário é avisado claramente que precisa
vincular depois pela Jornada, em vez de falhar silenciosamente.

Testado nos dois lados, bateria completa de regressão sem erros.


## 🆕 Grupo 1 de insights (rápidos) — Mural, Diário, Registro profissional (entregue)

- **Mural agora aparece pro Responsável** (rota + item de menu mobile) — o
  backend já não tinha restrição, só faltava a tela existir do lado dele
- **Seletor de público no Mural**: ao publicar um aviso, dá pra escolher
  "Todos", "Só equipe" ou "Só famílias" — o backend filtra corretamente
  por papel de quem consulta
- **Bug real de vazamento de dado sensível corrigido**: a "Evolução
  clínica" (linguagem técnica) estava sendo mostrada pro responsável em 3
  pontos — o preview da tela inicial dele mostrava ela truncada como
  resumo (era o campo errado!), a listagem de diários, e o bundle da
  jornada. Corrigido nos 3: a família nunca mais vê esse campo, mesmo em
  registros marcados como compartilhados — só a "Mensagem para a família"
  (que é o campo certo pra isso) chega até ela
- **Diário Terapêutico reordenado**: "Mensagem para a família" agora fica
  logo abaixo de "Evolução clínica", como pedido
- **Cadastro de profissional ganhou "Tipo de Registro" (dropdown: CRFa,
  CREFITO, CRP, CRN, CRE, Outro) + "Número de Registro"**
- **Mascote no cadastro de paciente**: confirmado que já era opcional (sem
  `required`, com fallback no backend) — nome/nascimento continuam
  obrigatórios

Testado nos dois lados, bateria completa de regressão sem erros.


## 🆕 Calendário em grade + encaixe pronto pra Google Calendar (entregue)

- **Agenda ganhou 3 visões**: Lista (a que já existia), **Semana** (7
  colunas, uma por dia, com o dia atual destacado e navegação ← →) e
  **Mês** (grade clássica 6×7, com até 2 consultas por célula e
  "+N mais" clicável, abrindo a lista completa daquele dia num modal).
  Responsivo — testado em 375px sem overflow, a semana vira scroll
  horizontal e o mês vira indicador de bolinha nos dias com consulta
- **Encaixe pronto pra Google Calendar real** (não é a integração de
  verdade — isso exige OAuth2 e acesso à internet externa, que este
  ambiente de execução não tem): criei `calendar_sync_service.py` com uma
  função única (`sincronizar_consulta_google`) chamada sempre que uma
  consulta é criada/atualizada/cancelada. Hoje ela só simula (marca um
  `google_event_id` fake se a integração estiver ligada); o dia que alguém
  continuar esse projeto num ambiente com internet (Claude Code ou Cowork,
  por exemplo), só precisa trocar o corpo dessa função pelas chamadas reais
  à API do Google — nenhum outro arquivo do sistema precisa mudar, já que
  `agenda_bp.py` só conhece essa única função
- Campos novos no schema (`consultas.google_event_id`,
  `google_sincronizado_em`) já preparados para isso

Testado nos dois lados (o "encaixe" replicado também no backend fake da
demo, pra manter a paridade de comportamento), bateria completa de
regressão sem erros.


## 🆕 Lote de acertos visuais + bug real de contraste encontrado (entregue)

Verificação ponto a ponto de mais uma leva de feedback com prints, todos
confirmados no código antes de mexer:

- **Especialidade do profissional**: removi o fallback silencioso pra lista
  fixa (que fazia o dropdown mostrar opções genéricas em vez do que a
  clínica realmente configurou). O campo virou texto livre com autocomplete
  das especialidades já cadastradas — mesmo em Equipe quanto no wizard de
  onboarding
- **Logo sem corte**: `object-fit:cover` forçando quadrado foi trocado por
  `contain`, preservando a proporção real da imagem enviada
- **Logo empilhado acima do nome** na sidebar (quando há imagem real —
  com só emoji continua compacto), com recomendação de tamanho ideal no
  texto de ajuda (retangular, até 240×80px, PNG transparente)
- **Ícones do chat trocados por SVG** (clipe de papel + seta), abandonando
  emoji pra não depender da fonte de emoji do sistema operacional de quem
  usa
- **Bug real de contraste encontrado no caminho**: o botão de enviar do
  chat estava com o ícone branco sobre fundo quase branco — praticamente
  invisível. Causa: conflito de especificidade CSS entre `.botao-primario`
  e `.botao-icone` (a segunda, declarada depois no arquivo, vencia o fundo
  colorido da primeira). Corrigido com uma regra combinada mais específica
- **"Meu Perfil" removido do menu do Gestor**: os campos (foto, nome,
  telefone) viraram um card "📇 Contato (decisor na clínica)" dentro da
  própria tela de Configurações — não precisa mais trocar de tela pra
  editar a própria identidade
- **Especialidades como tags livres também nos 2 modais do Admin** (criar
  clínica e editar clínica) — antes só a tela de Configurações do gestor
  tinha esse padrão; criei um helper reutilizável pra não duplicar a lógica
  3 vezes
- **Verificação de segurança do módulo Financeiro**: confirmei que uma
  clínica no plano Starter (que não inclui Financeiro) é bloqueada tanto
  na tela (toggle desabilitado, badge "Fora do plano") quanto no backend
  (403 em qualquer chamada direta à API, testado nos dois lados)

Testado nos dois lados, bateria completa de regressão sem erros.


## 🔍 Revisão geral (checkpoint) — o que falta de verdade

Fiz uma passada completa por todo o app antes de escrever esta seção: bateria
de testes cobrindo **55 combinações de tela/perfil/viewport** (Gestor,
Profissional, Admin, Responsável — desktop e mobile) mais os principais
fluxos interativos (concluir missão → celebração, criar diário, cadastrar
paciente com convite, jornada, agenda, módulos) — **zero erros encontrados**.
Também usei essa passada para achar tabelas antigas deste documento que já
estavam desatualizadas (listavam como "pendente" coisas que já entreguei em
rodadas posteriores, como upload real na Biblioteca, onboarding guiado, e
anexos na Evolução Clínica) — o resumo abaixo é o retrato fiel de agora.

### O que ainda não foi construído (verificado nesta revisão)

| Item | Tamanho | Nota |
|---|---|---|
| **Papel "Criança" com sessão própria (PIN/login)** | Médio | Hoje a criança só existe *dentro* da sessão do responsável, via troca de modo — não há conta/login separado |
| **Camada "Usuário" das Feature Flags** | Pequeno | Backend já suporta override de módulo por responsável específico; falta a tela pra usar isso |
| **Assistente de IA — Tool Layer completo** | Médio-Grande | Hoje existe só a heurística de "sugerir missão" por palavra-chave. O padrão arquitetural completo (Context Engine → Permission Engine → Tool Layer) não foi montado |
| **Seletor de Paciente com busca/favoritos/recentes** | Pequeno-Médio | Hoje é uma grade estática, sem busca instantânea |
| **Dashboard "Ecosystem Analytics" (funil)** | Pequeno-Médio | Os eventos já são registrados; falta a tela que monta o funil "criada → notificada → iniciada → concluída" |
| **Calendário visual em grade** | Médio | Agenda hoje é lista cronológica, não visão de semana/mês |
| **Tela de comparação de exercícios lado a lado** | Pequeno | Só existe visão em grade na Biblioteca |
| **Relatório exportável em PDF** | Pequeno | Já tenho a skill de PDF disponível pra isso quando for priorizado |
| **Mascote customizável (roupas/acessórios)** | Médio | Hoje evolui só automaticamente por estágio |
| **Compartilhamento social de conquistas** | Pequeno | "Cartão" pronto pra WhatsApp/Instagram |
| **Timeline de Alta Terapêutica** | Médio | Não existe fluxo de encerramento de tratamento hoje |
| **Push notification real / WhatsApp** | Alto | Depende de conta comercial (WhatsApp Business API) |
| **Integrações reais (OAuth/webhook)** | Alto | Central de Integrações hoje é só o toggle liga/desliga — a integração de fato com Google Calendar/ERP/pagamento não existe |
| **IA generativa real (LLM)** | Alto | Requer acesso a um provedor de IA externo, indisponível neste ambiente |
| **Soft delete consistente** | Baixo risco | `mensagens`/`cobranças`/`consultas` ainda fazem exclusão física, diferente do padrão usado no resto do app |
| **MFA, UUID em vez de ID incremental** | Adiado conscientemente | Débito técnico sinalizado, não erro — baixo valor pra uma demo local |
| **Testes automatizados em CI, i18n, modo escuro, auditoria WCAG completa** | Não iniciado | Fora do escopo funcional desta fase |

### O que estava listado como pendente mas já foi entregue (corrigido nesta revisão)
Upload real de arquivo na Biblioteca, onboarding guiado de nova clínica,
anexos reais na Evolução Clínica/Diário, endereço completo da clínica —
todos esses já estão prontos e testados; as tabelas antigas mais abaixo
neste documento só não tinham sido atualizadas.

---

## 🆕 Ficha Clínica opcional + acertos finais (entregue)

Fecha o item que o usuário pediu pra guardar por último, como "plus":
sub-registro clínico (diagnóstico, alergias, medicações, profissionais
externos) **completamente separado** da identidade básica do paciente, e
**opcional de verdade** — nada bloqueia, nada é obrigatório.

- Tabela própria `fichas_clinicas`, 1 registro por paciente, criado só
  quando alguém realmente preenche
- Card na Jornada mostra "Ainda não preenchida — é totalmente opcional"
  quando vazia, com botão discreto "+ Preencher (opcional)"
- **Só gestor/profissional edita** — o responsável **vê mas não edita**
  (testado o bloqueio: 403 se o responsável tenta escrever). Adicionei
  também uma tela somente-leitura no Perfil do Responsável, com botão
  "📋 Ficha" ao lado de cada filho
- Destaque visual pra alergias (⚠️) e rastreabilidade ("Atualizada por X · data")

Junto com isso, dois ajustes que o usuário trouxe depois de testar:

- **Modal "Ver detalhes comerciais" do Admin não mostrava os dados
  institucionais** (CNPJ, endereço, especialidades) que foram preenchidos na
  criação da clínica — eram salvos corretamente, só não apareciam nesse
  modal específico. Criei o endpoint `PUT /admin/clinicas/<id>/institucional`
  e estendi o modal pra mostrar/editar os dois grupos de dados juntos
- **"Área de atuação" virou "Especialidades"**, e trocou de checklist fixo
  pra campo de texto livre com tags removíveis — cada clínica pode ter
  especialidades bem diferentes, então faz mais sentido a gestora digitar
  as suas do que escolher de uma lista pré-definida

Testado nos dois lados, bateria completa de regressão sem erros.

---

## 🆕 Missões reorganizadas + gestão de categorias da Biblioteca (entregue)

Ajuste fino pedido depois de eu explicar onde ficava o feedback da família
(o usuário não achava porque os dados de exemplo já vêm com feedback
pré-cadastrado em tudo):

- **Tela do Responsável agora separa "📋 Missões desta semana" de
  "✅ Já conquistadas"**, igual ao Mundo da Criança — antes era uma lista só,
  concatenada
- **As concluídas sem feedback aparecem primeiro** dentro de "Já
  conquistadas" (e dentro de cada grupo, as mais recentes primeiro) — assim
  fica fácil achar o que ainda precisa de avaliação sem rolar a tela toda
- **Seed ajustado**: a missão concluída mais recente de cada paciente agora
  fica de propósito sem feedback — dá pra ver e testar o botão "Como foi
  essa atividade?" assim que abre a demo, sem precisar criar nada manualmente
- **Gestão de categorias da Biblioteca**: o backend já tinha o endpoint
  pronto, mas não existia nenhuma tela pra usar. Adicionei um botão
  "🏷️ Categorias" no cabeçalho da Biblioteca com um modal de criação —
  esclarecimento à parte: a **dificuldade** (fácil/médio/difícil) é uma
  escala fixa de 3 níveis por design, não configurável por clínica — só a
  **categoria** é personalizável

Testado nos dois lados, bateria completa de regressão sem erros.

---

## 🆕 Consertos visuais + prévia de missão + mídia real pra criança (entregue)

Segunda leva de feedback do usuário, com prints. Todos os 6 pontos verificados
no código antes de mexer (nem tudo era bug — o item da "dificuldade" é uma
escala fixa por design, expliquei o porquê em vez de mudar):

- **Ícones desalinhados**: bug de CSS real no `.botao-icone` (faltava
  `display:flex` centralizando o conteúdo) — afetava vários botões
  circulares (voltar, medalhas, etc.) em várias telas
- **Botão "Histórico" malfeito**: estava sem a classe base `.botao`,
  herdando a borda padrão feia do navegador
- **Estrelas/fogo sem explicação**: agora mostram "3 estrelas" e "3 dias
  seguidos" (com singular/plural certo) em vez de só números soltos, com
  tooltip explicando o que cada um significa
- **Arquivos da Biblioteca não apareciam pra criança** — esse era o gap mais
  sério dos 6: a tela de missão só mostrava ícone+título, nunca a foto,
  vídeo ou áudio real que foi enviado. Implementei o carregamento sob
  demanda da mídia de verdade (mesmo padrão do Diário/Chat), testado com uma
  imagem real
- **Responsável pode clicar na missão pra pré-visualizar**: abre exatamente
  a mesma prévia que a criança vê no Mundo dela, antes dela fazer — criei o
  endpoint `GET /jornada/missao/<id>` pra isso
- **Reforcei segurança**: o endpoint de detalhe de exercício não validava
  antes se o usuário tinha acesso à clínica dona daquele conteúdo

Testado nos dois lados (projeto real + demo), bateria completa de regressão
sem erros.

---



Essa leva é a mais **operacional/executável** de todas até aqui: User Stories
com critérios de aceite testáveis, contrato de API REST completo, schema de
banco em nível lógico, modelo de segurança, e o fluxo de onboarding
tela-a-tela. Diferente das levas anteriores (que validavam princípios), essa
aqui **valida implementação**: dá pra conferir, requisito por requisito, o
que já bate com o que construí.

**O que já bate (boa notícia):** isolamento multi-tenant por `organizacao_id`
em toda query, RBAC por papel, N:N paciente↔responsável e paciente↔profissional,
histórico nunca sobrescrito (diário terapêutico como registros append-only),
Financeiro desacoplado e opcional, "Modular Monolith" (meus blueprints Flask
= exatamente essa recomendação), princípio anti-ERP respeitado em todo o
produto, Golden Path (Clínica→Profissional→Paciente→Responsável→Missão→
Execução→Evolução) funcional de ponta a ponta — validado manualmente várias
vezes ao longo desta conversa.

**O que não bate — gaps novos e concretos**, abaixo.

---

## 🔴 Gaps concretos novos (desta leva de documentos) — ✅ TODOS ENTREGUES

*(tabela histórica — todo item abaixo já foi implementado em rodadas
posteriores; ver seção "Revisão geral" no topo do documento para o estado
atual real)*

| Item | Documento | Por que importa | Esforço |
|---|---|---|---|
| **Onboarding wizard completo da clínica** | Docs 31A, 32, 33 | Já era gap conhecido, mas agora tenho a especificação tela-a-tela completa (ONB-001 a ONB-015): cadastro → gestor → equipe → paciente → responsável → biblioteca → primeira missão → conclusão, com checklist "essencial vs recomendado" e métrica de TTFV (Time to First Value). Hoje o Admin cria a clínica e "solta" o gestor sozinho | Médio-Grande |
| **Convite por e-mail (ativação de conta)** | Docs 31A, 35, 36 | Hoje, ao cadastrar profissional/responsável, o gestor já define a senha (`mudar123`) diretamente. O fluxo correto é: convite → e-mail → destinatário define a própria senha → ativa conta. Simulável sem servidor de e-mail real (gerar link/token e mostrar na tela, já que não tenho SMTP neste ambiente) | Pequeno-Médio |
| **Reações rápidas no chat (👍❤️⭐👏😊)** | Doc 29 | Descoberta interessante: o **backend já tem** o endpoint (`/mensagem/:id/reagir`), mas a tela de Chat nunca ganhou o botão pra usar isso. É plugar a UI que falta | Pequeno |
| **Envio de imagem/vídeo no chat** | Docs 29, 30, 37 | Hoje o chat só manda texto. O padrão de upload que já uso no Diário/Biblioteca (base64, até 4MB) é diretamente reaproveitável aqui | Pequeno |
| **Estado "rascunho" na missão** | Docs 30, 31 | US-017/019 pedem que a missão possa ser salva como rascunho antes de "publicada". Hoje toda missão criada já nasce com status pendente/visível à família — não existe rascunho | Pequeno |
| **Ficha clínica separada da identidade** | Doc 34 (`ClinicalProfile`) | Diagnóstico, alergias, medicamentos, profissionais externos deveriam ficar num sub-registro separado do cadastro básico do paciente, com controle de acesso próprio (responsável não vê tudo por padrão). Hoje o cadastro de paciente só tem nome/nascimento/avatar | Médio |
| **Biblioteca em 3 camadas** | Doc 31A, 32 | Biblioteca da Plataforma (conteúdo do SaaS) → Biblioteca da Clínica (conteúdo próprio) → exercício efetivamente usado. Hoje só existe o nível "Biblioteca da Clínica" | Médio |
| **Área de atuação / especialidades da clínica** | Docs 31A, 32, 34 | Campo "quais especialidades a clínica oferece" (multi-select: Fonoaudiologia, Psicologia, TO...) não existe hoje em `organizacoes` — prepara o produto pra sair do nicho único de fonoaudiologia | Pequeno |
| **Reset de senha real (token de uso único)** | Docs 35, 36 | Hoje `/auth/esqueci-senha` é 100% simulado (só retorna uma mensagem). O fluxo correto: token com validade, uso único, invalidação de sessões antigas | Pequeno-Médio |
| **Estado "iniciada" na execução da missão** | Doc 30, 37 | Hoje uma atividade só tem pendente/concluída. Os documentos quer um estado intermediário "iniciada" (com evento `activity_started` distinto de `activity_completed`) — relevante pra funil de analytics | Pequeno |

## 🟡 Gaps de higiene/arquitetura (baixo risco, vale registrar)

| Item | Nota |
|---|---|
| **Soft delete inconsistente** | Uso `ativo` em `usuarios`/`exercicios`/`organizacoes`, mas não em `mensagens`, `cobrancas`, `consultas`. Doc 34 pede consistência via `deleted_at`/estado em todas as entidades relevantes |
| **MFA (autenticação multifator)** | Não implementado. Doc 36 recomenda ao menos para Gestor/Admin. Razoável adiar — exige um segundo fator real (TOTP), sem valor demonstrável num MVP local |
| **Endereço completo da clínica** (CEP, logradouro, número...) | Só tenho nome/cor/logo. Baixo valor prático pra demo, mas é campo P0 no Doc 32 |
| **UUID em vez de ID incremental** | Toda a arquitetura de referência usa UUID como identificador externo. Decisão de design válida para produção real (evita enumeração sequencial), mas re-arquitetar isso agora é custo alto para ganho baixo numa demo — sinalizo como débito técnico consciente, não erro |

## 🟢 Confirmado como "não fazer agora" (a nova leva concorda com isso)

Os documentos 29–37 reforçam, com convicção ainda maior que antes, que os
itens abaixo são **explicitamente fora do MVP** — não é lacuna, é decisão:
Agenda completa (fica no ERP), Prontuário clínico completo, Faturamento/
Convênios/Boleto/NF-e completos, IA autônoma/diagnóstica, Relatórios clínicos
automáticos, Microserviços (recomenda-se "Modular Monolith bem estruturado",
exatamente a arquitetura Flask+blueprints que já construí).

---

## 📚 Nova leva de documentos — o que eles mudam

Esses 20 documentos são de duas naturezas bem diferentes, e vale entender a
diferença antes da lista de gaps:

**Fundamentos de produto e UX** (Docs 02–06, 014–018) — descrevem *o quê* e
*o porquê*. Na maior parte, **validam** decisões que já tomei (os 4 perfis
independentes, mobile-first para Responsável/Criança, o Diário Terapêutico
como diferencial, tom de voz acolhedor). Onde divergem, é porque adicionam
camadas que eu ainda não tinha: um KPI central de negócio, um assistente de
IA personificado, um wizard de onboarding, navegação condicionada a módulos
habilitados.

**Arquitetura técnica** (Docs 20–27 — DDD, Multi-Tenant, Feature Flags,
Permissions, Event-Driven, IA, Integrações, Analytics) — descrevem *como*,
em nível de plataforma SaaS madura (múltiplos tenants, feature flags em 5
camadas, message broker, adapters por integração, LLM real com tool-calling).
Grande parte **já bate** com o que construí (isolamento por `organizacao_id`,
tabela `eventos` como event log, RBAC por papel). A parte que não bate é
essencialmente **escala**: essa arquitetura foi pensada para centenas de
clínicas e múltiplos ERPs; meu projeto é um MVP com SQLite. Não é um erro —
é o degrau certo antes do próximo. Sinalizo isso caso a caso abaixo.

---

## 🔴 Gaps concretos e implementáveis agora — ⚠️ PARCIALMENTE DESATUALIZADA

*(ICT, Feature Flags de 2 camadas, Onboarding wizard e Personalização/White
Label já foram entregues — ver seções "entregue" correspondentes. Os itens
realmente ainda pendentes desta tabela estão listados na seção "Revisão
geral" no topo do documento.)*

| Item | Documento(s) | Por que importa | Esforço |
|---|---|---|---|
| **Índice de Continuidade Terapêutica (ICT)** | Doc 04, Doc 27 | É citado como "o maior KPI da empresa" — mede se a plataforma mantém a criança engajada entre consultas (sequência + missões + interação da família). Tenho todos os dados (`eventos`, `missoes`, `gamificacao_paciente`) para calcular isso hoje; só falta a métrica composta e o card no dashboard do Gestor | Pequeno |
| **Feature Flags / módulos habilitáveis por clínica** | Docs 014, 015, 016, 022, 22A | Hoje o Financeiro aparece sempre no menu do Responsável, sem checar se está habilitado — os próprios documentos usam esse exato exemplo (BR-015-003, EXP-001 Tela 05). Dá pra implementar uma versão real das camadas "Plano → Clínica → Usuário" (as camadas "Plataforma" e "Feature Flag" globais fazem menos sentido numa instância única) | Médio |
| **Onboarding wizard da clínica** | Doc 016 (EXP-001) | Hoje o Admin cria a clínica e "solta" o gestor sozinho. O documento pede: boas-vindas → dados → identidade visual → plano → **ativação de módulos** → integrações → equipe → dashboard | Médio |
| **Nomes personalizáveis (White Label leve)** | Doc 018, Doc 022 | Nome do assistente de IA, nome da "moeda" da gamificação (hoje fixo em "XP"), nome das medalhas — hoje tudo hardcoded | Pequeno |
| **Seletor de Paciente com busca/favoritos/recentes** | Doc 017A (DC-010) | Listado como 1 dos 5 "componentes estratégicos". Hoje o profissional só tem uma grade estática de pacientes, sem busca instantânea, favoritos ou "recentes" | Pequeno-Médio |
| **Assistente de IA (v1 heurística, não-LLM)** | Docs 06, 017, 17A, 25 | O maior item novo. Os documentos pedem um "AI Orchestrator" com Tool Layer real (`search_patient`, `search_exercise`, `get_mission`...) sobre um LLM. Não tenho acesso à internet neste ambiente pra chamar uma IA real, mas dá pra construir o *mesmo padrão arquitetural* (Context Engine → Permission Engine → Tool Layer) com busca/regras locais, deixando o "encaixe" pronto para trocar por um LLM de verdade depois — mesmo espírito da "sugestão de missão" que já fiz no Diário | Médio-Grande |
| **Dashboard "Ecosystem Analytics"** | Doc 27 | Funil "Missão criada → notificado → visualizada → iniciada → concluída → recompensa" — consigo montar isso com os eventos que já registro, mas hoje não exponho esse funil em nenhuma tela | Pequeno-Médio |
| **Mascote com customização (roupas/acessórios)** | Doc 06 | Hoje o mascote evolui só automaticamente por estágio; o documento propõe que a criança escolha acessórios (usando moedas da gamificação) | Médio |
| **Compartilhamento social de conquistas** | Doc 05 | "Cartão" de conquista pronto pra compartilhar no WhatsApp/Instagram (ex: "30 dias de dedicação") | Pequeno |
| **Timeline de Alta Terapêutica** | Doc 06 | Ao encerrar o tratamento, gerar uma linha do tempo-presente com toda a jornada (fotos, medalhas, mensagens) como "presente" da clínica pra família — hoje não existe fluxo de encerramento algum | Médio |

## 🟡 Gaps arquiteturais — mapeados, não recomendo agora

Esses fazem sentido para uma plataforma SaaS com centenas de clínicas, mas
seriam over-engineering para o estágio atual (implementá-los "de brincadeira"
sem a necessidade real por trás criaria complexidade que atrapalha, não ajuda):

| Item | Documento | Por que esperar |
|---|---|---|
| **Event Bus real (Kafka/RabbitMQ/SQS)** | Doc 24 | Minha tabela `eventos` já implementa o *padrão* (publicar fato, dono não conhece consumidor); trocar por um broker de mensagens só se justifica com múltiplos serviços/filas reais, o que não é o caso de uma app monolítica Flask |
| **Permission Engine centralizado (recurso × ação × escopo × delegação)** | Doc 23 | Meu RBAC via decorators (`@papel_required`, `paciente_acessivel`) cobre as mesmas garantias hoje. Centralizar em um "motor" formal só compensa quando o catálogo de permissões crescer bem além dos 4 papéis atuais |
| **Integration Layer com adapters reais (ERP/PIX/NF-e)** | Doc 26 | Os próprios documentos dizem para não decidir o ERP-alvo antecipadamente. Minha Central de Integrações (toggle liga/desliga) já é o "contrato interno" — os adapters de verdade só fazem sentido com um ERP real definido |
| **IA com LLM real + guardrails de produção** | Doc 25 | Requer acesso a um provedor de IA (API paga, chave, rede) que não tenho neste ambiente de execução. O que dá pra fazer agora é o "andaime" (ver tabela acima) |
| **Analytics multi-camada completo (Produto/Clínica/Negócio/Ecossistema) com coortes** | Doc 27 | Faz sentido com volume real de dados de múltiplas clínicas ao longo de meses; hoje eu teria que simular tudo, o que teria pouco valor prático |

---

## 🆕 Biblioteca em 2 camadas: Plataforma + Clínica (entregue)

Fecha o item "Biblioteca em 3 camadas" (na prática, 2 camadas — a terceira,
"exercício efetivamente usado numa missão", já existia via a tabela
`atividades`). Um exercício com `organizacao_id` nulo é **Biblioteca da
Plataforma** — mantido pelo Admin do SaaS, visível automaticamente para
**todas as clínicas**. Um exercício com `organizacao_id` preenchido é
**Biblioteca da Clínica** — privado, só editável por quem é de lá.

- Toda clínica vê as duas camadas somadas na mesma tela, com badge
  "🌐 Plataforma" diferenciando a origem
- Só o Admin edita/arquiva a camada da Plataforma (testado o bloqueio: um
  gestor tentando editar item da Plataforma recebe 403)
- Gestor/Profissional podem "adotar" um item da Plataforma — duplica pra
  biblioteca da própria clínica, virando totalmente editável a partir daí
  (é assim que uma clínica customiza um conteúdo pronto do catálogo do SaaS)
- Admin ganhou uma tela própria (`#/admin/biblioteca`) pra gerenciar o
  catálogo central, com item de menu dedicado
- Populei a Biblioteca da Plataforma com 5 itens de exemplo no seed

Testado nos dois lados (projeto real + demo), incluindo as regras de
permissão cruzadas.

## 📋 Lista de revisão do usuário (8 pontos)

Grupo 1 (rápidos/alto impacto) entregue e testado. Grupos 2, 3 e 4 seguem
pendentes, na ordem combinada.

### ✅ Grupo 1 — entregue

- **#3 Especialidade dinâmica**: o dropdown de "Especialidade" (cadastro de
  profissional e wizard de onboarding) agora usa a Área de Atuação real da
  clínica, com fallback pra lista padrão em clínicas que ainda não configuraram
- **#4 Cores e logo reais**: as cores escolhidas em Configurações agora são
  **de verdade aplicadas** em toda a plataforma — criei um pequeno utilitário
  de mistura de cor (`escurecerCor`/`clarearCor`) que deriva os tons
  escuro/claro automaticamente a partir da cor escolhida, aplicado via CSS
  custom properties no login e ao salvar. Também implementei upload real de
  logo (imagem, base64, até 2MB) com fallback pro emoji quando não há imagem
- **#7 Feedback da família**: conectei a UI que faltava — botão "💬 Como foi
  essa atividade?" em missões concluídas sem feedback ainda, abrindo um
  seletor de humor (😄🙂😐😕) + comentário opcional. Também reforcei a
  segurança do endpoint (antes não validava se a missão pertencia ao
  paciente do responsável que estava enviando)

### ✅ Perfil do responsável editável — entregue

Upload real de foto do próprio responsável, edição de nome/telefone, e
upload de foto de cada filho (fallback pro mascote emoji quando não há
foto). Backend: `PUT /api/pessoas/perfil` (autoedição, qualquer papel) e
`PUT /api/pessoas/pacientes/<id>/foto`. `/auth/me` e `/auth/login` passaram
a devolver esses campos novos.

Durante a sincronização com a demo, encontrei e corrigi um bug sutil: lá, o
usuário "atual" em memória é uma *cópia* tirada no login, não uma referência
ao registro de verdade — minha primeira versão do endpoint estava
atualizando só a cópia (que se perderia num "reload" da sessão). Corrigido
para gravar no registro real, validado navegando pra outra tela e voltando.

Testado nos dois lados, bateria completa de regressão sem erros.

### ✅ Grupo 2 (cadastro/onboarding) — entregue

- **#1 Campos institucionais da clínica**: schema ganhou `cnpj`, `telefone`,
  e endereço completo (`cep`/`logradouro`/`numero`/`bairro`/`cidade`/`uf`)
- **#2 Área de atuação já no cadastro**: o modal "Nova Clínica" do Admin
  agora tem tudo isso de uma vez — antes só dava pra configurar depois, na
  tela de Configurações do gestor. A mesma seção também foi adicionada em
  Configurações, pra completar/editar quando quiser

Testado o ciclo completo: Admin cria clínica com todos os dados → gestor
edita depois → persiste corretamente (confirmado com reload real da
página, não só o estado da sessão). Nos dois lados, bateria completa de
regressão sem erros.

### ✅ Grupo 3 (missões) — entregue

- **#5 Editar/excluir missão**: `PUT /jornada/missao/<id>` e
  `DELETE /jornada/missao/<id>`, ambos **bloqueados para missões já
  concluídas** (uma vez que a criança ganhou a recompensa por aquele
  conteúdo, ele vira histórico permanente — testei esse bloqueio
  explicitamente). Os cards de missão ganharam ✏️/🗑️, visíveis só quando
  aplicável
- **#6 Criar exercício sem sair da tela de Nova Missão**: botão
  "+ Criar novo exercício" dentro do modal, que abre o modal de cadastro da
  Biblioteca por cima — ao salvar, a lista de exercícios dentro do modal de
  missão se atualiza sozinha e o item recém-criado já vem **marcado**

Testado o ciclo completo (criar → editar → excluir, e o bloqueio em missão
concluída) nos dois lados, bateria completa de regressão sem erros.

### ✅ Grupo 4 (perfil) — entregue

- **#8 Foto de perfil do profissional + tela de Perfil**: o endpoint
  `PUT /api/pessoas/perfil` já tinha sido construído de forma genérica (pra
  qualquer papel) quando implementei o perfil do Responsável — reaproveitei
  ele direto aqui, sem duplicar lógica
- Nova tela **"Meu Perfil"** no menu de Gestor e Profissional: upload de
  foto própria, edição de nome/telefone (e-mail fica travado, é o
  identificador de login)
- Upload de foto **também no cadastro/edição de profissional pelo gestor**
  (tela Equipe) — com preview ao vivo, e a foto real passa a aparecer na
  listagem da Equipe (com fallback pro ícone de especialidade)

Com isso, **fecha a lista inteira de 8 pontos** da segunda leva de revisão,
levantada pelo usuário com prints. Testado nos dois lados, bateria completa
de regressão sem erros (incluindo mobile).

## 🆕 Onboarding wizard completo (entregue)

O maior item pendente da lista. Fluxo guiado de 6 telas para clínicas novas
(Doc 31A/32/33): Boas-vindas → Identidade da clínica → Convidar equipe →
Primeiro paciente → Módulos → Conclusão com checklist.

**Decisão de design importante:** em vez de guardar "em qual etapa a pessoa
está" num campo à parte (que facilmente fica dessincronizado da realidade se
a pessoa sair no meio), cada etapa é **computada ao vivo a partir dos dados
reais** — "tem profissional cadastrado?", "tem paciente cadastrado?". Isso
faz o wizard ser naturalmente retomável sem duplicar estado, e reaproveita
exatamente os mesmos endpoints já usados no resto do produto (criar
profissional, criar paciente, alternar módulo) — o wizard é só uma camada de
orquestração/guia por cima deles, não uma reimplementação.

**Quando aparece:** só para clínicas que "parecem novas" (zero profissionais
e zero pacientes) e que ainda não concluíram ou pularam o onboarding —
verificado automaticamente no momento do login do gestor. Uma clínica com
dados reais nunca é interrompida por isso (testado explicitamente).

**Testado ponta a ponta**, nos dois lados (projeto real + demo interativa):
criar clínica pelo Admin → convite → ativação → wizard completo (todas as
etapas, incluindo pular etapas individuais) → conclusão → dashboard; além de
"pular tudo", relogar sem o wizard reaparecer, e responsividade mobile.

## 🆕 Convite por e-mail para ativação de conta (entregue)

Fecha o item "Convite por e-mail" da lista de gaps. Antes, o gestor criava
profissional/responsável/gestor-de-clínica já com uma senha padrão conhecida
(`mudar123`). Agora:

- A conta nasce com senha **aleatória e bloqueada** (impossível de adivinhar)
- Um token de convite de uso único é gerado (validade de 3 dias — mais longa
  que a de redefinição de senha, já que convite não é uma situação de urgência)
- Reaproveitei a mesma tabela e o mesmo fluxo de tela do "esqueci minha senha"
  (o serviço `tokens_service.py` já unificava os dois casos por trás de um
  campo `tipo`), mudando só o texto exibido: "Ativar minha conta" no caso de
  convite, "Salvar nova senha" no caso de redefinição
- Testado nos 3 pontos onde isso acontece: cadastro de profissional,
  vínculo de responsável, e criação de nova clínica pelo Admin — em todos,
  um modal mostra o link pra copiar e enviar manualmente (já que este
  ambiente não tem servidor de e-mail)

**Nota de transparência:** durante esta rodada o ambiente de execução foi
reiniciado no meio do trabalho, e o diretório local (fora de `/mnt/user-data/`)
foi perdido. Recuperei tudo a partir dos últimos arquivos já entregues (zip
do projeto real + HTML da demo) e reapliquei as mudanças do zero — validado
de novo, ponta a ponta, sem perda real de funcionalidade entregue.

## 🆕 Imagem/vídeo no chat, área de atuação e reset de senha real (entregue)

Mais 3 itens rápidos da lista de gaps, construídos e testados **primeiro no
projeto real** (Flask + SQLite) e só depois replicados na demo interativa:

- **Envio de imagem/vídeo/áudio no chat**: reaproveita o mesmo padrão de
  upload já usado no Diário Terapêutico e na Biblioteca (base64, até 4MB,
  carregado sob demanda para não pesar a listagem de mensagens). Botão 📎
  na barra do chat.
- **Área de atuação da clínica**: checklist de especialidades
  (Fonoaudiologia, TO, Psicopedagogia, Psicologia, Fisioterapia, Nutrição,
  Educação Física Adaptada) na tela de Configurações, com persistência real.
- **Reset de senha com token real**: token de uso único com expiração de 1h
  (`tokens_redefinicao_senha`), substituindo o endpoint 100% simulado de
  antes. Como este ambiente não tem servidor de e-mail, o link aparece
  diretamente na tela rotulado como "modo demonstração" — mas o fluxo em si
  (gerar token → validar → trocar senha → invalidar token usado) é real e
  testado, incluindo o caso de reuso de token bloqueado.

## 🆕 Reações no chat, missão em rascunho e estado "iniciada" (entregue)

Os 3 primeiros itens da lista de gaps concretos da terceira leva de documentos:

- **Reações rápidas no chat**: o backend já existia (só não tinha UI). Agora
  cada mensagem tem um botão "reagir" que abre um seletor com 👍❤️⭐👏😊 —
  clicar de novo na mesma reação remove (toggle). Validado com checagem de
  acesso (não dá pra reagir a mensagem de conversa que não é sua).
- **Missão com estado rascunho → publicada**: ciclo completo
  `rascunho → pendente → iniciada → concluída`. Rascunhos são **invisíveis**
  para o responsável (testado explicitamente) e só viram missão de verdade
  ao clicar em "Publicar" — momento em que a notificação é disparada. O
  formulário de nova missão agora tem dois botões: "Criar e publicar" e
  "Salvar como rascunho".
- **Estado "iniciada" (activity_started)**: abrir a missão no Mundo da
  Criança já conta como "iniciada" automaticamente (sem precisar de ação
  extra da criança) — o card mostra ⏳ "em andamento" tanto para a criança
  quanto para o responsável. O endpoint de conclusão aceita tanto `pendente`
  quanto `iniciada`, mas bloqueia `rascunho`.

Durante essa rodada também corrigi um bug real de responsividade encontrado
pela bateria de testes: o chat com múltiplas conversas (lista de pacientes +
mensagens lado a lado) estourava a largura da tela em celulares — a lista
agora vira uma faixa horizontal rolável abaixo de 700px.

## 🆕 Índice de Continuidade Terapêutica, Feature Flags e Personalização (entregue)

Os 3 itens rápidos da lista de gaps concretos foram implementados e testados
ponta a ponta (backend real + demo interativa):

- **ICT**: card em destaque no dashboard do Gestor + detalhamento na Jornada de
  cada paciente, com os 4 componentes (adesão, sequência, família, profissional)
  visíveis. Rotulado como métrica de engajamento, não clínica.
- **Feature Flags**: módulos Financeiro, IA, Indicadores Avançados, Integrações
  e Identidade Visual Própria agora respeitam 2 camadas reais — Plano
  (Starter/Pro/Enterprise) → Clínica (toggle do gestor em `/gestor/modulos`).
  O gate é aplicado no backend (não só escondido na tela): testei bloqueando
  o endpoint do Financeiro diretamente via API. Também existe a camada
  "Usuário" (override de Financeiro por responsável específico) no backend,
  ainda sem tela dedicada no frontend — próximo passo natural.
- **Personalização**: nome do assistente de IA, nome da "moeda" da
  gamificação e nome genérico das medalhas, editáveis em Configurações com
  pré-visualização ao vivo, já aplicados nas telas de Jornada, Responsável
  e Mundo da Criança.

## 🆕 Módulo 07 — Diário Terapêutico (entregue)

Implementado por completo: registro de evolução clínica, pontos positivos/de
atenção, objetivo da próxima semana, mensagem para a família, compartilhamento
automático (com notificação), histórico cronológico na Jornada, e **anexos
reais** (foto/áudio/vídeo curtos, upload de verdade via base64 — isso fecha
parcialmente o gap de "upload real de arquivo" listado abaixo, com o limite
de 4MB por anexo declarado). RBAC (BR-010): só profissional vinculado ao
paciente cria registros. Testado ponta a ponta (backend + UI, Gestor/
Profissional/Responsável).

---

---

## 🔴 Crítico — corrigido nesta rodada

| Gap | Onde estava | Status |
|---|---|---|
| **Navegação quebrada no mobile** | `layout.css`: `.shell-sidebar { display:none }` abaixo de 900px, sem substituto — Gestor/Profissional/Admin ficavam sem menu no celular | ✅ Corrigido — menu hambúrguer + drawer |
| **Notificações sem interface** | Backend (`notificacoes_bp.py`) completo desde o início, mas nenhuma tela consumia | ✅ Corrigido — sino com contador + painel |
| **Bug de sessão na demo** | `organizacao_id` sumia do usuário após login na versão em memória | ✅ Corrigido (relatado na entrega anterior) |

## 🟡 Fase 2 — iniciado nesta rodada

| Item | Descrição | Status |
|---|---|---|
| **Central de Integrações** (Módulo 10, Doc 10) | Tela para conectar WhatsApp, Google Calendar, ERP e gateway de pagamento — os *toggles* e o modelo de dados (`integracoes`) já existiam no schema, mas sem tela nem endpoints | ✅ Implementado (toggle liga/desliga, estado real salvo no banco; a integração de fato — OAuth, webhook — continua não implementada, como é honesto esperar nesta fase) |
| **Sugestão de missão assistida** (Doc 00 menciona IA no roadmap) | Botão "Sugerir com IA" no formulário de nova missão, que cruza o objetivo terapêutico com tags da Biblioteca | ✅ Implementado como **heurística por palavra-chave** (não é um modelo de IA real — deixei isso explícito na interface). É o degrau certo antes de plugar um LLM de verdade via API. |

## 🟡 Fase 2 — mapeado, não iniciado (candidatos para a próxima rodada) — ⚠️ PARCIALMENTE DESATUALIZADA

*(Upload real na Biblioteca, Onboarding guiado e Anexos na Evolução Clínica
já foram entregues. Os itens realmente pendentes estão na seção "Revisão
geral" no topo.)*

| Item | Por que importa | Esforço estimado |
|---|---|---|
| **Upload real de arquivo na Biblioteca** | Hoje um exercício guarda uma URL de texto; não dá pra realmente subir um vídeo/PDF/imagem. *(O Diário Terapêutico já resolve isso para seus próprios anexos — o mesmo padrão pode ser reaproveitado aqui.)* | Pequeno — reaproveitar o padrão de upload base64 do Diário |
| **Tela de comparação de exercícios** (lado a lado) | Mencionada como padrão de UX possível no Doc 13; hoje só existe visão em grade | Pequeno — reaproveita o `comparison_card` do design system |
| **Calendário visual (grade), não só lista** | Agenda hoje é uma lista cronológica; gestores de clínica costumam querer visão de semana/mês | Médio |
| **Anexos na Evolução Clínica** | Profissional só registra texto; documentos reais (fono, TO) costumam anexar fotos/vídeos de sessão | Médio (depende do storage, mesmo ponto do upload) |
| **Onboarding guiado de nova clínica** | Hoje o Admin do SaaS cria a clínica e "solta" o gestor sozinho — falta um wizard inicial (cadastrar 1ª equipe, 1º paciente) | Pequeno-Médio |
| **Relatório exportável (PDF)** | Gestor/família não conseguem baixar um resumo da jornada | Pequeno — já tenho a skill de PDF disponível para isso |
| **Push notification real / WhatsApp** | Notificação hoje só existe *dentro* do app; documentos citam WhatsApp como canal esperado | Alto — depende de conta comercial WhatsApp Business API |
| **Papel "Criança" com sessão própria** | Hoje a criança só existe "dentro" da sessão do responsável (trocar de modo); não há PIN/login próprio | Médio — decisão de produto antes de virar código |

## 🟢 Fase 3 — mapeado (mais distante, maior investimento)

| Item | Nota |
|---|---|
| **IA generativa real** (geração de plano terapêutico, missões personalizadas) | A heurística desta rodada é o "andaime" — trocar por chamada a um LLM real é o passo natural depois |
| **Integração ERP real (financeiro)** | Depende de qual ERP a clínica-piloto usa (Doc 013 já deixa claro: financeiro daqui *não substitui* o ERP) |
| **Multi-idioma (i18n)** | Hoje 100% pt-BR fixo no código, sem camada de tradução |
| **Modo escuro** | Não mencionado nos documentos, mas comum em produtos consumer |
| **Acessibilidade formal (WCAG)** | Há `:focus-visible` e `prefers-reduced-motion`, mas falta auditoria completa (contraste, `aria-label`, navegação por teclado em todos os modais) |
| **Testes automatizados (pytest + Playwright em CI)** | A validação até aqui foi manual/scriptada durante a construção, não uma suíte que roda sozinha |

---

## Sobre o mobile-first desta rodada

Faltava mobile-first especificamente nas **3 experiências desktop** (Gestor,
Profissional, Admin do SaaS) — o Responsável e a Criança já nasceram mobile
(Documento 12 pede isso explicitamente). O que mudou:

- Sidebar vira **drawer off-canvas** abaixo de 900px, acionado por um botão
  hambúrguer fixo no topo.
- Grades de KPI, biblioteca, listas de pacientes — já usavam
  `auto-fit`/`minmax`, então já colapsavam para 1 coluna corretamente; só
  precisavam da navegação para acompanhar.
- Modais ganharam padding/largura ajustados para telas pequenas.
- Testado em 375×667 (iPhone SE, o viewport mais restritivo comum) e
  390×844 (iPhone 12/13) via Playwright, nos 4 perfis.
