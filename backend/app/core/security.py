from datetime import datetime, timedelta, timezone
from typing import Optional
import logging

import jwt as pyjwt
from jwt.exceptions import PyJWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from rag_platform_common import hash_password, verify_password
from rag_platform_common.jwt_utils import create_access_token as _create_access_token, create_refresh_token as _create_refresh_token
from rag_platform_common.token_blacklist import (
    revoke_token as _revoke_token_impl,
    is_token_revoked as _is_token_revoked_impl,
)

from app.config import settings
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    return _create_access_token(
        data,
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        expires_delta=expires_delta,
        default_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )


def create_refresh_token(data: dict, expires_days: int | None = None) -> str:
    return _create_refresh_token(
        data,
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        expires_days=expires_days or settings.REFRESH_TOKEN_EXPIRE_DAYS,
    )


async def revoke_token(token: str) -> bool:
    """Add a token's JTI to the blacklist. Returns True on success."""
    return await _revoke_token_impl(
        token,
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        redis_url=settings.REDIS_URL,
    )


async def is_token_revoked(jti: str) -> bool:
    """Check if a token JTI is in the blacklist."""
    return await _is_token_revoked_impl(
        jti,
        redis_url=settings.REDIS_URL,
        strict=settings.TOKEN_BLACKLIST_STRICT,
    )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise credentials_exception
        if payload.get("type") == "2fa_pending":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="请先完成两步验证",
            )
        user_id = int(sub)
        jti = payload.get("jti")
        if jti and await is_token_revoked(jti):
            raise credentials_exception
    except (PyJWTError, ValueError, TypeError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    return user


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """已登录则返回用户；未带 Bearer 则返回 None。带 Token 但无效时仍抛 401。"""
    if not token:
        return None
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise credentials_exception
        if payload.get("type") == "2fa_pending":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="请先完成两步验证",
            )
        user_id = int(sub)
        jti = payload.get("jti")
        if jti and await is_token_revoked(jti):
            raise credentials_exception
    except (PyJWTError, ValueError, TypeError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    return user


async def get_user_from_token(token: str, db: AsyncSession) -> Optional[User]:
    """Validate a token string (e.g. from query param) and return the user, or None."""
    if not token:
        return None
    try:
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") == "refresh":
            return None
        sub = payload.get("sub")
        if sub is None:
            return None
        user_id = int(sub)
    except (PyJWTError, ValueError, TypeError):
        return None
    jti = payload.get("jti")
    if jti and await is_token_revoked(jti):
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not getattr(user, "is_active", True):
        return None
    return user


async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current_user
