// ============================================================================
// api.js — Cliente HTTP + Sessão
// ============================================================================

const API_BASE = "/api";

const Sessao = {
    get token() { return localStorage.getItem("encanto_token"); },
    set token(v) { v ? localStorage.setItem("encanto_token", v) : localStorage.removeItem("encanto_token"); },

    get usuario() {
        const raw = localStorage.getItem("encanto_usuario");
        return raw ? JSON.parse(raw) : null;
    },
    set usuario(v) { v ? localStorage.setItem("encanto_usuario", JSON.stringify(v)) : localStorage.removeItem("encanto_usuario"); },

    // Paciente atualmente selecionado no app do Responsável / Criança
    get pacienteAtivoId() { return localStorage.getItem("encanto_paciente_ativo"); },
    set pacienteAtivoId(v) { v ? localStorage.setItem("encanto_paciente_ativo", v) : localStorage.removeItem("encanto_paciente_ativo"); },

    get modoCrianca() { return localStorage.getItem("encanto_modo_crianca") === "1"; },
    set modoCrianca(v) { v ? localStorage.setItem("encanto_modo_crianca", "1") : localStorage.removeItem("encanto_modo_crianca"); },

    limpar() {
        localStorage.removeItem("encanto_token");
        localStorage.removeItem("encanto_usuario");
        localStorage.removeItem("encanto_paciente_ativo");
        localStorage.removeItem("encanto_modo_crianca");
    },

    logado() { return !!this.token && !!this.usuario; },

    // White Label completo (25/09/2026): endereço da tela de login da clínica
    // (#/entrar/<endereco>) — sobrevive ao "Sair" (limpar() não apaga), para a
    // pessoa voltar para a tela da própria clínica.
    get enderecoLogin() {
        try { return localStorage.getItem("encanto_endereco_login"); } catch (e) { return null; }
    },
    set enderecoLogin(v) {
        try {
            if (v && /^[a-z0-9-]{3,40}$/.test(v)) localStorage.setItem("encanto_endereco_login", v);
            else localStorage.removeItem("encanto_endereco_login");
        } catch (e) { /* armazenamento bloqueado: só não lembra */ }
    },
};

// Para onde ir depois de sair: a tela de login da clínica, se houver.
function urlLoginPosSaida() {
    const e = Sessao.enderecoLogin;
    return e ? `#/entrar/${e}` : "#/login";
}

async function api(metodo, caminho, body) {
    const headers = { "Content-Type": "application/json" };
    if (Sessao.token) headers["Authorization"] = `Bearer ${Sessao.token}`;

    let resposta;
    try {
        resposta = await fetch(`${API_BASE}${caminho}`, {
            method: metodo,
            headers,
            body: body !== undefined ? JSON.stringify(body) : undefined,
        });
    } catch (e) {
        Toast.erro("Não foi possível conectar ao servidor. Verifique se o backend está rodando.");
        throw e;
    }

    let dados = null;
    try { dados = await resposta.json(); } catch (e) { /* resposta vazia */ }

    if (resposta.status === 401) {
        Sessao.limpar();
        location.hash = urlLoginPosSaida();
        Toast.erro((dados && dados.erro) || "Sessão expirada. Faça login novamente.");
        throw new Error("401");
    }

    if (!resposta.ok) {
        const msg = (dados && dados.erro) || `Erro ${resposta.status}`;
        throw new Error(msg);
    }

    return dados;
}

const Api = {
    get: (caminho) => api("GET", caminho),
    post: (caminho, body) => api("POST", caminho, body || {}),
    put: (caminho, body) => api("PUT", caminho, body || {}),
    del: (caminho) => api("DELETE", caminho),

    // Downloads binários (PDF etc) não passam pelo fluxo normal de JSON —
    // precisam do header de autenticação, mas a resposta é um blob, não JSON.
    async baixarArquivo(caminho, nomeArquivoSugerido) {
        const headers = {};
        if (Sessao.token) headers["Authorization"] = `Bearer ${Sessao.token}`;
        const resposta = await fetch(`${API_BASE}${caminho}`, { headers });
        if (!resposta.ok) {
            let msg = `Erro ${resposta.status}`;
            try { const dados = await resposta.json(); msg = dados.erro || msg; } catch (e) { /* corpo não é JSON */ }
            throw new Error(msg);
        }
        const blob = await resposta.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = nomeArquivoSugerido || "arquivo";
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 4000);
    },
};
