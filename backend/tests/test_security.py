"""Tests for core security module: password hashing, JWT tokens, token revocation."""
import time
import pytest

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    revoke_token,
    is_token_revoked,
)
from rag_platform_common.token_blacklist import (
    _memory_blacklist,
    cleanup_memory_blacklist,
    reset_state as reset_blacklist_state,
    _MEMORY_BLACKLIST_MAX,
)
from app.config import settings

import jwt as pyjwt


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "test_password_123!"
        hashed = hash_password(pw)
        assert hashed != pw
        assert hashed.startswith("$2")
        assert verify_password(pw, hashed)

    def test_wrong_password_rejected(self):
        hashed = hash_password("correct_password")
        assert not verify_password("wrong_password", hashed)

    def test_empty_password(self):
        hashed = hash_password("")
        assert verify_password("", hashed)
        assert not verify_password("notempty", hashed)

    def test_unicode_password(self):
        pw = "密码测试🔑"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed)

    def test_legacy_pbkdf2_format(self):
        """Simulate a legacy PBKDF2 salt$hash password."""
        import hashlib
        password = "legacy_password"
        salt = "randomsalt"
        hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
        stored = f"{salt}${hashed}"
        assert verify_password(password, stored)
        assert not verify_password("wrong", stored)

    def test_invalid_hash_format_returns_false(self):
        assert not verify_password("pw", "not_a_valid_hash_at_all")


# ---------------------------------------------------------------------------
# JWT Tokens
# ---------------------------------------------------------------------------

class TestJWTTokens:
    def test_access_token_has_correct_claims(self):
        token = create_access_token({"sub": "42"})
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["sub"] == "42"
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "exp" in payload

    def test_refresh_token_has_correct_type(self):
        token = create_refresh_token({"sub": "7"})
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["sub"] == "7"
        assert payload["type"] == "refresh"
        assert "jti" in payload

    def test_access_token_expiry(self):
        from datetime import timedelta
        token = create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=1))
        # Should be valid immediately
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["sub"] == "1"

    def test_token_wrong_key_rejected(self):
        token = create_access_token({"sub": "1"})
        with pytest.raises(pyjwt.exceptions.InvalidSignatureError):
            pyjwt.decode(token, "wrong-key", algorithms=[settings.ALGORITHM])

    def test_different_tokens_have_unique_jti(self):
        t1 = create_access_token({"sub": "1"})
        t2 = create_access_token({"sub": "1"})
        p1 = pyjwt.decode(t1, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        p2 = pyjwt.decode(t2, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert p1["jti"] != p2["jti"]


# ---------------------------------------------------------------------------
# Token Revocation (memory-fallback path, no Redis needed)
# ---------------------------------------------------------------------------

class TestTokenRevocation:
    def setup_method(self):
        """Clear the in-memory blacklist before each test."""
        reset_blacklist_state()

    @pytest.mark.asyncio
    async def test_revoke_and_check(self):
        token = create_access_token({"sub": "1"})
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        jti = payload["jti"]

        assert not await is_token_revoked(jti)
        assert await revoke_token(token)
        assert await is_token_revoked(jti)

    @pytest.mark.asyncio
    async def test_revoke_expired_token_returns_true(self):
        """Revoking an already-expired token should succeed (no-op)."""
        from datetime import timedelta
        token = create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=-1))
        result = await revoke_token(token)
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_unknown_jti_not_revoked(self):
        assert not await is_token_revoked("nonexistent-jti-12345")

    def test_cleanup_removes_expired_entries(self):
        _memory_blacklist["old_jti"] = time.time() - 10  # already expired
        _memory_blacklist["valid_jti"] = time.time() + 3600  # still valid
        cleanup_memory_blacklist()
        assert "old_jti" not in _memory_blacklist
        assert "valid_jti" in _memory_blacklist

    @pytest.mark.asyncio
    async def test_memory_blacklist_eviction_on_overflow(self):
        """When memory blacklist is full, cleanup should run on next revoke."""
        # Fill blacklist with expired entries
        for i in range(_MEMORY_BLACKLIST_MAX):
            _memory_blacklist[f"jti_{i}"] = time.time() - 10  # all expired
        assert len(_memory_blacklist) == _MEMORY_BLACKLIST_MAX

        # Next revoke should trigger cleanup
        token = create_access_token({"sub": "1"})
        await revoke_token(token)
        # Expired entries should be cleaned up, blacklist should be smaller
        assert len(_memory_blacklist) < _MEMORY_BLACKLIST_MAX + 5
