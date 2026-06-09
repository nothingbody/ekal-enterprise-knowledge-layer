import hashlib
import logging
import secrets
import json
from collections import defaultdict
from datetime import date
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models.user import User
from app.models.published_app import PublishedApp
from app.models.knowledge_base import KnowledgeBase
from app.models.model_config import ModelConfig
from app.core.security import get_current_user
from app.services.access_service import require_kb_access, list_accessible_kb_ids
from app.services.chat_service import stream_chat
from app.schemas.chat import ChatRequest, PublicChatRequest
from app.schemas.published_app import PublishedAppCreate, PublishedAppUpdate

router = APIRouter()
_public_limiter = Limiter(key_func=get_remote_address)
_logger = logging.getLogger(__name__)

# In-memory fallback when Redis 不可用（多 Worker 下仍可能不一致）
_daily_usage: dict[tuple[str, str], int] = defaultdict(int)
_daily_usage_date: str = ""


def _check_daily_limit_memory(share_token: str, daily_limit: int) -> bool:
    """Increment and check daily usage. Returns True if within limit."""
    global _daily_usage, _daily_usage_date
    today = date.today().isoformat()
    if _daily_usage_date != today:
        _daily_usage.clear()
        _daily_usage_date = today
    if daily_limit <= 0:
        return True
    key = (share_token, today)
    if _daily_usage[key] >= daily_limit:
        return False
    _daily_usage[key] += 1
    return True


_RATE_LIMIT_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local current = tonumber(redis.call('GET', key) or '0')
if current >= limit then
    return 0
end
local val = redis.call('INCR', key)
if val == 1 then
    redis.call('EXPIRE', key, ttl)
end
return 1
"""


async def _check_daily_limit(share_token: str, daily_limit: int) -> bool:
    """跨进程日限额：优先 Redis（原子 Lua 脚本）；失败时回退进程内计数。"""
    if daily_limit <= 0:
        return True
    today = date.today().isoformat()
    key = f"rag:pubapp:daily:{share_token}:{today}"
    try:
        from redis.asyncio import from_url as redis_from_url
        from app.config import settings

        r = redis_from_url(settings.REDIS_URL, socket_connect_timeout=2)
        result = await r.eval(_RATE_LIMIT_LUA, 1, key, daily_limit, 172800)
        await r.aclose()
        return int(result) == 1
    except Exception as exc:
        _logger.warning("公开应用日限额 Redis 不可用，回退进程内计数（多 Worker 下不精确）: %s", exc)
        return _check_daily_limit_memory(share_token, daily_limit)


async def _verify_api_key(api_key: str, db: AsyncSession) -> PublishedApp:
    """Verify an API key (<api-key>) against stored SHA256 hashes and return the app."""
    if not api_key or not api_key.startswith("sk-"):
        raise HTTPException(401, "无效的 API Key 格式")

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    result = await db.execute(
        select(PublishedApp).where(
            PublishedApp.api_key_hash == key_hash,
            PublishedApp.is_active == True,
        )
    )
    app_obj = result.scalar_one_or_none()
    if not app_obj:
        raise HTTPException(401, "API Key 无效或应用已停用")
    return app_obj


def _serialize_app(app_obj: PublishedApp, can_manage: bool = True) -> dict:
    return {
        "id": app_obj.id,
        "name": app_obj.name,
        "share_token": app_obj.share_token,
        "has_api_key": bool(app_obj.api_key_hash or app_obj.api_key),
        "kb_id": app_obj.kb_id,
        "llm_model_id": app_obj.llm_model_id,
        "description": app_obj.description,
        "is_active": app_obj.is_active,
        "welcome_message": app_obj.welcome_message,
        "suggested_questions": app_obj.suggested_questions,
        "prompt_template": app_obj.prompt_template,
        "default_chat_mode": getattr(app_obj, "default_chat_mode", "auto") or "auto",
        "daily_limit": getattr(app_obj, "daily_limit", 100) or 100,
        "user_id": app_obj.user_id,
        "can_manage": can_manage,
        "created_at": str(app_obj.created_at),
    }


async def _validate_app_refs(db: AsyncSession, user_id: int, kb_id: int, llm_model_id: int):
    await require_kb_access(db, kb_id, user_id, "write")

    # Allow using own models OR workspace-shared models
    model_result = await db.execute(
        select(ModelConfig).where(ModelConfig.id == llm_model_id, ModelConfig.user_id == user_id)
    )
    if not model_result.scalar_one_or_none():
        # Check if the model is shared via any workspace the user belongs to
        from app.models.workspace import WorkspaceModelConfig, WorkspaceMember
        shared = await db.execute(
            select(WorkspaceModelConfig)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == WorkspaceModelConfig.workspace_id)
            .where(
                WorkspaceModelConfig.model_config_id == llm_model_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        if not shared.first():
            raise HTTPException(400, "LLM 模型不存在或无权使用")


async def _require_app_manage_access(db: AsyncSession, app_id: int, user_id: int) -> PublishedApp:
    result = await db.execute(select(PublishedApp).where(PublishedApp.id == app_id))
    app_obj = result.scalar_one_or_none()
    if not app_obj:
        raise HTTPException(404, "应用不存在")
    if app_obj.user_id == user_id:
        return app_obj
    await require_kb_access(db, app_obj.kb_id, user_id, "manage")
    return app_obj


@router.post("/")
async def create_app(
    data: PublishedAppCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _validate_app_refs(db, current_user.id, data.kb_id, data.llm_model_id)
    app_obj = PublishedApp(
        user_id=current_user.id,
        kb_id=data.kb_id,
        name=data.name,
        description=data.description,
        llm_model_id=data.llm_model_id,
        welcome_message=data.welcome_message,
        suggested_questions=data.suggested_questions,
        prompt_template=data.prompt_template,
        default_chat_mode=data.default_chat_mode,
        daily_limit=data.daily_limit,
    )
    db.add(app_obj)
    await db.commit()
    await db.refresh(app_obj)
    return _serialize_app(app_obj)


@router.get("/")
async def list_apps(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    readable_kb_ids = await list_accessible_kb_ids(db, current_user.id, "read")
    manageable_kb_ids = set(await list_accessible_kb_ids(db, current_user.id, "manage"))
    result = await db.execute(
        select(PublishedApp).where(
            or_(PublishedApp.user_id == current_user.id, PublishedApp.kb_id.in_(readable_kb_ids))
        )
        .order_by(PublishedApp.created_at.desc())
    )
    apps = result.scalars().all()
    return [
        _serialize_app(a, can_manage=(a.user_id == current_user.id or a.kb_id in manageable_kb_ids))
        for a in apps
    ]


@router.get("/{app_id}")
async def get_app(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PublishedApp).where(PublishedApp.id == app_id)
    )
    app_obj = result.scalar_one_or_none()
    if not app_obj:
        raise HTTPException(404, "应用不存在")
    can_manage = app_obj.user_id == current_user.id
    if not can_manage:
        accessible = await list_accessible_kb_ids(db, current_user.id, "read")
        if app_obj.kb_id not in accessible:
            raise HTTPException(404, "应用不存在")
    return _serialize_app(app_obj, can_manage=can_manage)


@router.put("/{app_id}")
async def update_app(
    app_id: int,
    data: PublishedAppUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app_obj = await _require_app_manage_access(db, app_id, current_user.id)

    update_data = data.model_dump(exclude_unset=True)
    next_kb_id = update_data.get("kb_id", app_obj.kb_id)
    next_llm_model_id = update_data.get("llm_model_id", app_obj.llm_model_id)
    if next_kb_id and next_llm_model_id:
        await _validate_app_refs(db, current_user.id, next_kb_id, next_llm_model_id)

    for key, value in update_data.items():
        setattr(app_obj, key, value)

    await db.commit()
    await db.refresh(app_obj)
    return _serialize_app(app_obj, can_manage=True)


@router.post("/{app_id}/generate-api-key")
async def generate_api_key(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app_obj = await _require_app_manage_access(db, app_id, current_user.id)
    raw_key = f"sk-{secrets.token_urlsafe(32)}"
    app_obj.api_key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    app_obj.api_key = None  # clear legacy plaintext
    await db.commit()
    return {"api_key": raw_key}


@router.delete("/{app_id}")
async def delete_app(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app_obj = await _require_app_manage_access(db, app_id, current_user.id)
    await db.delete(app_obj)
    await db.commit()
    return {"message": "删除成功"}


@router.post("/public/{share_token}/chat")
@_public_limiter.limit("10/minute")
async def public_chat(
    request: Request,
    share_token: str,
    data: PublicChatRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PublishedApp).where(PublishedApp.share_token == share_token, PublishedApp.is_active == True)
    )
    app_obj = result.scalar_one_or_none()
    if not app_obj:
        raise HTTPException(404, "应用不存在或已停用")

    app_daily_limit = getattr(app_obj, "daily_limit", 100) or 100
    if not await _check_daily_limit(share_token, app_daily_limit):
        raise HTTPException(429, f"该应用今日对话次数已达上限（{app_daily_limit} 次），请明天再试。")

    import re as _re
    visitor_id = (data.visitor_id or "guest").strip()
    # Sanitize visitor_id: alphanumeric + basic chars only, max 64 chars
    visitor_id = _re.sub(r'[^a-zA-Z0-9_\-.]', '', visitor_id)[:64] or "guest"
    conv_id = data.conversation_id
    if conv_id:
        from app.models.chat_history import ChatConversation
        conv_result = await db.execute(
            select(ChatConversation).where(
                ChatConversation.id == conv_id,
                ChatConversation.kb_id == app_obj.kb_id,
                ChatConversation.user_id == app_obj.user_id,
                ChatConversation.title.like(f"[pubapp:{app_obj.id}:{visitor_id}]%"),
            )
        )
        if not conv_result.scalar_one_or_none():
            conv_id = None

    chat_req = ChatRequest(
        kb_id=app_obj.kb_id,
        llm_model_id=app_obj.llm_model_id,
        question=data.question,
        conversation_id=conv_id,
        top_k=data.top_k,
        score_threshold=data.score_threshold,
        published_app_id=app_obj.id,
        visitor_id=visitor_id,
        prompt_template=app_obj.prompt_template,
        chat_mode=getattr(app_obj, "default_chat_mode", None) or "auto",
    )
    return StreamingResponse(
        stream_chat(db, app_obj.user_id, chat_req),
        media_type="text/event-stream",
    )


@router.get("/public/{share_token}/history")
async def public_app_history(
    share_token: str,
    visitor_id: str = "",
    conversation_id: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Return messages for an existing public-app conversation (read-only)."""
    import re as _re
    from app.models.chat_history import ChatConversation, ChatMessage

    result = await db.execute(
        select(PublishedApp).where(PublishedApp.share_token == share_token, PublishedApp.is_active == True)
    )
    app_obj = result.scalar_one_or_none()
    if not app_obj:
        raise HTTPException(404, "应用不存在或已停用")

    vid = _re.sub(r'[^a-zA-Z0-9_\-.]', '', (visitor_id or "").strip())[:64] or "guest"
    if not conversation_id:
        return {"messages": []}

    conv_result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.kb_id == app_obj.kb_id,
            ChatConversation.user_id == app_obj.user_id,
            ChatConversation.title.like(f"[pubapp:{app_obj.id}:{vid}]%"),
        )
    )
    if not conv_result.scalar_one_or_none():
        return {"messages": []}

    msgs_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at)
    )
    msgs = msgs_result.scalars().all()
    return {
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "references": m.references,
            }
            for m in msgs
        ]
    }


@router.get("/public/{share_token}/info")
async def public_app_info(share_token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PublishedApp).where(PublishedApp.share_token == share_token, PublishedApp.is_active == True)
    )
    app_obj = result.scalar_one_or_none()
    if not app_obj:
        raise HTTPException(404, "应用不存在或已停用")

    suggested = []
    if app_obj.suggested_questions:
        try:
            suggested = json.loads(app_obj.suggested_questions)
        except Exception:
            pass

    return {
        "name": app_obj.name,
        "description": app_obj.description,
        "welcome_message": app_obj.welcome_message,
        "suggested_questions": suggested,
        "brand_color": app_obj.brand_color,
        "logo_url": app_obj.logo_url,
        "custom_css": app_obj.custom_css,
    }


@router.post("/openapi/chat")
@_public_limiter.limit("10/minute")
async def openapi_chat(
    request: Request,
    data: PublicChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Programmatic chat endpoint authenticated via API Key (Authorization: Bearer <api-key>)."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "缺少 Authorization 请求头 (Bearer <api-key>)")
    api_key = auth_header[len("Bearer "):]

    app_obj = await _verify_api_key(api_key, db)

    api_daily_limit = getattr(app_obj, "daily_limit", 100) or 100
    if not await _check_daily_limit(app_obj.share_token, api_daily_limit):
        raise HTTPException(429, f"该应用今日对话次数已达上限（{api_daily_limit} 次），请明天再试。")

    import re as _re
    visitor_id = (data.visitor_id or "api").strip()
    visitor_id = _re.sub(r'[^a-zA-Z0-9_\-.]', '', visitor_id)[:64] or "api"
    conv_id = data.conversation_id
    if conv_id:
        from app.models.chat_history import ChatConversation
        conv_result = await db.execute(
            select(ChatConversation).where(
                ChatConversation.id == conv_id,
                ChatConversation.kb_id == app_obj.kb_id,
                ChatConversation.user_id == app_obj.user_id,
                ChatConversation.title.like(f"[pubapp:{app_obj.id}:{visitor_id}]%"),
            )
        )
        if not conv_result.scalar_one_or_none():
            conv_id = None

    chat_req = ChatRequest(
        kb_id=app_obj.kb_id,
        llm_model_id=app_obj.llm_model_id,
        question=data.question,
        conversation_id=conv_id,
        top_k=data.top_k,
        score_threshold=data.score_threshold,
        published_app_id=app_obj.id,
        visitor_id=visitor_id,
        prompt_template=app_obj.prompt_template,
        chat_mode=getattr(app_obj, "default_chat_mode", None) or "auto",
    )
    return StreamingResponse(
        stream_chat(db, app_obj.user_id, chat_req),
        media_type="text/event-stream",
    )
