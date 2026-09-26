// ============================================================================
// envio_arquivos.js — padronização dos envios de arquivo (25/09/2026)
//
// Cada campo de envio mostra, antes do envio, formato + dimensão ideal +
// tamanho máximo, e imagens são reduzidas no navegador (antes, foto de
// celular acima de 2 MB era simplesmente recusada). Parte pura (sem DOM)
// testada em frontend/tests/envio_arquivos.test.js; a parte com canvas
// fica no fim do arquivo.
// ============================================================================

const _MB = 1024 * 1024;
const _TIPOS_IMAGEM = ["jpeg", "png", "webp"];
const _DICA_HEIC = "Essa foto está em HEIC (formato do iPhone). Envie em JPG, PNG ou WebP — no iPhone, Compartilhar → Salvar como JPEG resolve.";

const PERFIS_ENVIO = {
    foto: {
        texto: "📐 JPG, PNG ou WebP · ideal 400 × 400 px (quadrada) · até 15 MB",
        tiposAceitos: _TIPOS_IMAGEM, maxImagemMB: 15, maxOutrosMB: 0,
        ladoMax: 400, limiteSaidaKB: 300, manterTransparencia: false, ladoMinAviso: 200,
    },
    logo: {
        texto: "📐 PNG com fundo transparente (ou JPG/WebP) · ideal 512 × 512 px (quadrado) ou 1024 × 512 px (horizontal) · até 15 MB",
        tiposAceitos: _TIPOS_IMAGEM, maxImagemMB: 15, maxOutrosMB: 0,
        ladoMax: 1024, limiteSaidaKB: 1536, manterTransparencia: true, ladoMinAviso: 128,
    },
    midia: {
        texto: "📐 Imagem: JPG, PNG ou WebP · ideal 1280 × 720 px · GIF até 4 MB · 🎬 Vídeo: MP4 ou WebM · 🎧 Áudio: MP3 ou M4A · 📄 PDF · até 4 MB (vídeos maiores: use link do YouTube)",
        tiposAceitos: [..._TIPOS_IMAGEM, "gif", "video", "audio", "pdf"], maxImagemMB: 15, maxOutrosMB: 4,
        ladoMax: 1920, limiteSaidaKB: 3584, manterTransparencia: false, ladoMinAviso: 256,
    },
    anexo: {
        texto: "📐 Foto: JPG, PNG, WebP ou GIF · 🎬 Vídeo: MP4 ou WebM · 🎧 Áudio: MP3 ou M4A · até 4 MB",
        tiposAceitos: [..._TIPOS_IMAGEM, "gif", "video", "audio"], maxImagemMB: 15, maxOutrosMB: 4,
        ladoMax: 1920, limiteSaidaKB: 3584, manterTransparencia: false, ladoMinAviso: 256,
    },
    // White Label completo (25/09/2026): ícone do app e mascote da clínica.
    icone: {
        texto: "📐 PNG com fundo transparente, JPG ou WebP · ideal 512 × 512 px (quadrado) · até 15 MB",
        tiposAceitos: _TIPOS_IMAGEM, maxImagemMB: 15, maxOutrosMB: 0,
        ladoMax: 512, limiteSaidaKB: 480, manterTransparencia: true, ladoMinAviso: 192,
    },
    // Imagem de cenário da clínica (fundo do Mundo da Criança e do Pandoo).
    cenario: {
        texto: "📐 JPG, PNG ou WebP · ideal 1600 × 1600 px (quadrada) · até 15 MB · deixe o mais importante no centro",
        tiposAceitos: _TIPOS_IMAGEM, maxImagemMB: 15, maxOutrosMB: 0,
        ladoMax: 1600, limiteSaidaKB: 780, manterTransparencia: false, ladoMinAviso: 800,
    },
    // Pandoo (25/09/2026): figuras do jogo e voz gravada da figura.
    figura: {
        texto: "📐 JPG, PNG ou WebP · ideal 512 × 512 px (quadrada) · até 5 MB",
        tiposAceitos: _TIPOS_IMAGEM, maxImagemMB: 5, maxOutrosMB: 0,
        ladoMax: 512, limiteSaidaKB: 300, manterTransparencia: false, ladoMinAviso: 200,
    },
    voz: {
        texto: "🎙️ MP3, M4A, OGG, WAV ou WebM · até 30 segundos · até 600 KB",
        tiposAceitos: ["audio"], maxImagemMB: 0, maxOutrosMB: 600 / 1024,
        ladoMax: 0, limiteSaidaKB: 0, manterTransparencia: false, ladoMinAviso: 0,
    },
    planilha: {
        texto: "📄 Planilha XLSX ou CSV · use o modelo desta tela",
        tiposAceitos: ["planilha"], maxImagemMB: 0, maxOutrosMB: 10,
        ladoMax: 0, limiteSaidaKB: 0, manterTransparencia: false, ladoMinAviso: 0,
    },
};

const _EXTENSOES = {
    jpg: "jpeg", jpeg: "jpeg", jfif: "jpeg", png: "png", webp: "webp", gif: "gif",
    heic: "heic", heif: "heic",
    mp4: "video", m4v: "video", mov: "video", webm: "video",
    mp3: "audio", m4a: "audio", aac: "audio", ogg: "audio", oga: "audio", wav: "audio", opus: "audio",
    pdf: "pdf", xlsx: "planilha", xlsm: "planilha", csv: "planilha",
};

// Alguns seletores de arquivo do Android mandam `type` vazio — por isso a
// extensão é a segunda fonte.
function formatoDoArquivo(file) {
    const tipo = String((file && file.type) || "").toLowerCase();
    if (tipo === "image/jpeg" || tipo === "image/jpg") return "jpeg";
    if (tipo === "image/png") return "png";
    if (tipo === "image/webp") return "webp";
    if (tipo === "image/gif") return "gif";
    if (tipo === "image/heic" || tipo === "image/heif") return "heic";
    if (tipo.startsWith("video/")) return "video";
    if (tipo.startsWith("audio/")) return "audio";
    if (tipo === "application/pdf") return "pdf";
    const ext = String((file && file.name) || "").split(".").pop().toLowerCase();
    return _EXTENSOES[ext] || "outro";
}

function _textoLimite(perfil) {
    return `Confira a orientação do campo: ${perfil.texto.replace(/^(📐|📄|🎙️)\s*/u, "")}`;
}

// Limites abaixo de 1 MB (voz do Pandoo) aparecem em KB: "passa de 600 KB".
function _rotuloTamanho(mb) {
    return mb >= 1 ? `${mb} MB` : `${Math.round(mb * 1024)} KB`;
}

function validarEntradaEnvio(file, perfilNome) {
    const perfil = PERFIS_ENVIO[perfilNome];
    const formato = formatoDoArquivo(file);
    if (formato === "heic") return { ok: false, erro: _DICA_HEIC };
    if (!perfil.tiposAceitos.includes(formato)) {
        return { ok: false, erro: `"${file.name}" não é um formato aceito aqui. ${_textoLimite(perfil)}` };
    }
    const ehImagem = _TIPOS_IMAGEM.includes(formato);
    const maxMB = ehImagem ? perfil.maxImagemMB : perfil.maxOutrosMB;
    if (file.size > maxMB * _MB) {
        // Só a Biblioteca aceita link; no Diário e no chat a dica confundiria.
        const dicaVideo = formato === "video" && perfilNome === "midia" ? " Para vídeos maiores, use um link do YouTube." : "";
        return { ok: false, erro: `"${file.name}" passa de ${_rotuloTamanho(maxMB)}.${dicaVideo} ${_textoLimite(perfil)}` };
    }
    return { ok: true, formato };
}

// GIF é imagem para quem recebe (Diário/chat/Biblioteca), mas não passa pela
// redução: o canvas congelaria a animação no primeiro quadro.
function categoriaEnvio(formato) {
    return [..._TIPOS_IMAGEM, "gif"].includes(formato) ? "imagem" : formato;
}

function dimensoesReduzidas(largura, altura, ladoMax) {
    const escala = Math.min(1, ladoMax / Math.max(largura, altura));
    return { largura: Math.round(largura * escala), altura: Math.round(altura * escala) };
}

// Só o logo guarda transparência (PNG/WebP); o resto vira JPEG, bem menor.
function formatoSaidaImagem(perfilNome, formatoEntrada) {
    if (PERFIS_ENVIO[perfilNome].manterTransparencia) {
        if (formatoEntrada === "png") return "image/png";
        if (formatoEntrada === "webp") return "image/webp";
    }
    return "image/jpeg";
}

function avisoImagemPequena(largura, altura, perfilNome) {
    const minimo = PERFIS_ENVIO[perfilNome].ladoMinAviso;
    if (!minimo || Math.min(largura, altura) >= minimo) return null;
    return `A imagem tem ${largura} × ${altura} px e pode ficar borrada — mas pode usar, se quiser.`;
}

function nomeComExtensao(nome, mime) {
    const ext = { "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp" }[mime];
    const base = String(nome || "imagem").replace(/\.[^.]+$/, "");
    return `${base}.${ext}`;
}

// ---------------------------------------------------------------- Parte com DOM/canvas (verificada no navegador)

function renderOrientacaoEnvio(perfilNome) {
    return `<p class="orientacao-envio">${escapeHtml(PERFIS_ENVIO[perfilNome].texto)}</p>`;
}

function lerArquivoBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = () => reject(new Error(`Não foi possível ler "${file.name || "o arquivo"}".`));
        reader.readAsDataURL(file);
    });
}

// A CSP do app (img-src 'self' data:) bloqueia URLs blob:, então nada de
// URL.createObjectURL aqui: createImageBitmap decodifica direto do arquivo
// (não é "carregar imagem" para a CSP) e, onde não existir, cai num data:.
// Devolve {fonte, largura, altura} — `fonte` serve para drawImage.
async function decodificarImagem(file) {
    const erro = () => new Error(`Não foi possível abrir "${file.name}" como imagem. ${PERFIS_ENVIO.foto.texto.replace(/ · ideal.*$/, "")}`);
    if (typeof createImageBitmap === "function") {
        try {
            // from-image: aplica a rotação do EXIF (foto de celular em pé);
            // navegadores antigos não aplicavam sem pedir.
            const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
            return { fonte: bmp, largura: bmp.width, altura: bmp.height };
        } catch (e) { /* tenta pelo caminho do data: abaixo */ }
    }
    const dataUrl = `data:${file.type || "image/jpeg"};base64,${await lerArquivoBase64(file)}`;
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve({ fonte: img, largura: img.naturalWidth, altura: img.naturalHeight });
        img.onerror = () => reject(erro());
        img.src = dataUrl;
    });
}

function _canvasParaBlob(canvas, mime, qualidade) {
    return new Promise(resolve => canvas.toBlob(resolve, mime, qualidade));
}

// Reduz para o lado máximo do perfil e comprime até caber no limite. Imagem
// que já está pequena e leve no formato certo segue como veio (não adianta
// recomprimir e às vezes até aumenta).
async function prepararImagemParaEnvio(file, perfilNome) {
    const perfil = PERFIS_ENVIO[perfilNome];
    const validacao = validarEntradaEnvio(file, perfilNome);
    if (!validacao.ok) throw new Error(validacao.erro);
    const img = await decodificarImagem(file);
    const { largura, altura } = dimensoesReduzidas(img.largura, img.altura, perfil.ladoMax);
    const aviso = avisoImagemPequena(img.largura, img.altura, perfilNome);
    const mime = formatoSaidaImagem(perfilNome, validacao.formato);
    const limiteBytes = perfil.limiteSaidaKB * 1024;

    const jaServe = largura === img.largura && file.size <= limiteBytes && `image/${validacao.formato}` === mime;
    if (jaServe) {
        return { base64: await lerArquivoBase64(file), nome: file.name, mime, largura, altura, aviso };
    }

    const canvas = document.createElement("canvas");
    canvas.width = largura;
    canvas.height = altura;
    const ctx = canvas.getContext("2d");
    // JPEG não tem transparência: sem isto, áreas transparentes viram preto.
    if (mime === "image/jpeg") { ctx.fillStyle = "#FFFFFF"; ctx.fillRect(0, 0, largura, altura); }
    ctx.drawImage(img.fonte, 0, 0, largura, altura);
    if (img.fonte.close) img.fonte.close(); // libera a memória do ImageBitmap

    const tentativas = mime === "image/png"
        ? [["image/png", undefined], ["image/webp", 0.9], ["image/webp", 0.75]]
        : [[mime, 0.85], [mime, 0.72], [mime, 0.6]];
    for (const [formato, qualidade] of tentativas) {
        const blob = await _canvasParaBlob(canvas, formato, qualidade);
        // toBlob devolve PNG quando o navegador não sabe gerar o formato pedido
        // (ex.: WebP em Safari antigo) — só aceita o blob se o tipo bater.
        if (blob && blob.type === formato && blob.size <= limiteBytes) {
            const base64 = await lerArquivoBase64(blob);
            return { base64, nome: nomeComExtensao(file.name, formato), mime: formato, largura, altura, aviso };
        }
    }
    throw new Error(`Não conseguimos deixar "${file.name}" leve o bastante. ${perfil.texto}`);
}

async function prepararArquivoParaEnvio(file, perfilNome) {
    const validacao = validarEntradaEnvio(file, perfilNome);
    if (!validacao.ok) throw new Error(validacao.erro);
    if (_TIPOS_IMAGEM.includes(validacao.formato)) {
        const r = await prepararImagemParaEnvio(file, perfilNome);
        return { ...r, formato: "imagem" };
    }
    return { base64: await lerArquivoBase64(file), nome: file.name, mime: file.type, formato: categoriaEnvio(validacao.formato), aviso: null };
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        PERFIS_ENVIO, formatoDoArquivo, validarEntradaEnvio, categoriaEnvio, dimensoesReduzidas,
        formatoSaidaImagem, avisoImagemPequena, nomeComExtensao,
        renderOrientacaoEnvio, lerArquivoBase64, decodificarImagem, prepararImagemParaEnvio, prepararArquivoParaEnvio,
    };
}
