"""Alembic environment configuration.

Reads DATABASE_URL from app.config.settings so credentials are never
hardcoded in alembic.ini.
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from alembic import context

# Import ALL ORM models so metadata is fully populated
import app.models  # noqa: F401
from app.database import Base, get_sync_database_url
from app.config import settings

config = context.config

# Override the ini-file URL with the app's configured DATABASE_URL (sync driver)
_sync_url = get_sync_database_url(settings.DATABASE_URL)
config.set_main_option("sqlalchemy.url", _sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    """Run migrations with an async engine (asyncpg / aiomysql)."""
    from sqlalchemy.ext.asyncio import async_engine_from_config as async_from_cfg
    connectable = async_from_cfg(
        {"sqlalchemy.url": settings.DATABASE_URL},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = settings.DATABASE_URL
    if "+asyncpg" in url or "+aiosqlite" in url or "+aiomysql" in url:
        asyncio.run(_run_async_migrations())
    else:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            _do_run_migrations(connection)
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
