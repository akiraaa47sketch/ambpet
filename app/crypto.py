"""Criptografia de campos no nível da aplicação.

- AES-256-GCM (autenticada) com nonce aleatório de 96 bits por valor.
- Cada valor cifrado carrega o id da chave ("v1$...") para permitir rotação.
- O nome da coluna entra como "associated data": um valor cifrado copiado para
  outra coluna/tabela não decifra (impede troca de campos no banco).
- Índices cegos (HMAC-SHA256 com chave separada) permitem busca exata e
  unicidade (CPF, telefone) e busca por prefixo de palavras do nome, sem
  guardar o texto em claro.

As chaves NUNCA ficam no banco nem no código: vêm de variáveis de ambiente.
"""
import base64
import hashlib
import hmac
import os
import re
import unicodedata

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


class ErroChave(RuntimeError):
    pass


class Chaveiro:
    def __init__(self):
        self.chaves = {}
        self.ativa = None
        self.chave_indice = None

    def configurar(self, chaves_env, ativa, chave_indice_b64):
        """chaves_env: 'v1:BASE64,v2:BASE64'; ativa: 'v2'; chave_indice_b64: BASE64."""
        chaves = {}
        for parte in filter(None, (p.strip() for p in (chaves_env or "").split(","))):
            kid, _, b64 = parte.partition(":")
            chave = _b64(b64)
            if len(chave) != 32 or not re.fullmatch(r"[A-Za-z0-9]{1,16}", kid):
                raise ErroChave(f"Chave '{kid}' inválida: precisa de id alfanumérico e 32 bytes em base64.")
            chaves[kid] = AESGCM(chave)
        if not chaves:
            raise ErroChave("ENCRYPTION_KEYS não configurada.")
        ativa = ativa or list(chaves)[-1]
        if ativa not in chaves:
            raise ErroChave("ENCRYPTION_ACTIVE_KEY não corresponde a nenhuma chave.")
        indice = _b64(chave_indice_b64 or "")
        if len(indice) < 32:
            raise ErroChave("BLIND_INDEX_KEY ausente ou curta (mín. 32 bytes em base64).")
        self.chaves, self.ativa, self.chave_indice = chaves, ativa, indice

    # --- cifra ---
    def cifrar(self, texto, contexto):
        if texto is None:
            return None
        nonce = os.urandom(12)
        ct = self.chaves[self.ativa].encrypt(nonce, str(texto).encode("utf-8"), contexto.encode())
        return f"{self.ativa}${base64.urlsafe_b64encode(nonce + ct).decode()}"

    def decifrar(self, valor, contexto):
        if valor is None:
            return None
        kid, sep, b64 = valor.partition("$")
        if not sep or kid not in self.chaves:
            raise ErroChave(f"Valor cifrado com chave desconhecida ({kid!r}).")
        bruto = base64.urlsafe_b64decode(b64)
        return self.chaves[kid].decrypt(bruto[:12], bruto[12:], contexto.encode()).decode("utf-8")

    # --- índices cegos ---
    def hash(self, valor, contexto):
        if valor is None or valor == "":
            return None
        return hmac.new(self.chave_indice, f"{contexto}|{valor}".encode(), hashlib.sha256).hexdigest()

    def tokens_nome(self, texto, contexto, minimo=2):
        """Tokens de prefixo de cada palavra normalizada (para busca por início de palavra)."""
        tokens = set()
        for palavra in normalizar(texto).split():
            for i in range(minimo, len(palavra) + 1):
                tokens.add(self.hash(palavra[:i], contexto)[:32])
        return tokens


chaveiro = Chaveiro()


def _b64(s):
    s = s.strip()
    try:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except Exception:  # noqa: BLE001
        try:
            return base64.b64decode(s + "=" * (-len(s) % 4))
        except Exception as e:  # noqa: BLE001
            raise ErroChave("Chave em base64 inválida.") from e


def nova_chave():
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", " ", texto.lower())


class Criptografado(TypeDecorator):
    """Coluna de texto cifrada de forma transparente (AES-256-GCM)."""
    impl = Text
    cache_ok = True

    def __init__(self, contexto, *a, **kw):
        self.contexto = contexto
        super().__init__(*a, **kw)

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return None
        return chaveiro.cifrar(value, self.contexto)

    def process_result_value(self, value, dialect):
        return chaveiro.decifrar(value, self.contexto)
