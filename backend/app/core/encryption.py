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


def encrypt_value(plaintext: str, secret: str = None) -> str:
    """Encrypt a string. Uses app SECRET_KEY if secret not provided."""
    return _encrypt_value(plaintext, secret or settings.SECRET_KEY)


def decrypt_value(ciphertext: str, secret: str = None) -> str:
    """Decrypt a string. Uses app SECRET_KEY if secret not provided."""
    return _decrypt_value(ciphertext, secret or settings.SECRET_KEY)


__all__ = [
    "encrypt_value",
    "decrypt_value",
    "is_encrypted",
    "migrate_to_fernet",
    "DecryptionError",
]
