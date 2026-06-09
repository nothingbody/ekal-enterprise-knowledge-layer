from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import datetime, timezone
from typing import Optional

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from jwt.exceptions import PyJWTError
from pydantic import BaseModel, Field
from sqlalchemy import and_, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session, get_db
from app.models.relay import (
    RelayHostedKnowledgeBase,
    RelayHostedWorkspace,
    RelayInvitation,
    RelayWorkspaceMember,
)
from app.models.user import User
from app.core.security import get_current_user, is_token_revoked
from app.services.relay_manager import HostOfflineError, RelayRequestError, relay_manager

router = APIRouter()


class HostedInvitationIn(BaseModel):
    invite_token: str = Field(min_length=8, max_length=128)
    role: str = "member"
    expires_at: Optional[datetime] = None
    max_uses: Optional[int] = None
    use_count: int = 0
    is_active: bool = True


class HostedKbIn(BaseModel):
    local_kb_id: int
    name: str
    description: Optional[str] = None
    doc_count: int = 0
    chunk_count: int = 0


class HostedWorkspaceIn(BaseModel):
    local_workspace_id: int
    name: str
    description: Optional[str] = None
    kbs: list[HostedKbIn] = []
    invitations: list[HostedInvitationIn] = []


class HostedWorkspacesPayload(BaseModel):
    device_id: str = Field(min_length=8, max_length=100)
    workspaces: list[HostedWorkspaceIn] = []


class RelayChatRequest(BaseModel):
    remote_kb_id: int
    question: str = Field(min_length=1, max_length=10000)
    conversation_id: Optional[int] = None
    top_k: int = Field(default=5, ge=1, le=50)
    score_threshold: Optional[float] = Field(default=None, ge=0, le=1)
    enable_rewrite: bool = True
    chat_mode: str = Field(default="auto")
    context_strategy: Optional[str] = None
    prompt_template_id: Optional[int] = None


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _ensure_relay_enabled() -> None:
    if not settings.REMOTE_RELAY_ENABLED:
        raise HTTPException(503, "远程知识库共享未启用")


def _invitation_unavailable(inv: RelayInvitation) -> str | None:
    if not inv.is_active:
        return "邀请链接已失效"
    exp = _aware(inv.expires_at)
    if exp and datetime.now(timezone.utc) > exp:
        return "邀请链接已过期"
    if inv.max_uses and inv.use_count >= inv.max_uses:
        return "邀请链接已达到使用上限"
    return None


async def _upsert_member(db: AsyncSession, workspace_id: int, user_id: int, role: str) -> RelayWorkspaceMember:
    result = await db.execute(
        select(RelayWorkspaceMember).where(
            RelayWorkspaceMember.hosted_workspace_id == workspace_id,
            RelayWorkspaceMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member:
        member.role = role or member.role
        return member
    member = RelayWorkspaceMember(hosted_workspace_id=workspace_id, user_id=user_id, role=role or "member")
    db.add(member)
    return member


async def _get_user_from_ws_token(token: str, db: AsyncSession) -> User | None:
    try:
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub = payload.get("sub")
        if not sub or payload.get("type") == "2fa_pending":
            return None
        jti = payload.get("jti")
        if jti and await is_token_revoked(jti):
            return None
        user_id = int(sub)
    except (PyJWTError, ValueError, TypeError):
        return None
    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    return user


@router.post("/hosted-workspaces")
async def publish_hosted_workspaces(
    data: HostedWorkspacesPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_relay_enabled()
    now = datetime.now(timezone.utc)
    await db.execute(
        sa_update(RelayHostedWorkspace)
        .where(
            RelayHostedWorkspace.owner_user_id == current_user.id,
            RelayHostedWorkspace.device_id == data.device_id,
        )
        .values(is_active=False, last_seen=now)
    )

    published = 0
    for ws_data in data.workspaces:
        result = await db.execute(
            select(RelayHostedWorkspace).where(
                RelayHostedWorkspace.owner_user_id == current_user.id,
                RelayHostedWorkspace.device_id == data.device_id,
                RelayHostedWorkspace.local_workspace_id == ws_data.local_workspace_id,
            )
        )
        ws = result.scalar_one_or_none()
        if not ws:
            ws = RelayHostedWorkspace(
                owner_user_id=current_user.id,
                device_id=data.device_id,
                local_workspace_id=ws_data.local_workspace_id,
                name=ws_data.name,
            )
            db.add(ws)
            await db.flush()
        ws.name = ws_data.name
        ws.description = ws_data.description
        ws.is_active = True
        ws.last_seen = now
        await _upsert_member(db, ws.id, current_user.id, "owner")

        await db.execute(
            sa_update(RelayHostedKnowledgeBase)
            .where(RelayHostedKnowledgeBase.hosted_workspace_id == ws.id)
            .values(is_active=False)
        )
        for kb_data in ws_data.kbs:
            kb_result = await db.execute(
                select(RelayHostedKnowledgeBase).where(
                    RelayHostedKnowledgeBase.hosted_workspace_id == ws.id,
                    RelayHostedKnowledgeBase.local_kb_id == kb_data.local_kb_id,
                )
            )
            kb = kb_result.scalar_one_or_none()
            if not kb:
                kb = RelayHostedKnowledgeBase(hosted_workspace_id=ws.id, local_kb_id=kb_data.local_kb_id, name=kb_data.name)
                db.add(kb)
            kb.name = kb_data.name
            kb.description = kb_data.description
            kb.doc_count = kb_data.doc_count or 0
            kb.chunk_count = kb_data.chunk_count or 0
            kb.is_active = True

        await db.execute(
            sa_update(RelayInvitation)
            .where(RelayInvitation.hosted_workspace_id == ws.id)
            .values(is_active=False)
        )
        for inv_data in ws_data.invitations:
            inv_result = await db.execute(select(RelayInvitation).where(RelayInvitation.invite_token == inv_data.invite_token))
            inv = inv_result.scalar_one_or_none()
            if not inv:
                inv = RelayInvitation(hosted_workspace_id=ws.id, invite_token=inv_data.invite_token)
                db.add(inv)
            inv.hosted_workspace_id = ws.id
            inv.role = inv_data.role or "member"
            inv.expires_at = inv_data.expires_at
            inv.max_uses = inv_data.max_uses
            inv.use_count = inv_data.use_count or 0
            inv.is_active = inv_data.is_active
        published += 1

    await db.commit()
    return {"status": "ok", "published": published}


@router.get("/shared-kbs")
async def list_shared_kbs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_relay_enabled()
    result = await db.execute(
        select(RelayHostedKnowledgeBase, RelayHostedWorkspace, RelayWorkspaceMember)
        .join(RelayHostedWorkspace, RelayHostedKnowledgeBase.hosted_workspace_id == RelayHostedWorkspace.id)
        .join(
            RelayWorkspaceMember,
            and_(
                RelayWorkspaceMember.hosted_workspace_id == RelayHostedWorkspace.id,
                RelayWorkspaceMember.user_id == current_user.id,
            ),
        )
        .where(RelayHostedWorkspace.is_active == True, RelayHostedKnowledgeBase.is_active == True)
        .order_by(RelayHostedWorkspace.updated_at.desc(), RelayHostedKnowledgeBase.updated_at.desc())
    )
    items = []
    for kb, ws, member in result.all():
        items.append({
            "id": kb.id,
            "remote_kb_id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "doc_count": kb.doc_count,
            "chunk_count": kb.chunk_count,
            "workspace_id": ws.id,
            "workspace_name": ws.name,
            "role": member.role,
            "host_user_id": ws.owner_user_id,
            "host_device_id": ws.device_id,
            "host_online": await relay_manager.is_host_online(ws.owner_user_id, ws.device_id),
            "is_remote": True,
        })
    return items


@router.get("/invitations/{token}/info")
async def get_relay_invitation_info(token: str, db: AsyncSession = Depends(get_db)):
    _ensure_relay_enabled()
    row = (await db.execute(
        select(RelayInvitation, RelayHostedWorkspace)
        .join(RelayHostedWorkspace, RelayInvitation.hosted_workspace_id == RelayHostedWorkspace.id)
        .where(RelayInvitation.invite_token == token)
    )).first()
    if not row:
        raise HTTPException(404, "邀请链接无效或已过期")
    inv, ws = row
    unavailable = _invitation_unavailable(inv)
    if unavailable:
        raise HTTPException(410, unavailable)
    return {
        "workspace_name": ws.name,
        "workspace_description": ws.description,
        "role": inv.role,
        "remote": True,
        "host_online": await relay_manager.is_host_online(ws.owner_user_id, ws.device_id),
    }


@router.post("/invitations/{token}/accept")
async def accept_relay_invitation(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_relay_enabled()
    row = (await db.execute(
        select(RelayInvitation, RelayHostedWorkspace)
        .join(RelayHostedWorkspace, RelayInvitation.hosted_workspace_id == RelayHostedWorkspace.id)
        .where(RelayInvitation.invite_token == token)
    )).first()
    if not row:
        raise HTTPException(404, "邀请链接无效或已过期")
    inv, ws = row
    unavailable = _invitation_unavailable(inv)
    if unavailable:
        raise HTTPException(410, unavailable)

    existing = (await db.execute(
        select(RelayWorkspaceMember).where(
            RelayWorkspaceMember.hosted_workspace_id == ws.id,
            RelayWorkspaceMember.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if existing:
        return {
            "message": "已加入工作空间",
            "workspace_id": ws.id,
            "workspace_name": ws.name,
            "role": existing.role,
            "remote": True,
        }

    try:
        result = await relay_manager.request_host(
            ws.owner_user_id,
            ws.device_id,
            "invite.accept",
            {
                "invite_token": token,
                "user": {
                    "id": current_user.id,
                    "username": current_user.username,
                    "email": current_user.email,
                    "role": str(current_user.role.value if hasattr(current_user.role, "value") else current_user.role),
                    "is_active": current_user.is_active,
                },
            },
            timeout_seconds=30,
        )
    except HostOfflineError:
        raise HTTPException(409, "知识库主机离线，暂时无法加入")
    except RelayRequestError as exc:
        raise HTTPException(400, str(exc))

    role = str(result.get("role") or inv.role or "member")
    await _upsert_member(db, ws.id, current_user.id, role)
    if not result.get("already_member"):
        inv.use_count = (inv.use_count or 0) + 1
    await db.commit()
    return {
        "message": "已成功加入远程工作空间",
        "workspace_id": ws.id,
        "workspace_name": ws.name,
        "role": role,
        "remote": True,
    }


@router.post("/chat/completions")
async def relay_chat_completions(
    data: RelayChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_relay_enabled()
    row = (await db.execute(
        select(RelayHostedKnowledgeBase, RelayHostedWorkspace)
        .join(RelayHostedWorkspace, RelayHostedKnowledgeBase.hosted_workspace_id == RelayHostedWorkspace.id)
        .join(
            RelayWorkspaceMember,
            and_(
                RelayWorkspaceMember.hosted_workspace_id == RelayHostedWorkspace.id,
                RelayWorkspaceMember.user_id == current_user.id,
            ),
        )
        .where(
            RelayHostedKnowledgeBase.id == data.remote_kb_id,
            RelayHostedKnowledgeBase.is_active == True,
            RelayHostedWorkspace.is_active == True,
        )
    )).first()
    if not row:
        raise HTTPException(403, "无权访问该远程知识库")
    kb, ws = row
    if not await relay_manager.is_host_online(ws.owner_user_id, ws.device_id):
        raise HTTPException(409, "知识库主机离线")

    payload = data.model_dump(exclude_none=True)
    payload["kb_id"] = kb.local_kb_id
    payload.pop("remote_kb_id", None)
    payload["requesting_user"] = {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": str(current_user.role.value if hasattr(current_user.role, "value") else current_user.role),
        "is_active": current_user.is_active,
    }

    async def generate():
        try:
            async for line in relay_manager.stream_host(ws.owner_user_id, ws.device_id, "chat.start", payload):
                yield line
        except (HostOfflineError, RelayRequestError) as exc:
            yield json.dumps({"type": "error", "data": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.websocket("/host")
async def relay_host_ws(
    websocket: WebSocket,
    token: str = Query(""),
    device_id: str = Query(""),
):
    if not settings.REMOTE_RELAY_ENABLED or not token or not device_id:
        await websocket.close(code=1008)
        return
    async with async_session() as db:
        user = await _get_user_from_ws_token(token, db)
    if not user:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    host_key = await relay_manager.register_host(user.id, device_id, websocket)

    async def renew_loop():
        while True:
            await asyncio.sleep(15)
            await relay_manager.touch_host(host_key, user.id, device_id)

    renew_task = asyncio.create_task(renew_loop(), name=f"relay:host_renew:{host_key}")
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "heartbeat":
                await relay_manager.touch_host(host_key, user.id, device_id)
                continue
            await relay_manager.publish_response(str(message.get("request_id") or ""), message)
    except WebSocketDisconnect:
        pass
    finally:
        renew_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await renew_task
        await relay_manager.unregister_host(host_key, websocket)
