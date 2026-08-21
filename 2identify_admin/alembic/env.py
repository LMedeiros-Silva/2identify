from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
from dotenv import load_dotenv

# ============================================================
# CARREGA AS VARIÁVEIS DO ARQUIVO .ENV
# ============================================================

load_dotenv()

# ============================================================
# CONFIGURAÇÃO DO ALEMBIC
# ============================================================

# Este é o objeto de configuração do Alembic.
# Ele permite acessar o alembic.ini e definir configurações.
config = context.config

# ============================================================
# CONFIGURAÇÃO DO LOG
# ============================================================

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ============================================================
# CONEXÃO COM O BANCO DE DADOS
# ============================================================

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError(
        "DATABASE_URL não encontrada no arquivo .env."
    )

# Coloca a URL do banco dentro da configuração do Alembic.
#
# O replace("%", "%%") é necessário porque o Alembic utiliza
# interpolação de strings no arquivo de configuração.
config.set_main_option(
    "sqlalchemy.url",
    database_url.replace("%", "%%")
)

# ============================================================
# MODELS / METADATA
# ============================================================

# Importamos a Base principal do SQLAlchemy.
from app.models.base import Base
from app.models import (
    Usuario,
    Setor,
    Funcionario,
    EPI,
    FuncionarioEPI,
    Camera,
    Ocorrencia,
    Alerta,
)

# Metadata que será utilizada pelo autogenerate do Alembic.
target_metadata = Base.metadata


# ============================================================
# MODO OFFLINE
# ============================================================

def run_migrations_offline() -> None:
    """
    Executa as migrations sem abrir uma conexão
    com o banco de dados.
    """

    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ============================================================
# MODO ONLINE
# ============================================================

def run_migrations_online() -> None:
    """
    Executa as migrations conectando diretamente
    ao banco de dados.
    """

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


# ============================================================
# EXECUÇÃO
# ============================================================

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()