"""Gera o DDL das tabelas (PostgreSQL) a partir dos modelos, no schema `ambpet`.

Uso: python scripts/gerar_migracao.py > supabase/migrations/arquivo.sql
(o arquivo versionado já inclui este DDL; use ao evoluir o modelo como base
para escrever o ALTER TABLE correspondente).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

from app import db  # noqa: E402
import app.models  # noqa: E402,F401

SCHEMA = os.environ.get("DB_SCHEMA", "ambpet")
dialeto = postgresql.dialect()
mapa = {None: SCHEMA}



def ddl(elemento):
    sql = str(elemento.compile(dialect=dialeto, schema_translate_map=mapa)).strip()
    return sql.replace("__[SCHEMA__none]", SCHEMA).replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ") \
              .replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ") + ";"


for tabela in db.metadata.sorted_tables:
    print(ddl(CreateTable(tabela)))
    for indice in sorted(tabela.indexes, key=lambda i: i.name):
        print(ddl(CreateIndex(indice)))
    print()
