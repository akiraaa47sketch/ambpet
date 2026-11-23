from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .. import db
from ..audit import registrar
from ..models import Usuario

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.inicio"))
    if request.method == "POST":
        login_ = (request.form.get("login") or "").strip().lower()
        senha = request.form.get("senha") or ""
        u = Usuario.query.filter_by(login=login_).first()
        if u and u.ativo and u.verificar_senha(senha):
            session.clear()
            login_user(u)
            session.permanent = True
            registrar("login", "usuario", u.id)
            db.session.commit()
            destino = request.args.get("next")
            if not destino or not destino.startswith("/") or destino.startswith("//"):
                destino = url_for("main.inicio")
            return redirect(destino)
        flash("Usuário ou senha inválidos.", "erro")
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    flash("Sessão encerrada.", "ok")
    return redirect(url_for("auth.login"))


@bp.route("/minha-senha", methods=["GET", "POST"])
@login_required
def minha_senha():
    if request.method == "POST":
        atual = request.form.get("atual") or ""
        nova = request.form.get("nova") or ""
        conf = request.form.get("confirmacao") or ""
        if not current_user.verificar_senha(atual):
            flash("Senha atual incorreta.", "erro")
        elif len(nova) < 8:
            flash("A nova senha deve ter pelo menos 8 caracteres.", "erro")
        elif nova != conf:
            flash("A confirmação não confere com a nova senha.", "erro")
        else:
            current_user.definir_senha(nova)
            registrar("alterar_senha", "usuario", current_user.id)
            db.session.commit()
            flash("Senha alterada com sucesso.", "ok")
            return redirect(url_for("main.inicio"))
    return render_template("auth/minha_senha.html")
