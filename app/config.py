"""Configuração lida exclusivamente de variáveis de ambiente (ou arquivo .env local).

Nenhum segredo fica no código. Em produção (APP_ENV=production, o padrão) o
sistema se recusa a iniciar se faltar algum segredo obrigatório.
"""
import os

from sqlalchemy.engine import make_url


class ErroConfiguracao(RuntimeError):
    pass


def _bool(nome, padrao):
    return os.environ.get(nome, "1" if padrao else "0").strip().lower() in ("1", "true", "sim", "yes")


def carregar(overrides=None):
    overrides = overrides or {}
    if not overrides.get("TESTING"):
        try:
            from dotenv import load_dotenv
            load_dotenv(os.environ.get("ENV_FILE", ".env"), override=False)
        except ImportError:
            pass

    env = os.environ.get("APP_ENV", "production").lower()
    producao = env == "production" and not overrides.get("TESTING")

    cfg = {
        "APP_ENV": env,
        "SECRET_KEY": os.environ.get("SECRET_KEY", ""),
        "SQLALCHEMY_DATABASE_URI": os.environ.get("DATABASE_URL", ""),
        "DB_SCHEMA": os.environ.get("DB_SCHEMA", "ambpet"),
        "DB_SSLROOTCERT": os.environ.get("DB_SSLROOTCERT", ""),
        "ENCRYPTION_KEYS": os.environ.get("ENCRYPTION_KEYS", ""),
        "ENCRYPTION_ACTIVE_KEY": os.environ.get("ENCRYPTION_ACTIVE_KEY", ""),
        "BLIND_INDEX_KEY": os.environ.get("BLIND_INDEX_KEY", ""),
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SESSION_COOKIE_NAME": "__Host-ambpet" if producao else "ambpet",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Strict",
        "SESSION_COOKIE_SECURE": producao or _bool("SESSION_COOKIE_SECURE", False),
        "PERMANENT_SESSION_LIFETIME": int(os.environ.get("SESSAO_MAX_HORAS", "10")) * 3600,
        "SESSAO_INATIVIDADE_MIN": int(os.environ.get("SESSAO_INATIVIDADE_MIN", "30")),
        "EXIGIR_2FA": _bool("EXIGIR_2FA", True),
        "LOGIN_MAX_TENTATIVAS": int(os.environ.get("LOGIN_MAX_TENTATIVAS", "5")),
        "LOGIN_BLOQUEIO_MIN": int(os.environ.get("LOGIN_BLOQUEIO_MIN", "15")),
        "BEHIND_PROXY": _bool("BEHIND_PROXY", False),
        "USAR_VIACEP": _bool("USAR_VIACEP", True),
        "CSRF_ENABLED": True,
        "MAX_CONTENT_LENGTH": 1024 * 1024,
        # Identificação da clínica (receita) e LGPD (aviso de privacidade)
        "CLINICA_NOME": os.environ.get("CLINICA_NOME", "Clínica Veterinária"),
        "CLINICA_ENDERECO": os.environ.get("CLINICA_ENDERECO", ""),
        "CLINICA_TELEFONE": os.environ.get("CLINICA_TELEFONE", ""),
        "CONTROLADOR_NOME": os.environ.get("CONTROLADOR_NOME", os.environ.get("CLINICA_NOME", "")),
        "CONTROLADOR_CNPJ": os.environ.get("CONTROLADOR_CNPJ", ""),
        "ENCARREGADO_NOME": os.environ.get("ENCARREGADO_NOME", ""),
        "ENCARREGADO_EMAIL": os.environ.get("ENCARREGADO_EMAIL", ""),
        "AVISO_PRIVACIDADE_VERSAO": os.environ.get("AVISO_PRIVACIDADE_VERSAO", "1.0"),
        "RETENCAO_PRONTUARIO_ANOS": int(os.environ.get("RETENCAO_PRONTUARIO_ANOS", "5")),
        "AGENDA_INTERVALO_MIN": int(os.environ.get("AGENDA_INTERVALO_MIN", "30")),
        "TESTING": False,
    }
    cfg.update(overrides)
    cfg["PRODUCAO"] = producao

    erros = []
    if len(cfg["SECRET_KEY"]) < 32:
        erros.append("SECRET_KEY ausente ou curta (mín. 32 caracteres).")
    if not cfg["SQLALCHEMY_DATABASE_URI"]:
        erros.append("DATABASE_URL não configurada.")
    elif "COLOQUE_" in cfg["SQLALCHEMY_DATABASE_URI"] or "<" in cfg["SQLALCHEMY_DATABASE_URI"]:
        erros.append("DATABASE_URL ainda tem um campo a preencher (host do pooler ou senha).")
    if not cfg["ENCRYPTION_KEYS"] or not cfg["BLIND_INDEX_KEY"]:
        erros.append("ENCRYPTION_KEYS e BLIND_INDEX_KEY são obrigatórias.")
    if erros:
        raise ErroConfiguracao(
            "Configuração incompleta:\n  - " + "\n  - ".join(erros) +
            "\nGere um .env com: python scripts/gerar_env.py")

    url = make_url(cfg["SQLALCHEMY_DATABASE_URI"])
    backend = url.get_backend_name()
    if producao and backend != "postgresql":
        raise ErroConfiguracao("Em produção use PostgreSQL (Supabase).")

    opcoes = {"pool_pre_ping": True}
    if backend == "postgresql":
        if url.drivername == "postgresql":
            url = url.set(drivername="postgresql+psycopg")
        q = dict(url.query)
        if cfg["DB_SSLROOTCERT"]:
            q["sslmode"] = "verify-full"
            q["sslrootcert"] = cfg["DB_SSLROOTCERT"]
        elif "sslmode" not in q:
            q["sslmode"] = "require"
        if producao and q["sslmode"] in ("disable", "allow", "prefer"):
            raise ErroConfiguracao("Conexão sem TLS não é permitida em produção.")
        url = url.set(query=q)
        cfg["SQLALCHEMY_DATABASE_URI"] = url.render_as_string(hide_password=False)
        opcoes.update(
            pool_size=int(os.environ.get("DB_POOL_SIZE", "5")),
            max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "5")),
            pool_recycle=300,
            # compatível com o pooler do Supabase (Supavisor em modo transação)
            connect_args={"prepare_threshold": None, "application_name": "ambpet"},
            execution_options={"schema_translate_map": {None: cfg["DB_SCHEMA"]}},
        )
    cfg["SQLALCHEMY_ENGINE_OPTIONS"] = {**opcoes, **cfg.get("SQLALCHEMY_ENGINE_OPTIONS", {})}
    return cfg
