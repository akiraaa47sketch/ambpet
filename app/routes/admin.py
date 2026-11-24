import secrets
import string

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .. import db
from ..audit import registrar, verificar_cadeia
from ..models import PERFIS, Auditoria, Usuario
from ..permissoes import requer_perfil
from .main import buscar_responsaveis

bp = Blueprint("admin", __name__, url_prefix="/admin")


def senha_temporaria():
    alfabeto = string.ascii_letters + string.digits
    while True:
        s = "".join(secrets.choice(alfabeto) for _ in range(14))
        if any(c.islower() for c in s) and any(c.isupper() for c in s) and any(c.isdigit() for c in s):
            return s


@bp.route("/usuarios")
@requer_perfil("admin")
def usuarios():
    from ..utils import agora
    return render_template("admin/usuarios.html", usuarios=Usuario.query.order_by(Usuario.nome).all(),
                           now=agora())


@bp.route("/usuarios/novo", methods=["GET", "POST"])
@bp.route("/usuarios/<int:uid>", methods=["GET", "POST"])
@requer_perfil("admin")
def usuario_form(uid=None):
    u = db.get_or_404(Usuario, uid) if uid else None
    erros = {}
    if request.method == "POST":
        nome = " ".join((request.form.get("nome") or "").split())[:120]
        login_ = (request.form.get("login") or "").strip().lower()[:60]
        perfil = request.form.get("perfil")
        crmv = (request.form.get("crmv") or "").strip()[:30] or None
        ativo = request.form.get("ativo") == "on" if u else True
        if not nome:
            erros["nome"] = "Informe o nome."
        if not login_ or not all(c.isalnum() or c in "._-" for c in login_):
            erros["login"] = "Use letras, números, ponto, hífen ou sublinhado."
        else:
            outro = Usuario.query.filter_by(login=login_).first()
            if outro and (not u or outro.id != u.id):
                erros["login"] = "Login já em uso."
        if perfil not in PERFIS:
            erros["perfil"] = "Selecione o perfil."
        if perfil == "veterinaria" and not crmv:
            erros["crmv"] = "Informe o CRMV (sai na receita)."
        if u and u.id == current_user.id and (not ativo or perfil != "admin"):
            erros["perfil"] = "Você não pode remover o próprio acesso de administrador."
        if not erros:
            temp = None
            if u is None:
                u = Usuario(nome=nome, login=login_, perfil=perfil)
                temp = senha_temporaria()
                u.definir_senha(temp)
                u.trocar_senha = True
                db.session.add(u)
            mudou_acesso = u.perfil != perfil or u.ativo != ativo
            u.nome, u.login, u.perfil, u.crmv, u.ativo = nome, login_, perfil, crmv, ativo
            if mudou_acesso and uid:
                u.sessao_versao += 1  # encerra sessões abertas
            db.session.flush()
            registrar("criar" if temp else "editar", "usuario", u.id,
                      {"login": login_, "perfil": perfil, "ativo": ativo})
            db.session.commit()
            if temp:
                return render_template("admin/senha_temporaria.html", u=u, senha=temp)
            flash("Usuário salvo.", "ok")
            return redirect(url_for(".usuarios"))
        flash("Revise os campos destacados.", "erro")
    return render_template("admin/usuario_form.html", u=u, erros=erros, form=request.form)


@bp.route("/usuarios/<int:uid>/redefinir", methods=["POST"])
@requer_perfil("admin")
def redefinir(uid):
    u = db.get_or_404(Usuario, uid)
    o_que = request.form.get("o_que")
    if o_que == "senha":
        temp = senha_temporaria()
        u.definir_senha(temp)
        u.trocar_senha = True
        u.falhas_login, u.bloqueado_ate = 0, None
        registrar("redefinir_senha", "usuario", u.id)
        db.session.commit()
        return render_template("admin/senha_temporaria.html", u=u, senha=temp)
    if o_que == "2fa":
        u.totp_ativo, u.totp_segredo, u.totp_ultimo_passo = False, None, None
        u.sessao_versao += 1
        registrar("redefinir_2fa", "usuario", u.id)
        db.session.commit()
        flash(f"Verificação em duas etapas de {u.nome} redefinida. Será configurada no próximo acesso.", "ok")
    if o_que == "desbloquear":
        u.falhas_login, u.bloqueado_ate = 0, None
        registrar("desbloquear", "usuario", u.id)
        db.session.commit()
        flash(f"{u.nome} desbloqueado.", "ok")
    return redirect(url_for(".usuario_form", uid=u.id))


@bp.route("/auditoria")
@requer_perfil("admin")
def auditoria():
    pagina = request.args.get("pagina", 1, type=int)
    entidade = request.args.get("entidade", "")
    q = db.select(Auditoria)
    if entidade:
        q = q.filter_by(entidade=entidade)
    pag = db.paginate(q.order_by(Auditoria.id.desc()), page=pagina, per_page=50)
    entidades = [e for (e,) in db.session.query(Auditoria.entidade).distinct().order_by(Auditoria.entidade)]
    integridade = verificar_cadeia() if request.args.get("verificar") else None
    return render_template("admin/auditoria.html", pag=pag, entidade=entidade, entidades=entidades,
                           integridade=integridade)


@bp.route("/lgpd", methods=["GET", "POST"])
@requer_perfil("admin")
def lgpd():
    q = request.form.get("q", "") if request.method == "POST" else ""
    return render_template("admin/lgpd.html", q=q, resultados=buscar_responsaveis(q) if q else [])
