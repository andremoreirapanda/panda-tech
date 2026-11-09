# Financeiro da clínica: cobrança das famílias, fechamento de caixa e repasse — desenho

Data: 07/11/2026. Referências analisadas na conversa: Agendart (conta de
demonstração) e Clínica Ágil (conta da clínica Encanto — só leitura; o
financeiro dela está vazio, a clínica controla o dinheiro fora do sistema).
Delas tiramos só a mecânica, nunca o visual nem os textos.

## 1. Por que

Hoje a clínica marca e atende tudo no PandaUp, mas o dinheiro fica fora: no
fim do período alguém cruza a agenda com os pagamentos para saber quem deve e
quanto pagar a cada terapeuta. O PandaUp já sabe o que aconteceu (consulta
finalizada, falta, procedimento e o valor do dia); falta saber **como cada
família paga** e **como cada terapeuta recebe**. Com isso, cobrança,
fechamento de caixa e repasse saem da agenda sem digitação dupla.

O que existe hoje (ponto de partida):
- `cobrancas` (paciente, descrição, valor, vencimento, status
  pendente/pago/vencido, campos do PIX do Mercado Pago) e `pagamentos`
  (cobrança, valor, forma pix/cartao/boleto/dinheiro/transferencia, pago_em).
- `financeiro_bp.py`: extrato por paciente, resumo do gestor, criar cobrança
  (sem tela), gerar PIX (Mercado Pago da clínica, baixa pelo webhook) e
  confirmar pagamento manual (só gestor/admin).
- Tela do gestor (`viewFinanceiroGestor`): 4 números + extrato de um paciente
  por vez. Tela da família (`viewFinanceiroResponsavel`): as cobranças dela.
- `procedimentos` com valor; a consulta guarda `procedimento_id` e
  `procedimento_valor_centavos` (valor no dia da marcação).
- Status da consulta: `agendada`, `confirmada`, `realizada` (Finalizado),
  `faltou`, `falta_justificada`, `desmarcada_profissional`, `cancelada`.
- Módulo `financeiro` (plano/extra da clínica) e a visibilidade do financeiro
  para o responsável (`financeiro_visivel_para_usuario`).

## 2. Objetivos, não objetivos e anti-objetivos

**Objetivos**
1. Cada paciente tem um **acordo de pagamento** e as cobranças nascem
   sozinhas da agenda.
2. Dar baixa rápido (manual ou automática pelo Mercado Pago) e ver o que está
   em aberto, vencido e para vencer.
3. **Fechamento de caixa** do dia/período por forma de pagamento e por quem
   recebeu.
4. **Repasse** calculado por regra do profissional, com o relatório de
   atendimentos (fechamento do profissional) em PDF e Excel.
5. A família vê, no app, o extrato do que foi cobrado e pago.

**Não objetivos (agora)**: despesas da clínica, plano de contas, DRE,
contas bancárias, centro de custo, convênio/TISS, nota fiscal, boleto,
cobrança automática no cartão da família, lembrete de cobrança por WhatsApp
(vem com o projeto de mensagens).

**Anti-objetivos (o que seria fracasso mesmo funcionando)**
- Ficar pesado como o lançamento da Clínica Ágil (15 campos por lançamento):
  a clínica volta para a planilha. Cada ação comum tem que caber em 1–2
  cliques.
- Profissional ou secretária enxergarem regra de repasse ou relatório.
- Mudar preço ou regra e alterar o que já foi cobrado/fechado.
- Cobrar duas vezes a mesma sessão ou pagar duas vezes o mesmo repasse.

## 3. Quem vê o quê (decidido pelo usuário)

| | Gestor | Secretária | Profissional | Responsável |
|---|---|---|---|---|
| Acordos de pagamento do paciente | vê e edita | vê e edita | não vê | não vê |
| Cobranças e baixa | sim | sim | não | só as dele (extrato), paga pelo PIX |
| Configurações do financeiro (faltas, base do repasse) | sim | não | não | não |
| Regras de repasse | sim | não | não | não |
| Relatórios (caixa, atendimentos/repasse, pendências) | sim | não | não | não |

Profissional não vê nem o próprio repasse. Admin da plataforma segue o
padrão atual (acesso de suporte).

## 4. Etapa 1 — Cobrança das famílias

### 4.1 Configuração da clínica (só gestor)
- **Falta sem aviso (`faltou`) gera cobrança para a família?** sim/não.
- **Falta sem aviso paga repasse ao terapeuta?** sim/não (usada na etapa 3).
- Falta justificada, desmarcada pelo profissional e cancelada **nunca**
  geram cobrança nem repasse (palpite do Claude, não contestado no playback).

### 4.2 Acordo de pagamento (por paciente)
Um paciente pode ter **vários acordos ativos**, um por especialidade (ex.:
mensalidade na Fono e avulsa na TO). Uma consulta pertence ao acordo da
especialidade do profissional que atende. Tipos:

1. **Sessões avulsas** — cada sessão vale o `procedimento_valor_centavos` da
   consulta. As sessões são **juntadas numa cobrança** conforme o combinado:
   - **a cada consulta** (uma cobrança por sessão),
   - **a cada 15 dias** (dias 1–15 e 16–fim do mês),
   - **mensal** (uma cobrança com as sessões do mês).
   Dia de vencimento combinado (ex.: "5 dias depois do fechamento" ou "dia 10
   do mês seguinte" — *chamada do construtor: um campo "vence N dias após o
   fechamento", padrão 5*).
2. **Mensalidade fixa** — valor por mês e dia de vencimento; cobre as sessões
   daquele mês na especialidade (elas não geram cobrança avulsa). Data de
   início e, opcional, de fim. **Mês incompleto (começo ou fim no meio do
   mês) é cobrado proporcional aos dias** (decisão do usuário): valor × dias
   de vigência no mês ÷ dias do mês, arredondado ao centavo.
3. **Pacote** — N sessões por um valor, parcelado em K vezes com vencimentos
   mensais a partir de uma data. Cada sessão finalizada (e a falta, se a
   clínica cobra falta) consome uma do pacote; a agenda e o Atender mostram
   "sessão 3 de 10". Pacote acabado com sessões novas → elas caem como
   "sem acordo" (ver 4.5) até a clínica renovar.

**Especialidade da consulta** *(chamada do Claude)*: a consulta passa a
guardar uma cópia da especialidade de quem atende no momento em que é
marcada ou reatribuída (como já faz com o valor do procedimento); as antigas
são preenchidas pela migração. Sem especialidade (ex.: gestor que não atua
como profissional) = "Geral". O acordo casa com a consulta ignorando caixa e
espaços. Um acordo pode ser marcado **"todas as especialidades"** para a
família que paga tudo junto; um acordo específico vence o "todas".

Paciente sem acordo na especialidade: as sessões ficam **"sem acordo"** e
aparecem nas pendências; nada é cobrado sozinho. *(Palpite: é o padrão mais
seguro para quem está começando a usar.)* Na pendência, três ações: criar o
acordo, cobrar como avulsa (uma cobrança com essas sessões) ou não cobrar
(com motivo, fica na auditoria). Ao **criar um acordo**, o sistema mostra as
sessões "sem acordo" daquela especialidade e pergunta se entram nele
*(chamada do Claude: as clínicas vão cadastrar acordos depois de já estarem
atendendo)*.

Sessão avulsa **sem procedimento ou com valor zero** não gera cobrança de
R$ 0: vai para as pendências como "sem valor", e o gestor ou a secretária
informa o valor na própria linha *(chamada do Claude)*.

Mudar o acordo vale dali para frente; o que já virou cobrança não muda.

### 4.3 Geração das cobranças
- **Avulsa por consulta**: a cobrança nasce quando a consulta vira
  `realizada` (ou `faltou`, se a clínica cobra falta). Se o status voltar
  atrás antes do pagamento, a cobrança é cancelada; se já foi paga, não muda
  sozinha e aparece um aviso para o gestor.
- **Quinzenal/mensal**: no fechamento do período, uma cobrança por paciente e
  acordo, com a lista das sessões (`cobranca_itens`: consulta, data,
  procedimento, valor). **A cobrança do período fica como rascunho** até o
  gestor ou a secretária conferir e **liberar** (pode tirar uma sessão ou dar
  desconto em valor, com motivo). Só a liberada aparece para a família.
  *(Palpite do Claude, não contestado no playback.)*
- **Mensalidade**: uma cobrança por mês, criada no 1º dia do mês (ou na
  criação do acordo, para o mês corrente).
- **Pacote**: as K parcelas são criadas quando o pacote é cadastrado.
- **Quando roda**: *chamada do construtor* — gerar de forma idempotente ao
  abrir as telas do financeiro e por um script de cron opcional (mesmo padrão
  de `gerar_cobrancas_planos_mensal.py`). Nunca depender só do cron (não
  sabemos se está agendado no servidor).
- **Sessão que muda depois** *(chamada do Claude)*: cobrança de período já
  liberada não reabre. Sessão finalizada com atraso (ex.: da 1ª quinzena,
  finalizada no dia 20) entra no **próximo período aberto** do acordo.
  Sessão que deixa de valer depois de liberada ou paga (ex.: virou falta
  justificada) gera o aviso "baixa a revisar"; o gestor resolve com um
  **ajuste** (desconto/crédito com descrição) na próxima cobrança da família
  ou cancelando a cobrança, se ainda não foi paga. No pacote, a sessão
  consumida volta para o saldo.
- Uma sessão só entra em **uma** cobrança (índice único por consulta nos
  itens). Cobrança manual avulsa continua possível (ex.: material, avaliação
  externa).

### 4.4 Baixa
- Botão **"Receber"**: valor (padrão = total; pagamento parcial permitido e
  a cobrança fica "parcial"), forma (pix, dinheiro, cartão de crédito, cartão
  de débito, transferência), data (padrão hoje) e **quem recebeu** (usuário
  logado). Estorno/desfazer baixa: só gestor, com motivo, fica na auditoria.
- PIX/cartão pelo Mercado Pago da clínica continuam dando baixa sozinhos pelo
  webhook (forma e data vindas do pagamento; "quem recebeu" = "Mercado Pago").
- Status: pendente, parcial, pago, vencido (passou do vencimento sem pagar),
  cancelado, rascunho (só quinzenal/mensal antes de liberar).
- A secretária hoje não confirma pagamento (rota só gestor/admin): passa a
  poder, conforme a tabela da seção 3.

### 4.5 Telas
- **Financeiro → Cobranças** (gestor e secretária): lista com filtros
  (período, status, paciente, especialidade), números do topo (recebido no
  período, em aberto, vencido) e ações Receber / Gerar PIX / ver itens.
  Bloco **"Para conferir"**: cobranças de período em rascunho.
- **Ficha do paciente**, cartão "Financeiro" (gestor e secretária): acordos
  ativos (criar, editar, encerrar) e extrato.
- **Pendências** (só gestor, também no dashboard): sessões sem acordo,
  pacotes com ≤ 2 sessões, mensalidades/pacotes terminando no mês,
  cobranças vencidas, baixas a revisar (status da consulta mudou depois de
  pago).
- **Família**: extrato com cada cobrança e suas sessões, status e botão de
  pagar pelo PIX (já existe), conforme a visibilidade atual do financeiro
  para o responsável.
- **Configurações → Financeiro** (só gestor): as duas chaves de falta e a
  base do repasse (etapa 3).

## 5. Etapa 2 — Fechamento de caixa (só gestor)

- Período (padrão: hoje), filtro por quem recebeu e por forma.
- Totais **por forma de pagamento** e **por quem recebeu**, e a lista dos
  recebimentos (data/hora, paciente, cobrança, forma, valor, quem recebeu).
  Base: os registros de `pagamentos` com data no período (o que de fato
  entrou), estornos descontados.
- PDF (logo da clínica, período, data de emissão) e Excel.
- *Chamada do construtor:* sem "abrir/fechar caixa" com saldo inicial neste
  momento; é um relatório de conferência.

## 6. Etapa 3 — Repasse aos profissionais e relatórios

### 6.1 Regras de repasse (só gestor)
- Por profissional: **regra padrão** = percentual **ou** valor fixo por
  sessão.
- **Exceções** por procedimento e por tipo de acordo (avulsa, mensalidade,
  pacote). Ordem: procedimento + tipo > procedimento > tipo > padrão.
- Na Clínica Ágil, a mesma profissional tem 65% num procedimento e 60% em
  outro: o caso comum é exceção por procedimento.
- Profissional sem regra: as sessões dele aparecem no relatório com repasse
  "a definir" e um aviso.
- A regra é aplicada **no fechamento do repasse** e o valor fica gravado na
  linha do fechamento; mudar a regra depois não altera fechamentos pagos.

### 6.2 Base do percentual (configuração da clínica)
**Sessão avulsa**: o valor da sessão **na cobrança** — o valor do
procedimento menos a parte dela no desconto da cobrança (desconto da
cobrança rateado entre as sessões na proporção do valor de cada uma). Sessão
tirada da cobrança não tem repasse (decisão do usuário: desconto ou retirada
reduz o repasse junto).

Para sessões cobertas por mensalidade ou pacote, a clínica escolhe:
- **valor do procedimento** da sessão (como se fosse avulsa), ou
- **valor rateado**: pacote ÷ número de sessões do pacote; mensalidade (o
  valor efetivamente cobrado no mês, já proporcional) ÷ sessões que contam
  (finalizadas + faltas cobradas) do mês naquele acordo.
Desconto dado na cobrança da mensalidade ou na parcela do pacote reduz a
base na mesma proporção. Valor fixo ignora a base, mas também só é pago
quando a sessão está paga (6.3).

### 6.3 Quais sessões entram
`realizada` sempre; `faltou` só se a clínica paga repasse de falta **e** a
falta foi cobrada. As demais nunca.

**Só entra no repasse a sessão que a família pagou** (decisão do usuário):
- avulsa: quando a cobrança que contém a sessão está paga por inteiro
  *(chamada do Claude: pagamento parcial não libera sessão nenhuma; a
  cobrança aparece como "aguardando pagamento")*;
- mensalidade: quando a cobrança daquele mês está paga;
- pacote: as sessões são liberadas na ordem, conforme o valor já pago do
  pacote — a sessão k entra quando o pago ≥ k × (valor do pacote ÷ número de
  sessões) *(chamada do Claude: parcelas não correspondem a sessões)*.

O relatório traz as sessões **pagas e ainda não repassadas** até o fim do
período escolhido (inclusive de meses anteriores que só foram pagas agora) e
mostra à parte, só para informação, as sessões do período **aguardando
pagamento da família**. Cobrança estornada depois do repasse pago vira aviso
para o gestor (ajuste negativo no próximo fechamento).

### 6.4 Relatório de atendimentos (fechamento do profissional)
- Filtros: período (padrão: mês anterior), profissional ou todos,
  especialidade.
- Agrupado por profissional; uma linha por sessão: data e hora, paciente,
  procedimento ou acordo (com o valor), "sessão N de M" no pacote,
  especialidade, **valor da clínica**, **valor do profissional**, regra (% ou
  fixo), valor total.
- Totais por especialidade (quantidade e valores), **ajustes** lançados pelo
  gestor (desconto ou acréscimo, com descrição) e **valor a pagar**.
- PDF com logo, período, profissional (nome e registro do conselho, se houver)
  e espaço para assinatura; Excel com as mesmas colunas.
- **Marcar repasse como pago** grava o fechamento (profissional, período,
  linhas e totais). Sessão que já está num fechamento pago não entra em
  outro; o relatório mostra "já pago em dd/mm".

### 6.5 Outros relatórios (só gestor)
Extrato do paciente (sessões × pagamentos, PDF), cobranças em aberto e
vencidas, pacotes/mensalidades acabando, sessões sem acordo. Todos com Excel.

## 7. Ordem de construção

Cada etapa com seu plano e PR(s):
1. **Etapa 1** — configuração das faltas, acordos, geração, baixa, telas de
   cobrança, ficha e família. Migração nova (acordos, itens da cobrança,
   status novos, colunas de pagamento: quem recebeu, estorno, forma ampliada).
2. **Etapa 2** — fechamento de caixa (só leitura sobre `pagamentos`).
3. **Etapa 3** — regras de repasse, base do percentual, relatório de
   atendimentos, fechamentos pagos.
Depois (fora deste documento): pendências no dashboard de gestão, despesas e
resultado do mês, lembrete de cobrança por WhatsApp.

## 8. Restrições

- Valores sempre em centavos (inteiro). Datas de consulta são horário local
  (ver `formatarDataHoraLocal`); "hoje" de Brasília para vencido/pendências.
- PDF pelo mesmo caminho do relatório em PDF que já existe; Excel com a
  biblioteca já usada na importação, se servir.
- Nada de RLS nem criptografia de campo (regra 2 do projeto).
- Toda mudança de schema com `.sql` em `backend/migracoes/` e `migrar_*.py`,
  segura para rodar de novo; avisar o usuário do passo em produção.
- Cobrança, baixa, estorno e fechamento de repasse vão para a auditoria.
- **Nenhuma clínica usa a cobrança do PandaUp hoje** (informado pelo usuário
  em 07/11/2026): a migração pode refazer o CHECK de status de `cobrancas` e
  de forma de `pagamentos` sem preencher dados antigos; ainda assim deve
  rodar sem erro se houver linhas (ex.: demonstração).
- A regra existente "dois canais de cobrança não se sobrepõem" é da cobrança
  **da plataforma** (Plataforma → Clínica) e não muda aqui.

## 9. Deixado para o construtor

Nomes de tabelas e colunas, formato da migração de `cobrancas` (status novos
e itens), layout das telas dentro do padrão atual (cartões, `kpiCard`,
`tabela`), como mostrar "sessão N de M" na agenda, paginação das listas, e o
texto exato dos avisos.
