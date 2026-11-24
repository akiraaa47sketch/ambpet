from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   url_for)

from .. import db
from ..audit import diff, registrar, snapshot
from ..crypto import chaveiro
from ..models import Agendamento, Auditoria, Responsavel
from ..permissoes import requer_perfil
from ..utils import agora, so_digitos, validar_cep, validar_cpf, validar_telefone
from .main import atualizar_indice_nome, buscar_responsaveis

bp = Blueprint("responsaveis", __name__, url_prefix="/tutores")

UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
       "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]


def ler_form(form, responsavel_id=None):
    d = {
        "nome": " ".join((form.get("nome") or "").split())[:150],
        "cpf": so_digitos(form.get("cpf")),
        "telefone": so_digitos(form.get("telefone")),
        "cep": so_digitos(form.get("cep")),
        "logradouro": (form.get("logradouro") or "").strip()[:150],
        "numero": (form.get("numero") or "").strip()[:20],
        "complemento": (form.get("complemento") or "").strip()[:80] or None,
        "bairro": (form.get("bairro") or "").strip()[:80],
        "cidade": (form.get("cidade") or "").strip()[:80],
        "uf": (form.get("uf") or "").strip().upper(),
        "ano_cadunico": (form.get("ano_cadunico") or "").strip(),
    }
    erros = {}
    if len(d["nome"]) < 3 or len(d["nome"].split()) < 2:
        erros["nome"] = "Informe nome e sobrenome."
    if not validar_cpf(d["cpf"]):
        erros["cpf"] = "CPF inválido."
    else:
        existente = Responsavel.query.filter_by(cpf_hash=chaveiro.hash(d["cpf"], "cpf")).first()
        if existente and existente.id != responsavel_id:
            erros["cpf"] = "Este CPF já está cadastrado."
            erros["_existente"] = existente.id
    if not validar_telefone(d["telefone"]):
        erros["telefone"] = "Telefone inválido. Use DDD + número."
    if not validar_cep(d["cep"]):
        erros["cep"] = "CEP inválido."
    for campo, rotulo in (("logradouro", "o logradouro"), ("numero", "o número"),
                          ("bairro", "o bairro"), ("cidade", "a cidade")):
        if not d[campo]:
            erros[campo] = f"Informe {rotulo}."
    if d["uf"] not in UFS:
        erros["uf"] = "Selecione a UF."
    try:
        if not 2000 <= int(d["ano_cadunico"]) <= agora().year:
            raise ValueError
    except ValueError:
        erros["ano_cadunico"] = f"Ano entre 2000 e {agora().year}."
    return d, erros


@bp.route("/", methods=["GET", "POST"])
@requer_perfil("recepcao", "veterinaria")
def lista():
    q = request.form.get("q", "") if request.method == "POST" else ""
    if q:
        itens = buscar_responsaveis(q, limite=100)
    else:
        itens = (Responsavel.query.filter(Responsavel.anonimizado_em.is_(None))
                 .order_by(Responsavel.criado_em.desc()).limit(25).all())
    return render_template("responsaveis/lista.html", itens=itens, q=q)


@bp.route("/novo", methods=["GET", "POST"])
@requer_perfil("recepcao")
def novo():
    dados, erros = {}, {}
    if request.method == "POST":
        dados, erros = ler_form(request.form)
        if request.form.get("aviso_privacidade") != "on":
            erros["aviso_privacidade"] = "Confirme que o tutor recebeu o aviso de privacidade."
        if not erros:
            r = Responsavel(**dados, aviso_privacidade_versao=current_app.config["AVISO_PRIVACIDADE_VERSAO"],
                            aviso_privacidade_em=agora())
            r.atualizar_indices()
            db.session.add(r)
            db.session.flush()
            atualizar_indice_nome(r)
            registrar("criar", "tutor", r.id, snapshot(r, Responsavel.CAMPOS))
            db.session.commit()
            flash("Tutor cadastrado. Agora cadastre o paciente.", "ok")
            return redirect(url_for("animais.novo", responsavel_id=r.id))
        flash("Revise os campos destacados.", "erro")
    return render_template("responsaveis/form.html", dados=dados, erros=erros, ufs=UFS, r=None)


def _obter(rid):
    r = db.get_or_404(Responsavel, rid)
    if r.anonimizado_em:
        abort(404)
    return r


@bp.route("/<int:rid>")
@requer_perfil("recepcao", "veterinaria")
def ver(rid):
    r = _obter(rid)
    registrar("visualizar", "tutor", r.id)  # registro de acesso (LGPD art. 37)
    db.session.commit()
    agendamentos = (Agendamento.query.filter_by(responsavel_id=r.id)
                    .order_by(Agendamento.data_hora.desc()).limit(15).all())
    return render_template("responsaveis/ver.html", r=r, agendamentos=agendamentos)


@bp.route("/<int:rid>/editar", methods=["GET", "POST"])
@requer_perfil("recepcao")
def editar(rid):
    r = _obter(rid)
    erros = {}
    dados = snapshot(r, Responsavel.CAMPOS)
    if request.method == "POST":
        dados, erros = ler_form(request.form, responsavel_id=r.id)
        if not erros:
            antes = snapshot(r, Responsavel.CAMPOS)
            for k, v in dados.items():
                setattr(r, k, v)
            r.atualizar_indices()
            mudancas = diff(antes, snapshot(r, Responsavel.CAMPOS))
            if "nome" in mudancas:
                atualizar_indice_nome(r)
            if mudancas:
                registrar("editar", "tutor", r.id, mudancas)
            db.session.commit()
            flash("Cadastro atualizado.", "ok")
            return redirect(url_for(".ver", rid=r.id))
        flash("Revise os campos destacados.", "erro")
    return render_template("responsaveis/form.html", dados=dados, erros=erros, ufs=UFS, r=r)


@bp.route("/<int:rid>/historico")
@requer_perfil("recepcao", "veterinaria")
def historico(rid):
    r = _obter(rid)
    logs = (Auditoria.query.filter_by(entidade="tutor", entidade_id=r.id)
            .filter(Auditoria.acao.in_(["criar", "editar"]))
            .order_by(Auditoria.id.desc()).all())
    return render_template("historico_alteracoes.html", titulo=r.nome, subtitulo="Tutor",
                           voltar=url_for(".ver", rid=r.id), logs=logs)
