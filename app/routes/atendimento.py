"""Módulo da Veterinária: atendimento (prontuário SOAP), complementos e receitas."""
from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .. import db
from ..audit import registrar
from ..models import (TIPOS_AGENDAMENTO, TIPOS_RECEITA, Adendo, Agendamento, Animal, Consulta,
                      Receita, ReceitaItem)
from ..permissoes import requer_perfil
from .animais import decimal_ou_erro

bp = Blueprint("atendimento", __name__)

MUCOSAS = ["Normocoradas", "Hipocoradas", "Hipercoradas", "Ictéricas", "Cianóticas", "Pálidas"]
HIDRATACAO = ["Normal", "Desidratação leve (até 5%)", "Desidratação moderada (6–8%)",
              "Desidratação grave (> 8%)"]
SOAP = ["queixa", "anamnese", "exame_fisico", "diagnostico", "conduta"]


def _animal(aid):
    a = db.get_or_404(Animal, aid)
    if a.responsavel.anonimizado_em:
        abort(404)
    return a


@bp.route("/agenda/<int:agid>/iniciar", methods=["POST"])
@requer_perfil("veterinaria")
def iniciar(agid):
    ag = db.get_or_404(Agendamento, agid)
    if ag.status in ("agendado", "confirmado", "aguardando"):
        registrar("status", "agendamento", ag.id, {"status": {"de": ag.status, "para": "em_atendimento"}})
        ag.status = "em_atendimento"
        db.session.commit()
    elif ag.status != "em_atendimento":
        flash("Este agendamento não pode ser iniciado.", "erro")
        return redirect(url_for("agenda.dia", data=ag.data_hora.date().isoformat()))
    return redirect(url_for(".novo", aid=ag.animal_id, agendamento_id=ag.id))


@bp.route("/pacientes/<int:aid>/atendimento", methods=["GET", "POST"])
@requer_perfil("veterinaria")
def novo(aid):
    a = _animal(aid)
    agid = request.values.get("agendamento_id", type=int)
    ag = db.session.get(Agendamento, agid) if agid else None
    if ag and ag.animal_id != a.id:
        abort(400)
    campos = SOAP + ["tipo", "peso_kg", "temperatura", "freq_cardiaca", "freq_respiratoria",
                     "mucosas", "hidratacao", "tpc"]
    dados = {k: request.form.get(k, "") for k in campos}
    if request.method == "GET":
        dados["tipo"] = ag.tipo if ag else "Consulta"
        if ag and ag.observacao:
            dados["queixa"] = ag.observacao
    erros = {}
    if request.method == "POST":
        peso, e1 = decimal_ou_erro(dados["peso_kg"], Decimal("0.01"), Decimal("999"))
        temp, e2 = decimal_ou_erro(dados["temperatura"], Decimal("30"), Decimal("45"))
        if e1:
            erros["peso_kg"] = "Peso inválido."
        if e2:
            erros["temperatura"] = "Entre 30 e 45 °C."
        fc = request.form.get("freq_cardiaca", type=int)
        fr = request.form.get("freq_respiratoria", type=int)
        if dados["freq_cardiaca"] and not (fc and 10 <= fc <= 400):
            erros["freq_cardiaca"] = "Valor inválido."
        if dados["freq_respiratoria"] and not (fr and 2 <= fr <= 200):
            erros["freq_respiratoria"] = "Valor inválido."
        if dados["tipo"] not in TIPOS_AGENDAMENTO:
            dados["tipo"] = "Consulta"
        if not any(dados[k].strip() for k in SOAP):
            erros["soap"] = "Preencha ao menos um campo do prontuário."
        if not erros:
            c = Consulta(animal_id=a.id, veterinario_id=current_user.id,
                         agendamento_id=ag.id if ag else None, tipo=dados["tipo"],
                         peso_kg=peso, temperatura=temp, freq_cardiaca=fc, freq_respiratoria=fr,
                         mucosas=dados["mucosas"] if dados["mucosas"] in MUCOSAS else None,
                         hidratacao=dados["hidratacao"] if dados["hidratacao"] in HIDRATACAO else None,
                         tpc=dados["tpc"].strip()[:10] or None,
                         **{k: dados[k].strip() or None for k in SOAP})
            db.session.add(c)
            if peso is not None:
                a.peso_kg = peso
            if ag and ag.status in ("agendado", "confirmado", "aguardando", "em_atendimento"):
                registrar("status", "agendamento", ag.id, {"status": {"de": ag.status, "para": "finalizado"}})
                ag.status = "finalizado"
            db.session.flush()
            registrar("criar", "atendimento", c.id, {"paciente_id": a.id, "agendamento_id": c.agendamento_id})
            db.session.commit()
            flash("Atendimento registrado no prontuário.", "ok")
            if request.form.get("acao") == "receita":
                return redirect(url_for(".nova_receita", aid=a.id, consulta_id=c.id))
            return redirect(url_for("animais.ver", aid=a.id))
        flash("Revise os campos destacados.", "erro")
    anteriores = a.consultas[:3]
    return render_template("atendimento/form.html", a=a, ag=ag, dados=dados, erros=erros,
                           mucosas=MUCOSAS, hidratacao=HIDRATACAO, tipos=TIPOS_AGENDAMENTO,
                           anteriores=anteriores)


@bp.route("/atendimentos/<int:cid>/complemento", methods=["POST"])
@requer_perfil("veterinaria")
def complemento(cid):
    c = db.get_or_404(Consulta, cid)
    texto = (request.form.get("texto") or "").strip()
    if not texto:
        flash("O complemento não pode ficar vazio.", "erro")
    else:
        ad = Adendo(consulta_id=c.id, autor_id=current_user.id, texto=texto[:5000])
        db.session.add(ad)
        db.session.flush()
        registrar("criar", "complemento", ad.id, {"atendimento_id": c.id})
        db.session.commit()
        flash("Complemento adicionado.", "ok")
    return redirect(url_for("animais.ver", aid=c.animal_id, _anchor=f"at-{c.id}"))


def _sugestoes():
    itens = ReceitaItem.query.order_by(ReceitaItem.id.desc()).limit(400).all()
    return sorted({i.medicamento for i in itens if i.medicamento}, key=str.lower)


@bp.route("/pacientes/<int:aid>/receita", methods=["GET", "POST"])
@requer_perfil("veterinaria")
def nova_receita(aid):
    a = _animal(aid)
    consulta_id = request.values.get("consulta_id", type=int)
    erros, orientacoes, tipo = {}, "", "simples"
    itens = [{}]
    base = request.args.get("repetir", type=int)
    if request.method == "GET" and base:
        rec = db.session.get(Receita, base)
        if rec and rec.animal_id == a.id:
            itens = [{k: getattr(i, k) or "" for k in ReceitaItem.CAMPOS} for i in rec.itens] or [{}]
            orientacoes, tipo = rec.orientacoes or "", rec.tipo
    if request.method == "POST":
        orientacoes = (request.form.get("orientacoes") or "").strip()[:3000]
        tipo = request.form.get("tipo") if request.form.get("tipo") in TIPOS_RECEITA else "simples"
        listas = {c: request.form.getlist(c) for c in ReceitaItem.CAMPOS}
        itens = []
        for i in range(min(len(listas["medicamento"]), 30)):
            item = {c: (listas[c][i] if i < len(listas[c]) else "").strip()[:300] for c in ReceitaItem.CAMPOS}
            if any(item.values()):
                itens.append(item)
        if not itens:
            erros["itens"] = "Inclua ao menos um medicamento."
            itens = [{}]
        elif any(not it["medicamento"] or not it["posologia"] for it in itens):
            erros["itens"] = "Cada medicamento precisa de nome e posologia."
        if not erros:
            if consulta_id:
                c = db.session.get(Consulta, consulta_id)
                if not c or c.animal_id != a.id:
                    consulta_id = None
            rec = Receita(animal_id=a.id, veterinario_id=current_user.id, consulta_id=consulta_id,
                          tipo=tipo, orientacoes=orientacoes or None)
            db.session.add(rec)
            db.session.flush()
            for it in itens:
                db.session.add(ReceitaItem(receita_id=rec.id, **{k: (v or None) for k, v in it.items()}))
            registrar("criar", "receita", rec.id, {"paciente_id": a.id, "tipo": tipo, "itens": len(itens)})
            db.session.commit()
            flash("Receita emitida e salva no prontuário.", "ok")
            return redirect(url_for(".imprimir_receita", rid=rec.id))
        flash("Revise os campos destacados.", "erro")
    return render_template("atendimento/receita_form.html", a=a, itens=itens, erros=erros,
                           orientacoes=orientacoes, consulta_id=consulta_id, tipo=tipo,
                           tipos=TIPOS_RECEITA, sugestoes=_sugestoes())


@bp.route("/receitas/<int:rid>")
@requer_perfil("veterinaria")
def imprimir_receita(rid):
    rec = db.get_or_404(Receita, rid)
    if rec.animal.responsavel.anonimizado_em:
        abort(404)
    registrar("visualizar", "receita", rec.id)
    db.session.commit()
    vias = ["1ª via — Farmácia", "2ª via — Tutor"] if rec.tipo == "controle_especial" else [None]
    return render_template("atendimento/receita_imprimir.html", rec=rec, a=rec.animal, vias=vias)
