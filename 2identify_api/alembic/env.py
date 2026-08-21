"""Alembic environment for a database initially owned by 2Identify Admin."""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import get_settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option(
    "sqlalchemy.url",
    settings.sqlalchemy_database_url.replace("%", "%%"),
)
target_metadata = Base.metadata


def _block_unsafe_autogenerate() -> None:
    command_options = getattr(config, "cmd_opts", None)
    if command_options is not None and getattr(command_options, "autogenerate", False):
        raise RuntimeError(
            "Autogenerate está bloqueado: os modelos da API ainda não representam o esquema real."
        )


def run_migrations_offline() -> None:
    """Configure offline SQL generation without executing database statements."""

    _block_unsafe_autogenerate()
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=settings.database_schema,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Configure an online migration context; Stage 33 never invokes upgrades."""

    _block_unsafe_autogenerate()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        hide_parameters=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=settings.database_schema,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
