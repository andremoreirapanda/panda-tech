// formatarData (util.js) com data SEM horário (24/09/2026): "2026-09-20" era
// lido como meia-noite UTC e aparecia como 19/09 no Brasil (cabeçalho da
// semana da agenda, toast de remarcação, datas do diário...).
// Rodar: node --test frontend/tests/*.test.js
process.env.TZ = "America/Sao_Paulo";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ctx = { console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, "../js/util.js"), "utf8"), ctx);

test("data sem horário mostra o próprio dia", () => {
    assert.equal(ctx.formatarData("2026-09-20"), "20/09/2026");
    assert.equal(ctx.formatarData("2026-01-01"), "01/01/2026");
});

test("timestamp UTC continua convertido para o fuso local", () => {
    // 02:00 UTC do dia 20 = 23:00 do dia 19 em Brasília (comportamento de agosto/2026, mantido)
    assert.equal(ctx.formatarData("2026-09-20 02:00:00"), "19/09/2026");
});

// Lista lateral da agenda (24/09/2026) passou a mostrar o avatar de OUTROS
// usuários — o emoji do avatar precisa sair escapado, como os demais campos.
test("renderAvatarUsuario escapa o avatar_emoji", () => {
    const html = ctx.renderAvatarUsuario({ avatar_emoji: '<img src=x onerror="alert(1)">' }, 30);
    assert.ok(!html.includes("<img src=x"), html);
    assert.ok(html.includes("&lt;img"), html);
    assert.ok(ctx.renderAvatarUsuario({ avatar_emoji: "🦊" }, 30).includes("🦊"));
});

// Pedido do usuário (30/09/2026): missão com prazo esgotado some das telas da
// criança e do responsável. "Hoje" é a data local (não UTC).
test("missaoAtivaVisivel: pendente/iniciada dentro do prazo", () => {
    const hoje = new Date(2026, 8, 30, 22, 30); // 30/09 22:30 no Brasil (já é 01/10 em UTC)
    assert.equal(ctx.missaoAtivaVisivel({ status: "pendente", prazo: "2026-09-30" }, hoje), true);
    assert.equal(ctx.missaoAtivaVisivel({ status: "iniciada", prazo: "2026-10-05" }, hoje), true);
    assert.equal(ctx.missaoAtivaVisivel({ status: "pendente", prazo: null }, hoje), true);
    assert.equal(ctx.missaoAtivaVisivel({ status: "pendente", prazo: "2026-09-29" }, hoje), false);
    assert.equal(ctx.missaoAtivaVisivel({ status: "concluida", prazo: "2026-10-05" }, hoje), false);
    assert.equal(ctx.missaoAtivaVisivel({ status: "rascunho", prazo: "2026-10-05" }, hoje), false);
});

// Agenda (01/10/2026): `consultas.data_hora` é horário LOCAL da clínica
// ("2026-10-01 09:00:00"), não UTC — a Lista do modo Geral mostrava 3 h a mais.
test("horário de consulta (local) não é convertido de UTC", () => {
    assert.equal(ctx.formatarDataHoraLocal("2026-10-01 09:00:00"), "01/10/2026 às 09:00");
    assert.equal(ctx.formatarDataHoraLocal("2026-10-01 23:30:00"), "01/10/2026 às 23:30");
    assert.equal(ctx.formatarDataHoraLocal("2026-10-01 9:05:00"), "01/10/2026 às 09:05");   // hora sem zero (seed)
    assert.equal(ctx.formatarDataHoraLocal("2026-10-01T14:00"), "01/10/2026 às 14:00");
    assert.equal(ctx.formatarDataHoraLocal(""), "-");
    assert.equal(ctx.formatarDataHoraLocal("lixo"), "lixo");
});

test("hora curta de consulta (local), com ou sem zero à esquerda", () => {
    assert.equal(ctx.formatarHoraLocal("2026-10-01 09:00:00"), "09:00");
    assert.equal(ctx.formatarHoraLocal("2026-10-01 9:05:00"), "09:05");
    assert.equal(ctx.formatarHoraLocal(""), "");
});
