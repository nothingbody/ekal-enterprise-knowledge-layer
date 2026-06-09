"""Channel management and webhook API endpoints."""

import time
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

_webhook_hits: dict[str, list[float]] = defaultdict(list)
_WEBHOOK_RATE_LIMIT = 60
_WEBHOOK_RATE_WINDOW = 60
_WEBHOOK_MAX_TOKENS = 10000  # max tracked tokens to prevent memory leak


def _check_webhook_rate(token: str) -> None:
    now = time.time()
    hits = _webhook_hits[token]
    _webhook_hits[token] = [t for t in hits if now - t < _WEBHOOK_RATE_WINDOW]
    if not _webhook_hits[token]:
        # No recent hits — remove key entirely to prevent unbounded dict growth
        _webhook_hits.pop(token, None)
    if len(_webhook_hits.get(token, [])) >= _WEBHOOK_RATE_LIMIT:
        raise HTTPException(429, "请求过于频繁，请稍后重试")
    # Evict stale tokens if dict has grown too large
    if len(_webhook_hits) > _WEBHOOK_MAX_TOKENS:
        stale_keys = [
            k for k, v in _webhook_hits.items()
            if not v or (now - max(v)) > _WEBHOOK_RATE_WINDOW
        ]
        for k in stale_keys:
            _webhook_hits.pop(k, None)
    _webhook_hits[token].append(now)

from app.database import get_db
from app.models.user import User
from app.core.security import get_current_user
from app.services.channel_service import (
    list_channels,
    get_channel,
    create_channel,
    update_channel,
    delete_channel,
    toggle_channel,
    send_test_message,
    process_webhook,
)

router = APIRouter()


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    platform: str = Field(min_length=1, max_length=32)
    kb_id: Optional[int] = None
    llm_model_id: Optional[int] = None
    chat_mode: str = Field(default="auto", pattern="^(auto|rag|sql|hybrid|agent|multi_agent)$")
    config: dict = Field(default_factory=dict)
    workspace_id: Optional[int] = None


class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    kb_id: Optional[int] = None
    llm_model_id: Optional[int] = None
    chat_mode: Optional[str] = Field(None, pattern="^(auto|rag|sql|hybrid|agent|multi_agent)$")
    config: Optional[dict] = None


class ChannelTestRequest(BaseModel):
    platform: str = Field(min_length=1, max_length=32)
    config: dict = Field(default_factory=dict)


@router.get("/platforms")
async def get_supported_platforms():
    """Return list of supported channel platforms."""
    from app.core.channels.registry import list_platforms
    return {"platforms": list_platforms()}


_REQUIRED_FIELDS: dict[str, list[str]] = {
    "wecom": ["token", "bot_webhook_key"],
    "dingtalk": ["app_secret", "access_token"],
    "feishu": ["verification_token", "app_secret", "bot_webhook_url"],
    "telegram": ["bot_token"],
    "discord": ["bot_token", "public_key"],
    "slack": ["bot_token", "signing_secret"],
}


@router.post("/test")
async def test_channel_config(
    data: ChannelTestRequest,
    current_user: User = Depends(get_current_user),
):
    """Validate channel config fields for a given platform."""
    from app.core.channels.registry import list_platforms
    if data.platform not in list_platforms():
        raise HTTPException(400, f"不支持的平台: {data.platform}")

    required = _REQUIRED_FIELDS.get(data.platform, [])
    missing = [f for f in required if not data.config.get(f, "").strip()]
    if missing:
        labels = ", ".join(missing)
        return {"valid": False, "message": f"缺少必填字段: {labels}"}

    return {"valid": True, "message": "配置格式正确"}


@router.get("/")
async def get_channels(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    workspace_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await list_channels(db, current_user.id, page=page, page_size=page_size, workspace_id=workspace_id)


@router.get("/{channel_id}")
async def get_channel_detail(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ch = await get_channel(db, current_user.id, channel_id)
    if not ch:
        raise HTTPException(404, "渠道不存在")
    return ch


@router.post("/")
async def add_channel(
    data: ChannelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate platform against registered adapters
    from app.core.channels.registry import list_platforms
    if data.platform not in list_platforms():
        raise HTTPException(400, f"不支持的平台: {data.platform}，支持的平台: {', '.join(list_platforms())}")
    return await create_channel(
        db,
        user_id=current_user.id,
        name=data.name,
        platform=data.platform,
        kb_id=data.kb_id,
        llm_model_id=data.llm_model_id,
        chat_mode=data.chat_mode,
        config=data.config,
        workspace_id=data.workspace_id,
    )


@router.put("/{channel_id}")
async def edit_channel(
    channel_id: int,
    data: ChannelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updates = data.model_dump(exclude_none=True)
    ch = await update_channel(db, current_user.id, channel_id, **updates)
    if not ch:
        raise HTTPException(404, "渠道不存在")
    return ch


@router.delete("/{channel_id}")
async def remove_channel(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ok = await delete_channel(db, current_user.id, channel_id)
    if not ok:
        raise HTTPException(404, "渠道不存在")
    return {"ok": True}


@router.post("/{channel_id}/toggle")
async def toggle_channel_active(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ch = await toggle_channel(db, current_user.id, channel_id)
    if not ch:
        raise HTTPException(404, "渠道不存在")
    return ch


@router.post("/{channel_id}/test-send")
async def test_send_message(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a test message to the channel's webhook/group."""
    ok, msg = await send_test_message(db, current_user.id, channel_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"message": msg}


# ---------------------------------------------------------------------------
# Public webhook endpoint (no auth required)
# ---------------------------------------------------------------------------

webhook_router = APIRouter()


@webhook_router.post("/webhook/{webhook_token}")
async def receive_webhook(
    webhook_token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _check_webhook_rate(webhook_token)
    body = await request.body()
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    headers = dict(request.headers)
    # Also include query params (some platforms send params in URL)
    for k, v in request.query_params.items():
        headers[k] = v

    result = await process_webhook(db, webhook_token, headers, body, payload)
    return JSONResponse(content=result or {"ok": True})


@webhook_router.get("/webhook/{webhook_token}")
async def verify_webhook(
    webhook_token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle GET-based webhook verification (e.g. WeChat URL verification)."""
    _check_webhook_rate(webhook_token)
    headers = dict(request.headers)
    for k, v in request.query_params.items():
        headers[k] = v

    payload = dict(request.query_params)
    result = await process_webhook(db, webhook_token, headers, b"", payload)
    # For echostr-style verification, return plain text
    if result and "echostr" in result:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(str(result["echostr"]))
    return JSONResponse(content=result or {"ok": True})
