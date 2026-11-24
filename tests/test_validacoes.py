from datetime import datetime, timedelta

from app.utils import (hoje, horarios_disponiveis, validar_cpf, validar_horario_agendamento,
                       validar_telefone)
from app.seguranca import validar_senha


def proxima(weekday, hora=10, minuto=0):
    d = hoje() + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return datetime(d.year, d.month, d.day, hora, minuto)


def test_cpf():
    assert validar_cpf("529.982.247-25")
    assert not validar_cpf("529.982.247-24")
    assert not validar_cpf("111.111.111-11")


def test_telefone():
    assert validar_telefone("(11) 98765-4321")
    assert validar_telefone("(11) 3456-7890")
    assert not validar_telefone("(11) 88765-4321")


def test_horario_dias_uteis():
    assert validar_horario_agendamento(proxima(0, 8, 0)) is None
    assert validar_horario_agendamento(proxima(4, 16, 0)) is None
    assert "segunda a sexta" in validar_horario_agendamento(proxima(5))
    assert "segunda a sexta" in validar_horario_agendamento(proxima(6))
    assert "08:00 às 16:00" in validar_horario_agendamento(proxima(2, 7, 59))
    assert "08:00 às 16:00" in validar_horario_agendamento(proxima(2, 16, 1))
    assert "já passou" in validar_horario_agendamento(datetime(2020, 1, 6, 10, 0))


def test_lista_horarios():
    h = horarios_disponiveis(30)
    assert h[0] == "08:00" and h[-1] == "16:00" and len(h) == 17


def test_politica_senha():
    assert validar_senha("curta1A") is not None
    assert validar_senha("1234567890") is not None
    assert validar_senha("Maria-12345", login="maria") is not None
    assert validar_senha("Cavalo-Bateria-9") is None
    assert validar_senha("uma frase longa e facil de lembrar") is None
