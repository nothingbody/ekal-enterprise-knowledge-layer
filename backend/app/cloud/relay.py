from __future__ import annotations

import asyncio
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import websockets
from sqlalchemy import and_, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.cloud.auth_bridge import sync_local_user_from_cloud
from app.cloud.client import (
    cloud_get_me,
    cloud_publish_hosted_workspaces,
    get_central_ws_url,
    is_cloud_enabled,
)
from app.cloud.sync import ensure_cloud_token, get_device_id
from app.config import settings
from app.core.security import hash_password
from app.database import async_session
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User, UserRole
from app.models.workspace import Workspace, WorkspaceInvitation, WorkspaceKnowledgeBase, WorkspaceMember, WorkspaceRole
from app.schemas.chat import ChatRequest
from app.services.access_service import require_kb_access
from app.services.chat_service import stream_chat

logger = logging.getLogger(__name__)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _role_value(role: Any) -> str:
    return role.value if hasattr(role, "value") else str(role or "member")


async def _ensure_remote_shadow_user(db: AsyncSession, cloud_user: dict) -> User:
    cloud_user_id = cloud_user.get("id")
    username = str(cloud_user.get("username") or f"cloud_{cloud_user_id}")
    email = str(cloud_user.get("email") or f"{username}@remote.invalid")

    local_user = None
    if cloud_user_id is not None:
        result = await db.execute(select(User).where(User.cloud_user_id == int(cloud_user_id)))
        local_user = result.scalar_one_or_none()
    if not local_user:
        result = await db.execute(select(User).where(User.username == username))
        local_user = result.scalar_one_or_none()

    role_raw = str(cloud_user.get("role") or "").lower()
    role = UserRole.ADMIN if role_raw in ("admin", "super_admin", "org_admin") else UserRole.USER
    if local_user:
        if cloud_user_id is not None:
            local_user.cloud_user_id = int(cloud_user_id)
        local_user.email = email
        local_user.role = role
        local_user.is_active = bool(cloud_user.get("is_active", True))
    else:
        local_user = User(
            cloud_user_id=int(cloud_user_id) if cloud_user_id is not None else None,
            username=username,
            email=email,
            hashed_password=hash_password(f"remote:{cloud_user_id or username}:{secrets.token_urlsafe(16)}"),
            role=role,
            is_active=bool(cloud_user.get("is_active", True)),
        )
        db.add(local_user)
    await db.flush()
    return local_user


async def _get_host_local_user(db: AsyncSession, token: str) -> User | None:
    cloud_user = await cloud_get_me(token)
    return await sync_local_user_from_cloud(db, cloud_user)


async def build_hosted_workspaces_payload(db: AsyncSession, local_user: User) -> dict:
    ws_result = await db.execute(
        select(Workspace)
        .where(Workspace.owner_id == local_user.id)
        .order_by(Workspace.created_at.desc())
    )
    workspaces = []
    for ws in ws_result.scalars().all():
        kb_result = await db.execute(
            select(KnowledgeBase)
            .join(WorkspaceKnowledgeBase, WorkspaceKnowledgeBase.kb_id == KnowledgeBase.id)
            .where(
                WorkspaceKnowledgeBase.workspace_id == ws.id,
                KnowledgeBase.deleted_at.is_(None),
            )
            .order_by(KnowledgeBase.updated_at.desc())
        )
        kbs = [
            {
                "local_kb_id": kb.id,
                "name": kb.name,
                "description": kb.description,
                "doc_count": kb.doc_count or 0,
                "chunk_count": kb.chunk_count or 0,
            }
            for kb in kb_result.scalars().all()
        ]
        if not kbs:
            continue

        inv_result = await db.execute(
            select(WorkspaceInvitation).where(
                WorkspaceInvitation.workspace_id == ws.id,
                WorkspaceInvitation.is_active == True,
            )
        )
        invitations = [
            {
                "invite_token": inv.invite_token,
                "role": _role_value(inv.role),
                "expires_at": _aware(inv.expires_at).isoformat() if _aware(inv.expires_at) else None,
                "max_uses": inv.max_uses,
                "use_count": inv.use_count or 0,
                "is_active": inv.is_active,
            }
            for inv in inv_result.scalars().all()
        ]
        workspaces.append({
            "local_workspace_id": ws.id,
            "name": ws.name,
            "description": ws.description,
            "kbs": kbs,
            "invitations": invitations,
        })
    return {"device_id": get_device_id(), "workspaces": workspaces}


async def publish_hosted_workspaces_once() -> None:
    if not settings.REMOTE_RELAY_ENABLED or not is_cloud_enabled():
        return
    token = await ensure_cloud_token()
    if not token:
        return
    async with async_session() as db:
        local_user = await _get_host_local_user(db, token)
        if not local_user:
            return
        payload = await build_hosted_workspaces_payload(db, local_user)
    await cloud_publish_hosted_workspaces(token, payload)


async def _send_json(ws, message: dict, send_lock: asyncio.Lock) -> None:
    async with send_lock:
        await ws.send(json.dumps(message, ensure_ascii=False))


async def _handle_invite_accept(ws, request_id: str, payload: dict, send_lock: asyncio.Lock) -> None:
    invite_token = str(payload.get("invite_token") or "")
    cloud_user = payload.get("user") or {}
    async with async_session() as db:
        result = await db.execute(
            select(WorkspaceInvitation).where(
                WorkspaceInvitation.invite_token == invite_token,
                WorkspaceInvitation.is_active == True,
            )
        )
        inv = result.scalar_one_or_none()
        if not inv:
            raise ValueError("邀请链接无效或已过期")
        exp = _aware(inv.expires_at)
        if exp and datetime.now(timezone.utc) > exp:
            raise ValueError("邀请链接已过期")
        if inv.max_uses and inv.use_count >= inv.max_uses:
            raise ValueError("邀请链接已达到使用上限")

        local_user = await _ensure_remote_shadow_user(db, cloud_user)
        existing = (await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == inv.workspace_id,
                WorkspaceMember.user_id == local_user.id,
            )
        )).scalar_one_or_none()
        if existing:
            await db.commit()
            await _send_json(ws, {
                "request_id": request_id,
                "type": "result",
                "data": {
                    "workspace_id": inv.workspace_id,
                    "role": _role_value(existing.role),
                    "already_member": True,
                },
            }, send_lock)
            return

        conditions = [WorkspaceInvitation.id == inv.id]
        if inv.max_uses:
            conditions.append(WorkspaceInvitation.use_count < inv.max_uses)
        inc = await db.execute(
            sa_update(WorkspaceInvitation)
            .where(*conditions)
            .values(use_count=WorkspaceInvitation.use_count + 1)
        )
        if inc.rowcount == 0:
            raise ValueError("邀请链接已达到使用上限")
        db.add(WorkspaceMember(workspace_id=inv.workspace_id, user_id=local_user.id, role=inv.role))
        await db.commit()
        await _send_json(ws, {
            "request_id": request_id,
            "type": "result",
            "data": {
                "workspace_id": inv.workspace_id,
                "role": _role_value(inv.role),
                "already_member": False,
            },
        }, send_lock)
    await publish_hosted_workspaces_once()


async def _handle_chat_start(ws, request_id: str, payload: dict, send_lock: asyncio.Lock) -> None:
    cloud_user = payload.get("requesting_user") or {}
    kb_id = int(payload.get("kb_id"))
    async with async_session() as db:
        local_user = await _ensure_remote_shadow_user(db, cloud_user)
        local_user_id = local_user.id
        await db.commit()
    async with async_session() as db:
        await require_kb_access(db, kb_id, local_user_id, "read")
        chat_req = ChatRequest(
            kb_id=kb_id,
            conversation_id=payload.get("conversation_id"),
            question=str(payload.get("question") or ""),
            top_k=int(payload.get("top_k") or settings.DEFAULT_TOP_K),
            score_threshold=payload.get("score_threshold"),
            enable_rewrite=bool(payload.get("enable_rewrite", True)),
            chat_mode=str(payload.get("chat_mode") or "auto"),
            context_strategy=payload.get("context_strategy"),
            prompt_template_id=payload.get("prompt_template_id"),
        )
        async for event_line in stream_chat(db, local_user_id, chat_req):
            await _send_json(ws, {
                "request_id": request_id,
                "type": "event",
                "data": event_line,
            }, send_lock)
    await _send_json(ws, {"request_id": request_id, "type": "done"}, send_lock)


async def _send_error(ws, request_id: str, exc: Exception, send_lock: asyncio.Lock) -> None:
    await _send_json(ws, {
        "request_id": request_id,
        "type": "error",
        "data": str(exc) or "远程知识库请求失败",
    }, send_lock)


async def _dispatch_command(ws, command: dict, tasks: dict[str, asyncio.Task], send_lock: asyncio.Lock) -> None:
    request_id = str(command.get("request_id") or "")
    action = str(command.get("action") or "")
    payload = command.get("payload") or {}
    if action == "cancel":
        task = tasks.pop(request_id, None)
        if task:
            task.cancel()
        return
    if action == "chat.start" and len(tasks) >= settings.RELAY_MAX_CONCURRENT_PER_HOST:
        await _send_error(ws, request_id, RuntimeError("远程知识库并发请求已达到上限"), send_lock)
        return

    async def runner() -> None:
        try:
            if action == "chat.start":
                await _handle_chat_start(ws, request_id, payload, send_lock)
            elif action == "invite.accept":
                await _handle_invite_accept(ws, request_id, payload, send_lock)
            else:
                raise ValueError(f"未知远程命令: {action}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Relay host command failed action=%s request=%s: %s", action, request_id, exc)
            await _send_error(ws, request_id, exc, send_lock)
        finally:
            tasks.pop(request_id, None)

    task = asyncio.create_task(runner(), name=f"relay:{action}:{request_id}")
    tasks[request_id] = task


async def relay_host_loop() -> None:
    if not settings.REMOTE_RELAY_ENABLED:
        return
    while True:
        if not is_cloud_enabled():
            await asyncio.sleep(30)
            continue
        token = await ensure_cloud_token()
        if not token:
            await asyncio.sleep(30)
            continue
        try:
            await publish_hosted_workspaces_once()
            query = urlencode({"token": token, "device_id": get_device_id()})
            ws_url = f"{get_central_ws_url('relay/host')}?{query}"
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20, max_size=2**22) as ws:
                logger.info("Remote relay host connected")
                tasks: dict[str, asyncio.Task] = {}
                send_lock = asyncio.Lock()

                async def heartbeat() -> None:
                    while True:
                        await asyncio.sleep(15)
                        await _send_json(ws, {"type": "heartbeat"}, send_lock)

                async def publisher() -> None:
                    while True:
                        await asyncio.sleep(60)
                        await publish_hosted_workspaces_once()

                hb_task = asyncio.create_task(heartbeat(), name="relay:heartbeat")
                pub_task = asyncio.create_task(publisher(), name="relay:publisher")
                try:
                    async for raw in ws:
                        await _dispatch_command(ws, json.loads(raw), tasks, send_lock)
                finally:
                    for task in [hb_task, pub_task, *tasks.values()]:
                        task.cancel()
                    await asyncio.gather(hb_task, pub_task, *tasks.values(), return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Remote relay host disconnected: %s", exc)
            await asyncio.sleep(10)
