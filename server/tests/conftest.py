"""Shared fixtures for server tests."""
import os
import sys
import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only")
os.environ.setdefault("ADMIN_PASSWORD", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

from app.config import settings  # noqa: E402
from app.database import engine, async_session  # noqa: E402
from app.models.base import Base  # noqa: E402
import app.models  # noqa: F401, E402 — register all models
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def disable_auth_rate_limiter():
    from app.api.auth import auth_limiter
    from app.config import settings
    from rag_platform_common.token_blacklist import reset_state

    original = settings.TOKEN_BLACKLIST_STRICT
    settings.TOKEN_BLACKLIST_STRICT = False
    reset_state()
    auth_limiter.enabled = False
    try:
        yield
    finally:
        settings.TOKEN_BLACKLIST_STRICT = original
        reset_state()


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
