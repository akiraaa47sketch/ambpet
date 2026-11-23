from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def requer_perfil(*perfis):
    """Restringe a rota aos perfis informados (o administrador sempre tem acesso)."""
    def deco(fn):
        @wraps(fn)
        @login_required
        def inner(*a, **kw):
            if not current_user.tem_perfil(*perfis):
                abort(403)
            return fn(*a, **kw)
        return inner
    return deco
