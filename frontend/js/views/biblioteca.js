// ============================================================================
// views/biblioteca.js — UX Pattern 04: Filtros → Categorias → Cards → Detalhes
// ============================================================================

const LIMITE_ARQUIVO_BIBLIOTECA_MB = 4;

// Monta a árvore de pastas (até 2 níveis: pasta → subpasta) a partir da lista
// plana que a API devolve. Uma subpasta cujo pai não está na lista (não
// deveria acontecer — o backend bloqueia excluir pasta com subpasta) fica de
// fora da árvore em vez de virar uma raiz por engano.
function construirArvorePastas(categorias) {
    const porId = new Map(categorias.map(c => [c.id, { ...c, subpastas: [] }]));
    const raizes = [];
    for (const c of porId.values()) {
        if (c.pasta_pai_id) {
            const pai = porId.get(c.pasta_pai_id);
            if (pai) pai.subpastas.push(c);
        } else {
            raizes.push(c);
        }
    }
    return raizes;
}

function renderOptionsCategoria(categorias, categoriaIdSelecionada) {
    return construirArvorePastas(categorias).map(pasta => `
        <optgroup label="${pasta.icone_emoji} ${escapeHtml(pasta.nome)}">
          <option value="${pasta.id}" ${categoriaIdSelecionada === pasta.id ? "selected" : ""}>${pasta.icone_emoji} ${escapeHtml(pasta.nome)}</option>
          ${pasta.subpastas.map(sub => `<option value="${sub.id}" ${categoriaIdSelecionada === sub.id ? "selected" : ""}>↳ ${sub.icone_emoji} ${escapeHtml(sub.nome)}</option>`).join("")}
        </optgroup>`).join("");
}

function encontrarPastaNaArvore(raizes, id) {
    for (const p of raizes) {
        if (p.id === id) return p;
        const achada = p.subpastas && p.subpastas.find(s => s.id === id);
        if (achada) return achada;
    }
    return null;
}

// Deriva a árvore de pastas do Admin (Biblioteca da Plataforma) a partir dos
// próprios exercícios da Plataforma — uma clínica não tem acesso à listagem
// de categorias do Admin (organizacao_id NULL é escopo exclusivo dele), então
// pra navegar "por dentro" da Biblioteca da Plataforma como se fosse uma
// pasta comum, reconstrói a árvore olhando os campos de categoria que já
// vêm junto de cada exercício de Plataforma. Uma pasta do Admin sem nenhum
// exercício dentro ainda não aparece aqui — não afeta quem só está navegando
// (não é possível criar conteúdo na Plataforma por essa tela mesmo).
function pastasDaPlataforma(exerciciosPlataforma) {
    const porId = new Map();
    for (const ex of exerciciosPlataforma) {
        if (!ex.categoria_id) continue;
        if (ex.categoria_pasta_pai_id && !porId.has(ex.categoria_pasta_pai_id)) {
            porId.set(ex.categoria_pasta_pai_id, { id: ex.categoria_pasta_pai_id, nome: ex.pasta_pai_nome || "Pasta", icone_emoji: ex.pasta_pai_icone || "📘", pasta_pai_id: null });
        }
        if (!porId.has(ex.categoria_id)) {
            porId.set(ex.categoria_id, { id: ex.categoria_id, nome: ex.categoria_nome || "Pasta", icone_emoji: ex.categoria_icone || "📘", pasta_pai_id: ex.categoria_pasta_pai_id || null });
        }
    }
    return Array.from(porId.values());
}

// Calcula o que mostrar no nível atual da navegação por pastas (estilo
// "abrir uma pasta e ver o que tem dentro dela", como no Google Drive):
// devolve as subpastas e os exercícios soltos dessa pasta. `pilha` é o
// caminho de pastas já abertas (breadcrumb); pilha vazia = raiz.
function nivelDeNavegacao(exerciciosAba, categoriasProprias, pilha, apenasPlataforma) {
    const topo = pilha.length ? pilha[pilha.length - 1] : null;

    if (!topo) {
        const raizesProprias = construirArvorePastas(categoriasProprias);
        if (apenasPlataforma) {
            return { pastas: raizesProprias, exercicios: exerciciosAba.filter(ex => !ex.categoria_id) };
        }
        const temPlataforma = exerciciosAba.some(ex => ex.escopo === "plataforma");
        const pontePlataforma = temPlataforma
            ? [{ id: "__plataforma__", nome: "Biblioteca da Plataforma", icone_emoji: "🌐", subpastas: [], ehPontePlataforma: true }]
            : [];
        const soltos = exerciciosAba.filter(ex => ex.escopo !== "plataforma" && !ex.categoria_id);
        return { pastas: [...pontePlataforma, ...raizesProprias], exercicios: soltos };
    }

    if (topo.ehPontePlataforma) {
        const exPlataforma = exerciciosAba.filter(ex => ex.escopo === "plataforma");
        const raizes = construirArvorePastas(pastasDaPlataforma(exPlataforma)).map(p => ({ ...p, viaPonte: true }));
        return { pastas: raizes, exercicios: exPlataforma.filter(ex => !ex.categoria_id) };
    }

    if (topo.viaPonte) {
        const exPlataforma = exerciciosAba.filter(ex => ex.escopo === "plataforma");
        const arvore = construirArvorePastas(pastasDaPlataforma(exPlataforma));
        const pastaObj = encontrarPastaNaArvore(arvore, topo.id);
        const subpastas = (pastaObj && pastaObj.subpastas || []).map(s => ({ ...s, viaPonte: true }));
        return { pastas: subpastas, exercicios: exPlataforma.filter(ex => ex.categoria_id === topo.id) };
    }

    // Pasta própria (da clínica, ou do próprio Admin navegando na sua Biblioteca da Plataforma).
    const arvore = construirArvorePastas(categoriasProprias);
    const pastaObj = encontrarPastaNaArvore(arvore, topo.id);
    const subpastas = (pastaObj && pastaObj.subpastas) || [];
    const fonte = apenasPlataforma ? exerciciosAba : exerciciosAba.filter(ex => ex.escopo !== "plataforma");
    return { pastas: subpastas, exercicios: fonte.filter(ex => ex.categoria_id === topo.id) };
}

function renderCardPasta(pasta) {
    const qtdSub = (pasta.subpastas || []).length;
    return `
    <div class="exercicio-card pasta-card" data-pasta-id="${pasta.id}" style="cursor:pointer; align-items:center; text-align:center; justify-content:center;">
      <div class="exercicio-icone-tipo" style="font-size:34px;">${pasta.icone_emoji || "📁"}</div>
      <div class="exercicio-titulo">${escapeHtml(pasta.nome)}</div>
      <p class="texto-xs texto-suave">${qtdSub ? `${qtdSub} subpasta${qtdSub > 1 ? "s" : ""}` : "Abrir pasta →"}</p>
    </div>`;
}

function renderMigalhasPasta(pilha) {
    if (!pilha.length) return "";
    return `
    <div id="migalhas-pasta" class="linha gap-2" style="margin-bottom:14px; flex-wrap:wrap; align-items:center;">
      <button type="button" class="botao-texto botao-sm" data-indice="-1">📚 Biblioteca</button>
      ${pilha.map((p, i) => `<span class="texto-suave">/</span><button type="button" class="botao-texto botao-sm" data-indice="${i}">${p.icone_emoji} ${escapeHtml(p.nome)}</button>`).join("")}
    </div>`;
}

function renderModoPastas(exerciciosAba, categoriasProprias, pilha, papel, apenasPlataforma) {
    const { pastas, exercicios } = nivelDeNavegacao(exerciciosAba, categoriasProprias, pilha, apenasPlataforma);
    if (!pastas.length && !exercicios.length) {
        return renderMigalhasPasta(pilha) + `<div class="estado-vazio"><div class="emoji">📂</div><p>Pasta vazia.</p></div>`;
    }
    const cards = [...pastas.map(renderCardPasta), ...exercicios.map(ex => renderExercicioCard(ex, papel, apenasPlataforma))];
    return renderMigalhasPasta(pilha) + `<div class="exercicio-grade">${cards.join("")}</div>`;
}

// Agrupa os exercícios já filtrados pela aba em seções visuais pra grade.
// Numa clínica com visão combinada, tudo que vem da Biblioteca da Plataforma
// cai numa seção única "🌐 Biblioteca da Plataforma" — misturar a pasta do
// Admin (que é uma árvore totalmente separada da da clínica) só confundiria.
// Já na visão do próprio Admin (apenasPlataforma), os itens são agrupados
// normalmente pela pasta/subpasta deles.
function agruparPorPasta(exercicios, apenasPlataforma) {
    const grupos = new Map();
    const ordem = [];
    function bucket(chave, titulo, icone) {
        if (!grupos.has(chave)) { grupos.set(chave, { chave, titulo, icone, itens: [] }); ordem.push(chave); }
        return grupos.get(chave);
    }
    for (const ex of exercicios) {
        if (ex.escopo === "plataforma" && !apenasPlataforma) {
            bucket("__plataforma__", "Biblioteca da Plataforma", "🌐").itens.push(ex);
        } else if (ex.categoria_id) {
            if (ex.categoria_pasta_pai_id) {
                bucket(`pasta-${ex.categoria_pasta_pai_id}`, ex.pasta_pai_nome || "Pasta", ex.pasta_pai_icone || "📘").itens.push(ex);
            } else {
                bucket(`pasta-${ex.categoria_id}`, ex.categoria_nome || "Pasta", ex.categoria_icone || "📘").itens.push(ex);
            }
        } else {
            bucket("__sem_pasta__", "Sem pasta", "📄").itens.push(ex);
        }
    }
    const prioridade = chave => (chave === "__plataforma__" ? 0 : (chave === "__sem_pasta__" ? 2 : 1));
    ordem.sort((a, b) => prioridade(a) - prioridade(b));
    return ordem.map(chave => grupos.get(chave));
}

async function viewBiblioteca(app) {
    const u = Sessao.usuario;
    const base = u.papel === "admin_master" ? "admin" : (u.papel === "gestor" ? "gestor" : "profissional");
    const apenasPlataforma = u.papel === "admin_master";
    // Insight do usuário (09/09/2026): "Arquivar" escondia o exercício pra
    // sempre — a listagem nunca pedia os inativos, embora o backend já
    // suportasse isso (incluir_inativos=1). Agora sempre traz os dois estados
    // numa única busca e filtra no cliente pela aba ativa, pra não duplicar
    // requisição a cada troca de aba.
    let [categorias, todosExercicios] = await Promise.all([
        Api.get("/biblioteca/categorias"),
        Api.get(`/biblioteca/exercicios?incluir_inativos=1${apenasPlataforma ? "&apenas_plataforma=1" : ""}`),
    ]);
    const podeCriar = u.papel === "gestor" || u.papel === "profissional" || u.papel === "admin_master";
    let abaAtual = "ativos";
    // Navegação por pastas, estilo Google Drive (insight do usuário,
    // 09/09/2026): `pilha` é o caminho de pastas abertas (breadcrumb) —
    // pilha vazia é a raiz. Só é usada quando busca/filtro/pasta não estão
    // ativos; assim que algum filtro é usado, cai no modo de busca (lista
    // plana vinda da API, como já funcionava antes).
    let pilha = [];

    const conteudo = `
    ${apenasPlataforma ? `
    <div class="cartao-flat" style="margin-bottom:20px; display:flex; gap:10px; align-items:flex-start;">
      <span style="font-size:18px;">🌐</span>
      <p class="texto-sm texto-suave">
        Este é o conteúdo da <strong>Biblioteca da Plataforma</strong> — visível automaticamente para
        <strong>todas as clínicas</strong>. Cada clínica também tem sua própria biblioteca privada, que só ela vê.
      </p>
    </div>` : ""}
    <div class="tabs" style="margin-bottom:16px;">
      <div class="tab-item ativo" data-aba="ativos" style="cursor:pointer;">Ativos</div>
      <div class="tab-item" data-aba="arquivados" style="cursor:pointer;">Arquivados</div>
    </div>
    <div class="linha gap-3" style="margin-bottom:20px; flex-wrap:wrap;">
      <input type="text" id="busca-biblioteca" placeholder="🔍 Buscar exercícios..." style="flex:1; min-width:220px; padding:11px 16px; border-radius:999px; border:1.5px solid var(--cor-borda);" />
      ${categorias.length ? `
      <select id="filtro-categoria" style="padding:11px 14px; border-radius:999px; border:1.5px solid var(--cor-borda);">
        <option value="">Todas pastas</option>
        ${renderOptionsCategoria(categorias, null)}
      </select>` : ""}
      <select id="filtro-dificuldade" style="padding:11px 14px; border-radius:999px; border:1.5px solid var(--cor-borda);">
        <option value="">Qualquer dificuldade</option>
        <option value="facil">Fácil</option><option value="medio">Médio</option><option value="dificil">Difícil</option>
      </select>
    </div>
    <div id="area-biblioteca"></div>
    `;

    app.innerHTML = renderShellSidebar(`#/${base}/biblioteca`, apenasPlataforma ? "Biblioteca da Plataforma" : "Biblioteca Terapêutica", conteudo,
        `${(u.papel === "gestor" || u.papel === "profissional" || u.papel === "admin_master") ? `<button class="botao botao-secundario botao-sm" id="btn-gerenciar-categorias">🏷️ Pastas</button>` : ""}
         ${podeCriar ? `<button class="botao botao-primario botao-sm" id="btn-novo-exercicio">+ Novo Exercício</button>` : ""}`);
    anexarEventosShell();

    const btnCategorias = document.getElementById("btn-gerenciar-categorias");
    if (btnCategorias) btnCategorias.addEventListener("click", () => abrirModalCategorias(categorias, atualizarGrade));

    async function atualizarGrade() {
        const area = document.getElementById("area-biblioteca");
        if (!area) return; // usuário já navegou para outra tela antes da resposta chegar
        const q = document.getElementById("busca-biblioteca").value.trim();
        const cat = document.getElementById("filtro-categoria")?.value || "";
        const dif = document.getElementById("filtro-dificuldade").value;

        if (q || cat || dif) {
            // Modo busca: resultado plano vindo da API (ignora a pasta aberta).
            const params = new URLSearchParams();
            params.set("incluir_inativos", "1");
            if (apenasPlataforma) params.set("apenas_plataforma", "1");
            if (q) params.set("q", q);
            if (cat) params.set("categoria_id", cat);
            if (dif) params.set("dificuldade", dif);
            const novos = await Api.get(`/biblioteca/exercicios?${params}`);
            area.innerHTML = renderGradeExercicios(filtrarPorAba(novos, abaAtual, u), u.papel, apenasPlataforma);
            anexarCliquesCard(categorias, atualizarGrade, u.papel);
            return;
        }

        // Modo pastas: busca sempre os dados mais atuais — um exercício pode
        // ter acabado de ser criado, editado ou arquivado (via aoSalvar de um
        // modal), então usar a lista carregada no início da tela mostraria
        // pasta desatualizada.
        todosExercicios = await Api.get(`/biblioteca/exercicios?incluir_inativos=1${apenasPlataforma ? "&apenas_plataforma=1" : ""}`);
        const exerciciosAba = filtrarPorAba(todosExercicios, abaAtual, u);
        area.innerHTML = renderModoPastas(exerciciosAba, categorias, pilha, u.papel, apenasPlataforma);
        anexarCliquesCard(categorias, atualizarGrade, u.papel);
        area.querySelectorAll(".pasta-card").forEach(card => card.addEventListener("click", () => {
            const { pastas } = nivelDeNavegacao(exerciciosAba, categorias, pilha, apenasPlataforma);
            const idClicado = card.dataset.pastaId;
            const pastaClicada = pastas.find(p => String(p.id) === idClicado);
            if (!pastaClicada) return;
            pilha.push(pastaClicada);
            atualizarGrade();
        }));
        area.querySelectorAll("#migalhas-pasta button[data-indice]").forEach(btn => btn.addEventListener("click", () => {
            const indice = parseInt(btn.dataset.indice, 10);
            pilha = indice < 0 ? [] : pilha.slice(0, indice + 1);
            atualizarGrade();
        }));
    }

    let debounce;
    document.getElementById("busca-biblioteca").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(atualizarGrade, 300); });
    document.getElementById("filtro-categoria")?.addEventListener("change", atualizarGrade);
    document.getElementById("filtro-dificuldade").addEventListener("change", atualizarGrade);

    document.querySelectorAll(".tab-item[data-aba]").forEach(tab => tab.addEventListener("click", () => {
        if (tab.dataset.aba === abaAtual) return;
        document.querySelectorAll(".tab-item[data-aba]").forEach(t => t.classList.remove("ativo"));
        tab.classList.add("ativo");
        abaAtual = tab.dataset.aba;
        atualizarGrade();
    }));

    const btnNovo = document.getElementById("btn-novo-exercicio");
    if (btnNovo) btnNovo.addEventListener("click", () => {
        // Como no Drive: criar "aqui dentro" da pasta que está aberta no
        // momento. Não se aplica dentro da ponte da Biblioteca da Plataforma
        // (uma clínica não cria conteúdo na árvore de pastas do Admin).
        const atual = pilha.length ? pilha[pilha.length - 1] : null;
        const pastaPadrao = (atual && !atual.ehPontePlataforma && !atual.viaPonte) ? atual.id : null;
        abrirModalExercicio(categorias, null, atualizarGrade, pastaPadrao);
    });

    atualizarGrade();
}

function filtrarPorAba(exercicios, aba, usuario) {
    if (aba !== "arquivados") return exercicios.filter(ex => !!ex.ativo);
    // Um exercício arquivado da Biblioteca da Plataforma só é gerenciável pelo
    // Admin do SaaS — pra gestor/profissional ele não aparece na aba
    // Arquivados (não têm nenhuma ação possível ali, e o "sumiu" seria
    // menos confuso que mostrar algo que não conseguem reativar).
    return exercicios.filter(ex => !ex.ativo && (usuario.papel === "admin_master" || ex.escopo !== "plataforma"));
}

function renderGradeExercicios(exercicios, papel, apenasPlataforma) {
    if (!exercicios.length) return `<div class="estado-vazio"><div class="emoji">🔍</div><p>Nenhum exercício encontrado.</p></div>`;

    const grupos = agruparPorPasta(exercicios, apenasPlataforma);
    // Enquanto a clínica/Admin não usa pastas, nem faz sentido mostrar um
    // cabeçalho "Sem pasta" pra tudo — mantém a grade simples de antes.
    if (grupos.length === 1 && grupos[0].chave === "__sem_pasta__") {
        return `<div class="exercicio-grade">${exercicios.map(ex => renderExercicioCard(ex, papel, apenasPlataforma)).join("")}</div>`;
    }
    return grupos.map(g => `
        <div class="secao-pasta" style="margin-bottom:24px;">
          <h4 class="texto-sm" style="margin-bottom:10px; display:flex; align-items:center; gap:6px; font-weight:700;">${g.icone} ${escapeHtml(g.titulo)}</h4>
          <div class="exercicio-grade">${g.itens.map(ex => renderExercicioCard(ex, papel, apenasPlataforma)).join("")}</div>
        </div>`).join("");
}

function anexarCliquesCard(categorias, aoSalvar, papel) {
    document.querySelectorAll(".exercicio-card:not(.pasta-card)").forEach(card => card.addEventListener("click", async () => {
        const ex = await Api.get(`/biblioteca/exercicios/${card.dataset.id}`);
        if (ex.pode_editar) abrirModalExercicio(categorias, ex, aoSalvar);
        else abrirModalDetalheExercicio(ex, papel, aoSalvar);
    }));
}

function renderExercicioCard(ex, papel, apenasPlataforma) {
    const difCor = { facil: "sucesso", medio: "aviso", dificil: "alerta" }[ex.dificuldade] || "neutro";
    const editavel = ex.escopo === "plataforma" ? papel === "admin_master" : true;
    // Quando o item de Plataforma já está agrupado na seção especial "🌐
    // Biblioteca da Plataforma" (visão combinada da clínica), repetir a
    // pasta interna do Admin no card só confundiria — essa pasta pertence a
    // uma árvore separada da da clínica.
    const mostrarPastaPropria = !(ex.escopo === "plataforma" && !apenasPlataforma);
    const badgePasta = ex.categoria_pasta_pai_id
        ? `${ex.pasta_pai_icone || "📘"} ${escapeHtml(ex.pasta_pai_nome || "")} / ${ex.categoria_icone || "📘"} ${escapeHtml(ex.categoria_nome || "")}`
        : `${ex.categoria_icone || "📘"} ${escapeHtml(ex.categoria_nome || "Geral")}`;
    return `
    <div class="exercicio-card" data-id="${ex.id}" style="cursor:pointer; ${ex.ativo ? "" : "opacity:.6;"}">
      <div class="exercicio-icone-tipo">${ICONES_TIPO_EXERCICIO[ex.tipo] || "📝"}</div>
      <div class="exercicio-titulo">${escapeHtml(ex.titulo)}</div>
      <p class="texto-xs texto-suave">${escapeHtml(ex.descricao || "")}</p>
      <div class="exercicio-tags">
        ${ex.escopo === "plataforma" ? `<span class="badge badge-marca">🌐 Plataforma</span>` : ""}
        ${mostrarPastaPropria ? `<span class="badge badge-neutro">${badgePasta}</span>` : ""}
        <span class="badge badge-${difCor}">${ex.dificuldade}</span>
        <span class="badge badge-neutro">${ex.faixa_etaria_min}-${ex.faixa_etaria_max} anos</span>
        ${ex.tem_arquivo || ex.arquivo_nome ? `<span class="badge badge-marca">📎 arquivo</span>` : (ex.conteudo_url ? `<span class="badge badge-marca">🔗 link</span>` : "")}
        ${ex.ativo ? "" : `<span class="badge badge-neutro">🗄️ Arquivado</span>`}
      </div>
      <p class="texto-xs texto-suave" style="margin-top:auto; padding-top:6px;">${editavel ? (ex.ativo ? "Clique para editar →" : "Clique para reativar →") : "Clique para ver detalhes →"}</p>
    </div>`;
}

// ---------------------------------------------------------------- Detalhe (somente leitura)
function abrirModalDetalheExercicio(ex, papel, aoSalvar) {
    const podeAdotar = ex.escopo === "plataforma" && (papel === "gestor" || papel === "profissional");
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <div class="linha-entre" style="margin-bottom:8px;">
          <h3>${ICONES_TIPO_EXERCICIO[ex.tipo] || "📝"} ${escapeHtml(ex.titulo)}</h3>
          ${ex.escopo === "plataforma" ? `<span class="badge badge-marca">🌐 Plataforma</span>` : ""}
        </div>
        <p class="texto-sm texto-suave" style="margin-bottom:16px;">${escapeHtml(ex.descricao || "")}</p>
        ${ex.conteudo_url ? `<a href="${escapeHtml(ex.conteudo_url)}" target="_blank" class="botao botao-secundario botao-sm">🔗 Abrir link</a>` : ""}
        ${podeAdotar ? `<p class="texto-xs texto-suave" style="margin-top:14px;">Gostou deste conteúdo? Adicione uma cópia editável à biblioteca da sua clínica.</p>` : ""}
        <div class="linha gap-3" style="margin-top:16px;">
          ${podeAdotar ? `<button type="button" class="botao botao-primario" id="btn-adotar-exercicio">+ Adicionar à minha Biblioteca</button>` : ""}
          <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Fechar</button>
        </div>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());
    const btnAdotar = document.getElementById("btn-adotar-exercicio");
    if (btnAdotar) btnAdotar.addEventListener("click", async () => {
        try {
            await Api.post(`/biblioteca/exercicios/${ex.id}/duplicar`);
            Toast.sucesso("Adicionado à biblioteca da sua clínica! Já pode editar como quiser.");
            modal.remove();
            aoSalvar();
        } catch (err) { Toast.erro(err.message); }
    });
}

// ---------------------------------------------------------------- Criar / Editar

function abrirModalExercicio(categorias, exercicioExistente, aoSalvar, categoriaPadraoId) {
    const editando = !!exercicioExistente;
    // Ao criar (nunca ao editar), pré-seleciona a pasta que estava aberta no
    // momento em que o usuário clicou em "Novo Exercício" — igual ao Drive,
    // que cria o arquivo novo dentro da pasta em que você está.
    const ex = exercicioExistente || (categoriaPadraoId ? { categoria_id: categoriaPadraoId } : {});
    let arquivoNovo = null; // { nome, base64 } — só preenchido se o usuário trocar o arquivo nesta sessão

    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:18px;">${editando ? "Editar exercício" : "Novo exercício"}</h3>
        <form id="form-exercicio">
          <div class="campo"><label>Título ${ASTERISCO_OBRIGATORIO}</label><input type="text" id="ex-titulo" value="${escapeHtml(ex.titulo || "")}" required /></div>
          <div class="campo"><label>Descrição</label><textarea id="ex-descricao" rows="2">${escapeHtml(ex.descricao || "")}</textarea></div>
          <div class="linha gap-4">
            ${categorias.length ? `
            <div class="campo" style="flex:1;"><label>Pasta</label>
              <select id="ex-categoria">
                <option value="" ${!ex.categoria_id ? "selected" : ""}>Sem pasta</option>
                ${renderOptionsCategoria(categorias, ex.categoria_id || null)}
              </select>
            </div>` : ""}
            <div class="campo" style="flex:1;"><label>Tipo</label>
              <select id="ex-tipo">${Object.entries(ICONES_TIPO_EXERCICIO).map(([k, v]) => `<option value="${k}" ${ex.tipo === k ? "selected" : ""}>${v} ${k}</option>`).join("")}</select>
            </div>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>Dificuldade</label>
              <select id="ex-dificuldade">
                <option value="facil" ${ex.dificuldade === "facil" ? "selected" : ""}>Fácil</option>
                <option value="medio" ${ex.dificuldade === "medio" ? "selected" : ""}>Médio</option>
                <option value="dificil" ${ex.dificuldade === "dificil" ? "selected" : ""}>Difícil</option>
              </select>
            </div>
            <div class="campo" style="flex:1;"><label>Faixa etária</label>
              <div class="linha gap-2">
                <input type="number" id="ex-idade-min" value="${ex.faixa_etaria_min ?? 2}" style="width:70px;" />
                <span>a</span>
                <input type="number" id="ex-idade-max" value="${ex.faixa_etaria_max ?? 10}" style="width:70px;" />
              </div>
            </div>
          </div>

          <div class="tabs" style="margin-bottom:14px;">
            <div class="tab-item ${!ex.conteudo_url ? "ativo" : ""}" data-tab="upload">📎 Enviar arquivo</div>
            <div class="tab-item ${ex.conteudo_url ? "ativo" : ""}" data-tab="link">🔗 Link externo</div>
          </div>

          <div id="painel-upload" class="campo" style="${ex.conteudo_url ? "display:none;" : ""}">
            <label>Arquivo (foto, PDF, áudio ou vídeo curto — até ${LIMITE_ARQUIVO_BIBLIOTECA_MB}MB)</label>
            <input type="file" id="ex-arquivo" accept="image/*,application/pdf,audio/*,video/*" />
            <div id="arquivo-atual" class="texto-sm texto-suave" style="margin-top:8px;">
              ${ex.arquivo_nome ? `📎 Arquivo atual: <strong>${escapeHtml(ex.arquivo_nome)}</strong> <button type="button" id="btn-remover-arquivo" class="botao-texto botao-sm" style="padding:2px 6px;">remover</button>` : "Nenhum arquivo enviado ainda."}
            </div>
          </div>
          <div id="painel-link" class="campo" style="${ex.conteudo_url ? "" : "display:none;"}">
            <label>URL do conteúdo</label>
            <input type="url" id="ex-url" value="${escapeHtml(ex.conteudo_url || "")}" placeholder="https://..." />
          </div>

          <div class="linha gap-3" style="margin-top:16px;">
            <button type="submit" class="botao botao-primario" id="btn-salvar-exercicio">Salvar exercício</button>
            ${editando ? `<button type="button" class="botao botao-perigo" id="btn-arquivar-exercicio">${ex.ativo === 0 ? "Reativar" : "Arquivar"}</button>` : ""}
            <button type="button" class="botao botao-secundario" id="btn-cancelar-modal">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => modal.remove());

    let removerArquivo = false;
    let modoConteudo = ex.conteudo_url ? "link" : "upload";
    modal.querySelectorAll(".tab-item").forEach(tab => tab.addEventListener("click", () => {
        modal.querySelectorAll(".tab-item").forEach(t => t.classList.remove("ativo"));
        tab.classList.add("ativo");
        modoConteudo = tab.dataset.tab;
        document.getElementById("painel-upload").style.display = modoConteudo === "upload" ? "" : "none";
        document.getElementById("painel-link").style.display = modoConteudo === "link" ? "" : "none";
    }));

    document.getElementById("ex-arquivo").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        if (file.size > LIMITE_ARQUIVO_BIBLIOTECA_MB * 1024 * 1024) {
            Toast.erro(`"${file.name}" passa de ${LIMITE_ARQUIVO_BIBLIOTECA_MB}MB.`);
            e.target.value = "";
            return;
        }
        const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        arquivoNovo = { nome: file.name, base64 };
        removerArquivo = false;
        document.getElementById("arquivo-atual").innerHTML = `📎 Selecionado: <strong>${escapeHtml(file.name)}</strong>`;
    });

    const btnRemoverArquivo = document.getElementById("btn-remover-arquivo");
    if (btnRemoverArquivo) btnRemoverArquivo.addEventListener("click", () => {
        removerArquivo = true;
        arquivoNovo = null;
        document.getElementById("arquivo-atual").textContent = "Arquivo será removido ao salvar.";
    });

    const btnArquivar = document.getElementById("btn-arquivar-exercicio");
    if (btnArquivar) btnArquivar.addEventListener("click", async () => {
        if (!confirm(ex.ativo === 0 ? "Reativar este exercício na biblioteca?" : "Arquivar este exercício? Ele deixa de aparecer na Biblioteca, mas missões que já o usam continuam funcionando.")) return;
        const r = await Api.put(`/biblioteca/exercicios/${ex.id}/arquivar`);
        Toast.sucesso(r.ativo ? "Exercício reativado!" : "Exercício arquivado.");
        modal.remove();
        aoSalvar();
    });

    document.getElementById("form-exercicio").addEventListener("submit", async (e) => {
        e.preventDefault();
        const btnSalvar = document.getElementById("btn-salvar-exercicio");
        btnSalvar.disabled = true;
        try {
            const body = {
                titulo: document.getElementById("ex-titulo").value.trim(),
                descricao: document.getElementById("ex-descricao").value.trim(),
                categoria_id: document.getElementById("ex-categoria") ? (parseInt(document.getElementById("ex-categoria").value) || null) : null,
                tipo: document.getElementById("ex-tipo").value,
                dificuldade: document.getElementById("ex-dificuldade").value,
                faixa_etaria_min: parseInt(document.getElementById("ex-idade-min").value),
                faixa_etaria_max: parseInt(document.getElementById("ex-idade-max").value),
                conteudo_url: modoConteudo === "link" ? document.getElementById("ex-url").value.trim() : "",
            };
            if (modoConteudo === "upload" && arquivoNovo) {
                body.arquivo_nome = arquivoNovo.nome;
                body.arquivo_base64 = arquivoNovo.base64;
            }
            if (removerArquivo) body.remover_arquivo = true;

            if (editando) {
                await Api.put(`/biblioteca/exercicios/${ex.id}`, body);
                Toast.sucesso("Exercício atualizado!");
            } else {
                await Api.post("/biblioteca/exercicios", body);
                Toast.sucesso("Exercício adicionado à biblioteca!");
            }
            modal.remove();
            aoSalvar();
        } catch (err) {
            Toast.erro(err.message);
            btnSalvar.disabled = false;
        }
    });
}

// ---------------------------------------------------------------- Gerenciar categorias

function abrirModalCategorias(categoriasAtuais, aoAtualizar) {
    const EMOJIS_SUGERIDOS = ["📘", "🗣️", "🤸", "🧠", "🖐️", "🤝", "🎨", "🎵", "🧩", "❤️"];
    let categorias = categoriasAtuais;
    let emojiEscolhido = EMOJIS_SUGERIDOS[0];
    let pastaPaiSelecionada = null; // null = nova pasta de topo; senão, nova subpasta dessa pasta

    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:6px;">🏷️ Pastas da Biblioteca</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:16px;">
          Organize os exercícios em pastas e, se precisar, subpastas (até 2 níveis de profundidade).
        </p>
        <div id="arvore-pastas" class="coluna gap-2" style="margin-bottom:18px;"></div>
        <hr style="border:none; border-top:1px solid var(--cor-borda); margin-bottom:16px;" />
        <p class="texto-sm" id="titulo-form-pasta" style="font-weight:700; margin-bottom:10px;">Nova pasta</p>
        <div class="linha gap-2" style="margin-bottom:10px; flex-wrap:wrap;">
          ${EMOJIS_SUGERIDOS.map((e, i) => `<button type="button" class="botao-icone btn-emoji-categoria ${i === 0 ? "ativo" : ""}" data-emoji="${e}" style="${i === 0 ? "border-color:var(--cor-marca);" : ""}">${e}</button>`).join("")}
        </div>
        <div class="linha gap-2">
          <input type="text" id="nova-categoria-nome" placeholder="Ex: Alimentação, Fala, Coordenação..." style="flex:1; padding:9px 12px; border-radius:8px; border:1.5px solid var(--cor-borda);" />
          <button type="button" class="botao botao-primario botao-sm" id="btn-adicionar-categoria">Adicionar</button>
          <button type="button" class="botao botao-secundario botao-sm" id="btn-cancelar-subpasta" style="display:none;">Cancelar</button>
        </div>
        <button type="button" class="botao botao-secundario" id="btn-cancelar-modal" style="width:100%; margin-top:18px;">Fechar</button>
      </div>
    </div>`);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    document.getElementById("btn-cancelar-modal").addEventListener("click", () => { modal.remove(); if (aoAtualizar) aoAtualizar(); despachar(); });

    modal.querySelectorAll(".btn-emoji-categoria").forEach(btn => btn.addEventListener("click", () => {
        modal.querySelectorAll(".btn-emoji-categoria").forEach(b => b.style.borderColor = "var(--cor-borda)");
        btn.style.borderColor = "var(--cor-marca)";
        emojiEscolhido = btn.dataset.emoji;
    }));

    function selecionarPastaPai(pasta) {
        pastaPaiSelecionada = pasta;
        document.getElementById("titulo-form-pasta").textContent = pasta ? `Nova subpasta em "${pasta.nome}"` : "Nova pasta";
        document.getElementById("btn-cancelar-subpasta").style.display = pasta ? "" : "none";
        document.getElementById("nova-categoria-nome").focus();
    }
    document.getElementById("btn-cancelar-subpasta").addEventListener("click", () => selecionarPastaPai(null));

    async function recarregar() {
        categorias = await Api.get("/biblioteca/categorias");
        renderArvore();
    }

    function renderArvore() {
        const raizes = construirArvorePastas(categorias);
        const container = document.getElementById("arvore-pastas");
        container.innerHTML = raizes.length ? raizes.map(pasta => `
            <div class="cartao-flat" style="padding:8px 12px;">
              <div class="linha gap-2" style="align-items:center;">
                <span style="font-size:18px;">${pasta.icone_emoji}</span>
                <span class="texto-sm" style="flex:1; font-weight:600;">${escapeHtml(pasta.nome)}</span>
                <button type="button" class="botao-texto botao-sm btn-add-subpasta" data-id="${pasta.id}">+ subpasta</button>
                <button type="button" class="botao-texto botao-sm btn-renomear-pasta" data-id="${pasta.id}">renomear</button>
                <button type="button" class="botao-texto botao-sm btn-excluir-pasta" data-id="${pasta.id}">excluir</button>
              </div>
              ${pasta.subpastas.length ? `
              <div class="coluna gap-1" style="margin-top:8px; margin-left:26px;">
                ${pasta.subpastas.map(sub => `
                <div class="linha gap-2" style="align-items:center;">
                  <span>↳</span><span>${sub.icone_emoji}</span>
                  <span class="texto-sm" style="flex:1;">${escapeHtml(sub.nome)}</span>
                  <button type="button" class="botao-texto botao-sm btn-renomear-pasta" data-id="${sub.id}">renomear</button>
                  <button type="button" class="botao-texto botao-sm btn-excluir-pasta" data-id="${sub.id}">excluir</button>
                </div>`).join("")}
              </div>` : ""}
            </div>`).join("") : `<p class="texto-sm texto-suave">Nenhuma pasta criada ainda.</p>`;

        container.querySelectorAll(".btn-add-subpasta").forEach(btn => btn.addEventListener("click", () => {
            selecionarPastaPai(categorias.find(c => c.id === parseInt(btn.dataset.id)));
        }));
        container.querySelectorAll(".btn-renomear-pasta").forEach(btn => btn.addEventListener("click", async () => {
            const pasta = categorias.find(c => c.id === parseInt(btn.dataset.id));
            const novoNome = prompt("Novo nome da pasta:", pasta.nome);
            if (!novoNome || !novoNome.trim() || novoNome.trim() === pasta.nome) return;
            try {
                await Api.put(`/biblioteca/categorias/${pasta.id}`, { nome: novoNome.trim() });
                Toast.sucesso("Pasta renomeada!");
                await recarregar();
            } catch (err) { Toast.erro(err.message); }
        }));
        container.querySelectorAll(".btn-excluir-pasta").forEach(btn => btn.addEventListener("click", async () => {
            const pasta = categorias.find(c => c.id === parseInt(btn.dataset.id));
            if (!confirm(`Excluir a pasta "${pasta.nome}"? Só é possível se ela estiver vazia (sem subpastas nem exercícios).`)) return;
            try {
                await Api.del(`/biblioteca/categorias/${pasta.id}`);
                Toast.sucesso("Pasta excluída.");
                if (pastaPaiSelecionada && pastaPaiSelecionada.id === pasta.id) selecionarPastaPai(null);
                await recarregar();
            } catch (err) { Toast.erro(err.message); }
        }));
    }

    document.getElementById("btn-adicionar-categoria").addEventListener("click", async () => {
        const nome = document.getElementById("nova-categoria-nome").value.trim();
        if (!nome) { Toast.erro("Dê um nome pra pasta."); return; }
        try {
            const corpo = { nome, icone_emoji: emojiEscolhido };
            if (pastaPaiSelecionada) corpo.pasta_pai_id = pastaPaiSelecionada.id;
            await Api.post("/biblioteca/categorias", corpo);
            Toast.sucesso(pastaPaiSelecionada ? "Subpasta criada!" : "Pasta criada!");
            document.getElementById("nova-categoria-nome").value = "";
            selecionarPastaPai(null);
            await recarregar();
        } catch (err) { Toast.erro(err.message); }
    });

    renderArvore();
}
