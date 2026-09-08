from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.models import forecasting as _forecasting  # noqa: F401
from backend.app.models import intelligence as _intelligence  # noqa: F401
from backend.app.models import knowledge as _knowledge  # noqa: F401
from backend.app.models import market as _market  # noqa: F401
from backend.app.models import operations as _operations  # noqa: F401
from backend.app.models import recommendation as _recommendation  # noqa: F401
from backend.app.models import scenario as _scenario  # noqa: F401
from backend.app.models import weather as _weather  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
