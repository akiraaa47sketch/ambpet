from markupsafe import Markup

from .utils import formatar_cep, formatar_cpf, formatar_telefone, idade_texto

DIAS = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira",
        "Sábado", "Domingo"]
DIAS_CURTOS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


def numero(v, casas=1):
    if v is None:
        return ""
    s = f"{float(v):.{casas}f}".replace(".", ",")
    return s.rstrip("0").rstrip(",") if "," in s else s


def registrar_filtros(app):
    f = app.jinja_env.filters
    f["cpf"] = formatar_cpf
    f["telefone"] = formatar_telefone
    f["cep"] = formatar_cep
    f["idade"] = idade_texto
    f["num"] = numero
    f["data"] = lambda d: d.strftime("%d/%m/%Y") if d else ""
    f["datahora"] = lambda d: d.strftime("%d/%m/%Y %H:%M") if d else ""
    f["hora"] = lambda d: d.strftime("%H:%M") if d else ""
    f["dia_semana"] = lambda d: DIAS[d.weekday()]
    f["dia_curto"] = lambda d: DIAS_CURTOS[d.weekday()]
    f["data_extenso"] = lambda d: f"{d.day} de {MESES[d.month - 1]} de {d.year}"
    f["data_curta"] = lambda d: f"{d.day:02d}/{d.month:02d}"

    from .icones import icone
    app.jinja_env.globals["icone"] = lambda nome, classe="": Markup(icone(nome, classe))
