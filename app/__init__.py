import secrets
import time

from flask import Flask, abort, flash, redirect, request, session, url_for
from flask_login import LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()


def create_app(test_config=None):
    from .config import carregar
    from .crypto import chaveiro

    app = Flask(__name__, instance_relative_config=True)
    app.config.update(carregar(test_config))
    chaveiro.configurar(app.config["ENCRYPTION_KEYS"], app.config["ENCRYPTION_ACTIVE_KEY"],
                        app.config["BLIND_INDEX_KEY"])

    if app.config["BEHIND_PROXY"]:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Entre para continuar."
    login_manager.login_message_category = "aviso"
    login_manager.session_protection = "strong"

    from . import models  # noqa: F401
    from .routes import admin, agenda, animais, atendimento, auth, lgpd, main, responsaveis

    for bp in (auth.bp, main.bp, responsaveis.bp, animais.bp, agenda.bp, atendimento.bp,
               admin.bp, lgpd.bp):
        app.register_blueprint(bp)

    from .cli import register_cli
    register_cli(app)

    from .filtros import registrar_filtros
    registrar_filtros(app)

    # ---------- Proteções por requisição ----------
    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(32)
        return session["_csrf"]

    @app.before_request
    def protecoes():
        if request.method == "POST" and app.config["CSRF_ENABLED"]:
            token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
            esperado = session.get("_csrf") or ""
            if not token or not esperado or not secrets.compare_digest(token, esperado):
                abort(400, "Sessão expirada ou formulário inválido. Recarregue a página.")

        if current_user.is_authenticated:
            # expiração por inatividade
            agora_s = int(time.time())
            ultimo = session.get("_ultimo", agora_s)
            if agora_s - ultimo > app.config["SESSAO_INATIVIDADE_MIN"] * 60:
                logout_user()
                session.clear()
                flash("Sua sessão expirou por inatividade.", "aviso")
                return redirect(url_for("auth.login"))
            session["_ultimo"] = agora_s

            livres = {"auth.logout", "auth.trocar_senha", "auth.configurar_2fa", "static",
                      "lgpd.aviso"}
            if request.endpoint not in livres:
                if current_user.trocar_senha:
                    return redirect(url_for("auth.trocar_senha"))
                if app.config["EXIGIR_2FA"] and not current_user.totp_ativo:
                    return redirect(url_for("auth.configurar_2fa"))

    @app.context_processor
    def injetar():
        from .models import PERFIS
        return {"csrf_token": csrf_token, "PERFIS": PERFIS, "config": app.config}

    @app.after_request
    def cabecalhos(resp):
        connect = "'self' https://viacep.com.br" if app.config["USAR_VIACEP"] else "'self'"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            f"connect-src {connect}; font-src 'self'; object-src 'none'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'")
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if app.config["SESSION_COOKIE_SECURE"]:
            resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        if request.endpoint != "static":
            # dados sensíveis não devem ficar em cache do navegador/proxy
            resp.headers["Cache-Control"] = "no-store"
            resp.headers["Pragma"] = "no-cache"
        return resp

    if not app.config["PRODUCAO"]:
        with app.app_context():
            db.create_all()

    return app
