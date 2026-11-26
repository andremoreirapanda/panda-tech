# IA fase 1 — base comum + ditado por voz nos campos de prontuário

Data: 25/11/2026. Conversa com o usuário no Claude Code (decisões marcadas como **do usuário**;
o que foi escolhido por mim está marcado como **(decisão do construtor)**).

## 1. Intenção

O PandaUp vai ter recursos de IA nos planos superiores. O primeiro é ajudar o profissional a preencher
o prontuário **falando em vez de digitar**: ele aperta 🎤 ao lado de um campo, fala, e o texto transcrito
entra no campo para ele revisar e salvar. Economiza tempo no fim da sessão e é o recurso que justifica o
plano superior.

Esta fase também cria a **base comum de IA** que as próximas vão reaproveitar (próxima: o agente de
suporte do PandaUp para as clínicas, com Claude; depois, relatório de evolução, resumo antes da sessão etc.).

## 2. Decisões do usuário

- **Cobrança**: a conta com o fornecedor é do PandaUp (não chave da clínica). A IA entra nos planos com
  **cota mensal**; quando a clínica precisa de mais, o **Admin libera minutos extras manualmente**
  (compra automática de pacotes fica para depois).
- **Cota por plano, configurada pelo Admin** na tela de Planos.
- **Microfone por campo** (não um ditado único que a IA distribui).
- **Telas**: Atender, Diário (Novo Diário e Editar registro) e Ficha Clínica. A anamnese não existe no
  PandaUp ainda; quando for criada, já nasce com o microfone.
- **Áudio apagado** depois de transcrever.
- **Fornecedor**: Whisper/OpenAI para transcrição; Claude para os recursos de texto (fases seguintes).
- **Caminho do áudio**: navegador grava → envia ao servidor do PandaUp → servidor confere a cota e chama
  a OpenAI → devolve o texto (abordagem 1, abaixo).
- O texto transcrito **entra na caixa de texto e pode ser editado** antes de salvar; nada é gravado
  até o Salvar de sempre.
- O agente de suporte (fase seguinte) será para **todos os planos, sem gastar a cota**.

## 3. Objetivos, não objetivos, antiobjetivos

**Objetivos**
- Botão 🎤 em cada campo de texto livre das três telas, para gestor e profissional de clínica com o
  módulo "Assistente de IA".
- Cota mensal de minutos por plano + minutos extras por clínica, com consumo registrado.
- Admin vê o consumo de cada clínica e o custo estimado; o gestor vê quanto da cota a clínica já usou.

**Não objetivos (fase 1)**
- Agente de suporte, relatórios, resumos, qualquer uso de Claude.
- Ditado em tempo real (texto aparecendo enquanto fala).
- Compra automática de pacotes de minutos.
- Ditado em outras telas (missões, objetivos, chat, anamnese).

**Antiobjetivos (seria um fracasso mesmo funcionando)**
- Qualquer texto salvo no prontuário sem o profissional ver e clicar em Salvar.
- O áudio ficar guardado em algum lugar (disco, Storage, banco, log).
- A chave da OpenAI chegar ao navegador.
- A clínica gastar além da cota, ou o PandaUp pagar por uma transcrição que a clínica não tinha cota para fazer.
- O texto transcrito aparecer em log, auditoria ou mensagem de erro.

## 4. Abordagens consideradas

1. **Pelo servidor do PandaUp (escolhida pelo usuário).** O navegador grava; ao parar, envia o áudio
   ao Flask, que confere permissão e cota, chama a OpenAI e devolve o texto. O áudio só existe na memória
   do pedido. Chave só no servidor; cota conferida antes de gastar. Contra: o texto só aparece depois de
   parar de falar (~10–20 s para 5 min).
2. **Navegador direto na OpenAI, em tempo real** (chave temporária por sessão). Texto aparecendo enquanto
   fala, mas bem mais complexo: CSP, conexão contínua, cota difícil de medir, internet instável derruba o
   ditado. Fica como possível melhoria, reaproveitando o mesmo botão.
3. **Áudio no Storage e transcrição depois.** Contraria "não guardar o áudio" e acrescenta um passo que
   pode falhar.
4. (Descartada antes) **Reconhecimento de voz do navegador** (Web Speech API): grátis, mas instável no
   iPhone, sem contrato e manda o áudio ao Google sem controle.

## 5. Desenho

### 5.1 Módulo e quem pode ditar

- O módulo `ia` ("Assistente de IA", hoje `"oculto": True` em `modulos_service.MODULOS_OPCIONAIS`) deixa
  de ser oculto. Descrição nova (decisão do construtor, o usuário pode reescrever): "Ditado por voz nos
  campos do prontuário (Atender, Diário e Ficha Clínica): o profissional fala e o texto aparece no campo
  para revisar. Inclui uma cota mensal de minutos." Vale tudo o que já existe para módulos: entra em plano
  (`planos_modulos`, com herança) ou como extra da clínica (`modulos_clinica.liberado_admin`).
- Pode ditar: **gestor e profissional** da clínica com o módulo ativo
  (`modulo_ativo_para_clinica(org, plano, "ia")`). Secretária não (não edita nenhum desses campos);
  responsável e criança nunca. Admin da plataforma: não (não tem clínica) (decisão do construtor).
- O botão só aparece com o módulo ativo. Com o módulo ativo e **0 minutos restantes** (cota zerada ou
  acabou), o botão aparece apagado, com a dica "Os minutos de ditado deste mês acabaram. Fale com o
  PandaUp para liberar mais." (decisão do construtor: mostra que o recurso existe). O `/auth/me` precisa expor o necessário para a tela saber
  (o builder confere como as outras telas sabem dos módulos hoje e segue o mesmo padrão).

### 5.2 Cota

- **Plano**: coluna nova `planos.ia_minutos_mes` (INTEGER, NULL ou 0 = sem minutos). Editada no
  formulário de plano do Admin ("Minutos de ditado por mês"), só faz sentido com o módulo `ia` marcado
  (no plano ou herdado). **Herança** (decisão do construtor): se o plano não define (NULL), vale o da
  base, recursivamente, como os módulos. Entra na lista automática de recursos do plano
  (`admin_bp._recursos_automaticos`): "Ditado por voz: N minutos por mês".
- **Minutos extras por clínica**: no detalhe da clínica (Admin), "Liberar minutos de ditado" com
  quantidade e motivo. **Valem só no mês em que foram liberados** (decisão do construtor: é o equivalente
  manual de "comprar um pacote"). Tabela `ia_creditos` (organizacao_id, mes 'AAAA-MM', minutos, motivo,
  criado_por, criado_em). Mostra o histórico de liberações da clínica.
- **Clínica com o módulo como extra e plano sem minutos**: cota do plano = 0; o Admin libera minutos
  extras a cada mês. (Decisão do construtor; ver seção 7, ponto para o usuário conferir.)
- **Mês** = mês civil no horário de Brasília (`ausencias_service.agora_brasilia_iso`/`hoje_brasilia`).
- **Cota do mês** = minutos do plano + soma dos créditos do mês. **Usado** = soma dos segundos
  transcritos no mês. **Restante** = cota − usado.
- **Conferência antes de gastar**: o pedido chega com a duração medida pelo navegador; se
  `restante < duração estimada` → 402/409 com mensagem "Os minutos de ditado deste mês acabaram"
  (ou "Este áudio passa dos minutos que restam (N min)"). Sem chamada à OpenAI.
- **Cobrança da cota** (decisão do construtor, depois da revisão): usa a duração devolvida pela OpenAI
  quando o modelo devolve segundos; senão, a duração medida pelo navegador **conferida pelo tamanho do
  arquivo** (se o tamanho indicar um áudio bem mais longo do que o declarado, vale a estimativa pelo
  tamanho, com teto de 300 s). Sem biblioteca nova para ler cabeçalho de áudio e sem ffmpeg. Qualidade
  em português pesa mais na escolha do modelo do que medir a duração no servidor. Arredondada para
  cima, em segundos. Uma gravação pode deixar o "usado" passar um pouco da cota (o último áudio do mês); aceito.
- **Concorrência**: dois profissionais ditando ao mesmo tempo podem passar um pouco da cota; aceito
  (diferença de poucos minutos), sem trava.

### 5.3 Registro de uso

Tabela `ia_uso`: id, organizacao_id, usuario_id, recurso (`ditado` nesta fase; `suporte` etc. depois),
segundos (INTEGER), modelo (TEXT), custo_estimado_micro_usd (INTEGER, calculado com o preço por minuto
de uma constante no `ia_service`), sucesso (0/1), criado_em. **Nunca** guarda áudio, texto, paciente
nem campo. Falha da OpenAI grava `sucesso = 0` com 0 segundos (para o Admin ver falhas) e não gasta cota.

### 5.4 Backend

- **`backend/ia_service.py`** — único ponto que fala com fornecedores de IA (como o
  `armazenamento_service.py` para o Storage). Nesta fase: `transcrever(audio_bytes, mime, nome_arquivo)`
  → `{texto, segundos}`; via `requests` (multipart) para a API de transcrição da OpenAI, `language=pt`,
  timeout ~90 s, um `prompt` com vocabulário clínico em português (fono, TO, psicopedagogia, psicologia;
  constante no serviço). **Sem nome de paciente** no prompt (minimização; decisão do construtor). Erro
  do fornecedor → exceção própria que a rota transforma em 502 amigável ("Não foi possível transcrever
  agora. Tente de novo em instantes."). Funções de cota (`cota_do_mes`, `uso_do_mes`, `restante`) e
  `registrar_uso`.
  - **Modelo**: o builder escolhe entre `whisper-1` e `gpt-4o-mini-transcribe`/`gpt-4o-transcribe`
    conferindo a documentação atual (preço, qualidade em pt-BR, se devolve a duração). Fica numa
    variável opcional `OPENAI_MODELO_TRANSCRICAO` com padrão no código.
- **Variáveis de ambiente** (cPanel → Setup Python App, como as do Supabase): `OPENAI_API_KEY`
  (obrigatória para o ditado funcionar), `OPENAI_MODELO_TRANSCRICAO` (opcional). Sem a chave, o botão
  não aparece (o `/auth/me` ou a config diz que o ditado está indisponível) e a rota responde 503.
- **Rotas** (blueprint novo `ia_bp.py`, prefixo `/api/ia`):
  - `GET /api/ia/ditado/config` → `{disponivel, minutos_cota, minutos_usados, minutos_restantes,
    limite_segundos}` para gestor/profissional com o módulo (403 sem módulo).
  - `POST /api/ia/ditado` — multipart com o arquivo de áudio e `duracao_segundos` (do navegador).
    Confere: papel, módulo, chave configurada, tamanho (≤ 15 MB, decisão do construtor), tipo
    (assinatura de áudio webm/ogg/mp4/m4a/mpeg/wav — reaproveitar `validacao_arquivo` se servir),
    duração ≤ 300 s (+ folga), cota. Chama `ia_service.transcrever`, registra o uso e devolve
    `{texto, minutos_restantes}`. O áudio nunca é gravado. Limite por usuário: no máximo 1 ditado em
    andamento e um rate limit simples (ex.: 30 por 10 min) contra abuso (decisão do construtor).
  - Admin: `GET /api/admin/ia/uso?mes=AAAA-MM` (por clínica: cota, usado, ditados, falhas, custo
    estimado; totais), `GET/POST /api/admin/clinicas/<id>/ia/creditos`.
  - Plano: `ia_minutos_mes` entra no criar/editar plano existente (validação: inteiro 0–100.000 ou vazio).
- **Tamanho do pedido**: conferir se o Flask/Passenger tem `MAX_CONTENT_LENGTH` ou limite do LiteSpeed
  que barre 15 MB; se necessário, limite só nessa rota.
- **Migração**: `backend/migracoes/migracao_ia_ditado.sql` + `backend/migrar_ia_ditado.py`
  (coluna `planos.ia_minutos_mes`, tabelas `ia_uso` e `ia_creditos`, índices por organização+data);
  idempotente. Antes da migração, nada quebra: o ditado se comporta como indisponível.
- **Ninguém ganha o ditado automaticamente no deploy (decisão do usuário)**: o `ia` estava em
  `planos_padrao.MODULOS_PADRAO["pro"]` e o módulo oculto "volta sozinho" ao deixar de ser oculto. A
  migração **apaga as linhas `modulo_codigo = 'ia'` de `planos_modulos`** (e de `modulos_clinica`, onde
  hoje não há nenhuma em produção) e o `ia` sai do `MODULOS_PADRAO`. O usuário liga o módulo plano a
  plano pela tela de Planos (testando antes na homologação), definindo os minutos. **A migração tem de
  rodar antes do deploy** (senão as clínicas Pro veem o módulo entre o deploy e a migração, com 0
  minutos — o botão apagado).

### 5.5 Frente (navegador)

- **Componente único** `frontend/js/ditado.js`: `ligarDitado(textarea, opcoes)` acrescenta o botão 🎤 ao
  rótulo/canto do campo. Reaproveita a lógica de gravação do Pandoo (`views/pandoo.js`, ~linha 620:
  `getUserMedia`, `MediaRecorder`, webm/opus quando houver, senão o padrão do aparelho — mp4 no iPhone).
  Pode extrair a parte comum para um arquivo compartilhado, sem mudar o comportamento do Pandoo.
- **Estados do botão**:
  ```
  [🎤]                      parado — dica "Ditar (N min restantes)"
  [⏹ 0:42 ●]                gravando — tempo correndo; aos 4:30 aviso "faltam 30 s"; para sozinho em 5:00
  [⏳ Transcrevendo…]        enviando/aguardando — campo travado para edição só nesse intervalo
  [🎤]  + texto inserido     pronto — texto entra NA POSIÇÃO DO CURSOR (ou no fim), com espaço/quebra
                             de linha se preciso; campo recebe foco com o trecho novo selecionado
  ```
  Erros em aviso curto embaixo do campo: sem permissão do microfone (com dica de como liberar no
  celular), navegador sem gravação, cota acabou, falha na transcrição ("Tente de novo" reenvia o mesmo
  áudio guardado só na memória da página até dar certo ou o usuário desistir).
- **Só um campo grava por vez** na página; começar outro para o anterior? Decisão do construtor:
  **bloqueia** o segundo botão enquanto um grava ou transcreve.
- Fechar o pop-up ou sair da tela durante a gravação: para e descarta (sem enviar). Durante a
  transcrição: o texto que chegar depois é descartado.
- O texto inserido dispara o evento `input` no campo (para o rascunho automático de `modais.js` e para
  qualquer contador/aviso de alteração não salva funcionarem).
- **Onde liga** (11 campos): Atender (`#at-descricao`, `#at-observacao`, `#at-mensagem`); Diário
  (`#di-evolucao`, `#di-mensagem`, `#ed-evolucao`, `#ed-mensagem`); Ficha Clínica (`#fc-diagnostico`,
  `#fc-alergias`, `#fc-medicamentos`, `#fc-externos`, `#fc-observacoes`, `#fc-observacoes-equipe`).
  O builder confere se o Diário/Atender tem outros campos de texto livre que valham o mesmo.
- **Gestor** vê o consumo em Configurações ou Módulos (o builder escolhe o lugar mais natural):
  "🎤 Ditado por voz: 120 de 300 minutos usados em novembro".
- **Admin**:
  - Planos: campo "Minutos de ditado por mês" (habilitado quando o módulo IA está marcado/herdado).
  - Detalhe da clínica: cartão "Ditado por voz" — cota do mês, usado, botão "Liberar minutos extras"
    (quantidade + motivo) e histórico.
  - Tela nova ou cartão "Consumo de IA" (por mês): tabela por clínica (cota, usado, % , ditados, falhas,
    custo estimado em US$) e total do mês.
- Mensagens sempre com o nome "PandaUp" quando citarem o app (teste de varredura existente).

### 5.6 Privacidade (LGPD)

- Áudio: só na memória do pedido; não vai para disco, Storage, banco, log nem auditoria. O texto
  transcrito também não é registrado no servidor (só volta ao navegador).
- Ao fornecedor vai apenas o áudio e um vocabulário genérico; nenhum dado de cadastro.
- Política da OpenAI para API: dados não são usados para treino; retenção para abuso por até 30 dias,
  salvo "zero data retention" aprovado. **Fora do código**: o usuário pede a retenção zero à OpenAI e
  atualiza termos de uso/política de privacidade citando o uso de IA e a transferência internacional.
- Primeiro uso do 🎤 por usuário: aviso curto, uma vez (guardado no `localStorage`): "O áudio é
  enviado para transcrição automática e apagado em seguida. Revise o texto antes de salvar."
  (decisão do construtor).

## 6. Testes (o builder detalha no plano)

- Backend com o fornecedor simulado (monkeypatch em `ia_service`): permissão por papel e módulo,
  clínica sem chave → 503, cota (plano, herança, créditos do mês, mês de Brasília, acabou → sem chamada
  ao fornecedor), falha do fornecedor não gasta cota, tamanho/tipo/duração, áudio não persistido
  (nenhuma tabela/arquivo novo com conteúdo), rotas do Admin, `ia_minutos_mes` no plano, recursos
  automáticos do plano.
- Front (Node): funções puras de inserir texto na posição do cursor, formatação de tempo/minutos.
- Varredura no navegador com Playwright: gravação simulada (fake media stream do Chromium) nas três
  telas, celular e computador.

## 7. Para o usuário conferir (decisões do construtor com efeito no produto)

1. Minutos extras valem **só no mês em que foram liberados**.
2. Clínica com o IA como **extra** recebe 0 minutos do plano e depende de minutos liberados todo mês.
3. Plano que não define minutos **herda** os da base.
4. Duração máxima de **5 min** por gravação; o próprio botão para sozinho.
5. **Sem o nome do paciente** no pedido ao fornecedor.

## 8. O que fica para o builder

Modelo de transcrição exato e preço por minuto (documentação atual), extração do gravador do Pandoo,
lugar do consumo para o gestor, layout exato dos cartões do Admin, nomes internos, rate limit exato.
Passos manuais em produção (migração antes do deploy, `OPENAI_API_KEY` no cPanel, restart) vão no
CLAUDE.md ao final.
