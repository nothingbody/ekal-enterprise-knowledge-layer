import asyncio
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.database import get_db
from pydantic import BaseModel, Field
from app.schemas.user import UserCreate, UserLogin, Token, UserResponse, PasswordChange, RefreshTokenRequest, ProfileUpdate, LogoutRequest


class TwoFAEnableRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=10, description="TOTP 验证码")


class TwoFADisableRequest(BaseModel):
    password: str = Field(..., min_length=1, description="用户密码")


class TwoFAVerifyRequest(BaseModel):
    temp_token: str = Field(..., min_length=1, description="临时令牌")
    code: str = Field(..., min_length=1, max_length=10, description="TOTP 验证码")
from app.services.auth_service import register_user, login_user, change_password
from app.core.security import get_current_user, revoke_token, hash_password, verify_password
from app.cloud.client import is_cloud_enabled
from app.models.user import User
from fastapi.security import OAuth2PasswordBearer

_audit = logging.getLogger("audit")
router = APIRouter()


def _raise_cloud_proxy_error(exc: Exception, action: str) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if 300 <= status < 400:
            raise HTTPException(
                status_code=502,
                detail=f"中心认证服务返回了重定向 ({status})，请检查 CENTRAL_SERVER_URL 是否使用了 HTTPS",
            ) from exc
        try:
            payload = exc.response.json()
        except Exception:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("detail"), str) and payload["detail"].strip():
            detail = payload["detail"]
        else:
            detail = exc.response.text.strip() or f"中心认证服务{action}失败"
        raise HTTPException(status_code=status, detail=detail) from exc
    if isinstance(exc, httpx.RequestError):
        raise HTTPException(status_code=503, detail=f"无法连接中心认证服务，{action}失败") from exc
    raise HTTPException(status_code=502, detail=f"中心认证服务异常，{action}失败") from exc


def _detect_limiter_storage() -> str:
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=0.5)
        r.ping()
        r.close()
        return settings.REDIS_URL
    except Exception:
        return "memory://"


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://" if getattr(settings, "DESKTOP_MODE", False) else _detect_limiter_storage(),
)


@router.get("/register-config")
async def register_config():
    if is_cloud_enabled():
        try:
            from app.cloud.client import cloud_get_register_config
            return await cloud_get_register_config()
        except Exception as exc:
            _raise_cloud_proxy_error(exc, "获取注册配置")
    return {
        "allow_registration": settings.ALLOW_REGISTRATION,
        "require_invite_code": bool(settings.INVITE_CODE),
    }


@router.post("/register", response_model=UserResponse)
@limiter.limit("5/minute")
async def register(request: Request, data: UserCreate, db: AsyncSession = Depends(get_db)):
    client_ip = request.client.host if request.client else "-"
    if is_cloud_enabled():
        try:
            from app.cloud.auth_bridge import bridge_register
            cloud_result = await bridge_register(
                db, data.username, data.email, data.password,
                invite_code=getattr(data, "invite_code", None),
            )
            _audit.info("REGISTER_OK(cloud) user=%s ip=%s", data.username, client_ip)
            return cloud_result
        except HTTPException:
            _audit.warning("REGISTER_FAIL user=%s ip=%s", data.username, client_ip)
            raise
        except Exception as exc:
            _audit.warning("CLOUD_REGISTER_ERR user=%s ip=%s err=%s", data.username, client_ip, exc)
            if settings.DESKTOP_MODE:
                try:
                    user = await register_user(db, data)
                    _audit.info("REGISTER_OK(local_fallback) user=%s ip=%s", data.username, client_ip)
                    return user
                except HTTPException:
                    pass
            _raise_cloud_proxy_error(exc, "注册")
    try:
        user = await register_user(db, data)
        _audit.info("REGISTER_OK user=%s ip=%s", data.username, client_ip)
        return user
    except HTTPException:
        _audit.warning("REGISTER_FAIL user=%s ip=%s", data.username, client_ip)
        raise


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(request: Request, data: UserLogin, db: AsyncSession = Depends(get_db)):
    client_ip = request.client.host if request.client else "-"
    if is_cloud_enabled():
        try:
            from app.cloud.auth_bridge import bridge_login
            cloud_result = await bridge_login(db, data.username, data.password)
            _audit.info("LOGIN_OK(cloud) user=%s ip=%s", data.username, client_ip)
            return cloud_result
        except HTTPException as he:
            if settings.DESKTOP_MODE:
                try:
                    token = await login_user(db, data, client_ip=client_ip)
                    _audit.info("LOGIN_OK(local_fallback) user=%s ip=%s", data.username, client_ip)
                    return token
                except HTTPException as le:
                    _audit.warning("LOGIN_FAIL user=%s ip=%s", data.username, client_ip)
                    raise le
            _audit.warning("LOGIN_FAIL user=%s ip=%s", data.username, client_ip)
            raise he
        except Exception as exc:
            _audit.warning("CLOUD_LOGIN_ERR user=%s ip=%s err=%s", data.username, client_ip, exc)
            if settings.DESKTOP_MODE:
                try:
                    token = await login_user(db, data, client_ip=client_ip)
                    _audit.info("LOGIN_OK(local_fallback) user=%s ip=%s", data.username, client_ip)
                    return token
                except HTTPException:
                    pass
            _raise_cloud_proxy_error(exc, "登录")
    try:
        token = await login_user(db, data, client_ip=client_ip)
        _audit.info("LOGIN_OK user=%s ip=%s", data.username, client_ip)
        return token
    except HTTPException:
        _audit.warning("LOGIN_FAIL user=%s ip=%s", data.username, client_ip)
        raise


@router.post("/refresh")
@limiter.limit("20/minute")
async def refresh_token(request: Request, data: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    import jwt as pyjwt
    from jwt.exceptions import PyJWTError
    from app.core.security import create_access_token, create_refresh_token

    token = data.refresh_token
    try:
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(401, "无效的 token 类型")
        user_id = int(payload["sub"])
    except (PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "refresh_token 无效或已过期")

    from app.core.security import is_token_revoked
    jti = payload.get("jti")
    if jti and await is_token_revoked(jti):
        raise HTTPException(401, "refresh_token 已被吊销")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not getattr(user, "is_active", True):
        raise HTTPException(401, "用户不存在或已禁用")

    await revoke_token(token)

    new_access = create_access_token(data={"sub": str(user.id)})
    new_refresh = create_refresh_token(data={"sub": str(user.id)})
    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserResponse)
async def get_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if is_cloud_enabled():
        try:
            from app.cloud.sync import ensure_cloud_token
            from app.cloud.client import cloud_get_me
            from app.cloud.auth_bridge import sync_local_user_from_cloud
            token = await ensure_cloud_token()
            if token:
                cloud_user = await cloud_get_me(token)
                local_user = await sync_local_user_from_cloud(db, cloud_user)
                return UserResponse.model_validate(local_user)
        except HTTPException:
            raise
        except Exception:
            pass
    return UserResponse.model_validate(current_user)


@router.post("/change-password")
async def api_change_password(
    data: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if is_cloud_enabled():
        try:
            from app.cloud.sync import ensure_cloud_token
            from app.cloud.client import cloud_change_password as _cloud_change_password
            token = await ensure_cloud_token()
            if not token:
                raise HTTPException(status_code=401, detail="中心认证已失效，请重新登录")
            result = await _cloud_change_password(token, data.old_password, data.new_password)
            current_user.hashed_password = hash_password(data.new_password)
            current_user.must_change_password = False
            await db.commit()
            return result
        except HTTPException:
            raise
        except Exception as exc:
            _raise_cloud_proxy_error(exc, "修改密码")
    await change_password(db, current_user, data)
    return {"message": "密码修改成功"}


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    data: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if is_cloud_enabled():
        try:
            from app.cloud.sync import ensure_cloud_token
            from app.cloud.client import cloud_update_profile as _cloud_update_profile
            from app.cloud.auth_bridge import sync_local_user_from_cloud
            token = await ensure_cloud_token()
            if not token:
                raise HTTPException(status_code=401, detail="中心认证已失效，请重新登录")
            cloud_user = await _cloud_update_profile(token, data.model_dump(exclude_none=True))
            local_user = await sync_local_user_from_cloud(db, cloud_user)
            return UserResponse.model_validate(local_user)
        except HTTPException:
            raise
        except Exception as exc:
            _raise_cloud_proxy_error(exc, "更新资料")
    new_email = data.email
    if new_email and new_email != current_user.email:
        existing = await db.execute(select(User).where(User.email == new_email, User.id != current_user.id))
        if existing.scalar_one_or_none():
            raise HTTPException(400, "该邮箱已被其他用户使用")
        current_user.email = new_email
    if data.nickname is not None:
        current_user.nickname = data.nickname
    if data.avatar_url is not None:
        current_user.avatar_url = data.avatar_url
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)


class DeleteAccountRequest(BaseModel):
    password: str


@router.delete("/account")
async def delete_account(
    data: DeleteAccountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if is_cloud_enabled():
        try:
            from app.cloud.sync import ensure_cloud_token, clear_cloud_tokens
            from app.cloud.client import cloud_delete_account as _cloud_delete_account
            token = await ensure_cloud_token()
            if not token:
                raise HTTPException(status_code=401, detail="中心认证已失效，请重新登录")
            result = await _cloud_delete_account(token, data.password)
            current_user.is_active = False
            await db.commit()
            clear_cloud_tokens()
            _audit.info("ACCOUNT_DELETED user=%s id=%d", current_user.username, current_user.id)
            return result
        except HTTPException:
            raise
        except Exception as exc:
            _raise_cloud_proxy_error(exc, "注销账号")
    if not verify_password(data.password, current_user.hashed_password):
        raise HTTPException(400, "密码错误")
    from datetime import datetime, timezone
    current_user.deleted_at = datetime.now(timezone.utc)
    current_user.is_active = False
    await db.commit()
    _audit.info("ACCOUNT_DELETED user=%s id=%d (soft-delete)", current_user.username, current_user.id)
    return {"message": "账号已注销"}


@router.post("/2fa/setup")
async def setup_2fa(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a TOTP secret and return the provisioning URI for QR code scanning."""
    import pyotp
    from app.core.encryption import encrypt_value

    if current_user.totp_enabled:
        raise HTTPException(400, "双因素认证已启用")

    secret = pyotp.random_base32()
    current_user.totp_secret = encrypt_value(secret, settings.SECRET_KEY)
    await db.commit()

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=current_user.username, issuer_name=settings.APP_NAME)
    return {"secret": secret, "uri": uri}


@router.post("/2fa/enable")
async def enable_2fa(
    data: TwoFAEnableRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify a TOTP code and enable 2FA."""
    import pyotp
    from app.core.encryption import decrypt_value

    code = data.code.strip()

    if not current_user.totp_secret:
        raise HTTPException(400, "请先调用 /2fa/setup 生成密钥")

    secret = decrypt_value(current_user.totp_secret, settings.SECRET_KEY)
    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(400, "验证码错误，请重试")

    current_user.totp_enabled = True
    await db.commit()
    _audit.info("2FA_ENABLED user_id=%d", current_user.id)
    return {"message": "双因素认证已启用"}


@router.post("/2fa/disable")
async def disable_2fa(
    data: TwoFADisableRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Disable 2FA after password verification."""
    if not verify_password(data.password, current_user.hashed_password):
        raise HTTPException(400, "密码错误")

    current_user.totp_enabled = False
    current_user.totp_secret = None
    await db.commit()
    _audit.info("2FA_DISABLED user_id=%d", current_user.id)
    return {"message": "双因素认证已关闭"}


@router.post("/2fa/verify")
@limiter.limit("3/minute")
async def verify_2fa(
    request: Request,
    data: TwoFAVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify TOTP code during login (step 2 of 2FA login)."""
    import pyotp
    from app.core.encryption import decrypt_value

    temp_token = data.temp_token
    code = data.code.strip()

    try:
        import jwt as pyjwt
        payload = pyjwt.decode(temp_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "2fa_pending":
            raise HTTPException(401, "无效的临时令牌")
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(401, "临时令牌无效或已过期")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.totp_secret:
        raise HTTPException(401, "用户不存在")

    secret = decrypt_value(user.totp_secret, settings.SECRET_KEY)
    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(400, "验证码错误")

    from app.core.security import create_access_token, create_refresh_token
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    from app.schemas.user import UserResponse
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user).model_dump(mode="json"),
    }


@router.post("/logout")
async def logout(
    request: Request,
    data: LogoutRequest = None,
    current_user: User = Depends(get_current_user),
):
    if is_cloud_enabled():
        try:
            from app.cloud.sync import ensure_cloud_token, clear_cloud_tokens
            from app.cloud.client import cloud_logout as _cloud_logout
            token = await ensure_cloud_token()
            if token:
                try:
                    await _cloud_logout(token)
                except Exception:
                    pass
            clear_cloud_tokens()
        except Exception:
            pass
    auth_header = request.headers.get("Authorization", "")
    access_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    revoked_access = False
    revoked_refresh = False
    if access_token:
        revoked_access = await revoke_token(access_token)
    if data and data.refresh_token:
        revoked_refresh = await revoke_token(data.refresh_token)
    return {"message": "已登出", "revoked": revoked_access or revoked_refresh}
