# AMBPET — Sistema da Clínica (Recepção + Veterinária)

Sistema web de gestão de atendimento veterinário, implementando o **Grupo Clínica** do
documento de requisitos. O módulo Castramóvel/Escritório (Grupo Campo) **não faz parte**
deste sistema — ele é atendido por um sistema separado.

## Perfis

| Perfil | Pode fazer |
|---|---|
| **Recepção** | Cadastrar/editar responsáveis e animais, agendar consultas, painel do dia, alterar situação do agendamento |
| **Veterinária** | Painel do dia, localizar animal pelo responsável, atualizar ficha (dados cadastrais + clínicos), anotações de consulta, complementos, receitas, histórico de medicações |
| **Administrador** | Tudo acima + cadastro de usuários e registro de auditoria |

A Recepção **não** vê anotações de consulta nem receitas (dados de saúde — LGPD).

## Requisitos atendidos

| Requisito | Como |
|---|---|
| RF01/RF02 | Cadastro de responsável (nome, CPF único e validado, telefone, endereço com CEP, ano do CadÚnico) e de um ou mais animais (nome, sexo, espécie, raça, idade, castrado) |
| RF03/RF04 | Agendamento só para responsável + animal cadastrados; seg–sex, 08:00–16:00 (validado no servidor); não permite data passada |
| RF05/RNF07 | Painel do dia: hora, responsável, animal, telefone, observação e situação; navegação por data; impressão |
| RF06 | Veterinária edita a ficha (inclui peso, pelagem, alergias, condições crônicas, observações, óbito) |
| RF07/RF08 | Anotações de consulta por data, histórico cronológico na ficha |
| RF09/RF10 | Receitas com vários medicamentos, impressão com CRMV; aba "Medicações receitadas" com filtro |
| RNF01 | Login individual, controle por perfil em todas as rotas |
| RNF04 | Tabela `auditoria`: usuário, data/hora e detalhes de cada cadastro, edição, agendamento, consulta e receita; histórico de alterações (de → para) visível na ficha |
| RNF05 | Consultas e receitas não têm edição nem exclusão; só complementos (adendos) |
| RNF06 | Validação de CPF (dígito verificador), telefone e CEP + máscaras; endereço preenchido pelo CEP (ViaCEP) |
| RNF09/RNF11 | Busca por nome, CPF, telefone ou nome do animal, com índices no banco |
| RNF10 | `flask backup` (SQLite) ou `pg_dump` (PostgreSQL); senhas com hash; CSRF; cookies HttpOnly |

## Rodando localmente

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/flask --app wsgi criar-usuario --login admin --nome "Administrador" --perfil admin
.venv/bin/flask --app wsgi run --debug
```

Acesse http://localhost:5000, entre como `admin` e cadastre os usuários da Recepção e da
Veterinária em **Administração** (informe o CRMV da veterinária — ele sai na receita).

## Configuração (variáveis de ambiente)

| Variável | Padrão | Descrição |
|---|---|---|
| `SECRET_KEY` | (dev) | **Obrigatório em produção** — string aleatória longa |
| `DATABASE_URL` | SQLite em `instance/ambpet.db` | Ex.: `postgresql+psycopg://user:senha@host/ambpet` (instale `psycopg[binary]`) |
| `CLINICA_NOME`, `CLINICA_ENDERECO`, `CLINICA_TELEFONE` | | Cabeçalho da receita |
| `AGENDA_INTERVALO_MIN` | `15` | Intervalo entre horários oferecidos na agenda |
| `SESSION_COOKIE_SECURE` | `0` | Use `1` quando estiver atrás de HTTPS |
| `TZ_CLINICA` | `America/Sao_Paulo` | Fuso horário da clínica |
| `BACKUP_DIR` | `./backups` | Destino do `flask backup` |

## Produção

```bash
SECRET_KEY=... SESSION_COOKIE_SECURE=1 .venv/bin/gunicorn -w 3 -b 0.0.0.0:8000 wsgi:app
```

Coloque atrás de um proxy com HTTPS (nginx, Caddy). Para LGPD/RNF10, use disco ou banco
com criptografia em repouso (ex.: PostgreSQL gerenciado) e agende o backup:

```cron
0 19 * * 1-5  cd /srv/ambpet && .venv/bin/flask --app wsgi backup
```

## Testes

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```
