// ============================================================================
// views/agenda_ausencia_modal.js — pop-up de Ausência (spec 07/10/2026)
//
// Lançar, editar, apagar ou só ver uma ausência do profissional. Uma ausência
// é uma regra (período + horário + dias da semana); editar/apagar mexe nela
// inteira. As regras de bloqueio ficam no backend (ausencias_service.py).
// ============================================================================

const DIAS_AUSENCIA = [["1", "Seg"], ["2", "Ter"], ["3", "Qua"], ["4", "Qui"], ["5", "Sex"], ["6", "Sáb"], ["0", "Dom"]];

function renderSeletorTipoAgendamento(tipoAtivo) {
    return `
    <div class="linha gap-2" style="margin-bottom:14px;">
      <button type="button" class="botao botao-sm ${tipoAtivo === "consulta" ? "botao-primario" : "botao-secundario"} btn-tipo-agendamento" data-tipo="consulta">📅 Consulta</button>
      <button type="button" class="botao botao-sm ${tipoAtivo === "ausencia" ? "botao-primario" : "botao-secundario"} btn-tipo-agendamento" data-tipo="ausencia">⛔ Ausência</button>
    </div>`;
}

function _textoPeriodoAusencia(o) {
    const periodo = o.data_fim
        ? (o.data_fim === o.data_inicio ? formatarData(o.data_inicio) : `${formatarData(o.data_inicio)} a ${formatarData(o.data_fim)}`)
        : `a partir de ${formatarData(o.data_inicio)}, sem fim`;
    const horario = o.dia_inteiro ? "dia inteiro" : `${o.hora_inicio}–${o.hora_fim}`;
    const dias = DIAS_AUSENCIA.filter(([v]) => String(o.dias_semana || "").includes(v)).map(([, n]) => n).join(", ");
    return `${periodo} · ${horario} · ${dias}`;
}

function _mostrarConsultasNoPeriodo(lista) {
    if (!lista || !lista.length) return;
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:8px;">Há ${lista.length} ${lista.length === 1 ? "consulta" : "consultas"} nesse período</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:12px;">A ausência foi salva. Remarque ou cancele estas consultas na agenda:</p>
        <ul class="texto-sm" style="margin:0 0 16px 18px;">
          ${lista.map(c => `<li>${escapeHtml(formatarDataHoraLocal(c.data_hora))} — ${escapeHtml(c.paciente_nome || "")}</li>`).join("")}
        </ul>
        <button type="button" class="botao botao-primario" id="btn-ok-consultas-periodo" style="width:100%;">Entendi</button>
      </div>
    </div>`);
    document.body.appendChild(modal);
    document.getElementById("btn-ok-consultas-periodo").addEventListener("click", () => modal.remove());
}

// pre: {profissionalId, data, hora} para lançar; {ocorrencia} (item do GET
// /agenda/ausencias) para editar — ou só ver, quando não pode editar.
async function abrirModalAusencia(pre, aoAtualizar) {
    const atualizar = aoAtualizar || despachar;
    const u = Sessao.usuario;
    const o = pre.ocorrencia || null;
    const editando = !!o;

    if (editando && !o.pode_editar) {
        const modal = el(`
        <div class="modal-fundo"><div class="modal-caixa">
          <h3 style="margin-bottom:6px;">⛔ ${escapeHtml(o.profissional_nome || "Profissional")} ausente</h3>
          <p class="texto-sm" style="margin-bottom:6px;">${escapeHtml(o.motivo || "Sem motivo informado")}</p>
          <p class="texto-xs texto-suave" style="margin-bottom:16px;">${escapeHtml(_textoPeriodoAusencia(o))}</p>
          <button type="button" class="botao botao-secundario" id="btn-fechar-ausencia" style="width:100%;">Fechar</button>
        </div></div>`);
        document.body.appendChild(modal);
        document.getElementById("btn-fechar-ausencia").addEventListener("click", () => modal.remove());
        return;
    }

    const ehProfissionalComum = u.papel === "profissional";
    const profissionais = ehProfissionalComum ? [{ id: u.id, nome: u.nome, especialidade: u.especialidade }]
        : await Api.get("/pessoas/profissionais?incluir_gestor=1");
    const profId = o ? o.profissional_id : (pre.profissionalId || (ehProfissionalComum ? u.id : profissionais[0] && profissionais[0].id));
    const dataIni = o ? o.data_inicio : (pre.data || paraChaveDia(new Date()));
    // Lançamento novo começa num dia só: "sem fim" precisa ser escolhido de propósito.
    const dataFim = o ? (o.data_fim || "") : dataIni;
    const diaInteiro = o ? !!o.dia_inteiro : false;
    const horaIni = o ? (o.hora_inicio || "12:00") : (pre.hora || "12:00");
    const horaFim = o ? (o.hora_fim || "13:00") : calcularFim(horaIni, 60);
    const dias = o ? String(o.dias_semana || "") : diasSemanaPadrao(dataIni, dataFim);
    // No editar, a lista pode não ter o profissional (ex.: arquivado depois).
    const opcoesProf = profissionais.some(p => p.id === profId) ? profissionais
        : [{ id: profId, nome: o && o.profissional_nome || "Profissional" }, ...profissionais];

    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:14px;">${editando ? "Editar ausência" : "Agendar"}</h3>
        ${editando ? "" : renderSeletorTipoAgendamento("ausencia")}
        <form id="form-ausencia">
          <div class="campo"><label>Profissional ${ASTERISCO_OBRIGATORIO}</label>
            <select id="au-profissional" ${ehProfissionalComum || editando ? "disabled" : ""}>
              ${opcoesProf.map(p => `<option value="${p.id}" ${p.id === profId ? "selected" : ""}>${escapeHtml(p.nome)}${p.especialidade ? ` (${escapeHtml(p.especialidade)})` : ""}</option>`).join("")}
            </select>
          </div>
          <div class="linha gap-4">
            <div class="campo" style="flex:1;"><label>De ${ASTERISCO_OBRIGATORIO}</label><input type="date" id="au-data-inicio" required value="${escapeHtml(dataIni)}" /></div>
            <div class="campo" style="flex:1;"><label>Até <span class="texto-xs texto-suave">(vazio = sem fim)</span></label><input type="date" id="au-data-fim" value="${escapeHtml(dataFim)}" /></div>
          </div>
          <label class="linha gap-2" style="align-items:center; cursor:pointer; margin-bottom:10px;">
            <input type="checkbox" id="au-dia-inteiro" ${diaInteiro ? "checked" : ""} /> <span class="texto-sm">Dia inteiro</span>
          </label>
          <div class="linha gap-4" id="au-wrap-horas" style="${diaInteiro ? "display:none;" : ""}">
            <div class="campo" style="flex:1;"><label>Das</label><input type="time" id="au-hora-inicio" value="${escapeHtml(horaIni)}" /></div>
            <div class="campo" style="flex:1;"><label>Até</label><input type="time" id="au-hora-fim" value="${escapeHtml(horaFim)}" /></div>
          </div>
          <div class="campo"><label>Dias da semana</label>
            <div class="linha gap-2" style="flex-wrap:wrap;" id="au-dias">
              ${DIAS_AUSENCIA.map(([v, n]) => `<label class="linha gap-1" style="align-items:center; cursor:pointer;"><input type="checkbox" value="${v}" ${dias.includes(v) ? "checked" : ""} /><span class="texto-sm">${n}</span></label>`).join("")}
            </div>
          </div>
          <div class="campo"><label>Motivo</label><input type="text" id="au-motivo" maxlength="120" placeholder="Ex.: Almoço, Férias, Curso" value="${escapeHtml(o ? (o.motivo || "") : "")}" /></div>
          <div class="linha gap-3" style="margin-top:16px; flex-wrap:wrap;">
            <button type="submit" class="botao botao-primario">${editando ? "Salvar alterações" : "Salvar ausência"}</button>
            ${editando ? `<button type="button" class="botao botao-secundario" id="btn-apagar-ausencia">🗑️ Apagar ausência</button>` : ""}
            <button type="button" class="botao botao-secundario" id="btn-cancelar-ausencia">Cancelar</button>
          </div>
        </form>
      </div>
    </div>`);
    document.body.appendChild(modal);
    const fechar = () => modal.remove();
    document.getElementById("btn-cancelar-ausencia").addEventListener("click", fechar);
    document.getElementById("au-dia-inteiro").addEventListener("change", (e) => {
        document.getElementById("au-wrap-horas").style.display = e.target.checked ? "none" : "";
    });
    // Sem dias marcados à mão, as datas sugerem os dias (um dia só → o dia dele).
    let diasTocados = editando;
    document.querySelectorAll("#au-dias input").forEach(cb => cb.addEventListener("change", () => { diasTocados = true; }));
    const sugerirDias = () => {
        if (diasTocados) return;
        const sug = diasSemanaPadrao(document.getElementById("au-data-inicio").value, document.getElementById("au-data-fim").value);
        document.querySelectorAll("#au-dias input").forEach(cb => { cb.checked = sug.includes(cb.value); });
    };
    document.getElementById("au-data-inicio").addEventListener("change", sugerirDias);
    document.getElementById("au-data-fim").addEventListener("change", sugerirDias);

    modal.querySelectorAll(".btn-tipo-agendamento").forEach(btn => btn.addEventListener("click", () => {
        if (btn.dataset.tipo !== "consulta") return;
        const prof = parseInt(document.getElementById("au-profissional").value, 10);
        const pre2 = { profissionalId: prof, data: document.getElementById("au-data-inicio").value, hora: document.getElementById("au-hora-inicio").value };
        fechar();
        abrirModalNovaConsulta(pre2, atualizar);
    }));

    if (editando) {
        document.getElementById("btn-apagar-ausencia").addEventListener("click", async () => {
            if (!confirm("Apagar esta ausência inteira (todas as datas dela)?")) return;
            try {
                await Api.del(`/agenda/ausencias/${o.ausencia_id}`);
                Toast.sucesso("Ausência apagada.");
                fechar();
                atualizar();
            } catch (err) { Toast.erro(err.message); }
        });
    }

    document.getElementById("form-ausencia").addEventListener("submit", async (e) => {
        e.preventDefault();
        const corpo = {
            profissional_id: parseInt(document.getElementById("au-profissional").value, 10),
            data_inicio: document.getElementById("au-data-inicio").value,
            data_fim: document.getElementById("au-data-fim").value,
            dia_inteiro: document.getElementById("au-dia-inteiro").checked,
            hora_inicio: document.getElementById("au-hora-inicio").value,
            hora_fim: document.getElementById("au-hora-fim").value,
            dias_semana: Array.from(document.querySelectorAll("#au-dias input:checked")).map(cb => cb.value).join(""),
            motivo: document.getElementById("au-motivo").value.trim(),
        };
        try {
            const r = editando ? await Api.put(`/agenda/ausencias/${o.ausencia_id}`, corpo) : await Api.post("/agenda/ausencias", corpo);
            Toast.sucesso(editando ? "Ausência atualizada!" : "Ausência salva!");
            fechar();
            atualizar();
            _mostrarConsultasNoPeriodo(r.consultas_no_periodo);
        } catch (err) { Toast.erro(err.message); }
    });
}
