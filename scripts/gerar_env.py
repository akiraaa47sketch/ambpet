"""Gera um arquivo .env com segredos aleatórios fortes.

Uso:  python scripts/gerar_env.py            (cria .env para desenvolvimento)
      python scripts/gerar_env.py --producao (imprime os segredos na tela)

O .env está no .gitignore: NUNCA faça commit dele. Em produção, cadastre os
valores no gerenciador de segredos da hospedagem (variáveis de ambiente).
Guarde ENCRYPTION_KEYS e BLIND_INDEX_KEY em local seguro (cofre de senhas):
sem elas os dados criptografados não podem ser recuperados.
"""
import base64
import os
import secrets
import sys


def chave():
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def main():
    producao = "--producao" in sys.argv
    valores = {
        "SECRET_KEY": secrets.token_urlsafe(48),
        "ENCRYPTION_KEYS": f"v1:{chave()}",
        "ENCRYPTION_ACTIVE_KEY": "v1",
        "BLIND_INDEX_KEY": chave(),
    }
    if producao:
        for k, v in valores.items():
            print(f"{k}={v}")
        return
    if os.path.exists(".env"):
        sys.exit(".env já existe — não vou sobrescrever (as chaves atuais decifram seus dados).")
    linhas = [
        "# Gerado por scripts/gerar_env.py — NÃO versionar",
        "APP_ENV=development",
        "DATABASE_URL=sqlite:///instance/ambpet-dev.db",
        "EXIGIR_2FA=0",
        *(f"{k}={v}" for k, v in valores.items()),
        "CLINICA_NOME=Clínica Veterinária",
    ]
    fd = os.open(".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(linhas) + "\n")
    print(".env criado (permissão 600).")


if __name__ == "__main__":
    main()
