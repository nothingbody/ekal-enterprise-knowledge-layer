"""Integration tests for server auth API endpoints."""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from app.models.system_config import SystemConfig


@pytest.mark.asyncio
class TestAuthFlow:
    async def test_register_config_default(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/register-config")
        assert resp.status_code == 200
        assert resp.json() == {
            "allow_registration": True,
            "require_invite_code": False,
        }

    async def test_register_config_from_system_config(self, client: AsyncClient, db_session):
        db_session.add(SystemConfig(key="allow_registration", value="false"))
        db_session.add(SystemConfig(key="invite_code", value="INV-001"))
        await db_session.commit()

        resp = await client.get("/api/v1/auth/register-config")
        assert resp.status_code == 200
        assert resp.json() == {
            "allow_registration": False,
            "require_invite_code": True,
        }

    async def test_register_first_user_is_super_admin(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "username": "admin",
            "email": "admin@test.com",
            "password": "Test123456",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"
        assert data["role"] == "super_admin"

    async def test_register_second_user_is_regular(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "username": "first",
            "email": "first@test.com",
            "password": "Test123456",
        })
        resp = await client.post("/api/v1/auth/register", json={
            "username": "second",
            "email": "second@test.com",
            "password": "Test123456",
        })
        assert resp.status_code == 200
        assert resp.json()["role"] == "user"

    async def test_register_duplicate_username_fails(self, client: AsyncClient):
        payload = {"username": "dup", "email": "dup@test.com", "password": "Test123456"}
        await client.post("/api/v1/auth/register", json=payload)
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 400

    async def test_register_respects_system_config(self, client: AsyncClient, db_session):
        db_session.add(SystemConfig(key="allow_registration", value="false"))
        await db_session.commit()

        resp = await client.post("/api/v1/auth/register", json={
            "username": "blocked",
            "email": "blocked@test.com",
            "password": "Test123456",
        })
        assert resp.status_code == 403

    async def test_register_requires_invite_code_from_system_config(self, client: AsyncClient, db_session):
        db_session.add(SystemConfig(key="invite_code", value="INV-001"))
        await db_session.commit()

        resp = await client.post("/api/v1/auth/register", json={
            "username": "inviteuser",
            "email": "invite@test.com",
            "password": "Test123456",
        })
        assert resp.status_code == 403

        ok = await client.post("/api/v1/auth/register", json={
            "username": "inviteuser",
            "email": "invite@test.com",
            "password": "Test123456",
            "invite_code": "INV-001",
        })
        assert ok.status_code == 200

    async def test_login_success(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "username": "loginuser",
            "email": "login@test.com",
            "password": "MyPassword1",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "username": "loginuser",
            "password": "MyPassword1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["username"] == "loginuser"

    async def test_login_wrong_password(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "username": "wrongpwd",
            "email": "wrong@test.com",
            "password": "Correct123",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "username": "wrongpwd",
            "password": "Wrong123",
        })
        assert resp.status_code == 401

    async def test_me_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code in (401, 403)

    async def test_me_with_valid_token(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "username": "meuser",
            "email": "me@test.com",
            "password": "Test123456",
        })
        login_resp = await client.post("/api/v1/auth/login", json={
            "username": "meuser",
            "password": "Test123456",
        })
        token = login_resp.json()["access_token"]
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "meuser"

    async def test_refresh_token_rotation(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "username": "refreshuser",
            "email": "refresh@test.com",
            "password": "Test123456",
        })
        login_resp = await client.post("/api/v1/auth/login", json={
            "username": "refreshuser",
            "password": "Test123456",
        })
        old_refresh = login_resp.json()["refresh_token"]

        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": old_refresh,
        })
        assert resp.status_code == 200
        new_data = resp.json()
        assert "access_token" in new_data
        assert new_data["refresh_token"] != old_refresh

        replay = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": old_refresh,
        })
        assert replay.status_code == 401

    async def test_logout_revokes_token(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "username": "logoutuser",
            "email": "logout@test.com",
            "password": "Test123456",
        })
        login_resp = await client.post("/api/v1/auth/login", json={
            "username": "logoutuser",
            "password": "Test123456",
        })
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/v1/auth/logout", headers=headers)
        assert resp.status_code == 200

        me_resp = await client.get("/api/v1/auth/me", headers=headers)
        assert me_resp.status_code in (401, 403)
