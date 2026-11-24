"""Modelo de dados.

Dados pessoais do tutor e todo o conteúdo clínico ficam cifrados (AES-256-GCM)
via coluna `Criptografado`. Para busca e unicidade usam-se índices cegos (HMAC).
"""
import json

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, login_manager
from .crypto import Criptografado, chaveiro
from .utils import agora, formatar_cep

PERFIS = {
    "admin": "Administrador",
    "recepcao": "Recepção",
    "veterinaria": "Veterinária",
}

STATUS_AGENDAMENTO = {
    "agendado": "Agendado",
    "confirmado": "Confirmado",
    "aguardando": "Na sala de espera",
    "em_atendimento": "Em atendimento",
    "finalizado": "Finalizado",
    "faltou": "Não compareceu",
    "cancelado": "Cancelado",
}
STATUS_ATIVOS = ("agendado", "confirmado", "aguardando", "em_atendimento")

TIPOS_AGENDAMENTO = ["Consulta", "Retorno", "Vacinação", "Exame", "Procedimento"]


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    login = db.Column(db.String(60), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    perfil = db.Column(db.String(20), nullable=False)
    crmv = db.Column(db.String(30))
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    criado_em = db.Column(db.DateTime, default=agora, nullable=False)
    senha_alterada_em = db.Column(db.DateTime, default=agora, nullable=False)
    trocar_senha = db.Column(db.Boolean, default=True, nullable=False)
    ultimo_login_em = db.Column(db.DateTime)
    falhas_login = db.Column(db.Integer, default=0, nullable=False)
    bloqueado_ate = db.Column(db.DateTime)
    sessao_versao = db.Column(db.Integer, default=1, nullable=False)
    totp_segredo = db.Column(Criptografado("usuarios.totp_segredo"))
    totp_ativo = db.Column(db.Boolean, default=False, nullable=False)
    totp_ultimo_passo = db.Column(db.BigInteger)

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha, method="scrypt")
        self.senha_alterada_em = agora()
        self.sessao_versao = (self.sessao_versao or 0) + 1  # derruba outras sessões

    def verificar_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

    def get_id(self):
        # a versão faz sessões antigas expirarem ao trocar senha/2FA ou desativar o usuário
        return f"{self.id}:{self.sessao_versao}"

    @property
    def is_active(self):
        return self.ativo

    @property
    def perfil_nome(self):
        return PERFIS.get(self.perfil, self.perfil)

    @property
    def iniciais(self):
        partes = self.nome.split()
        return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper()

    def tem_perfil(self, *perfis):
        return self.perfil == "admin" or self.perfil in perfis


@login_manager.user_loader
def carregar_usuario(ident):
    uid, _, versao = (ident or "").partition(":")
    if not uid.isdigit() or not versao.isdigit():
        return None
    u = db.session.get(Usuario, int(uid))
    if u and u.ativo and u.sessao_versao == int(versao):
        return u
    return None


class Responsavel(db.Model):
    """Tutor (responsável pelo animal). Todos os dados pessoais são cifrados."""
    __tablename__ = "tutores"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(Criptografado("tutores.nome"), nullable=False)
    cpf = db.Column(Criptografado("tutores.cpf"), nullable=False)
    cpf_hash = db.Column(db.String(64), unique=True, nullable=False)
    telefone = db.Column(Criptografado("tutores.telefone"), nullable=False)
    telefone_hash = db.Column(db.String(64), nullable=False, index=True)
    cep = db.Column(Criptografado("tutores.cep"), nullable=False)
    logradouro = db.Column(Criptografado("tutores.logradouro"), nullable=False)
    numero = db.Column(Criptografado("tutores.numero"), nullable=False)
    complemento = db.Column(Criptografado("tutores.complemento"))
    bairro = db.Column(Criptografado("tutores.bairro"), nullable=False)
    cidade = db.Column(Criptografado("tutores.cidade"), nullable=False)
    uf = db.Column(Criptografado("tutores.uf"), nullable=False)
    ano_cadunico = db.Column(Criptografado("tutores.ano_cadunico"), nullable=False)
    aviso_privacidade_versao = db.Column(db.String(20), nullable=False)
    aviso_privacidade_em = db.Column(db.DateTime, nullable=False)
    anonimizado_em = db.Column(db.DateTime)
    criado_em = db.Column(db.DateTime, default=agora, nullable=False, index=True)
    atualizado_em = db.Column(db.DateTime, default=agora, onupdate=agora, nullable=False)

    animais = db.relationship("Animal", back_populates="responsavel", order_by="Animal.nome")

    CAMPOS = ["nome", "cpf", "telefone", "cep", "logradouro", "numero", "complemento",
              "bairro", "cidade", "uf", "ano_cadunico"]

    def atualizar_indices(self):
        from .utils import so_digitos
        self.cpf_hash = chaveiro.hash(so_digitos(self.cpf), "cpf")
        self.telefone_hash = chaveiro.hash(so_digitos(self.telefone), "telefone")

    @property
    def endereco_completo(self):
        if self.anonimizado_em:
            return "—"
        comp = f", {self.complemento}" if self.complemento else ""
        return (f"{self.logradouro}, {self.numero}{comp} — {self.bairro}, "
                f"{self.cidade}/{self.uf} — CEP {formatar_cep(self.cep)}")

    @property
    def cpf_mascarado(self):
        from .utils import so_digitos
        c = so_digitos(self.cpf)
        return f"***.{c[3:6]}.{c[6:9]}-**" if len(c) == 11 else "—"


class IndiceBusca(db.Model):
    """Tokens HMAC de prefixos do nome do tutor: busca sem guardar o nome em claro."""
    __tablename__ = "indice_busca"
    id = db.Column(db.Integer, primary_key=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False, index=True)
    token = db.Column(db.String(32), nullable=False, index=True)


class Animal(db.Model):
    """Paciente. Dados do animal em claro; informações clínicas cifradas."""
    __tablename__ = "pacientes"
    id = db.Column(db.Integer, primary_key=True)
    responsavel_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False, index=True)
    nome = db.Column(db.String(100), nullable=False, index=True)
    sexo = db.Column(db.String(1), nullable=False)
    especie = db.Column(db.String(40), nullable=False)
    raca = db.Column(db.String(80), nullable=False)
    idade_anos = db.Column(db.Integer, nullable=False, default=0)
    idade_meses = db.Column(db.Integer, nullable=False, default=0)
    idade_referencia = db.Column(db.Date, nullable=False)
    castrado = db.Column(db.Boolean, nullable=False, default=False)
    pelagem = db.Column(db.String(80))
    peso_kg = db.Column(db.Numeric(6, 2))
    alergias = db.Column(Criptografado("pacientes.alergias"))
    condicoes_cronicas = db.Column(Criptografado("pacientes.condicoes_cronicas"))
    observacoes_clinicas = db.Column(Criptografado("pacientes.observacoes_clinicas"))
    obito = db.Column(db.Boolean, nullable=False, default=False)
    criado_em = db.Column(db.DateTime, default=agora, nullable=False)
    atualizado_em = db.Column(db.DateTime, default=agora, onupdate=agora, nullable=False)

    responsavel = db.relationship("Responsavel", back_populates="animais")
    consultas = db.relationship("Consulta", back_populates="animal",
                                order_by="Consulta.data_hora.desc()")
    receitas = db.relationship("Receita", back_populates="animal",
                               order_by="Receita.emitida_em.desc()")

    CAMPOS_CADASTRO = ["nome", "sexo", "especie", "raca", "idade_anos", "idade_meses",
                       "idade_referencia", "castrado"]
    CAMPOS_CLINICOS = ["peso_kg", "pelagem", "alergias", "condicoes_cronicas",
                       "observacoes_clinicas", "obito"]

    @property
    def sexo_nome(self):
        return {"M": "Macho", "F": "Fêmea"}.get(self.sexo, self.sexo)


class Agendamento(db.Model):
    __tablename__ = "agendamentos"
    id = db.Column(db.Integer, primary_key=True)
    responsavel_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False, index=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("pacientes.id"), nullable=False, index=True)
    data_hora = db.Column(db.DateTime, nullable=False, index=True)
    tipo = db.Column(db.String(30), nullable=False, default="Consulta")
    observacao = db.Column(Criptografado("agendamentos.observacao"))
    status = db.Column(db.String(20), nullable=False, default="agendado")
    chegada_em = db.Column(db.DateTime)
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    criado_em = db.Column(db.DateTime, default=agora, nullable=False)

    responsavel = db.relationship("Responsavel")
    animal = db.relationship("Animal")
    criado_por = db.relationship("Usuario")

    @property
    def status_nome(self):
        return STATUS_AGENDAMENTO.get(self.status, self.status)

    @property
    def ativo(self):
        return self.status in STATUS_ATIVOS


class Consulta(db.Model):
    """Registro de atendimento (prontuário, formato SOAP). Imutável (RNF05)."""
    __tablename__ = "atendimentos"
    id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("pacientes.id"), nullable=False, index=True)
    veterinario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    agendamento_id = db.Column(db.Integer, db.ForeignKey("agendamentos.id"))
    data_hora = db.Column(db.DateTime, default=agora, nullable=False, index=True)
    tipo = db.Column(db.String(30), nullable=False, default="Consulta")
    # Sinais vitais
    peso_kg = db.Column(db.Numeric(6, 2))
    temperatura = db.Column(db.Numeric(4, 1))
    freq_cardiaca = db.Column(db.Integer)
    freq_respiratoria = db.Column(db.Integer)
    mucosas = db.Column(db.String(30))
    hidratacao = db.Column(db.String(30))
    tpc = db.Column(db.String(10))
    # SOAP (cifrado)
    queixa = db.Column(Criptografado("atendimentos.queixa"))
    anamnese = db.Column(Criptografado("atendimentos.anamnese"))
    exame_fisico = db.Column(Criptografado("atendimentos.exame_fisico"))
    diagnostico = db.Column(Criptografado("atendimentos.diagnostico"))
    conduta = db.Column(Criptografado("atendimentos.conduta"))

    animal = db.relationship("Animal", back_populates="consultas")
    veterinario = db.relationship("Usuario")
    adendos = db.relationship("Adendo", back_populates="consulta", order_by="Adendo.criado_em")
    receitas = db.relationship("Receita", back_populates="consulta")


class Adendo(db.Model):
    __tablename__ = "adendos"
    id = db.Column(db.Integer, primary_key=True)
    consulta_id = db.Column(db.Integer, db.ForeignKey("atendimentos.id"), nullable=False, index=True)
    autor_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    texto = db.Column(Criptografado("adendos.texto"), nullable=False)
    criado_em = db.Column(db.DateTime, default=agora, nullable=False)

    consulta = db.relationship("Consulta", back_populates="adendos")
    autor = db.relationship("Usuario")


TIPOS_RECEITA = {"simples": "Receita simples", "controle_especial": "Controle especial (2 vias)"}


class Receita(db.Model):
    """Receita. Imutável após emissão (RNF05)."""
    __tablename__ = "receitas"
    id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("pacientes.id"), nullable=False, index=True)
    veterinario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    consulta_id = db.Column(db.Integer, db.ForeignKey("atendimentos.id"))
    tipo = db.Column(db.String(20), nullable=False, default="simples")
    emitida_em = db.Column(db.DateTime, default=agora, nullable=False, index=True)
    orientacoes = db.Column(Criptografado("receitas.orientacoes"))

    animal = db.relationship("Animal", back_populates="receitas")
    veterinario = db.relationship("Usuario")
    consulta = db.relationship("Consulta", back_populates="receitas")
    itens = db.relationship("ReceitaItem", back_populates="receita", order_by="ReceitaItem.id")

    @property
    def tipo_nome(self):
        return TIPOS_RECEITA.get(self.tipo, self.tipo)


class ReceitaItem(db.Model):
    __tablename__ = "receita_itens"
    id = db.Column(db.Integer, primary_key=True)
    receita_id = db.Column(db.Integer, db.ForeignKey("receitas.id"), nullable=False, index=True)
    medicamento = db.Column(Criptografado("receita_itens.medicamento"), nullable=False)
    concentracao = db.Column(Criptografado("receita_itens.concentracao"))
    quantidade = db.Column(Criptografado("receita_itens.quantidade"))
    via = db.Column(db.String(40))
    posologia = db.Column(Criptografado("receita_itens.posologia"), nullable=False)
    duracao = db.Column(Criptografado("receita_itens.duracao"))

    receita = db.relationship("Receita", back_populates="itens")

    CAMPOS = ["medicamento", "concentracao", "quantidade", "via", "posologia", "duracao"]


class Auditoria(db.Model):
    """Trilha de auditoria (RNF04 / LGPD art. 37). Somente inserção, encadeada por HMAC."""
    __tablename__ = "auditoria"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    acao = db.Column(db.String(30), nullable=False)
    entidade = db.Column(db.String(40), nullable=False, index=True)
    entidade_id = db.Column(db.Integer, index=True)
    detalhes = db.Column(Criptografado("auditoria.detalhes"))
    ip = db.Column(Criptografado("auditoria.ip"))
    criado_em = db.Column(db.DateTime, default=agora, nullable=False, index=True)
    hash_anterior = db.Column(db.String(64), nullable=False)
    hash = db.Column(db.String(64), nullable=False)

    usuario = db.relationship("Usuario")

    @property
    def detalhes_dict(self):
        try:
            return json.loads(self.detalhes) if self.detalhes else {}
        except ValueError:
            return {}
