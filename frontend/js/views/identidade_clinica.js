// ============================================================================
// views/identidade_clinica.js — White Label completo (25/09/2026)
//
// Cartão "Identidade Visual Própria" de Configurações (gestor): Aplicativo
// (nome e ícone), Tela de login (endereço + mensagem) e Mundo da Criança
// (fonte, fundo animado, mascote padrão, texto da comemoração). Sem o módulo,
// tudo aparece travado — o que for salvo fica guardado e passa a valer quando
// o módulo for liberado (a regra de verdade está no backend,
// identidade_service.identidade_efetiva).
// ============================================================================

// Fundo da clínica no app da equipe/famílias (26/09/2026).
const FUNDOS_APP_WL = [
    { codigo: "padrao", rotulo: "Padrão", icone: "⬜", amostra: "#FAF7F2" },
    { codigo: "cor", rotulo: "Colorido", icone: "🎨", amostra: "linear-gradient(135deg,#D9D1FF,#FFD6E4)" },
    { codigo: "bambu", rotulo: "Bambuzal", icone: "🎋", amostra: "linear-gradient(180deg,#BDF0D2,#4FB07E)" },
    { codigo: "mar", rotulo: "Fundo do mar", icone: "🐠", amostra: "linear-gradient(180deg,#5FD0F0,#1D5FA8)" },
    { codigo: "espaco", rotulo: "Espaço", icone: "🚀", amostra: "radial-gradient(circle at 30% 20%,#4B3D8F,#1E1745 70%)" },
    { codigo: "clinica", rotulo: "Imagem da clínica", icone: "🖼️", amostra: "repeating-linear-gradient(45deg,#F6E7D0 0 14px,#F1DDBF 14px 28px)" },
];

const FONTES_WL = [
    { codigo: "fredoka", rotulo: "Fredoka" },
    { codigo: "baloo", rotulo: "Baloo" },
    { codigo: "nunito", rotulo: "Nunito" },
    { codigo: "escolar", rotulo: "Escolar" },
];
const FUNDOS_WL = [
    { codigo: "estrelas", rotulo: "Estrelinhas (atual)", icone: "✨", amostra: "#F3EEFF" },
    { codigo: "bambu", rotulo: "Bambuzal", icone: "🎋", amostra: "linear-gradient(180deg,#BDF0D2,#4FB07E)" },
    { codigo: "mar", rotulo: "Fundo do mar", icone: "🐠", amostra: "linear-gradient(180deg,#5FD0F0,#1D5FA8)" },
    { codigo: "espaco", rotulo: "Espaço", icone: "🚀", amostra: "radial-gradient(circle at 30% 20%,#4B3D8F,#1E1745 70%)" },
    { codigo: "clinica", rotulo: "Imagem da clínica", icone: "🖼️", amostra: "repeating-linear-gradient(45deg,#F6E7D0 0 14px,#F1DDBF 14px 28px)" },
    { codigo: "pandoo", rotulo: "Igual ao Pandoo", icone: "🎮", amostra: "linear-gradient(135deg,#BDF0D2 0 50%,#5FD0F0 50%)" },
];


function _imgBase64(b64, estilo) {
    const seguro = base64Seguro(b64);
    return seguro ? `<img src="data:image/png;base64,${seguro}" alt="" style="${estilo}" />` : "";
}

function renderCartaoIdentidadePropria(org) {
    // Sem o módulo, o cartão nem aparece (pedido do usuário, 26/09/2026).
    if (!org.white_label_ativo) return "";
    const ativo = true;
    const fundoApp = org.app_fundo || "padrao";
    const corFundo = org.app_fundo_cor || "lavanda";
    const fonte = org.mundo_fonte || "fredoka";
    const fundo = org.mundo_fundo || "estrelas";
    const mascote = org.mundo_mascote || "🐻";
    const selo = `<span class="selo-wl">Identidade Visual Própria</span>`;
    return `
    <div class="cartao" id="cartao-identidade-propria" style="max-width:900px; margin-top:20px;">
      <h3 style="margin-bottom:6px;">🎨 Identidade Visual Própria ${selo}</h3>
      <p class="texto-xs texto-suave" style="margin-bottom:14px;">Deixe o app com a cara da clínica: nome e ícone no celular, tela de login própria e o Mundo da Criança.</p>
      <form id="form-wl">
      <fieldset class="wl-grupo" ${ativo ? "" : "disabled"}>
        <p class="texto-sm" style="font-weight:700; margin:6px 0 8px;">📱 Aplicativo</p>
        <div class="linha gap-4" style="align-items:flex-start; flex-wrap:wrap;">
          <div class="campo" style="flex:1; min-width:220px;"><label>Nome do app</label>
            <input type="text" id="wl-app-nome" maxlength="30" value="${escapeHtml(org.app_nome || "")}" placeholder="Panda Tech" />
            <p class="texto-xs texto-suave" style="margin-top:4px;">Aparece na aba do navegador e embaixo do ícone no celular.</p>
          </div>
          <div class="campo" style="flex:1; min-width:220px;"><label>Ícone do app</label>
            <div class="linha gap-3" style="align-items:center;">
              <div id="wl-icone-preview" class="wl-miniatura">${_imgBase64(org.app_icone_base64, "width:100%; height:100%; object-fit:cover;") || "🐼"}</div>
              <input type="file" id="wl-icone-arquivo" accept="image/*" style="flex:1;" />
            </div>
            ${renderOrientacaoEnvio("icone")}
            <button type="button" class="botao-texto botao-sm" id="wl-icone-remover">Remover ícone</button>
          </div>
        </div>

        <hr class="wl-divisor" />
        <p class="texto-sm" style="font-weight:700; margin-bottom:4px;">🖼️ Fundo da clínica</p>
        <p class="texto-xs texto-suave" style="margin-bottom:8px;">Aparece atrás das telas da equipe e das famílias; o conteúdo fica sobre um painel claro, para continuar legível com qualquer fundo.</p>
        <div class="wl-cenas" id="wl-fundos-app">
          ${FUNDOS_APP_WL.map(f => `<button type="button" class="wl-cena ${f.codigo === fundoApp ? "ativo" : ""}" data-fundo-app="${f.codigo}"><span class="wl-amostra" style="background:${f.amostra}">${f.icone}</span><span>${f.rotulo}</span></button>`).join("")}
        </div>
        <div id="wl-cores-fundo-grupo" style="margin-top:10px;">
          <label class="wl-rotulo">Cor do fundo</label>
          <div class="wl-opcoes" id="wl-cores-fundo">
            ${Object.keys(PALETA_FUNDO_APP).map(k => `<button type="button" class="wl-cor-fundo ${k === corFundo ? "ativo" : ""}" data-cor-fundo="${k}" title="${k}" style="background:${PALETA_FUNDO_APP[k]}"></button>`).join("")}
            <label class="texto-sm linha gap-2" style="align-items:center;">outra cor <input type="color" id="wl-cor-fundo-livre" value="${/^#[0-9a-fA-F]{6}$/.test(corFundo) ? corFundo : "#EFEAFF"}" style="width:44px; height:36px; padding:2px;" /></label>
          </div>
        </div>
        <p class="texto-xs texto-suave" style="margin-top:6px;">A imagem da clínica é a mesma do fundo do Mundo da Criança e do Pandoo (envie no grupo Mundo da Criança, abaixo).</p>

        <hr class="wl-divisor" />
        <p class="texto-sm" style="font-weight:700; margin-bottom:8px;">🔑 Tela de login</p>
        <div class="campo"><label>Endereço da tela de login</label>
          <div class="linha gap-2" style="align-items:center; flex-wrap:wrap;">
            <span class="texto-sm texto-suave">${escapeHtml(location.origin)}/#/entrar/</span>
            <input type="text" id="wl-endereco" maxlength="40" value="${escapeHtml(org.endereco_login || "")}" style="flex:1; min-width:140px;" />
            <button type="button" class="botao botao-secundario botao-sm" id="wl-copiar-link">Copiar link</button>
          </div>
          <p class="texto-xs texto-suave" style="margin-top:4px;">Letras minúsculas, números e hífen. Envie esse link para a equipe e as famílias.</p>
        </div>
        <div class="campo"><label>Mensagem de boas-vindas</label>
          <textarea id="wl-login-msg" maxlength="120" rows="2" placeholder="Entre com sua conta para continuar a jornada.">${escapeHtml(org.login_mensagem || "")}</textarea>
          <p class="texto-xs texto-suave" style="margin-top:4px;">A tela mostra o logo, as cores, o mascote e esta mensagem (até 120 caracteres).</p>
        </div>

        <hr class="wl-divisor" />
        <p class="texto-sm" style="font-weight:700; margin-bottom:8px;">🧒 Mundo da Criança</p>
        <div class="wl-mundo">
          <div style="flex:1; min-width:260px;">
            <label class="wl-rotulo">Fonte dos títulos</label>
            <div class="wl-opcoes" id="wl-fontes">
              ${FONTES_WL.map(f => `<button type="button" class="opcao-cartao ${f.codigo === fonte ? "ativo" : ""}" data-fonte="${f.codigo}" style="font-family:${fonteCrianca(f.codigo).familia}; font-size:18px;">${f.rotulo}</button>`).join("")}
            </div>

            <label class="wl-rotulo">Fundo animado</label>
            <div class="wl-cenas" id="wl-fundos">
              ${FUNDOS_WL.map(f => `<button type="button" class="wl-cena ${f.codigo === fundo ? "ativo" : ""}" data-fundo="${f.codigo}"><span class="wl-amostra" style="background:${f.amostra}">${f.icone}</span><span>${f.rotulo}</span></button>`).join("")}
            </div>
            <div id="wl-cenario-img-grupo" class="campo" style="margin-top:10px;">
              <label>Imagem da clínica (fundo)</label>
              <div class="linha gap-3" style="align-items:center;">
                <div id="wl-cenario-preview" class="wl-miniatura">${_imgBase64(org.pandoo_cenario_imagem, "width:100%; height:100%; object-fit:cover;") || "🖼️"}</div>
                <input type="file" id="wl-cenario-arquivo" accept="image/*" style="flex:1;" />
              </div>
              ${renderOrientacaoEnvio("cenario")}
              <p class="texto-xs texto-suave">É a mesma imagem do cenário dos jogos do Pandoo — uma foto serve para os dois.</p>
            </div>

            <label class="wl-rotulo">Mascote padrão das crianças novas</label>
            <div class="wl-opcoes" id="wl-mascotes">
              ${MASCOTES_DISPONIVEIS.map(m => `<button type="button" class="opcao-cartao wl-mascote ${m === mascote ? "ativo" : ""}" data-mascote="${m}">${m}</button>`).join("")}
              <button type="button" class="opcao-cartao ${mascote === "clinica" ? "ativo" : ""}" data-mascote="clinica">🖼️ Imagem da clínica</button>
            </div>
            <div id="wl-mascote-img-grupo" class="campo" style="margin-top:10px;">
              <div class="linha gap-3" style="align-items:center;">
                <div id="wl-mascote-preview" class="wl-miniatura">${_imgBase64(org.mundo_mascote_imagem, "width:100%; height:100%; object-fit:contain;") || "🖼️"}</div>
                <input type="file" id="wl-mascote-arquivo" accept="image/*" style="flex:1;" />
              </div>
              ${renderOrientacaoEnvio("icone")}
            </div>
            <p class="texto-xs texto-suave">Vale para as crianças cadastradas daqui para frente; o responsável pode trocar depois.</p>

            <div class="campo" style="margin-top:12px;"><label>Texto da comemoração</label>
              <input type="text" id="wl-comemoracao" maxlength="40" value="${escapeHtml(org.mundo_comemoracao || "")}" placeholder="Muito bem!!" />
              <p class="texto-xs texto-suave" style="margin-top:4px;">Aparece quando a criança conclui uma missão (até 40 caracteres).</p>
            </div>
          </div>
          <div class="wl-previa-celular" aria-label="Prévia do Mundo da Criança">
            <div class="cenario-animado" id="wl-previa-cenario"></div>
            <div class="wl-previa-conteudo" id="wl-previa-conteudo">
              <div id="wl-previa-mascote" style="text-align:center;"></div>
              <p class="wl-previa-titulo">Oi, Benício! 👋</p>
              <div class="wl-previa-card">🗺️ Missão de hoje</div>
              <div class="wl-previa-card">🎡 Jogo da roleta</div>
            </div>
          </div>
        </div>
        <button type="submit" class="botao botao-primario" style="margin-top:16px;">Salvar identidade</button>
      </fieldset>
      </form>
    </div>`;
}

// Tom (claro/escuro) da imagem de cenário pelo brilho médio — decide a cor do
// texto por cima. Mesma regra da prévia do Pandoo (> 0,6 = claro).
function tomDaImagemBase64(base64) {
    return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => {
            try {
                const c = document.createElement("canvas");
                c.width = 32; c.height = 32;
                const ctx = c.getContext("2d");
                ctx.drawImage(img, 0, 0, 32, 32);
                const d = ctx.getImageData(0, 0, 32, 32).data;
                let soma = 0;
                for (let i = 0; i < d.length; i += 4) soma += 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2];
                resolve(soma / (d.length / 4) / 255 > 0.6 ? "claro" : "escuro");
            } catch (e) { resolve("claro"); }
        };
        img.onerror = () => resolve("claro");
        img.src = `data:image/png;base64,${base64}`;
    });
}

function anexarEventosIdentidadePropria(org) {
    const form = document.getElementById("form-wl");
    if (!form) return;
    const estado = {
        fundoApp: org.app_fundo || "padrao",
        corFundo: org.app_fundo_cor || "lavanda",
        fonte: org.mundo_fonte || "fredoka",
        fundo: org.mundo_fundo || "estrelas",
        mascote: org.mundo_mascote || "🐻",
        icone: undefined,          // undefined = não mexeu; null = remover; string = novo
        mascoteImagem: undefined,
        cenarioImagem: undefined,
        cenarioTom: undefined,
        temCenario: !!org.pandoo_cenario_imagem,
        temMascoteImagem: !!org.mundo_mascote_imagem,
        cenarioPreviaB64: base64Seguro(org.pandoo_cenario_imagem),
        mascotePreviaB64: base64Seguro(org.mundo_mascote_imagem),
    };

    function atualizarPrevia() {
        const fonte = fonteCrianca(estado.fonte);
        carregarFonteCrianca(fonte.url);
        const conteudo = document.getElementById("wl-previa-conteudo");
        conteudo.style.setProperty("--fonte-previa", fonte.familia);
        // A prévia desenha a imagem da clínica direto do base64 (a rota pública
        // só mostra o que já está salvo e com o módulo ligado).
        let tipo = estado.fundo === "pandoo" ? (org.pandoo_cenario_padrao || "bambu") : estado.fundo;
        if (tipo === "clinica" && !estado.cenarioPreviaB64) tipo = "estrelas";
        const tom = tipo === "clinica" ? (estado.cenarioTom || org.pandoo_cenario_tom || "claro") : TONS_CENARIO[tipo] || "claro";
        const camada = document.getElementById("wl-previa-cenario");
        montarCenarioAnimado(camada, { tipo: tipo === "clinica" ? "clinica" : tipo, imagemUrl: tipo === "clinica" ? `data:image/png;base64,${estado.cenarioPreviaB64}` : null, tom });
        document.querySelector(".wl-previa-celular").dataset.tom = tom;
        document.querySelector(".wl-previa-celular").dataset.fundo = tipo;
        const usarImagem = estado.mascote === "clinica" && estado.mascotePreviaB64;
        document.getElementById("wl-previa-mascote").innerHTML = svgMascote({
            emoji: usarImagem ? "clinica" : (estado.mascote === "clinica" ? "🐻" : estado.mascote), estagio: 2, tamanho: 70, flutuar: true,
            imagemUrl: usarImagem ? `data:image/png;base64,${estado.mascotePreviaB64}` : null,
        });
        document.getElementById("wl-cenario-img-grupo").style.display = (estado.fundo === "clinica" || estado.fundoApp === "clinica" || (estado.fundo === "pandoo" && org.pandoo_cenario_padrao === "clinica")) ? "" : "none";
        document.getElementById("wl-cores-fundo-grupo").style.display = estado.fundoApp === "cor" ? "" : "none";
        document.getElementById("wl-mascote-img-grupo").style.display = estado.mascote === "clinica" ? "" : "none";
    }

    function escolher(containerId, atributo, chave) {
        const chaveDataset = atributo.replace(/-([a-z])/g, (_, l) => l.toUpperCase());
        document.querySelectorAll(`#${containerId} [data-${atributo}]`).forEach(btn => btn.addEventListener("click", () => {
            document.querySelectorAll(`#${containerId} [data-${atributo}]`).forEach(b => b.classList.toggle("ativo", b === btn));
            estado[chave] = btn.dataset[chaveDataset];
            atualizarPrevia();
        }));
    }
    escolher("wl-fontes", "fonte", "fonte");
    escolher("wl-fundos", "fundo", "fundo");
    escolher("wl-mascotes", "mascote", "mascote");
    escolher("wl-fundos-app", "fundo-app", "fundoApp");
    document.querySelectorAll("#wl-cores-fundo [data-cor-fundo]").forEach(btn => btn.addEventListener("click", () => {
        document.querySelectorAll("#wl-cores-fundo [data-cor-fundo]").forEach(b => b.classList.toggle("ativo", b === btn));
        estado.corFundo = btn.dataset.corFundo;
    }));
    document.getElementById("wl-cor-fundo-livre").addEventListener("input", (e) => {
        document.querySelectorAll("#wl-cores-fundo [data-cor-fundo]").forEach(b => b.classList.remove("ativo"));
        estado.corFundo = e.target.value;
    });

    async function aoEscolherImagem(inputId, perfil, aoPreparar) {
        document.getElementById(inputId).addEventListener("change", async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            let preparada;
            try { preparada = await prepararImagemParaEnvio(file, perfil); }
            catch (err) { Toast.erro(err.message); e.target.value = ""; return; }
            if (preparada.aviso) Toast.info(preparada.aviso);
            await aoPreparar(preparada.base64);
            atualizarPrevia();
        });
    }
    aoEscolherImagem("wl-icone-arquivo", "icone", async (b64) => {
        estado.icone = b64;
        document.getElementById("wl-icone-preview").innerHTML = _imgBase64(b64, "width:100%; height:100%; object-fit:cover;");
    });
    aoEscolherImagem("wl-mascote-arquivo", "icone", async (b64) => {
        estado.mascoteImagem = b64;
        estado.mascotePreviaB64 = b64;
        document.getElementById("wl-mascote-preview").innerHTML = _imgBase64(b64, "width:100%; height:100%; object-fit:contain;");
    });
    aoEscolherImagem("wl-cenario-arquivo", "cenario", async (b64) => {
        estado.cenarioImagem = b64;
        estado.cenarioPreviaB64 = b64;
        estado.cenarioTom = await tomDaImagemBase64(b64);
        document.getElementById("wl-cenario-preview").innerHTML = _imgBase64(b64, "width:100%; height:100%; object-fit:cover;");
    });
    document.getElementById("wl-icone-remover").addEventListener("click", () => {
        estado.icone = null;
        document.getElementById("wl-icone-preview").textContent = "🐼";
        document.getElementById("wl-icone-arquivo").value = "";
    });
    document.getElementById("wl-copiar-link").addEventListener("click", () => {
        const link = `${location.origin}/#/entrar/${document.getElementById("wl-endereco").value.trim().toLowerCase()}`;
        navigator.clipboard?.writeText(link).then(() => Toast.sucesso("Link copiado!")).catch(() => Toast.info(link));
    });

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const body = {
            app_nome: document.getElementById("wl-app-nome").value.trim(),
            endereco_login: document.getElementById("wl-endereco").value.trim().toLowerCase(),
            login_mensagem: document.getElementById("wl-login-msg").value.trim(),
            mundo_fonte: estado.fonte,
            mundo_fundo: estado.fundo,
            mundo_mascote: estado.mascote,
            mundo_comemoracao: document.getElementById("wl-comemoracao").value.trim(),
            app_fundo: estado.fundoApp,
        };
        if (estado.fundoApp === "cor") body.app_fundo_cor = estado.corFundo;
        if (estado.icone !== undefined) body.app_icone_base64 = estado.icone;
        if (estado.mascoteImagem !== undefined) body.mundo_mascote_imagem = estado.mascoteImagem;
        if (estado.cenarioImagem !== undefined) {
            body.pandoo_cenario_imagem = estado.cenarioImagem;
            body.pandoo_cenario_tom = estado.cenarioTom || "claro";
        }
        try {
            await Api.put("/pessoas/organizacao", body);
            // A sessão recebe a identidade EFETIVA (sem o módulo, continua o padrão).
            const me = await Api.get("/auth/me");
            const u = Sessao.usuario;
            u.organizacao = me.organizacao;
            Sessao.usuario = u;
            aplicarTemaClinica(me.organizacao);
            Toast.sucesso("Identidade salva!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });

    atualizarPrevia();
}
