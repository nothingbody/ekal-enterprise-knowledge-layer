from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User
from app.models.device import Device
from app.schemas import DeviceRegister, DeviceHeartbeat, DeviceResponse, PaginatedResponse
from app.core.security import get_current_user, get_admin_user

router = APIRouter()


@router.post("/register", response_model=DeviceResponse)
async def register_device(
    data: DeviceRegister,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = (await db.execute(
        select(Device).where(Device.device_id == data.device_id)
    )).scalar_one_or_none()

    if existing:
        if existing.user_id != current_user.id:
            raise HTTPException(403, "该设备已被其他用户注册")
        existing.device_name = data.device_name or existing.device_name
        existing.os_info = data.os_info or existing.os_info
        existing.app_version = data.app_version or existing.app_version
        existing.last_heartbeat = datetime.now(timezone.utc)
        existing.is_active = True
        await db.commit()
        await db.refresh(existing)
        return DeviceResponse.model_validate(existing)

    device = Device(
        user_id=current_user.id,
        device_id=data.device_id,
        device_name=data.device_name,
        os_info=data.os_info,
        app_version=data.app_version,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return DeviceResponse.model_validate(device)


@router.post("/heartbeat")
async def heartbeat(
    data: DeviceHeartbeat,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = (await db.execute(
        select(Device).where(Device.device_id == data.device_id, Device.user_id == current_user.id)
    )).scalar_one_or_none()

    if not device:
        raise HTTPException(404, "设备未注册")

    device.last_heartbeat = datetime.now(timezone.utc)
    if data.app_version:
        device.app_version = data.app_version
    if data.extra:
        if data.extra.get("mac_address"):
            device.mac_address = data.extra["mac_address"]
        if data.extra.get("os_info"):
            device.os_info = data.extra["os_info"]
    device.is_active = True
    await db.commit()
    return {"status": "ok"}


@router.get("/", response_model=PaginatedResponse)
async def list_devices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[int] = None,
    online_only: bool = False,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    base_query = select(Device, User.username).join(User, Device.user_id == User.id).where(User.deleted_at.is_(None))
    count_query = select(func.count(Device.id)).select_from(Device).join(User, Device.user_id == User.id).where(User.deleted_at.is_(None))

    if user_id is not None:
        base_query = base_query.where(Device.user_id == user_id)
        count_query = count_query.where(Device.user_id == user_id)
    if online_only:
        threshold = datetime.now(timezone.utc) - timedelta(minutes=10)
        base_query = base_query.where(Device.last_heartbeat >= threshold)
        count_query = count_query.where(Device.last_heartbeat >= threshold)
    if search:
        from app.core.utils import escape_like
        pattern = f"%{escape_like(search)}%"
        search_filter = Device.device_id.ilike(pattern) | Device.device_name.ilike(pattern) | User.username.ilike(pattern)
        base_query = base_query.where(search_filter)
        count_query = count_query.where(search_filter)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        base_query.order_by(Device.last_heartbeat.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    items = []
    for device, username in result.all():
        d = DeviceResponse.model_validate(device).model_dump()
        d["username"] = username
        is_online = device.last_heartbeat and device.last_heartbeat > datetime.now(timezone.utc) - timedelta(minutes=10)
        d["is_online"] = bool(is_online)
        items.append(d)

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.put("/{device_db_id}/deactivate")
async def deactivate_device(
    device_db_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    device = (await db.execute(
        select(Device).where(Device.id == device_db_id)
    )).scalar_one_or_none()
    if not device:
        raise HTTPException(404, "设备不存在")
    device.is_active = False
    await db.commit()
    return {"message": "设备已停用"}
