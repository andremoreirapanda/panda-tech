// ============================================================================
// Agenda — faixa horária da grade "Por Profissional" (spec 24/09/2026)
//
// Funções puras (sem DOM) usadas por views/agenda.js: qual faixa de horário
// a grade mostra, onde cada consulta cai nela e qual horário corresponde a
// um clique. Ficam separadas pra poderem ser testadas com `node --test`
// (frontend/tests/agenda_faixa.test.js) — no navegador viram globais, como
// o resto do front-end.
// ============================================================================

const AGENDA_FAIXA_PADRAO = { ini: 8 * 60, fim: 18 * 60 }; // mínimo do modo automático
const AGENDA_PASSO_MIN = 15;       // clique/arraste encaixam de 15 em 15 min (combina com horário picado)
const AGENDA_DURACAO_PADRAO = 50;  // mesmo padrão de consultas.duracao_min no backend

function hhmmParaMinutos(hhmm) {
    const m = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(hhmm || "");
    return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : null;
}

// Minuto do dia do horário de uma consulta ("YYYY-MM-DD HH:MM:SS"). Aceita
// hora sem zero à esquerda ("2026-09-24 9:00:00" — existe em dados antigos
// e no seed): a grade antiga tolerava, e uma consulta assim não pode sumir.
function minutoDoDia(dataHora) {
    const m = /[ T](\d{1,2}):(\d{2})/.exec(String(dataHora || ""));
    if (!m) return null;
    const h = parseInt(m[1], 10), mi = parseInt(m[2], 10);
    return h < 24 && mi < 60 ? h * 60 + mi : null;
}

function minutosParaHHMM(minutos) {
    const t = ((minutos % 1440) + 1440) % 1440;
    return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
}

// Faixa exibida, em minutos do dia. Com horário da clínica válido, usa ele no
// minuto exato (08:10–19:15 fica 08:10–19:15); sem ele, parte de 08:00–18:00.
// Nos dois casos, consulta fora da faixa estica a faixa até a hora cheia mais
// próxima — nada fica escondido. Horário incompleto/invertido (dado antigo ou
// gravado antes da validação) cai no automático em vez de quebrar a grade.
function calcularFaixaAgenda(consultas, horaInicioClinica, horaFimClinica) {
    const iniClinica = hhmmParaMinutos(horaInicioClinica);
    const fimClinica = hhmmParaMinutos(horaFimClinica);
    const temHorario = iniClinica !== null && fimClinica !== null && iniClinica < fimClinica;
    let ini = temHorario ? iniClinica : AGENDA_FAIXA_PADRAO.ini;
    let fim = temHorario ? fimClinica : AGENDA_FAIXA_PADRAO.fim;
    (consultas || []).forEach(c => {
        const inicioConsulta = minutoDoDia(c && c.data_hora);
        if (inicioConsulta === null) return;
        const fimConsulta = Math.min(1440, inicioConsulta + (c.duracao_min || AGENDA_DURACAO_PADRAO));
        if (inicioConsulta < ini) ini = Math.floor(inicioConsulta / 60) * 60;
        if (fimConsulta > fim) fim = Math.min(1440, Math.ceil(fimConsulta / 60) * 60);
    });
    return { ini, fim };
}

// Posição vertical (px dentro da coluna) -> horário, de 15 em 15 min, para
// baixo (clicar em 09:10 abre 09:00), preso entre a abertura e o último
// passo antes do fechamento.
function minutoNaFaixa(yPx, alturaPx, faixa) {
    const bruto = faixa.ini + (yPx / alturaPx) * (faixa.fim - faixa.ini);
    const passo = Math.floor(bruto / AGENDA_PASSO_MIN) * AGENDA_PASSO_MIN;
    const ultimo = Math.max(faixa.ini, Math.ceil(faixa.fim / AGENDA_PASSO_MIN) * AGENDA_PASSO_MIN - AGENDA_PASSO_MIN);
    return Math.min(Math.max(passo, faixa.ini), ultimo);
}

// Semana da grade é segunda a sábado; domingo só entra se tiver consulta.
function precisaDomingo(chaveDomingo, consultas) {
    return (consultas || []).some(c => String(c.data_hora || "").slice(0, 10) === chaveDomingo);
}

// Chave "YYYY-MM-DD" pela data LOCAL. Antes usava toISOString() (UTC), que
// depois das 21h em Brasília já apontava para o dia seguinte.
function paraChaveDia(data) {
    return `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, "0")}-${String(data.getDate()).padStart(2, "0")}`;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        AGENDA_FAIXA_PADRAO, AGENDA_PASSO_MIN, AGENDA_DURACAO_PADRAO,
        hhmmParaMinutos, minutoDoDia, minutosParaHHMM, calcularFaixaAgenda, minutoNaFaixa, precisaDomingo, paraChaveDia,
    };
}
