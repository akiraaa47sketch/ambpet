"""Regras de senha, bloqueio de conta e 2FA (TOTP)."""
import base64
import time
import io
from datetime import timedelta

import pyotp
import qrcode
import qrcode.image.svg
from flask import current_app

from .utils import agora

SENHAS_COMUNS = {
    "1234567890", "12345678910", "senha12345", "senha123456", "password123", "qwerty1234",
    "abcdefghij", "0123456789", "veterinaria", "clinica123", "admin12345", "mudar12345",
    "brasil2024", "brasil2025", "brasil2026",
}


def validar_senha(senha, login="", nome=""):
    """Retorna mensagem de erro ou None."""
    if len(senha) < 10:
        return "A senha precisa ter pelo menos 10 caracteres."
    if len(senha) > 128:
        return "A senha pode ter no máximo 128 caracteres."
    if senha.lower() in SENHAS_COMUNS or len(set(senha)) < 5:
        return "Senha muito previsível. Use uma frase ou combine palavras."
    baixa = senha.lower()
    for parte in [login, *nome.split()]:
        if parte and len(parte) >= 3 and parte.lower() in baixa:
            return "A senha não pode conter seu nome ou login."
    classes = sum([any(c.islower() for c in senha), any(c.isupper() for c in senha),
                   any(c.isdigit() for c in senha), any(not c.isalnum() for c in senha)])
    if classes < 3 and len(senha) < 16:
        return "Use letras maiúsculas, minúsculas e números (ou uma frase com 16+ caracteres)."
    return None


def conta_bloqueada(u):
    return u.bloqueado_ate is not None and u.bloqueado_ate > agora()


def registrar_falha(u):
    u.falhas_login = (u.falhas_login or 0) + 1
    if u.falhas_login >= current_app.config["LOGIN_MAX_TENTATIVAS"]:
        u.bloqueado_ate = agora() + timedelta(minutes=current_app.config["LOGIN_BLOQUEIO_MIN"])
        u.falhas_login = 0
        return True
    return False


def registrar_sucesso(u):
    u.falhas_login = 0
    u.bloqueado_ate = None
    u.ultimo_login_em = agora()


# ---------- TOTP ----------
def novo_segredo_totp():
    return pyotp.random_base32()


def uri_totp(u, segredo):
    return pyotp.TOTP(segredo).provisioning_uri(name=u.login,
                                                issuer_name=current_app.config["CLINICA_NOME"])


def qr_svg_data_uri(texto):
    img = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


def verificar_totp(u, codigo, segredo=None):
    """Valida código de 6 dígitos (janela de ±30 s) e impede reutilização do mesmo código."""
    segredo = segredo or u.totp_segredo
    codigo = "".join(ch for ch in (codigo or "") if ch.isdigit())
    if not segredo or len(codigo) != 6:
        return False
    totp = pyotp.TOTP(segredo)
    passo_atual = int(time.time()) // 30
    for delta in (-1, 0, 1):
        passo = passo_atual + delta
        if totp.verify(codigo, for_time=passo * 30):
            if u.totp_ultimo_passo is not None and passo <= u.totp_ultimo_passo:
                return False  # código já usado
            u.totp_ultimo_passo = passo
            return True
    return False
