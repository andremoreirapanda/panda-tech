# Pandoo — Cruzadinha Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Novo modelo `cruzadinha` no Pandoo: o profissional cadastra de 2 a 10 figuras com palavra e voz, o editor monta e guarda a arrumação, e a criança preenche pelo teclado, tocando em letras ou escolhendo figuras.

**Architecture:** Backend valida conteúdo, regras e a `grade` guardada (`pandoo_service.py`, sem migração: `pandoo_jogos.modelo` é TEXT livre). As regras puras do front ficam num arquivo novo, `frontend/js/pandoo/cruzadinha_core.js` (gerador da grade, numeração, estado da partida), testado em Node. O jogo (`jogos/cruzadinha.js`) só desenha e chama essas funções e o palco. O editor (`views/pandoo.js`) ganha o painel de regras, os contadores de limite e a miniatura da grade.

**Tech Stack:** Flask/Python 3.11 + pytest; JS puro (globais no navegador, `module.exports` no Node) + `node --test`; Playwright para fumaça.

**Spec:** `docs/superpowers/specs/2026-10-29-pandoo-cruzadinha-design.md`. Prévia aprovada: artifact "Prévia Cruzadinha Pandoo" (v3).

## Global Constraints

- Comandos (de `backend/`): `PYTHONUTF8=1 ENCANTO_SECRET=teste-local FLASK_DEBUG=1 venv/Scripts/python.exe -m pytest -q`; front (da raiz): `node --test frontend/tests/*.test.js`.
- 2 a 10 figuras na cruzadinha (os outros modelos continuam 2 a 24).
- Palavra: só letras (com acento/ç), hífen e espaço; espaços repetidos viram um; 2 a 12 letras sem contar hífen/espaço; não começa nem termina com hífen/espaço; sem repetir (sem acento/caixa).
- Grade guardada em `regras.grade = {linhas, colunas, palavras: [{item_id, linha, coluna, direcao: "h"|"v"}]}`, no máximo 15×15.
- `REGRAS_PADRAO["cruzadinha"] = {"formas": ["teclado", "letras"], "primeira_letra": false, "som": true, "voz": true, "voz_acertar": true, "grade": null}`; `formas` sempre na ordem `teclado, letras, figuras`.
- Resultado por palavra: "conseguiu" com 0 erros, senão "treinar". Só palavras feitas vão para `palco.registrar`.
- Textos fixos da spec, literais: mensagens de erro da seção 1; "A arrumação da cruzadinha está desatualizada. Toque em 'Montar a cruzadinha' de novo."; "Não deu para montar a cruzadinha com essas palavras. Use palavras menores ou tire alguma figura."; "A palavra X não cruza com nenhuma outra; ela vai aparecer separada."; `avisoSemRodada` "Você ainda não completou nenhuma palavra. Complete pelo menos uma para liberar a missão 🧩"; "Máximo de 10 palavras"; "Use até 12 letras"; "Use só letras, hífen e espaço".
- Nome visível "PandaUp" (teste de varredura `test_nome_pandaup.py` / `nome_pandaup.test.js`); nunca "Panda Tech" em texto novo.
- CSP: nada de `blob:`; sem bibliotecas novas.
- Cada commit termina com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Branch `pandoo-cruzadinha`.

## Review Focus

1. Palavra com acento no cruzamento ("ÉGUA" × "ELEFANTE"): grade válida no backend e no front, e a criança digita "E" sem acento → aceita. (Teste no Task 1 e Task 3.)
2. Teclado do Android que manda o texto inteiro ou com autocorreção no `input` (ex.: valor "Gato" de uma vez): cada letra entra em sequência, e caracteres não-letra são ignorados. (Teste Node no Task 3 via `letrasDoInput`.)
3. Editar a palavra de uma figura depois de salvar: a grade antiga deixa de valer e o editor remonta sozinho antes de salvar; salvar com grade velha dá o erro "desatualizada" no backend. (Testes Task 1 e Task 5.)
4. Jogo com 2 figuras sem letra em comum: as duas ficam soltas, sem encostar, e o jogo é jogável. (Teste Task 2.)
5. Trocar de modelo de um jogo com 12 figuras para Cruzadinha: contador vermelho e salvar bloqueado, sem perder figuras. (Fumaça Playwright no Task 6.)

---

### Task 1: Backend — validação da Cruzadinha

**Files:**
- Modify: `backend/pandoo_service.py`
- Create: `backend/tests/test_pandoo_cruzadinha.py`

**Interfaces:**
- Produces: `MODELOS` com `"cruzadinha"`; `LIMITES_ITENS = {"cruzadinha": (2, 10)}` (padrão `(MIN_ITENS, MAX_ITENS)`); `MAX_LETRAS_CRUZADINHA = 12`; `MAX_GRADE = 15`; `casas_da_palavra(texto) -> list[tuple[str, bool]]` (letra normalizada em maiúscula ou "-"/" ", `fixa`); `validar_jogo` inalterado na assinatura.

- [ ] **Step 1: Write the failing tests** em `tests/test_pandoo_cruzadinha.py`, reaproveitando `_c`/`_it`/`PNG` como em `test_pandoo_memoria.py` e um helper `_grade(*palavras, linhas, colunas)`. Use a grade da prévia (CASA v (0,1), GATO h (1,0), OVO v (1,3), SAPO h (3,0), SOL v (3,0), LUA h (5,0); 6×4).

```python
def test_regras_padrao_e_formas():
    _, r = ps.validar_jogo("cruzadinha", _c(ITENS), {"grade": GRADE}, None)
    assert r == {"formas": ["teclado", "letras"], "primeira_letra": False, "som": True,
                 "voz": True, "voz_acertar": True, "grade": GRADE}
    for ruim in ([], ["xx"], "teclado", None):
        _, r = ps.validar_jogo("cruzadinha", _c(ITENS), {"formas": ruim, "grade": GRADE}, None)
        assert r["formas"] == ["teclado", "letras"]
    _, r = ps.validar_jogo("cruzadinha", _c(ITENS), {"formas": ["figuras", "teclado", "figuras"], "grade": GRADE}, None)
    assert r["formas"] == ["teclado", "figuras"]

def test_limite_de_figuras():  # 1 e 11 → "A cruzadinha precisa ter de 2 a 10 figuras."
def test_roleta_continua_ate_24():  # 24 itens na roleta passam
def test_imagem_e_palavra_obrigatorias():  # "a cruzadinha precisa de uma imagem…", "…precisa da palavra de cada figura."
def test_caracteres_e_tamanho():
    # "Gato1", "ga.to" → "use só letras, hífen e espaço"; "-gato", "gato " (após strip ok), "a  b" vira "a b"
    # "A" (1 letra) e 13 letras → "precisa ter de 2 a 12 letras"; "guarda-chuva" (11 letras) passa
def test_palavra_repetida():  # "Robô" e " robo " → "Item 2: a palavra repete a de outra figura."
def test_nao_guarda_distratores():
def test_grade_invalida():
    # cada caso → match "arrumação da cruzadinha está desatualizada":
    # grade None; item faltando; item repetido; item_id desconhecido; direcao "d";
    # fora dos limites; linhas/colunas > 15; letras diferentes no cruzamento;
    # cruzamento num hífen; duas palavras na mesma direção dividindo casa
def test_acento_no_cruzamento_vale():  # "ÉGUA" h e "ELA" v cruzando no E → passa
def test_rotas_salvam_e_registram_partida(client, db_ctx):
    # como test_pandoo_jogos.py: _liberar, POST /api/pandoo/jogos modelo "cruzadinha" → 201,
    # GET devolve regras["grade"] igual; POST /api/pandoo/resultados com 2 detalhes → 201
```

- [ ] **Step 2: Run** `venv/Scripts/python.exe -m pytest -q tests/test_pandoo_cruzadinha.py` → FAIL ("Esse modelo de jogo ainda não existe").

- [ ] **Step 3: Implement** em `pandoo_service.py`:
  - `MODELOS`, `REGRAS_PADRAO`, `NOME_MODELO`, `LIMITES_ITENS`; `validar_jogo` usa `LIMITES_ITENS.get(modelo, (MIN_ITENS, MAX_ITENS))` e, para cruzadinha, a mensagem "A cruzadinha precisa ter de 2 a 10 figuras.".
  - `_regras("cruzadinha", …)`: `formas` filtrada/ordenada; booleanos; `grade` copiada como veio (conferida depois, com os itens).
  - Exigir imagem (`exigir_imagem` inclui cruzadinha); palavra: colapsar espaços (`" ".join(texto.split())`), checar com `re.fullmatch(r"[A-Z]+([ -][A-Z]+)*", _sem_acento_maiuscula(texto))`, contar letras, repetição com `_normalizar_palavra`. Guardar o texto colapsado.
  - `_checar_grade(grade, itens)` levanta `ErroPandoo` com a mensagem "desatualizada" para qualquer falha listada no teste; monta um dicionário `(linha, coluna) -> (letra, fixa, direcoes)` a partir de `casas_da_palavra`.

- [ ] **Step 4: Run** o arquivo novo e depois `tests/test_pandoo_*.py` → PASS.

- [ ] **Step 5: Commit** `git commit -m "Pandoo: validação da Cruzadinha no backend"`.

---

### Task 2: Front — palavras, grade e gerador (`cruzadinha_core.js`)

**Files:**
- Create: `frontend/js/pandoo/cruzadinha_core.js`
- Modify: `frontend/js/pandoo/pandoo_core.js` (limites por modelo, `REGRAS_PADRAO_PANDOO.cruzadinha`, delegação em `problemasDoConteudo`)
- Create: `frontend/tests/pandoo_cruzadinha.test.js`

**Interfaces:**
- Consumes: `normalizarPalavra` (pandoo_core).
- Produces (globais + `module.exports`):
  - `LIMITES_CRUZADINHA = {minItens: 2, maxItens: 10, maxLetras: 12, maxGrade: 15}`
  - `limitesDoModelo(modelo) -> {minItens, maxItens}` (em pandoo_core; `PANDOO_LIMITES` para os outros)
  - `casasDaPalavra(texto) -> [{letra, fixa}]` (letra maiúscula sem acento; hífen `{letra:"-", fixa:true}`, espaço `{letra:"", fixa:true}`)
  - `contarLetras(texto) -> number`
  - `problemaDaPalavraCruzadinha(texto) -> string|null` ("Use só letras, hífen e espaço" / "Use até 12 letras" / "Use pelo menos 2 letras" / null)
  - `palavrasDaGrade(grade, itens) -> [{item_id, item, direcao, linha, coluna, casas: [{chave:"l,c", letra, fixa}]}]`
  - `conferirGrade(grade, itens) -> boolean` (mesmas regras do backend)
  - `montarGradeCruzadinha(itens, aleatorio = Math.random) -> {grade, soltas: [item_id]} | null`
  - `numerarGrade(grade, itens) -> {[item_id]: number}`
  - `problemasCruzadinha(conteudo, regras) -> string[]` ("Figura N: …"; grade inválida → "Não deu para montar a cruzadinha com essas palavras. Use palavras menores ou tire alguma figura.")
- `index.html`: `<script src="/js/pandoo/cruzadinha_core.js">` logo depois de `pandoo_core.js`.

- [ ] **Step 1: Write the failing tests**

```js
test("casas da palavra", () => {
  assert.deepEqual(c.casasDaPalavra("Pé-de-moça").map(x => x.letra).join(""), "PE-DE-MOCA");
  assert.equal(c.casasDaPalavra("arco íris")[4].fixa, true);
  assert.equal(c.contarLetras("guarda-chuva"), 11);
});
test("problema da palavra", () => { /* "gato1", "BORBOLETINHAS", "a", "-gato" → mensagens; "guarda-chuva" → null */ });
test("grade gerada sempre confere", () => {
  for (const palavras of [["gato","pato"], SEIS_DA_PREVIA, DEZ_ATE_8_LETRAS]) for (let s = 0; s < 20; s++) {
    const r = c.montarGradeCruzadinha(itens(palavras), semente(s));
    assert.ok(r && c.conferirGrade(r.grade, itens(palavras)));
    assert.ok(r.grade.linhas <= 15 && r.grade.colunas <= 15);
  }
});
test("palavras sem letra em comum ficam soltas e não encostam", () => {
  const r = c.montarGradeCruzadinha(itens(["sol", "uva"]), semente(1));
  assert.equal(r.soltas.length, 1);   // uma é a base; a outra fica solta
  // nenhuma casa de uma palavra é vizinha (8 direções) de casa da outra
});
test("nenhuma palavra encosta de lado em paralela", () => { /* varre a grade dos DEZ */ });
test("impossível em 15×15 → null", () => { /* 10 palavras de 12 letras sem letra em comum */ });
test("numeração em ordem de leitura; começo compartilhado tem o mesmo número", () => {
  assert.deepEqual(c.numerarGrade(GRADE_PREVIA, ITENS_PREVIA), {casa:1, gato:2, ovo:3, sapo:4, sol:4, lua:5});
});
test("problemasCruzadinha", () => { /* 11 figuras, sem imagem, palavra ruim, repetida, grade velha */ });
test("limitesDoModelo", () => { assert.equal(p.limitesDoModelo("cruzadinha").maxItens, 10); assert.equal(p.limitesDoModelo("quiz").maxItens, 24); });
```

`semente(s)` = gerador linear simples no próprio teste, para reproduzir.

- [ ] **Step 2: Run** `node --test frontend/tests/pandoo_cruzadinha.test.js` → FAIL (módulo não existe).

- [ ] **Step 3: Implement.** Gerador (o algoritmo não sai da assinatura; seguir isto):

```
melhor = null
repetir 150 tentativas:
  ordem = itens por nº de letras desc (empate embaralhado com `aleatorio`)
  coloca ordem[0] deitada em (0,0)
  para cada próxima palavra:
    candidatas = todas as posições que cruzam ≥1 letra igual (não fixa) já colocada
                 e passam em podeColocar()
    se houver: escolhe a de menor (área da caixa, |linhas−colunas|), empate pelo aleatorio
    senão: marca como solta
  soltas: coloca cada uma deitada na primeira posição livre abaixo/à direita da caixa
          atual, com uma casa vazia de margem em volta (podeColocar com vizinhança 8)
  normaliza para começar em (0,0); pontua (nº soltas, área, |linhas−colunas|)
  guarda a melhor que caiba em 15×15
devolve melhor ou null
podeColocar: dentro dos limites ±; casa ocupada só se mesma letra e não fixa e
  direção diferente; casa antes do começo e depois do fim vazias; cada casa nova
  sem vizinho lateral (perpendicular) ocupado; pelo menos uma casa nova
```

  Em `pandoo_core.js`: `REGRAS_PADRAO_PANDOO.cruzadinha` (espelho), `limitesDoModelo`, `problemasDoConteudo` usa `limitesDoModelo(modelo)` na mensagem de quantidade e, para `cruzadinha`, faz `problemas.push(...problemasCruzadinha(conteudo, regras))` quando `typeof problemasCruzadinha === "function"` (no Node, exige `require("./cruzadinha_core.js")` dentro do `if (typeof module …)`); `modelo === "cruzadinha"` também entra na checagem de imagem.

- [ ] **Step 4: Run** `node --test frontend/tests/*.test.js` → PASS (os antigos continuam passando).

- [ ] **Step 5: Commit** `"Pandoo: palavras, grade e gerador da Cruzadinha"`.

---

### Task 3: Front — estado da partida (`cruzadinha_core.js`)

**Files:**
- Modify: `frontend/js/pandoo/cruzadinha_core.js`
- Modify: `frontend/tests/pandoo_cruzadinha.test.js`

**Interfaces:**
- Consumes: `palavrasDaGrade` (Task 2).
- Produces (funções puras; o estado nunca é mutado, sempre devolvido novo):
  - `estadoInicialCruzadinha(palavras) -> {letras: {chave: letra}, travadas: {chave: true}, erros: {item_id: n}, feitas: [item_id]}` — casas fixas já entram em `travadas`, com a letra fixa em `letras`.
  - `palavraAoTocar(palavras, estado, escolhida, chave, ultimaChave) -> item_id|null` (regra da spec seção 2; `ultimaChave` = casa tocada antes, para a troca no toque repetido).
  - `primeiraCasaAberta(palavra, estado) -> chave|null`
  - `colocarLetraCruzadinha(palavras, estado, escolhida, chave, letra) -> {estado, proxima, feitas: [{item_id, resultado}], errou: boolean, limpar: [chave]}` — confere a escolhida se ficou completa (errada: soma erro, `limpar` = casas não travadas com letra diferente, já tiradas do estado novo); confere também cruzadas completas **certas** (feitas); cruzada completa errada fica como está, sem erro.
  - `apagarLetraCruzadinha(palavras, estado, escolhida, chave) -> {estado, ativa}`
  - `registrarErroCruzadinha(estado, item_id) -> estado` (letra errada no banco, figura errada)
  - `escreverPalavraCruzadinha(palavras, estado, item_id) -> {estado, feitas}` (forma figuras: preenche e trava; resultado pelos erros; inclui cruzadas que ficaram certas)
  - `limparSoltasCruzadinha(estado) -> estado` (troca de forma)
  - `letrasDoInput(valor) -> string[]` (normaliza e fica só com A–Z)
  - `bancoDeLetras(palavra, estado, aleatorio) -> string[]` (letras das casas não travadas + 2 de fora da palavra)
  - `opcoesFigurasCruzadinha(item_id, palavras, estado, aleatorio) -> [item]` (3, ou 2 com 2 figuras; prefere não feitas)
  - `resultadoDaPalavra(estado, item_id) -> "conseguiu"|"treinar"`
  - `cruzadinhaTerminou(palavras, estado) -> boolean`

- [ ] **Step 1: Write the failing tests** (grade da prévia):

```js
test("tocar no número escolhe a palavra que começa nele (caso do usuário)", () => {
  assert.equal(c.palavraAoTocar(P, E0, "gato", "1,3", null), "ovo");
});
test("começo compartilhado alterna a cada toque", () => {
  assert.equal(c.palavraAoTocar(P, E0, "sapo", "3,0", "3,0"), "sol");
  assert.equal(c.palavraAoTocar(P, E0, "sol", "3,0", "3,0"), "sapo");
});
test("casa de outra palavra aberta escolhe essa palavra", () => { /* gato escolhida, tocar "2,1" (meio de CASA) → "casa" */ });
test("casa de palavra feita: escolhe a cruzada aberta ou null", () => {});
test("letra certa avança e palavra completa vira feita com conseguiu", () => {});
test("palavra errada limpa só as erradas e soma erro → treinar", () => {
  // digitar G,A,X,O em gato → errou, limpar ["1,2"], letras de G,A,O ficam; depois T → feita "treinar"
});
test("letra que completa a cruzada certa faz a cruzada; errada não conta erro", () => {});
test("acento: É digitado vale E", () => { assert.deepEqual(c.letrasDoInput("é"), ["E"]); });
test("input do Android com várias letras e lixo", () => { assert.deepEqual(c.letrasDoInput("Ga to!1"), ["G","A","T","O"]); });
test("hífen é casa fixa e o cursor pula", () => {});
test("banco de letras: faltantes + 2 de fora", () => {});
test("opções de figura: a certa + 2, só 2 com 2 figuras", () => {});
test("trocar de forma limpa as soltas e mantém as feitas", () => {});
test("terminou quando todas feitas", () => {});
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** as funções acima.
- [ ] **Step 4: Run** `node --test frontend/tests/*.test.js` → PASS.
- [ ] **Step 5: Commit** `"Pandoo: estado da partida da Cruzadinha"`.

---

### Task 4: O jogo no palco (`jogos/cruzadinha.js` + CSS)

**Files:**
- Create: `frontend/js/pandoo/jogos/cruzadinha.js`
- Modify: `frontend/css/pandoo.css` (prefixo `pdc-`)
- Modify: `frontend/index.html` (script depois de `memoria.js`)

**Interfaces:**
- Consumes: Tasks 2–3; palco (`area`, `registrar(item, resultado, {comemorar:true})`, `atualizarPlacar`, `falarItem`, `efeito("treinar")`, `finalizar`, `aoEncerrar`, `encerrado`); `PandooSom.falarItem(item, {cortarSom:false})`; `_imgItemPandoo`.
- Produces: `registrarJogo("cruzadinha", {nome: "Cruzadinha", icone: "🧩", rotuloRodada: ["palavra", "palavras"], avisoSemRodada: "<texto da spec>", requisitos: (c, r) => problemasDoConteudo("cruzadinha", c, r), iniciar(palco, conteudo, regras)})`.

- [ ] **Step 1: Implementar o jogo** seguindo a prévia v3 (visual e textos) e a spec seção 3:
  - Ordem na `area`: `.pdc-trocar` (só com `formas.length > 1`; trocar chama `limparSoltasCruzadinha` e redesenha), `.pdc-grade` (CSS grid; casa = `clamp(30px, …, 64px)` calculado pela largura de `palco.area`; abaixo de 30 px, `overflow:auto` só na grade), `.pdc-instrucao`, `.pdc-banco` (forma letras), `.pdc-dicas`.
  - Casa com número (`numerarGrade`), pista da 1ª letra (`primeira_letra` ou forma figuras) em `.pdc-pista` clarinha; casa fixa mostra "-" ou fica vazia sem clique.
  - Teclado: `<input class="pdc-entrada">` invisível com os atributos da spec e `font-size:16px`; foco ao escolher palavra e ao tocar casa; `input` → `letrasDoInput` → `colocarLetraCruzadinha` em sequência; `keydown` Backspace → `apagarLetraCruzadinha`; `visualViewport` `resize` → `scrollIntoView({block:"nearest"})` na casa ativa; listeners removidos em `palco.aoEncerrar`.
  - Erro: classe `pdc-balanca` nas casas por 450 ms, depois redesenha o estado novo; `palco.efeito("treinar")`.
  - Feita: `palco.registrar(item, resultado, {comemorar: true})`, pulinho `pdc-pop`, e se `regras.voz_acertar` → `PandooSom.falarItem(item, {cortarSom: false})`. Ao escolher palavra (exceto forma figuras) → `palco.falarItem(item)`.
  - Figuras: sobreposto `.pdc-escolha` com `opcoesFigurasCruzadinha`; errada → `registrarErroCruzadinha` + `.errada` (balança/apaga); certa → `escreverPalavraCruzadinha`, desenhando letra a letra a cada 220 ms antes de registrar.
  - Placar `🧩 x de N palavras` + estrelas; terminou → `palco.finalizar()` 1,2 s depois.
  - Acessibilidade: casas e dicas `button` com `aria-label` da spec; `:focus-visible`; `prefers-reduced-motion` sem animação.

- [ ] **Step 2: Verificar** `node --check frontend/js/pandoo/jogos/cruzadinha.js` e `node --test frontend/tests/*.test.js` → OK.
- [ ] **Step 3: Commit** `"Pandoo: jogo da Cruzadinha no palco"`.

(O teste de tela fica no Task 6, depois do editor, porque a prévia sai do editor.)

---

### Task 5: Editor — modelo, regras, limites e miniatura

**Files:**
- Modify: `frontend/js/views/pandoo.js`
- Modify: `frontend/css/pandoo.css`
- Modify: `frontend/tests/pandoo_cruzadinha.test.js` (só se extrair função pura nova)

**Interfaces:**
- Consumes: `limitesDoModelo`, `problemaDaPalavraCruzadinha`, `contarLetras`, `montarGradeCruzadinha`, `conferirGrade`, `numerarGrade`.

- [ ] **Step 1: Implementar:**
  - `MODELOS_PANDOO_EDITOR`: `{codigo: "cruzadinha", nome: "Cruzadinha", icone: "🧩", pronto: true}` antes de "associacao".
  - Os três usos de `PANDOO_LIMITES.minItens/maxItens` passam a `limitesDoModelo(est.modelo)`.
  - `textos.cruzadinha = ["2. Palavras da cruzadinha", "De 2 a 10 palavras, cada uma com até 12 letras (hífen e espaço não contam). Para cada uma: a imagem, a palavra (só letras, hífen ou espaço) e, se quiser, a sua voz."]`.
  - Contador ao lado do título (`#pd-contador-itens`, só cruzadinha): "N de 10 palavras"; acima do máximo, vermelho com "N de 10 palavras — tire K para salvar". Com 10, `#pd-add` desativado e com o texto "Máximo de 10 palavras".
  - Em cada `.pd-item` (só cruzadinha): `.pd-item-letras` "N de 12 letras"; com `problemaDaPalavraCruzadinha` ≠ null, vermelho com a mensagem. Atualizar no `input` sem rerender da lista (não perder o foco).
  - `renderRegras`/`lerRegras` para cruzadinha: caixas `name="pd-forma"` (teclado/letras/figuras; impedir desmarcar a última), nota "Com mais de uma, a criança escolhe no jogo.", checks `pd-primeira-letra`, `pd-voz-regra` ("Falar a palavra ao tocar na figura"), `pd-voz-acertar-regra`, `pd-som-regra`; bloco "Arrumação da cruzadinha" com `.pd-mini-grade` (casas e números) e botão `#pd-sortear` "🔀 Sortear outra"; avisos de soltas e de "não deu para montar". `lerRegras` preserva `est.regras.grade`.
  - Remontar a grade: função `garantirGrade({sortear = false})` — se `sortear` ou `!conferirGrade(est.regras.grade, itens)`, chama `montarGradeCruzadinha` (resultado `null` → `grade = null`) e redesenha a miniatura. Chamar ao trocar para cruzadinha, ao editar palavra (com espera de 300 ms), ao adicionar/remover/reordenar figura, e antes de pré-visualizar/salvar. Imagem e voz não remontam.
  - Salvar e pré-visualizar já passam por `problemasDoConteudo` (que agora inclui `problemasCruzadinha`).

- [ ] **Step 2: Verificar** `node --check frontend/js/views/pandoo.js`, `node --test frontend/tests/*.test.js` e a suíte do backend completa → tudo PASS.
- [ ] **Step 3: Commit** `"Pandoo: editor da Cruzadinha com limites à vista"`.

---

### Task 6: Fumaça no navegador, documentação e PR

**Files:**
- Modify: `CLAUDE.md` (seção 5: item novo "ar) Pandoo — Cruzadinha"; seção 6 "Novo modelo do Pandoo" cita `cruzadinha_core.js`; seção 7 ordem dos jogos; seção 8 tabela)

- [ ] **Step 1: Subir o servidor local** (banco recriado pelo `seed.py`, módulo Pandoo liberado para a clínica de demonstração pelo Admin) e rodar com Playwright, em 390×844 e 1366×768, os roteiros da spec seção 4 "Navegador":
  - editor: criar cruzadinha com 6 figuras, "Sortear outra", palavra com 13 letras (vermelho + não salva), 10 figuras (botão desativado), trocar de um jogo de 12 figuras para Cruzadinha (contador vermelho), salvar;
  - prévia: as três formas (digitar errado e certo; letra errada no banco; figura errada e certa), trocar de forma no meio, tocar no "3" com a palavra 2 escolhida;
  - celular: grade de 10 palavras sem rolar a página para os lados; tocar numa casa foca o `input`;
  - missão da criança (responsável `ana@familia.com`): sem palavra não libera; com uma libera; no mesmo dia "encerrado por hoje";
  - ficha mostra a partida; console sem erro de JS.
- [ ] **Step 2: Rodar tudo:** pytest completo e `node --test frontend/tests/*.test.js` → PASS; anotar os números no CLAUDE.md.
- [ ] **Step 3: Commit** `"CLAUDE.md: Cruzadinha do Pandoo (item 5ar)"`, push e PR para `main`; com CI verde, merge automático (regra do CLAUDE.md; não é schema/cobrança). Avisar o usuário: **sem migração**, deploy de sempre (`git pull` + `touch tmp/restart.txt`).
