// App instalável (29/10/2026): como orientar a família a pôr o PandaUp na tela inicial.
// Rodar: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const i = require("../js/instalar_app.js");

const IPHONE_SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1";
const IPHONE_CHROME = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/126.0 Mobile/15E148 Safari/604.1";
const IPHONE_INSTAGRAM = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 340.0";
const IPAD = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15";
const ANDROID = "Mozilla/5.0 (Linux; Android 14; SM-A546E) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36";
const WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36";

test("comoInstalar: cada celular recebe o caminho certo", () => {
    assert.equal(i.comoInstalar({ userAgent: IPHONE_SAFARI }), "iphone");
    assert.equal(i.comoInstalar({ userAgent: IPHONE_CHROME }), "iphone");
    assert.equal(i.comoInstalar({ userAgent: IPHONE_INSTAGRAM }), "iphone-outro-app");
    assert.equal(i.comoInstalar({ userAgent: IPAD, toque: true }), "iphone");
    assert.equal(i.comoInstalar({ userAgent: IPAD, toque: false }), "computador");
    assert.equal(i.comoInstalar({ userAgent: ANDROID, temPrompt: true }), "android");
    assert.equal(i.comoInstalar({ userAgent: ANDROID, temPrompt: false }), "android-menu");
    assert.equal(i.comoInstalar({ userAgent: WINDOWS }), "computador");
    assert.equal(i.comoInstalar({}), "computador");
});

test("comoInstalar: já aberto pelo ícone = instalado", () => {
    assert.equal(i.comoInstalar({ userAgent: IPHONE_SAFARI, standalone: true }), "instalado");
    assert.equal(i.comoInstalar({ userAgent: ANDROID, temPrompt: true, standalone: true }), "instalado");
});

test("mostrarConvite: só no celular, sem instalar e sem dispensar", () => {
    assert.equal(i.mostrarConvite("iphone", false), true);
    assert.equal(i.mostrarConvite("android-menu", false), true);
    assert.equal(i.mostrarConvite("iphone", true), false);
    assert.equal(i.mostrarConvite("instalado", false), false);
    assert.equal(i.mostrarConvite("computador", false), false);
});

test("passos do iPhone e do Android falam a língua da família", () => {
    const iphone = i.passosInstalar("iphone").join(" ");
    assert.match(iphone, /Compartilhar/);
    assert.match(iphone, /Adicionar à Tela de Início/);
    assert.match(i.passosInstalar("iphone-outro-app").join(" "), /Safari/);
    assert.match(i.passosInstalar("android-menu").join(" "), /Instalar app|Adicionar à tela inicial/);
    assert.deepEqual(i.passosInstalar("computador"), []);
});
