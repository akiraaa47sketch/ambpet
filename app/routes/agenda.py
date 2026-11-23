from datetime import datetime, timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .. import db
from ..audit import registrar
from ..models import (STATUS_AGENDAMENTO, STATUS_ATIVOS, TIPOS_AGENDAMENTO, Agendamento, Animal,
                      Responsavel)
from ..permissoes import requer_perfil
from ..utils import (HORA_FIM, HORA_INICIO, agora, hoje, horarios_disponiveis, parse_data,
                     validar_horario_agendamento)
from .main import buscar_responsaveis

bp = Blueprint("agenda", __name__, url_prefix="/agenda")

# transições permitidas (quem pode e para onde)
TRANSICOES = {
    "confirmar": ("confirmado", ("agendado",), ("recepcao",)),
    "chegou": ("aguardando", ("agendado", "confirmado"), ("recepcao",)),
    "faltou": ("faltou", ("agendado", "confirmado"), ("recepcao",)),
    "cancelar": ("cancelado", ("agendado", "confirmado", "aguardando"), ("recepcao",)),
    "reabrir": ("agendado", ("faltou", "cancelado"), ("recepcao",)),
    "desfazer_chegada": ("confirmado", ("aguardando",), ("recepcao",)),
}


def _intervalo_dia(d):
    ini = datetime.combine(d, datetime.min.time())
    return ini, ini + timedelta(days=1)


def _proximo_dia_util(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _do_periodo(ini, fim):
    return (Agendamento.query.filter(Agendamento.data_hora >= ini, Agendamento.data_hora < fim)
            .order_by(Agendamento.data_hora, Agendamento.id).all())


@bp.route("/")
@requer_perfil("recepcao", "veterinaria")
def dia():
    """Agenda do dia (RF05): grade de horários + sala de espera."""
    data = parse_data(request.args.get("data")) or hoje()
    ags = _do_periodo(*_intervalo_dia(data))
    intervalo = current_app.config["AGENDA_INTERVALO_MIN"]
    slots = {h: [] for h in horarios_disponiveis(intervalo)}
    fora = []
    for ag in ags:
        # encaixa no horário de grade imediatamente anterior
        m = ag.data_hora.hour * 60 + ag.data_hora.minute
        base = HORA_INICIO.hour * 60
        chave = base + ((m - base) // intervalo) * intervalo
        k = f"{chave // 60:02d}:{chave % 60:02d}"
        (slots[k] if k in slots else fora).append(ag)
    espera = sorted([a for a in ags if a.status in ("aguardando", "em_atendimento")],
                    key=lambda a: (a.status != "em_atendimento", a.chegada_em or a.data_hora))
    contagem = {s: sum(1 for a in ags if a.status == s) for s in STATUS_AGENDAMENTO}
    agora_ = agora()
    return render_template("agenda/dia.html", data=data, slots=slots, fora=fora, ags=ags,
                           espera=espera, contagem=contagem, hoje=hoje(), agora=agora_,
                           anterior=data - timedelta(days=1), proximo=data + timedelta(days=1),
                           util=data.weekday() < 5, passado=data < hoje())


@bp.route("/semana")
@requer_perfil("recepcao", "veterinaria")
def semana():
    ref = parse_data(request.args.get("data")) or hoje()
    seg = ref - timedelta(days=ref.weekday())
    dias = [seg + timedelta(days=i) for i in range(5)]
    ags = _do_periodo(datetime.combine(seg, datetime.min.time()),
                      datetime.combine(seg + timedelta(days=5), datetime.min.time()))
    intervalo = current_app.config["AGENDA_INTERVALO_MIN"]
    horas = horarios_disponiveis(intervalo)
    grade = {(d, h): [] for d in dias for h in horas}
    base = HORA_INICIO.hour * 60
    for ag in ags:
        if ag.status == "cancelado":
            continue
        m = ag.data_hora.hour * 60 + ag.data_hora.minute
        c = base + ((m - base) // intervalo) * intervalo
        k = (ag.data_hora.date(), f"{c // 60:02d}:{c % 60:02d}")
        if k in grade:
            grade[k].append(ag)
    total = {d: sum(1 for a in ags if a.data_hora.date() == d and a.status != "cancelado") for d in dias}
    return render_template("agenda/semana.html", dias=dias, horas=horas, grade=grade, total=total,
                           hoje=hoje(), anterior=seg - timedelta(days=7), proximo=seg + timedelta(days=7))


@bp.route("/novo", methods=["GET", "POST"])
@requer_perfil("recepcao")
def novo():
    rid = request.values.get("responsavel_id", type=int)
    responsavel = db.session.get(Responsavel, rid) if rid else None
    if responsavel and responsavel.anonimizado_em:
        responsavel = None
    pre = {"data": request.values.get("data", ""), "hora": request.values.get("hora", "")}
    if not responsavel:
        q = request.form.get("q", "") if request.method == "POST" else ""
        return render_template("agenda/escolher_tutor.html", q=q, pre=pre,
                               resultados=buscar_responsaveis(q) if q else [])

    dados = {
        "animal_id": request.values.get("animal_id", type=int),
        "data": pre["data"] or _proximo_dia_util(hoje()).isoformat(),
        "hora": pre["hora"],
        "tipo": request.values.get("tipo", "Consulta"),
        "observacao": request.form.get("observacao", ""),
    }
    erros = {}
    if request.method == "POST" and request.form.get("confirmar"):
        animal = db.session.get(Animal, dados["animal_id"]) if dados["animal_id"] else None
        if not animal or animal.responsavel_id != responsavel.id:
            erros["animal_id"] = "Selecione o paciente que será atendido."
        elif animal.obito:
            erros["animal_id"] = "Paciente com óbito registrado."
        if dados["tipo"] not in TIPOS_AGENDAMENTO:
            erros["tipo"] = "Selecione o tipo."
        data_hora = None
        try:
            data_hora = datetime.strptime(f"{dados['data']} {dados['hora']}", "%Y-%m-%d %H:%M")
        except ValueError:
            erros["data"] = "Escolha data e horário."
        if data_hora and "data" not in erros:
            msg = validar_horario_agendamento(data_hora)
            if msg:
                erros["data"] = msg
        if not erros and Agendamento.query.filter(
                Agendamento.animal_id == animal.id, Agendamento.data_hora == data_hora,
                Agendamento.status.in_(STATUS_ATIVOS)).first():
            erros["data"] = "Este paciente já tem agendamento neste horário."
        if not erros:
            ag = Agendamento(responsavel_id=responsavel.id, animal_id=animal.id, data_hora=data_hora,
                             tipo=dados["tipo"], observacao=dados["observacao"].strip()[:500] or None,
                             criado_por_id=current_user.id)
            db.session.add(ag)
            db.session.flush()
            registrar("criar", "agendamento", ag.id, {"paciente_id": animal.id, "data_hora": data_hora,
                                                      "tipo": ag.tipo})
            db.session.commit()
            flash(f"{animal.nome} agendado para {data_hora:%d/%m} às {data_hora:%H:%M}.", "ok")
            return redirect(url_for(".dia", data=data_hora.date().isoformat()))
        flash("Não foi possível agendar. Revise os campos.", "erro")

    animais = [a for a in responsavel.animais if not a.obito]
    if len(animais) == 1 and not dados["animal_id"]:
        dados["animal_id"] = animais[0].id
    ocupados = {}
    d = parse_data(dados["data"])
    if d:
        for a in _do_periodo(*_intervalo_dia(d)):
            if a.ativo:
                k = a.data_hora.strftime("%H:%M")
                ocupados[k] = ocupados.get(k, 0) + 1
    return render_template("agenda/form.html", responsavel=responsavel, animais=animais,
                           dados=dados, erros=erros, ocupados=ocupados, tipos=TIPOS_AGENDAMENTO,
                           horarios=horarios_disponiveis(15),
                           inicio=HORA_INICIO, fim=HORA_FIM)


@bp.route("/<int:agid>/acao", methods=["POST"])
@requer_perfil("recepcao")
def acao(agid):
    ag = db.get_or_404(Agendamento, agid)
    nome = request.form.get("acao")
    regra = TRANSICOES.get(nome)
    if not regra or ag.status not in regra[1]:
        flash("Ação não permitida para a situação atual.", "erro")
    else:
        novo = regra[0]
        registrar("status", "agendamento", ag.id, {"status": {"de": ag.status, "para": novo}})
        ag.status = novo
        if novo == "aguardando":
            ag.chegada_em = agora()
        elif nome == "desfazer_chegada":
            ag.chegada_em = None
        db.session.commit()
        flash(f"{ag.animal.nome}: {ag.status_nome.lower()}.", "ok")
    destino = request.form.get("voltar", "")
    if not destino.startswith("/") or destino.startswith("//"):
        destino = url_for(".dia", data=ag.data_hora.date().isoformat())
    return redirect(destino)
