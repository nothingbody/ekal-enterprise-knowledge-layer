import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User, UserRole
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.schemas import (
    WorkspaceCreate, WorkspaceResponse, WorkspaceUpdate,
    WorkspaceMemberAdd, PaginatedResponse,
)
from app.core.security import get_current_user, check_role_level

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=PaginatedResponse)
async def list_workspaces(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if check_role_level(current_user, UserRole.ADMIN):
        filters = [Workspace.deleted_at.is_(None)]
    else:
        member_ws = select(WorkspaceMember.workspace_id).where(
            WorkspaceMember.user_id == current_user.id
        ).scalar_subquery()
        filters = [
            Workspace.deleted_at.is_(None),
            (Workspace.owner_id == current_user.id) | Workspace.id.in_(member_ws),
        ]

    total = (await db.execute(select(func.count(Workspace.id)).where(*filters))).scalar() or 0

    mc_sub = (
        select(WorkspaceMember.workspace_id, func.count(WorkspaceMember.id).label("mc"))
        .group_by(WorkspaceMember.workspace_id)
        .subquery()
    )
    result = await db.execute(
        select(Workspace, func.coalesce(mc_sub.c.mc, 0).label("member_count"))
        .outerjoin(mc_sub, Workspace.id == mc_sub.c.workspace_id)
        .where(*filters)
        .order_by(Workspace.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )

    items = []
    for ws, mc in result.all():
        d = WorkspaceResponse.model_validate(ws).model_dump()
        d["member_count"] = mc + 1
        items.append(d)

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/", response_model=WorkspaceResponse)
async def create_workspace(
    data: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = Workspace(
        name=data.name,
        description=data.description,
        org_id=data.org_id or current_user.org_id,
        owner_id=current_user.id,
    )
    db.add(ws)
    await db.commit()
    await db.refresh(ws)
    logger.info("WS_CREATE user=%s ws=%s", current_user.username, ws.name)
    return WorkspaceResponse.model_validate(ws)


async def _check_ws_access(ws: Workspace, user: User, db: AsyncSession) -> None:
    if check_role_level(user, UserRole.ADMIN):
        return
    if ws.owner_id == user.id:
        return
    member = (await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ws.id,
            WorkspaceMember.user_id == user.id,
        )
    )).scalar_one_or_none()
    if not member:
        raise HTTPException(403, "无权访问此工作空间")


@router.get("/{ws_id}", response_model=WorkspaceResponse)
async def get_workspace(
    ws_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = (await db.execute(select(Workspace).where(Workspace.id == ws_id, Workspace.deleted_at.is_(None)))).scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "工作空间不存在")
    await _check_ws_access(ws, current_user, db)
    return WorkspaceResponse.model_validate(ws)


@router.put("/{ws_id}", response_model=WorkspaceResponse)
async def update_workspace(
    ws_id: int,
    data: WorkspaceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = (await db.execute(select(Workspace).where(Workspace.id == ws_id, Workspace.deleted_at.is_(None)))).scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "工作空间不存在")
    if ws.owner_id != current_user.id and not check_role_level(current_user, UserRole.ADMIN):
        raise HTTPException(403, "无权修改此工作空间")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(ws, field, value)
    await db.commit()
    await db.refresh(ws)
    return WorkspaceResponse.model_validate(ws)


@router.delete("/{ws_id}")
async def delete_workspace(
    ws_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = (await db.execute(select(Workspace).where(Workspace.id == ws_id, Workspace.deleted_at.is_(None)))).scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "工作空间不存在")
    if ws.owner_id != current_user.id and not check_role_level(current_user, UserRole.ADMIN):
        raise HTTPException(403, "无权删除此工作空间")

    from datetime import datetime, timezone
    ws.deleted_at = datetime.now(timezone.utc)
    ws.is_active = False
    await db.commit()
    return {"message": "工作空间已删除"}


@router.get("/{ws_id}/members")
async def list_members(
    ws_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = (await db.execute(select(Workspace).where(Workspace.id == ws_id, Workspace.deleted_at.is_(None)))).scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "工作空间不存在")
    await _check_ws_access(ws, current_user, db)

    result = await db.execute(
        select(WorkspaceMember, User)
        .join(User, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == ws_id)
    )
    return [
        {
            "id": m.id,
            "user_id": u.id,
            "username": u.username,
            "email": u.email,
            "role": m.role.value,
            "joined_at": m.joined_at.isoformat() if m.joined_at else None,
        }
        for m, u in result.all()
    ]


@router.post("/{ws_id}/members")
async def add_member(
    ws_id: int,
    data: WorkspaceMemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = (await db.execute(select(Workspace).where(Workspace.id == ws_id, Workspace.deleted_at.is_(None)))).scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "工作空间不存在")
    if ws.owner_id != current_user.id and not check_role_level(current_user, UserRole.ADMIN):
        raise HTTPException(403, "无权管理此工作空间成员")

    target_user_id = data.user_id
    if not target_user_id and data.username:
        user_result = (await db.execute(
            select(User).where(User.username == data.username, User.deleted_at.is_(None))
        )).scalar_one_or_none()
        if not user_result:
            raise HTTPException(404, f"用户 '{data.username}' 不存在")
        target_user_id = user_result.id
    if not target_user_id:
        raise HTTPException(400, "请提供 user_id 或 username")

    existing = (await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ws_id,
            WorkspaceMember.user_id == target_user_id,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "用户已是成员")

    member = WorkspaceMember(
        workspace_id=ws_id,
        user_id=target_user_id,
        role=data.role,
    )
    db.add(member)
    await db.commit()
    return {"message": "已添加"}


@router.delete("/{ws_id}/members/{user_id}")
async def remove_member(
    ws_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = (await db.execute(select(Workspace).where(Workspace.id == ws_id, Workspace.deleted_at.is_(None)))).scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "工作空间不存在")
    if ws.owner_id != current_user.id and not check_role_level(current_user, UserRole.ADMIN):
        raise HTTPException(403, "无权管理此工作空间成员")

    member = (await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ws_id,
            WorkspaceMember.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not member:
        raise HTTPException(404, "成员不存在")

    await db.delete(member)
    await db.commit()
    return {"message": "已移除"}
