from app import db
from app.models import Agendamento, Animal, Auditoria, Consulta, Receita, Responsavel
from tests.conftest import entrar
from tests.test_validacoes import proxima

RESP = {"nome": "Maria da Silva", "cpf": "529.982.247-25", "telefone": "(11) 98765-4321",
        "cep": "01001-000", "logradouro": "Praça da Sé", "numero": "100", "bairro": "Sé",
        "cidade": "São Paulo", "uf": "SP", "ano_cadunico": "2024"}
ANIMAL = {"nome": "Rex", "sexo": "M", "especie": "Canina", "raca": "SRD",
          "idade_anos": "3", "idade_meses": "2", "castrado": "nao"}


def cadastrar(client):
    entrar(client, "recep")
    r = client.post("/responsaveis/novo", data=RESP)
    assert r.status_code == 302
    rid = Responsavel.query.one().id
    r = client.post(f"/animais/novo?responsavel_id={rid}", data={**ANIMAL, "responsavel_id": rid})
    assert r.status_code == 302
    return rid, Animal.query.one().id


def test_login_obrigatorio(client):
    assert client.get("/agenda/").status_code == 302


def test_cadastro_valida_cpf_e_unicidade(app, client):
    entrar(client, "recep")
    r = client.post("/responsaveis/novo", data={**RESP, "cpf": "123.456.789-00"})
    assert "CPF inválido".encode() in r.data
    client.post("/responsaveis/novo", data=RESP)
    r = client.post("/responsaveis/novo", data=RESP)
    assert "CPF já cadastrado".encode() in r.data
    with app.app_context():
        assert Responsavel.query.count() == 1


def test_fluxo_completo(app, client):
    with app.app_context():
        rid, aid = cadastrar(client)
        # sábado é recusado
        sab = proxima(5)
        r = client.post("/agenda/novo", data={"responsavel_id": rid, "animal_id": aid,
                                              "data": sab.date().isoformat(), "hora": "10:00"})
        assert "segunda a sexta".encode() in r.data
        # fora do horário é recusado
        seg = proxima(0)
        r = client.post("/agenda/novo", data={"responsavel_id": rid, "animal_id": aid,
                                              "data": seg.date().isoformat(), "hora": "17:00"})
        assert "08:00 às 16:00".encode() in r.data
        assert Agendamento.query.count() == 0
        # válido
        r = client.post("/agenda/novo", data={"responsavel_id": rid, "animal_id": aid,
                                              "data": seg.date().isoformat(), "hora": "09:30",
                                              "observacao": "Vacina anual"})
        assert r.status_code == 302
        ag = Agendamento.query.one()
        # painel do dia mostra responsável, animal, telefone e observação
        r = client.get(f"/agenda/?data={seg.date().isoformat()}")
        for txt in ("Maria da Silva", "Rex", "(11) 98765-4321", "Vacina anual", "09:30"):
            assert txt.encode() in r.data
        # recepção não acessa consultas/receitas
        assert client.get(f"/animais/{aid}/consultas/nova").status_code == 403
        assert client.get(f"/animais/{aid}/receitas/nova").status_code == 403

        entrar(client, "vet")
        r = client.post(f"/animais/{aid}/consultas/nova",
                        data={"agendamento_id": ag.id, "anotacao": "Animal saudável.", "peso_kg": "12,5"})
        assert r.status_code == 302
        c = Consulta.query.one()
        assert db.session.get(Agendamento, ag.id).status == "realizado"
        assert str(db.session.get(Animal, aid).peso_kg) == "12.50"
        client.post(f"/consultas/{c.id}/adendo", data={"texto": "Retorno em 30 dias."})
        r = client.post(f"/animais/{aid}/receitas/nova", data={
            "medicamento": ["Amoxicilina", ""], "concentracao": ["250 mg", ""],
            "quantidade": ["", ""], "via": ["Oral", ""],
            "posologia": ["1 comprimido a cada 12h", ""], "duracao": ["7 dias", ""]})
        assert r.status_code == 302
        rec = Receita.query.one()
        assert len(rec.itens) == 1
        r = client.get(f"/animais/{aid}")
        for txt in ("Animal saudável.", "Retorno em 30 dias.", "Amoxicilina", "1 comprimido a cada 12h"):
            assert txt.encode() in r.data
        r = client.get(f"/receitas/{rec.id}")
        assert b"CRMV SP-1" in r.data
        # não existem rotas para editar/excluir consulta
        assert client.post(f"/consultas/{c.id}/editar").status_code == 404

        # auditoria registrou as ações
        acoes = {(a.acao, a.entidade) for a in Auditoria.query}
        for esperado in (("criar", "responsavel"), ("criar", "animal"), ("criar", "agendamento"),
                         ("criar", "consulta"), ("criar", "adendo"), ("criar", "receita")):
            assert esperado in acoes
        assert all(a.usuario_id for a in Auditoria.query)


def test_edicao_gera_historico(app, client):
    with app.app_context():
        rid, aid = cadastrar(client)
        client.post(f"/responsaveis/{rid}/editar", data={**RESP, "telefone": "(11) 91234-5678"})
        log = Auditoria.query.filter_by(entidade="responsavel", acao="editar").one()
        assert log.detalhes_dict["telefone"] == {"de": "11987654321", "para": "11912345678"}
        r = client.get(f"/responsaveis/{rid}/historico")
        assert b"11912345678" in r.data


def test_agendar_animal_de_outro_responsavel(app, client):
    with app.app_context():
        rid, aid = cadastrar(client)
        outro = {**RESP, "cpf": "111.444.777-35", "nome": "João"}
        client.post("/responsaveis/novo", data=outro)
        rid2 = Responsavel.query.filter_by(nome="João").one().id
        client.post(f"/animais/novo?responsavel_id={rid2}", data={**ANIMAL, "nome": "Mimi", "responsavel_id": rid2})
        seg = proxima(0)
        r = client.post("/agenda/novo", data={"responsavel_id": rid2, "animal_id": aid,
                                              "data": seg.date().isoformat(), "hora": "10:00"})
        assert "Selecione qual animal".encode() in r.data
        assert Agendamento.query.count() == 0


def test_admin_paginas(client):
    entrar(client, "admin")
    assert client.get("/admin/usuarios").status_code == 200
    assert client.get("/admin/auditoria").status_code == 200
    entrar(client, "recep")
    assert client.get("/admin/usuarios").status_code == 403
