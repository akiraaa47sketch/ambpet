"""Módulo da Veterinária: anotações de consulta, adendos e receitas."""
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .. import db
from ..audit import registrar
from ..models import Adendo, Agendamento, Animal, Consulta, Receita, ReceitaItem
from ..permissoes import requer_perfil

bp = Blueprint("clinica", __name__)


def _dec(v):
    v = (v or "").strip().replace(",", ".")
    if not v:
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        return "invalido"


@bp.route("/animais/<int:aid>/consultas/nova", methods=["GET", "POST"])
@requer_perfil("veterinaria")
def nova_consulta(aid):
    a = db.get_or_404(Animal, aid)
    agid = request.values.get("agendamento_id", type=int)
    ag = db.session.get(Agendamento, agid) if agid else None
    if ag and ag.animal_id != a.id:
        abort(400)
    dados = {k: request.form.get(k, "") for k in ("motivo", "peso_kg", "temperatura", "anotacao")}
    if not dados["motivo"] and ag and ag.observacao:
        dados["motivo"] = ag.observacao[:200]
    erros = {}
    if request.method == "POST":
        peso, temp = _dec(dados["peso_kg"]), _dec(dados["temperatura"])
        if peso == "invalido" or (peso is not None and peso <= 0):
            erros["peso_kg"] = "Peso inválido."
        if temp == "invalido" or (temp is not None and not 30 <= temp <= 45):
            erros["temperatura"] = "Temperatura inválida (°C)."
        if len(dados["anotacao"].strip()) < 3:
            erros["anotacao"] = "Escreva a anotação da consulta."
        if not erros:
            c = Consulta(animal_id=a.id, veterinario_id=current_user.id,
                         agendamento_id=ag.id if ag else None,
                         motivo=dados["motivo"].strip() or None, peso_kg=peso,
                         temperatura=temp, anotacao=dados["anotacao"].strip())
            db.session.add(c)
            if peso is not None:
                a.peso_kg = peso
            if ag and ag.status == "agendado":
                ag.status = "realizado"
            db.session.flush()
            registrar("criar", "consulta", c.id, {"animal_id": a.id, "agendamento_id": c.agendamento_id})
            db.session.commit()
            flash("Anotação de consulta registrada.", "ok")
            if request.form.get("acao") == "receita":
                return redirect(url_for(".nova_receita", aid=a.id, consulta_id=c.id))
            return redirect(url_for("animais.ver", aid=a.id, _anchor="consultas"))
        flash("Corrija os campos destacados.", "erro")
    return render_template("clinica/consulta_form.html", a=a, ag=ag, dados=dados, erros=erros)


@bp.route("/consultas/<int:cid>/adendo", methods=["POST"])
@requer_perfil("veterinaria")
def adendo(cid):
    c = db.get_or_404(Consulta, cid)
    texto = (request.form.get("texto") or "").strip()
    if not texto:
        flash("O complemento não pode ser vazio.", "erro")
    else:
        ad = Adendo(consulta_id=c.id, autor_id=current_user.id, texto=texto)
        db.session.add(ad)
        db.session.flush()
        registrar("criar", "adendo", ad.id, {"consulta_id": c.id})
        db.session.commit()
        flash("Complemento adicionado à consulta.", "ok")
    return redirect(url_for("animais.ver", aid=c.animal_id, _anchor=f"consulta-{c.id}"))


@bp.route("/animais/<int:aid>/receitas/nova", methods=["GET", "POST"])
@requer_perfil("veterinaria")
def nova_receita(aid):
    a = db.get_or_404(Animal, aid)
    consulta_id = request.values.get("consulta_id", type=int)
    erros = {}
    itens = [{}]
    orientacoes = ""
    if request.method == "POST":
        orientacoes = (request.form.get("orientacoes") or "").strip()
        campos = ["medicamento", "concentracao", "quantidade", "via", "posologia", "duracao"]
        listas = {c: request.form.getlist(c) for c in campos}
        itens = []
        for i in range(len(listas["medicamento"])):
            item = {c: (listas[c][i] if i < len(listas[c]) else "").strip() for c in campos}
            if any(item.values()):
                itens.append(item)
        if not itens:
            erros["itens"] = "Inclua ao menos um medicamento."
            itens = [{}]
        for item in itens:
            if item and (not item.get("medicamento") or not item.get("posologia")):
                erros["itens"] = "Cada item precisa de medicamento e posologia."
        if not erros:
            if consulta_id:
                c = db.session.get(Consulta, consulta_id)
                if not c or c.animal_id != a.id:
                    consulta_id = None
            rec = Receita(animal_id=a.id, veterinario_id=current_user.id,
                          consulta_id=consulta_id, orientacoes=orientacoes or None)
            db.session.add(rec)
            db.session.flush()
            for item in itens:
                db.session.add(ReceitaItem(receita_id=rec.id,
                                           **{k: (v or None) for k, v in item.items()}))
            registrar("criar", "receita", rec.id, {"animal_id": a.id, "itens": itens})
            db.session.commit()
            flash("Receita emitida e registrada no perfil do animal.", "ok")
            return redirect(url_for(".imprimir_receita", rid=rec.id))
        flash("Corrija os campos destacados.", "erro")
    # sugestões de medicamentos já receitados (autocomplete)
    sugestoes = [m for (m,) in db.session.query(ReceitaItem.medicamento).distinct()
                 .order_by(ReceitaItem.medicamento).limit(500)]
    return render_template("clinica/receita_form.html", a=a, itens=itens, erros=erros,
                           orientacoes=orientacoes, consulta_id=consulta_id, sugestoes=sugestoes)


@bp.route("/receitas/<int:rid>")
@requer_perfil("veterinaria")
def imprimir_receita(rid):
    rec = db.get_or_404(Receita, rid)
    return render_template("clinica/receita_imprimir.html", rec=rec, a=rec.animal)
