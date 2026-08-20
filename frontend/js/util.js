// ============================================================================
// util.js — Formatação e helpers genéricos
// ============================================================================

function formatarMoeda(centavos) {
    return (centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatarData(dataStr) {
    if (!dataStr) return "-";
    const d = new Date(dataStr.replace(" ", "T"));
    if (isNaN(d)) return dataStr;
    return d.toLocaleDateString("pt-BR");
}

function formatarDataHora(dataStr) {
    if (!dataStr) return "-";
    const d = new Date(dataStr.replace(" ", "T"));
    if (isNaN(d)) return dataStr;
    return d.toLocaleDateString("pt-BR") + " às " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function formatarHora(dataStr) {
    if (!dataStr) return "-";
    const d = new Date(dataStr.replace(" ", "T"));
    if (isNaN(d)) return "";
    return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function tempoRelativo(dataStr) {
    if (!dataStr) return "-";
    const d = new Date(dataStr.replace(" ", "T"));
    const diffMs = Date.now() - d.getTime();
    const min = Math.floor(diffMs / 60000);
    if (min < 1) return "agora mesmo";
    if (min < 60) return `há ${min} min`;
    const h = Math.floor(min / 60);
    if (h < 24) return `há ${h}h`;
    const dias = Math.floor(h / 24);
    if (dias === 1) return "ontem";
    if (dias < 7) return `há ${dias} dias`;
    return formatarData(dataStr);
}

function calcularIdade(dataNascimento) {
    if (!dataNascimento) return "";
    const nasc = new Date(dataNascimento);
    const hoje = new Date();
    let anos = hoje.getFullYear() - nasc.getFullYear();
    let meses = hoje.getMonth() - nasc.getMonth();
    if (hoje.getDate() < nasc.getDate()) meses--;
    if (meses < 0) { anos--; meses += 12; }
    if (anos < 0) return "";
    if (anos === 0 && meses === 0) return "recém-nascido(a)";
    const partes = [];
    if (anos > 0) partes.push(`${anos} ${anos === 1 ? "ano" : "anos"}`);
    if (meses > 0) partes.push(`${meses} ${meses === 1 ? "mês" : "meses"}`);
    return partes.join(" e ");
}

function iniciais(nome) {
    if (!nome) return "?";
    const partes = nome.trim().split(" ");
    return (partes[0][0] + (partes.length > 1 ? partes[partes.length - 1][0] : "")).toUpperCase();
}

function el(html) {
    const div = document.createElement("div");
    div.innerHTML = html.trim();
    return div.firstElementChild;
}

function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str).replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
}

function truncarTexto(str, max) {
    if (!str) return "";
    return str.length > max ? str.slice(0, max).trimEnd() + "…" : str;
}

// Círculo de progresso (ex: Índice de Continuidade Terapêutica) — dá destaque
// visual a um número, em vez de uma barra linear discreta.
function circuloProgresso({ pct = 0, tamanho = 96, espessura = 9, cor = "var(--cor-marca)", valorTexto = null, label = "" }) {
    const raio = (tamanho - espessura) / 2;
    const circ = 2 * Math.PI * raio;
    const offset = circ - (circ * Math.min(Math.max(pct, 0), 100) / 100);
    const centro = tamanho / 2;
    const texto = valorTexto !== null ? valorTexto : `${pct}%`;
    return `
    <div style="position:relative; width:${tamanho}px; height:${tamanho}px; display:inline-flex; align-items:center; justify-content:center; flex-shrink:0;">
      <svg width="${tamanho}" height="${tamanho}" style="transform:rotate(-90deg); position:absolute; top:0; left:0;">
        <circle cx="${centro}" cy="${centro}" r="${raio}" fill="none" stroke="var(--cor-fundo-alt)" stroke-width="${espessura}" />
        <circle cx="${centro}" cy="${centro}" r="${raio}" fill="none" stroke="${cor}" stroke-width="${espessura}"
                stroke-dasharray="${circ}" stroke-dashoffset="${offset}" stroke-linecap="round"
                style="transition: stroke-dashoffset .6s ease;" />
      </svg>
      <div style="position:relative; text-align:center; line-height:1.1;">
        <div style="font-family:var(--fonte-display); font-weight:700; font-size:${Math.round(tamanho * 0.26)}px; color:var(--cor-tinta);">${texto}</div>
        ${label ? `<div style="font-size:${Math.max(9, Math.round(tamanho * 0.09))}px; color:var(--cor-tinta-suave); font-weight:700; margin-top:2px;">${label}</div>` : ""}
      </div>
    </div>`;
}

const ICONES_TIPO_EXERCICIO = { video: "🎬", pdf: "📄", imagem: "🖼️", jogo: "🎮", link: "🔗", atividade: "📝" };

// Exibe o link de convite de ativação (Doc 31A/35/36) — como não há servidor de
// e-mail neste ambiente, o link é mostrado direto para quem cadastrou compartilhar.
function mostrarModalConvite(link, nomeDestinatario) {
    const urlCompleta = `${location.origin}${location.pathname}${link}`;
    const modal = el(`
    <div class="modal-fundo">
      <div class="modal-caixa">
        <h3 style="margin-bottom:8px;">✅ Cadastro concluído!</h3>
        <p class="texto-sm texto-suave" style="margin-bottom:16px;">
          Envie este link para <strong>${escapeHtml(nomeDestinatario)}</strong> ativar a própria conta e criar a senha.
        </p>
        <div class="cartao-flat" style="margin-bottom:16px;">
          <p class="texto-xs texto-suave" style="margin-bottom:8px;">🎭 Modo demonstração — em produção isso seria enviado por e-mail automaticamente.</p>
          <div class="linha gap-2">
            <input type="text" readonly value="${escapeHtml(urlCompleta)}" id="input-link-convite" style="flex:1; padding:9px 12px; border-radius:8px; border:1.5px solid var(--cor-borda); font-size:12.5px;" />
            <button type="button" class="botao botao-secundario botao-sm" id="btn-copiar-convite">Copiar</button>
          </div>
        </div>
        <button type="button" class="botao botao-primario" id="btn-fechar-convite" style="width:100%;">Concluir</button>
      </div>
    </div>`);
    document.body.appendChild(modal);
    document.getElementById("btn-copiar-convite").addEventListener("click", () => {
        const input = document.getElementById("input-link-convite");
        input.select();
        navigator.clipboard?.writeText(input.value).then(() => Toast.sucesso("Link copiado!")).catch(() => {});
    });
    document.getElementById("btn-fechar-convite").addEventListener("click", () => { modal.remove(); despachar(); });
    modal.addEventListener("click", (e) => { if (e.target === modal) { modal.remove(); despachar(); } });
}
const ICONES_ESPECIALIDADE = {
    "Fonoaudiologia": "🗣️", "Terapia Ocupacional": "🧩", "Psicopedagogia": "📚", "Psicologia": "🧠", "Fisioterapia": "🤸",
};
const ESPECIALIDADES_PADRAO = ["Fonoaudiologia", "Terapia Ocupacional", "Psicopedagogia", "Psicologia", "Fisioterapia", "Nutrição", "Educação Física Adaptada"];

// Especialidades a oferecer nos formulários: usa exatamente o que a própria
// clínica configurou em Configurações. Sem fallback pra lista fixa — o
// gestor decide o nicho, a plataforma não impõe um catálogo pré-definido.
function especialidadesDaClinica() {
    return Sessao.usuario?.organizacao?.especialidades || [];
}

// Campo de tags livre reutilizável (Especialidades da clínica) — usado em
// Configurações e nos modais de clínica do Admin. Digite e adicione, sem
// lista fixa pré-definida (cada clínica tem seu próprio nicho).
function renderCampoTagsEspecialidade(idPrefixo, valoresIniciais = []) {
    return `
    <div class="linha gap-2" style="margin-bottom:10px;">
      <input type="text" id="${idPrefixo}-input" placeholder="Ex: Fonoaudiologia, Musicoterapia..." style="flex:1; padding:9px 12px; border-radius:8px; border:1.5px solid var(--cor-borda);" />
      <button type="button" class="botao botao-secundario botao-sm" id="${idPrefixo}-btn-add">+ Adicionar</button>
    </div>
    <div class="linha gap-2" id="${idPrefixo}-lista" style="flex-wrap:wrap;">
      ${valoresIniciais.map(esp => `
        <span class="badge badge-marca chip-especialidade" data-nome="${escapeHtml(esp)}" style="padding:8px 10px 8px 14px; display:inline-flex; align-items:center; gap:6px;">
          ${escapeHtml(esp)}<button type="button" class="btn-remover-tag-esp" style="border:none; background:none; cursor:pointer; font-size:14px; line-height:1; color:inherit; padding:0;">✕</button>
        </span>`).join("")}
    </div>`;
}

// Conecta os eventos do campo acima e devolve um getter pro array atual de tags.
function ativarCampoTagsEspecialidade(idPrefixo, valoresIniciais = []) {
    let valores = [...valoresIniciais];
    const listaEl = document.getElementById(`${idPrefixo}-lista`);
    function render() {
        listaEl.innerHTML = valores.map(esp => `
          <span class="badge badge-marca chip-especialidade" data-nome="${escapeHtml(esp)}" style="padding:8px 10px 8px 14px; display:inline-flex; align-items:center; gap:6px;">
            ${escapeHtml(esp)}<button type="button" class="btn-remover-tag-esp" style="border:none; background:none; cursor:pointer; font-size:14px; line-height:1; color:inherit; padding:0;">✕</button>
          </span>`).join("");
        listaEl.querySelectorAll(".btn-remover-tag-esp").forEach(btn => btn.addEventListener("click", () => {
            valores = valores.filter(v => v !== btn.closest(".chip-especialidade").dataset.nome);
            render();
        }));
    }
    render();
    function adicionar() {
        const input = document.getElementById(`${idPrefixo}-input`);
        const nome = input.value.trim();
        if (!nome) return;
        if (!valores.includes(nome)) valores.push(nome);
        input.value = "";
        render();
        input.focus();
    }
    document.getElementById(`${idPrefixo}-btn-add`).addEventListener("click", adicionar);
    document.getElementById(`${idPrefixo}-input`).addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); adicionar(); }
    });
    return () => valores;
}

// Nomes personalizáveis por clínica (White Label leve — Doc 018/022)
function nomeMoeda() {
    return (Sessao.usuario && Sessao.usuario.organizacao && Sessao.usuario.organizacao.nome_moeda_gamificacao) || "XP";
}
function nomeIA() {
    return (Sessao.usuario && Sessao.usuario.organizacao && Sessao.usuario.organizacao.nome_ia) || "Lumi";
}
function nomeMedalhaGenerico() {
    return (Sessao.usuario && Sessao.usuario.organizacao && Sessao.usuario.organizacao.nome_medalha_generico) || "Medalha";
}

// ---------------------------------------------------------------- Tema dinâmico da clínica (White Label leve)
function _hexParaRgb(hex) {
    hex = (hex || "#5B4FE9").replace("#", "");
    if (hex.length === 3) hex = hex.split("").map(c => c + c).join("");
    const num = parseInt(hex, 16);
    return { r: (num >> 16) & 255, g: (num >> 8) & 255, b: num & 255 };
}
function _rgbParaHex({ r, g, b }) {
    return "#" + [r, g, b].map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("");
}
function _misturarCor(hex, alvoRgb, proporcao) {
    const c = _hexParaRgb(hex);
    return _rgbParaHex({
        r: c.r + (alvoRgb.r - c.r) * proporcao,
        g: c.g + (alvoRgb.g - c.g) * proporcao,
        b: c.b + (alvoRgb.b - c.b) * proporcao,
    });
}
function escurecerCor(hex, proporcao = 0.22) { return _misturarCor(hex, { r: 0, g: 0, b: 0 }, proporcao); }
function clarearCor(hex, proporcao = 0.9) { return _misturarCor(hex, { r: 255, g: 255, b: 255 }, proporcao); }

/**
 * Aplica de verdade as cores escolhidas pela clínica em Configurações — sem
 * isso, o seletor de cor era só um campo decorativo que não mudava nada
 * visualmente. Chamado a cada login e a cada troca de tela do shell.
 */
function aplicarTemaClinica(org) {
    if (!org) return;
    const raiz = document.documentElement.style;
    const primaria = org.cor_primaria || "#5B4FE9";
    const secundaria = org.cor_secundaria || "#FFB84D";
    raiz.setProperty("--cor-marca", primaria);
    raiz.setProperty("--cor-marca-escura", escurecerCor(primaria, 0.22));
    raiz.setProperty("--cor-marca-clara", clarearCor(primaria, 0.9));
    raiz.setProperty("--cor-acento", secundaria);
    raiz.setProperty("--cor-acento-escuro", escurecerCor(secundaria, 0.18));
    raiz.setProperty("--cor-acento-claro", clarearCor(secundaria, 0.88));
}

// Exibe o avatar do usuário: foto enviada (se houver) ou, por padrão, o emoji.
function renderAvatarUsuario(usuario, tamanhoPx = 40) {
    if (usuario && usuario.avatar_base64) {
        return `<img src="data:image/png;base64,${usuario.avatar_base64}" alt="Foto" style="width:${tamanhoPx}px; height:${tamanhoPx}px; border-radius:50%; object-fit:cover; vertical-align:middle;" />`;
    }
    return `<span style="font-size:${Math.round(tamanhoPx * 0.85)}px;">${(usuario && usuario.avatar_emoji) || "🙂"}</span>`;
}

// Exibe a foto/mascote da criança: foto real enviada, ou o mascote emoji como fallback.
function renderFotoPaciente(paciente, tamanhoPx = 40) {
    if (paciente && paciente.foto_base64) {
        return `<img src="data:image/png;base64,${paciente.foto_base64}" alt="Foto" style="width:${tamanhoPx}px; height:${tamanhoPx}px; border-radius:50%; object-fit:cover; vertical-align:middle;" />`;
    }
    return `<span style="font-size:${Math.round(tamanhoPx * 0.85)}px;">${(paciente && paciente.avatar_mascote) || "🐻"}</span>`;
}

// Exibe o logo da clínica: imagem enviada (se houver) ou, por padrão, o emoji.
function renderLogoClinica(org, alturaPx = 26) {
    if (org && org.logo_base64) {
        return `<img src="data:image/png;base64,${org.logo_base64}" alt="Logo" style="max-height:${alturaPx}px; max-width:${alturaPx * 4}px; width:auto; height:auto; object-fit:contain; display:block;" />`;
    }
    return `<span style="font-size:${Math.round(alturaPx * 0.85)}px; line-height:1;">${(org && org.logo_emoji) || "🌟"}</span>`;
}
