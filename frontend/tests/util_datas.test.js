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
