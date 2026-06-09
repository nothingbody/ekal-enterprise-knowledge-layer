from __future__ import annotations

import json
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.cloud.client import (
    cloud_relay_accept_invitation,
    cloud_relay_chat_stream,
    cloud_relay_invitation_info,
    cloud_relay_shared_kbs,
)
from app.cloud.sync import ensure_cloud_token
from app.config import settings
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter()


class RemoteRelayChatRequest(BaseModel):
    remote_kb_id: int
    question: str = Field(min_length=1, max_length=10000)
    conversation_id: Optional[int] = None
    top_k: int = Field(default=5, ge=1, le=50)
    score_threshold: Optional[float] = Field(default=None, ge=0, le=1)
    enable_rewrite: bool = True
    chat_mode: str = "auto"
    context_strategy: Optional[str] = None
    prompt_template_id: Optional[int] = None


def _cloud_error(exc: httpx.HTTPStatusError) -> HTTPException:
    try:
        detail = exc.response.json().get("detail")
    except Exception:
        detail = exc.response.text or "中心服务器请求失败"
    return HTTPException(exc.response.status_code, detail)


def _ensure_relay_enabled() -> None:
    if not settings.REMOTE_RELAY_ENABLED:
        raise HTTPException(503, "远程知识库共享未启用")


async def _cloud_token_or_401() -> str:
    token = await ensure_cloud_token()
    if not token:
        raise HTTPException(401, "请先登录云端账号")
    return token


@router.get("/shared-kbs")
async def list_remote_shared_kbs(_current_user: User = Depends(get_current_user)):
    _ensure_relay_enabled()
    token = await _cloud_token_or_401()
    try:
        return await cloud_relay_shared_kbs(token)
    except httpx.HTTPStatusError as exc:
        raise _cloud_error(exc)


@router.get("/invitations/{invite_token}/info")
async def relay_invitation_info(invite_token: str):
    _ensure_relay_enabled()
    try:
        return await cloud_relay_invitation_info(invite_token)
    except httpx.HTTPStatusError as exc:
        raise _cloud_error(exc)


@router.post("/invitations/{invite_token}/accept")
async def relay_accept_invitation(invite_token: str, _current_user: User = Depends(get_current_user)):
    _ensure_relay_enabled()
    token = await _cloud_token_or_401()
    try:
        return await cloud_relay_accept_invitation(token, invite_token)
    except httpx.HTTPStatusError as exc:
        raise _cloud_error(exc)


@router.post("/chat/completions")
async def relay_chat_completions(data: RemoteRelayChatRequest, _current_user: User = Depends(get_current_user)):
    _ensure_relay_enabled()
    token = await _cloud_token_or_401()

    async def generate():
        try:
            async for chunk in cloud_relay_chat_stream(token, data.model_dump(exclude_none=True)):
                yield chunk
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("detail")
            except Exception:
                detail = exc.response.text or "远程知识库请求失败"
            yield json.dumps({"type": "error", "data": detail}, ensure_ascii=False) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "data": str(exc) or "远程知识库请求失败"}, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
