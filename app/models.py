import json

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, login_manager
from .utils import agora

PERFIS = {
    "admin": "Administrador",
    "recepcao": "Recepção",
    "veterinaria": "Veterinária",
}

STATUS_AGENDAMENTO = {
    "agendado": "Agendado",
    "realizado": "Realizado",
    "faltou": "Não compareceu",
    "cancelado": "Cancelado",
}


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    login = db.Column(db.String(60), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    perfil = db.Column(db.String(20), nullable=False)
    crmv = db.Column(db.String(30))  # para receitas emitidas pela veterinária
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    criado_em = db.Column(db.DateTime, default=agora, nullable=False)

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

    @property
    def is_active(self):
        return self.ativo

    @property
    def perfil_nome(self):
        return PERFIS.get(self.perfil, self.perfil)

    def tem_perfil(self, *perfis):
        return self.perfil == "admin" or self.perfil in perfis


@login_manager.user_loader
def carregar_usuario(uid):
    return db.session.get(Usuario, int(uid))


class Auditavel:
    criado_em = db.Column(db.DateTime, default=agora, nullable=False)
    atualizado_em = db.Column(db.DateTime, default=agora, onupdate=agora, nullable=False)


class Responsavel(Auditavel, db.Model):
    __tablename__ = "responsaveis"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False, index=True)
    cpf = db.Column(db.String(11), unique=True, nullable=False, index=True)
    telefone = db.Column(db.String(11), nullable=False, index=True)
    cep = db.Column(db.String(8), nullable=False)
    logradouro = db.Column(db.String(150), nullable=False)
    numero = db.Column(db.String(20), nullable=False)
    complemento = db.Column(db.String(80))
    bairro = db.Column(db.String(80), nullable=False)
    cidade = db.Column(db.String(80), nullable=False)
    uf = db.Column(db.String(2), nullable=False)
    ano_cadunico = db.Column(db.Integer, nullable=False)

    animais = db.relationship("Animal", back_populates="responsavel", order_by="Animal.nome")

    CAMPOS = ["nome", "cpf", "telefone", "cep", "logradouro", "numero", "complemento",
              "bairro", "cidade", "uf", "ano_cadunico"]

    @property
    def endereco_completo(self):
        from .utils import formatar_cep
        comp = f", {self.complemento}" if self.complemento else ""
        return (f"{self.logradouro}, {self.numero}{comp} — {self.bairro}, "
                f"{self.cidade}/{self.uf} — CEP {formatar_cep(self.cep)}")


class Animal(Auditavel, db.Model):
    __tablename__ = "animais"
    id = db.Column(db.Integer, primary_key=True)
    responsavel_id = db.Column(db.Integer, db.ForeignKey("responsaveis.id"), nullable=False, index=True)
    nome = db.Column(db.String(100), nullable=False, index=True)
    sexo = db.Column(db.String(1), nullable=False)  # M / F
    especie = db.Column(db.String(40), nullable=False)
    raca = db.Column(db.String(80), nullable=False)
    idade_anos = db.Column(db.Integer, nullable=False, default=0)
    idade_meses = db.Column(db.Integer, nullable=False, default=0)
    idade_referencia = db.Column(db.Date, nullable=False)  # data em que a idade foi informada
    castrado = db.Column(db.Boolean, nullable=False, default=False)
    # Informações clínicas (preenchidas pela Veterinária)
    peso_kg = db.Column(db.Numeric(6, 2))
    pelagem = db.Column(db.String(80))
    alergias = db.Column(db.Text)
    condicoes_cronicas = db.Column(db.Text)
    observacoes_clinicas = db.Column(db.Text)
    obito = db.Column(db.Boolean, nullable=False, default=False)

    responsavel = db.relationship("Responsavel", back_populates="animais")
    consultas = db.relationship("Consulta", back_populates="animal",
                                order_by="Consulta.data_hora.desc()")
    receitas = db.relationship("Receita", back_populates="animal",
                               order_by="Receita.emitida_em.desc()")

    CAMPOS_CADASTRO = ["nome", "sexo", "especie", "raca", "idade_anos", "idade_meses",
                       "idade_referencia", "castrado", "responsavel_id"]
    CAMPOS_CLINICOS = ["peso_kg", "pelagem", "alergias", "condicoes_cronicas",
                       "observacoes_clinicas", "obito"]

    @property
    def sexo_nome(self):
        return {"M": "Macho", "F": "Fêmea"}.get(self.sexo, self.sexo)


class Agendamento(db.Model):
    __tablename__ = "agendamentos"
    id = db.Column(db.Integer, primary_key=True)
    responsavel_id = db.Column(db.Integer, db.ForeignKey("responsaveis.id"), nullable=False)
    animal_id = db.Column(db.Integer, db.ForeignKey("animais.id"), nullable=False, index=True)
    data_hora = db.Column(db.DateTime, nullable=False, index=True)
    observacao = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="agendado")
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    criado_em = db.Column(db.DateTime, default=agora, nullable=False)

    responsavel = db.relationship("Responsavel")
    animal = db.relationship("Animal")
    criado_por = db.relationship("Usuario")

    @property
    def status_nome(self):
        return STATUS_AGENDAMENTO.get(self.status, self.status)


class Consulta(db.Model):
    """Anotação de consulta. Imutável: só pode ser complementada com adendos (RNF05)."""
    __tablename__ = "consultas"
    id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("animais.id"), nullable=False, index=True)
    veterinario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    agendamento_id = db.Column(db.Integer, db.ForeignKey("agendamentos.id"))
    data_hora = db.Column(db.DateTime, default=agora, nullable=False, index=True)
    peso_kg = db.Column(db.Numeric(6, 2))
    temperatura = db.Column(db.Numeric(4, 1))
    motivo = db.Column(db.String(200))
    anotacao = db.Column(db.Text, nullable=False)

    animal = db.relationship("Animal", back_populates="consultas")
    veterinario = db.relationship("Usuario")
    adendos = db.relationship("Adendo", back_populates="consulta", order_by="Adendo.criado_em")


class Adendo(db.Model):
    __tablename__ = "adendos"
    id = db.Column(db.Integer, primary_key=True)
    consulta_id = db.Column(db.Integer, db.ForeignKey("consultas.id"), nullable=False, index=True)
    autor_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    texto = db.Column(db.Text, nullable=False)
    criado_em = db.Column(db.DateTime, default=agora, nullable=False)

    consulta = db.relationship("Consulta", back_populates="adendos")
    autor = db.relationship("Usuario")


class Receita(db.Model):
    """Receita médica. Imutável após emissão (RNF05)."""
    __tablename__ = "receitas"
    id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("animais.id"), nullable=False, index=True)
    veterinario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    consulta_id = db.Column(db.Integer, db.ForeignKey("consultas.id"))
    emitida_em = db.Column(db.DateTime, default=agora, nullable=False, index=True)
    orientacoes = db.Column(db.Text)

    animal = db.relationship("Animal", back_populates="receitas")
    veterinario = db.relationship("Usuario")
    itens = db.relationship("ReceitaItem", back_populates="receita", order_by="ReceitaItem.id")


class ReceitaItem(db.Model):
    __tablename__ = "receita_itens"
    id = db.Column(db.Integer, primary_key=True)
    receita_id = db.Column(db.Integer, db.ForeignKey("receitas.id"), nullable=False, index=True)
    medicamento = db.Column(db.String(150), nullable=False, index=True)
    concentracao = db.Column(db.String(80))
    quantidade = db.Column(db.String(80))
    via = db.Column(db.String(40))
    posologia = db.Column(db.String(300), nullable=False)
    duracao = db.Column(db.String(80))

    receita = db.relationship("Receita", back_populates="itens")


class Auditoria(db.Model):
    """Registro de auditoria (RNF04): quem fez o quê, quando."""
    __tablename__ = "auditoria"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    acao = db.Column(db.String(30), nullable=False)
    entidade = db.Column(db.String(40), nullable=False, index=True)
    entidade_id = db.Column(db.Integer, index=True)
    detalhes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=agora, nullable=False, index=True)

    usuario = db.relationship("Usuario")

    @property
    def detalhes_dict(self):
        try:
            return json.loads(self.detalhes) if self.detalhes else {}
        except ValueError:
            return {}
