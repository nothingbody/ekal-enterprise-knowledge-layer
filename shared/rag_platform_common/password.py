"""
密码哈希与验证。兼容 bcrypt 与旧版 PBKDF2 格式。
"""
import hashlib


def hash_password(password: str) -> str:
    """使用 bcrypt 对密码进行哈希。"""
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码。支持：
    - bcrypt ($2a$, $2b$, $2y$)
    - 旧版 PBKDF2 格式：salt$hexhash
    """
    if hashed_password.startswith("$2"):
        import bcrypt
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except Exception:
            return False
    # Legacy PBKDF2 format: salt$hash
    try:
        salt, hashed = hashed_password.split("$", 1)
        check = hashlib.pbkdf2_hmac(
            "sha256", plain_password.encode(), salt.encode(), 100000
        ).hex()
        return check == hashed
    except Exception:
        return False
