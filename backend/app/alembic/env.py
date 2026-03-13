from alembic.autogenerate.api import AutogenContext
from logging.config import fileConfig
from typing import Any, Literal

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register all table models
from app.core.config import settings
from app.core.db import PydanticJSON

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | Literal[False]:
    """Render PydanticJSON columns as plain sa.JSON() in migrations.

    No need to add ``import sqlalchemy as sa`` — Alembic already emits it
    for any migration that references ``sa.Column``.
    """
    if type_ == "type" and isinstance(obj, PydanticJSON):
        return "sa.JSON()"
    return False


def get_url() -> str:
    return str(settings.SQLALCHEMY_DATABASE_URI)


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section)
    assert configuration is not None  # noqa: S101
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
