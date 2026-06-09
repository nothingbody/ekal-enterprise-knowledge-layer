"""Entry point for the central server."""
import asyncio
import logging
import os

import uvicorn

from app.config import settings
from app.database import engine
from app.models.base import Base
import app.models

logger = logging.getLogger(__name__)


async def prepare_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _run_migrations()


def _run_migrations():
    """Run pending Alembic migrations so new columns are added to existing tables."""
    try:
        from alembic.config import Config
        from alembic import command

        alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations applied successfully")
    except Exception as exc:
        logger.warning("Alembic migration skipped or failed: %s", exc)


def main():
    debug = settings.DEBUG
    workers = settings.WEB_WORKERS
    asyncio.run(prepare_database())
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        log_level="debug" if debug else "info",
        reload=debug,
        workers=1 if debug else workers,
    )


if __name__ == "__main__":
    main()
