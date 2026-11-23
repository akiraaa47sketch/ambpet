"""Trilha de auditoria encadeada.

Cada registro guarda o HMAC do anterior + seu conteúdo. Alterar ou apagar um
registro quebra a cadeia, o que é detectado por `flask verificar-auditoria`.
"""
import hashlib
import hmac
import json
from datetime import date, datetime
from decimal import Decimal

from flask import has_request_context, request
from flask_login import current_user
from sqlalchemy import text

from . import db
from .crypto import chaveiro
from .models import Auditoria
from .utils import agora

GENESIS = "0" * 64


def _serial(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return v


def snapshot(obj, campos):
    return {c: _serial(getattr(obj, c)) for c in campos}


def diff(antes, depois):
    return {c: {"de": antes.get(c), "para": depois.get(c)}
            for c in depois if antes.get(c) != depois.get(c)}


def calcular_hash(anterior, usuario_id, acao, entidade, entidade_id, detalhes, criado_em):
    conteudo = "|".join(str(x) for x in (anterior, usuario_id, acao, entidade, entidade_id,
                                          detalhes or "", criado_em.isoformat()))
    return hmac.new(chaveiro.chave_indice, conteudo.encode(), hashlib.sha256).hexdigest()


def registrar(acao, entidade, entidade_id, detalhes=None, usuario_id=None):
    """Adiciona um registro de auditoria à transação atual (o commit fica com quem chamou)."""
    if usuario_id is None and has_request_context() and current_user and current_user.is_authenticated:
        usuario_id = current_user.id
    det = json.dumps(detalhes, ensure_ascii=False, default=_serial, sort_keys=True) if detalhes else None
    ip = request.remote_addr if has_request_context() else None

    if db.engine.dialect.name == "postgresql":
        # serializa a cadeia entre transações concorrentes
        db.session.execute(text("select pg_advisory_xact_lock(724001)"))
    ultimo = db.session.query(Auditoria.hash).order_by(Auditoria.id.desc()).limit(1).scalar()
    anterior = ultimo or GENESIS
    criado = agora()
    reg = Auditoria(usuario_id=usuario_id, acao=acao, entidade=entidade, entidade_id=entidade_id,
                    detalhes=det, ip=ip, criado_em=criado, hash_anterior=anterior,
                    hash=calcular_hash(anterior, usuario_id, acao, entidade, entidade_id, det, criado))
    db.session.add(reg)
    db.session.flush()
    return reg


def verificar_cadeia():
    """Retorna (ok, id_do_primeiro_registro_inválido_ou_None, total)."""
    anterior = GENESIS
    total = 0
    for reg in db.session.query(Auditoria).order_by(Auditoria.id).yield_per(500):
        total += 1
        esperado = calcular_hash(anterior, reg.usuario_id, reg.acao, reg.entidade,
                                 reg.entidade_id, reg.detalhes, reg.criado_em)
        if reg.hash_anterior != anterior or not hmac.compare_digest(reg.hash, esperado):
            return False, reg.id, total
        anterior = reg.hash
    return True, None, total
