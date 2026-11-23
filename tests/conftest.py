import base64
import os

import pyotp
import pytest

from app import create_app, db
from app.models import Usuario

SENHA = "Senha-Forte-123"


def _chave():
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


@pytest.fixture
def app(tmp_path):
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path}/teste.db"
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": url,
        "CSRF_ENABLED": False,
        "SECRET_KEY": "x" * 40,
        "ENCRYPTION_KEYS": f"v1:{_chave()}",
        "ENCRYPTION_ACTIVE_KEY": "v1",
        "BLIND_INDEX_KEY": _chave(),
        "EXIGIR_2FA": False,
        "USAR_VIACEP": False,
    })
    with app.app_context():
        if url.startswith("postgresql"):
            db.drop_all()
            db.create_all()
        for login, perfil in (("admin", "admin"), ("recep", "recepcao"), ("vet", "veterinaria")):
            u = Usuario(login=login, nome=f"{login.title()} Teste", perfil=perfil,
                        crmv="SP-1" if perfil == "veterinaria" else None)
            u.definir_senha(SENHA)
            u.trocar_senha = False
            db.session.add(u)
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        if url.startswith("postgresql"):
            db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def entrar(client, login, senha=SENHA):
    client.post("/logout")
    r = client.post("/login", data={"login": login, "senha": senha})
    assert r.status_code == 302, r.data[:2000]
    return client
