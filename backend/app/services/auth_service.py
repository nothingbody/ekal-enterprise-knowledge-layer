from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status

from app.config import settings
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserLogin, Token, UserResponse, PasswordChange
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token


async def register_user(db: AsyncSession, data: UserCreate) -> UserResponse:
    user_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    is_first_user = user_count == 0

    if not is_first_user:
        if not settings.ALLOW_REGISTRATION:
            raise HTTPException(status_code=403, detail="管理员已关闭注册，请联系管理员获取账号")
        if settings.INVITE_CODE and (data.invite_code or "").strip() != settings.INVITE_CODE:
            raise HTTPException(status_code=403, detail="邀请码无效")

    existing = await db.execute(
        select(User).where((User.username == data.username) | (User.email == data.email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="注册失败，请检查输入信息")

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=UserRole.ADMIN if is_first_user else UserRole.USER,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


async def ensure_desktop_default_admin(db: AsyncSession) -> User | None:
    if not settings.DESKTOP_MODE:
        return None

    from app.cloud.client import is_cloud_enabled
    if is_cloud_enabled():
        return None

    user_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    if user_count != 0:
        return None

    user = User(
        username="admin",
        email="admin@desktop.local",
        hashed_password=hash_password("123456"),
        must_change_password=True,
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login_user(db: AsyncSession, data: UserLogin, client_ip: str | None = None) -> Token:
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    if not getattr(user, 'is_active', True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用，请联系管理员")

    from datetime import datetime, timezone as tz
    if client_ip:
        user.last_login_ip = client_ip
        user.last_login_at = datetime.now(tz.utc)

    if data.device_id:
        await _upsert_device(db, user.id, data, datetime.now(tz.utc))

    await db.commit()

    if getattr(user, "totp_enabled", False) and getattr(user, "totp_secret", None):
        from datetime import timedelta
        temp_token = create_access_token(
            data={"sub": str(user.id), "type": "2fa_pending"},
            expires_delta=timedelta(minutes=5),
        )
        return Token(
            access_token="",
            refresh_token="",
            user=UserResponse.model_validate(user),
            requires_2fa=True,
            temp_token=temp_token,
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    return Token(access_token=access_token, refresh_token=refresh_token, user=UserResponse.model_validate(user))


async def _upsert_device(db: AsyncSession, user_id: int, data: UserLogin, now) -> None:
    from app.models.device import Device
    result = await db.execute(select(Device).where(Device.device_id == data.device_id))
    dev = result.scalar_one_or_none()
    if dev:
        dev.user_id = user_id
        dev.device_name = data.device_name or dev.device_name
        dev.os_info = data.os_info or dev.os_info
        dev.app_version = data.app_version or dev.app_version
        dev.last_heartbeat = now
        dev.is_active = True
    else:
        db.add(Device(
            user_id=user_id,
            device_id=data.device_id,
            device_name=data.device_name,
            os_info=data.os_info,
            app_version=data.app_version,
        ))


async def change_password(db: AsyncSession, user: User, data: PasswordChange) -> bool:
    if not verify_password(data.old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="原密码错误")

    user.hashed_password = hash_password(data.new_password)
    user.must_change_password = False
    await db.commit()
    return True
