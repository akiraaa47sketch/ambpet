import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
import os

TZ = ZoneInfo(os.environ.get("TZ_CLINICA", "America/Sao_Paulo"))

HORA_INICIO = time(8, 0)
HORA_FIM = time(16, 0)
DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]


def agora():
    """Data/hora local da clínica, sem fuso (armazenada assim no banco)."""
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


def hoje():
    return agora().date()


def so_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def validar_cpf(cpf):
    cpf = so_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in (9, 10):
        soma = sum(int(cpf[j]) * ((i + 1) - j) for j in range(i))
        dig = (soma * 10) % 11
        if dig == 10:
            dig = 0
        if dig != int(cpf[i]):
            return False
    return True


def validar_telefone(tel):
    tel = so_digitos(tel)
    # DDD + 8 dígitos (fixo) ou DDD + 9 dígitos começando com 9 (celular)
    if len(tel) == 10:
        return tel[0] != "0" and tel[2] in "2345"
    if len(tel) == 11:
        return tel[0] != "0" and tel[2] == "9"
    return False


def validar_cep(cep):
    return len(so_digitos(cep)) == 8


def formatar_cpf(cpf):
    c = so_digitos(cpf)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}" if len(c) == 11 else (cpf or "")


def formatar_telefone(tel):
    t = so_digitos(tel)
    if len(t) == 11:
        return f"({t[:2]}) {t[2:7]}-{t[7:]}"
    if len(t) == 10:
        return f"({t[:2]}) {t[2:6]}-{t[6:]}"
    return tel or ""


def formatar_cep(cep):
    c = so_digitos(cep)
    return f"{c[:5]}-{c[5:]}" if len(c) == 8 else (cep or "")


def validar_horario_agendamento(data_hora, permitir_passado=False):
    """Retorna mensagem de erro ou None se o horário for permitido.

    Regras (RF04 / seção 6): segunda a sexta, das 08:00 às 16:00.
    """
    if data_hora is None:
        return "Informe data e horário."
    if data_hora.weekday() >= 5:
        return (f"Não é possível agendar em {DIAS_SEMANA[data_hora.weekday()]}. "
                "Agendamentos somente de segunda a sexta-feira.")
    t = data_hora.time()
    if t < HORA_INICIO or t > HORA_FIM:
        return "Horário fora do expediente. Agendamentos somente das 08:00 às 16:00."
    if not permitir_passado and data_hora < agora():
        return "Não é possível agendar em data/horário que já passou."
    return None


def horarios_disponiveis(intervalo_min=30):
    out = []
    m = HORA_INICIO.hour * 60 + HORA_INICIO.minute
    fim = HORA_FIM.hour * 60 + HORA_FIM.minute
    while m <= fim:
        out.append(f"{m // 60:02d}:{m % 60:02d}")
        m += intervalo_min
    return out


def idade_texto(animal):
    """Idade estimada atual, a partir da idade informada e da data em que foi informada."""
    if animal is None or (animal.idade_anos is None and animal.idade_meses is None):
        return "—"
    total = (animal.idade_anos or 0) * 12 + (animal.idade_meses or 0)
    ref = animal.idade_referencia or hoje()
    h = hoje()
    total += max(0, (h.year - ref.year) * 12 + (h.month - ref.month) - (1 if h.day < ref.day else 0))
    anos, meses = divmod(total, 12)
    partes = []
    if anos:
        partes.append(f"{anos} ano" + ("s" if anos > 1 else ""))
    if meses:
        partes.append(f"{meses} " + ("meses" if meses > 1 else "mês"))
    return " e ".join(partes) or "menos de 1 mês"


def parse_data(valor):
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None
