"""Tests for server security module: password hashing, JWT tokens, token revocation."""
import pytest
import jwt as pyjwt
from datetime import timedelta

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    revoke_token,
    is_token_revoked,
    check_role_level,
    ROLE_HIERARCHY,
)
from app.config import settings
from app.models.user import UserRole


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pwd = "StrongP@ssw0rd!"
        hashed = hash_password(pwd)
        assert hashed != pwd
        assert verify_password(pwd, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2

    def test_invalid_hash_returns_false(self):
        assert not verify_password("any", "not-a-valid-bcrypt-hash")


class TestJWTTokens:
    def test_access_token_contains_expected_claims(self):
        token = create_access_token(data={"sub": "42"})
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["sub"] == "42"
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "exp" in payload

    def test_refresh_token_contains_expected_claims(self):
        token = create_refresh_token(data={"sub": "7"})
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["sub"] == "7"
        assert payload["type"] == "refresh"
        assert "jti" in payload

    def test_custom_expiry(self):
        token = create_access_token(
            data={"sub": "1"},
            expires_delta=timedelta(minutes=5),
        )
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["exp"] is not None

    def test_invalid_secret_raises(self):
        token = create_access_token(data={"sub": "1"})
        with pytest.raises(pyjwt.exceptions.InvalidSignatureError):
            pyjwt.decode(token, "wrong-secret", algorithms=[settings.ALGORITHM])


class TestTokenRevocation:
    @pytest.mark.asyncio
    async def test_revoke_and_check(self):
        token = create_access_token(data={"sub": "1"})
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        jti = payload["jti"]

        assert not await is_token_revoked(jti)
        result = await revoke_token(token)
        assert result is True
        assert await is_token_revoked(jti)

    @pytest.mark.asyncio
    async def test_revoke_invalid_token_returns_false(self):
        result = await revoke_token("completely.invalid.token")
        assert result is False

    @pytest.mark.asyncio
    async def test_nonexistent_jti_not_revoked(self):
        assert not await is_token_revoked("nonexistent-jti-12345")


class TestRoleHierarchy:
    def test_super_admin_highest(self):
        assert ROLE_HIERARCHY[UserRole.SUPER_ADMIN] > ROLE_HIERARCHY[UserRole.ADMIN]
        assert ROLE_HIERARCHY[UserRole.ADMIN] > ROLE_HIERARCHY[UserRole.USER]

    def test_check_role_level(self):
        class FakeUser:
            def __init__(self, role):
                self.role = role

        admin = FakeUser(UserRole.ADMIN)
        user = FakeUser(UserRole.USER)

        assert check_role_level(admin, UserRole.USER)
        assert check_role_level(admin, UserRole.ADMIN)
        assert not check_role_level(user, UserRole.ADMIN)
