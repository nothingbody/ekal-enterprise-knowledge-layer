import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User
from app.models.device import Device
from app.models.usage import UsageReport
from app.schemas import UserResponse, UserUpdate, PaginatedResponse, ModelConfigCreate, ModelConfigUpdate
from app.core.security import get_admin_user, hash_password
from app.core.audit import record_audit

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    role: Optional[str] = None,
    org_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    filters = [User.deleted_at.is_(None)]
    if search:
        from app.core.utils import escape_like
        s = escape_like(search)
        filters.append(User.username.ilike(f"%{s}%") | User.email.ilike(f"%{s}%"))
    if role:
        filters.append(User.role == role)
    if org_id is not None:
        filters.append(User.org_id == org_id)

    total = (await db.execute(select(func.count(User.id)).where(*filters))).scalar() or 0

    device_count_sub = (
        select(Device.user_id, func.count(Device.id).label("device_count"))
        .group_by(Device.user_id)
        .subquery()
    )
    result = await db.execute(
        select(User, func.coalesce(device_count_sub.c.device_count, 0).label("dc"))
        .outerjoin(device_count_sub, User.id == device_count_sub.c.user_id)
        .where(*filters)
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    items = []
    for u, dc in result.all():
        d = UserResponse.model_validate(u).model_dump()
        d["device_count"] = dc
        items.append(d)

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/analytics")
async def user_analytics(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Admin: list all users with aggregated usage stats from synced data."""
    from app.models.synced_user_data import SyncedOperationLog
    from app.models.chat import ChatConversation, ChatMessage
    from sqlalchemy import literal_column

    total = (await db.execute(
        select(func.count(User.id)).where(User.deleted_at.is_(None))
    )).scalar() or 0

    conv_sub = (
        select(ChatConversation.user_id, func.count(ChatConversation.id).label("conv_count"))
        .group_by(ChatConversation.user_id).subquery()
    )
    msg_sub = (
        select(ChatConversation.user_id, func.count(ChatMessage.id).label("msg_count"))
        .join(ChatMessage, ChatMessage.conversation_id == ChatConversation.id)
        .group_by(ChatConversation.user_id).subquery()
    )
    usage_sub = (
        select(UsageReport.user_id, func.coalesce(func.sum(UsageReport.token_count), 0).label("usage_tokens"))
        .group_by(UsageReport.user_id).subquery()
    )
    log_sub = (
        select(
            SyncedOperationLog.user_id,
            func.coalesce(func.sum(SyncedOperationLog.total_tokens), 0).label("log_tokens"),
            func.avg(SyncedOperationLog.latency_ms).label("avg_latency"),
            func.max(SyncedOperationLog.remote_created_at).label("last_active"),
        )
        .group_by(SyncedOperationLog.user_id).subquery()
    )

    query = (
        select(
            User,
            func.coalesce(conv_sub.c.conv_count, 0).label("conv_count"),
            func.coalesce(msg_sub.c.msg_count, 0).label("msg_count"),
            func.coalesce(usage_sub.c.usage_tokens, 0).label("usage_tokens"),
            func.coalesce(log_sub.c.log_tokens, 0).label("log_tokens"),
            log_sub.c.avg_latency,
            log_sub.c.last_active,
        )
        .outerjoin(conv_sub, User.id == conv_sub.c.user_id)
        .outerjoin(msg_sub, User.id == msg_sub.c.user_id)
        .outerjoin(usage_sub, User.id == usage_sub.c.user_id)
        .outerjoin(log_sub, User.id == log_sub.c.user_id)
        .where(User.deleted_at.is_(None))
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )

    result = await db.execute(query)
    items = []
    for row in result.all():
        u = row[0]
        usage_tokens = int(row.usage_tokens or 0)
        log_tokens = int(row.log_tokens or 0)
        items.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role.value if hasattr(u.role, "value") else str(u.role),
            "is_active": u.is_active,
            "created_at": str(u.created_at),
            "conv_count": int(row.conv_count or 0),
            "msg_count": int(row.msg_count or 0),
            "total_tokens": max(usage_tokens, log_tokens),
            "avg_latency": round(float(row.avg_latency), 1) if row.avg_latency else 0,
            "last_active": str(row.last_active) if row.last_active else None,
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    if user.id == admin.id and data.is_active is False:
        raise HTTPException(400, "不能禁用自己")

    if data.password is not None:
        user.hashed_password = hash_password(data.password)
    if data.role is not None:
        # Prevent assigning a role higher than the admin's own role
        from app.core.security import ROLE_HIERARCHY
        admin_level = ROLE_HIERARCHY.get(admin.role, 0)
        target_level = ROLE_HIERARCHY.get(data.role, 0)
        if target_level > admin_level:
            raise HTTPException(403, "不能分配高于自身的角色")
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.org_id is not None:
        user.org_id = data.org_id

    await db.commit()
    await db.refresh(user)
    changes = data.model_dump(exclude_none=True)
    logger.info("USER_UPDATE admin=%s target=%s changes=%s", admin.username, user.username, changes)
    await record_audit(
        db, user_id=admin.id, username=admin.username,
        action="update_user", resource_type="user", resource_id=str(user.id),
        detail=str(changes),
    )
    return UserResponse.model_validate(user)


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")

    import secrets
    new_password = secrets.token_urlsafe(10)
    user.hashed_password = hash_password(new_password)
    await db.commit()
    logger.info("PASSWORD_RESET admin=%s target=%s", admin.username, user.username)
    await record_audit(
        db, user_id=admin.id, username=admin.username,
        action="reset_password", resource_type="user", resource_id=str(user_id),
        detail=f"reset password for {user.username}",
    )
    return {"message": "密码已重置", "temp_password": new_password}


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    if user_id == admin.id:
        raise HTTPException(400, "不能删除自己")
    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")

    from datetime import datetime, timezone
    user.deleted_at = datetime.now(timezone.utc)
    user.is_active = False
    await db.commit()
    logger.info("USER_DELETE admin=%s target=%s", admin.username, user.username)
    await record_audit(
        db, user_id=admin.id, username=admin.username,
        action="delete_user", resource_type="user", resource_id=str(user_id),
        detail=f"deleted user {user.username}",
    )
    return {"message": "用户已删除"}


@router.get("/{user_id}/audit-logs")
async def user_audit_logs(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Admin: list audit logs for a specific user."""
    from app.models.audit_log import AuditLog
    total = (await db.execute(
        select(func.count(AuditLog.id)).where(AuditLog.user_id == user_id)
    )).scalar() or 0
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.user_id == user_id)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        {
            "id": log.id,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "detail": log.detail,
            "ip_address": log.ip_address,
            "created_at": str(log.created_at) if log.created_at else None,
        }
        for log in result.scalars().all()
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{user_id}/devices")
async def user_devices(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Admin: list devices for a specific user."""
    result = await db.execute(
        select(Device)
        .where(Device.user_id == user_id)
        .order_by(Device.last_heartbeat.desc())
    )
    items = [
        {
            "id": d.id,
            "device_id": d.device_id,
            "device_name": d.device_name,
            "os_info": d.os_info,
            "app_version": d.app_version,
            "is_active": d.is_active,
            "last_heartbeat": str(d.last_heartbeat) if d.last_heartbeat else None,
            "created_at": str(d.created_at) if d.created_at else None,
        }
        for d in result.scalars().all()
    ]
    return {"items": items, "total": len(items)}


@router.get("/{user_id}/models")
async def user_models(
    user_id: int,
    model_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Admin: list model configs created by a specific user."""
    from app.models.model_config import ModelConfig
    query = select(ModelConfig).where(ModelConfig.created_by == user_id)
    if model_type:
        query = query.where(ModelConfig.model_type == model_type)
    query = query.order_by(ModelConfig.created_at.desc())
    result = await db.execute(query)
    items = []
    for m in result.scalars().all():
        items.append({
            "id": m.id,
            "org_id": m.org_id,
            "created_by": m.created_by,
            "model_type": m.model_type.value if hasattr(m.model_type, "value") else str(m.model_type),
            "provider": m.provider.value if hasattr(m.provider, "value") else str(m.provider),
            "api_base": m.api_base,
            "model_name": m.model_name,
            "display_name": m.display_name,
            "params": m.params,
            "is_default": m.is_default,
            "is_shared": m.is_shared,
            "created_at": str(m.created_at),
            "api_key_set": bool(m.api_key_encrypted),
        })
    return {"items": items, "total": len(items)}


@router.post("/{user_id}/models")
async def admin_create_user_model(
    user_id: int,
    data: ModelConfigCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Admin: create a model config for a specific user."""
    from app.models.model_config import ModelConfig
    from app.core.encryption import encrypt_value

    target = (await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))).scalar_one_or_none()
    if not target:
        raise HTTPException(404, "用户不存在")

    model = ModelConfig(
        org_id=target.org_id,
        created_by=user_id,
        model_type=data.model_type,
        provider=data.provider,
        api_base=data.api_base,
        api_key_encrypted=encrypt_value(data.api_key) if data.api_key else None,
        model_name=data.model_name,
        display_name=data.display_name,
        params=data.params,
        is_default=data.is_default,
        is_shared=getattr(data, "is_shared", False),
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    await record_audit(
        db, user_id=admin.id, username=admin.username,
        action="admin_create_model", resource_type="model_config", resource_id=str(model.id),
        detail=f"为用户 {user_id} 创建模型 {model.model_name}",
    )
    return {"id": model.id, "message": "已创建"}


@router.put("/{user_id}/models/{model_id}")
async def admin_update_user_model(
    user_id: int,
    model_id: int,
    data: ModelConfigUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Admin: update a user's model config (including API key)."""
    from app.models.model_config import ModelConfig
    from app.core.encryption import encrypt_value

    result = await db.execute(
        select(ModelConfig).where(ModelConfig.id == model_id, ModelConfig.created_by == user_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "模型配置不存在")

    update_data = data.model_dump(exclude_unset=True)
    changed_fields = list(update_data.keys())

    if "api_key" in update_data:
        raw_key = update_data.pop("api_key")
        if raw_key:
            update_data["api_key_encrypted"] = encrypt_value(raw_key)
        elif raw_key == "":
            update_data["api_key_encrypted"] = None

    for key, value in update_data.items():
        if hasattr(model, key):
            setattr(model, key, value)

    await db.commit()
    await db.refresh(model)
    await record_audit(
        db, user_id=admin.id, username=admin.username,
        action="admin_update_model", resource_type="model_config", resource_id=str(model_id),
        detail=f"更新用户 {user_id} 的模型 {model.model_name}，字段: {','.join(changed_fields)}",
    )
    return {"id": model.id, "message": "已更新"}


@router.delete("/{user_id}/models/{model_id}")
async def admin_delete_user_model(
    user_id: int,
    model_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Admin: delete a user's model config."""
    from app.models.model_config import ModelConfig
    result = await db.execute(
        select(ModelConfig).where(ModelConfig.id == model_id, ModelConfig.created_by == user_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "模型配置不存在")

    model_name = model.model_name
    await db.delete(model)
    await db.commit()
    await record_audit(
        db, user_id=admin.id, username=admin.username,
        action="admin_delete_model", resource_type="model_config", resource_id=str(model_id),
        detail=f"删除用户 {user_id} 的模型 {model_name}",
    )
    return {"message": "模型配置已删除"}


@router.get("/{user_id}/usage")
async def get_user_usage(
    user_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    from datetime import date, timedelta
    start_date = date.today() - timedelta(days=days)
    result = await db.execute(
        select(UsageReport)
        .where(UsageReport.user_id == user_id, UsageReport.report_date >= start_date)
        .order_by(UsageReport.report_date.asc())
    )
    reports = result.scalars().all()
    return [
        {
            "date": str(r.report_date),
            "tokens": r.token_count,
            "conversations": r.conversation_count,
            "messages": r.message_count,
            "kb_count": r.kb_count,
            "doc_count": r.doc_count,
        }
        for r in reports
    ]


@router.get("/{user_id}/usage-detail")
async def get_user_usage_detail(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Admin: get detailed per-model usage breakdown for a user."""
    from app.models.synced_user_data import SyncedUserData
    import json
    result = await db.execute(
        select(SyncedUserData).where(
            SyncedUserData.user_id == user_id,
            SyncedUserData.data_type == "usage_detail",
        )
    )
    row = result.scalar_one_or_none()
    if not row or not row.data:
        return {"by_model": [], "synced_at": None}
    try:
        data = json.loads(row.data)
        data["synced_at"] = str(row.synced_at) if row.synced_at else None
        return data
    except Exception:
        return {"by_model": [], "synced_at": None}


@router.get("/{user_id}/operation-logs")
async def get_user_operation_logs(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Admin: list synced operation logs for a specific user."""
    from app.models.synced_user_data import SyncedOperationLog

    filters = [SyncedOperationLog.user_id == user_id]
    if action:
        filters.append(SyncedOperationLog.action == action)

    total = (await db.execute(
        select(func.count(SyncedOperationLog.id)).where(*filters)
    )).scalar() or 0

    result = await db.execute(
        select(SyncedOperationLog)
        .where(*filters)
        .order_by(SyncedOperationLog.remote_created_at.desc().nullslast(), SyncedOperationLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    logs = result.scalars().all()

    return {
        "items": [
            {
                "id": log.id,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "detail": log.detail,
                "ip_address": log.ip_address,
                "prompt_tokens": log.prompt_tokens,
                "completion_tokens": log.completion_tokens,
                "total_tokens": log.total_tokens,
                "latency_ms": log.latency_ms,
                "device_id": log.device_id,
                "created_at": log.remote_created_at.isoformat() if log.remote_created_at else None,
                "synced_at": log.synced_at.isoformat() if log.synced_at else None,
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{user_id}/token-summary")
async def get_user_token_summary(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Admin: get aggregated token consumption summary for a user from operation logs."""
    from app.models.synced_user_data import SyncedOperationLog

    total_prompt = (await db.execute(
        select(func.coalesce(func.sum(SyncedOperationLog.prompt_tokens), 0))
        .where(SyncedOperationLog.user_id == user_id)
    )).scalar() or 0

    total_completion = (await db.execute(
        select(func.coalesce(func.sum(SyncedOperationLog.completion_tokens), 0))
        .where(SyncedOperationLog.user_id == user_id)
    )).scalar() or 0

    total_tokens = (await db.execute(
        select(func.coalesce(func.sum(SyncedOperationLog.total_tokens), 0))
        .where(SyncedOperationLog.user_id == user_id)
    )).scalar() or 0

    chat_count = (await db.execute(
        select(func.count(SyncedOperationLog.id))
        .where(SyncedOperationLog.user_id == user_id, SyncedOperationLog.action.in_(["chat", "public_chat"]))
    )).scalar() or 0

    avg_latency = (await db.execute(
        select(func.avg(SyncedOperationLog.latency_ms))
        .where(
            SyncedOperationLog.user_id == user_id,
            SyncedOperationLog.action.in_(["chat", "public_chat"]),
            SyncedOperationLog.latency_ms > 0,
        )
    )).scalar()

    usage_total = (await db.execute(
        select(func.coalesce(func.sum(UsageReport.token_count), 0))
        .where(UsageReport.user_id == user_id)
    )).scalar() or 0

    return {
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "total_tokens": max(total_tokens, usage_total),
        "chat_count": chat_count,
        "avg_latency_ms": round(avg_latency, 1) if avg_latency else None,
        "usage_report_tokens": usage_total,
    }
