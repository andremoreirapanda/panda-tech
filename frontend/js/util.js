// ============================================================================
// util.js — Formatação e helpers genéricos
// ============================================================================

function formatarMoeda(centavos) {
    return (centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

// CORREÇÃO DE BUG (agosto/2026): todo `criado_em`/`atualizado_em`/`pago_em`
// vindo do backend é gravado em UTC, sem indicação de fuso, no formato
// "YYYY-MM-DD HH:MM:SS" (ver `agora_sql()` em db.py e os DEFAULTs em
// schema.sql/schema_postgres.sql). O `new Date(...)` do JavaScript, quando
// recebe uma string sem fuso, assume que ela já está no horário LOCAL do
// navegador — então esses timestamps apareciam sempre adiantados em relação
// à hora real (3h adiantado no Brasil), incluindo cobranças mostrando um
// horário de criação que ainda nem tinha acontecido. A correção é dizer
// explicitamente ao JS que a string é UTC, acrescentando "Z" — a partir daí
// toLocaleDateString/toLocaleTimeString já convertem certo pro fuso do
// navegador sozinhos.
function _parseDataUtc(dataStr) {
    return new Date(dataStr.replace(" ", "T") + "Z");
}

function formatarData(dataStr) {
    if (!dataStr) return "-";
    const d = _parseDataUtc(dataStr);
    if (isNaN(d)) return dataStr;
    return d.toLocaleDateString("pt-BR");
}

function formatarDataHora(dataStr) {
    if (!dataStr) return "-";
    const d = _parseDataUtc(dataStr);
    if (isNaN(d)) return dataStr;
    return d.toLocaleDateString("pt-BR") + " às " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function formatarHora(dataStr) {
    if (!dataStr) return "-";
    const d = _parseDataUtc(dataStr);
    if (isNaN(d)) return "";
    return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function tempoRelativo(dataStr) {
    if (!dataStr) return "-";
    const d = _parseDataUtc(dataStr);
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

// CORREÇÃO DE AUDITORIA (25/08/2026, achado do CodeQL): cor_primaria,
// cor_secundaria (organização) e cor_agenda (profissional) são salvas sem
// nenhuma validação de formato no backend, e eram usadas direto (sem
// escapeHtml) dentro de atributos HTML (value="..." de <input type="color">,
// style="background:...") em vários lugares (onboarding, financeiro, agenda,
// cadastro de profissional/paciente) — um valor malicioso salvo por um
// gestor/admin (ex: `red" onmouseover="...`) rodava para qualquer outro
// usuário da mesma clínica que visse essa tela. Esta função é o único ponto
// usado por todos esses lugares: só deixa passar um valor que já é
// literalmente um código de cor hexadecimal (#RGB/#RRGGBB/#RRGGBBAA, o
// único formato que um <input type="color"> de verdade produz); qualquer
// outra coisa cai no valor padrão, sem exceção.
function corSegura(valor, padrao) {
    return typeof valor === "string" && /^#[0-9a-fA-F]{3,8}$/.test(valor) ? valor : padrao;
}

// CORREÇÃO DE AUDITORIA (25/08/2026, achado do CodeQL): avatar_base64,
// foto_base64 e logo_base64 são interpolados sem escapeHtml dentro de
// `src="data:image/...;base64,${...}"` (renderAvatarUsuario/
// renderFotoPaciente/renderLogoClinica, abaixo) — o backend já valida a
// assinatura (magic bytes) e agora exige base64 estrito (validate=True em
// validacao_arquivo.py), mas esta função é a segunda camada: garante que só
// um valor que É de fato base64 puro (o único formato que esse atributo
// src espera) chega a ser interpolado, mesmo que algum dado antigo/de outra
// origem não tenha passado pela validação do backend.
function base64Seguro(valor) {
    return typeof valor === "string" && valor.length > 0 && /^[A-Za-z0-9+/]+={0,2}$/.test(valor) ? valor : null;
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
// SEGURANÇA: estes 3 valores vêm de texto livre editado pelo gestor em
// Configurações — SEMPRE envolva a chamada em escapeHtml(...) antes de
// interpolar em innerHTML (correção de auditoria — item 4.8, XSS armazenado
// que chegava até o Mundo da Criança). Nunca interpole o retorno direto.
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
    const b64 = usuario && base64Seguro(usuario.avatar_base64);
    if (b64) {
        return `<img src="data:image/png;base64,${b64}" alt="Foto" style="width:${tamanhoPx}px; height:${tamanhoPx}px; border-radius:50%; object-fit:cover; vertical-align:middle;" />`;
    }
    return `<span style="font-size:${Math.round(tamanhoPx * 0.85)}px;">${(usuario && usuario.avatar_emoji) || "🙂"}</span>`;
}

// Exibe a foto/mascote da criança: foto real enviada, ou o mascote emoji como fallback.
function renderFotoPaciente(paciente, tamanhoPx = 40) {
    const b64 = paciente && base64Seguro(paciente.foto_base64);
    if (b64) {
        return `<img src="data:image/png;base64,${b64}" alt="Foto" style="width:${tamanhoPx}px; height:${tamanhoPx}px; border-radius:50%; object-fit:cover; vertical-align:middle;" />`;
    }
    return `<span style="font-size:${Math.round(tamanhoPx * 0.85)}px;">${(paciente && paciente.avatar_mascote) || "🐻"}</span>`;
}

// Exibe o logo da clínica: imagem enviada (se houver) ou, por padrão, o emoji.
function renderLogoClinica(org, alturaPx = 26) {
    const b64 = org && base64Seguro(org.logo_base64);
    if (b64) {
        return `<img src="data:image/png;base64,${b64}" alt="Logo" style="max-height:${alturaPx}px; max-width:${alturaPx * 4}px; width:auto; height:auto; object-fit:contain; display:block;" />`;
    }
    return `<span style="font-size:${Math.round(alturaPx * 0.85)}px; line-height:1;">${(org && org.logo_emoji) || "🌟"}</span>`;
}

// ============================================================================
// Formulários — asterisco de obrigatório + máscara/validação de campos
// (CPF, telefone). Convenção usada em toda a aplicação a partir desta rodada.
// ============================================================================

// Cole isto dentro do <label> de qualquer campo obrigatório, ex:
// `<label>Nome completo ${ASTERISCO_OBRIGATORIO}</label>`.
// O asterisco é decorativo (aria-hidden) — quem usa leitor de tela já ouve
// "obrigatório" pelo texto oculto (.sr-only) e/ou pelo atributo required do
// próprio input, então a informação nunca depende só da cor vermelha.
const ASTERISCO_OBRIGATORIO = `<span class="obrigatorio" aria-hidden="true">*</span><span class="sr-only"> (obrigatório)</span>`;

const MASCARAS_CAMPO = {
    telefone: {
        formatar(valor) {
            const d = (valor || "").replace(/\D/g, "").slice(0, 11);
            if (d.length <= 2) return d.replace(/^(\d*)/, "($1");
            if (d.length <= 3) return d.replace(/^(\d{2})(\d*)/, "($1) $2");
            if (d.length <= 7) return d.replace(/^(\d{2})(\d{1})(\d*)/, "($1) $2 $3");
            return d.replace(/^(\d{2})(\d{1})(\d{4})(\d*)/, "($1) $2 $3-$4");
        },
        placeholder: "(00) 0 0000-0000",
        pattern: "\\(\\d{2}\\) \\d \\d{4}-\\d{4}",
        maxlength: 16,
        dica: "Formato: DDD entre parênteses, espaço, um dígito, espaço, quatro dígitos, hífen e mais quatro dígitos. Exemplo: (11) 9 8888-7777.",
        tituloInvalido: "Telefone incompleto. Formato esperado: (11) 9 8888-7777",
    },
    cpf: {
        formatar(valor) {
            const d = (valor || "").replace(/\D/g, "").slice(0, 11);
            if (d.length <= 3) return d;
            if (d.length <= 6) return d.replace(/^(\d{3})(\d*)/, "$1.$2");
            if (d.length <= 9) return d.replace(/^(\d{3})(\d{3})(\d*)/, "$1.$2.$3");
            return d.replace(/^(\d{3})(\d{3})(\d{3})(\d*)/, "$1.$2.$3-$4");
        },
        placeholder: "000.000.000-00",
        pattern: "\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2}",
        maxlength: 14,
        dica: "Formato: três dígitos, ponto, três dígitos, ponto, três dígitos, hífen e mais dois dígitos. Exemplo: 123.456.789-00.",
        tituloInvalido: "CPF incompleto. Formato esperado: 123.456.789-00",
    },
    // Achado de UAT (26/08/2026): CNPJ e CEP tinham placeholder estático no
    // HTML mas nenhuma máscara/validação de fato — dava pra digitar qualquer
    // quantidade de dígitos, o que inclusive escondia o autopreenchimento por
    // CEP (ver ativarAutoCompleteCep): bastava digitar um dígito a mais ou a
    // menos que os 8 esperados para o preenchimento simplesmente não
    // disparar, sem nenhum aviso na tela.
    cnpj: {
        formatar(valor) {
            const d = (valor || "").replace(/\D/g, "").slice(0, 14);
            if (d.length <= 2) return d;
            if (d.length <= 5) return d.replace(/^(\d{2})(\d*)/, "$1.$2");
            if (d.length <= 8) return d.replace(/^(\d{2})(\d{3})(\d*)/, "$1.$2.$3");
            if (d.length <= 12) return d.replace(/^(\d{2})(\d{3})(\d{3})(\d*)/, "$1.$2.$3/$4");
            return d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d*)/, "$1.$2.$3/$4-$5");
        },
        placeholder: "00.000.000/0000-00",
        pattern: "\\d{2}\\.\\d{3}\\.\\d{3}\\/\\d{4}-\\d{2}",
        maxlength: 18,
        dica: "Formato: dois dígitos, ponto, três dígitos, ponto, três dígitos, barra, quatro dígitos, hífen e mais dois dígitos. Exemplo: 12.345.678/0001-90.",
        tituloInvalido: "CNPJ incompleto. Formato esperado: 12.345.678/0001-90",
    },
    cep: {
        formatar(valor) {
            const d = (valor || "").replace(/\D/g, "").slice(0, 8);
            if (d.length <= 5) return d;
            return d.replace(/^(\d{5})(\d*)/, "$1-$2");
        },
        placeholder: "00000-000",
        pattern: "\\d{5}-\\d{3}",
        maxlength: 9,
        dica: "Formato: cinco dígitos, hífen e mais três dígitos. Exemplo: 01310-100.",
        tituloInvalido: "CEP incompleto. Formato esperado: 01310-100 (8 dígitos)",
    },
};

// ---------------------------------------------------------------- CEP → endereço (ViaCEP)
// Achado de UAT (26/08/2026): todo cadastro de endereço (clínica, em
// Configurações e no Admin) exigia digitar rua/bairro/cidade/UF na mão.
// ViaCEP é um serviço público gratuito, sem chave de API, usado só no
// navegador de quem está preenchendo o formulário — nenhum dado da clínica
// ou de pacientes trafega para lá, só o CEP digitado.
async function _buscarEnderecoPorCep(cep) {
    const digits = (cep || "").replace(/\D/g, "");
    if (digits.length !== 8) return null;
    const resposta = await fetch(`https://viacep.com.br/ws/${digits}/json/`);
    if (!resposta.ok) return null;
    const dados = await resposta.json();
    if (dados.erro) return null;
    return {
        logradouro: dados.logradouro || "",
        bairro: dados.bairro || "",
        cidade: dados.localidade || "",
        uf: dados.uf || "",
    };
}

/**
 * Liga o autopreenchimento de endereço a partir do CEP num formulário que
 * segue a convenção `${idPrefixo}-cep/-logradouro/-numero/-bairro/-cidade/-uf`
 * (mesmo padrão usado em admin.js e financeiro.js). Dispara ao sair do campo
 * de CEP (blur) ou ao completar 8 dígitos digitando. Nunca sobrescreve um
 * valor que a pessoa já preencheu à mão nos outros campos — só entra onde
 * estiver vazio, então dá pra corrigir depois sem o autopreenchimento brigar.
 */
function ativarAutoCompleteCep(idPrefixo) {
    const cepInput = document.getElementById(`${idPrefixo}-cep`);
    if (!cepInput) return;
    const campo = (sufixo) => document.getElementById(`${idPrefixo}-${sufixo}`);

    let emAndamento = false;
    async function buscar() {
        const digits = cepInput.value.replace(/\D/g, "");
        if (digits.length !== 8 || emAndamento) return;
        emAndamento = true;
        cepInput.setAttribute("aria-busy", "true");
        try {
            const endereco = await _buscarEnderecoPorCep(digits);
            if (!endereco) {
                Toast.erro?.("CEP não encontrado — confira os números ou preencha o endereço manualmente.");
                return;
            }
            const logradouroEl = campo("logradouro"), bairroEl = campo("bairro"), cidadeEl = campo("cidade"), ufEl = campo("uf");
            if (logradouroEl && !logradouroEl.value.trim()) logradouroEl.value = endereco.logradouro;
            if (bairroEl && !bairroEl.value.trim()) bairroEl.value = endereco.bairro;
            if (cidadeEl && !cidadeEl.value.trim()) cidadeEl.value = endereco.cidade;
            if (ufEl && !ufEl.value.trim()) ufEl.value = endereco.uf;
            // Depois de preenchido, leva o foco pro número — é o único dado que o ViaCEP nunca traz.
            const numeroEl = campo("numero");
            if (numeroEl && !numeroEl.value.trim()) numeroEl.focus();
        } catch (e) {
            // Sem internet ou ViaCEP fora do ar — não bloqueia o preenchimento manual.
        } finally {
            emAndamento = false;
            cepInput.removeAttribute("aria-busy");
        }
    }
    cepInput.addEventListener("blur", () => {
        const digits = cepInput.value.replace(/\D/g, "");
        // Antes disto, sair do campo com uma quantidade errada de dígitos
        // (ex.: 7 ou 9) não disparava o preenchimento E não avisava nada —
        // parecia que o recurso simplesmente não existia.
        if (digits.length > 0 && digits.length !== 8) {
            Toast.info?.("CEP incompleto — confira se tem 8 dígitos para o preenchimento automático funcionar.");
            return;
        }
        buscar();
    });
    cepInput.addEventListener("input", () => { if (cepInput.value.replace(/\D/g, "").length === 8) buscar(); });
}

/**
 * Liga a formatação automática (enquanto digita) e os atributos de
 * validação/acessibilidade de um campo de telefone ou CPF: placeholder no
 * formato esperado, pattern (validação nativa do navegador, com foco
 * automático e mensagem acessível no campo errado ao tentar enviar), title
 * (mensagem exibida pelo navegador quando o pattern falha) e uma dica
 * associada via aria-describedby — essa parte é o que garante que quem usa
 * leitor de tela receba a instrução de formato mesmo depois que o
 * placeholder some (ao começar a digitar), já que depender só do
 * placeholder não é suficiente (WCAG 3.3.2).
 *
 * Uso: `ativarMascaraCampo(document.getElementById("pf-telefone"), "telefone")`.
 */
function ativarMascaraCampo(input, tipo) {
    if (!input) return;
    const cfg = MASCARAS_CAMPO[tipo];
    if (!cfg) return;
    input.placeholder = cfg.placeholder;
    input.setAttribute("inputmode", "numeric");
    input.setAttribute("autocomplete", tipo === "telefone" ? "tel" : "off");
    input.setAttribute("pattern", cfg.pattern);
    input.setAttribute("title", cfg.tituloInvalido);
    input.setAttribute("maxlength", String(cfg.maxlength));

    const dicaId = `${input.id}-dica`;
    if (input.id && !document.getElementById(dicaId)) {
        const dica = document.createElement("span");
        dica.id = dicaId;
        dica.className = "sr-only";
        dica.textContent = cfg.dica;
        input.insertAdjacentElement("afterend", dica);
        const existente = input.getAttribute("aria-describedby");
        input.setAttribute("aria-describedby", existente ? `${existente} ${dicaId}` : dicaId);
    }

    if (input.value) input.value = cfg.formatar(input.value);
    input.addEventListener("input", () => {
        const tamanhoAntes = input.value.length;
        const posicaoAntes = input.selectionStart ?? tamanhoAntes;
        input.value = cfg.formatar(input.value);
        const diferenca = input.value.length - tamanhoAntes;
        const novaPos = Math.max(0, posicaoAntes + diferenca);
        input.setSelectionRange(novaPos, novaPos);
    });
    // Mantém aria-invalid em sincronia pra estilizar a borda (CSS já cobre
    // :invalid, isso aqui é só reforço pra quando o campo tem valor mas
    // ainda incompleto e o usuário sai do campo).
    input.addEventListener("blur", () => {
        input.setAttribute("aria-invalid", input.value && !input.checkValidity() ? "true" : "false");
    });
}
