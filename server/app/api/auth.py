import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.database import get_db
from app.models.user import User, UserRole
from app.models.device import Device
from app.models.system_config import SystemConfig
from app.schemas import UserRegister, UserLogin, TokenResponse, UserResponse, RefreshTokenRequest
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    get_current_user, revoke_token, is_token_revoked,
)
import jwt as pyjwt
from jwt.exceptions import PyJWTError

router = APIRouter()
logger = logging.getLogger(__name__)


def _detect_limiter_storage() -> str:
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=0.5)
        r.ping()
        r.close()
        return settings.REDIS_URL
    except Exception:
        logger.warning("Redis 不可用，auth 限流器回退到内存模式")
        return "memory://"


auth_limiter = Limiter(key_func=get_remote_address, storage_uri=_detect_limiter_storage())


async def _get_config_value(db: AsyncSession, key: str, default):
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    row = result.scalar_one_or_none()
    if row and row.value is not None:
        if key == "allow_registration":
            return str(row.value).lower() in ("1", "true", "yes")
        return row.value
    return default


@router.get("/register-config")
async def register_config(db: AsyncSession = Depends(get_db)):
    allow_registration = await _get_config_value(db, "allow_registration", settings.ALLOW_REGISTRATION)
    invite_code = await _get_config_value(db, "invite_code", settings.INVITE_CODE)
    return {
        "allow_registration": allow_registration,
        "require_invite_code": bool(invite_code),
    }


@router.post("/register", response_model=UserResponse)
@auth_limiter.limit("5/minute")
async def register(request: Request, data: UserRegister, db: AsyncSession = Depends(get_db)):
    allow_registration = await _get_config_value(db, "allow_registration", settings.ALLOW_REGISTRATION)
    invite_code = await _get_config_value(db, "invite_code", settings.INVITE_CODE)

    if not allow_registration:
        raise HTTPException(403, "注册已关闭")
    if invite_code and (data.invite_code or "").strip() != invite_code:
        raise HTTPException(403, "邀请码无效")

    existing = await db.execute(
        select(User).where(
            User.deleted_at.is_(None),
            (User.username == data.username) | (User.email == data.email),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "用户名或邮箱已存在")

    user_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    role = UserRole.SUPER_ADMIN if user_count == 0 else UserRole.USER

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("USER_REGISTER username=%s role=%s", user.username, user.role.value)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
@auth_limiter.limit("10/minute")
async def login(request: Request, data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(403, "账号已被禁用")

    client_ip = request.client.host if request.client else None
    user.last_login_at = datetime.now(timezone.utc)
    if client_ip:
        user.last_login_ip = client_ip

    if data.device_id:
        dev = (await db.execute(
            select(Device).where(Device.device_id == data.device_id)
        )).scalar_one_or_none()
        if dev:
            dev.user_id = user.id
            dev.device_name = data.device_name or dev.device_name
            dev.os_info = data.os_info or dev.os_info
            dev.app_version = data.app_version or dev.app_version
            dev.last_heartbeat = datetime.now(timezone.utc)
            dev.is_active = True
        else:
            db.add(Device(
                user_id=user.id,
                device_id=data.device_id,
                device_name=data.device_name,
                os_info=data.os_info,
                app_version=data.app_version,
            ))

    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = pyjwt.decode(data.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(401, "无效的 token 类型")
        user_id = int(payload["sub"])
    except (PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "refresh_token 无效或已过期")

    jti = payload.get("jti")
    if jti and await is_token_revoked(jti):
        raise HTTPException(401, "refresh_token 已被吊销")

    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(401, "用户不存在或已禁用")

    await revoke_token(data.refresh_token)

    new_access = create_access_token(data={"sub": str(user.id)})
    new_refresh = create_refresh_token(data={"sub": str(user.id)})
    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        user=UserResponse.model_validate(user),
    )


@router.post("/logout")
async def logout(request: Request, current_user: User = Depends(get_current_user)):
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        await revoke_token(auth_header[7:])
    logger.info("USER_LOGOUT user=%s", current_user.username)
    return {"message": "已退出登录"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=100)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        from app.schemas import _validate_password_strength
        return _validate_password_strength(v)


class UpdateProfileRequest(BaseModel):
    nickname: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.old_password, current_user.hashed_password):
        raise HTTPException(400, "原密码错误")
    current_user.hashed_password = hash_password(data.new_password)
    await db.commit()
    logger.info("PASSWORD_CHANGED user=%s", current_user.username)
    return {"message": "密码已修改"}


class DeleteAccountRequest(BaseModel):
    password: str


@router.delete("/account")
async def delete_account(
    data: DeleteAccountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.password, current_user.hashed_password):
        raise HTTPException(400, "密码错误")
    current_user.deleted_at = datetime.now(timezone.utc)
    current_user.is_active = False
    await db.commit()
    logger.info("ACCOUNT_DELETED user=%s", current_user.username)
    return {"message": "账号已注销"}


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    data: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.nickname is not None:
        current_user.nickname = data.nickname.strip()[:100] if data.nickname.strip() else None
    if data.email is not None:
        existing = (await db.execute(
            select(User).where(User.email == data.email, User.id != current_user.id, User.deleted_at.is_(None))
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(400, "邮箱已被占用")
        current_user.email = data.email
    if data.avatar_url is not None:
        if data.avatar_url:
            from urllib.parse import urlparse
            try:
                parsed = urlparse(data.avatar_url)
                if parsed.scheme not in ('http', 'https', ''):
                    raise HTTPException(400, "头像 URL 仅允许 http/https 协议")
            except Exception:
                raise HTTPException(400, "无效的头像 URL")
        current_user.avatar_url = data.avatar_url
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)
