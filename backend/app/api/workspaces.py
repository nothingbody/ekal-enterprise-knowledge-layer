from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import secrets
from datetime import datetime, timedelta, timezone

from app.database import get_db
from app.models.user import User
from app.models.workspace import (
    Workspace, WorkspaceMember, WorkspaceRole, WorkspaceKnowledgeBase,
    WorkspaceModelConfig, WorkspaceInvitation,
)
from app.models.model_config import ModelConfig
from app.models.operation_log import OperationLog, add_log_and_sync
from app.core.security import get_current_user
from app.cloud.client import (
    cloud_relay_accept_invitation,
    cloud_relay_invitation_info,
    get_central_public_origin,
    is_cloud_enabled,
)
from app.cloud.sync import ensure_cloud_token
from app.schemas.workspace import (
    WorkspaceCreate, WorkspaceMemberAdd, MemberRoleUpdate, WorkspaceUpdate,
    WorkspaceModelShare, InvitationCreate,
)

router = APIRouter()

MANAGE_MEMBER_ROLES = {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}


async def _require_workspace_member_management_access(
    db: AsyncSession,
    ws_id: int,
    current_user: User,
):
    result = await db.execute(select(Workspace).where(Workspace.id == ws_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "工作空间不存在")

    if ws.owner_id == current_user.id:
        return ws, WorkspaceRole.OWNER

    member_result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ws_id,
            WorkspaceMember.user_id == current_user.id,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member or member.role not in MANAGE_MEMBER_ROLES:
        raise HTTPException(403, "无权操作")
    return ws, member.role


@router.post("/")
async def create_workspace(
    data: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = Workspace(name=data.name, description=data.description, owner_id=current_user.id)
    db.add(ws)
    await db.commit()
    await db.refresh(ws)
    member = WorkspaceMember(workspace_id=ws.id, user_id=current_user.id, role=WorkspaceRole.OWNER)
    db.add(member)
    await db.commit()
    return {"id": ws.id, "name": ws.name, "description": ws.description, "created_at": str(ws.created_at)}


@router.get("/")
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import func

    member_count_sub = (
        select(
            WorkspaceMember.workspace_id,
            func.count(WorkspaceMember.id).label("member_count"),
        )
        .group_by(WorkspaceMember.workspace_id)
        .subquery()
    )
    kb_count_sub = (
        select(
            WorkspaceKnowledgeBase.workspace_id,
            func.count(WorkspaceKnowledgeBase.id).label("kb_count"),
        )
        .group_by(WorkspaceKnowledgeBase.workspace_id)
        .subquery()
    )

    result = await db.execute(
        select(
            Workspace,
            WorkspaceMember.role,
            func.coalesce(member_count_sub.c.member_count, 0).label("member_count"),
            func.coalesce(kb_count_sub.c.kb_count, 0).label("kb_count"),
        )
        .join(WorkspaceMember, Workspace.id == WorkspaceMember.workspace_id)
        .outerjoin(member_count_sub, Workspace.id == member_count_sub.c.workspace_id)
        .outerjoin(kb_count_sub, Workspace.id == kb_count_sub.c.workspace_id)
        .where(WorkspaceMember.user_id == current_user.id)
    )
    workspaces = result.all()
    return [{
        "id": w.id,
        "name": w.name,
        "description": w.description,
        "role": role.value,
        "member_count": member_count,
        "kb_count": kb_count,
        "created_at": str(w.created_at),
    } for w, role, member_count, kb_count in workspaces]


@router.put("/{ws_id}")
async def update_workspace(
    ws_id: int,
    data: WorkspaceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Workspace).where(Workspace.id == ws_id, Workspace.owner_id == current_user.id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(403, "无权操作")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(ws, key, value)
    await db.commit()
    await db.refresh(ws)
    return {"id": ws.id, "name": ws.name, "description": ws.description, "created_at": str(ws.created_at)}


@router.post("/{ws_id}/members")
async def add_member(
    ws_id: int,
    data: WorkspaceMemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_workspace_member_management_access(db, ws_id, current_user)

    user_result = await db.execute(select(User).where(User.username == data.username))
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(404, "用户不存在")

    existing = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ws_id, WorkspaceMember.user_id == target_user.id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "该用户已是成员")

    member = WorkspaceMember(
        workspace_id=ws_id,
        user_id=target_user.id,
        role=data.role,
    )
    db.add(member)
    add_log_and_sync(db,
        user_id=current_user.id,
        action="add_workspace_member",
        resource_type="workspace",
        resource_id=ws_id,
        detail=f"添加成员「{data.username}」到工作空间（角色: {data.role}）",
    )
    await db.commit()
    return {"message": "添加成功"}


@router.get("/{ws_id}/members")
async def list_members(
    ws_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify the current user is a member or owner of the workspace
    ws_result = await db.execute(select(Workspace).where(Workspace.id == ws_id))
    ws = ws_result.scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "工作空间不存在")
    is_owner = ws.owner_id == current_user.id
    is_admin = current_user.role == "admin"
    if not is_owner and not is_admin:
        membership = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ws_id,
                WorkspaceMember.user_id == current_user.id,
            )
        )
        if not membership.scalar_one_or_none():
            raise HTTPException(403, "无权查看该工作空间成员")

    result = await db.execute(
        select(WorkspaceMember, User)
        .join(User, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == ws_id)
    )
    members = []
    for wm, user in result:
        members.append({
            "id": wm.id, "user_id": user.id,
            "username": user.username, "email": user.email,
            "role": wm.role.value, "joined_at": str(wm.joined_at),
        })
    return members


@router.put("/{ws_id}/members/{member_id}")
async def update_member_role(
    ws_id: int,
    member_id: int,
    data: MemberRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_workspace_member_management_access(db, ws_id, current_user)

    mem_result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.id == member_id, WorkspaceMember.workspace_id == ws_id))
    member = mem_result.scalar_one_or_none()
    if not member:
        raise HTTPException(404, "成员不存在")
    if member.role == WorkspaceRole.OWNER:
        raise HTTPException(400, "不能修改所有者角色")

    member.role = WorkspaceRole(data.role)
    await db.commit()
    return {"message": "角色已更新"}


@router.delete("/{ws_id}/members/{member_id}")
async def remove_member(
    ws_id: int,
    member_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_workspace_member_management_access(db, ws_id, current_user)

    mem_result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.id == member_id,
            WorkspaceMember.workspace_id == ws_id,
        )
    )
    member = mem_result.scalar_one_or_none()
    if not member:
        raise HTTPException(404, "成员不存在")
    if member.role == WorkspaceRole.OWNER:
        raise HTTPException(400, "不能移除所有者")

    user_result = await db.execute(select(User).where(User.id == member.user_id))
    target_user = user_result.scalar_one_or_none()
    target_name = target_user.username if target_user else str(member.user_id)

    await db.delete(member)
    add_log_and_sync(db,
        user_id=current_user.id,
        action="remove_workspace_member",
        resource_type="workspace",
        resource_id=ws_id,
        detail=f"从工作空间移除成员「{target_name}」",
    )
    await db.commit()
    return {"message": "移除成功"}


@router.get("/{ws_id}")
async def get_workspace(
    ws_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Workspace).where(Workspace.id == ws_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "工作空间不存在")

    # Check membership
    is_owner = ws.owner_id == current_user.id
    if not is_owner:
        mem = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ws_id,
                WorkspaceMember.user_id == current_user.id,
            )
        )
        if not mem.scalar_one_or_none():
            raise HTTPException(403, "无权查看该工作空间")

    # Get member count
    from sqlalchemy import func
    member_count = (await db.execute(
        select(func.count(WorkspaceMember.id)).where(WorkspaceMember.workspace_id == ws_id)
    )).scalar() or 0

    # Get KB count
    kb_count = (await db.execute(
        select(func.count(WorkspaceKnowledgeBase.id)).where(WorkspaceKnowledgeBase.workspace_id == ws_id)
    )).scalar() or 0

    # Get current user's role
    role_result = await db.execute(
        select(WorkspaceMember.role).where(
            WorkspaceMember.workspace_id == ws_id,
            WorkspaceMember.user_id == current_user.id,
        )
    )
    role_row = role_result.scalar_one_or_none()

    return {
        "id": ws.id,
        "name": ws.name,
        "description": ws.description,
        "owner_id": ws.owner_id,
        "created_at": str(ws.created_at),
        "member_count": member_count,
        "kb_count": kb_count,
        "role": role_row.value if role_row else ("owner" if is_owner else None),
    }


@router.get("/{ws_id}/knowledge-bases")
async def list_workspace_kbs(
    ws_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify membership
    result = await db.execute(select(Workspace).where(Workspace.id == ws_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "工作空间不存在")
    is_owner = ws.owner_id == current_user.id
    if not is_owner:
        mem = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ws_id,
                WorkspaceMember.user_id == current_user.id,
            )
        )
        if not mem.scalar_one_or_none():
            raise HTTPException(403, "无权查看该工作空间")

    from app.models.knowledge_base import KnowledgeBase
    result = await db.execute(
        select(KnowledgeBase)
        .join(WorkspaceKnowledgeBase, WorkspaceKnowledgeBase.kb_id == KnowledgeBase.id)
        .where(
            WorkspaceKnowledgeBase.workspace_id == ws_id,
            KnowledgeBase.deleted_at.is_(None),
        )
        .order_by(KnowledgeBase.updated_at.desc())
    )
    kbs = result.scalars().all()
    return [
        {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "doc_count": kb.doc_count,
            "chunk_count": kb.chunk_count,
            "embedding_model_id": kb.embedding_model_id,
            "created_at": str(kb.created_at),
            "updated_at": str(kb.updated_at),
        }
        for kb in kbs
    ]


# ---------------------------------------------------------------------------
# Workspace model sharing
# ---------------------------------------------------------------------------


@router.get("/{ws_id}/models")
async def list_workspace_models(
    ws_id: int,
    model_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List models shared to this workspace (any member can view)."""
    # Verify membership
    result = await db.execute(select(Workspace).where(Workspace.id == ws_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "工作空间不存在")
    is_owner = ws.owner_id == current_user.id
    if not is_owner:
        mem = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ws_id,
                WorkspaceMember.user_id == current_user.id,
            )
        )
        if not mem.scalar_one_or_none():
            raise HTTPException(403, "无权查看该工作空间")

    query = (
        select(WorkspaceModelConfig, ModelConfig, User)
        .join(ModelConfig, WorkspaceModelConfig.model_config_id == ModelConfig.id)
        .outerjoin(User, WorkspaceModelConfig.shared_by == User.id)
        .where(WorkspaceModelConfig.workspace_id == ws_id)
    )
    if model_type:
        query = query.where(ModelConfig.model_type == model_type)
    query = query.order_by(WorkspaceModelConfig.created_at.desc())
    rows = (await db.execute(query)).all()
    return [
        {
            "link_id": wmc.id,
            "model_id": mc.id,
            "model_type": mc.model_type.value if hasattr(mc.model_type, 'value') else mc.model_type,
            "provider": mc.provider.value if hasattr(mc.provider, 'value') else mc.provider,
            "display_name": mc.display_name,
            "model_name": mc.model_name,
            "api_base": mc.api_base,
            "is_default": mc.is_default,
            "shared_by_username": u.username if u else None,
            "created_at": str(wmc.created_at),
        }
        for wmc, mc, u in rows
    ]


@router.post("/{ws_id}/models")
async def share_model_to_workspace(
    ws_id: int,
    data: WorkspaceModelShare,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Share one of your models to the workspace (requires ADMIN+)."""
    await _require_workspace_member_management_access(db, ws_id, current_user)

    # Verify the model belongs to the current user
    model_result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == data.model_config_id,
            ModelConfig.user_id == current_user.id,
        )
    )
    if not model_result.scalar_one_or_none():
        raise HTTPException(400, "模型不存在或不属于你")

    # Check if already shared
    existing = await db.execute(
        select(WorkspaceModelConfig).where(
            WorkspaceModelConfig.workspace_id == ws_id,
            WorkspaceModelConfig.model_config_id == data.model_config_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "该模型已共享到此工作空间")

    link = WorkspaceModelConfig(
        workspace_id=ws_id,
        model_config_id=data.model_config_id,
        shared_by=current_user.id,
    )
    db.add(link)
    await db.commit()
    return {"message": "模型已共享到工作空间"}


@router.delete("/{ws_id}/models/{link_id}")
async def unshare_model_from_workspace(
    ws_id: int,
    link_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a shared model from the workspace (requires ADMIN+)."""
    await _require_workspace_member_management_access(db, ws_id, current_user)

    result = await db.execute(
        select(WorkspaceModelConfig).where(
            WorkspaceModelConfig.id == link_id,
            WorkspaceModelConfig.workspace_id == ws_id,
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(404, "共享记录不存在")

    await db.delete(link)
    await db.commit()
    return {"message": "已取消共享"}


# ---------------------------------------------------------------------------
# Workspace invitations
# ---------------------------------------------------------------------------


@router.post("/{ws_id}/invitations")
async def create_invitation(
    ws_id: int,
    data: InvitationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate an invitation link (requires ADMIN+)."""
    await _require_workspace_member_management_access(db, ws_id, current_user)

    expires_at = None
    if data.expires_hours and data.expires_hours > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=data.expires_hours)

    token = secrets.token_urlsafe(32)
    invitation = WorkspaceInvitation(
        workspace_id=ws_id,
        invite_token=token,
        role=WorkspaceRole(data.role),
        created_by=current_user.id,
        expires_at=expires_at,
        max_uses=data.max_uses,
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    remote_invite_url = None
    if is_cloud_enabled():
        try:
            from app.cloud.relay import publish_hosted_workspaces_once
            await publish_hosted_workspaces_once()
            remote_invite_url = f"{get_central_public_origin().rstrip('/')}/invite/{token}"
        except Exception:
            remote_invite_url = None
    return {
        "id": invitation.id,
        "invite_token": token,
        "role": data.role,
        "expires_at": str(expires_at) if expires_at else None,
        "max_uses": data.max_uses,
        "remote_invite_url": remote_invite_url,
    }


@router.get("/{ws_id}/invitations")
async def list_invitations(
    ws_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List active invitations for a workspace (requires ADMIN+)."""
    await _require_workspace_member_management_access(db, ws_id, current_user)

    result = await db.execute(
        select(WorkspaceInvitation, User)
        .outerjoin(User, WorkspaceInvitation.created_by == User.id)
        .where(
            WorkspaceInvitation.workspace_id == ws_id,
            WorkspaceInvitation.is_active == True,
        )
        .order_by(WorkspaceInvitation.created_at.desc())
    )
    return [
        {
            "id": inv.id,
            "invite_token": inv.invite_token,
            "role": inv.role.value if hasattr(inv.role, 'value') else inv.role,
            "created_by_username": u.username if u else None,
            "expires_at": str(inv.expires_at) if inv.expires_at else None,
            "max_uses": inv.max_uses,
            "use_count": inv.use_count,
            "created_at": str(inv.created_at),
        }
        for inv, u in result.all()
    ]


@router.delete("/{ws_id}/invitations/{invitation_id}")
async def revoke_invitation(
    ws_id: int,
    invitation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke an invitation link."""
    await _require_workspace_member_management_access(db, ws_id, current_user)

    result = await db.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.id == invitation_id,
            WorkspaceInvitation.workspace_id == ws_id,
        )
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(404, "邀请不存在")
    inv.is_active = False
    await db.commit()
    return {"message": "邀请已撤销"}


# ---------------------------------------------------------------------------
# Public invitation endpoints (separate router, no /workspaces prefix)
# ---------------------------------------------------------------------------

invitation_router = APIRouter()


@invitation_router.get("/invitations/{token}/info")
async def get_invitation_info(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint: get invitation info (workspace name, role)."""
    result = await db.execute(
        select(WorkspaceInvitation, Workspace)
        .join(Workspace, WorkspaceInvitation.workspace_id == Workspace.id)
        .where(
            WorkspaceInvitation.invite_token == token,
            WorkspaceInvitation.is_active == True,
        )
    )
    row = result.first()
    if not row:
        if is_cloud_enabled():
            try:
                return await cloud_relay_invitation_info(token)
            except Exception:
                pass
        raise HTTPException(404, "邀请链接无效或已过期")

    inv, ws = row
    # Check expiration
    if inv.expires_at:
        exp = inv.expires_at.replace(tzinfo=timezone.utc) if inv.expires_at.tzinfo is None else inv.expires_at
        if datetime.now(timezone.utc) > exp:
            raise HTTPException(410, "邀请链接已过期")
    # Check usage limit
    if inv.max_uses and inv.use_count >= inv.max_uses:
        raise HTTPException(410, "邀请链接已达到使用上限")

    return {
        "workspace_name": ws.name,
        "workspace_description": ws.description,
        "role": inv.role.value if hasattr(inv.role, 'value') else inv.role,
    }


@invitation_router.post("/invitations/{token}/accept")
async def accept_invitation(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Accept an invitation (requires login). Auto-joins the workspace."""
    result = await db.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.invite_token == token,
            WorkspaceInvitation.is_active == True,
        )
    )
    inv = result.scalar_one_or_none()
    if not inv:
        if is_cloud_enabled():
            cloud_token = await ensure_cloud_token()
            if cloud_token:
                try:
                    return await cloud_relay_accept_invitation(cloud_token, token)
                except Exception as exc:
                    response = getattr(exc, "response", None)
                    detail = str(exc)
                    if response is not None:
                        try:
                            detail = response.json().get("detail") or response.text
                        except Exception:
                            detail = response.text
                    raise HTTPException(getattr(response, "status_code", 400) if response is not None else 400, detail)
        raise HTTPException(404, "邀请链接无效或已过期")

    # Check expiration
    if inv.expires_at:
        exp = inv.expires_at.replace(tzinfo=timezone.utc) if inv.expires_at.tzinfo is None else inv.expires_at
        if datetime.now(timezone.utc) > exp:
            raise HTTPException(410, "邀请链接已过期")
    # Check usage limit (preliminary — authoritative check is the atomic UPDATE below)
    if inv.max_uses and inv.use_count >= inv.max_uses:
        raise HTTPException(410, "邀请链接已达到使用上限")

    # Check if already a member
    existing = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == inv.workspace_id,
            WorkspaceMember.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "你已是该工作空间的成员")

    # Atomic increment with max_uses guard to prevent TOCTOU race.
    # The WHERE clause ensures use_count < max_uses at the DB level.
    from sqlalchemy import update as sa_update
    conditions = [WorkspaceInvitation.id == inv.id]
    if inv.max_uses:
        conditions.append(WorkspaceInvitation.use_count < inv.max_uses)
    inc_result = await db.execute(
        sa_update(WorkspaceInvitation)
        .where(*conditions)
        .values(use_count=WorkspaceInvitation.use_count + 1)
    )
    if inc_result.rowcount == 0:
        raise HTTPException(410, "邀请链接已达到使用上限")

    # Join
    member = WorkspaceMember(
        workspace_id=inv.workspace_id,
        user_id=current_user.id,
        role=inv.role,
    )
    db.add(member)
    await db.commit()
    if is_cloud_enabled():
        try:
            from app.cloud.relay import publish_hosted_workspaces_once
            await publish_hosted_workspaces_once()
        except Exception:
            pass

    # Get workspace name for response
    ws_result = await db.execute(select(Workspace).where(Workspace.id == inv.workspace_id))
    ws = ws_result.scalar_one_or_none()

    return {
        "message": "已成功加入工作空间",
        "workspace_id": inv.workspace_id,
        "workspace_name": ws.name if ws else None,
        "role": inv.role.value if hasattr(inv.role, 'value') else inv.role,
    }


@router.post("/{ws_id}/leave")
async def leave_workspace(
    ws_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Leave a workspace. Owners cannot leave — they must delete the workspace."""
    result = await db.execute(select(Workspace).where(Workspace.id == ws_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "工作空间不存在")
    if ws.owner_id == current_user.id:
        raise HTTPException(400, "所有者不能退出工作空间，请先转让或删除")

    mem_result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ws_id,
            WorkspaceMember.user_id == current_user.id,
        )
    )
    member = mem_result.scalar_one_or_none()
    if not member:
        raise HTTPException(400, "你不是该工作空间的成员")

    await db.delete(member)
    await db.commit()
    return {"message": "已退出工作空间"}


@router.delete("/{ws_id}")
async def delete_workspace(
    ws_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Workspace).where(Workspace.id == ws_id, Workspace.owner_id == current_user.id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "工作空间不存在")
    # cascade="all, delete-orphan" on Workspace.knowledge_base_links
    # handles deleting WorkspaceKnowledgeBase rows; KnowledgeBase records are preserved.
    await db.delete(ws)
    await db.commit()
    return {"message": "工作空间已删除，关联知识库已解绑为个人知识库"}
