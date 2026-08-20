// ============================================================================
// views/onboarding.js — Wizard guiado de primeiros passos (Doc 32)
//
// Boas-vindas -> Identidade -> Equipe -> Primeiro Paciente -> Modulos -> Conclusao
// Cada etapa reaproveita os MESMOS endpoints ja usados no resto do produto -
// o wizard e so uma camada de orquestracao/guia por cima deles.
// ============================================================================

const ETAPAS_ONBOARDING = ["boasvindas", "identidade", "equipe", "paciente", "modulos", "conclusao"];

async function viewOnboardingWizard(app) {
    const status = await Api.get("/onboarding/status");
    let etapaAtual = 0;
    if (status.etapas.equipe || status.etapas.paciente) etapaAtual = 2;

    app.innerHTML = `
    <div class="tela-cheia" style="align-items:flex-start; justify-content:center; background:var(--cor-fundo);">
      <div style="width:100%; max-width:640px; padding:32px 24px 60px;">
        <div class="linha-entre" style="margin-bottom:24px;">
          <div class="linha gap-2">
            <span style="font-size:22px;">${Sessao.usuario.organizacao?.logo_emoji || "🌟"}</span>
            <strong>${escapeHtml(Sessao.usuario.organizacao?.nome || "")}</strong>
          </div>
          <button type="button" class="botao-texto botao-sm" id="btn-pular-onboarding">Pular por agora →</button>
        </div>
        <div id="barra-progresso-onboarding" class="progresso-barra" style="margin-bottom:32px;"><div class="progresso-preenchimento" style="width:0%"></div></div>
        <div id="conteudo-etapa"></div>
      </div>
    </div>`;

    document.getElementById("btn-pular-onboarding").addEventListener("click", async () => {
        if (!confirm("Você pode configurar tudo isso depois em Equipe, Pacientes e Configurações. Pular por agora?")) return;
        await Api.post("/onboarding/concluir");
        location.hash = "#/gestor/dashboard";
    });

    function atualizarProgresso() {
        const pct = Math.round((etapaAtual / (ETAPAS_ONBOARDING.length - 1)) * 100);
        document.querySelector("#barra-progresso-onboarding .progresso-preenchimento").style.width = `${pct}%`;
    }

    async function irPara(indice) {
        etapaAtual = indice;
        atualizarProgresso();
        const nome = ETAPAS_ONBOARDING[indice];
        const el = document.getElementById("conteudo-etapa");
        if (nome === "boasvindas") renderBoasVindas(el);
        else if (nome === "identidade") renderIdentidade(el);
        else if (nome === "equipe") renderEquipe(el);
        else if (nome === "paciente") renderPaciente(el);
        else if (nome === "modulos") await renderModulos(el);
        else if (nome === "conclusao") await renderConclusao(el);
    }

    function renderBoasVindas(el) {
        el.innerHTML = `
        <div style="text-align:center; padding:20px 0;">
          ${svgMascote({ emoji: "🐻", estagio: 3, tamanho: 130, flutuar: true })}
          <h1 style="font-size:24px; margin-top:16px;">Bem-vindo(a) à ${escapeHtml(Sessao.usuario.organizacao?.nome || "sua clínica")}! 👋</h1>
          <p class="texto-suave" style="max-width:440px; margin:12px auto 28px; line-height:1.6;">
            Vamos deixar tudo pronto em poucos passos: identidade da clínica, sua equipe, o primeiro
            paciente e os módulos que você quer usar. Leva menos de 5 minutos.
          </p>
          <button class="botao botao-primario" id="btn-comecar" style="padding:14px 32px;">Vamos começar →</button>
        </div>`;
        document.getElementById("btn-comecar").addEventListener("click", () => irPara(1));
    }



    function renderEquipe(el) {
        el.innerHTML = `
        <div class="cartao">
          <p class="texto-xs texto-suave" style="font-weight:700;">PASSO 2 DE 4</p>
          <h2 style="margin-bottom:6px;">Convide sua equipe</h2>
          <p class="texto-sm texto-suave" style="margin-bottom:20px;">Cadastre ao menos um profissional. Ele recebe um link para criar a própria senha.</p>
          <form id="form-onb-equipe">
            <div class="campo"><label>Nome completo</label><input type="text" id="onb-prof-nome" required /></div>
            <div class="campo"><label>E-mail</label><input type="email" id="onb-prof-email" required /></div>
            <div class="campo">
              <label>Especialidade</label>
              <input type="text" id="onb-prof-esp" list="lista-especialidades-onb" placeholder="Ex: Fonoaudiologia" />
              <datalist id="lista-especialidades-onb">
                ${especialidadesDaClinica().map(e => `<option value="${escapeHtml(e)}">`).join("")}
              </datalist>
            </div>
            <div id="onb-equipe-resultado"></div>
            <div class="linha gap-3" style="margin-top:8px;">
              <button type="submit" class="botao botao-primario">Cadastrar e continuar →</button>
              <button type="button" class="botao botao-texto" id="btn-pular-etapa">Pular esta etapa</button>
            </div>
          </form>
        </div>`;
        document.getElementById("btn-pular-etapa").addEventListener("click", () => irPara(3));
        document.getElementById("form-onb-equipe").addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                const r = await Api.post("/pessoas/profissionais", {
                    nome: document.getElementById("onb-prof-nome").value.trim(),
                    email: document.getElementById("onb-prof-email").value.trim(),
                    especialidade: document.getElementById("onb-prof-esp").value,
                });
                document.getElementById("onb-equipe-resultado").innerHTML = `
                  <div class="cartao-flat" style="margin-top:12px;">
                    <p class="texto-sm" style="margin-bottom:8px;">✅ Profissional cadastrado! Envie este link para ativar a conta:</p>
                    <div class="linha gap-2">
                      <input type="text" readonly value="${location.origin}${location.pathname}${r.link_convite}" style="flex:1; padding:8px 10px; border-radius:8px; border:1.5px solid var(--cor-borda); font-size:12px;" />
                    </div>
                  </div>`;
                setTimeout(() => irPara(3), 1400);
            } catch (err) { Toast.erro(err.message); }
        });
    }

    function renderPaciente(el) {
        el.innerHTML = `
        <div class="cartao">
          <p class="texto-xs texto-suave" style="font-weight:700;">PASSO 3 DE 4</p>
          <h2 style="margin-bottom:6px;">Cadastre o primeiro paciente</h2>
          <p class="texto-sm texto-suave" style="margin-bottom:20px;">E, se quiser, já vincule o responsável — ele também recebe um link de ativação.</p>
          <form id="form-onb-paciente">
            <div class="campo"><label>Nome da criança</label><input type="text" id="onb-pac-nome" required /></div>
            <div class="campo"><label>Data de nascimento</label><input type="date" id="onb-pac-nasc" required /></div>
            <hr style="border:none; border-top:1px solid var(--cor-borda); margin:16px 0;" />
            <p class="texto-sm" style="font-weight:700; margin-bottom:10px;">Responsável (opcional agora)</p>
            <div class="campo"><label>Nome</label><input type="text" id="onb-resp-nome" /></div>
            <div class="campo"><label>E-mail</label><input type="email" id="onb-resp-email" /></div>
            <div id="onb-paciente-resultado"></div>
            <div class="linha gap-3" style="margin-top:8px;">
              <button type="submit" class="botao botao-primario">Cadastrar e continuar →</button>
              <button type="button" class="botao botao-texto" id="btn-pular-etapa">Pular esta etapa</button>
            </div>
          </form>
        </div>`;
        document.getElementById("btn-pular-etapa").addEventListener("click", () => irPara(4));
        document.getElementById("form-onb-paciente").addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                const r = await Api.post("/pessoas/pacientes", {
                    nome: document.getElementById("onb-pac-nome").value.trim(),
                    data_nascimento: document.getElementById("onb-pac-nasc").value,
                    avatar_mascote: "🐻",
                });
                const respNome = document.getElementById("onb-resp-nome").value.trim();
                const respEmail = document.getElementById("onb-resp-email").value.trim();
                let html = `<div class="cartao-flat" style="margin-top:12px;"><p class="texto-sm">✅ Paciente cadastrado!</p>`;
                if (respNome && respEmail) {
                    const rResp = await Api.post(`/pessoas/pacientes/${r.id}/vincular-responsavel`, { nome: respNome, email: respEmail });
                    if (rResp.link_convite) {
                        html += `<p class="texto-sm" style="margin-top:8px;">Envie este link para ${escapeHtml(respNome)} ativar a conta:</p>
                          <input type="text" readonly value="${location.origin}${location.pathname}${rResp.link_convite}" style="width:100%; margin-top:6px; padding:8px 10px; border-radius:8px; border:1.5px solid var(--cor-borda); font-size:12px;" />`;
                    }
                }
                html += `</div>`;
                document.getElementById("onb-paciente-resultado").innerHTML = html;
                setTimeout(() => irPara(4), 1400);
            } catch (err) { Toast.erro(err.message); }
        });
    }

    async function renderModulos(el) {
        const modulos = await Api.get("/modulos");
        el.innerHTML = `
        <div class="cartao">
          <p class="texto-xs texto-suave" style="font-weight:700;">PASSO 4 DE 4</p>
          <h2 style="margin-bottom:6px;">Módulos da plataforma</h2>
          <p class="texto-sm texto-suave" style="margin-bottom:20px;">Ative o que sua clínica vai usar. Dá pra mudar isso quando quiser em Módulos.</p>
          <div class="coluna gap-2">
            ${modulos.map(m => `
              <div class="linha-entre cartao-flat" style="${!m.liberado_pelo_plano ? "opacity:.5;" : ""}">
                <div class="linha gap-2"><span style="font-size:20px;">${m.icone}</span><span class="texto-sm" style="font-weight:600;">${escapeHtml(m.nome)}</span></div>
                ${m.liberado_pelo_plano ? `
                  <label class="chave-toggle">
                    <input type="checkbox" class="chk-onb-modulo" data-codigo="${m.codigo}" ${m.habilitado ? "checked" : ""} />
                    <span class="chave-slider"></span>
                  </label>` : `<span class="texto-xs texto-suave">fora do plano</span>`}
              </div>`).join("")}
          </div>
          <button type="button" class="botao botao-primario" id="btn-onb-modulos-continuar" style="margin-top:20px;">Próximo →</button>
        </div>`;
        el.querySelectorAll(".chk-onb-modulo").forEach(chk => {
            const estadoOriginal = chk.checked;
            chk.addEventListener("change", async () => {
                if (chk.checked !== estadoOriginal) {
                    try { await Api.post(`/modulos/${chk.dataset.codigo}/toggle`); } catch (err) { Toast.erro(err.message); chk.checked = !chk.checked; }
                }
            });
        });
        document.getElementById("btn-onb-modulos-continuar").addEventListener("click", () => irPara(5));
    }

    async function renderConclusao(el) {
        const statusFinal = await Api.get("/onboarding/status");
        await Api.post("/onboarding/concluir");
        const itens = [
            { chave: "identidade", label: "Identidade da clínica" },
            { chave: "equipe", label: "Equipe cadastrada" },
            { chave: "paciente", label: "Primeiro paciente" },
            { chave: "responsavel", label: "Responsável vinculado" },
        ];
        el.innerHTML = `
        <div style="text-align:center; padding:20px 0;">
          ${svgMascote({ emoji: "🐻", estagio: 4, tamanho: 130, flutuar: true })}
          <h1 style="font-size:24px; margin-top:16px;">Tudo pronto! 🎉</h1>
          <p class="texto-suave" style="max-width:420px; margin:10px auto 24px;">Sua clínica já está configurada. Você pode ajustar qualquer coisa depois nos menus normais.</p>
          <div class="cartao" style="text-align:left; max-width:380px; margin:0 auto 28px;">
            ${itens.map(i => `<div class="linha gap-2" style="padding:6px 0;"><span>${statusFinal.etapas[i.chave] ? "✅" : "⬜"}</span><span class="texto-sm">${i.label}</span></div>`).join("")}
          </div>
          <button class="botao botao-primario" id="btn-ir-dashboard" style="padding:14px 32px;">Ir para o Dashboard →</button>
        </div>`;
        document.getElementById("btn-ir-dashboard").addEventListener("click", () => { location.hash = "#/gestor/dashboard"; });
    }

    irPara(etapaAtual);
}

