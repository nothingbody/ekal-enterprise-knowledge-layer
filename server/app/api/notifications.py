import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from app.database import get_db
from app.models.user import User, UserRole
from app.models.organization import Organization
from app.models.notification import (
    Notification, NotificationRead,
    NotificationType, NotificationPriority,
)
from app.schemas import PaginatedResponse
from app.core.security import get_current_user, get_admin_user, check_role_level

router = APIRouter()
logger = logging.getLogger(__name__)


class NotificationCreate(BaseModel):
    type: str = "system"
    priority: str = "normal"
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    org_id: Optional[int] = None
    target_user_id: Optional[int] = None
    expires_at: Optional[datetime] = None


def _visibility_filter(user: User):
    now = datetime.now(timezone.utc)
    return and_(
        or_(Notification.expires_at.is_(None), Notification.expires_at > now),
        or_(
            Notification.type == NotificationType.SYSTEM,
            and_(Notification.type == NotificationType.TEAM, Notification.org_id == user.org_id),
            and_(Notification.type == NotificationType.PERSONAL, Notification.target_user_id == user.id),
        ),
    )


def _read_subquery(user_id: int):
    return select(NotificationRead.notification_id).where(
        NotificationRead.user_id == user_id
    ).scalar_subquery()


@router.post("/send")
async def send_notification(
    data: NotificationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notif_type = NotificationType(data.type)

    if notif_type == NotificationType.SYSTEM and not check_role_level(current_user, UserRole.ADMIN):
        raise HTTPException(403, "系统通知需要管理员权限")

    if notif_type == NotificationType.TEAM:
        if not data.org_id:
            raise HTTPException(400, "团队通知需要指定 org_id")
        if not check_role_level(current_user, UserRole.ORG_ADMIN):
            raise HTTPException(403, "团队通知需要组织管理员或更高权限")
        org = (await db.execute(
            select(Organization).where(Organization.id == data.org_id, Organization.deleted_at.is_(None))
        )).scalar_one_or_none()
        if not org:
            raise HTTPException(404, "组织不存在")

    if notif_type == NotificationType.PERSONAL:
        if not data.target_user_id:
            raise HTTPException(400, "个人通知需要指定 target_user_id")
        target = (await db.execute(
            select(User).where(User.id == data.target_user_id, User.deleted_at.is_(None))
        )).scalar_one_or_none()
        if not target:
            raise HTTPException(404, "目标用户不存在")

    notif = Notification(
        type=notif_type,
        priority=NotificationPriority(data.priority),
        title=data.title,
        content=data.content,
        sender_id=current_user.id,
        org_id=data.org_id if notif_type == NotificationType.TEAM else None,
        target_user_id=data.target_user_id if notif_type == NotificationType.PERSONAL else None,
        expires_at=data.expires_at,
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)

    logger.info("NOTIF_SEND type=%s sender=%s title=%s", data.type, current_user.username, data.title)
    return {"id": notif.id, "message": "通知已发送"}


@router.get("/admin/list", response_model=PaginatedResponse)
async def admin_list_notifications(
    type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    filters = []
    if type:
        filters.append(Notification.type == type)

    total = (await db.execute(select(func.count(Notification.id)).where(*filters))).scalar() or 0

    read_count_sub = (
        select(NotificationRead.notification_id, func.count(NotificationRead.id).label("rc"))
        .group_by(NotificationRead.notification_id)
        .subquery()
    )

    result = await db.execute(
        select(Notification, User.username, func.coalesce(read_count_sub.c.rc, 0).label("read_count"))
        .outerjoin(User, Notification.sender_id == User.id)
        .outerjoin(read_count_sub, Notification.id == read_count_sub.c.notification_id)
        .where(*filters)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )

    items = []
    for notif, sender_name, rc in result.all():
        items.append({
            "id": notif.id,
            "type": notif.type.value,
            "priority": notif.priority.value,
            "title": notif.title,
            "content": notif.content,
            "sender_name": sender_name,
            "org_id": notif.org_id,
            "target_user_id": notif.target_user_id,
            "read_count": rc,
            "expires_at": notif.expires_at.isoformat() if notif.expires_at else None,
            "created_at": notif.created_at.isoformat() if notif.created_at else None,
        })

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.delete("/admin/{notif_id}")
async def admin_delete_notification(
    notif_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    notif = (await db.execute(select(Notification).where(Notification.id == notif_id))).scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "通知不存在")
    await db.delete(notif)
    await db.commit()
    return {"message": "通知已删除"}


@router.get("/mine", response_model=PaginatedResponse)
async def my_notifications(
    unread_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    vis = _visibility_filter(current_user)
    read_sub = _read_subquery(current_user.id)

    filters = [vis]
    if unread_only:
        filters.append(~Notification.id.in_(read_sub))

    total = (await db.execute(select(func.count(Notification.id)).where(*filters))).scalar() or 0
    result = await db.execute(
        select(Notification, User.username)
        .outerjoin(User, Notification.sender_id == User.id)
        .where(*filters)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )

    read_ids_result = await db.execute(
        select(NotificationRead.notification_id).where(NotificationRead.user_id == current_user.id)
    )
    read_ids = {r[0] for r in read_ids_result.all()}

    items = []
    for notif, sender_name in result.all():
        items.append({
            "id": notif.id,
            "type": notif.type.value,
            "priority": notif.priority.value,
            "title": notif.title,
            "content": notif.content,
            "sender_name": sender_name,
            "is_read": notif.id in read_ids,
            "created_at": notif.created_at.isoformat() if notif.created_at else None,
        })

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/unread-count")
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    vis = _visibility_filter(current_user)
    read_sub = _read_subquery(current_user.id)

    count = (await db.execute(
        select(func.count(Notification.id)).where(vis, ~Notification.id.in_(read_sub))
    )).scalar() or 0

    return {"count": count}


@router.put("/{notif_id}/read")
async def mark_as_read(
    notif_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notif = (await db.execute(select(Notification).where(Notification.id == notif_id))).scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "通知不存在")

    existing = (await db.execute(
        select(NotificationRead).where(
            NotificationRead.notification_id == notif_id,
            NotificationRead.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if existing:
        return {"message": "已标记"}

    db.add(NotificationRead(notification_id=notif_id, user_id=current_user.id))
    await db.commit()
    return {"message": "已标记已读"}


@router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    vis = _visibility_filter(current_user)
    read_sub = _read_subquery(current_user.id)

    unread = await db.execute(
        select(Notification.id).where(vis, ~Notification.id.in_(read_sub))
    )
    unread_ids = [r[0] for r in unread.all()]

    if unread_ids:
        db.add_all([
            NotificationRead(notification_id=nid, user_id=current_user.id)
            for nid in unread_ids
        ])

    await db.commit()
    return {"marked": len(unread_ids)}
