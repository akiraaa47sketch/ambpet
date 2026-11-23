from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import db
from ..audit import diff, registrar, snapshot
from ..models import Agendamento, Auditoria, Responsavel
from ..permissoes import requer_perfil
from ..utils import agora, so_digitos, validar_cep, validar_cpf, validar_telefone
from .main import buscar_responsaveis

bp = Blueprint("responsaveis", __name__, url_prefix="/responsaveis")

UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
       "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]


def ler_form(form, responsavel_id=None):
    d = {
        "nome": (form.get("nome") or "").strip(),
        "cpf": so_digitos(form.get("cpf")),
        "telefone": so_digitos(form.get("telefone")),
        "cep": so_digitos(form.get("cep")),
        "logradouro": (form.get("logradouro") or "").strip(),
        "numero": (form.get("numero") or "").strip(),
        "complemento": (form.get("complemento") or "").strip() or None,
        "bairro": (form.get("bairro") or "").strip(),
        "cidade": (form.get("cidade") or "").strip(),
        "uf": (form.get("uf") or "").strip().upper(),
        "ano_cadunico": (form.get("ano_cadunico") or "").strip(),
    }
    erros = {}
    if len(d["nome"]) < 3:
        erros["nome"] = "Informe o nome completo."
    if not validar_cpf(d["cpf"]):
        erros["cpf"] = "CPF inválido."
    else:
        existente = Responsavel.query.filter_by(cpf=d["cpf"]).first()
        if existente and existente.id != responsavel_id:
            erros["cpf"] = f"CPF já cadastrado para {existente.nome}."
    if not validar_telefone(d["telefone"]):
        erros["telefone"] = "Telefone inválido. Use (DD) 9XXXX-XXXX ou (DD) XXXX-XXXX."
    if not validar_cep(d["cep"]):
        erros["cep"] = "CEP inválido (8 dígitos)."
    for campo, rotulo in (("logradouro", "o logradouro"), ("numero", "o número"),
                          ("bairro", "o bairro"), ("cidade", "a cidade")):
        if not d[campo]:
            erros[campo] = f"Informe {rotulo}."
    if d["uf"] not in UFS:
        erros["uf"] = "Selecione a UF."
    try:
        ano = int(d["ano_cadunico"])
        if not 2000 <= ano <= agora().year:
            raise ValueError
        d["ano_cadunico"] = ano
    except ValueError:
        erros["ano_cadunico"] = f"Informe um ano válido (2000 a {agora().year})."
    return d, erros


@bp.route("/")
@requer_perfil("recepcao", "veterinaria")
def lista():
    q = request.args.get("q", "")
    if q:
        itens = buscar_responsaveis(q, limite=200)
    else:
        itens = Responsavel.query.order_by(Responsavel.criado_em.desc()).limit(50).all()
    return render_template("responsaveis/lista.html", itens=itens, q=q)


@bp.route("/novo", methods=["GET", "POST"])
@requer_perfil("recepcao")
def novo():
    dados, erros = {}, {}
    if request.method == "POST":
        dados, erros = ler_form(request.form)
        if not erros:
            r = Responsavel(**dados)
            db.session.add(r)
            db.session.flush()
            registrar("criar", "responsavel", r.id, snapshot(r, Responsavel.CAMPOS))
            db.session.commit()
            flash("Responsável cadastrado. Agora cadastre o(s) animal(is).", "ok")
            return redirect(url_for("animais.novo", responsavel_id=r.id))
        flash("Corrija os campos destacados.", "erro")
    return render_template("responsaveis/form.html", dados=dados, erros=erros, ufs=UFS, r=None)


@bp.route("/<int:rid>")
@requer_perfil("recepcao", "veterinaria")
def ver(rid):
    r = db.get_or_404(Responsavel, rid)
    agendamentos = (Agendamento.query.filter_by(responsavel_id=r.id)
                    .order_by(Agendamento.data_hora.desc()).limit(20).all())
    return render_template("responsaveis/ver.html", r=r, agendamentos=agendamentos)


@bp.route("/<int:rid>/editar", methods=["GET", "POST"])
@requer_perfil("recepcao")
def editar(rid):
    r = db.get_or_404(Responsavel, rid)
    erros = {}
    dados = snapshot(r, Responsavel.CAMPOS)
    if request.method == "POST":
        dados, erros = ler_form(request.form, responsavel_id=r.id)
        if not erros:
            antes = snapshot(r, Responsavel.CAMPOS)
            for k, v in dados.items():
                setattr(r, k, v)
            mudancas = diff(antes, snapshot(r, Responsavel.CAMPOS))
            if mudancas:
                registrar("editar", "responsavel", r.id, mudancas)
            db.session.commit()
            flash("Cadastro atualizado.", "ok")
            return redirect(url_for(".ver", rid=r.id))
        flash("Corrija os campos destacados.", "erro")
    return render_template("responsaveis/form.html", dados=dados, erros=erros, ufs=UFS, r=r)


@bp.route("/<int:rid>/historico")
@requer_perfil("recepcao", "veterinaria")
def historico(rid):
    r = db.get_or_404(Responsavel, rid)
    logs = (Auditoria.query.filter_by(entidade="responsavel", entidade_id=r.id)
            .filter(Auditoria.acao.in_(["criar", "editar"]))
            .order_by(Auditoria.criado_em.desc()).all())
    return render_template("historico_alteracoes.html", titulo=f"Responsável: {r.nome}",
                           voltar=url_for(".ver", rid=r.id), logs=logs)
