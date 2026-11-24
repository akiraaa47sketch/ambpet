"""Gera o arquivo .env com segredos aleatórios fortes.

Uso:
  python scripts/gerar_env.py                      .env de desenvolvimento (SQLite)
  python scripts/gerar_env.py --supabase <URL|REF>  .env de produção ligado ao Supabase
  python scripts/gerar_env.py --producao            só imprime os segredos na tela

O .env está no .gitignore: NUNCA faça commit dele nem cole o conteúdo em chats.
Guarde ENCRYPTION_KEYS e BLIND_INDEX_KEY em local seguro (cofre de senhas):
sem elas os dados criptografados não podem ser recuperados.
"""
import base64
import getpass
import os
import re
import secrets
import string
import sys
from urllib.parse import quote


def chave():
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def senha_banco():
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(32))


def segredos():
    return {
        "SECRET_KEY": secrets.token_urlsafe(48),
        "ENCRYPTION_KEYS": f"v1:{chave()}",
        "ENCRYPTION_ACTIVE_KEY": "v1",
        "BLIND_INDEX_KEY": chave(),
    }


def gravar(linhas):
    if os.path.exists(".env"):
        sys.exit(".env já existe — não vou sobrescrever (as chaves atuais decifram seus dados).\n"
                 "Se ainda não há dados no banco, apague o .env e rode de novo.")
    fd = os.open(".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(linhas) + "\n")


def ref_do_projeto(valor):
    m = re.search(r"([a-z0-9]{20})(?:\.supabase\.co)?", valor or "")
    if not m:
        sys.exit("Informe a URL do projeto (https://<ref>.supabase.co) ou o ref de 20 caracteres.")
    return m.group(1)


def supabase(valor):
    ref = ref_do_projeto(valor)
    print(f"Projeto Supabase: {ref}\n")
    print("Host do pooler: no painel do Supabase clique em 'Connect' > 'Session pooler'")
    print("e copie só o host (ex.: aws-0-sa-east-1.pooler.supabase.com).")
    host = input("Host do pooler [deixe vazio para preencher depois]: ").strip()
    senha = getpass.getpass("Senha do papel ambpet_app [Enter = gerar uma forte]: ").strip()
    gerada = not senha
    if gerada:
        senha = senha_banco()
    host = host or "COLOQUE_O_HOST_DO_POOLER_AQUI"
    url = f"postgresql://ambpet_app.{ref}:{quote(senha, safe='')}@{host}:5432/postgres"

    nome = input("Nome da clínica [Clínica Veterinária]: ").strip() or "Clínica Veterinária"
    linhas = [
        "# Gerado por scripts/gerar_env.py — NÃO versionar, NÃO compartilhar",
        "APP_ENV=production",
        "",
        "# --- Banco (Supabase) ---",
        f"DATABASE_URL={url}",
        "DB_SCHEMA=ambpet",
        "# Caminho do certificado CA baixado em Database Settings > SSL (ativa verify-full)",
        "DB_SSLROOTCERT=",
        "",
        "# --- Segredos da aplicação (guarde uma cópia em um cofre de senhas) ---",
        *(f"{k}={v}" for k, v in segredos().items()),
        "",
        "# --- Segurança ---",
        "EXIGIR_2FA=1",
        "SESSAO_INATIVIDADE_MIN=30",
        "SESSAO_MAX_HORAS=10",
        "LOGIN_MAX_TENTATIVAS=5",
        "LOGIN_BLOQUEIO_MIN=15",
        "BEHIND_PROXY=1",
        "USAR_VIACEP=1",
        "",
        "# --- Clínica / LGPD ---",
        f"CLINICA_NOME={nome}",
        "CLINICA_ENDERECO=",
        "CLINICA_TELEFONE=",
        f"CONTROLADOR_NOME={nome}",
        "CONTROLADOR_CNPJ=",
        "ENCARREGADO_NOME=",
        "ENCARREGADO_EMAIL=",
        "AVISO_PRIVACIDADE_VERSAO=1.0",
        "RETENCAO_PRONTUARIO_ANOS=5",
        "AGENDA_INTERVALO_MIN=30",
    ]
    gravar(linhas)
    print("\n.env criado (permissão 600).")
    if gerada:
        print("\nRode no SQL Editor do Supabase (depois da migração) e não salve este comando:\n")
        print(f"  alter role ambpet_app with login password '{senha}';\n")
    if host.startswith("COLOQUE"):
        print("Falta o host do pooler: edite DATABASE_URL no .env.")
    print("Complete CLINICA_ENDERECO, CLINICA_TELEFONE, CONTROLADOR_CNPJ e ENCARREGADO_* no .env.")


def main():
    args = sys.argv[1:]
    if "--producao" in args:
        for k, v in segredos().items():
            print(f"{k}={v}")
        return
    if "--supabase" in args:
        i = args.index("--supabase")
        supabase(args[i + 1] if i + 1 < len(args) else input("URL do projeto Supabase: "))
        return
    gravar([
        "# Gerado por scripts/gerar_env.py — NÃO versionar",
        "APP_ENV=development",
        "DATABASE_URL=sqlite:///instance/ambpet-dev.db",
        "EXIGIR_2FA=0",
        *(f"{k}={v}" for k, v in segredos().items()),
        "CLINICA_NOME=Clínica Veterinária",
    ])
    print(".env de desenvolvimento criado (permissão 600).")


if __name__ == "__main__":
    main()
