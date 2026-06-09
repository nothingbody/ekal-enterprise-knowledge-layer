"""
Encryption utilities for sensitive data like API keys.

This module wraps the shared rag_platform_common.encryption module,
binding it to the app's SECRET_KEY for convenience.
"""
from rag_platform_common.encryption import (
    encrypt_value as _encrypt_value,
    decrypt_value as _decrypt_value,
    is_encrypted,
    migrate_to_fernet,
    DecryptionError,
)

from app.config import settings


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string using app SECRET_KEY."""
    return _encrypt_value(plaintext, settings.SECRET_KEY)


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a string using app SECRET_KEY.

    Raises DecryptionError on failure instead of returning raw ciphertext,
    to prevent leaking encrypted data in logs or API responses.
    """
    return _decrypt_value(ciphertext, settings.SECRET_KEY)


__all__ = [
    "encrypt_value",
    "decrypt_value",
    "is_encrypted",
    "migrate_to_fernet",
    "DecryptionError",
]
