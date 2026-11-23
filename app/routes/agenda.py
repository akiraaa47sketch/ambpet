from datetime import datetime, timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .. import db
from ..audit import registrar
from ..models import STATUS_AGENDAMENTO, Agendamento, Animal, Responsavel
from ..permissoes import requer_perfil
from ..utils import hoje, horarios_disponiveis, parse_data, validar_horario_agendamento
from .main import buscar_responsaveis

bp = Blueprint("agenda", __name__, url_prefix="/agenda")


def _proximo_dia_util(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


@bp.route("/")
@requer_perfil("recepcao", "veterinaria")
def painel():
    """Painel de agendamentos do dia (RF05)."""
    data = parse_data(request.args.get("data")) or hoje()
    ags = (Agendamento.query
           .filter(Agendamento.data_hora >= datetime.combine(data, datetime.min.time()),
                   Agendamento.data_hora < datetime.combine(data + timedelta(days=1),
                                                            datetime.min.time()))
           .order_by(Agendamento.data_hora).all())
    contagem = {s: sum(1 for a in ags if a.status == s) for s in STATUS_AGENDAMENTO}
    return render_template("agenda/painel.html", data=data, ags=ags, contagem=contagem,
                           anterior=data - timedelta(days=1), proximo=data + timedelta(days=1),
                           hoje=hoje(), STATUS=STATUS_AGENDAMENTO)


@bp.route("/novo", methods=["GET", "POST"])
@requer_perfil("recepcao")
def novo():
    rid = request.values.get("responsavel_id", type=int)
    responsavel = db.session.get(Responsavel, rid) if rid else None
    if not responsavel:
        q = request.args.get("q", "")
        return render_template("agenda/escolher_responsavel.html", q=q,
                               resultados=buscar_responsaveis(q))

    dados = {
        "animal_id": request.values.get("animal_id", type=int),
        "data": request.values.get("data") or _proximo_dia_util(hoje()).isoformat(),
        "hora": request.values.get("hora", ""),
        "observacao": request.values.get("observacao", ""),
    }
    erros = {}
    if request.method == "POST":
        animal = db.session.get(Animal, dados["animal_id"]) if dados["animal_id"] else None
        if not animal or animal.responsavel_id != responsavel.id:
            erros["animal_id"] = "Selecione qual animal deste responsável será atendido."
        elif animal.obito:
            erros["animal_id"] = "Este animal está registrado como óbito."
        data_hora = None
        try:
            data_hora = datetime.strptime(f"{dados['data']} {dados['hora']}", "%Y-%m-%d %H:%M")
        except ValueError:
            erros["data"] = "Informe data e horário válidos."
        if data_hora and "data" not in erros:
            msg = validar_horario_agendamento(data_hora)
            if msg:
                erros["data"] = msg
        if not erros:
            conflito = Agendamento.query.filter_by(animal_id=animal.id, data_hora=data_hora,
                                                   status="agendado").first()
            if conflito:
                erros["data"] = "Este animal já possui agendamento neste horário."
        if not erros:
            ag = Agendamento(responsavel_id=responsavel.id, animal_id=animal.id,
                             data_hora=data_hora,
                             observacao=dados["observacao"].strip() or None,
                             criado_por_id=current_user.id)
            db.session.add(ag)
            db.session.flush()
            registrar("criar", "agendamento", ag.id, {
                "responsavel": responsavel.nome, "animal": animal.nome,
                "data_hora": data_hora, "observacao": ag.observacao})
            db.session.commit()
            flash(f"Agendado: {animal.nome} em {data_hora:%d/%m/%Y às %H:%M}.", "ok")
            return redirect(url_for(".painel", data=data_hora.date().isoformat()))
        flash("Não foi possível agendar. Verifique os campos.", "erro")

    animais = [a for a in responsavel.animais if not a.obito]
    if len(animais) == 1 and not dados["animal_id"]:
        dados["animal_id"] = animais[0].id
    # horários já ocupados na data escolhida (apenas informativo)
    ocupados = {}
    d = parse_data(dados["data"])
    if d:
        for a in Agendamento.query.filter(
                Agendamento.status == "agendado",
                Agendamento.data_hora >= datetime.combine(d, datetime.min.time()),
                Agendamento.data_hora < datetime.combine(d + timedelta(days=1), datetime.min.time())):
            ocupados[a.data_hora.strftime("%H:%M")] = ocupados.get(a.data_hora.strftime("%H:%M"), 0) + 1
    return render_template("agenda/form.html", responsavel=responsavel, animais=animais,
                           dados=dados, erros=erros, ocupados=ocupados,
                           horarios=horarios_disponiveis(current_app.config["AGENDA_INTERVALO_MIN"]))


@bp.route("/<int:agid>/status", methods=["POST"])
@requer_perfil("recepcao", "veterinaria")
def alterar_status(agid):
    ag = db.get_or_404(Agendamento, agid)
    novo = request.form.get("status")
    if novo not in STATUS_AGENDAMENTO:
        flash("Status inválido.", "erro")
    elif novo != ag.status:
        registrar("status", "agendamento", ag.id, {"status": {"de": ag.status, "para": novo}})
        ag.status = novo
        db.session.commit()
        flash(f"Agendamento de {ag.animal.nome}: {ag.status_nome}.", "ok")
    return redirect(request.form.get("voltar") or url_for(".painel",
                                                          data=ag.data_hora.date().isoformat()))
