-- =============================================================================
-- AMBPET — esquema do banco (Supabase / PostgreSQL 15+)
--
-- Rode UMA vez como usuário "postgres" no SQL Editor do Supabase
-- (ou: psql "$ADMIN_DATABASE_URL" -f este_arquivo.sql).
--
-- Camadas de proteção:
--   1. Schema privado "ambpet" — fora da Data API (PostgREST) do Supabase.
--   2. RLS ligado em todas as tabelas, com política apenas para o papel da app.
--   3. Papel "ambpet_app" de menor privilégio (sem DELETE/UPDATE onde não precisa).
--   4. Prontuário, receitas e auditoria imutáveis por trigger (RNF05 / RNF04).
--   5. Dados pessoais e clínicos já chegam cifrados (AES-256-GCM) pela aplicação;
--      a chave nunca é enviada ao banco.
--
-- Depois de rodar, defina a senha do papel da aplicação (NÃO versione):
--   alter role ambpet_app with login password '<senha-forte-gerada>';
-- =============================================================================

begin;

-- ---------- Papel da aplicação (sem login até a senha ser definida) ----------
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'ambpet_app') then
    create role ambpet_app nologin noinherit nosuperuser nocreatedb nocreaterole nobypassrls noreplication;
  end if;
end $$;
alter role ambpet_app set search_path = ambpet;
alter role ambpet_app set statement_timeout = '15s';
alter role ambpet_app set idle_in_transaction_session_timeout = '60s';
alter role ambpet_app connection limit 30;

-- ---------- Schema privado ----------
create schema if not exists ambpet;
revoke all on schema ambpet from public;
grant usage on schema ambpet to ambpet_app;

-- ---------- Tabelas (gerado por scripts/gerar_migracao.py) ----------
CREATE TABLE IF NOT EXISTS ambpet.tutores (
	id SERIAL NOT NULL, 
	nome TEXT NOT NULL, 
	cpf TEXT NOT NULL, 
	cpf_hash VARCHAR(64) NOT NULL, 
	telefone TEXT NOT NULL, 
	telefone_hash VARCHAR(64) NOT NULL, 
	cep TEXT NOT NULL, 
	logradouro TEXT NOT NULL, 
	numero TEXT NOT NULL, 
	complemento TEXT, 
	bairro TEXT NOT NULL, 
	cidade TEXT NOT NULL, 
	uf TEXT NOT NULL, 
	ano_cadunico TEXT NOT NULL, 
	aviso_privacidade_versao VARCHAR(20) NOT NULL, 
	aviso_privacidade_em TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	anonimizado_em TIMESTAMP WITHOUT TIME ZONE, 
	criado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	atualizado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (cpf_hash)
);
CREATE INDEX IF NOT EXISTS ix_tutores_criado_em ON ambpet.tutores (criado_em);
CREATE INDEX IF NOT EXISTS ix_tutores_telefone_hash ON ambpet.tutores (telefone_hash);

CREATE TABLE IF NOT EXISTS ambpet.usuarios (
	id SERIAL NOT NULL, 
	nome VARCHAR(120) NOT NULL, 
	login VARCHAR(60) NOT NULL, 
	senha_hash VARCHAR(255) NOT NULL, 
	perfil VARCHAR(20) NOT NULL, 
	crmv VARCHAR(30), 
	ativo BOOLEAN NOT NULL, 
	criado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	senha_alterada_em TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	trocar_senha BOOLEAN NOT NULL, 
	ultimo_login_em TIMESTAMP WITHOUT TIME ZONE, 
	falhas_login INTEGER NOT NULL, 
	bloqueado_ate TIMESTAMP WITHOUT TIME ZONE, 
	sessao_versao INTEGER NOT NULL, 
	totp_segredo TEXT, 
	totp_ativo BOOLEAN NOT NULL, 
	totp_ultimo_passo BIGINT, 
	PRIMARY KEY (id), 
	UNIQUE (login)
);

CREATE TABLE IF NOT EXISTS ambpet.auditoria (
	id SERIAL NOT NULL, 
	usuario_id INTEGER, 
	acao VARCHAR(30) NOT NULL, 
	entidade VARCHAR(40) NOT NULL, 
	entidade_id INTEGER, 
	detalhes TEXT, 
	ip TEXT, 
	criado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	hash_anterior VARCHAR(64) NOT NULL, 
	hash VARCHAR(64) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(usuario_id) REFERENCES ambpet.usuarios (id)
);
CREATE INDEX IF NOT EXISTS ix_auditoria_criado_em ON ambpet.auditoria (criado_em);
CREATE INDEX IF NOT EXISTS ix_auditoria_entidade ON ambpet.auditoria (entidade);
CREATE INDEX IF NOT EXISTS ix_auditoria_entidade_id ON ambpet.auditoria (entidade_id);

CREATE TABLE IF NOT EXISTS ambpet.indice_busca (
	id SERIAL NOT NULL, 
	tutor_id INTEGER NOT NULL, 
	token VARCHAR(32) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tutor_id) REFERENCES ambpet.tutores (id)
);
CREATE INDEX IF NOT EXISTS ix_indice_busca_token ON ambpet.indice_busca (token);
CREATE INDEX IF NOT EXISTS ix_indice_busca_tutor_id ON ambpet.indice_busca (tutor_id);

CREATE TABLE IF NOT EXISTS ambpet.pacientes (
	id SERIAL NOT NULL, 
	responsavel_id INTEGER NOT NULL, 
	nome VARCHAR(100) NOT NULL, 
	sexo VARCHAR(1) NOT NULL, 
	especie VARCHAR(40) NOT NULL, 
	raca VARCHAR(80) NOT NULL, 
	idade_anos INTEGER NOT NULL, 
	idade_meses INTEGER NOT NULL, 
	idade_referencia DATE NOT NULL, 
	castrado BOOLEAN NOT NULL, 
	pelagem VARCHAR(80), 
	peso_kg NUMERIC(6, 2), 
	alergias TEXT, 
	condicoes_cronicas TEXT, 
	observacoes_clinicas TEXT, 
	obito BOOLEAN NOT NULL, 
	criado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	atualizado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(responsavel_id) REFERENCES ambpet.tutores (id)
);
CREATE INDEX IF NOT EXISTS ix_pacientes_nome ON ambpet.pacientes (nome);
CREATE INDEX IF NOT EXISTS ix_pacientes_responsavel_id ON ambpet.pacientes (responsavel_id);

CREATE TABLE IF NOT EXISTS ambpet.agendamentos (
	id SERIAL NOT NULL, 
	responsavel_id INTEGER NOT NULL, 
	animal_id INTEGER NOT NULL, 
	data_hora TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	tipo VARCHAR(30) NOT NULL, 
	observacao TEXT, 
	status VARCHAR(20) NOT NULL, 
	chegada_em TIMESTAMP WITHOUT TIME ZONE, 
	criado_por_id INTEGER NOT NULL, 
	criado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(responsavel_id) REFERENCES ambpet.tutores (id), 
	FOREIGN KEY(animal_id) REFERENCES ambpet.pacientes (id), 
	FOREIGN KEY(criado_por_id) REFERENCES ambpet.usuarios (id)
);
CREATE INDEX IF NOT EXISTS ix_agendamentos_animal_id ON ambpet.agendamentos (animal_id);
CREATE INDEX IF NOT EXISTS ix_agendamentos_data_hora ON ambpet.agendamentos (data_hora);
CREATE INDEX IF NOT EXISTS ix_agendamentos_responsavel_id ON ambpet.agendamentos (responsavel_id);

CREATE TABLE IF NOT EXISTS ambpet.atendimentos (
	id SERIAL NOT NULL, 
	animal_id INTEGER NOT NULL, 
	veterinario_id INTEGER NOT NULL, 
	agendamento_id INTEGER, 
	data_hora TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	tipo VARCHAR(30) NOT NULL, 
	peso_kg NUMERIC(6, 2), 
	temperatura NUMERIC(4, 1), 
	freq_cardiaca INTEGER, 
	freq_respiratoria INTEGER, 
	mucosas VARCHAR(30), 
	hidratacao VARCHAR(30), 
	tpc VARCHAR(10), 
	queixa TEXT, 
	anamnese TEXT, 
	exame_fisico TEXT, 
	diagnostico TEXT, 
	conduta TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(animal_id) REFERENCES ambpet.pacientes (id), 
	FOREIGN KEY(veterinario_id) REFERENCES ambpet.usuarios (id), 
	FOREIGN KEY(agendamento_id) REFERENCES ambpet.agendamentos (id)
);
CREATE INDEX IF NOT EXISTS ix_atendimentos_animal_id ON ambpet.atendimentos (animal_id);
CREATE INDEX IF NOT EXISTS ix_atendimentos_data_hora ON ambpet.atendimentos (data_hora);

CREATE TABLE IF NOT EXISTS ambpet.adendos (
	id SERIAL NOT NULL, 
	consulta_id INTEGER NOT NULL, 
	autor_id INTEGER NOT NULL, 
	texto TEXT NOT NULL, 
	criado_em TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(consulta_id) REFERENCES ambpet.atendimentos (id), 
	FOREIGN KEY(autor_id) REFERENCES ambpet.usuarios (id)
);
CREATE INDEX IF NOT EXISTS ix_adendos_consulta_id ON ambpet.adendos (consulta_id);

CREATE TABLE IF NOT EXISTS ambpet.receitas (
	id SERIAL NOT NULL, 
	animal_id INTEGER NOT NULL, 
	veterinario_id INTEGER NOT NULL, 
	consulta_id INTEGER, 
	tipo VARCHAR(20) NOT NULL, 
	emitida_em TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	orientacoes TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(animal_id) REFERENCES ambpet.pacientes (id), 
	FOREIGN KEY(veterinario_id) REFERENCES ambpet.usuarios (id), 
	FOREIGN KEY(consulta_id) REFERENCES ambpet.atendimentos (id)
);
CREATE INDEX IF NOT EXISTS ix_receitas_animal_id ON ambpet.receitas (animal_id);
CREATE INDEX IF NOT EXISTS ix_receitas_emitida_em ON ambpet.receitas (emitida_em);

CREATE TABLE IF NOT EXISTS ambpet.receita_itens (
	id SERIAL NOT NULL, 
	receita_id INTEGER NOT NULL, 
	medicamento TEXT NOT NULL, 
	concentracao TEXT, 
	quantidade TEXT, 
	via VARCHAR(40), 
	posologia TEXT NOT NULL, 
	duracao TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(receita_id) REFERENCES ambpet.receitas (id)
);
CREATE INDEX IF NOT EXISTS ix_receita_itens_receita_id ON ambpet.receita_itens (receita_id);

-- ---------- Permissões mínimas da aplicação ----------
revoke all on all tables in schema ambpet from public;
revoke all on all sequences in schema ambpet from public;

grant select, insert, update on ambpet.usuarios, ambpet.tutores, ambpet.pacientes, ambpet.agendamentos to ambpet_app;
grant select, insert, delete on ambpet.indice_busca to ambpet_app;
grant select, insert on ambpet.atendimentos, ambpet.adendos, ambpet.receitas, ambpet.receita_itens,
                        ambpet.auditoria to ambpet_app;
grant usage, select on all sequences in schema ambpet to ambpet_app;

-- Papéis da API do Supabase não têm acesso algum (defesa extra caso o schema seja exposto por engano)
do $$
declare papel text;
begin
  foreach papel in array array['anon', 'authenticated', 'service_role'] loop
    if exists (select 1 from pg_roles where rolname = papel) then
      execute format('revoke all on schema ambpet from %I', papel);
      execute format('revoke all on all tables in schema ambpet from %I', papel);
      execute format('revoke all on all sequences in schema ambpet from %I', papel);
      execute format('alter default privileges in schema ambpet revoke all on tables from %I', papel);
      execute format('alter default privileges in schema ambpet revoke all on sequences from %I', papel);
    end if;
  end loop;
end $$;
alter default privileges in schema ambpet revoke all on tables from public;

-- ---------- Row Level Security ----------
do $$
declare t text;
begin
  foreach t in array array['usuarios','tutores','indice_busca','pacientes','agendamentos','atendimentos',
                           'adendos','receitas','receita_itens','auditoria'] loop
    execute format('alter table ambpet.%I enable row level security', t);
    execute format('drop policy if exists ambpet_app_acesso on ambpet.%I', t);
    execute format('create policy ambpet_app_acesso on ambpet.%I for all to ambpet_app using (true) with check (true)', t);
  end loop;
end $$;

-- ---------- Imutabilidade (prontuário, receitas, auditoria) ----------
-- Bloqueia UPDATE/DELETE/TRUNCATE para qualquer papel, inclusive o dono.
-- Exceção controlada: manutenção (ex.: rotação de chaves) com
--   set local ambpet.manutencao = 'on';  -- somente via conexão administrativa
create or replace function ambpet.bloquear_alteracao() returns trigger
language plpgsql set search_path = pg_catalog as $$
begin
  if coalesce(current_setting('ambpet.manutencao', true), '') = 'on' and tg_op = 'UPDATE' then
    return new;
  end if;
  raise exception 'Registro imutável (%.%): % não permitido', tg_table_schema, tg_table_name, tg_op
    using errcode = 'insufficient_privilege';
end $$;
revoke all on function ambpet.bloquear_alteracao() from public;

do $$
declare t text;
begin
  foreach t in array array['atendimentos','adendos','receitas','receita_itens','auditoria'] loop
    execute format('drop trigger if exists imutavel on ambpet.%I', t);
    execute format('create trigger imutavel before update or delete on ambpet.%I for each row execute function ambpet.bloquear_alteracao()', t);
    execute format('drop trigger if exists imutavel_truncate on ambpet.%I', t);
    execute format('create trigger imutavel_truncate before truncate on ambpet.%I for each statement execute function ambpet.bloquear_alteracao()', t);
  end loop;
  -- cadastros não são apagados (LGPD: anonimização); preserva o vínculo do prontuário
  foreach t in array array['tutores','pacientes','usuarios'] loop
    execute format('drop trigger if exists sem_exclusao on ambpet.%I', t);
    execute format('create trigger sem_exclusao before delete on ambpet.%I for each row execute function ambpet.bloquear_alteracao()', t);
  end loop;
end $$;

-- ---------- Sanidade: colunas sensíveis devem conter apenas texto cifrado ----------
alter table ambpet.tutores drop constraint if exists tutores_cpf_cifrado;
alter table ambpet.tutores add constraint tutores_cpf_cifrado check (cpf ~ '^[A-Za-z0-9]{1,16}\$');
alter table ambpet.tutores drop constraint if exists tutores_nome_cifrado;
alter table ambpet.tutores add constraint tutores_nome_cifrado check (nome ~ '^[A-Za-z0-9]{1,16}\$');

commit;
