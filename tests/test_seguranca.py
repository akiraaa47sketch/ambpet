import re
import time

import pyotp
import pytest

from app import db
from app.audit import registrar, verificar_cadeia
from app.config import ErroConfiguracao, carregar
from app.models import Auditoria, Usuario
from tests.conftest import SENHA, entrar


def test_bloqueio_apos_tentativas(app, client):
    for _ in range(5):
        client.post("/login", data={"login": "recep", "senha": "errada"})
    r = client.post("/login", data={"login": "recep", "senha": SENHA})
    assert r.status_code == 200 and "Acesso indisponível".encode() in r.data
    with app.app_context():
        assert Usuario.query.filter_by(login="recep").one().bloqueado_ate is not None


def test_mensagem_nao_revela_usuario(client):
    a = client.post("/login", data={"login": "naoexiste", "senha": "x"}).data
    b = client.post("/login", data={"login": "recep", "senha": "x"}).data
    assert "Usuário ou senha inválidos".encode() in a and "Usuário ou senha inválidos".encode() in b


def test_2fa_obrigatorio_e_login_com_codigo(app, client):
    app.config["EXIGIR_2FA"] = True
    entrar(client, "vet")
    r = client.get("/agenda/")
    assert r.status_code == 302 and "/conta/2fa" in r.location
    r = client.get("/conta/2fa")
    segredo = re.search(rb'class="chave-manual">([A-Z2-7]+)<', r.data).group(1).decode()
    assert client.post("/conta/2fa", data={"codigo": "000000"}).status_code == 200
    r = client.post("/conta/2fa", data={"codigo": pyotp.TOTP(segredo).now()})
    assert r.status_code == 302
    assert client.get("/agenda/").status_code == 200
    # novo login exige o código
    client.post("/logout")
    r = client.post("/login", data={"login": "vet", "senha": SENHA})
    assert "/login/verificacao" in r.location
    assert client.get("/agenda/").status_code == 302
    # mesmo código não pode ser reutilizado
    r = client.post("/login/verificacao", data={"codigo": pyotp.TOTP(segredo).now()})
    assert "Código inválido".encode() in r.data
    with app.app_context():
        u = Usuario.query.filter_by(login="vet").one()
        u.totp_ultimo_passo = None
        db.session.commit()
    r = client.post("/login/verificacao", data={"codigo": pyotp.TOTP(segredo).now()})
    assert r.status_code == 302
    assert client.get("/agenda/").status_code == 200


def test_troca_de_senha_derruba_outras_sessoes(app):
    c1, c2 = app.test_client(), app.test_client()
    entrar(c1, "recep")
    entrar(c2, "recep")
    r = c1.post("/conta/senha", data={"atual": SENHA, "nova": "Nova-Senha-Forte-9",
                                      "confirmacao": "Nova-Senha-Forte-9"})
    assert r.status_code == 302
    assert c1.get("/agenda/").status_code == 200
    assert c2.get("/agenda/").status_code == 302


def test_senha_temporaria_forca_troca(app, client):
    entrar(client, "admin")
    r = client.post("/admin/usuarios/novo", data={"nome": "Ana Lima", "login": "ana", "perfil": "recepcao"})
    temp = re.search(rb'<p class="senha-temp"><code>([A-Za-z0-9]+)</code>', r.data).group(1).decode()
    entrar(client, "ana", temp)
    r = client.get("/agenda/")
    assert "/conta/senha" in r.location


def test_inatividade_expira_sessao(app, client):
    entrar(client, "recep")
    with client.session_transaction() as s:
        s["_ultimo"] = int(time.time()) - 31 * 60
    r = client.get("/agenda/")
    assert r.status_code == 302 and "/login" in r.location


def test_csrf(app, client):
    app.config["CSRF_ENABLED"] = True
    r = client.post("/login", data={"login": "recep", "senha": SENHA})
    assert r.status_code == 400


def test_cabecalhos_seguranca(client):
    r = client.get("/login")
    csp = r.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Cache-Control"] == "no-store"


def test_sem_script_em_linha(app, client):
    entrar(client, "admin")
    for url in ("/agenda/", "/tutores/", "/admin/usuarios", "/admin/auditoria"):
        html = client.get(url).data.decode()
        assert not re.search(r"\son[a-z]+=", html), url
        assert not re.search(r"<script>(?!</script>)", html), url
        assert "style=" not in html, url


def test_cadeia_auditoria_detecta_adulteracao(app):
    with app.app_context():
        for i in range(3):
            registrar("teste", "x", i)
        db.session.commit()
        assert verificar_cadeia()[0]
        reg = Auditoria.query.filter_by(entidade="x", entidade_id=1).one()
        reg.acao = "adulterado"
        db.session.commit()
        ok, rid, _ = verificar_cadeia()
        assert not ok and rid == reg.id


def test_producao_exige_segredos(monkeypatch):
    for k in ("SECRET_KEY", "DATABASE_URL", "ENCRYPTION_KEYS", "BLIND_INDEX_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENV_FILE", "/nao/existe")
    with pytest.raises(ErroConfiguracao):
        carregar()
    monkeypatch.setenv("SECRET_KEY", "s" * 40)
    monkeypatch.setenv("ENCRYPTION_KEYS", "v1:" + "A" * 43)
    monkeypatch.setenv("BLIND_INDEX_KEY", "B" * 43)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///x.db")
    with pytest.raises(ErroConfiguracao, match="PostgreSQL"):
        carregar()
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.exemplo.supabase.co:5432/postgres?sslmode=disable")
    with pytest.raises(ErroConfiguracao, match="TLS"):
        carregar()
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.exemplo.supabase.co:5432/postgres")
    cfg = carregar()
    assert "sslmode=require" in cfg["SQLALCHEMY_DATABASE_URI"]
    assert cfg["SESSION_COOKIE_SECURE"] and cfg["SESSION_COOKIE_NAME"].startswith("__Host-")
