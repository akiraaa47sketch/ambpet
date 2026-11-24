import json

from app import db
from app.models import (Agendamento, Animal, Auditoria, Consulta, Receita, Responsavel, Usuario)
from tests.conftest import entrar
from tests.test_validacoes import proxima

RESP = {"nome": "Maria da Silva", "cpf": "529.982.247-25", "telefone": "(11) 98765-4321",
        "cep": "01001-000", "logradouro": "Praça da Sé", "numero": "100", "bairro": "Sé",
        "cidade": "São Paulo", "uf": "SP", "ano_cadunico": "2024", "aviso_privacidade": "on"}
ANIMAL = {"nome": "Rex", "sexo": "M", "especie": "Canina", "raca": "SRD",
          "idade_anos": "3", "idade_meses": "2", "castrado": "nao"}


def cadastrar(client):
    entrar(client, "recep")
    r = client.post("/tutores/novo", data=RESP)
    assert r.status_code == 302, r.data[:3000]
    rid = Responsavel.query.one().id
    r = client.post(f"/pacientes/novo?responsavel_id={rid}", data=ANIMAL)
    assert r.status_code == 302
    return rid, Animal.query.one().id


def agendar(client, rid, aid, quando, **extra):
    return client.post("/agenda/novo", data={"responsavel_id": rid, "animal_id": aid, "confirmar": "1",
                                             "data": quando.date().isoformat(),
                                             "hora": quando.strftime("%H:%M"), **extra})


def test_login_obrigatorio(client):
    assert client.get("/agenda/").status_code == 302


def test_cadastro_exige_aviso_e_valida_cpf(app, client):
    entrar(client, "recep")
    r = client.post("/tutores/novo", data={**RESP, "aviso_privacidade": ""})
    assert "aviso de privacidade".encode() in r.data
    r = client.post("/tutores/novo", data={**RESP, "cpf": "123.456.789-00"})
    assert "CPF inválido".encode() in r.data
    client.post("/tutores/novo", data=RESP)
    r = client.post("/tutores/novo", data=RESP)
    assert "já está cadastrado".encode() in r.data
    with app.app_context():
        assert Responsavel.query.count() == 1


def test_busca(app, client):
    with app.app_context():
        cadastrar(client)
        for termo in ("mar", "Maria", "silva", "MARIA DA", "529.982.247-25", "(11) 98765-4321", "rex"):
            r = client.post("/busca", data={"q": termo})
            assert b"Maria da Silva" in r.data, termo
        for termo in ("joao", "11122233344", "ria"):
            r = client.post("/busca", data={"q": termo})
            assert b"Maria da Silva" not in r.data, termo


def test_fluxo_completo(app, client):
    with app.app_context():
        rid, aid = cadastrar(client)
        assert "segunda a sexta".encode() in agendar(client, rid, aid, proxima(5)).data
        assert "08:00 às 16:00".encode() in agendar(client, rid, aid, proxima(0, 17)).data
        assert Agendamento.query.count() == 0
        seg = proxima(0, 9, 30)
        assert agendar(client, rid, aid, seg, observacao="Vacina anual", tipo="Vacinação").status_code == 302
        ag = Agendamento.query.one()
        r = client.get(f"/agenda/?data={seg.date().isoformat()}")
        for txt in ("Maria da Silva", "Rex", "(11) 98765-4321", "Vacina anual", "09:30"):
            assert txt.encode() in r.data
        assert client.get(f"/agenda/semana?data={seg.date().isoformat()}").status_code == 200
        # check-in
        client.post(f"/agenda/{ag.id}/acao", data={"acao": "chegou"})
        assert db.session.get(Agendamento, ag.id).status == "aguardando"
        # recepção não acessa prontuário nem receitas
        assert client.get(f"/pacientes/{aid}/atendimento").status_code == 403
        assert client.get(f"/pacientes/{aid}/receita").status_code == 403
        assert client.post(f"/agenda/{ag.id}/iniciar").status_code == 403

        entrar(client, "vet")
        r = client.post(f"/agenda/{ag.id}/iniciar")
        assert r.status_code == 302 and db.session.get(Agendamento, ag.id).status == "em_atendimento"
        r = client.post(f"/pacientes/{aid}/atendimento", data={
            "agendamento_id": ag.id, "tipo": "Vacinação", "queixa": "Vacina anual",
            "exame_fisico": "Animal saudável.", "peso_kg": "12,5", "temperatura": "38,6",
            "freq_cardiaca": "100", "mucosas": "Normocoradas", "acao": "receita"})
        assert r.status_code == 302 and "/receita" in r.location
        c = Consulta.query.one()
        assert db.session.get(Agendamento, ag.id).status == "finalizado"
        assert str(db.session.get(Animal, aid).peso_kg) == "12.50"
        client.post(f"/atendimentos/{c.id}/complemento", data={"texto": "Retorno em 30 dias."})
        r = client.post(f"/pacientes/{aid}/receita?consulta_id={c.id}", data={
            "tipo": "controle_especial",
            "medicamento": ["Amoxicilina", ""], "concentracao": ["250 mg", ""], "quantidade": ["", ""],
            "via": ["Oral", ""], "posologia": ["1 comprimido a cada 12h", ""], "duracao": ["7 dias", ""]})
        assert r.status_code == 302
        rec = Receita.query.one()
        assert rec.consulta_id == c.id and len(rec.itens) == 1
        r = client.get(f"/pacientes/{aid}")
        for txt in ("Animal saudável.", "Retorno em 30 dias.", "Amoxicilina", "1 comprimido a cada 12h", "12,5 kg"):
            assert txt.encode() in r.data, txt
        r = client.get(f"/receitas/{rec.id}")
        assert b"CRMV SP-1" in r.data and "2ª via".encode() in r.data
        r = client.get(f"/pacientes/{aid}/receita?repetir={rec.id}")
        assert b'value="Amoxicilina"' in r.data
        assert client.post(f"/atendimentos/{c.id}/editar").status_code == 404

        # recepção vê a ficha mas não o conteúdo clínico
        entrar(client, "recep")
        r = client.get(f"/pacientes/{aid}")
        assert r.status_code == 200 and b"Amoxicilina" not in r.data and "saudável".encode() not in r.data

        acoes = {(a.acao, a.entidade) for a in Auditoria.query}
        for esperado in (("criar", "tutor"), ("criar", "paciente"), ("criar", "agendamento"),
                         ("criar", "atendimento"), ("criar", "complemento"), ("criar", "receita"),
                         ("visualizar_prontuario", "paciente"), ("status", "agendamento")):
            assert esperado in acoes, esperado


def test_edicao_gera_historico(app, client):
    with app.app_context():
        rid, aid = cadastrar(client)
        client.post(f"/tutores/{rid}/editar", data={**RESP, "telefone": "(11) 91234-5678"})
        log = Auditoria.query.filter_by(entidade="tutor", acao="editar").one()
        assert log.detalhes_dict["telefone"] == {"de": "11987654321", "para": "11912345678"}
        assert b"11912345678" in client.get(f"/tutores/{rid}/historico").data
        r = client.post("/busca", data={"q": "(11) 91234-5678"})
        assert b"Maria da Silva" in r.data


def test_agendar_paciente_de_outro_tutor(app, client):
    with app.app_context():
        rid, aid = cadastrar(client)
        client.post("/tutores/novo", data={**RESP, "cpf": "111.444.777-35", "nome": "João Souza"})
        rid2 = [r.id for r in Responsavel.query if r.nome == "João Souza"][0]
        client.post(f"/pacientes/novo?responsavel_id={rid2}", data={**ANIMAL, "nome": "Mimi"})
        r = agendar(client, rid2, aid, proxima(0))
        assert "Selecione o paciente".encode() in r.data
        assert Agendamento.query.count() == 0


def test_lgpd_exportar_e_anonimizar(app, client):
    with app.app_context():
        rid, aid = cadastrar(client)
        assert client.get(f"/tutores/{rid}/dados-pessoais").status_code == 403
        entrar(client, "admin")
        r = client.get(f"/tutores/{rid}/dados-pessoais")
        dados = json.loads(r.data)
        assert dados["titular"]["cpf"] == "52998224725" and dados["animais"][0]["nome"] == "Rex"
        r = client.post(f"/tutores/{rid}/anonimizar", data={"confirmacao": "ANONIMIZAR", "senha": "errada"})
        assert db.session.get(Responsavel, rid).anonimizado_em is None
        from tests.conftest import SENHA
        client.post(f"/tutores/{rid}/anonimizar", data={"confirmacao": "ANONIMIZAR", "senha": SENHA})
        db.session.expire_all()
        r_ = db.session.get(Responsavel, rid)
        assert r_.anonimizado_em and r_.nome == "Titular anonimizado" and r_.cpf == "0"
        assert b"Maria da Silva" not in client.post("/busca", data={"q": "Maria"}).data
        assert client.get(f"/tutores/{rid}").status_code == 404
        assert Animal.query.count() == 1  # prontuário mantido
        # CPF liberado para novo cadastro
        entrar(client, "recep")
        assert client.post("/tutores/novo", data=RESP).status_code == 302


def test_admin_paginas_e_permissoes(app, client):
    entrar(client, "admin")
    for url in ("/admin/usuarios", "/admin/auditoria", "/admin/auditoria?verificar=1", "/admin/lgpd",
                "/admin/usuarios/novo", "/conta/meus-acessos", "/privacidade"):
        assert client.get(url).status_code == 200, url
    entrar(client, "recep")
    assert client.get("/admin/usuarios").status_code == 403
    assert client.get("/admin/auditoria").status_code == 403
