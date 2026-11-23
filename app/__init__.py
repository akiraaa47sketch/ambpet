import os
import secrets

from flask import Flask, abort, request, session
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-troque-esta-chave"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL", "sqlite:///" + os.path.join(app.instance_path, "ambpet.db")
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 10,
        CLINICA_NOME=os.environ.get("CLINICA_NOME", "Clínica Veterinária"),
        CLINICA_ENDERECO=os.environ.get("CLINICA_ENDERECO", ""),
        CLINICA_TELEFONE=os.environ.get("CLINICA_TELEFONE", ""),
        AGENDA_INTERVALO_MIN=int(os.environ.get("AGENDA_INTERVALO_MIN", "15")),
        BACKUP_DIR=os.environ.get("BACKUP_DIR", os.path.join(app.root_path, "..", "backups")),
        CSRF_ENABLED=True,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Faça login para continuar."
    login_manager.login_message_category = "warning"

    from . import models  # noqa: F401
    from .routes import admin, agenda, animais, auth, clinica, main, responsaveis

    for bp in (auth.bp, main.bp, responsaveis.bp, animais.bp, agenda.bp, clinica.bp, admin.bp):
        app.register_blueprint(bp)

    from .cli import register_cli
    register_cli(app)

    from .utils import formatar_cpf, formatar_telefone, formatar_cep, idade_texto
    app.jinja_env.filters["cpf"] = formatar_cpf
    app.jinja_env.filters["telefone"] = formatar_telefone
    app.jinja_env.filters["cep"] = formatar_cep
    app.jinja_env.filters["idade"] = idade_texto
    app.jinja_env.filters["data"] = lambda d: d.strftime("%d/%m/%Y") if d else ""
    app.jinja_env.filters["datahora"] = lambda d: d.strftime("%d/%m/%Y %H:%M") if d else ""
    app.jinja_env.filters["hora"] = lambda d: d.strftime("%H:%M") if d else ""

    # --- Proteção CSRF simples (token por sessão) ---
    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(32)
        return session["_csrf"]

    @app.before_request
    def verificar_csrf():
        if not app.config["CSRF_ENABLED"]:
            return
        if request.method == "POST":
            token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
            if not token or not secrets.compare_digest(token, session.get("_csrf", "")):
                abort(400, "Token de segurança inválido. Recarregue a página e tente novamente.")

    @app.context_processor
    def injetar():
        from .models import PERFIS
        return {"csrf_token": csrf_token, "PERFIS": PERFIS, "config": app.config}

    @app.after_request
    def cabecalhos_seguranca(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    with app.app_context():
        db.create_all()

    return app
