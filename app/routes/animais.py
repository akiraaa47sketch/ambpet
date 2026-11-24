from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .. import db
from ..audit import diff, registrar, snapshot
from ..models import Agendamento, Animal, Auditoria, Responsavel
from ..permissoes import requer_perfil
from ..utils import hoje

bp = Blueprint("animais", __name__, url_prefix="/pacientes")

ESPECIES = ["Canina", "Felina", "Outra"]


def _int(v, padrao=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return padrao


def decimal_ou_erro(v, minimo=None, maximo=None):
    v = (v or "").strip().replace(",", ".")
    if not v:
        return None, False
    try:
        d = Decimal(v)
    except InvalidOperation:
        return None, True
    if (minimo is not None and d < minimo) or (maximo is not None and d > maximo):
        return None, True
    return d, False


def ler_cadastro(form, animal=None):
    d = {
        "nome": " ".join((form.get("nome") or "").split())[:100],
        "sexo": form.get("sexo") or "",
        "especie": (form.get("especie") or "").strip(),
        "raca": (form.get("raca") or "").strip()[:80],
        "idade_anos": _int(form.get("idade_anos"), 0),
        "idade_meses": _int(form.get("idade_meses"), 0),
        "castrado": {"sim": True, "nao": False}.get(form.get("castrado")),
    }
    if d["especie"] == "Outra":
        d["especie"] = (form.get("especie_outra") or "").strip()[:40]
    erros = {}
    if not d["nome"]:
        erros["nome"] = "Informe o nome do paciente."
    if d["sexo"] not in ("M", "F"):
        erros["sexo"] = "Selecione o sexo."
    if not d["especie"]:
        erros["especie"] = "Informe a espécie."
    if not d["raca"]:
        erros["raca"] = "Informe a raça (SRD se sem raça definida)."
    if not (0 <= d["idade_anos"] <= 40) or not (0 <= d["idade_meses"] <= 11):
        erros["idade"] = "Idade inválida."
    if d["castrado"] is None:
        erros["castrado"] = "Informe se é castrado."
    if animal is None or (animal.idade_anos, animal.idade_meses) != (d["idade_anos"], d["idade_meses"]):
        d["idade_referencia"] = hoje()
    else:
        d["idade_referencia"] = animal.idade_referencia
    return d, erros


def ler_clinico(form):
    peso, erro_peso = decimal_ou_erro(form.get("peso_kg"), Decimal("0.01"), Decimal("999"))
    d = {
        "peso_kg": peso,
        "pelagem": (form.get("pelagem") or "").strip()[:80] or None,
        "alergias": (form.get("alergias") or "").strip() or None,
        "condicoes_cronicas": (form.get("condicoes_cronicas") or "").strip() or None,
        "observacoes_clinicas": (form.get("observacoes_clinicas") or "").strip() or None,
        "obito": form.get("obito") == "on",
    }
    return d, ({"peso_kg": "Peso inválido."} if erro_peso else {})


def _obter(aid):
    a = db.get_or_404(Animal, aid)
    if a.responsavel.anonimizado_em:
        abort(404)
    return a


@bp.route("/novo", methods=["GET", "POST"])
@requer_perfil("recepcao")
def novo():
    responsavel = db.session.get(Responsavel, _int(request.values.get("responsavel_id"), 0))
    if not responsavel or responsavel.anonimizado_em:
        flash("Selecione primeiro o tutor do paciente.", "aviso")
        return redirect(url_for("responsaveis.lista"))
    dados, erros = {}, {}
    if request.method == "POST":
        dados, erros = ler_cadastro(request.form)
        if not erros:
            a = Animal(**dados, responsavel_id=responsavel.id)
            db.session.add(a)
            db.session.flush()
            registrar("criar", "paciente", a.id, snapshot(a, Animal.CAMPOS_CADASTRO))
            db.session.commit()
            flash(f"Paciente {a.nome} cadastrado.", "ok")
            if request.form.get("acao") == "outro":
                return redirect(url_for(".novo", responsavel_id=responsavel.id))
            if request.form.get("acao") == "agendar":
                return redirect(url_for("agenda.novo", responsavel_id=responsavel.id, animal_id=a.id))
            return redirect(url_for("responsaveis.ver", rid=responsavel.id))
        flash("Revise os campos destacados.", "erro")
    return render_template("animais/form.html", dados=dados, erros=erros, a=None,
                           responsavel=responsavel, especies=ESPECIES, clinico=False)


@bp.route("/<int:aid>")
@requer_perfil("recepcao", "veterinaria")
def ver(aid):
    a = _obter(aid)
    clinico = current_user.tem_perfil("veterinaria")
    registrar("visualizar_prontuario" if clinico else "visualizar", "paciente", a.id)
    db.session.commit()
    agendamentos = (Agendamento.query.filter_by(animal_id=a.id)
                    .order_by(Agendamento.data_hora.desc()).limit(20).all())
    linha, medicacoes, pesos = [], [], []
    if clinico:
        for c in a.consultas:
            linha.append(("atendimento", c.data_hora, c))
            if c.peso_kg is not None:
                pesos.append((c.data_hora, c.peso_kg))
        for rec in a.receitas:
            if rec.consulta_id is None:
                linha.append(("receita", rec.emitida_em, rec))
            for item in rec.itens:
                medicacoes.append((rec, item))
        linha.sort(key=lambda x: x[1], reverse=True)
    return render_template("animais/ver.html", a=a, agendamentos=agendamentos, clinico=clinico,
                           linha=linha, medicacoes=medicacoes, pesos=pesos)


@bp.route("/<int:aid>/editar", methods=["GET", "POST"])
@requer_perfil("recepcao", "veterinaria")
def editar(aid):
    a = _obter(aid)
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
                registrar("editar", "paciente", a.id, mudancas)
            db.session.commit()
            flash("Ficha atualizada.", "ok")
            return redirect(url_for(".ver", aid=a.id))
        flash("Revise os campos destacados.", "erro")
    return render_template("animais/form.html", dados=dados, erros=erros, a=a,
                           responsavel=a.responsavel, especies=ESPECIES, clinico=clinico)


@bp.route("/<int:aid>/historico")
@requer_perfil("recepcao", "veterinaria")
def historico(aid):
    a = _obter(aid)
    logs = (Auditoria.query.filter_by(entidade="paciente", entidade_id=a.id)
            .filter(Auditoria.acao.in_(["criar", "editar"]))
            .order_by(Auditoria.id.desc()).all())
    if not current_user.tem_perfil("veterinaria"):
        # recepção não vê alterações de campos clínicos
        for log in logs:
            log.filtrado = {k: v for k, v in log.detalhes_dict.items() if k not in Animal.CAMPOS_CLINICOS}
    return render_template("historico_alteracoes.html", titulo=a.nome, subtitulo="Paciente",
                           voltar=url_for(".ver", aid=a.id), logs=logs)
