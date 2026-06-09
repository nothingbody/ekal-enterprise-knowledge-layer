"""Tests for auth API endpoints: register, login, register-config, me, change-password."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.database import Base, get_db
from app.main import app
from app.config import settings
from app.models.user import User, UserRole
from app.core.security import create_access_token, hash_password

TEST_DB_URL = "sqlite+aiosqlite:///./test_auth.db"
API_PREFIX = "/api/v1/auth"

engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    from app.api.auth import limiter as auth_limiter
    auth_limiter.enabled = False
    app.dependency_overrides[get_db] = override_get_db
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_register_config(client: AsyncClient):
    """Without CENTRAL_SERVER_URL, register-config returns local settings."""
    original = settings.CENTRAL_SERVER_URL
    settings.CENTRAL_SERVER_URL = ""
    try:
        resp = await client.get(f"{API_PREFIX}/register-config")
        assert resp.status_code == 200
        data = resp.json()
        assert "allow_registration" in data
        assert "require_invite_code" in data
    finally:
        settings.CENTRAL_SERVER_URL = original


@pytest.mark.asyncio
async def test_register_first_user_becomes_admin(client: AsyncClient):
    """Without CENTRAL_SERVER_URL, local registration works."""
    original = settings.CENTRAL_SERVER_URL
    settings.CENTRAL_SERVER_URL = ""
    try:
        resp = await client.post(f"{API_PREFIX}/register", json={
            "username": "admin1",
            "email": "admin1@test.com",
            "password": "pass1234aa",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin1"
        assert data["role"] == "admin"
    finally:
        settings.CENTRAL_SERVER_URL = original


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """Without CENTRAL_SERVER_URL, local login works."""
    original = settings.CENTRAL_SERVER_URL
    settings.CENTRAL_SERVER_URL = ""
    try:
        async with TestSession() as session:
            user = User(
                username="loginuser",
                email="login@test.com",
                hashed_password=hash_password("pass1234aa"),
                role=UserRole.USER,
                is_active=True,
            )
            session.add(user)
            await session.commit()

        resp = await client.post(f"{API_PREFIX}/login", json={
            "username": "loginuser",
            "password": "pass1234aa",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
    finally:
        settings.CENTRAL_SERVER_URL = original


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    original = settings.CENTRAL_SERVER_URL
    settings.CENTRAL_SERVER_URL = ""
    try:
        async with TestSession() as session:
            user = User(
                username="wrongpwd",
                email="wrong@test.com",
                hashed_password=hash_password("correctpass1"),
                role=UserRole.USER,
                is_active=True,
            )
            session.add(user)
            await session.commit()

        resp = await client.post(f"{API_PREFIX}/login", json={
            "username": "wrongpwd",
            "password": "wrongpass1",
        })
        assert resp.status_code == 401
    finally:
        settings.CENTRAL_SERVER_URL = original


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient):
    resp = await client.get(f"{API_PREFIX}/me")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_change_password(client: AsyncClient):
    """Without CENTRAL_SERVER_URL, local password change works."""
    original = settings.CENTRAL_SERVER_URL
    settings.CENTRAL_SERVER_URL = ""
    try:
        async with TestSession() as session:
            user = User(
                username="pwduser",
                email="pwd@test.com",
                hashed_password=hash_password("oldpass1234"),
                role=UserRole.USER,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            token = create_access_token(data={"sub": str(user.id)})

        resp = await client.post(
            f"{API_PREFIX}/change-password",
            json={"old_password": "oldpass1234", "new_password": "newpass4567"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "密码修改成功"
    finally:
        settings.CENTRAL_SERVER_URL = original


@pytest.mark.asyncio
async def test_desktop_default_admin_created_without_cloud():
    """When cloud is NOT enabled, desktop mode creates a default admin."""
    from app.services.auth_service import ensure_desktop_default_admin

    original_desktop_mode = settings.DESKTOP_MODE
    original_central_url = settings.CENTRAL_SERVER_URL
    settings.DESKTOP_MODE = True
    settings.CENTRAL_SERVER_URL = ""
    try:
        async with TestSession() as session:
            result = await ensure_desktop_default_admin(session)
            assert result is not None
            assert result.username == "admin"
            assert result.must_change_password is True
    finally:
        settings.DESKTOP_MODE = original_desktop_mode
        settings.CENTRAL_SERVER_URL = original_central_url


@pytest.mark.asyncio
async def test_desktop_default_admin_skipped_with_cloud():
    """When cloud IS enabled, desktop mode does NOT create a default admin."""
    from app.services.auth_service import ensure_desktop_default_admin

    original_desktop_mode = settings.DESKTOP_MODE
    original_central_url = settings.CENTRAL_SERVER_URL
    settings.DESKTOP_MODE = True
    settings.CENTRAL_SERVER_URL = "http://fake-server.example.com"
    try:
        async with TestSession() as session:
            result = await ensure_desktop_default_admin(session)
            assert result is None
    finally:
        settings.DESKTOP_MODE = original_desktop_mode
        settings.CENTRAL_SERVER_URL = original_central_url
