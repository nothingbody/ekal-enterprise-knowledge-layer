"""User memory management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.models.model_config import ModelConfig, ModelType
from app.core.security import get_current_user
from app.services.memory_service import (
    list_memories,
    create_memory,
    update_memory,
    delete_memory,
    clear_all_memories,
    cleanup_expired_memories,
    build_user_profile,
    get_user_profile,
)

router = APIRouter()


class MemoryCreate(BaseModel):
    content: str = Field(min_length=2, max_length=2000)
    category: str = Field(default="general", pattern="^(general|preference|fact|insight)$")


class MemoryUpdate(BaseModel):
    content: str = Field(min_length=2, max_length=2000)


@router.get("/")
async def get_memories(
    category: Optional[str] = Query(None, pattern="^(general|preference|fact|insight)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await list_memories(db, current_user.id, category=category, page=page, page_size=page_size)


@router.post("/")
async def add_memory(
    data: MemoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mem = await create_memory(db, current_user.id, data.content, data.category)
    return {
        "id": mem.id,
        "content": mem.content,
        "category": mem.category,
        "importance": mem.importance,
        "memory_type": mem.memory_type,
    }


@router.put("/{memory_id}")
async def edit_memory(
    memory_id: int,
    data: MemoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mem = await update_memory(db, current_user.id, memory_id, data.content)
    if not mem:
        raise HTTPException(404, "记忆不存在")
    return {
        "id": mem.id,
        "content": mem.content,
        "category": mem.category,
        "importance": mem.importance,
        "memory_type": mem.memory_type,
    }


@router.delete("/{memory_id}")
async def remove_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ok = await delete_memory(db, current_user.id, memory_id)
    if not ok:
        raise HTTPException(404, "记忆不存在")
    return {"ok": True}


@router.delete("/")
async def clear_memories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = await clear_all_memories(db, current_user.id)
    return {"deleted": count}


@router.get("/profile")
async def get_profile(
    regenerate: bool = Query(False, description="强制重新生成用户画像"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取或生成用户画像。"""
    if not regenerate:
        profile = await get_user_profile(db, current_user.id)
        if profile:
            return {
                "user_id": profile.user_id,
                "profile_summary": profile.profile_summary,
                "topics_of_interest": profile.topics_of_interest,
                "communication_style": profile.communication_style,
                "expertise_areas": profile.expertise_areas,
                "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
            }
        return {
            "user_id": current_user.id,
            "profile_summary": None,
            "topics_of_interest": None,
            "communication_style": None,
            "expertise_areas": None,
            "updated_at": None,
        }

    # Need to regenerate — find a default LLM model
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.user_id == current_user.id,
            ModelConfig.model_type == ModelType.LLM,
            ModelConfig.is_default == True,
        )
    )
    llm_config = result.scalar_one_or_none()
    if not llm_config:
        raise HTTPException(400, "未找到默认 LLM 模型，无法生成用户画像")

    profile = await build_user_profile(db, current_user.id, llm_config)
    return {
        "user_id": profile.user_id,
        "profile_summary": profile.profile_summary,
        "topics_of_interest": profile.topics_of_interest,
        "communication_style": profile.communication_style,
        "expertise_areas": profile.expertise_areas,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@router.post("/cleanup")
async def trigger_cleanup(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动触发清理过期记忆。"""
    count = await cleanup_expired_memories(db)
    return {"deleted": count, "message": f"已清理 {count} 条过期记忆"}
