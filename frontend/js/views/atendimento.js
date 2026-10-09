// ============================================================================
// views/atendimento.js — Atender / Evoluir a partir da consulta (08/10/2026)
//
// Página aberta pelo "▶ Atender" do pop-up da consulta (só o profissional da
// consulta e o gestor). Evolução enxuta (descrição, observação, desfecho) e uma
// seção recolhida "Para a família"; tudo vira um registro do Diário ligado à
// consulta. Embaixo, o histórico de todos os atendimentos do paciente.
// ============================================================================

const DESFECHOS_ATENDIMENTO = ["realizada", "faltou", "falta_justificada", "desmarcada_profissional"];

async function viewAtendimento(app, params) {
    const u = Sessao.usuario;
    const base = u.papel === "gestor" ? "gestor" : "profissional";
    let dados;
    try {
        dados = await Api.get(`/agenda/${params.id}/atendimento`);
    } catch (err) {
        app.innerHTML = renderShellSidebar(`#/${base}/agenda`, "Atendimento",
            `<div class="cartao estado-vazio"><p>${escapeHtml(err.message)}</p><a class="botao botao-secundario" href="#/${base}/agenda">← Voltar à agenda</a></div>`);
        anexarEventosShell();
        return;
    }
    const { consulta, paciente, profissional: prof, diario } = dados;
    const d = diario || {};
    const positivos = (d.pontos_positivos || []).slice();
    const atencao = (d.pontos_atencao || []).slice();
    const statusInicial = DESFECHOS_ATENDIMENTO.includes(consulta.status) ? consulta.status : "realizada";
    const temFamilia = !!(d.mensagem_familia || positivos.length || atencao.length || d.objetivo_semana);
    const inicio = minutoDoDia(consulta.data_hora);
    const horario = inicio === null ? "" : `${minutosParaHHMM(inicio)}–${minutosParaHHMM(inicio + (consulta.duracao_min || AGENDA_DURACAO_PADRAO))}`;
    const dia = consulta.data_hora.slice(0, 10);
    const diaSemana = DIAS_SEMANA_ABREV[new Date(dia + "T00:00:00").getDay()].toLowerCase();
    const primeiroNome = (paciente.nome || "").split(" ")[0];
    const registro = [prof.tipo_registro, prof.numero_registro].filter(Boolean).join(" ");

    const conteudo = `
    <div class="cartao atd-cabecalho">
      <div class="atd-avatar">${escapeHtml(emojiMascote(paciente.avatar_mascote, u.organizacao))}</div>
      <div class="atd-identidade">
        <h2>${escapeHtml(paciente.nome)}</h2>
        <p class="texto-sm texto-suave">${escapeHtml(calcularIdade(paciente.data_nascimento))} · ${diaSemana}, ${formatarData(dia)} · ${horario}</p>
        <div class="linha gap-2" style="flex-wrap:wrap; margin-top:6px;">
          ${prof.especialidade ? `<span class="badge badge-neutro">${escapeHtml(etiquetaEspecialidade(prof.especialidade))}</span>` : ""}
          <span class="badge badge-sucesso">Sessão ${dados.sessao_numero}${prof.especialidade ? ` de ${escapeHtml(prof.especialidade)}` : ""}</span>
        </div>
      </div>
    </div>

    ${dados.atraso_dias ? `<p class="aviso-atraso">⚠️ Esta evolução está em atraso (${dados.atraso_dias} ${dados.atraso_dias === 1 ? "dia" : "dias"}). Finalize esta sessão.</p>` : ""}

    <form class="cartao" id="form-atendimento">
      <h3>Evolução de ${escapeHtml(primeiroNome)}${prof.especialidade ? ` em ${escapeHtml(prof.especialidade)}` : ""}</h3>
      <div class="atd-grade">
        <div class="coluna gap-3" style="min-width:0;">
          <div class="campo"><label for="at-descricao">Descrição <span class="texto-xs texto-suave" id="at-descricao-dica">(obrigatória em "Finalizado")</span></label>
            <textarea id="at-descricao" rows="5" placeholder="O que foi trabalhado, como a criança respondeu…">${escapeHtml(d.evolucao_clinica || "")}</textarea>
            <p class="texto-xs texto-suave" style="margin-top:4px;">Fica no histórico clínico — a família nunca vê este campo.</p></div>
          <div class="campo"><label for="at-observacao">Observação</label>
            <textarea id="at-observacao" rows="2" placeholder="Ex.: orientado treino em casa">${escapeHtml(d.observacao || "")}</textarea></div>
        </div>
        <div class="coluna gap-3" style="min-width:0;">
          <div class="campo"><label>Profissional</label>
            <div class="atd-prof">${escapeHtml(prof.nome)}${registro ? ` <span class="texto-xs texto-suave">· ${escapeHtml(registro)}</span>` : ""}</div></div>
          <fieldset class="campo atd-desfechos"><legend>Desfecho ${ASTERISCO_OBRIGATORIO}</legend>
            ${DESFECHOS_ATENDIMENTO.map(s => `
              <label class="atd-desfecho">
                <input type="radio" name="at-status" value="${s}" ${s === statusInicial ? "checked" : ""} />
                <span class="ponto" style="background:${STATUS_CONSULTA_INFO[s].cor};"></span>${escapeHtml(STATUS_CONSULTA_INFO[s].label)}
              </label>`).join("")}
          </fieldset>
        </div>
      </div>

      <details class="atd-familia" ${temFamilia ? "open" : ""}>
        <summary><strong>💛 Para a família</strong> <span class="texto-xs texto-suave">— mensagem, pontos positivos e de atenção, objetivo da semana (opcional)</span></summary>
        <div class="coluna gap-3" style="margin-top:12px;">
          <div class="campo"><label for="at-mensagem">Mensagem para a família</label>
            <textarea id="at-mensagem" rows="2" placeholder="Escreva em linguagem simples e acolhedora — é isso que a família vai ler.">${escapeHtml(d.mensagem_familia || "")}</textarea></div>
          <div class="campo"><label>✔️ Pontos positivos</label><div id="at-wrap-positivos">${renderListaDinamica("lista-at-positivos", positivos, "Ex: Participou bem da sessão")}</div></div>
          <div class="campo"><label>⚠️ Pontos de atenção</label><div id="at-wrap-atencao">${renderListaDinamica("lista-at-atencao", atencao, "Ex: Continuar estimulando frases completas")}</div></div>
          <div class="campo"><label for="at-objetivo">🎯 Objetivo da próxima semana</label><input type="text" id="at-objetivo" value="${escapeHtml(d.objetivo_semana || "")}" /></div>
          <label class="linha gap-2" style="font-size:13.5px;"><input type="checkbox" id="at-compartilhar" ${diario ? (d.compartilhado_familia ? "checked" : "") : "checked"} /> Compartilhar com a família</label>
          <p class="texto-xs texto-suave">Fotos, áudios e vídeos continuam pelo "+ Novo Diário" da ficha.</p>
        </div>
      </details>

      <div class="linha gap-3" style="flex-wrap:wrap;">
        <button type="submit" class="botao botao-primario" id="at-salvar">Salvar atendimento</button>
        <span class="texto-xs texto-suave">Grava no Diário Terapêutico, ligado a esta consulta, e atualiza o status na agenda.</span>
      </div>
    </form>

    <div class="cartao">
      <h3>🕘 Histórico de todos os atendimentos do paciente (${dados.historico.length})</h3>
      ${dados.historico.length ? `
      <div class="atd-tabela-rolagem">
        <table class="atd-tabela">
          <thead><tr><th>Data</th><th>Especialidade</th><th>Descrição</th><th>Profissional</th><th>Status</th></tr></thead>
          <tbody>
            ${dados.historico.map(h => `
              <tr class="${h.consulta_id === consulta.id ? "atual" : ""}">
                <td>${formatarData(String(h.data_hora).slice(0, 10))}</td>
                <td>${escapeHtml(h.especialidade || "—")}</td>
                <td>${h.descricao ? escapeHtml(h.descricao) : ""}${h.observacao ? `<span class="atd-obs">Obs.: ${escapeHtml(h.observacao)}</span>` : ""}${!h.descricao && !h.observacao ? `<span class="texto-suave">—</span>` : ""}</td>
                <td>${escapeHtml(h.profissional_nome || "")}</td>
                <td><span class="linha gap-1" style="align-items:center;"><span class="ponto" style="background:${(STATUS_CONSULTA_INFO[h.status] || {}).cor};"></span>${escapeHtml((STATUS_CONSULTA_INFO[h.status] || {}).label || h.status)}</span></td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>` : `<p class="texto-sm texto-suave">Nenhum atendimento registrado ainda.</p>`}
    </div>`;

    app.innerHTML = renderShellSidebar(`#/${base}/agenda`, "Atendimento", conteudo, `
        <a href="#/${base}/paciente/${paciente.id}" class="botao botao-secundario botao-sm">Ficha do paciente</a>
        <a href="#/${base}/agenda" class="botao botao-secundario botao-sm">← Voltar à agenda</a>`);
    anexarEventosShell();

    ativarListaDinamica(document.getElementById("at-wrap-positivos"), positivos);
    ativarListaDinamica(document.getElementById("at-wrap-atencao"), atencao);

    document.getElementById("form-atendimento").addEventListener("submit", async (e) => {
        e.preventDefault();
        const status = (document.querySelector('input[name="at-status"]:checked') || {}).value;
        const descricao = document.getElementById("at-descricao").value.trim();
        if (status === "realizada" && !descricao) { Toast.erro("Descreva a sessão para finalizar o atendimento."); return; }
        const botao = document.getElementById("at-salvar");
        botao.disabled = true;
        try {
            await Api.put(`/agenda/${consulta.id}/atendimento`, {
                status, descricao,
                observacao: document.getElementById("at-observacao").value.trim(),
                familia: {
                    mensagem: document.getElementById("at-mensagem").value.trim(),
                    pontos_positivos: positivos, pontos_atencao: atencao,
                    objetivo_semana: document.getElementById("at-objetivo").value.trim(),
                    compartilhar: document.getElementById("at-compartilhar").checked,
                },
            });
            Toast.sucesso("Atendimento salvo!");
            location.hash = `#/${base}/agenda`;
        } catch (err) {
            Toast.erro(err.message);
            botao.disabled = false;
        }
    });
}
