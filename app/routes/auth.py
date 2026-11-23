import time

from flask import (Blueprint, current_app, flash, redirect, render_template, request, session,
                   url_for)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from .. import db
from ..audit import registrar
from ..models import Usuario
from ..seguranca import (conta_bloqueada, novo_segredo_totp, qr_svg_data_uri, registrar_falha,
                         registrar_sucesso, uri_totp, validar_senha, verificar_totp)

bp = Blueprint("auth", __name__)

_HASH_FALSO = generate_password_hash("senha-inexistente-para-tempo-constante", method="scrypt")
MSG_FALHA = "Usuário ou senha inválidos."


def _destino():
    d = session.pop("_destino", None)
    return d if d and d.startswith("/") and not d.startswith("//") else url_for("main.inicio")


def _entrar(u):
    destino = session.get("_destino")
    session.clear()
    if destino:
        session["_destino"] = destino
    login_user(u)
    session.permanent = True
    session["_ultimo"] = int(time.time())
    registrar_sucesso(u)
    registrar("login", "usuario", u.id, usuario_id=u.id)
    db.session.commit()


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.inicio"))
    if request.args.get("next"):
        session["_destino"] = request.args["next"]
    if request.method == "POST":
        login_ = (request.form.get("login") or "").strip().lower()
        senha = request.form.get("senha") or ""
        u = Usuario.query.filter_by(login=login_).first() if login_ else None
        if not u:
            check_password_hash(_HASH_FALSO, senha)  # tempo constante
            registrar("login_falhou", "usuario", None)
            db.session.commit()
            flash(MSG_FALHA, "erro")
        elif not u.ativo or conta_bloqueada(u):
            check_password_hash(_HASH_FALSO, senha)
            registrar("login_bloqueado", "usuario", u.id, usuario_id=u.id)
            db.session.commit()
            flash("Acesso indisponível. Se errou a senha várias vezes, aguarde "
                  f"{current_app.config['LOGIN_BLOQUEIO_MIN']} minutos ou procure o administrador.", "erro")
        elif not u.verificar_senha(senha):
            bloqueou = registrar_falha(u)
            registrar("login_falhou", "usuario", u.id, {"bloqueio": bloqueou}, usuario_id=u.id)
            db.session.commit()
            flash(MSG_FALHA, "erro")
        elif u.totp_ativo:
            session["_2fa_uid"] = u.id
            session["_2fa_exp"] = int(time.time()) + 300
            return redirect(url_for(".verificacao"))
        else:
            _entrar(u)
            return redirect(_destino())
    return render_template("auth/login.html")


@bp.route("/login/verificacao", methods=["GET", "POST"])
def verificacao():
    uid = session.get("_2fa_uid")
    if not uid or session.get("_2fa_exp", 0) < time.time():
        session.pop("_2fa_uid", None)
        flash("Tempo esgotado. Entre novamente.", "aviso")
        return redirect(url_for(".login"))
    u = db.session.get(Usuario, uid)
    if not u or not u.ativo or conta_bloqueada(u):
        session.clear()
        return redirect(url_for(".login"))
    if request.method == "POST":
        if verificar_totp(u, request.form.get("codigo")):
            _entrar(u)
            return redirect(_destino())
        bloqueou = registrar_falha(u)
        registrar("2fa_falhou", "usuario", u.id, {"bloqueio": bloqueou}, usuario_id=u.id)
        db.session.commit()
        if bloqueou:
            session.clear()
            flash("Muitas tentativas. Acesso bloqueado temporariamente.", "erro")
            return redirect(url_for(".login"))
        flash("Código inválido.", "erro")
    return render_template("auth/verificacao.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    registrar("logout", "usuario", current_user.id)
    db.session.commit()
    logout_user()
    session.clear()
    flash("Você saiu do sistema.", "ok")
    return redirect(url_for(".login"))


@bp.route("/conta/senha", methods=["GET", "POST"])
@login_required
def trocar_senha():
    if request.method == "POST":
        atual = request.form.get("atual") or ""
        nova = request.form.get("nova") or ""
        erro = None
        if not current_user.verificar_senha(atual):
            erro = "Senha atual incorreta."
        elif nova != request.form.get("confirmacao"):
            erro = "A confirmação não confere."
        elif nova == atual:
            erro = "A nova senha deve ser diferente da atual."
        else:
            erro = validar_senha(nova, current_user.login, current_user.nome)
        if erro:
            flash(erro, "erro")
        else:
            u = current_user._get_current_object()
            u.definir_senha(nova)
            u.trocar_senha = False
            registrar("alterar_senha", "usuario", u.id)
            db.session.commit()
            login_user(u)  # renova a sessão com a nova versão
            session["_ultimo"] = int(time.time())
            flash("Senha alterada. Outras sessões abertas foram encerradas.", "ok")
            return redirect(url_for("main.inicio"))
    return render_template("auth/trocar_senha.html", obrigatoria=current_user.trocar_senha)


@bp.route("/conta/2fa", methods=["GET", "POST"])
@login_required
def configurar_2fa():
    u = current_user._get_current_object()
    if request.method == "POST":
        if request.form.get("acao") == "desativar":
            if current_app.config["EXIGIR_2FA"]:
                flash("A verificação em duas etapas é obrigatória nesta clínica.", "erro")
            elif u.verificar_senha(request.form.get("senha") or ""):
                u.totp_ativo, u.totp_segredo, u.totp_ultimo_passo = False, None, None
                u.sessao_versao += 1
                registrar("2fa_desativado", "usuario", u.id)
                db.session.commit()
                login_user(u)
                flash("Verificação em duas etapas desativada.", "ok")
            else:
                flash("Senha incorreta.", "erro")
            return redirect(url_for(".configurar_2fa"))
        if verificar_totp(u, request.form.get("codigo")):
            u.totp_ativo = True
            u.sessao_versao += 1
            registrar("2fa_ativado", "usuario", u.id)
            db.session.commit()
            login_user(u)
            session["_ultimo"] = int(time.time())
            flash("Verificação em duas etapas ativada.", "ok")
            return redirect(url_for("main.inicio"))
        flash("Código inválido. Confira o horário do celular e tente novamente.", "erro")
    if not u.totp_ativo and not u.totp_segredo:
        u.totp_segredo = novo_segredo_totp()
        db.session.commit()
    qr = None if u.totp_ativo else qr_svg_data_uri(uri_totp(u, u.totp_segredo))
    return render_template("auth/2fa.html", qr=qr,
                           segredo=None if u.totp_ativo else u.totp_segredo,
                           obrigatorio=current_app.config["EXIGIR_2FA"])
