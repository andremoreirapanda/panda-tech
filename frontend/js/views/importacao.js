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
// ============================================================================

const IMPORTACAO_CAMPOS_CSV = [
    "nome", "data_nascimento", "genero", "avatar_mascote",
    "responsavel_nome", "responsavel_email", "responsavel_telefone", "parentesco",
];

const IMPORTACAO_LINHAS_EXEMPLO = [
    ["Maria Silva", "2019-05-20", "feminino", "", "Ana Silva", "ana.silva@exemplo.com", "11999998888", "Mãe"],
    ["João Souza", "2020-03-10", "", "", "Carlos Souza", "carlos.souza@exemplo.com", "", "Pai"],
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
        if (coluna === "data_nascimento" && window.XLSX && window.XLSX.SSF) {
            const partes = XLSX.SSF.parse_date_code(valor);
            if (partes) return `${partes.y}-${String(partes.m).padStart(2, "0")}-${String(partes.d).padStart(2, "0")}`;
        }
        return String(valor);
    }
    return String(valor).trim();
}

function _importacaoLinhasParaObjetos(linhasBrutas, paraTexto) {
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
        IMPORTACAO_CAMPOS_CSV.forEach(campo => {
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

async function _importacaoBaixarModeloExcel() {
    try {
        await _importacaoCarregarXlsxLib();
        const planilha = XLSX.utils.aoa_to_sheet([IMPORTACAO_CAMPOS_CSV, ...IMPORTACAO_LINHAS_EXEMPLO]);
        planilha["!cols"] = IMPORTACAO_CAMPOS_CSV.map(c => ({ wch: Math.max(c.length, 18) }));
        const pasta = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(pasta, planilha, "Pacientes");
        XLSX.writeFile(pasta, "modelo-importacao-pacientes.xlsx");
    } catch (err) {
        Toast.erro(err.message || "Não foi possível gerar o modelo em Excel.");
    }
}

function _importacaoBaixarModeloCsv() {
    const cabecalho = IMPORTACAO_CAMPOS_CSV.join(",");
    const exemplos = IMPORTACAO_LINHAS_EXEMPLO.map(linha => linha.join(","));
    const csv = "﻿" + [cabecalho, ...exemplos].join("\n"); // BOM: acentos abrem certo no Excel
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "modelo-importacao-pacientes.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
}

async function viewImportarPacientes(app) {
    let linhasAtuais = []; // últimas linhas lidas do arquivo, no formato que a API espera

    function renderStatusLinha(r) {
        if (!r.valido) {
            return `<span class="badge badge-alerta" title="${escapeHtml(r.erros.join(" "))}">❌ ${escapeHtml(r.erros[0])}</span>`;
        }
        if (r.aviso) {
            return `<span class="badge badge-aviso" title="${escapeHtml(r.aviso)}">⚠️ Atenção</span>`;
        }
        return r.responsavel_status === "existente"
            ? `<span class="badge badge-sucesso">✅ Vai vincular ao responsável já cadastrado</span>`
            : `<span class="badge badge-sucesso">✅ Novo responsável</span>`;
    }

    function renderResultadoPreview(resultado) {
        const semLinhas = resultado.linhas.length === 0;
        return `
        <div class="cartao" style="margin-top:20px;">
          <div class="linha-entre" style="margin-bottom:14px; flex-wrap:wrap; gap:8px;">
            <h3 style="font-size:15.5px;">Pré-visualização</h3>
            <span class="texto-sm texto-suave">
              ${resultado.validas} de ${resultado.total} linha(s) prontas para importar
              ${resultado.invalidas ? ` · ${resultado.invalidas} com erro` : ""}
            </span>
          </div>
          ${resultado.erro_limite_plano ? `
            <div class="cartao-flat" style="margin-bottom:14px; border-left:3px solid var(--cor-alerta);">
              <p class="texto-sm">🚫 ${escapeHtml(resultado.erro_limite_plano)}</p>
            </div>` : ""}
          ${semLinhas ? `<p class="texto-sm texto-suave">Nenhuma linha encontrada no arquivo.</p>` : `
          <div class="tabela-wrap"><table class="tabela">
            <thead><tr><th>#</th><th>Paciente</th><th>Nascimento</th><th>Responsável</th><th>Situação</th></tr></thead>
            <tbody>
              ${resultado.linhas.map(r => `
                <tr>
                  <td class="texto-sm">${r.linha + 1}</td>
                  <td class="texto-sm">${escapeHtml(r.nome || "—")}</td>
                  <td class="texto-sm">${escapeHtml(r.data_nascimento || "—")}</td>
                  <td class="texto-sm">${escapeHtml(r.responsavel_nome || "—")}<br><span class="texto-suave">${escapeHtml(r.responsavel_email || "")}</span></td>
                  <td>${renderStatusLinha(r)}</td>
                </tr>`).join("")}
            </tbody>
          </table></div>`}
          <div class="linha gap-3" style="margin-top:18px;">
            <button class="botao botao-primario" id="btn-confirmar-importacao" ${resultado.validas === 0 || resultado.erro_limite_plano ? "disabled" : ""}>
              ✅ Confirmar importação (${resultado.validas} paciente${resultado.validas === 1 ? "" : "s"})
            </button>
            <button class="botao botao-secundario" id="btn-cancelar-importacao">Cancelar</button>
          </div>
        </div>`;
    }

    function renderResultadoConfirmacao(resultado) {
        return `
        <div class="cartao" style="margin-top:20px;">
          <h3 style="font-size:15.5px; margin-bottom:10px;">Importação concluída</h3>
          <p class="texto-sm" style="margin-bottom:10px;">✅ ${resultado.total_criados} paciente(s) importado(s) com sucesso.</p>
          ${resultado.ignorados.length ? `
            <p class="texto-sm texto-suave" style="margin-bottom:6px;">${resultado.ignorados.length} linha(s) foram ignoradas por erro:</p>
            <ul class="texto-sm texto-suave" style="margin-left:18px; margin-bottom:10px;">
              ${resultado.ignorados.map(i => `<li>Linha ${i.linha + 1} (${escapeHtml(i.nome || "sem nome")}): ${escapeHtml(i.erros.join(" "))}</li>`).join("")}
            </ul>` : ""}
          <a href="#/gestor/pacientes" class="botao botao-primario">Ver pacientes</a>
        </div>`;
    }

    const conteudo = `
    <div class="cartao-flat" style="margin-bottom:20px; display:flex; gap:10px; align-items:flex-start;">
      <span style="font-size:18px;">📥</span>
      <p class="texto-sm texto-suave">
        Já tem os pacientes cadastrados em outro sistema? Baixe o modelo de planilha, preencha uma linha por
        paciente e envie o arquivo aqui — a gente confere tudo antes de importar de verdade, e nada é criado
        até você confirmar. Se um responsável já tiver outro filho na clínica, basta repetir o mesmo e-mail
        dele: o sistema reconhece e vincula à conta existente, em vez de duplicar.
      </p>
    </div>
    <div class="cartao">
      <div class="linha gap-3" style="flex-wrap:wrap; align-items:center;">
        <button class="botao botao-secundario" id="btn-baixar-modelo-excel">⬇️ Baixar modelo (Excel)</button>
        <button class="botao botao-link texto-sm" id="btn-baixar-modelo-csv" style="background:none; border:none; text-decoration:underline; cursor:pointer;">ou baixar em CSV</button>
        <div class="campo" style="margin:0; flex:1; min-width:240px;">
          <label>Enviar planilha preenchida (.xlsx ou .csv)</label>
          <input type="file" id="input-arquivo-importacao" accept=".xlsx,.xlsm,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" />
        </div>
      </div>
    </div>
    <div id="area-resultado-importacao"></div>`;

    app.innerHTML = renderShellSidebar("#/gestor/importar-pacientes", "Importar Pacientes", conteudo);
    anexarEventosShell();

    document.getElementById("btn-baixar-modelo-excel").addEventListener("click", _importacaoBaixarModeloExcel);
    document.getElementById("btn-baixar-modelo-csv").addEventListener("click", _importacaoBaixarModeloCsv);

    document.getElementById("input-arquivo-importacao").addEventListener("change", async (e) => {
        const arquivo = e.target.files[0];
        if (!arquivo) return;
        const area = document.getElementById("area-resultado-importacao");
        area.innerHTML = `<p class="texto-sm texto-suave" style="margin-top:16px;">Lendo arquivo...</p>`;
        try {
            const linhasBrutas = await _importacaoLerArquivoComoLinhas(arquivo);
            const objetos = _importacaoLinhasParaObjetos(linhasBrutas, _importacaoCelulaParaTexto);
            if (!objetos.length) {
                area.innerHTML = `<p class="texto-sm texto-suave" style="margin-top:16px;">Não encontramos nenhuma linha de paciente nesse arquivo — confira se ele segue o modelo baixado.</p>`;
                return;
            }
            linhasAtuais = objetos;
            const resultado = await Api.post("/importacao/pacientes/preview", { linhas: objetos });
            area.innerHTML = renderResultadoPreview(resultado);

            const btnConfirmar = document.getElementById("btn-confirmar-importacao");
            if (btnConfirmar) {
                btnConfirmar.addEventListener("click", async () => {
                    btnConfirmar.disabled = true;
                    btnConfirmar.textContent = "Importando...";
                    try {
                        const confirmado = await Api.post("/importacao/pacientes/confirmar", { linhas: linhasAtuais });
                        area.innerHTML = renderResultadoConfirmacao(confirmado);
                        Toast.sucesso(`${confirmado.total_criados} paciente(s) importado(s)!`);
                    } catch (err) {
                        Toast.erro(err.message);
                        btnConfirmar.disabled = false;
                        btnConfirmar.textContent = "✅ Confirmar importação";
                    }
                });
            }
            const btnCancelar = document.getElementById("btn-cancelar-importacao");
            if (btnCancelar) btnCancelar.addEventListener("click", () => {
                area.innerHTML = "";
                document.getElementById("input-arquivo-importacao").value = "";
            });
        } catch (err) {
            Toast.erro(err.message || "Não foi possível ler esse arquivo.");
            area.innerHTML = "";
        }
    });
}
