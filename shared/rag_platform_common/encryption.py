"""
统一加密模块。

使用 Fernet 作为主加密方式，同时保持对历史 AES-256-CBC 数据的解密兼容性。
不依赖具体应用的 config，由调用方传入参数。
"""
import base64
import hashlib
import os
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)

_HKDF_INFO = b"rag-platform-api-key-encryption"


class DecryptionError(Exception):
    """Raised when decryption fails, typically due to a changed SECRET_KEY."""
    pass


def _derive_key_hkdf(secret: str) -> bytes:
    """Derive a 32-byte key using HKDF (preferred)."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_HKDF_INFO,
    ).derive(secret.encode("utf-8"))


def _derive_key_legacy(secret: str) -> bytes:
    """Legacy key derivation via raw SHA-256, kept for decryption compatibility."""
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _get_fernet_key(secret: str) -> bytes:
    """Get Fernet-compatible key (base64-encoded 32-byte key)."""
    return base64.urlsafe_b64encode(_derive_key_hkdf(secret))


def encrypt_value(plaintext: str, secret: str) -> str:
    """
    Encrypt a string using Fernet.
    
    :param plaintext: 明文字符串
    :param secret: 加密密钥
    :return: 加密后的字符串
    """
    if not plaintext:
        return ""
    fernet = Fernet(_get_fernet_key(secret))
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def _try_decrypt_fernet(ciphertext: str, secret: str, use_hkdf: bool = True) -> Optional[str]:
    """Try Fernet decryption with specified key derivation."""
    try:
        if use_hkdf:
            key = _get_fernet_key(secret)
        else:
            key = base64.urlsafe_b64encode(_derive_key_legacy(secret))
        fernet = Fernet(key)
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        return None


def _try_decrypt_aes_cbc(ciphertext_bytes: bytes, key: bytes) -> Optional[str]:
    """Try AES-256-CBC decryption (for legacy Backend data)."""
    try:
        if len(ciphertext_bytes) < 32:
            return None
        iv = ciphertext_bytes[:16]
        ct = ciphertext_bytes[16:]
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(ct) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded_data) + unpadder.finalize()
        return plaintext.decode("utf-8")
    except Exception:
        return None


def decrypt_value(ciphertext: str, secret: str) -> str:
    """
    Decrypt an encrypted string.
    
    Tries multiple decryption methods in order:
    1. Fernet with HKDF key (current standard)
    2. Fernet with legacy SHA-256 key
    3. AES-256-CBC with HKDF key (legacy Backend format)
    4. AES-256-CBC with legacy SHA-256 key (oldest Backend format)
    
    :param ciphertext: 加密后的字符串
    :param secret: 加密密钥
    :return: 明文字符串
    :raises DecryptionError: 所有解密方式都失败时
    """
    if not ciphertext:
        return ""
    
    # Try Fernet (HKDF)
    result = _try_decrypt_fernet(ciphertext, secret, use_hkdf=True)
    if result is not None:
        return result
    
    # Try Fernet (legacy SHA-256)
    result = _try_decrypt_fernet(ciphertext, secret, use_hkdf=False)
    if result is not None:
        return result
    
    # Try AES-256-CBC (for legacy Backend data)
    try:
        raw = base64.b64decode(ciphertext)
    except Exception as exc:
        raise DecryptionError(
            "密钥/密码解密失败，请重新编辑并保存密码。"
            "（可能原因：SECRET_KEY 已变更）"
        ) from exc
    
    # AES-CBC with HKDF key
    result = _try_decrypt_aes_cbc(raw, _derive_key_hkdf(secret))
    if result is not None:
        return result
    
    # AES-CBC with legacy SHA-256 key
    result = _try_decrypt_aes_cbc(raw, _derive_key_legacy(secret))
    if result is not None:
        return result
    
    raise DecryptionError(
        "密钥/密码解密失败，请重新编辑并保存密码。"
        "（可能原因：SECRET_KEY 已变更）"
    )


def is_encrypted(value: str) -> bool:
    """
    Heuristic check if a value appears to be encrypted.
    
    Checks for Fernet format (gAAAAA prefix) or AES-CBC format.
    
    :param value: 待检查的字符串
    :return: True if likely encrypted
    """
    if not value:
        return False
    
    # Fernet tokens start with 'gAAAAA' (base64-encoded version + timestamp)
    if value.startswith("gAAAAA"):
        return True
    
    # Check for AES-CBC format: base64(iv_16 + ciphertext_16n)
    try:
        raw = base64.b64decode(value, validate=True)
        # Must be at least 32 bytes (16 IV + 16 min ciphertext)
        # and total length must be 16 (IV) + multiple of 16 (AES blocks)
        return len(raw) >= 32 and (len(raw) - 16) % 16 == 0
    except Exception:
        return False


def migrate_to_fernet(ciphertext: str, secret: str) -> str:
    """
    Migrate an old encrypted value to Fernet format.
    
    If already Fernet, returns as-is. Otherwise decrypts and re-encrypts.
    
    :param ciphertext: 旧加密字符串
    :param secret: 加密密钥
    :return: Fernet 格式的加密字符串
    """
    if not ciphertext:
        return ""
    
    # Already Fernet format
    if ciphertext.startswith("gAAAAA"):
        return ciphertext
    
    # Decrypt and re-encrypt
    plaintext = decrypt_value(ciphertext, secret)
    return encrypt_value(plaintext, secret)
