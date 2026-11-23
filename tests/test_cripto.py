import base64
import os

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import text

from app import db
from app.crypto import Chaveiro, chaveiro
from tests.test_fluxo import RESP, cadastrar


def k():
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def test_roundtrip_e_contexto():
    c = Chaveiro()
    c.configurar(f"v1:{k()}", "v1", k())
    ct = c.cifrar("52998224725", "tutores.cpf")
    assert ct.startswith("v1$") and "52998224725" not in ct
    assert c.decifrar(ct, "tutores.cpf") == "52998224725"
    assert c.cifrar("x", "a") != c.cifrar("x", "a")  # nonce aleatório
    with pytest.raises(InvalidTag):
        c.decifrar(ct, "tutores.nome")  # valor movido para outra coluna não decifra


def test_rotacao_de_chave():
    c = Chaveiro()
    k1, k2, idx = k(), k(), k()
    c.configurar(f"v1:{k1}", "v1", idx)
    antigo = c.cifrar("segredo", "t")
    c.configurar(f"v1:{k1},v2:{k2}", "v2", idx)
    assert c.decifrar(antigo, "t") == "segredo"
    assert c.cifrar("segredo", "t").startswith("v2$")


def test_chave_invalida():
    with pytest.raises(Exception):
        Chaveiro().configurar("v1:curta", "v1", k())


def test_banco_nao_guarda_texto_claro(app, client):
    with app.app_context():
        rid, aid = cadastrar(client)
        pre = "ambpet." if db.engine.dialect.name == "postgresql" else ""
        bruto = " ".join(str(v) for row in db.session.execute(text(f"select * from {pre}tutores")) for v in row)
        for claro in ("Maria", "52998224725", "11987654321", "Praça", "2024"):
            assert claro not in bruto
        bruto_busca = " ".join(str(v) for row in db.session.execute(text(f"select * from {pre}indice_busca")) for v in row)
        assert "maria" not in bruto_busca.lower()
