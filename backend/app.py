"""
ENCANTO EM CASA — Plataforma de Desenvolvimento Infantil
Backend (Flask + SQLite)

Para rodar:
    cd backend
    pip install -r requirements.txt
    python seed.py      # cria o banco e popula dados de demonstração
    python app.py        # sobe o servidor em http://localhost:5000
"""
import os

from dotenv import load_dotenv

load_dotenv()  # carrega backend/.env se existir — precisa vir antes dos imports que leem env vars (auth.py, calendar_sync_service.py etc.)

from flask import Flask, jsonify, send_from_directory, request

import db
from blueprints import (
    auth_bp, pessoas_bp, jornada_bp, biblioteca_bp, comunicacao_bp,
    agenda_bp, gamificacao_bp, financeiro_bp, indicadores_bp,
    notificacoes_bp, admin_bp, integracoes_bp, diario_bp, modulos_bp, onboarding_bp,
)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


def create_app():
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
    db.init_app(app)

    # CORS simples (permite abrir o front-end separadamente durante o desenvolvimento).
    # Em produção, defina ALLOWED_ORIGIN (ex: https://app.suaclinica.com.br) em vez de
    # deixar '*' — sem isso, qualquer site pode fazer requisições autenticadas à API.
    allowed_origin = os.environ.get("ALLOWED_ORIGIN", "*")
    if allowed_origin == "*":
        print("⚠️  ALLOWED_ORIGIN não definida — usando '*' (qualquer site pode fazer "
              "requisições à API). Defina ALLOWED_ORIGIN em produção (ex: "
              "https://app.suaclinica.com.br).")

    @app.after_request
    def add_cors_headers(resp):
        resp.headers["Access-Control-Allow-Origin"] = allowed_origin
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        # Correção de auditoria: cabeçalhos de segurança HTTP básicos — nenhum
        # deles existia antes. Sem X-Frame-Options/CSP frame-ancestors, a
        # aplicação (que lida com dados de crianças) podia ser embutida num
        # <iframe> de terceiros para clickjacking; sem X-Content-Type-Options,
        # o navegador podia "adivinhar" o tipo de conteúdo de uma resposta
        # (risco de MIME-sniffing); HSTS reforça que o navegador só volte a
        # falar com o domínio via HTTPS. CSP aqui é propositalmente permissiva
        # (o front-end é um SPA que usa scripts/estilos inline) — o objetivo é
        # bloquear frame embedding, não travar o app; endurecer o CSP fica como
        # próximo passo se/quando o front parar de depender de inline.
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # Correção de auditoria (recomendação 4, 25/08/2026 — "endurecer quando o
        # front parar de depender de inline"): checado o código real do front-end
        # antes de mexer aqui — NÃO existe nenhum <script> inline nem atributo
        # onXXX= em lugar nenhum (todo JS vem de arquivo, mesma origem), então
        # script-src trava para 'self' sem quebrar nada — é o ganho mais
        # importante do CSP contra XSS (impede um <script> injetado de rodar).
        # O que ainda existe, em escala grande (800+ ocorrências), é style="..."
        # inline nas telas que montam HTML via template string — por isso
        # style-src ainda precisa de 'unsafe-inline'; remover isso é um
        # refactor de front-end à parte, não uma correção de segurança pontual,
        # e fica registrado como pendência conhecida (não é o mesmo risco que
        # permitir <script> arbitrário). img-src cobre data: porque fotos/anexos
        # são armazenados e exibidos como base64 inline, não como arquivo servido.
        resp.headers.setdefault("Content-Security-Policy", (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            # Achado de UAT (26/08/2026): o autopreenchimento de endereço por
            # CEP (ativarAutoCompleteCep, em util.js) chama a API pública do
            # ViaCEP direto do navegador. Sem esta exceção, o próprio
            # connect-src 'self' bloqueava a chamada silenciosamente (o
            # fetch() falha com erro de rede, que o front-end já tratava sem
            # travar o preenchimento manual — por isso parecia só "não
            # funcionar", sem nenhum erro visível). Nenhum dado da clínica ou
            # de pacientes é enviado ao ViaCEP, só o CEP digitado.
            "connect-src 'self' https://viacep.com.br; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'"
        ))
        # Nota (Fase 1 da cobrança por cartão, 26/08/2026): o Card Payment
        # Brick embutido da Mercado Pago (que precisaria de *.mercadopago.com
        # liberado aqui) foi testado ao vivo e trava na inicialização nesta
        # conta ("Bricks.create: Bricks component initialization failed"),
        # mesmo com CSP, chave pública e rede corretas. Trocamos pelo
        # Checkout Pro (link hospedado pela própria Mercado Pago, aberto em
        # nova aba) — que não roda nenhum JS deles aqui — então essas
        # exceções de CSP não são mais necessárias. Ver criar_checkout_cartao
        # em pagamento_plataforma_service.py.
        # Navegadores ignoram este cabeçalho em respostas servidas por HTTP puro
        # (não-HTTPS), então é seguro sempre enviá-lo — mesmo sem confiar em
        # X-Forwarded-Proto, que o Apache/Passenger da produção pode ou não
        # repassar de forma confiável.
        resp.headers.setdefault("Strict-Transport-Security", "max-age=15552000; includeSubDomains")
        return resp

    @app.route("/api/<path:_any>", methods=["OPTIONS"])
    def options_handler(_any):
        return "", 204

    app.register_blueprint(auth_bp.bp)
    app.register_blueprint(pessoas_bp.bp)
    app.register_blueprint(jornada_bp.bp)
    app.register_blueprint(biblioteca_bp.bp)
    app.register_blueprint(comunicacao_bp.bp)
    app.register_blueprint(agenda_bp.bp)
    app.register_blueprint(gamificacao_bp.bp)
    app.register_blueprint(financeiro_bp.bp)
    app.register_blueprint(indicadores_bp.bp)
    app.register_blueprint(notificacoes_bp.bp)
    app.register_blueprint(admin_bp.bp)
    app.register_blueprint(integracoes_bp.bp)
    app.register_blueprint(diario_bp.bp)
    app.register_blueprint(modulos_bp.bp)
    app.register_blueprint(onboarding_bp.bp)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "produto": "Panda Tech"})

    @app.errorhandler(404)
    def not_found(e):
        # CORREÇÃO (agosto/2026): uma rota de API mal digitada (ex: uma URL
        # de webhook configurada errada num serviço externo) caía aqui e
        # recebia de volta HTML da SPA com status 200 — o chamador (ex:
        # Mercado Pago) entendia que a notificação tinha sido "entregue com
        # sucesso" e nunca mais tentava de novo, mesmo o endpoint real nunca
        # tendo sido chamado. Agora, qualquer caminho começando com /api/
        # que não bata com nenhuma rota real recebe um 404 JSON de verdade.
        if request.path.startswith("/api/"):
            return jsonify({"erro": "rota não encontrada"}), 404
        # Se não for uma rota de API, serve o front-end (SPA) — permite F5 em qualquer rota.
        return send_from_directory(FRONTEND_DIR, "index.html")

    # Serve o front-end estático (SPA) na raiz
    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    return app


app = create_app()

if __name__ == "__main__":
    if not os.path.exists(db.DB_PATH):
        print("⚠️  Banco de dados não encontrado. Rode primeiro: python seed.py")
    if not os.environ.get("ENCANTO_SECRET"):
        print("⚠️  ENCANTO_SECRET não definida — usando a chave padrão de desenvolvimento.")
        print("    NÃO rode assim em produção (qualquer um pode forjar tokens de login).")
    # Correção de auditoria (item 4.2): o default seguro é "desligado" — quem
    # quiser o debugger interativo do Werkzeug em desenvolvimento local define
    # FLASK_DEBUG=1 explicitamente (o .env.example já documenta isso).
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode, use_reloader=debug_mode)
