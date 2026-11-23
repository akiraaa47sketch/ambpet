import pytest

from app import create_app, db
from app.models import Usuario


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/teste.db",
        "CSRF_ENABLED": False,
        "SECRET_KEY": "teste",
    })
    with app.app_context():
        for login, perfil in (("admin", "admin"), ("recep", "recepcao"), ("vet", "veterinaria")):
            u = Usuario(login=login, nome=login.title(), perfil=perfil, crmv="SP-1" if perfil == "veterinaria" else None)
            u.definir_senha("senha1234")
            db.session.add(u)
        db.session.commit()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def entrar(client, login):
    client.post("/logout")
    r = client.post("/login", data={"login": login, "senha": "senha1234"})
    assert r.status_code == 302, r.data
    return client
