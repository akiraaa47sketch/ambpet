import json
from datetime import date, datetime
from decimal import Decimal

from flask_login import current_user

from . import db
from .models import Auditoria


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


def registrar(acao, entidade, entidade_id, detalhes=None):
    """Adiciona um registro de auditoria à sessão atual (commit fica com quem chamou)."""
    db.session.add(Auditoria(
        usuario_id=current_user.id if current_user and current_user.is_authenticated else None,
        acao=acao,
        entidade=entidade,
        entidade_id=entidade_id,
        detalhes=json.dumps(detalhes, ensure_ascii=False, default=_serial) if detalhes else None,
    ))
