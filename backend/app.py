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

    @app.after_request
    def add_cors_headers(resp):
        resp.headers["Access-Control-Allow-Origin"] = allowed_origin
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
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
