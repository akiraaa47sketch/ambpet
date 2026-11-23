from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..models import Animal, Responsavel
from ..utils import so_digitos

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def inicio():
    return redirect(url_for("agenda.painel"))


def buscar_responsaveis(q, limite=50):
    q = (q or "").strip()
    if not q:
        return []
    dig = so_digitos(q)
    filtros = [Responsavel.nome.ilike(f"%{q}%")]
    if len(dig) >= 3:
        filtros += [Responsavel.cpf.like(f"%{dig}%"), Responsavel.telefone.like(f"%{dig}%")]
    # também encontra o responsável pelo nome do animal
    filtros.append(Responsavel.animais.any(Animal.nome.ilike(f"%{q}%")))
    return (Responsavel.query.filter(or_(*filtros))
            .order_by(Responsavel.nome).limit(limite).all())


@bp.route("/busca")
@login_required
def busca():
    q = request.args.get("q", "")
    return render_template("busca.html", q=q, resultados=buscar_responsaveis(q))


@bp.app_errorhandler(403)
def proibido(e):
    return render_template("erro.html", codigo=403,
                           mensagem="Seu perfil não tem acesso a esta página."), 403


@bp.app_errorhandler(404)
def nao_encontrado(e):
    return render_template("erro.html", codigo=404, mensagem="Página não encontrada."), 404


@bp.app_errorhandler(400)
def requisicao_invalida(e):
    return render_template("erro.html", codigo=400,
                           mensagem=getattr(e, "description", "Requisição inválida.")), 400
