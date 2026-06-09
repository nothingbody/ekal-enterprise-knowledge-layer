"""Auth bridge — proxy login/register through the central server.

When cloud mode is enabled, user credentials are verified against the central
server. A local shadow user is created/updated so that the rest of the desktop
backend (knowledge bases, conversations, etc.) still works against the local
database without any changes.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app._version import __version__
from app.cloud.client import cloud_login, cloud_register, is_cloud_enabled
from app.cloud.sync import (
    get_device_id,
    get_device_name,
    get_os_info,
    set_cloud_tokens,
)
from app.models.user import User, UserRole
from app.schemas.user import UserResponse
from app.core.security import hash_password, create_access_token, create_refresh_token

logger = logging.getLogger(__name__)


def _extract_cloud_error_detail(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            data = exc.response.json()
        except Exception:
            data = None
        if isinstance(data, dict):
            detail = data.get("detail")
            if isinstance(detail, str) and detail.strip():
                return detail
        text = exc.response.text.strip()
        if text:
            return text
    return str(exc) or "中心认证服务异常"


def _raise_cloud_auth_error(exc: Exception, action: str) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if 300 <= status < 400:
            raise HTTPException(
                status_code=502,
                detail=f"中心认证服务返回了重定向 ({status})，请检查 CENTRAL_SERVER_URL 是否使用了 HTTPS",
            ) from exc
        raise HTTPException(
            status_code=status,
            detail=_extract_cloud_error_detail(exc),
        ) from exc
    if isinstance(exc, httpx.RequestError):
        raise HTTPException(
            status_code=503,
            detail=f"无法连接中心认证服务，{action}失败",
        ) from exc
    raise HTTPException(
        status_code=502,
        detail=f"中心认证服务异常，{action}失败",
    ) from exc


async def bridge_login(
    db: AsyncSession,
    username: str,
    password: str,
) -> Optional[dict]:
    """Attempt cloud login → sync local user → return local token bundle.

    Returns None if cloud is disabled, letting the caller fall through to
    the normal local-only login flow.
    """
    if not is_cloud_enabled():
        return None

    try:
        device_id = get_device_id()
        from app.cloud.sync import get_cached_client_ip
        client_ip = get_cached_client_ip()
        os_info_str = get_os_info()
        if client_ip:
            os_info_str = f"{os_info_str} ip={client_ip}"
        cloud_resp = await cloud_login(
            username=username,
            password=password,
            device_id=device_id,
            device_name=get_device_name(),
            os_info=os_info_str,
            app_version=__version__,
        )
    except Exception as exc:
        logger.warning("Cloud login failed: %s", exc)
        _raise_cloud_auth_error(exc, "登录")

    cloud_user = cloud_resp.get("user", {})
    cloud_access = cloud_resp.get("access_token", "")
    cloud_refresh = cloud_resp.get("refresh_token", "")

    set_cloud_tokens(cloud_access, cloud_refresh)

    local_user = await _sync_local_user(db, cloud_user, password)
    await _sync_quota_from_cloud(db, local_user.id, cloud_user)
    _trigger_model_sync_after_login()

    local_access = create_access_token(data={"sub": str(local_user.id)})
    local_refresh = create_refresh_token(data={"sub": str(local_user.id)})

    return {
        "access_token": local_access,
        "refresh_token": local_refresh,
        "token_type": "bearer",
        "user": UserResponse.model_validate(local_user).model_dump(mode="json"),
    }


async def bridge_register(
    db: AsyncSession,
    username: str,
    email: str,
    password: str,
    invite_code: Optional[str] = None,
) -> Optional[dict]:
    """Register on the central server, then create a local shadow user.

    Returns None if cloud is disabled.
    """
    if not is_cloud_enabled():
        return None

    try:
        cloud_user = await cloud_register(username, email, password, invite_code)
    except Exception as exc:
        logger.warning("Cloud register failed: %s", exc)
        _raise_cloud_auth_error(exc, "注册")

    local_user = await _sync_local_user(db, cloud_user, password)

    return UserResponse.model_validate(local_user).model_dump(mode="json")


def _normalize_role(role_value: str | None) -> UserRole:
    role = str(role_value or "").lower()
    if role in ("admin", "super_admin", "org_admin"):
        return UserRole.ADMIN
    return UserRole.USER


async def sync_local_user_from_cloud(
    db: AsyncSession,
    cloud_user: dict,
) -> User:
    return await _sync_local_user(db, cloud_user, None)


async def _sync_local_user(
    db: AsyncSession,
    cloud_user: dict,
    password: str | None,
) -> User:
    """Create or update a local shadow user matching the cloud account."""
    cloud_user_id = cloud_user.get("id")
    cloud_username = cloud_user.get("username", "")
    cloud_email = cloud_user.get("email", "")
    cloud_role = _normalize_role(cloud_user.get("role"))
    cloud_is_active = bool(cloud_user.get("is_active", True))
    cloud_must_change_password = bool(cloud_user.get("must_change_password", False))
    password_seed = password or f"cloud:{cloud_username or cloud_email or 'user'}"

    if cloud_user_id is not None:
        result = await db.execute(select(User).where(User.cloud_user_id == int(cloud_user_id)))
        local_user = result.scalar_one_or_none()
    else:
        local_user = None

    if not local_user:
        result = await db.execute(select(User).where(User.username == cloud_username))
        local_user = result.scalar_one_or_none()

    if local_user:
        if cloud_user_id is not None:
            local_user.cloud_user_id = int(cloud_user_id)
        local_user.email = cloud_email
        if password is not None:
            local_user.hashed_password = hash_password(password_seed)
        local_user.role = cloud_role
        local_user.is_active = cloud_is_active
        local_user.must_change_password = cloud_must_change_password
    else:
        local_user = User(
            cloud_user_id=int(cloud_user_id) if cloud_user_id is not None else None,
            username=cloud_username,
            email=cloud_email,
            hashed_password=hash_password(password_seed),
            role=cloud_role,
            is_active=cloud_is_active,
            must_change_password=cloud_must_change_password,
        )
        db.add(local_user)

    await db.commit()
    await db.refresh(local_user)
    return local_user


def _trigger_model_sync_after_login() -> None:
    """Fire-and-forget model + agent/MCP sync so shared configs are available immediately after login."""
    import asyncio
    try:
        from app.cloud.sync import do_model_sync, do_agent_mcp_sync
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(do_model_sync())
            asyncio.ensure_future(do_agent_mcp_sync())
    except Exception as exc:
        logger.debug("Failed to trigger sync after login: %s", exc)


async def _sync_quota_from_cloud(
    db: AsyncSession,
    local_user_id: int,
    cloud_user: dict,
) -> None:
    """Sync quota from the central server user record to the local user_quotas table."""
    cloud_plan = cloud_user.get("plan")
    if not cloud_plan:
        return

    try:
        from app.models.user_quota import UserQuota

        result = await db.execute(
            select(UserQuota).where(UserQuota.user_id == local_user_id)
        )
        quota = result.scalar_one_or_none()

        if quota:
            quota.plan = cloud_plan
            quota.trial_total = cloud_user.get("trial_total", quota.trial_total)
            quota.trial_used = cloud_user.get("trial_used", quota.trial_used)
            quota.token_credit = cloud_user.get("token_credit", quota.token_credit)
            quota.token_used = cloud_user.get("token_used", quota.token_used)
        else:
            quota = UserQuota(
                user_id=local_user_id,
                plan=cloud_plan,
                trial_total=cloud_user.get("trial_total", 50),
                trial_used=cloud_user.get("trial_used", 0),
                token_credit=cloud_user.get("token_credit", 0),
                token_used=cloud_user.get("token_used", 0),
            )
            db.add(quota)

        await db.commit()
        logger.info("已从服务器同步用户 %d 的配额: plan=%s", local_user_id, cloud_plan)
    except Exception as exc:
        logger.warning("同步配额失败: %s", exc)
