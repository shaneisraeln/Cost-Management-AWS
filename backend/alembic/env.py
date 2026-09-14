"""Alembic migration environment (async engine + autogenerate)."""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.db.base import Base

# Import models so metadata is fully populated for autogenerate.
import app.db.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()

# Migrations run synchronously with psycopg (sync mode). Normalize whatever
# async driver the app uses (asyncpg / psycopg async) to a sync psycopg URL.
_url = settings.database_url
for _async_driver in ("postgresql+asyncpg", "postgresql+psycopg"):
    if _url.startswith(_async_driver):
        _url = _url.replace(_async_driver, "postgresql+psycopg", 1)
        break
SYNC_DATABASE_URL = _url


def run_migrations_offline() -> None:
    context.configure(
        url=SYNC_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(SYNC_DATABASE_URL, pool_pre_ping=True)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
