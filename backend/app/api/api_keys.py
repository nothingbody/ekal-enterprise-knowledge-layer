import hashlib
import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.api_key import ApiKey
from app.schemas.api_key import ApiKeyCreate, ApiKeyUpdate

router = APIRouter()


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _make_preview(raw_key: str) -> str:
    return raw_key[:8] + "..." + raw_key[-4:]


@router.get("/")
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == current_user.id)
        .order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "key_preview": k.key_preview or "***",
            "is_active": k.is_active,
            "last_used_at": str(k.last_used_at) if k.last_used_at else None,
            "created_at": str(k.created_at),
        }
        for k in keys
    ]


@router.get("/{key_id}")
async def get_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
    )
    k = result.scalar_one_or_none()
    if not k:
        raise HTTPException(404, "API Key 不存在")
    return {
        "id": k.id,
        "name": k.name,
        "key_preview": k.key_preview or "***",
        "is_active": k.is_active,
        "last_used_at": str(k.last_used_at) if k.last_used_at else None,
        "created_at": str(k.created_at),
    }


@router.post("/")
async def create_api_key(
    data: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = data.name.strip()
    raw_key = "rag-" + secrets.token_urlsafe(32)
    api_key = ApiKey(
        user_id=current_user.id,
        name=name,
        key_hash=_hash_key(raw_key),
        key_preview=_make_preview(raw_key),
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": raw_key,
        "created_at": str(api_key.created_at),
    }


@router.put("/{key_id}")
async def update_api_key(
    key_id: int,
    data: ApiKeyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(404, "API Key 不存在")

    if data.name is not None:
        api_key.name = data.name
    if data.is_active is not None:
        api_key.is_active = data.is_active

    await db.commit()
    await db.refresh(api_key)
    return {"message": "已更新"}


@router.delete("/{key_id}")
async def delete_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(404, "API Key 不存在")

    await db.delete(api_key)
    await db.commit()
    return {"message": "已删除"}
