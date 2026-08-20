// ============================================================================
// views/modulos.js — Feature Flags: módulos opcionais da clínica (Doc 22A)
// ============================================================================

async function viewModulos(app) {
    const modulos = await Api.get("/modulos");
    const NOME_PLANO_MINIMO = { financeiro: "Pro", ia: "Pro", analytics_avancado: "Pro", integracoes: "Pro", white_label: "Enterprise" };

    const conteudo = `
    <div class="cartao-flat" style="margin-bottom:24px; display:flex; gap:10px; align-items:flex-start;">
      <span style="font-size:18px;">🧩</span>
      <p class="texto-sm texto-suave">
        Cada módulo abaixo só pode ser ligado se estiver incluído no <strong>plano contratado</strong> da sua clínica.
        Módulos essenciais (Jornada, Biblioteca, Comunicação, Diário Terapêutico, Gamificação, Agenda) estão sempre
        ativos e não aparecem aqui.
      </p>
    </div>
    <div class="grade" style="grid-template-columns: repeat(auto-fill, minmax(280px,1fr));">
      ${modulos.map(m => `
        <div class="cartao" style="${!m.liberado_pelo_plano ? "opacity:.55;" : ""}">
          <div class="linha-entre" style="margin-bottom:10px;">
            <span style="font-size:30px;">${m.icone}</span>
            ${m.liberado_pelo_plano ? `
              <label class="chave-toggle">
                <input type="checkbox" class="chk-modulo" data-codigo="${m.codigo}" ${m.habilitado ? "checked" : ""} />
                <span class="chave-slider"></span>
              </label>` : `<span class="badge badge-neutro">Fora do plano</span>`}
          </div>
          <h3 style="font-size:15.5px;">${escapeHtml(m.nome)}</h3>
          <p class="texto-sm texto-suave" style="margin-top:6px;">${escapeHtml(m.descricao)}</p>
          ${!m.liberado_pelo_plano ? `<p class="texto-xs" style="margin-top:10px; color:var(--cor-marca-escura); font-weight:700;">Disponível a partir do plano ${NOME_PLANO_MINIMO[m.codigo] || "Pro"}</p>` : ""}
        </div>`).join("")}
    </div>`;

    app.innerHTML = renderShellSidebar("#/gestor/modulos", "Módulos da Plataforma", conteudo);
    anexarEventosShell();

    document.querySelectorAll(".chk-modulo").forEach(chk => {
        chk.addEventListener("change", async () => {
            try {
                const r = await Api.post(`/modulos/${chk.dataset.codigo}/toggle`);
                Toast.sucesso(r.habilitado ? "Módulo ativado!" : "Módulo desativado.");
                // Atualiza a sessão para a navegação refletir a mudança imediatamente
                const me = await Api.get("/auth/me");
                const u = Sessao.usuario;
                u.organizacao.modulos_habilitados = me.organizacao.modulos_habilitados;
                Sessao.usuario = u;
                despachar();
            } catch (err) {
                Toast.erro(err.message);
                chk.checked = !chk.checked;
            }
        });
    });
}
