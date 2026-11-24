from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from .. import db
from ..crypto import chaveiro, normalizar
from ..models import Animal, IndiceBusca, Responsavel
from ..utils import so_digitos

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def inicio():
    return redirect(url_for("agenda.dia"))


def atualizar_indice_nome(tutor):
    IndiceBusca.query.filter_by(tutor_id=tutor.id).delete()
    for t in chaveiro.tokens_nome(tutor.nome, "nome"):
        db.session.add(IndiceBusca(tutor_id=tutor.id, token=t))


def buscar_responsaveis(q, limite=50):
    """Busca por início das palavras do nome do tutor, CPF ou telefone completos, ou nome do pet."""
    q = (q or "").strip()
    if len(q) < 2:
        return []
    ids = set()
    dig = so_digitos(q)
    if len(dig) == 11:
        ids |= {i for (i,) in db.session.query(Responsavel.id).filter(
            (Responsavel.cpf_hash == chaveiro.hash(dig, "cpf")) |
            (Responsavel.telefone_hash == chaveiro.hash(dig, "telefone")))}
    elif len(dig) == 10:
        ids |= {i for (i,) in db.session.query(Responsavel.id).filter(
            Responsavel.telefone_hash == chaveiro.hash(dig, "telefone"))}
    palavras = [p for p in normalizar(q).split() if len(p) >= 2 and not p.isdigit()]
    if palavras:
        tokens = [chaveiro.hash(p, "nome")[:32] for p in palavras]
        sub = (db.session.query(IndiceBusca.tutor_id)
               .filter(IndiceBusca.token.in_(tokens))
               .group_by(IndiceBusca.tutor_id)
               .having(func.count(func.distinct(IndiceBusca.token)) == len(set(tokens))))
        ids |= {i for (i,) in sub.limit(limite * 2)}
        termo = q.replace("%", "").replace("_", "")
        ids |= {i for (i,) in db.session.query(Animal.responsavel_id)
                .filter(Animal.nome.ilike(f"%{termo}%")).limit(limite * 2)}
    if not ids:
        return []
    res = (Responsavel.query.filter(Responsavel.id.in_(ids), Responsavel.anonimizado_em.is_(None))
           .limit(limite).all())
    return sorted(res, key=lambda r: normalizar(r.nome))


@bp.route("/busca", methods=["GET", "POST"])
@login_required
def busca():
    # POST: o termo (pode ser CPF/telefone) não fica na URL, no histórico nem em logs
    q = request.form.get("q", "") if request.method == "POST" else ""
    return render_template("busca.html", q=q, resultados=buscar_responsaveis(q) if q else [])


def _erro(codigo, titulo, mensagem):
    return render_template("erro.html", codigo=codigo, titulo=titulo, mensagem=mensagem), codigo


@bp.app_errorhandler(403)
def proibido(e):
    return _erro(403, "Acesso não permitido", "Seu perfil não tem acesso a esta página.")


@bp.app_errorhandler(404)
def nao_encontrado(e):
    return _erro(404, "Página não encontrada", "O endereço acessado não existe ou foi removido.")


@bp.app_errorhandler(400)
def requisicao_invalida(e):
    return _erro(400, "Não foi possível concluir", getattr(e, "description", "Requisição inválida."))


@bp.app_errorhandler(413)
def grande_demais(e):
    return _erro(413, "Envio muito grande", "O conteúdo enviado excede o limite permitido.")


@bp.app_errorhandler(500)
def erro_interno(e):
    db.session.rollback()
    return _erro(500, "Erro inesperado", "Tente novamente. Se persistir, avise o administrador.")
