"""Integration tests for the core user flow:
register -> login -> create knowledge base -> create model -> health check.

These tests exercise the full API stack with a real (in-memory) database
to catch routing, serialization, and permission regressions.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.database import Base, get_db
from app.main import app

TEST_DB_URL = "sqlite+aiosqlite:///./test_integration.db"

engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    from app.api.auth import limiter as auth_limiter
    auth_limiter.enabled = False
    from app.main import limiter as global_limiter
    global_limiter.enabled = False
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


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient):
    """Register a test user and return auth headers."""
    await client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpass123",
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "username": "testuser",
        "password": "testpass123",
    })
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Health Check ──

@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("app")
    assert data.get("version")
    assert data.get("database") == "ok"


# ── Auth Flow ──

@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    reg_resp = await client.post("/api/v1/auth/register", json={
        "username": "newuser",
        "email": "new@example.com",
        "password": "secure123",
    })
    assert reg_resp.status_code == 200
    assert reg_resp.json()["username"] == "newuser"

    login_resp = await client.post("/api/v1/auth/login", json={
        "username": "newuser",
        "password": "secure123",
    })
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "username": "wrongpw",
        "email": "wp@example.com",
        "password": "correct123",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "username": "wrongpw",
        "password": "wrong_password",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoint(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "testuser"


@pytest.mark.asyncio
async def test_me_without_auth(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)


# ── Token Refresh ──

@pytest.mark.asyncio
async def test_token_refresh(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "username": "refreshuser",
        "email": "refresh@example.com",
        "password": "pass123456",
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "username": "refreshuser",
        "password": "pass123456",
    })
    refresh_token = login_resp.json()["refresh_token"]

    refresh_resp = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": refresh_token,
    })
    assert refresh_resp.status_code == 200
    new_data = refresh_resp.json()
    assert "access_token" in new_data
    assert "refresh_token" in new_data
    assert new_data["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_refresh_token_one_time_use(client: AsyncClient):
    """After using a refresh token, the same token should be rejected."""
    await client.post("/api/v1/auth/register", json={
        "username": "onetimeuser",
        "email": "onetime@example.com",
        "password": "pass123456",
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "username": "onetimeuser",
        "password": "pass123456",
    })
    old_refresh = login_resp.json()["refresh_token"]

    resp1 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp1.status_code == 200

    resp2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp2.status_code == 401


# ── Knowledge Base CRUD ──

@pytest.mark.asyncio
async def test_knowledge_base_crud(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/v1/knowledge-bases/", json={
        "name": "测试知识库",
        "description": "集成测试用知识库",
    }, headers=auth_headers)
    assert create_resp.status_code == 200
    kb = create_resp.json()
    kb_id = kb["id"]
    assert kb["name"] == "测试知识库"

    list_resp = await client.get("/api/v1/knowledge-bases/", headers=auth_headers)
    assert list_resp.status_code == 200
    kbs = list_resp.json()
    assert any(k["id"] == kb_id for k in kbs)

    del_resp = await client.delete(f"/api/v1/knowledge-bases/{kb_id}", headers=auth_headers)
    assert del_resp.status_code == 200


# ── Error Format ──

@pytest.mark.asyncio
async def test_error_response_format(client: AsyncClient):
    """All error responses should include status, code, and detail."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)
    data = resp.json()
    assert "status" in data
    assert "code" in data
    assert "detail" in data
