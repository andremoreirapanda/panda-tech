// O produto se chama PandaUp em tudo o que o usuário vê (spec 12/10/2026).
// Comentários podem continuar citando o nome antigo.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const FRONT = path.join(__dirname, "..");

function arquivos(dir) {
    return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => {
        const p = path.join(dir, e.name);
        if (e.isDirectory()) return e.name === "vendor" ? [] : arquivos(p);
        return p.endsWith(".js") ? [p] : [];
    });
}

function semComentarios(texto) {
    return texto
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/<!--[\s\S]*?-->/g, "")
        .split(/\r?\n/).map(l => l.replace(/(^|\s)\/\/.*$/, "")).join("\n");
}

test("nenhum texto do front diz 'Panda Tech'", () => {
    const lista = [...arquivos(path.join(FRONT, "js")), path.join(FRONT, "index.html")];
    const achados = lista.filter(p => semComentarios(fs.readFileSync(p, "utf8")).includes("Panda Tech"))
        .map(p => path.relative(FRONT, p));
    assert.deepEqual(achados, []);
});
