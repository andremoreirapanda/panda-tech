// ============================================================================
// views/procedimentos.js — Procedimentos da clínica (09/10/2026, só gestor)
//
// Lista editável (como na Clínica Ágil): arrastar para ordenar, desativar,
// código, nome, valor e remover. "Salvar" manda a lista inteira para
// PUT /api/procedimentos. Procedimento já usado em consulta não é removido:
// só desativado (o backend recusa com 409).
// ============================================================================

async function viewProcedimentos(app) {
    let linhas = [];
    try {
        linhas = (await Api.get("/procedimentos")).map(p => ({
            id: p.id, codigo: p.codigo || "", nome: p.nome, valor: centavosParaReais(p.valor_centavos),
            ativo: !!p.ativo, emUso: p.em_uso || 0,
        }));
    } catch (err) {
        Toast.erro(err.message);
    }
    let arrastando = null;
    let sujo = false;   // alteração ainda não salva
    window.SaidaProtegida = () => (sujo ? "Há alterações nos procedimentos que ainda não foram salvas. Sair mesmo assim?" : null);

    function renderLinha(l, i) {
        const valorOk = reaisParaCentavos(l.valor) !== null;
        return `
        <tr class="${l.ativo ? "" : "proc-inativo"}" data-i="${i}">
          <td class="proc-alca" draggable="true" title="Arraste para mudar a ordem" aria-hidden="true">⋮⋮</td>
          <td class="proc-centro"><input type="checkbox" class="proc-desativar" data-i="${i}" ${l.ativo ? "" : "checked"} aria-label="Desativar ${escapeHtml(l.nome)}" /></td>
          <td><input type="text" class="proc-codigo" data-i="${i}" value="${escapeHtml(l.codigo)}" maxlength="30" aria-label="Código" /></td>
          <td><input type="text" class="proc-nome" data-i="${i}" value="${escapeHtml(l.nome)}" maxlength="120" placeholder="Nome do procedimento" aria-label="Procedimento" />
            ${l.emUso ? `<div class="texto-xs texto-suave">usado em ${l.emUso} ${l.emUso === 1 ? "consulta" : "consultas"}</div>` : ""}
            ${l.ativo ? "" : `<div class="texto-xs texto-suave">desativado · não aparece no agendamento</div>`}</td>
          <td><input type="text" class="proc-valor ${valorOk || !l.valor ? "" : "proc-erro"}" data-i="${i}" value="${escapeHtml(l.valor)}" inputmode="decimal" placeholder="0,00" aria-label="Valor em reais" /></td>
          <td class="proc-centro">${l.emUso
              ? `<button type="button" class="botao-icone proc-travado" title="Já usado: só dá para desativar" aria-label="Já usado: só dá para desativar" disabled>🔒</button>`
              : `<button type="button" class="botao-icone proc-remover" data-i="${i}" title="Remover" aria-label="Remover">✕</button>`}</td>
        </tr>`;
    }

    function render() {
        const conteudo = `
        <div class="cartao coluna gap-4">
          <div class="aviso-info texto-sm">
            <strong>ℹ️ Como funciona</strong>
            <ul style="margin:4px 0 0; padding-left:18px;">
              <li>Mudar o valor só vale para as consultas marcadas a partir de agora. As já marcadas guardam o valor do dia.</li>
              <li>Mudar o nome atualiza o nome em todas as consultas.</li>
              <li>Procedimento já usado em consulta não pode ser removido: marque “Desativar” para tirá-lo do agendamento.</li>
              <li>O valor só aparece para o gestor. A equipe vê apenas o nome ao agendar.</li>
            </ul>
          </div>
          ${linhas.length ? `
          <div class="proc-rolagem">
            <table class="proc-tabela">
              <thead><tr><th></th><th>Desativar</th><th>Código</th><th>Procedimento</th><th>Valor (R$)</th><th>Remover</th></tr></thead>
              <tbody id="proc-corpo">${linhas.map(renderLinha).join("")}</tbody>
            </table>
          </div>` : `
          <div class="estado-vazio">
            <p>Nenhum procedimento cadastrado.</p>
            <p class="texto-sm texto-suave">Cadastre os procedimentos da clínica (ex.: “Sessão de fonoaudiologia”, R$ 230,00). Depois disso, todo agendamento passa a pedir o procedimento.</p>
          </div>`}
          <div class="linha gap-3" style="flex-wrap:wrap;">
            <button type="button" class="botao botao-secundario" id="proc-nova">+ Nova linha</button>
            <button type="button" class="botao botao-primario" id="proc-salvar">Salvar</button>
          </div>
        </div>`;
        app.innerHTML = renderShellSidebar("#/gestor/procedimentos", "Procedimentos", conteudo);
        anexarEventosShell();
        anexar();
    }

    function anexar() {
        const corpo = document.getElementById("proc-corpo");
        document.getElementById("proc-nova").addEventListener("click", () => {
            linhas.push({ id: null, codigo: "", nome: "", valor: "", ativo: true, emUso: 0 });
            sujo = true;
            render();
            const nomes = document.querySelectorAll(".proc-nome");
            nomes[nomes.length - 1].focus();
        });
        document.getElementById("proc-salvar").addEventListener("click", salvar);
        if (!corpo) return;
        corpo.addEventListener("input", (e) => {
            const i = parseInt(e.target.dataset.i, 10);
            if (Number.isNaN(i)) return;
            sujo = true;
            if (e.target.classList.contains("proc-codigo")) linhas[i].codigo = e.target.value;
            if (e.target.classList.contains("proc-nome")) linhas[i].nome = e.target.value;
            if (e.target.classList.contains("proc-valor")) {
                linhas[i].valor = e.target.value;
                e.target.classList.toggle("proc-erro", !!e.target.value.trim() && reaisParaCentavos(e.target.value) === null);
            }
        });
        corpo.addEventListener("focusout", (e) => {
            if (!e.target.classList.contains("proc-valor")) return;
            const i = parseInt(e.target.dataset.i, 10);
            const centavos = reaisParaCentavos(e.target.value);
            if (centavos !== null) { linhas[i].valor = centavosParaReais(centavos); e.target.value = linhas[i].valor; }
        });
        corpo.addEventListener("change", (e) => {
            if (!e.target.classList.contains("proc-desativar")) return;
            linhas[parseInt(e.target.dataset.i, 10)].ativo = !e.target.checked;
            sujo = true;
            render();
        });
        corpo.addEventListener("click", (e) => {
            const btn = e.target.closest(".proc-remover");
            if (!btn) return;
            linhas.splice(parseInt(btn.dataset.i, 10), 1);
            sujo = true;
            render();
        });
        // Arrastar para reordenar (só pela linha; os campos continuam editáveis).
        corpo.addEventListener("dragstart", (e) => {
            const tr = e.target.closest("tr");
            if (!tr || !e.target.closest(".proc-alca")) { e.preventDefault(); return; }
            arrastando = parseInt(tr.dataset.i, 10);
            tr.classList.add("proc-arrastando");
            e.dataTransfer.effectAllowed = "move";
            try { e.dataTransfer.setData("text/plain", String(arrastando)); } catch (_) { /* alguns navegadores */ }
        });
        corpo.addEventListener("dragover", (e) => { if (arrastando !== null) e.preventDefault(); });
        corpo.addEventListener("drop", (e) => {
            e.preventDefault();
            const tr = e.target.closest("tr");
            if (arrastando === null || !tr) return;
            const destino = parseInt(tr.dataset.i, 10);
            const [item] = linhas.splice(arrastando, 1);
            linhas.splice(destino, 0, item);
            arrastando = null;
            sujo = true;
            render();
        });
        corpo.addEventListener("dragend", () => { arrastando = null; corpo.querySelectorAll(".proc-arrastando").forEach(t => t.classList.remove("proc-arrastando")); });
    }

    async function salvar() {
        const invalida = linhas.find(l => !l.nome.trim() || reaisParaCentavos(l.valor) === null);
        if (invalida) {
            Toast.erro(!invalida.nome.trim() ? "Preencha o nome de todos os procedimentos." : `Valor inválido em “${invalida.nome}” (use, por exemplo, 230,00).`);
            return;
        }
        const botao = document.getElementById("proc-salvar");
        botao.disabled = true;
        try {
            await Api.put("/procedimentos", { procedimentos: linhas.map(l => ({
                id: l.id, codigo: l.codigo.trim(), nome: l.nome.trim(), valor: l.valor, ativo: l.ativo })) });
            Toast.sucesso("Procedimentos salvos!");
            sujo = false;
            viewProcedimentos(app);
        } catch (err) {
            Toast.erro(err.message);
            botao.disabled = false;
        }
    }

    render();
}
