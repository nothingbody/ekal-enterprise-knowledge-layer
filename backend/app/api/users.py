import logging
import os
import shutil
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document, DocumentChunk
from app.models.chat_history import ChatConversation, ChatMessage
from app.models.operation_log import OperationLog
from app.models.api_key import ApiKey
from app.models.published_app import PublishedApp
from app.schemas.user import UserResponse, UserUpdate, UserResetPassword
from app.schemas.model_config import ModelConfigCreate, ModelConfigUpdate
from app.core.security import get_admin_user, hash_password

logger = logging.getLogger(__name__)
_audit = logging.getLogger("audit")

router = APIRouter()


def _model_to_dict(m) -> dict:
    """Convert a ModelConfig ORM instance to a dict with masked API key."""
    return {
        "id": m.id,
        "user_id": m.user_id,
        "model_type": m.model_type.value if hasattr(m.model_type, "value") else str(m.model_type),
        "provider": m.provider.value if hasattr(m.provider, "value") else str(m.provider),
        "api_base": m.api_base,
        "model_name": m.model_name,
        "display_name": m.display_name,
        "params": m.params,
        "is_default": m.is_default,
        "created_at": str(m.created_at),
        "api_key_set": bool(m.api_key_encrypted),
    }


@router.get("/")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    total = (await db.execute(select(func.count(User.id)))).scalar() or 0
    result = await db.execute(
        select(User)
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [UserResponse.model_validate(u) for u in result.scalars().all()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/analytics")
async def user_analytics(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """Admin: list all users with conversation/token stats."""
    from sqlalchemy import text

    total = (await db.execute(select(func.count(User.id)))).scalar() or 0

    # Use raw SQL to avoid asyncpg type-casting issues with coalesce/round
    rows = (await db.execute(text("""
        SELECT
            u.id, u.username, u.email, u.role, u.is_active, u.created_at,
            COALESCE(c.conv_count, 0)   AS conv_count,
            COALESCE(m.msg_count, 0)    AS msg_count,
            COALESCE(m.total_tokens, 0) AS total_tokens,
            COALESCE(m.avg_latency, 0)  AS avg_latency,
            m.last_active
        FROM users u
        LEFT JOIN (
            SELECT user_id, COUNT(*) AS conv_count
            FROM chat_conversations GROUP BY user_id
        ) c ON u.id = c.user_id
        LEFT JOIN (
            SELECT cc.user_id,
                   COUNT(cm.id) AS msg_count,
                   COALESCE(SUM(cm.token_count), 0) AS total_tokens,
                   ROUND(COALESCE(CAST(AVG(cm.latency_ms) AS numeric), 0), 1) AS avg_latency,
                   MAX(cm.created_at) AS last_active
            FROM chat_messages cm
            JOIN chat_conversations cc ON cm.conversation_id = cc.id
            GROUP BY cc.user_id
        ) m ON u.id = m.user_id
        ORDER BY COALESCE(m.total_tokens, 0) DESC
        LIMIT :lim OFFSET :off
    """), {"lim": page_size, "off": (page - 1) * page_size})).all()

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "username": r.username,
            "email": r.email,
            "role": r.role.value if hasattr(r.role, 'value') else str(r.role),
            "is_active": r.is_active,
            "created_at": str(r.created_at),
            "conv_count": int(r.conv_count),
            "msg_count": int(r.msg_count),
            "total_tokens": int(r.total_tokens),
            "avg_latency": float(r.avg_latency or 0),
            "last_active": str(r.last_active) if r.last_active else None,
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{user_id}/detail", response_model=UserResponse)
async def get_user_detail(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """Admin: get a single user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    return UserResponse.model_validate(user)


@router.get("/{user_id}/conversations")
async def user_conversations(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """Admin: list conversations for a specific user."""
    from app.models.knowledge_base import KnowledgeBase as KB

    total = (await db.execute(
        select(func.count(ChatConversation.id)).where(ChatConversation.user_id == user_id)
    )).scalar() or 0

    # Subquery: per-conversation message stats
    msg_sub = (
        select(
            ChatMessage.conversation_id.label("cid"),
            func.count(ChatMessage.id).label("msg_count"),
            func.coalesce(func.sum(ChatMessage.token_count), 0).label("tokens"),
        )
        .group_by(ChatMessage.conversation_id)
        .subquery()
    )

    result = await db.execute(
        select(
            ChatConversation.id,
            ChatConversation.title,
            ChatConversation.kb_id,
            ChatConversation.created_at,
            KB.name.label("kb_name"),
            func.coalesce(msg_sub.c.msg_count, 0).label("msg_count"),
            func.coalesce(msg_sub.c.tokens, 0).label("tokens"),
        )
        .outerjoin(KB, ChatConversation.kb_id == KB.id)
        .outerjoin(msg_sub, ChatConversation.id == msg_sub.c.cid)
        .where(ChatConversation.user_id == user_id)
        .order_by(ChatConversation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = []
    for row in result.all():
        items.append({
            "id": row.id,
            "title": row.title or "新对话",
            "kb_id": row.kb_id,
            "kb_name": row.kb_name or "已删除",
            "msg_count": row.msg_count,
            "tokens": row.tokens,
            "created_at": str(row.created_at),
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{user_id}/conversations/{conv_id}/messages")
async def user_conversation_messages(
    user_id: int,
    conv_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """Admin: get messages for a specific conversation."""
    conv = (await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conv_id,
            ChatConversation.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "对话不存在")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "token_count": m.token_count,
            "latency_ms": m.latency_ms,
            "feedback": m.feedback,
            "created_at": str(m.created_at),
        }
        for m in messages
    ]


@router.get("/{user_id}/memories")
async def user_memories(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """Admin: list memories for a specific user."""
    from app.models.user_memory import UserMemory

    total = (await db.execute(
        select(func.count(UserMemory.id)).where(UserMemory.user_id == user_id)
    )).scalar() or 0

    result = await db.execute(
        select(UserMemory)
        .where(UserMemory.user_id == user_id)
        .order_by(UserMemory.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        {
            "id": m.id,
            "content": m.content,
            "category": m.category,
            "source": m.source,
            "importance": m.importance,
            "access_count": m.access_count,
            "memory_type": m.memory_type,
            "expires_at": str(m.expires_at) if m.expires_at else None,
            "created_at": str(m.created_at),
            "updated_at": str(m.updated_at),
        }
        for m in result.scalars().all()
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{user_id}/profile")
async def user_profile(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """Admin: get profile for a specific user."""
    from app.models.user_profile import UserProfile

    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return {"user_id": user_id, "profile_summary": None, "topics_of_interest": None,
                "communication_style": None, "expertise_areas": None}
    return {
        "user_id": profile.user_id,
        "profile_summary": profile.profile_summary,
        "topics_of_interest": profile.topics_of_interest,
        "communication_style": profile.communication_style,
        "expertise_areas": profile.expertise_areas,
        "updated_at": str(profile.updated_at) if profile.updated_at else None,
    }


@router.get("/{user_id}/agents")
async def user_agents(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """Admin: list agent configs for a specific user."""
    from app.models.agent_config import AgentConfig

    result = await db.execute(
        select(AgentConfig)
        .where(AgentConfig.user_id == user_id)
        .order_by(AgentConfig.created_at.desc())
    )
    items = [
        {
            "id": a.id,
            "name": a.name,
            "description": a.description,
            "kb_ids": a.kb_ids,
            "llm_model_id": a.llm_model_id,
            "system_prompt": a.system_prompt,
            "is_active": a.is_active,
            "created_at": str(a.created_at),
            "updated_at": str(a.updated_at),
        }
        for a in result.scalars().all()
    ]
    return {"items": items, "total": len(items)}


@router.get("/{user_id}/models")
async def user_models(
    user_id: int,
    model_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """Admin: list model configs for a specific user. API key is masked for security."""
    from app.models.model_config import ModelConfig

    query = select(ModelConfig).where(ModelConfig.user_id == user_id)
    if model_type:
        query = query.where(ModelConfig.model_type == model_type)
    query = query.order_by(ModelConfig.created_at.desc())
    result = await db.execute(query)
    items = []
    for m in result.scalars().all():
        items.append(_model_to_dict(m))
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
    from sqlalchemy import update as sa_update

    target_user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target_user:
        raise HTTPException(404, "用户不存在")

    if data.is_default:
        await db.execute(
            sa_update(ModelConfig)
            .where(ModelConfig.user_id == user_id, ModelConfig.model_type == data.model_type)
            .values(is_default=False)
        )

    encrypted_key = encrypt_value(data.api_key, settings.SECRET_KEY) if data.api_key else None
    model = ModelConfig(
        user_id=user_id,
        model_type=data.model_type,
        provider=data.provider,
        api_base=data.api_base,
        api_key_encrypted=encrypted_key,
        model_name=data.model_name,
        display_name=data.display_name,
        params=data.params,
        is_default=data.is_default,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    _audit.info(
        "ADMIN_CREATE_MODEL user_id=%d model_id=%d model_name=%s by_admin=%d",
        user_id, model.id, model.model_name, admin.id,
    )
    return _model_to_dict(model)


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
        select(ModelConfig).where(
            ModelConfig.id == model_id,
            ModelConfig.user_id == user_id,
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "模型配置不存在")

    update_data = data.model_dump(exclude_unset=True)
    changed_fields = list(update_data.keys())

    if update_data.get("is_default"):
        from sqlalchemy import update as sa_update
        await db.execute(
            sa_update(ModelConfig)
            .where(
                ModelConfig.user_id == user_id,
                ModelConfig.model_type == model.model_type,
            )
            .values(is_default=False)
        )

    if "api_key" in update_data:
        raw_key = update_data.pop("api_key")
        if raw_key:
            update_data["api_key_encrypted"] = encrypt_value(raw_key, settings.SECRET_KEY)
        elif raw_key == "":
            update_data["api_key_encrypted"] = None

    for key, value in update_data.items():
        if hasattr(model, key):
            setattr(model, key, value)

    await db.commit()
    await db.refresh(model)
    _audit.info(
        "ADMIN_UPDATE_MODEL user_id=%d model_id=%d fields=%s by_admin=%d",
        user_id, model_id, ",".join(changed_fields), admin.id,
    )
    return _model_to_dict(model)


@router.delete("/{user_id}/models/{model_id}")
async def admin_delete_user_model(
    user_id: int,
    model_id: int,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Admin: delete a user's model config."""
    from app.models.model_config import ModelConfig
    from app.services.model_service import check_model_usage

    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == model_id,
            ModelConfig.user_id == user_id,
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "模型配置不存在")

    if not force:
        usages = await check_model_usage(db, model_id)
        if usages:
            raise HTTPException(409, "模型正在被使用：" + "；".join(usages))

    model_name = model.model_name
    await db.delete(model)
    await db.commit()
    _audit.info(
        "ADMIN_DELETE_MODEL user_id=%d model_id=%d model_name=%s by_admin=%d",
        user_id, model_id, model_name, admin.id,
    )
    return {"message": "模型配置已删除"}


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    if user.id == admin.id and data.role and data.role != "admin":
        raise HTTPException(400, "不能修改自己的管理员角色")
    if user.id == admin.id and data.is_active is False:
        raise HTTPException(400, "不能禁用自己的账号")

    if data.role is not None:
        if data.role != user.role:
            _audit.info("ROLE_CHANGE user_id=%d old=%s new=%s by_admin=%d", user_id, user.role, data.role, admin.id)
        user.role = data.role
    if data.is_active is not None:
        if data.is_active != user.is_active:
            action = "USER_ENABLE" if data.is_active else "USER_DISABLE"
            _audit.info("%s user_id=%d username=%s by_admin=%d", action, user_id, user.username, admin.id)
        user.is_active = data.is_active
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    data: UserResetPassword,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    user.hashed_password = hash_password(data.new_password)
    await db.commit()
    _audit.info("PASSWORD_RESET user_id=%d username=%s by_admin=%d", user_id, user.username, _.id)
    return {"message": "密码已重置"}


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    if user_id == admin.id:
        raise HTTPException(400, "不能删除自己的账号")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")

    # ── 1. Clean up resources NOT handled by ORM cascades ──
    kb_ids = (
        await db.execute(select(KnowledgeBase.id).where(KnowledgeBase.user_id == user_id))
    ).scalars().all()

    # Delete vector store collections for each KB
    if kb_ids:
        from app.services.embedding_service import delete_collection
        for kb_id in kb_ids:
            try:
                delete_collection(kb_id)
            except Exception as exc:
                logger.warning("Failed to delete vector collection for kb %s: %s", kb_id, exc)

        # Delete uploaded files for each KB
        for kb_id in kb_ids:
            upload_dir = os.path.join(settings.UPLOAD_DIR, str(kb_id))
            if os.path.isdir(upload_dir):
                shutil.rmtree(upload_dir, ignore_errors=True)

    # Delete published apps (FK CASCADE handles DB rows, but clean explicitly for clarity)
    await db.execute(delete(PublishedApp).where(PublishedApp.user_id == user_id))

    # Delete operation logs (no ORM cascade on User model)
    await db.execute(delete(OperationLog).where(OperationLog.user_id == user_id))

    # ── 2. Delete user — ORM cascades handle the rest ──
    # User model cascades: knowledge_bases, model_configs, conversations
    # KnowledgeBase cascades: documents, chunks, database_sources, workspace_link, conversations
    # DB-level FK CASCADE: web_sources, published_apps (kb_id)
    await db.delete(user)
    await db.commit()
    logger.info("用户已删除: user_id=%s, cleaned %d KBs", user_id, len(kb_ids))
    _audit.info("USER_DELETE user_id=%d username=%s by_admin=%d kbs_cleaned=%d", user_id, user.username, admin.id, len(kb_ids))
    return {"message": "用户已删除"}
