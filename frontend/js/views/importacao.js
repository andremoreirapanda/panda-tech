// ============================================================================
// views/importacao.js — Importação em lote de pacientes (Doc 22A, módulo
// opcional Pro/Enterprise; insight do usuário, 02/09/2026): clínicas que já
// têm uma base cadastrada em outro sistema podem trazer tudo de uma vez, por
// planilha, em vez de recadastrar paciente por paciente.
//
// O arquivo é lido e interpretado inteiramente no navegador (nunca sobe pro
// servidor como arquivo) — só as linhas já convertidas em texto simples vão
// pro backend, que faz a validação de verdade (o front nunca decide sozinho
// o que é válido) e, na confirmação, cria os pacientes reaproveitando a
// mesma regra de "mesmo e-mail nesta clínica = mesma conta" que protege o
// cadastro manual (ver util.js::ativarAutocompleteResponsavel).
//
// Formatos aceitos (insight do usuário, 02/09/2026 — "poderia ser normal, ao
// invés de CSV?"): Excel de verdade (.xlsx/.xlsm), que é o que a clínica já
// tem à mão, além do CSV. O leitor de Excel (SheetJS, frontend/js/vendor/) só
// é carregado quando alguém realmente usa esta tela — não pesa no carregamento
// do resto do sistema pra quem não mexe com importação.
//
// Prontuário (26/10/2026): duas abas. "Pacientes e Ficha Clínica" ganhou as
// colunas da Ficha Clínica (opcionais) e reconhece o paciente que já existe
// (mesmo nome + nascimento) sem duplicar; "Histórico de evoluções" lê uma 2ª
// planilha que vira registros "Importado" no Diário, só para a equipe. As
// funções puras ficam em importacao_util.js.
// ============================================================================

const IMPORTACAO_CAMPOS_CSV = [
    "nome", "data_nascimento", "genero", "avatar_mascote",
    "responsavel_nome", "responsavel_email", "responsavel_telefone", "parentesco",
    ...CAMPOS_FICHA_CSV,
];

const IMPORTACAO_LINHAS_EXEMPLO = [
    ["Maria Silva", "2019-05-20", "feminino", "", "Ana Silva", "ana.silva@exemplo.com", "11999998888", "Mãe",
        "TEA nível 1", "Lactose", "Risperidona 0,5 mg", "Dra. Paula (neuropediatra)", "Gosta de música; evita barulho alto."],
    ["João Souza", "2020-03-10", "", "", "Carlos Souza", "carlos.souza@exemplo.com", "", "Pai", "", "", "", "", ""],
];

const IMPORTACAO_EVOLUCOES_EXEMPLO = [
    ["Maria Silva", "2019-05-20", "2026-08-12", "camila@suaclinica.com.br", "Camila Rocha",
        "Trabalhou os sons /p/ e /b/ com figuras. Boa atenção na maior parte da sessão.", "Chegou cansada."],
    ["João Souza", "10/03/2020", "05/08/2026", "", "Dra. Ana (sistema anterior)",
        "Avaliação inicial de linguagem: compreende ordens simples.", ""],
];

let _importacaoXlsxLibPromise = null;

function _importacaoCarregarXlsxLib() {
    // Carregada sob demanda (só quando o usuário baixa o modelo em Excel ou
    // envia um .xlsx) — é uma biblioteca de ~250KB, sem sentido pesar no
    // carregamento das outras telas do sistema pra quem nunca usa importação.
    if (window.XLSX) return Promise.resolve();
    if (_importacaoXlsxLibPromise) return _importacaoXlsxLibPromise;
    _importacaoXlsxLibPromise = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "/js/vendor/xlsx.mini.min.js";
        script.onload = () => resolve();
        script.onerror = () => { _importacaoXlsxLibPromise = null; reject(new Error("Não foi possível carregar o suporte a Excel. Tente novamente.")); };
        document.head.appendChild(script);
    });
    return _importacaoXlsxLibPromise;
}

function _importacaoParseCsv(texto) {
    // Parser simples de CSV (sem dependência externa): entende campos entre
    // aspas (com vírgula ou quebra de linha dentro) e aspas duplicadas ("")
    // como aspas literais — o suficiente para o que um Excel/Google Sheets
    // exporta, sem precisar de uma biblioteca.
    const linhas = [];
    let campo = "", linha = [], dentroAspas = false;
    const t = texto.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    for (let i = 0; i < t.length; i++) {
        const c = t[i];
        if (dentroAspas) {
            if (c === '"') {
                if (t[i + 1] === '"') { campo += '"'; i++; } else { dentroAspas = false; }
            } else { campo += c; }
        } else if (c === '"') {
            dentroAspas = true;
        } else if (c === "," || c === ";") {
            // Aceita vírgula OU ponto-e-vírgula: o Excel em português salva
            // CSV com ";" por padrão, e isso já confundiu muita gente.
            linha.push(campo); campo = "";
        } else if (c === "\n") {
            linha.push(campo); linhas.push(linha); linha = []; campo = "";
        } else {
            campo += c;
        }
    }
    if (campo !== "" || linha.length) { linha.push(campo); linhas.push(linha); }
    return linhas.filter(l => l.some(c => c.trim() !== ""));
}

function _importacaoCelulaParaTexto(valor, coluna) {
    // Uma célula de planilha Excel pode vir como número, data (objeto Date
    // ou serial numérico) ou string — precisa virar sempre texto simples
    // antes de mandar pra API. Data de nascimento merece cuidado especial:
    // se a célula foi formatada como data no Excel, o valor "cru" é um
    // número serial (dias desde 1900), não o texto "2019-05-20" que a gente
    // precisa — por isso converte via XLSX.SSF.parse_date_code em vez de só
    // usar o texto formatado (que sairia no formato local, ex: "20/05/2019",
    // e quebraria a validação AAAA-MM-DD do backend).
    if (valor === null || valor === undefined) return "";
    if (valor instanceof Date) {
        const y = valor.getFullYear(), m = String(valor.getMonth() + 1).padStart(2, "0"), d = String(valor.getDate()).padStart(2, "0");
        return `${y}-${m}-${d}`;
    }
    if (typeof valor === "number") {
        if (ehColunaDeData(coluna) && window.XLSX && window.XLSX.SSF) {
            const partes = XLSX.SSF.parse_date_code(valor);
            if (partes) return `${partes.y}-${String(partes.m).padStart(2, "0")}-${String(partes.d).padStart(2, "0")}`;
        }
        return String(valor);
    }
    return String(valor).trim();
}

function _importacaoLinhasParaObjetos(linhasBrutas, paraTexto, campos = IMPORTACAO_CAMPOS_CSV) {
    // `linhasBrutas` é uma matriz (array de arrays) — a primeira linha é o
    // cabeçalho. Funciona tanto pro CSV (todas as células já são string)
    // quanto pro Excel (células podem vir com outros tipos — daí o
    // `paraTexto` customizado). A ordem das colunas na planilha não importa:
    // casa pelo NOME do cabeçalho, não pela posição.
    if (!linhasBrutas.length) return [];
    const converter = paraTexto || ((v) => (v == null ? "" : String(v).trim()));
    const cabecalho = linhasBrutas[0].map(h => String(h || "").trim().toLowerCase());
    return linhasBrutas.slice(1).map(linha => {
        const obj = {};
        campos.forEach(campo => {
            const idx = cabecalho.indexOf(campo);
            obj[campo] = idx >= 0 ? converter(linha[idx], campo) : "";
        });
        return obj;
    });
}

function _importacaoLerArquivoComoLinhas(arquivo) {
    // Devolve uma Promise<array de arrays> — a representação crua da
    // planilha, seja ela .csv ou .xlsx/.xlsm — pronta pra virar objetos via
    // `_importacaoLinhasParaObjetos`.
    const nomeMinusculo = arquivo.name.toLowerCase();
    if (nomeMinusculo.endsWith(".xlsx") || nomeMinusculo.endsWith(".xlsm")) {
        return _importacaoCarregarXlsxLib().then(() => arquivo.arrayBuffer()).then(buffer => {
            const pasta = XLSX.read(buffer, { type: "array" });
            const primeiraAba = pasta.SheetNames[0];
            if (!primeiraAba) return [];
            return XLSX.utils.sheet_to_json(pasta.Sheets[primeiraAba], { header: 1, defval: "", raw: true, blankrows: false });
        });
    }
    return arquivo.text().then(texto => _importacaoParseCsv(texto));
}

// Modelos das duas abas: { campos, exemplos, arquivo, aba }.
const IMPORTACAO_MODELOS = {
    pacientes: { campos: IMPORTACAO_CAMPOS_CSV, exemplos: IMPORTACAO_LINHAS_EXEMPLO, arquivo: "modelo-importacao-pacientes", aba: "Pacientes" },
    evolucoes: { campos: CAMPOS_EVOLUCOES_CSV, exemplos: IMPORTACAO_EVOLUCOES_EXEMPLO, arquivo: "modelo-importacao-evolucoes", aba: "Evolucoes" },
};

async function _importacaoBaixarModeloExcel(modelo) {
    try {
        await _importacaoCarregarXlsxLib();
        const planilha = XLSX.utils.aoa_to_sheet([modelo.campos, ...modelo.exemplos]);
        planilha["!cols"] = modelo.campos.map(c => ({ wch: Math.max(c.length, 18) }));
        const pasta = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(pasta, planilha, modelo.aba);
        XLSX.writeFile(pasta, `${modelo.arquivo}.xlsx`);
    } catch (err) {
        Toast.erro(err.message || "Não foi possível gerar o modelo em Excel.");
    }
}

function _importacaoCampoCsv(valor) {
    const texto = String(valor ?? "");
    return /[",;\n]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
}

function _importacaoBaixarModeloCsv(modelo) {
    const linhas = [modelo.campos, ...modelo.exemplos].map(l => l.map(_importacaoCampoCsv).join(","));
    const csv = "﻿" + linhas.join("\n"); // BOM: acentos abrem certo no Excel
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${modelo.arquivo}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
}

function _importacaoCartaoArquivo(aba) {
    return `
    <div class="cartao">
      <div class="linha gap-3" style="flex-wrap:wrap; align-items:center;">
        <button class="botao botao-secundario" id="btn-baixar-modelo-excel">⬇️ Baixar modelo (Excel)</button>
        <button class="botao botao-link texto-sm" id="btn-baixar-modelo-csv" style="background:none; border:none; text-decoration:underline; cursor:pointer;">ou baixar em CSV</button>
        <div class="campo" style="margin:0; flex:1; min-width:240px;">
          <label for="input-arquivo-importacao">Enviar planilha ${aba === "evolucoes" ? "de evoluções" : "preenchida"} (.xlsx ou .csv)</label>
          <input type="file" id="input-arquivo-importacao" accept=".xlsx,.xlsm,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" />
          ${renderOrientacaoEnvio("planilha")}
        </div>
      </div>
    </div>
    <div id="area-resultado-importacao"></div>`;
}

async function viewImportarPacientes(app) {
    const conteudo = `
    <div class="tabs" role="tablist" style="margin-bottom:18px; flex-wrap:wrap;">
      <button type="button" class="tab-item ativo" role="tab" aria-selected="true" data-aba="pacientes">👶 Pacientes e Ficha Clínica</button>
      <button type="button" class="tab-item" role="tab" aria-selected="false" data-aba="evolucoes">📔 Histórico de evoluções</button>
    </div>
    <div id="conteudo-aba-importacao"></div>`;

    app.innerHTML = renderShellSidebar("#/gestor/importar-pacientes", "Importar Pacientes", conteudo);
    anexarEventosShell();

    function abrirAba(aba) {
        document.querySelectorAll(".tabs .tab-item").forEach(b => {
            const ativa = b.dataset.aba === aba;
            b.classList.toggle("ativo", ativa);
            b.setAttribute("aria-selected", ativa ? "true" : "false");
        });
        const area = document.getElementById("conteudo-aba-importacao");
        if (aba === "evolucoes") _importacaoAbaEvolucoes(area);
        else _importacaoAbaPacientes(area);
        document.getElementById("btn-baixar-modelo-excel").addEventListener("click", () => _importacaoBaixarModeloExcel(IMPORTACAO_MODELOS[aba]));
        document.getElementById("btn-baixar-modelo-csv").addEventListener("click", () => _importacaoBaixarModeloCsv(IMPORTACAO_MODELOS[aba]));
    }
    document.querySelectorAll(".tabs .tab-item").forEach(b => b.addEventListener("click", () => abrirAba(b.dataset.aba)));
    abrirAba("pacientes");
}

// ------------------------------------------------------------ aba Pacientes
function _importacaoAbaPacientes(area) {
    let linhasAtuais = []; // últimas linhas lidas do arquivo, no formato que a API espera

    function renderStatusLinha(r) {
        if (!r.valido) {
            return `<span class="badge badge-alerta" title="${escapeHtml(r.erros.join(" "))}">❌ ${escapeHtml(r.erros[0])}</span>`;
        }
        if (r.aviso) {
            return `<span class="badge badge-aviso" title="${escapeHtml(r.aviso)}">⚠️ Atenção</span>
              <div class="texto-xs texto-suave" style="margin-top:4px;">${escapeHtml(r.aviso)}</div>`;
        }
        if (r.paciente_status === "existente") return `<span class="badge badge-sucesso">✅ Completa a ficha</span>`;
        return r.responsavel_status === "existente"
            ? `<span class="badge badge-sucesso">✅ Vai vincular ao responsável já cadastrado</span>`
            : `<span class="badge badge-sucesso">✅ Novo responsável</span>`;
    }

    function renderPaciente(r) {
        if (!r.valido && !r.paciente_status) return "—";
        if (r.paciente_status === "existente") {
            return `<span class="badge badge-neutro">Já cadastrado</span>${r.paciente_arquivado ? ` <span class="badge badge-neutro">arquivado</span>` : ""}`;
        }
        return `<span class="badge badge-marca">Novo</span>`;
    }

    function renderFicha(r) {
        if (!r.ficha_campos) return `<span class="texto-suave">—</span>`;
        const entram = r.ficha_campos - (r.ficha_mantidos || 0);
        return `${entram} campo(s)${r.ficha_mantidos ? `<br><span class="texto-xs texto-suave">${r.ficha_mantidos} já preenchido(s), mantido(s)</span>` : ""}`;
    }

    function renderResultadoPreview(resultado) {
        const semLinhas = resultado.linhas.length === 0;
        return `
        <div class="cartao" style="margin-top:20px;">
          <div class="linha-entre" style="margin-bottom:14px; flex-wrap:wrap; gap:8px;">
            <h3 style="font-size:15.5px;">Pré-visualização</h3>
            <span class="texto-sm texto-suave">
              ${resultado.validas} de ${resultado.total} linha(s) prontas
              ${resultado.existentes ? ` · ${resultado.existentes} já cadastrado(s)` : ""}
              ${resultado.invalidas ? ` · ${resultado.invalidas} com erro` : ""}
            </span>
          </div>
          ${resultado.erro_limite_plano ? `
            <div class="cartao-flat" style="margin-bottom:14px; border-left:3px solid var(--cor-alerta);">
              <p class="texto-sm">🚫 ${escapeHtml(resultado.erro_limite_plano)}</p>
            </div>` : ""}
          ${semLinhas ? `<p class="texto-sm texto-suave">Nenhuma linha encontrada no arquivo.</p>` : `
          <div class="tabela-wrap"><table class="tabela">
            <thead><tr><th>#</th><th>Paciente</th><th>Nascimento</th><th>Cadastro</th><th>Ficha</th><th>Responsável</th><th>Situação</th></tr></thead>
            <tbody>
              ${resultado.linhas.map(r => `
                <tr>
                  <td class="texto-sm">${r.linha + 1}</td>
                  <td class="texto-sm">${escapeHtml(r.nome || "—")}</td>
                  <td class="texto-sm">${escapeHtml(r.data_nascimento || "—")}</td>
                  <td class="texto-sm">${renderPaciente(r)}</td>
                  <td class="texto-sm">${renderFicha(r)}</td>
                  <td class="texto-sm">${escapeHtml(r.responsavel_nome || "—")}<br><span class="texto-suave">${escapeHtml(r.responsavel_email || "")}</span></td>
                  <td>${renderStatusLinha(r)}</td>
                </tr>`).join("")}
            </tbody>
          </table></div>`}
          <div class="linha gap-3" style="margin-top:18px;">
            <button class="botao botao-primario" id="btn-confirmar-importacao" ${resultado.validas === 0 || resultado.erro_limite_plano ? "disabled" : ""}>
              ✅ Importar ${resultado.validas} paciente${resultado.validas === 1 ? "" : "s"}
            </button>
            <button class="botao botao-secundario" id="btn-cancelar-importacao">Cancelar</button>
          </div>
        </div>`;
    }

    function renderResultadoConfirmacao(resultado) {
        const atualizados = resultado.total_atualizados || 0;
        return `
        <div class="cartao" style="margin-top:20px;">
          <h3 style="font-size:15.5px; margin-bottom:10px;">Importação concluída</h3>
          <p class="texto-sm" style="margin-bottom:10px;">✅ ${resultado.total_criados} paciente(s) novo(s) importado(s)${atualizados ? ` · ${atualizados} já cadastrado(s) com a ficha completada` : ""}.</p>
          ${resultado.ignorados.length ? `
            <p class="texto-sm texto-suave" style="margin-bottom:6px;">${resultado.ignorados.length} linha(s) foram ignoradas por erro:</p>
            <ul class="texto-sm texto-suave" style="margin-left:18px; margin-bottom:10px;">
              ${resultado.ignorados.map(i => `<li>Linha ${i.linha + 1} (${escapeHtml(i.nome || "sem nome")}): ${escapeHtml(i.erros.join(" "))}</li>`).join("")}
            </ul>` : ""}
          <a href="#/gestor/pacientes" class="botao botao-primario">Ver pacientes</a>
        </div>`;
    }

    area.innerHTML = `
    <div class="cartao-flat" style="margin-bottom:20px; display:flex; gap:10px; align-items:flex-start;">
      <span style="font-size:18px;">📥</span>
      <p class="texto-sm texto-suave">
        Já tem os pacientes cadastrados em outro sistema? Baixe o modelo de planilha, preencha uma linha por
        paciente e envie o arquivo aqui — a gente confere tudo antes de importar de verdade, e nada é criado
        até você confirmar. Se um responsável já tiver outro filho na clínica, basta repetir o mesmo e-mail
        dele: o sistema reconhece e vincula à conta existente, em vez de duplicar.
        As colunas da Ficha Clínica (diagnóstico, alergias, medicamentos, profissionais externos e observações)
        são opcionais. Paciente que já está no PandaUp (mesmo nome e nascimento) não é criado de novo: só
        completamos os campos vazios da ficha.
      </p>
    </div>
    <div class="cartao-flat" style="margin-bottom:20px; display:flex; gap:10px; align-items:flex-start; border-left:3px solid var(--cor-aviso);">
      <span style="font-size:18px;">👪</span>
      <p class="texto-sm">Diagnóstico, alergias, medicamentos e profissionais externos aparecem para a família na
        tela dela, como a ficha preenchida à mão. A coluna de observações clínicas vai para "🔒 Observações da
        equipe", na ficha, que a família não vê.</p>
    </div>
    ${_importacaoCartaoArquivo("pacientes")}`;

    document.getElementById("input-arquivo-importacao").addEventListener("change", async (e) => {
        const arquivo = e.target.files[0];
        if (!arquivo) return;
        const resultadoArea = document.getElementById("area-resultado-importacao");
        resultadoArea.innerHTML = `<p class="texto-sm texto-suave" style="margin-top:16px;">Lendo arquivo...</p>`;
        try {
            const linhasBrutas = await _importacaoLerArquivoComoLinhas(arquivo);
            const objetos = _importacaoLinhasParaObjetos(linhasBrutas, _importacaoCelulaParaTexto);
            if (!objetos.length) {
                resultadoArea.innerHTML = `<p class="texto-sm texto-suave" style="margin-top:16px;">Não encontramos nenhuma linha de paciente nesse arquivo — confira se ele segue o modelo baixado.</p>`;
                return;
            }
            linhasAtuais = objetos;
            const resultado = await Api.post("/importacao/pacientes/preview", { linhas: objetos });
            resultadoArea.innerHTML = renderResultadoPreview(resultado);

            const btnConfirmar = document.getElementById("btn-confirmar-importacao");
            if (btnConfirmar) {
                const rotulo = btnConfirmar.textContent;
                btnConfirmar.addEventListener("click", async () => {
                    btnConfirmar.disabled = true;
                    btnConfirmar.textContent = "Importando...";
                    try {
                        const confirmado = await Api.post("/importacao/pacientes/confirmar", { linhas: linhasAtuais });
                        resultadoArea.innerHTML = renderResultadoConfirmacao(confirmado);
                        Toast.sucesso(`${confirmado.total_criados} paciente(s) importado(s)!`);
                    } catch (err) {
                        Toast.erro(err.message);
                        btnConfirmar.disabled = false;
                        btnConfirmar.textContent = rotulo;
                    }
                });
            }
            const btnCancelar = document.getElementById("btn-cancelar-importacao");
            if (btnCancelar) btnCancelar.addEventListener("click", () => {
                resultadoArea.innerHTML = "";
                document.getElementById("input-arquivo-importacao").value = "";
            });
        } catch (err) {
            Toast.erro(err.message || "Não foi possível ler esse arquivo.");
            resultadoArea.innerHTML = "";
        }
    });
}

// ------------------------------------------------------------ aba Evoluções
function _importacaoAbaEvolucoes(area) {
    let envios = []; // linhas do arquivo divididas em envios de até 1.000

    const ROTULOS = {
        pronta: `<span class="badge badge-sucesso">✅ Pronta</span>`,
        aviso: `<span class="badge badge-aviso">⚠️ Pronta, com aviso</span>`,
        erro: `<span class="badge badge-alerta">❌ Erro</span>`,
        ja_importada: `<span class="badge badge-neutro">Já importada</span>`,
    };

    function renderPrevia(p) {
        const aImportar = p.prontas + p.avisos;
        return `
        <div class="cartao" style="margin-top:20px;">
          <div class="linha-entre" style="margin-bottom:14px; flex-wrap:wrap; gap:8px;">
            <h3 style="font-size:15.5px;">Pré-visualização</h3>
            <span class="texto-sm texto-suave">
              ${p.prontas} pronta(s) · ${p.avisos} com aviso · ${p.erros} com erro${p.ja_importadas ? ` · ${p.ja_importadas} já importada(s)` : ""}
            </span>
          </div>
          <div class="tabela-wrap"><table class="tabela">
            <thead><tr><th>#</th><th>Paciente</th><th>Atendimento</th><th>Profissional</th><th>Situação</th></tr></thead>
            <tbody>
              ${p.linhas.map(l => `
                <tr>
                  <td class="texto-sm">${l.linha + 1}</td>
                  <td class="texto-sm">${escapeHtml(l.paciente_nome || "—")}</td>
                  <td class="texto-sm">${escapeHtml(l.data_atendimento || "—")}</td>
                  <td class="texto-sm">${escapeHtml(l.profissional || "—")}</td>
                  <td>${ROTULOS[l.status] || ""}
                    ${[...(l.erros || []), ...(l.avisos || [])].map(t => `<div class="texto-xs texto-suave" style="margin-top:4px;">${escapeHtml(t)}</div>`).join("")}</td>
                </tr>`).join("")}
            </tbody>
          </table></div>
          <div class="linha gap-3" style="margin-top:18px; flex-wrap:wrap; align-items:center;">
            <button class="botao botao-primario" id="btn-confirmar-evolucoes" ${aImportar === 0 ? "disabled" : ""}>
              ✅ Importar ${aImportar} evoluç${aImportar === 1 ? "ão" : "ões"}
            </button>
            <button class="botao botao-secundario" id="btn-cancelar-evolucoes">Cancelar</button>
            <span class="texto-sm texto-suave" id="progresso-evolucoes" aria-live="polite"></span>
          </div>
        </div>`;
    }

    area.innerHTML = `
    <div class="cartao-flat" style="margin-bottom:12px; display:flex; gap:10px; align-items:flex-start; border-left:3px solid var(--cor-marca);">
      <span style="font-size:18px;">🔒</span>
      <p class="texto-sm"><strong>As evoluções importadas ficam só para a equipe. Nada aparece para as famílias.</strong></p>
    </div>
    <div class="cartao-flat" style="margin-bottom:20px; display:flex; gap:10px; align-items:flex-start;">
      <span style="font-size:18px;">📔</span>
      <p class="texto-sm texto-suave">
        Uma linha por atendimento antigo: ela vira um registro no Diário do paciente, com o selo "Importado".
        O paciente é encontrado pelo nome e pela data de nascimento, então <strong>importe os pacientes antes
        das evoluções</strong>. Datas em AAAA-MM-DD ou DD/MM/AAAA. Se o e-mail do profissional não for de
        ninguém da Equipe, o registro fica no seu nome, com o nome dele no começo do texto. Importar a mesma
        planilha de novo não duplica nada.
      </p>
    </div>
    ${_importacaoCartaoArquivo("evolucoes")}`;

    document.getElementById("input-arquivo-importacao").addEventListener("change", async (e) => {
        const arquivo = e.target.files[0];
        if (!arquivo) return;
        const resultadoArea = document.getElementById("area-resultado-importacao");
        resultadoArea.innerHTML = `<p class="texto-sm texto-suave" style="margin-top:16px;">Lendo arquivo...</p>`;
        try {
            const linhasBrutas = await _importacaoLerArquivoComoLinhas(arquivo);
            const objetos = _importacaoLinhasParaObjetos(linhasBrutas, _importacaoCelulaParaTexto, CAMPOS_EVOLUCOES_CSV);
            if (!objetos.length) {
                resultadoArea.innerHTML = `<p class="texto-sm texto-suave" style="margin-top:16px;">Não encontramos nenhuma evolução nesse arquivo — confira se ele segue o modelo baixado.</p>`;
                return;
            }
            envios = dividirEmEnvios(objetos);
            const previas = [];
            for (let i = 0; i < envios.length; i++) {
                if (envios.length > 1) resultadoArea.innerHTML = `<p class="texto-sm texto-suave" style="margin-top:16px;">Conferindo parte ${i + 1} de ${envios.length}...</p>`;
                previas.push(await Api.post("/importacao/evolucoes/preview", { linhas: envios[i] }));
            }
            resultadoArea.innerHTML = renderPrevia(juntarPrevias(previas));

            const btnConfirmar = document.getElementById("btn-confirmar-evolucoes");
            const progresso = document.getElementById("progresso-evolucoes");
            btnConfirmar.addEventListener("click", async () => {
                btnConfirmar.disabled = true;
                document.getElementById("btn-cancelar-evolucoes").disabled = true;
                let importadas = 0, puladas = 0, comErro = 0;
                try {
                    for (let i = 0; i < envios.length; i++) {
                        progresso.textContent = envios.length > 1 ? `Enviando ${i + 1} de ${envios.length}...` : "Importando...";
                        const r = await Api.post("/importacao/evolucoes/confirmar", { linhas: envios[i] });
                        importadas += r.importadas; puladas += r.puladas; comErro += (r.erros || []).length;
                    }
                } catch (err) {
                    Toast.erro(err.message);
                    // Cada envio é tudo ou nada; os anteriores já ficaram gravados e
                    // reenviar o arquivo pula o que já entrou (não duplica).
                    progresso.textContent = importadas
                        ? `${importadas} evolução(ões) já gravada(s). Envie o arquivo de novo para continuar: o que já entrou é pulado.`
                        : "";
                    btnConfirmar.disabled = false;
                    document.getElementById("btn-cancelar-evolucoes").disabled = false;
                    return;
                }
                resultadoArea.innerHTML = `
                <div class="cartao" style="margin-top:20px;">
                  <h3 style="font-size:15.5px; margin-bottom:10px;">Importação concluída</h3>
                  <p class="texto-sm" style="margin-bottom:10px;">✅ ${importadas} evoluç${importadas === 1 ? "ão importada" : "ões importadas"}, ${puladas} pulada(s) (já importadas)${comErro ? `, ${comErro} com erro` : ""}.</p>
                  <p class="texto-sm texto-suave" style="margin-bottom:12px;">Elas aparecem no Diário de cada paciente com o selo "Importado", só para a equipe.</p>
                  <a href="#/gestor/pacientes" class="botao botao-primario">Ver pacientes</a>
                </div>`;
                Toast.sucesso(`${importadas} evolução(ões) importada(s)!`);
            });
            document.getElementById("btn-cancelar-evolucoes").addEventListener("click", () => {
                resultadoArea.innerHTML = "";
                document.getElementById("input-arquivo-importacao").value = "";
            });
        } catch (err) {
            Toast.erro(err.message || "Não foi possível ler esse arquivo.");
            resultadoArea.innerHTML = "";
        }
    });
}
