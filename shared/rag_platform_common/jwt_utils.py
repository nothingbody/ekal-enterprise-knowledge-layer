"""
JWT 创建工具。不依赖具体应用的 config，由调用方传入参数。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

import jwt as pyjwt


def create_access_token(
    data: dict,
    secret_key: str,
    algorithm: str = "HS256",
    expires_delta: Optional[timedelta] = None,
    default_minutes: int = 60 * 24,
) -> str:
    """
    创建访问令牌。
    :param data: 载荷数据，需包含 sub
    :param secret_key: JWT 签名密钥
    :param algorithm: 算法
    :param expires_delta: 过期时间间隔，None 时使用 default_minutes
    :param default_minutes: 默认过期分钟数
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=default_minutes)
    )
    to_encode.update({"exp": expire, "type": "access", "jti": uuid.uuid4().hex})
    return pyjwt.encode(to_encode, secret_key, algorithm=algorithm)


def create_refresh_token(
    data: dict,
    secret_key: str,
    algorithm: str = "HS256",
    expires_days: int = 30,
) -> str:
    """
    创建刷新令牌。
    :param data: 载荷数据，需包含 sub
    :param secret_key: JWT 签名密钥
    :param algorithm: 算法
    :param expires_days: 过期天数
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=expires_days)
    to_encode.update({"exp": expire, "type": "refresh", "jti": uuid.uuid4().hex})
    return pyjwt.encode(to_encode, secret_key, algorithm=algorithm)
