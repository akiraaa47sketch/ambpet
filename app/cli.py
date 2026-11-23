import getpass
import os

import click
from sqlalchemy.engine import make_url

from . import db
from .models import PERFIS, Usuario
from .utils import agora


def register_cli(app):
    @app.cli.command("criar-usuario")
    @click.option("--login", prompt=True)
    @click.option("--nome", prompt=True)
    @click.option("--perfil", type=click.Choice(list(PERFIS)), prompt=True, default="admin")
    @click.option("--crmv", default="")
    def criar_usuario(login, nome, perfil, crmv):
        """Cria um usuário (use para criar o primeiro administrador)."""
        login = login.strip().lower()
        if Usuario.query.filter_by(login=login).first():
            raise click.ClickException("Login já existe.")
        senha = os.environ.get("NOVA_SENHA") or getpass.getpass("Senha (mín. 8): ")
        if len(senha) < 8:
            raise click.ClickException("Senha muito curta.")
        u = Usuario(login=login, nome=nome, perfil=perfil, crmv=crmv or None)
        u.definir_senha(senha)
        db.session.add(u)
        db.session.commit()
        click.echo(f"Usuário '{login}' ({PERFIS[perfil]}) criado.")

    @app.cli.command("backup")
    def backup():
        """Copia o banco SQLite para a pasta de backups (agende no cron)."""
        url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
        if url.get_backend_name() != "sqlite":
            raise click.ClickException("Para PostgreSQL use pg_dump (ver README).")
        destino_dir = os.path.abspath(app.config["BACKUP_DIR"])
        os.makedirs(destino_dir, exist_ok=True)
        destino = os.path.join(destino_dir, f"ambpet-{agora():%Y%m%d-%H%M%S}.db")
        import sqlite3
        src = sqlite3.connect(url.database)
        dst = sqlite3.connect(destino)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        click.echo(f"Backup salvo em {destino}")
