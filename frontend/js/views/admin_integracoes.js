// ============================================================================
// views/admin_integracoes.js — Central de Integrações da PLATAFORMA (Admin)
//
// Diferente de views/integracoes.js (Módulo 10, uma linha por clínica), esta
// tela guarda as credenciais da PRÓPRIA Panda Tech — hoje a peça principal é
// o Mercado Pago que gera o PIX de cobrança quando uma clínica nova é
// cadastrada (ver admin.js > abrirModalNovaClinica). WhatsApp e Google
// Agenda entram por paridade visual com a tela do Gestor, mas com o nível de
// integração que já existe de fato — nada aqui finge estar pronto quando
// não está.
// ============================================================================

async function viewAdminIntegracoes(app) {
    const lista = await Api.get("/admin/integracoes");
    const porTipo = Object.fromEntries(lista.map(i => [i.tipo, i]));
    const mp = porTipo.mercadopago, wa = porTipo.whatsapp, google = porTipo.google_calendar;

    const conteudo = `
    <div class="cartao-flat" style="margin-bottom:24px; display:flex; gap:10px; align-items:flex-start;">
      <span style="font-size:18px;">ℹ️</span>
      <p class="texto-sm texto-suave">
        Estas são as credenciais da própria Panda Tech (não de uma clínica) — usadas para cobrar as clínicas pela
        assinatura do plano. Nada aqui é compartilhado com o painel de nenhuma clínica.
      </p>
    </div>
    <div class="grade" style="grid-template-columns: repeat(auto-fill, minmax(320px,1fr)); gap:16px;">

      <!-- Mercado Pago (gateway de pagamento) -->
      <div class="cartao" id="cartao-mercadopago">
        <div class="linha-entre" style="margin-bottom:10px;">
          <span style="font-size:30px;">${mp.icone}</span>
          <span class="badge ${mp.status === "conectado" ? "badge-sucesso" : "badge-neutro"}">
            ${mp.status === "conectado" ? "✓ Conectado" : "Desconectado"}
          </span>
        </div>
        <h3 style="font-size:15.5px;">${escapeHtml(mp.nome)}</h3>
        <p class="texto-sm texto-suave" style="margin-top:6px;">${escapeHtml(mp.descricao)}</p>
        <form id="form-mp-plataforma" style="margin-top:12px; display:flex; flex-direction:column; gap:8px;">
          <input type="password" id="mp-plat-access-token" placeholder="Access Token do Mercado Pago" autocomplete="off" />
          <input type="text" id="mp-plat-public-key" placeholder="Public Key (opcional)" autocomplete="off" />
          <input type="password" id="mp-plat-webhook-secret" placeholder="Chave secreta do Webhook (necessária para confirmar pagamento sozinho)" autocomplete="off" />
          <button type="submit" class="botao botao-primario botao-sm">Salvar</button>
        </form>
        <p class="texto-xs texto-suave" style="margin-top:10px;">
          Não sabe onde pegar? No painel do Mercado Pago: <strong>Seu negócio → Configurações → Credenciais → Credenciais de produção</strong>.
        </p>
        <p class="texto-xs texto-suave" style="margin-top:6px;">
          A chave secreta do webhook fica em <strong>Suas integrações > [seu app] > Webhooks > Chave secreta</strong> — é DIFERENTE da chave de cada clínica (cada uma tem a própria conta de Mercado Pago). Sem ela configurada aqui, a assinatura NUNCA vai validar e a cobrança de assinatura das clínicas não confirma sozinha.
        </p>
        ${mp.status === "conectado" ? `
        <hr style="border:none; border-top:1px solid var(--cor-borda); margin:14px 0;" />
        <div class="linha-entre">
          <div>
            <p class="texto-sm" style="font-weight:700;">Cobrança automática</p>
            <p class="texto-xs texto-suave" style="margin-top:2px; max-width:220px;">
              Gera o PIX da assinatura de cada clínica ativa/inadimplente todo mês, sozinho.
            </p>
          </div>
          <label class="chave-toggle">
            <input type="checkbox" id="chk-cobranca-automatica" ${mp.cobranca_automatica_ativa ? "checked" : ""} />
            <span class="chave-slider"></span>
          </label>
        </div>
        <p class="texto-xs texto-suave" style="margin-top:8px;">
          ${mp.cobranca_automatica_ativa
            ? "✅ Ligada — as clínicas estão sendo cobradas todo mês. Acompanhe em \"Cobranças\", no menu."
            : "⏸️ Desligada — nenhuma clínica é cobrada automaticamente enquanto isso, mesmo com o Mercado Pago conectado."}
        </p>

        <hr style="border:none; border-top:1px solid var(--cor-borda); margin:14px 0;" />
        <p class="texto-sm" style="font-weight:700; margin-bottom:8px;">Como avisar o Gestor</p>
        <div class="linha-entre" style="margin-bottom:10px;">
          <div>
            <p class="texto-sm">🔔 Notificação no sininho</p>
            <p class="texto-xs texto-suave" style="margin-top:2px; max-width:220px;">Sempre entrega — aparece pro Gestor assim que ele acessa o app.</p>
          </div>
          <label class="chave-toggle">
            <input type="checkbox" id="chk-notif-sininho" ${mp.notificacoes?.sininho ? "checked" : ""} />
            <span class="chave-slider"></span>
          </label>
        </div>
        <div class="linha-entre">
          <div>
            <p class="texto-sm">💬 Notificação por WhatsApp</p>
            <p class="texto-xs texto-suave" style="margin-top:2px; max-width:220px;">
              ${wa.status === "conectado"
                ? "Manda do WhatsApp da Panda Tech pro contato da clínica. Só entrega se ela tiver mandado mensagem pro nosso WhatsApp nas últimas 24h."
                : "Conecte o WhatsApp da Panda Tech (card ao lado) pra este aviso funcionar."}
            </p>
          </div>
          <label class="chave-toggle">
            <input type="checkbox" id="chk-notif-whatsapp" ${mp.notificacoes?.whatsapp ? "checked" : ""} />
            <span class="chave-slider"></span>
          </label>
        </div>
        ` : `
        <p class="texto-xs texto-suave" style="margin-top:10px; font-style:italic;">
          Conecte o Mercado Pago acima para liberar a cobrança automática das clínicas.
        </p>`}
      </div>

      <!-- WhatsApp -->
      <div class="cartao" id="cartao-wa-plataforma">
        <div class="linha-entre" style="margin-bottom:10px;">
          <span style="font-size:30px;">${wa.icone}</span>
          <span class="badge ${wa.status === "conectado" ? "badge-sucesso" : "badge-neutro"}">
            ${wa.status === "conectado" ? "✓ Conectado" : "Desconectado"}
          </span>
        </div>
        <h3 style="font-size:15.5px;">${escapeHtml(wa.nome)}</h3>
        <p class="texto-sm texto-suave" style="margin-top:6px;">${escapeHtml(wa.descricao)}</p>
        <form id="form-wa-plataforma" style="margin-top:12px; display:flex; flex-direction:column; gap:8px;">
          <input type="text" id="wa-plat-phone-number-id" placeholder="Phone Number ID" autocomplete="off" />
          <input type="password" id="wa-plat-access-token" placeholder="Access Token" autocomplete="off" />
          <button type="submit" class="botao botao-primario botao-sm">Salvar</button>
        </form>
      </div>

      <!-- Google Agenda (Client ID/Secret do app OAuth da Panda Tech) -->
      <div class="cartao" id="cartao-google-plataforma">
        <div class="linha-entre" style="margin-bottom:10px;">
          <span style="font-size:30px;">${google.icone}</span>
          <span class="badge ${google.status === "conectado" ? "badge-sucesso" : "badge-neutro"}">
            ${google.status === "conectado" ? "✓ Configurado" : "Não configurado"}
          </span>
        </div>
        <h3 style="font-size:15.5px;">${escapeHtml(google.nome)}</h3>
        <p class="texto-sm texto-suave" style="margin-top:6px;">${escapeHtml(google.descricao)}</p>
        <form id="form-google-plataforma" style="margin-top:12px; display:flex; flex-direction:column; gap:8px;">
          <input type="text" id="google-plat-client-id" placeholder="Client ID" autocomplete="off" />
          <input type="password" id="google-plat-client-secret" placeholder="Client Secret" autocomplete="off" />
          <button type="submit" class="botao botao-primario botao-sm">Salvar</button>
        </form>
        <p class="texto-xs texto-suave" style="margin-top:10px;">
          Não tem ainda? Crie em <strong>console.cloud.google.com/apis/credentials</strong> (tipo "Aplicativo da Web") e ative a Google Calendar API antes.
        </p>
        <p class="texto-xs texto-suave" style="margin-top:6px;">
          Em <strong>URIs de redirecionamento autorizados</strong>, adicione exatamente:<br />
          <code style="user-select:all; word-break:break-all;">${escapeHtml(google.redirect_uri_esperado || "(configure ALLOWED_ORIGIN no servidor primeiro)")}</code>
        </p>
        <p class="texto-xs texto-suave" style="margin-top:10px;">
          Depois de salvo aqui, cada clínica clica em "Conectar" na própria Central de Integrações — nada mais precisa mudar por clínica.
        </p>
      </div>
    </div>`;

    app.innerHTML = renderShellSidebar("#/admin/integracoes", "Integrações", conteudo);
    anexarEventosShell();

    ativarToggleSenha(document.getElementById("mp-plat-access-token"));
    ativarToggleSenha(document.getElementById("mp-plat-webhook-secret"));
    ativarToggleSenha(document.getElementById("wa-plat-access-token"));
    ativarToggleSenha(document.getElementById("google-plat-client-secret"));

    document.getElementById("form-mp-plataforma").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            await Api.post("/admin/integracoes/mercadopago", {
                access_token: document.getElementById("mp-plat-access-token").value.trim(),
                public_key: document.getElementById("mp-plat-public-key").value.trim(),
                webhook_secret: document.getElementById("mp-plat-webhook-secret").value.trim(),
            });
            Toast.sucesso("Gateway de pagamento conectado!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });

    document.getElementById("form-wa-plataforma").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            await Api.post("/admin/integracoes/whatsapp", {
                phone_number_id: document.getElementById("wa-plat-phone-number-id").value.trim(),
                access_token: document.getElementById("wa-plat-access-token").value.trim(),
            });
            Toast.sucesso("WhatsApp conectado!");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });

    document.getElementById("form-google-plataforma").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            await Api.post("/admin/integracoes/google_calendar", {
                client_id: document.getElementById("google-plat-client-id").value.trim(),
                client_secret: document.getElementById("google-plat-client-secret").value.trim(),
            });
            Toast.sucesso("Google Agenda configurado! As clínicas já podem conectar a própria agenda.");
            despachar();
        } catch (err) { Toast.erro(err.message); }
    });

    const chkCobrancaAutomatica = document.getElementById("chk-cobranca-automatica");
    if (chkCobrancaAutomatica) chkCobrancaAutomatica.addEventListener("change", async (e) => {
        const ligar = e.target.checked;
        if (ligar && !confirm(
            "Ligar a cobrança automática? A partir de agora, todo mês será gerado um PIX real cobrando cada " +
            "clínica ativa (ou inadimplente) pelo valor do plano dela, sozinho, sem revisão manual.\n\n" +
            "Você pode desligar a qualquer momento aqui mesmo."
        )) {
            e.target.checked = false;
            return;
        }
        try {
            await Api.post("/admin/integracoes/mercadopago/cobranca-automatica", { ativa: ligar });
            Toast.sucesso(ligar ? "Cobrança automática ligada!" : "Cobrança automática desligada.");
            despachar();
        } catch (err) {
            e.target.checked = !ligar;
            Toast.erro(err.message);
        }
    });

    const chkSininho = document.getElementById("chk-notif-sininho");
    const chkWhatsapp = document.getElementById("chk-notif-whatsapp");
    async function salvarPreferenciasNotificacao(elAlterado) {
        try {
            await Api.post("/admin/integracoes/mercadopago/notificacoes", {
                sininho: chkSininho.checked,
                whatsapp: chkWhatsapp.checked,
            });
            Toast.sucesso("Preferência de aviso salva!");
        } catch (err) {
            elAlterado.checked = !elAlterado.checked;
            Toast.erro(err.message);
        }
    }
    if (chkSininho) chkSininho.addEventListener("change", () => salvarPreferenciasNotificacao(chkSininho));
    if (chkWhatsapp) chkWhatsapp.addEventListener("change", () => salvarPreferenciasNotificacao(chkWhatsapp));
}
