from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .. import db
from ..audit import registrar
from ..models import PERFIS, Auditoria, Usuario
from ..permissoes import requer_perfil

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/usuarios")
@requer_perfil("admin")
def usuarios():
    return render_template("admin/usuarios.html",
                           usuarios=Usuario.query.order_by(Usuario.nome).all())


@bp.route("/usuarios/novo", methods=["GET", "POST"])
@bp.route("/usuarios/<int:uid>", methods=["GET", "POST"])
@requer_perfil("admin")
def usuario_form(uid=None):
    u = db.get_or_404(Usuario, uid) if uid else None
    erros = {}
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        login_ = (request.form.get("login") or "").strip().lower()
        perfil = request.form.get("perfil")
        crmv = (request.form.get("crmv") or "").strip() or None
        senha = request.form.get("senha") or ""
        ativo = request.form.get("ativo") == "on"
        if not nome:
            erros["nome"] = "Informe o nome."
        if not login_ or " " in login_:
            erros["login"] = "Informe um login sem espaços."
        else:
            outro = Usuario.query.filter_by(login=login_).first()
            if outro and (not u or outro.id != u.id):
                erros["login"] = "Login já em uso."
        if perfil not in PERFIS:
            erros["perfil"] = "Selecione o perfil."
        if (not u or senha) and len(senha) < 8:
            erros["senha"] = "A senha deve ter pelo menos 8 caracteres."
        if u and u.id == current_user.id and (not ativo or perfil != "admin"):
            erros["perfil"] = "Você não pode remover o próprio acesso de administrador."
        if not erros:
            novo = u is None
            if novo:
                u = Usuario(nome=nome, login=login_, perfil=perfil)
                db.session.add(u)
            u.nome, u.login, u.perfil, u.crmv, u.ativo = nome, login_, perfil, crmv, ativo
            if senha:
                u.definir_senha(senha)
            db.session.flush()
            registrar("criar" if novo else "editar", "usuario", u.id,
                      {"login": login_, "perfil": perfil, "ativo": ativo,
                       "senha_alterada": bool(senha)})
            db.session.commit()
            flash("Usuário salvo.", "ok")
            return redirect(url_for(".usuarios"))
        flash("Corrija os campos destacados.", "erro")
    return render_template("admin/usuario_form.html", u=u, erros=erros, form=request.form)


@bp.route("/auditoria")
@requer_perfil("admin")
def auditoria():
    pagina = request.args.get("pagina", 1, type=int)
    entidade = request.args.get("entidade", "")
    q = db.select(Auditoria)
    if entidade:
        q = q.filter_by(entidade=entidade)
    pag = db.paginate(q.order_by(Auditoria.criado_em.desc(), Auditoria.id.desc()),
                      page=pagina, per_page=50)
    entidades = [e for (e,) in db.session.query(Auditoria.entidade).distinct().order_by(Auditoria.entidade)]
    return render_template("admin/auditoria.html", pag=pag, entidade=entidade, entidades=entidades)
