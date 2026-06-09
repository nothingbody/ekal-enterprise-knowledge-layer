from datetime import datetime, timezone, timedelta, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.organization import Organization
from app.models.device import Device
from app.models.usage import UsageReport
from app.models.skill import MarketSkill, SkillStatus
from app.schemas import DashboardStats
from app.core.security import get_admin_user

router = APIRouter()


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    today = date.today()
    online_threshold = datetime.now(timezone.utc) - timedelta(minutes=10)

    total_users = (await db.execute(select(func.count(User.id)).where(User.deleted_at.is_(None)))).scalar() or 0

    active_users_today = (await db.execute(
        select(func.count(func.distinct(UsageReport.user_id)))
        .where(UsageReport.report_date == today)
    )).scalar() or 0

    total_orgs = (await db.execute(select(func.count(Organization.id)).where(Organization.deleted_at.is_(None)))).scalar() or 0
    total_devices = (await db.execute(select(func.count(Device.id)))).scalar() or 0

    online_devices = (await db.execute(
        select(func.count(Device.id)).where(Device.last_heartbeat >= online_threshold)
    )).scalar() or 0

    total_skills = (await db.execute(
        select(func.count(MarketSkill.id)).where(MarketSkill.status == SkillStatus.APPROVED)
    )).scalar() or 0

    pending_skills = (await db.execute(
        select(func.count(MarketSkill.id)).where(MarketSkill.status == SkillStatus.PENDING)
    )).scalar() or 0

    total_tokens_today = (await db.execute(
        select(func.sum(UsageReport.token_count)).where(UsageReport.report_date == today)
    )).scalar() or 0

    total_tokens_total = (await db.execute(
        select(func.sum(UsageReport.token_count))
    )).scalar() or 0

    return DashboardStats(
        total_users=total_users,
        active_users_today=active_users_today,
        total_organizations=total_orgs,
        total_devices=total_devices,
        online_devices=online_devices,
        total_skills=total_skills,
        pending_skills=pending_skills,
        total_tokens_today=total_tokens_today,
        total_tokens_total=total_tokens_total,
    )


async def _get_config_value(db: AsyncSession, key: str, default):
    """Get config from DB or return default."""
    from app.models.system_config import SystemConfig
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    row = result.scalar_one_or_none()
    if row and row.value is not None:
        if key == "allow_registration":
            return row.value.lower() in ("1", "true", "yes")
        return row.value
    return default


@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    allow_reg = await _get_config_value(db, "allow_registration", settings.ALLOW_REGISTRATION)
    invite = await _get_config_value(db, "invite_code", settings.INVITE_CODE)
    return {
        "allow_registration": allow_reg,
        "invite_code": invite,
        "cors_origins": settings.CORS_ORIGINS,
        "app_name": settings.APP_NAME,
    }


class SettingsUpdate(BaseModel):
    allow_registration: Optional[bool] = None
    invite_code: Optional[str] = None


@router.put("/settings")
async def update_settings(
    data: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    from app.models.system_config import SystemConfig
    if data.allow_registration is not None:
        val = str(data.allow_registration).lower()
        settings.ALLOW_REGISTRATION = data.allow_registration
        existing = (await db.execute(select(SystemConfig).where(SystemConfig.key == "allow_registration"))).scalar_one_or_none()
        if existing:
            existing.value = val
        else:
            db.add(SystemConfig(key="allow_registration", value=val))
    if data.invite_code is not None:
        settings.INVITE_CODE = data.invite_code
        existing = (await db.execute(select(SystemConfig).where(SystemConfig.key == "invite_code"))).scalar_one_or_none()
        if existing:
            existing.value = data.invite_code
        else:
            db.add(SystemConfig(key="invite_code", value=data.invite_code))

    await db.commit()

    from app.core.audit import record_audit
    await record_audit(
        db, user_id=admin.id, username=admin.username,
        action="update_settings", resource_type="settings",
        detail=str(data.model_dump(exclude_none=True)),
    )

    return {
        "allow_registration": settings.ALLOW_REGISTRATION,
        "invite_code": settings.INVITE_CODE,
    }


@router.get("/audit-logs")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    from app.models.audit_log import AuditLog

    filters = []
    if action:
        filters.append(AuditLog.action == action)
    if user_id:
        filters.append(AuditLog.user_id == user_id)
    if search:
        from sqlalchemy import or_
        from app.core.utils import escape_like
        keyword = f"%{escape_like(search)}%"
        filters.append(or_(
            AuditLog.username.ilike(keyword),
            AuditLog.detail.ilike(keyword),
            AuditLog.resource_type.ilike(keyword),
        ))
    if start_date:
        from datetime import datetime
        try:
            filters.append(AuditLog.created_at >= datetime.fromisoformat(start_date))
        except ValueError:
            pass
    if end_date:
        from datetime import datetime, timedelta
        try:
            end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
            filters.append(AuditLog.created_at < end_dt)
        except ValueError:
            pass

    total = (await db.execute(select(func.count(AuditLog.id)).where(*filters))).scalar() or 0
    result = await db.execute(
        select(AuditLog).where(*filters)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    logs = result.scalars().all()

    return {
        "items": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "username": log.username,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "detail": log.detail,
                "ip_address": log.ip_address,
                "status_code": log.status_code,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/server-logs")
async def get_server_logs(
    limit: int = Query(100, ge=1, le=500),
    level: Optional[str] = None,
    _admin: User = Depends(get_admin_user),
):
    """Admin: view recent server application logs."""
    from app.core.log_buffer import get_recent_logs
    return {"items": get_recent_logs(limit, level)}


class QuotaUpdate(BaseModel):
    plan: Optional[str] = None
    trial_total: Optional[int] = None
    trial_used: Optional[int] = None
    token_credit: Optional[int] = None
    token_used: Optional[int] = None


@router.get("/users/{user_id}/quota")
async def get_user_quota(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    return {
        "user_id": user.id,
        "username": user.username,
        "plan": user.plan,
        "trial_total": user.trial_total,
        "trial_used": user.trial_used,
        "trial_remaining": max(0, user.trial_total - user.trial_used),
        "token_credit": user.token_credit,
        "token_used": user.token_used,
        "token_remaining": max(0, user.token_credit - user.token_used),
    }


@router.put("/users/{user_id}/quota")
async def update_user_quota(
    user_id: int,
    data: QuotaUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")

    if data.plan is not None:
        user.plan = data.plan
    if data.trial_total is not None:
        user.trial_total = data.trial_total
    if data.trial_used is not None:
        user.trial_used = data.trial_used
    if data.token_credit is not None:
        user.token_credit = data.token_credit
    if data.token_used is not None:
        user.token_used = data.token_used

    await db.commit()
    await db.refresh(user)
    return {
        "message": "额度已更新",
        "plan": user.plan,
        "trial_total": user.trial_total,
        "trial_used": user.trial_used,
        "token_credit": user.token_credit,
        "token_used": user.token_used,
    }


@router.post("/users/{user_id}/add-credit")
async def add_user_credit(
    user_id: int,
    amount: int = Query(ge=1),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")

    user.token_credit += amount
    if user.plan == "trial":
        user.plan = "basic"
    await db.commit()
    return {
        "message": f"已添加 {amount} 算力额度",
        "plan": user.plan,
        "token_credit": user.token_credit,
    }
