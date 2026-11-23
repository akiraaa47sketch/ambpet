import getpass
import os

import click
from sqlalchemy import text
from sqlalchemy.orm.attributes import flag_modified

from . import db
from .crypto import Criptografado, nova_chave
from .models import PERFIS, Usuario


def register_cli(app):
    @app.cli.command("criar-usuario")
    @click.option("--login", prompt=True)
    @click.option("--nome", prompt=True)
    @click.option("--perfil", type=click.Choice(list(PERFIS)), prompt=True, default="admin")
    @click.option("--crmv", default="")
    def criar_usuario(login, nome, perfil, crmv):
        """Cria um usuário (use para criar o primeiro administrador)."""
        from .seguranca import validar_senha
        login = login.strip().lower()
        if Usuario.query.filter_by(login=login).first():
            raise click.ClickException("Login já existe.")
        senha = os.environ.get("NOVA_SENHA") or getpass.getpass("Senha: ")
        erro = validar_senha(senha, login, nome)
        if erro:
            raise click.ClickException(erro)
        u = Usuario(login=login, nome=nome, perfil=perfil, crmv=crmv or None)
        u.definir_senha(senha)
        u.trocar_senha = False
        db.session.add(u)
        db.session.commit()
        click.echo(f"Usuário '{login}' ({PERFIS[perfil]}) criado.")

    @app.cli.command("gerar-chave")
    def gerar_chave():
        """Gera uma nova chave AES-256 (para ENCRYPTION_KEYS / BLIND_INDEX_KEY)."""
        click.echo(nova_chave())

    @app.cli.command("verificar-auditoria")
    def verificar_auditoria():
        """Confere a integridade da cadeia de auditoria."""
        from .audit import verificar_cadeia
        ok, rid, total = verificar_cadeia()
        if ok:
            click.echo(f"Íntegra: {total} registros.")
        else:
            raise click.ClickException(f"Cadeia quebrada no registro {rid}.")

    @app.cli.command("rotacionar-chaves")
    @click.option("--confirmar", is_flag=True)
    def rotacionar_chaves(confirmar):
        """Recifra todos os campos com a chave ativa (ENCRYPTION_ACTIVE_KEY).

        Rode com a conexão de administração (dono das tabelas), pois tabelas
        imutáveis exigem a sessão de manutenção."""
        if not confirmar:
            raise click.ClickException("Faça backup antes e rode novamente com --confirmar.")
        if db.engine.dialect.name == "postgresql":
            db.session.execute(text("set local ambpet.manutencao = 'on'"))
        total = 0
        for mapper in db.Model.registry.mappers:
            modelo = mapper.class_
            cols = [c.key for c in mapper.columns if isinstance(c.type, Criptografado)]
            if not cols:
                continue
            for obj in modelo.query.yield_per(200):
                for c in cols:
                    if getattr(obj, c) is not None:
                        flag_modified(obj, c)
                total += 1
        db.session.commit()
        click.echo(f"{total} registros recifrados com a chave ativa.")
