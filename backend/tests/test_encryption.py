"""Tests for AES-256-CBC encryption utilities."""
import pytest
from app.core.encryption import encrypt_value, decrypt_value, is_encrypted


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        secret = "test-secret-key-123"
        plaintext = "test-api-key-abc123"
        encrypted = encrypt_value(plaintext, secret)
        assert encrypted != plaintext
        decrypted = decrypt_value(encrypted, secret)
        assert decrypted == plaintext

    def test_encrypt_empty_string(self):
        assert encrypt_value("", "secret") == ""

    def test_decrypt_empty_string(self):
        assert decrypt_value("", "secret") == ""

    def test_different_secrets_produce_different_ciphertext(self):
        plaintext = "my-api-key"
        enc1 = encrypt_value(plaintext, "secret-1")
        enc2 = encrypt_value(plaintext, "secret-2")
        assert enc1 != enc2

    def test_decrypt_with_wrong_secret_fails(self):
        encrypted = encrypt_value("my-api-key", "correct-secret")
        with pytest.raises(Exception):
            decrypt_value(encrypted, "wrong-secret")

    def test_is_encrypted_true_for_encrypted_value(self):
        encrypted = encrypt_value("test-key", "secret")
        assert is_encrypted(encrypted) is True

    def test_is_encrypted_false_for_plaintext(self):
        assert is_encrypted("plain-api-key-placeholder") is False

    def test_is_encrypted_false_for_empty(self):
        assert is_encrypted("") is False

    def test_is_encrypted_false_for_none(self):
        assert is_encrypted(None) is False

    def test_unicode_content(self):
        secret = "unicode-secret"
        plaintext = "测试中文API密钥-🔑"
        encrypted = encrypt_value(plaintext, secret)
        decrypted = decrypt_value(encrypted, secret)
        assert decrypted == plaintext

    def test_long_api_key(self):
        secret = "secret"
        plaintext = "sk-" + "a" * 500
        encrypted = encrypt_value(plaintext, secret)
        decrypted = decrypt_value(encrypted, secret)
        assert decrypted == plaintext
