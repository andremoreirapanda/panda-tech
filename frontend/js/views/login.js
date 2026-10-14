// ============================================================================
// views/login.js — Autenticação (UX Pattern 01, Documento 13)
// ============================================================================

// White Label completo (25/09/2026): tela de login da clínica em
// #/entrar/<endereco>. Os dados vêm da rota pública; se ela der 404 (endereço
// errado, clínica sem o módulo), cai no login comum sem mensagem de erro.
async function viewLoginClinica(app, params) {
    let clinica = null;
    try {
        clinica = await Api.get(`/publico/clinica/${encodeURIComponent(params.endereco || "")}`);
    } catch (e) { clinica = null; }
    if (clinica && clinica.endereco_login) Sessao.enderecoLogin = clinica.endereco_login;
    return viewLogin(app, clinica);
}

function _painelLoginClinica(clinica) {
    const cor = corSegura(clinica.cor_primaria, "#5B4FE9");
    const mascoteUrl = clinica.tem_mascote_imagem ? urlMascoteClinica(clinica) : null;
    return `
      <div class="login-painel-ilustracao" style="flex:1; background: linear-gradient(160deg, ${cor} 0%, ${escurecerCor(cor, 0.35)} 100%);
                  display:flex; flex-direction:column; align-items:center; justify-content:center; gap:22px; padding:40px; position:relative; overflow:hidden;">
        <div style="background:#fff; border-radius:18px; padding:10px 14px; box-shadow:0 6px 20px #0002;">${renderLogoClinica(clinica, 56)}</div>
        <div class="login-mascote-principal" style="position:relative; z-index:1;">${svgMascote({ emoji: clinica.mundo_mascote || "🐼", estagio: 3, tamanho: 150, flutuar: true, imagemUrl: mascoteUrl })}</div>
        <div style="color:#fff; text-align:center; position:relative; z-index:1;">
          <h1 class="login-titulo" style="font-size:32px; margin-bottom:10px;">${escapeHtml(clinica.app_nome && clinica.app_nome !== "PandaUp" ? clinica.app_nome : clinica.nome)}</h1>
          <p class="login-subtitulo" style="opacity:.92; max-width:340px; font-size:15px; line-height:1.5;">${escapeHtml(clinica.login_mensagem || "")}</p>
        </div>
        <p class="texto-xs" style="position:absolute; bottom:14px; color:#fff; opacity:.8;">tecnologia PandaUp 🐼</p>
      </div>`;
}

// Fundo roxo do login: o logo próprio dele (letras claras), senão o principal (15/10/2026).
function _logoNoLogin() {
    return logoParaLogin(versaoLogoPlataforma("login"), versaoLogoPlataforma("principal"));
}

async function viewLogin(app, clinica = null) {
    if (clinica) aplicarTemaClinica({ ...clinica, white_label_ativo: true });
    else restaurarIdentidadePadrao();
    app.innerHTML = `
    <div class="tela-cheia">
      ${clinica ? _painelLoginClinica(clinica) : `
      <div class="login-painel-ilustracao" style="flex:1; background: linear-gradient(160deg, var(--cor-marca) 0%, #4238C4 55%, #8B5FBF 100%);
                  display:flex; flex-direction:column; align-items:center; justify-content:center; gap:28px; padding:40px; position:relative; overflow:hidden;">
        <div class="login-mascote-decorativo" style="position:absolute; top:12%; left:10%; opacity:.5;">${svgMascote({ emoji: "🐰", estagio: 2, tamanho: 70, flutuar: true })}</div>
        <div class="login-mascote-decorativo" style="position:absolute; bottom:14%; right:12%; opacity:.5;">${svgMascote({ emoji: "🦊", estagio: 4, tamanho: 90, flutuar: true })}</div>
        <div class="login-mascote-principal" style="position:relative; z-index:1;">${svgMascote({ emoji: "🐼", estagio: 3, tamanho: 160, flutuar: true })}</div>
        <div style="color:#fff; text-align:center; position:relative; z-index:1;">
          ${_logoNoLogin().versao
            ? `<h1 class="login-titulo" style="margin-bottom:14px; display:flex; justify-content:center;">${htmlLogoPlataforma(_logoNoLogin().versao, 72, "", _logoNoLogin().tipo)}</h1>`
            : `<h1 class="login-titulo" style="font-size:34px; margin-bottom:10px;">PandaUp</h1>`}
          <p class="login-subtitulo" style="opacity:.9; max-width:340px; font-size:15px; line-height:1.5;">
            A jornada terapêutica infantil, viva também fora do consultório — para clínicas, terapeutas e famílias.
          </p>
        </div>
      </div>`}

      <div style="flex:1; display:flex; align-items:center; justify-content:center; padding:40px;">
        <div style="width:100%; max-width:380px;">
          <h2 style="font-size:24px; margin-bottom:6px;">Bem-vindo(a) de volta 👋</h2>
          <p class="texto-suave" style="margin-bottom:28px;">${clinica ? `Entre com sua conta da ${escapeHtml(clinica.nome)}.` : "Entre com sua conta para continuar a jornada."}</p>

          <form id="form-login">
            <div class="campo">
              <label for="email">E-mail</label>
              <input type="email" id="email" required placeholder="seu@email.com" autocomplete="username" />
            </div>
            <div class="campo">
              <label for="senha">Senha</label>
              <input type="password" id="senha" required placeholder="••••••••" autocomplete="current-password" />
            </div>
            <div id="erro-login" class="campo-erro oculto" style="margin-bottom:14px;"></div>
            <button type="submit" class="botao botao-primario" style="width:100%; padding:14px;">Entrar</button>
          </form>
          <div style="text-align:center; margin-top:16px;">
            <a href="#/esqueci-senha" class="botao-texto botao-sm">Esqueci minha senha</a>
          </div>
        </div>
      </div>
    </div>`;

    ativarToggleSenha(document.getElementById("senha"));

    document.getElementById("form-login").addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("email").value.trim();
        const senha = document.getElementById("senha").value;
        const erroEl = document.getElementById("erro-login");
        erroEl.classList.add("oculto");
        try {
            const dados = await Api.post("/auth/login", { email, senha });
            Sessao.token = dados.token;
            Sessao.usuario = dados.usuario;
            Sessao.modoCrianca = false;
            if (dados.usuario.organizacao) aplicarTemaClinica(dados.usuario.organizacao);
            // Lembra a tela de login da clínica para o "Sair" voltar para ela.
            const org = dados.usuario.organizacao;
            Sessao.enderecoLogin = org && org.white_label_ativo ? org.endereco_login : null;
            Toast.sucesso(`Bem-vindo(a), ${dados.usuario.nome.split(" ")[0]}!`);

            if (dados.usuario.papel === "gestor") {
                try {
                    const onboarding = await Api.get("/onboarding/status");
                    if (onboarding.mostrar_wizard) { location.hash = "#/gestor/onboarding"; return; }
                } catch (err) { /* se a checagem falhar, segue o fluxo normal */ }
            }
            location.hash = paginaInicialPara(dados.usuario.papel);
        } catch (err) {
            erroEl.textContent = err.message || "Não foi possível entrar.";
            erroEl.classList.remove("oculto");
        }
    });
}

// Logo do PandaUp nas telas de recuperar acesso (14/10/2026): o logo da
// plataforma, se o Admin enviou; senão, o panda da tela de login.
function logoPandaUp(tamanho = 88) {
    const logo = htmlLogoPlataforma(versaoLogoPlataforma(), Math.round(tamanho * 0.7));
    return `<div class="logo-pandaup" aria-hidden="true" style="display:flex; justify-content:center; margin-bottom:10px;">${logo || svgMascote({ emoji: "🐼", estagio: 3, tamanho })}</div>`;
}

async function viewEsqueciSenha(app, emailInicial = "") {
    app.innerHTML = `
    <div class="tela-cheia" style="align-items:center; justify-content:center;">
      <div id="caixa-esqueci" style="width:100%; max-width:380px; padding:40px;">
        <h2 style="font-size:22px; margin-bottom:8px;">Recuperar acesso</h2>
        <p class="texto-suave" style="margin-bottom:24px;">Informe seu e-mail cadastrado. Enviaremos instruções para redefinir sua senha.</p>
        <form id="form-esqueci">
          <div class="campo"><label for="email">E-mail</label><input type="email" id="email" required value="${escapeHtml(emailInicial)}" /></div>
          <button type="submit" id="btn-esqueci" class="botao botao-primario" style="width:100%; padding:14px;">Enviar instruções</button>
        </form>
        <div style="text-align:center; margin-top:16px;"><a href="#/login" class="botao-texto botao-sm">← Voltar ao login</a></div>
        <div id="msg-esqueci" class="oculto texto-sm" style="margin-top:14px; text-align:center;"></div>
      </div>
    </div>`;

    document.getElementById("form-esqueci").addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("email").value.trim();
        const btn = document.getElementById("btn-esqueci");
        const msgEl = document.getElementById("msg-esqueci");
        btn.disabled = true;
        btn.textContent = "Enviando…";
        let r;
        try {
            r = await Api.post("/auth/esqueci-senha", { email });
        } catch (err) {
            // Ex.: muitas tentativas (429). O formulário continua para tentar depois.
            msgEl.textContent = err.message || "Não foi possível enviar agora. Tente de novo em instantes.";
            msgEl.classList.remove("oculto");
            btn.disabled = false;
            btn.textContent = "Enviar instruções";
            return;
        }
        if (r.modo_demonstracao && r.link_redefinicao) {
            btn.disabled = false;
            btn.textContent = "Enviar instruções";
            msgEl.innerHTML = `
              <div class="cartao-flat" style="text-align:left;">
                <p style="margin-bottom:8px;">${escapeHtml(r.mensagem)}</p>
                <p class="texto-xs texto-suave" style="margin-bottom:10px;">
                  🎭 Modo demonstração — sem servidor de e-mail configurado aqui, então o link aparece direto na tela
                  (válido por ${r.validade_minutos} minutos):
                </p>
                <a href="${r.link_redefinicao}" class="botao botao-primario botao-sm" style="width:100%;">Abrir link de redefinição</a>
              </div>`;
            msgEl.classList.remove("oculto");
            return;
        }
        mostrarConfirmacaoEsqueci(app, email, r);
    });
}

// Tela depois do envio (13/10/2026): no lugar do formulário, para a pessoa
// saber que terminou e o que fazer se o e-mail não chegar.
function mostrarConfirmacaoEsqueci(app, email, resposta) {
    const c = confirmacaoEsqueciSenha(email, resposta);
    const dicas = c.dicas.length ? `
        <div class="cartao-flat" style="text-align:left; margin-bottom:20px;">
          <p class="texto-sm" style="font-weight:700; margin-bottom:6px;">Não chegou?</p>
          <ul class="texto-sm texto-suave" style="margin:0; padding-left:18px;">
            ${c.dicas.map(d => `<li style="margin-bottom:4px;">${escapeHtml(d)}</li>`).join("")}
          </ul>
        </div>` : "";
    const acoesEmail = c.porEmail ? `
        <div class="texto-sm" style="margin-top:14px;">
          <button type="button" id="btn-reenviar-esqueci" class="botao-texto botao-sm">Enviar de novo</button>
          <span class="texto-suave"> · </span>
          <button type="button" id="btn-outro-email" class="botao-texto botao-sm">Usar outro e-mail</button>
        </div>
        <div id="msg-reenvio" class="oculto texto-xs texto-suave" style="margin-top:8px;"></div>` : "";
    document.getElementById("caixa-esqueci").innerHTML = `
      <div style="text-align:center;">
        ${logoPandaUp()}
        <h2 style="font-size:22px; margin-bottom:10px;">${escapeHtml(c.titulo)}</h2>
        <p class="texto-suave" style="margin-bottom:20px;" role="status">${escapeHtml(c.texto)}</p>
        ${dicas}
        <a href="#/login" class="botao botao-primario" style="width:100%; padding:14px; display:block;">Voltar ao login</a>
        ${acoesEmail}
      </div>`;
    if (!c.porEmail) return;

    document.getElementById("btn-outro-email").addEventListener("click", () => viewEsqueciSenha(app, email));
    const btnReenviar = document.getElementById("btn-reenviar-esqueci");
    btnReenviar.addEventListener("click", async () => {
        const msg = document.getElementById("msg-reenvio");
        btnReenviar.disabled = true;
        try {
            await Api.post("/auth/esqueci-senha", { email });
            msg.textContent = "Enviamos de novo. Pode levar alguns minutos.";
        } catch (err) {
            msg.textContent = err.message || "Não foi possível enviar agora. Tente de novo em instantes.";
            btnReenviar.disabled = false;
        }
        msg.classList.remove("oculto");
    });
}

async function viewRedefinirSenha(app) {
    const queryString = (location.hash.split("?")[1]) || "";
    const token = new URLSearchParams(queryString).get("token") || "";

    app.innerHTML = `
    <div class="tela-cheia" style="align-items:center; justify-content:center;">
      <div style="width:100%; max-width:380px; padding:40px;" id="wrap-redefinir">
        <div class="carregando"><div class="spinner"></div></div>
      </div>
    </div>`;

    const wrap = document.getElementById("wrap-redefinir");
    if (!token) {
        wrap.innerHTML = `<div class="estado-vazio">${logoPandaUp(72)}<div class="emoji">🔒</div><h3>Link inválido</h3><p>Solicite um novo link de redefinição.</p><a href="#/esqueci-senha" class="botao botao-primario botao-sm" style="margin-top:14px;">Solicitar novo link</a></div>`;
        return;
    }

    let validacao;
    try {
        validacao = await Api.get(`/auth/validar-token-redefinicao/${token}`);
    } catch (e) {
        validacao = { valido: false };
    }

    if (!validacao.valido) {
        wrap.innerHTML = `<div class="estado-vazio">${logoPandaUp(72)}<div class="emoji">⏰</div><h3>Link expirado ou já usado</h3><p>Solicite um novo link de redefinição.</p><a href="#/esqueci-senha" class="botao botao-primario botao-sm" style="margin-top:14px;">Solicitar novo link</a></div>`;
        return;
    }

    wrap.innerHTML = `
      <h2 style="font-size:22px; margin-bottom:4px;">${validacao.tipo === "convite" ? "Bem-vindo(a)! Crie sua senha" : "Criar nova senha"}</h2>
      <p class="texto-suave" style="margin-bottom:24px;">${validacao.tipo === "convite" ? `Olá, ${escapeHtml(validacao.nome.split(" ")[0])}! Para ativar seu acesso, defina uma senha para ${escapeHtml(validacao.email)}.` : `Olá, ${escapeHtml(validacao.nome.split(" ")[0])}! Defina sua nova senha para ${escapeHtml(validacao.email)}.`}</p>
      <form id="form-redefinir">
        <div class="campo"><label for="nova-senha">${validacao.tipo === "convite" ? "Escolha uma senha" : "Nova senha"}</label><input type="password" id="nova-senha" required minlength="8" placeholder="Mínimo 8 caracteres" /></div>
        <div class="campo"><label for="confirmar-senha">Confirmar senha</label><input type="password" id="confirmar-senha" required minlength="8" /></div>
        <div id="erro-redefinir" class="campo-erro oculto" style="margin-bottom:14px;"></div>
        <button type="submit" class="botao botao-primario" style="width:100%; padding:14px;">${validacao.tipo === "convite" ? "Ativar minha conta" : "Salvar nova senha"}</button>
      </form>`;

    ativarToggleSenha(document.getElementById("nova-senha"));
    ativarToggleSenha(document.getElementById("confirmar-senha"));

    document.getElementById("form-redefinir").addEventListener("submit", async (e) => {
        e.preventDefault();
        const novaSenha = document.getElementById("nova-senha").value;
        const confirmar = document.getElementById("confirmar-senha").value;
        const erroEl = document.getElementById("erro-redefinir");
        erroEl.classList.add("oculto");
        if (novaSenha !== confirmar) {
            erroEl.textContent = "As senhas não coincidem.";
            erroEl.classList.remove("oculto");
            return;
        }
        try {
            await Api.post("/auth/redefinir-senha", { token, nova_senha: novaSenha });
            Toast.sucesso(validacao.tipo === "convite" ? "Conta ativada! Faça login com sua nova senha." : "Senha atualizada! Faça login com a nova senha.");
            location.hash = urlLoginPosSaida();
        } catch (err) {
            erroEl.textContent = err.message;
            erroEl.classList.remove("oculto");
        }
    });
}
