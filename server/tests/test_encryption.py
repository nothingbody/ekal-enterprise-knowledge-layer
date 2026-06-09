"""Tests for server encryption module: encrypt/decrypt, key derivation, legacy fallback."""
import base64
import hashlib
import pytest

from app.core.encryption import DecryptionError, encrypt_value, decrypt_value, is_encrypted
from app.config import settings
from rag_platform_common.encryption import _derive_key_hkdf, _derive_key_legacy


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "test-api-key-1234567890abcdef"
        encrypted = encrypt_value(plaintext)
        assert encrypted != plaintext
        assert decrypt_value(encrypted) == plaintext

    def test_empty_string_passthrough(self):
        assert encrypt_value("") == ""
        assert decrypt_value("") == ""

    def test_different_ciphertexts_for_same_plaintext(self):
        """Fernet uses random IV, so repeated encryption should differ."""
        a = encrypt_value("test-key")
        b = encrypt_value("test-key")
        assert a != b
        assert decrypt_value(a) == decrypt_value(b) == "test-key"

    def test_unicode_value(self):
        val = "密钥-тест-🔑"
        assert decrypt_value(encrypt_value(val)) == val


class TestKeyDerivation:
    def test_hkdf_and_legacy_produce_different_keys(self):
        hkdf_key = _derive_key_hkdf(settings.SECRET_KEY)
        legacy_key = _derive_key_legacy(settings.SECRET_KEY)
        assert hkdf_key != legacy_key

    def test_hkdf_key_is_deterministic(self):
        assert _derive_key_hkdf(settings.SECRET_KEY) == _derive_key_hkdf(settings.SECRET_KEY)

    def test_legacy_key_is_deterministic(self):
        assert _derive_key_legacy(settings.SECRET_KEY) == _derive_key_legacy(settings.SECRET_KEY)


class TestLegacyFallback:
    def test_legacy_encrypted_value_still_decryptable(self):
        """Simulate a value encrypted with legacy SHA-256 derivation."""
        from cryptography.fernet import Fernet

        legacy_key = base64.urlsafe_b64encode(_derive_key_legacy(settings.SECRET_KEY))
        f = Fernet(legacy_key)
        ciphertext = f.encrypt(b"old-api-key").decode("utf-8")
        assert decrypt_value(ciphertext) == "old-api-key"

    def test_invalid_ciphertext_raises(self):
        with pytest.raises(DecryptionError):
            decrypt_value("not-a-valid-fernet-token")
