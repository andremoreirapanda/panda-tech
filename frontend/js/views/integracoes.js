// ============================================================================
// views/integracoes.js — Central de Integrações (Módulo 10)
//
// ATUALIZAÇÃO: cada integração agora tem um fluxo de conexão real (não é
// mais um toggle genérico único). Google Agenda usa OAuth2 (redireciona pro
// Google); WhatsApp e Pagamento pedem as credenciais da própria clínica em
// um formulário; ERP continua como toggle simples (é honesto: sem saber
// qual ERP a clínica-piloto usa, não dá pra integrar de fato — ver
// GAP_ANALYSIS.md).
// ============================================================================

async function viewIntegracoes(app) {
    const lista = await Api.get("/integracoes");
    const params = new URLSearchParams(location.hash.split("?")[1] || "");

    const porTipo = Object.fromEntries(lista.map(i => [i.tipo, i]));

    const conteudo = `
    <div class="cartao-flat" style="margin-bottom:24px; display:flex; gap:10px; align-items:flex-start;">
      <span style="font-size:18px;">ℹ️</span>
      <p class="texto-sm texto-suave">
        Conecte cada integração com as credenciais reais da clínica (ou do provedor de teste, no piloto). Nenhuma senha
        fica visível depois de salva — só a clínica dona consegue usá-la, e nenhum dado é enviado a outra clínica.
      </p>
    </div>
    <div class="grade" style="grid-template-columns: repeat(auto-fill, minmax(320px,1fr)); gap:16px;">

      <!-- Google Agenda -->
      <div class="cartao" id="cartao-google">
        <div class="linha-entre" style="margin-bottom:10px;">
          <span style="font-size:30px;">📅</span>
          <span class="badge ${porTipo.google_calendar.status === "conectado" ? "badge-sucesso" : "badge-neutro"}">
            ${porTipo.google_calendar.status === "conectado" ? "✓ Conectado" : "Desconectado"}
          </span>
        </div>
        <h3 style="font-size:15.5px;">Google Agenda</h3>
        <p class="texto-sm texto-suave" style="margin-top:6px;">Sincroniza a agenda da clínica com o Google Calendar da equipe.</p>
        ${!porTipo.google_calendar.disponivel_no_saas ? `
          <p class="texto-xs" style="margin-top:12px; color:var(--cor-erro,#E8385A);">
            O SaaS ainda não configurou as credenciais OAuth do Google (variáveis GOOGLE_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI). Ver SETUP_INTEGRACOES.md.
          </p>
        ` : porTipo.google_calendar.status === "conectado" ? `
          <button class="botao botao-secundario botao-sm" id="btn-google-desconectar" style="margin-top:14px;">Desconectar</button>
        ` : `
          <button class="botao botao-primario botao-sm" id="btn-google-conectar" style="margin-top:14px;">Conectar com o Google</button>
        `}
      </div>

      <!-- WhatsApp -->
      <div class="cartao" id="cartao-whatsapp">
        <div class="linha-entre" style="margin-bottom:10px;">
          <span style="font-size:30px;">💬</span>
          <span class="badge ${porTipo.whatsapp.status === "conectado" ? "badge-sucesso" : "badge-neutro"}">
            ${porTipo.whatsapp.status === "conectado" ? "✓ Conectado" : "Desconectado"}
          </span>
        </div>
        <h3 style="font-size:15.5px;">WhatsApp Business</h3>
        <p class="texto-sm texto-suave" style="margin-top:6px;">Envia lembretes de missão e consulta direto no WhatsApp da família (WhatsApp Cloud API da Meta).</p>
        <form id="form-whatsapp" style="margin-top:12px; display:flex; flex-direction:column; gap:8px;">
          <input type="text" id="wa-phone-number-id" placeholder="Phone Number ID" autocomplete="off" />
          <input type="password" id="wa-access-token" placeholder="Access Token" autocomplete="off" />
          <button type="submit" class="botao botao-primario botao-sm">Salvar</button>
        </form>
        ${porTipo.whatsapp.status === "conectado" ? `
          <div class="linha gap-2" style="margin-top:8px;">
            <input type="text" id="wa-telefone-teste" placeholder="Seu telefone com DDD" style="flex:1;" />
            <button class="botao botao-secundario botao-sm" id="btn-whatsapp-testar">Enviar teste</button>
          </div>
        ` : ""}
      </div>

      <!-- Pagamento -->
      <div class="cartao" id="cartao-pagamento">
        <div class="linha-entre" style="margin-bottom:10px;">
          <span style="font-size:30px;">💳</span>
          <span class="badge ${porTipo.pagamento.status === "conectado" ? "badge-sucesso" : "badge-neutro"}">
            ${porTipo.pagamento.status === "conectado" ? "✓ Conectado" : "Desconectado"}
          </span>
        </div>
        <h3 style="font-size:15.5px;">Gateway de pagamento</h3>
        <p class="texto-sm texto-suave" style="margin-top:6px;">Habilita cobrança automática via PIX direto no app da família (Mercado Pago).</p>
        <form id="form-pagamento" style="margin-top:12px; display:flex; flex-direction:column; gap:8px;">
          <input type="password" id="mp-access-token" placeholder="Access Token do Mercado Pago" autocomplete="off" />
          <button type="submit" class="botao botao-primario botao-sm">Salvar</button>
        </form>
      </div>

      <!-- ERP -->
      <div class="cartao" id="cartao-erp">
        <div class="linha-entre" style="margin-bottom:10px;">
          <span style="font-size:30px;">🧾</span>
          <label class="chave-toggle">
            <input type="checkbox" class="chk-integracao" data-tipo="erp" ${porTipo.erp.status === "conectado" ? "checked" : ""} />
            <span class="chave-slider"></span>
          </label>
        </div>
        <h3 style="font-size:15.5px;">ERP / Sistema financeiro</h3>
        <p class="texto-sm texto-suave" style="margin-top:6px;">Sincroniza cobranças e notas fiscais com o ERP já usado pela clínica.</p>
        <p class="texto-xs texto-suave" style="margin-top:10px;">
          Ainda não integrado de verdade — depende de qual ERP a clínica-piloto usa. Este toggle só guarda a intenção.
        </p>
      </div>
    </div>`;

    app.innerHTML = renderShellSidebar("#/gestor/integracoes", "Central de Integrações", conteudo);
    anexarEventosShell();

    // Mensagem de retorno do fluxo OAuth do Google (redirect com querystring)
    if (params.get("google_calendar") === "conectado") Toast.sucesso("Google Agenda conectado! 🎉");
    if (params.get("google_calendar") === "erro") Toast.erro(`Não deu para conectar o Google: ${params.get("motivo") || "tente novamente"}`);

    document.querySelectorAll(".chk-integracao").forEach(chk => {
        chk.addEventListener("change", async () => {
            try {
                const r = await Api.post(`/integracoes/${chk.dataset.tipo}/toggle`);
                Toast.sucesso(r.status === "conectado" ? "Integração ativada!" : "Integração desativada.");
                despachar();
            } catch (err) {
                Toast.erro(err.message);
                chk.checked = !chk.checked;
            }
        });
    });

    const btnGoogleConectar = document.getElementById("btn-google-conectar");
    if (btnGoogleConectar) btnGoogleConectar.addEventListener("click", async () => {
        try {
            const r = await Api.get("/integracoes/google_calendar/autorizar");
            window.location.href = r.url; // navegação de página inteira (fluxo OAuth do Google)
        } catch (err) { Toast.erro(err.message); }
    });

    const btnGoogleDesconectar = document.getElementById("btn-google-desconectar");
    if (btnGoogleDesconectar) btnGoogleDesconectar.addEventListener("click", async () => {
        if (!confirm("Desconectar o Google Agenda desta clínica?")) return;
        try {
            await Api.post("/integracoes/google_calendar/desconectar");
            Toast.sucesso("Google Agenda desconectado.");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });

    document.getElementById("form-whatsapp").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            await Api.post("/integracoes/whatsapp/config", {
                phone_number_id: document.getElementById("wa-phone-number-id").value.trim(),
                access_token: document.getElementById("wa-access-token").value.trim(),
            });
            Toast.sucesso("WhatsApp conectado!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });

    const btnWhatsappTestar = document.getElementById("btn-whatsapp-testar");
    if (btnWhatsappTestar) btnWhatsappTestar.addEventListener("click", async () => {
        const telefone = document.getElementById("wa-telefone-teste").value.trim();
        if (!telefone) { Toast.erro("Informe um telefone."); return; }
        try {
            await Api.post("/integracoes/whatsapp/testar", { telefone });
            Toast.sucesso("Mensagem de teste enviada! Confira o WhatsApp informado.");
        } catch (err) { Toast.erro(err.message); }
    });

    document.getElementById("form-pagamento").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            await Api.post("/integracoes/pagamento/config", {
                access_token: document.getElementById("mp-access-token").value.trim(),
            });
            Toast.sucesso("Gateway de pagamento conectado!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });
}
