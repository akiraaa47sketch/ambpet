from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .. import db
from ..audit import diff, registrar, snapshot
from ..models import Agendamento, Animal, Auditoria, Responsavel
from ..permissoes import requer_perfil
from ..utils import hoje

bp = Blueprint("animais", __name__, url_prefix="/animais")

ESPECIES = ["Canina", "Felina", "Outra"]


def _int(v, padrao=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return padrao


def _decimal(v):
    v = (v or "").strip().replace(",", ".")
    if not v:
        return None
    try:
        d = Decimal(v)
        return d if d >= 0 else None
    except InvalidOperation:
        return "invalido"


def ler_cadastro(form, animal=None):
    d = {
        "nome": (form.get("nome") or "").strip(),
        "sexo": form.get("sexo") or "",
        "especie": (form.get("especie") or "").strip(),
        "raca": (form.get("raca") or "").strip(),
        "idade_anos": _int(form.get("idade_anos"), 0),
        "idade_meses": _int(form.get("idade_meses"), 0),
        "castrado": form.get("castrado"),
        "responsavel_id": _int(form.get("responsavel_id")),
    }
    if d["especie"] == "Outra":
        d["especie"] = (form.get("especie_outra") or "").strip()
    erros = {}
    if not d["nome"]:
        erros["nome"] = "Informe o nome do animal."
    if d["sexo"] not in ("M", "F"):
        erros["sexo"] = "Selecione o sexo."
    if not d["especie"]:
        erros["especie"] = "Informe a espécie."
    if not d["raca"]:
        erros["raca"] = "Informe a raça (use SRD se sem raça definida)."
    if not (0 <= d["idade_anos"] <= 40) or not (0 <= d["idade_meses"] <= 11):
        erros["idade"] = "Idade inválida (anos 0–40, meses 0–11)."
    d["castrado"] = {"sim": True, "nao": False}.get(d["castrado"])
    if d["castrado"] is None:
        erros["castrado"] = "Informe se o animal é castrado."
    if not d["responsavel_id"] or not db.session.get(Responsavel, d["responsavel_id"]):
        erros["responsavel_id"] = "Selecione um responsável cadastrado."
    # a "data de referência" da idade só muda quando a idade é alterada
    if animal is None or (animal.idade_anos, animal.idade_meses) != (d["idade_anos"], d["idade_meses"]):
        d["idade_referencia"] = hoje()
    else:
        d["idade_referencia"] = animal.idade_referencia
    return d, erros


def ler_clinico(form):
    d = {
        "peso_kg": _decimal(form.get("peso_kg")),
        "pelagem": (form.get("pelagem") or "").strip() or None,
        "alergias": (form.get("alergias") or "").strip() or None,
        "condicoes_cronicas": (form.get("condicoes_cronicas") or "").strip() or None,
        "observacoes_clinicas": (form.get("observacoes_clinicas") or "").strip() or None,
        "obito": form.get("obito") == "on",
    }
    erros = {}
    if d["peso_kg"] == "invalido":
        erros["peso_kg"] = "Peso inválido."
    return d, erros


@bp.route("/novo", methods=["GET", "POST"])
@requer_perfil("recepcao")
def novo():
    responsavel = db.session.get(Responsavel, _int(request.values.get("responsavel_id"), 0))
    if not responsavel:
        flash("Selecione primeiro o responsável pelo animal.", "aviso")
        return redirect(url_for("responsaveis.lista"))
    dados, erros = {"responsavel_id": responsavel.id}, {}
    if request.method == "POST":
        dados, erros = ler_cadastro(request.form)
        if not erros:
            a = Animal(**dados)
            db.session.add(a)
            db.session.flush()
            registrar("criar", "animal", a.id, snapshot(a, Animal.CAMPOS_CADASTRO))
            db.session.commit()
            flash(f"Animal {a.nome} cadastrado.", "ok")
            if request.form.get("acao") == "outro":
                return redirect(url_for(".novo", responsavel_id=responsavel.id))
            return redirect(url_for("responsaveis.ver", rid=responsavel.id))
        flash("Corrija os campos destacados.", "erro")
    return render_template("animais/form.html", dados=dados, erros=erros, a=None,
                           responsavel=responsavel, especies=ESPECIES, clinico=False)


@bp.route("/<int:aid>")
@requer_perfil("recepcao", "veterinaria")
def ver(aid):
    a = db.get_or_404(Animal, aid)
    agendamentos = (Agendamento.query.filter_by(animal_id=a.id)
                    .order_by(Agendamento.data_hora.desc()).limit(20).all())
    pode_clinico = current_user.tem_perfil("veterinaria")
    medicacoes = []
    if pode_clinico:
        for rec in a.receitas:
            for item in rec.itens:
                medicacoes.append((rec, item))
    return render_template("animais/ver.html", a=a, agendamentos=agendamentos,
                           pode_clinico=pode_clinico, medicacoes=medicacoes)


@bp.route("/<int:aid>/editar", methods=["GET", "POST"])
@requer_perfil("recepcao", "veterinaria")
def editar(aid):
    a = db.get_or_404(Animal, aid)
    clinico = current_user.tem_perfil("veterinaria")
    campos = Animal.CAMPOS_CADASTRO + (Animal.CAMPOS_CLINICOS if clinico else [])
    dados, erros = snapshot(a, campos), {}
    if request.method == "POST":
        dados, erros = ler_cadastro(request.form, animal=a)
        if clinico:
            dc, ec = ler_clinico(request.form)
            dados.update(dc)
            erros.update(ec)
        if not erros:
            antes = snapshot(a, campos)
            for k, v in dados.items():
                setattr(a, k, v)
            mudancas = diff(antes, snapshot(a, campos))
            mudancas.pop("idade_referencia", None)
            if mudancas:
                registrar("editar", "animal", a.id, mudancas)
            db.session.commit()
            flash("Ficha do animal atualizada.", "ok")
            return redirect(url_for(".ver", aid=a.id))
        flash("Corrija os campos destacados.", "erro")
    return render_template("animais/form.html", dados=dados, erros=erros, a=a,
                           responsavel=a.responsavel, especies=ESPECIES, clinico=clinico)


@bp.route("/<int:aid>/historico")
@requer_perfil("recepcao", "veterinaria")
def historico(aid):
    a = db.get_or_404(Animal, aid)
    logs = (Auditoria.query.filter_by(entidade="animal", entidade_id=a.id)
            .filter(Auditoria.acao.in_(["criar", "editar"]))
            .order_by(Auditoria.criado_em.desc()).all())
    return render_template("historico_alteracoes.html", titulo=f"Animal: {a.nome}",
                           voltar=url_for(".ver", aid=a.id), logs=logs)
