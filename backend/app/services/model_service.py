import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List, Optional

from app.models.model_config import ModelConfig, ModelType
from app.schemas.model_config import ModelConfigCreate, ModelConfigUpdate, ModelConfigResponse
from app.core.llm_client import test_model_connection
from app.core.encryption import encrypt_value
from app.config import settings

logger = logging.getLogger(__name__)


def _to_response(model: ModelConfig) -> ModelConfigResponse:
    from app.services.platform_model_service import is_platform_model
    base = ModelConfigResponse.model_validate(model)
    return base.model_copy(update={
        "api_key_set": bool(model.api_key_encrypted),
        "is_platform": is_platform_model(model),
    })


async def create_model(db: AsyncSession, user_id: int, data: ModelConfigCreate) -> ModelConfigResponse:
    if data.is_default:
        await db.execute(
            update(ModelConfig)
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
    return _to_response(model)


async def list_models(
    db: AsyncSession, user_id: int, model_type: Optional[str] = None,
    workspace_id: Optional[int] = None,
) -> List[ModelConfigResponse]:
    from app.services.platform_model_service import ensure_platform_models
    try:
        await ensure_platform_models(db, user_id)
    except Exception as e:
        logger.warning("ensure_platform_models 失败: %s", e)

    if workspace_id:
        # Return workspace shared models + user's own models (deduplicated)
        from app.models.workspace import WorkspaceModelConfig
        from sqlalchemy import or_
        query = (
            select(ModelConfig)
            .outerjoin(
                WorkspaceModelConfig,
                ModelConfig.id == WorkspaceModelConfig.model_config_id,
            )
            .where(
                or_(
                    ModelConfig.user_id == user_id,
                    WorkspaceModelConfig.workspace_id == workspace_id,
                )
            )
        )
    else:
        query = select(ModelConfig).where(ModelConfig.user_id == user_id)
    if model_type:
        query = query.where(ModelConfig.model_type == model_type)
    query = query.order_by(ModelConfig.created_at.desc())
    result = await db.execute(query)
    seen: set[int] = set()
    items: list[ModelConfigResponse] = []
    for m in result.scalars().all():
        if m.id not in seen:
            seen.add(m.id)
            items.append(_to_response(m))
    return items


async def get_model(db: AsyncSession, model_id: int) -> Optional[ModelConfig]:
    result = await db.execute(select(ModelConfig).where(ModelConfig.id == model_id))
    return result.scalar_one_or_none()


async def update_model(
    db: AsyncSession, user_id: int, model_id: int, data: ModelConfigUpdate
) -> ModelConfigResponse:
    model = await get_model(db, model_id)
    if not model or model.user_id != user_id:
        raise ValueError("模型配置不存在")

    if data.is_default:
        await db.execute(
            update(ModelConfig)
            .where(ModelConfig.user_id == user_id, ModelConfig.model_type == model.model_type)
            .values(is_default=False)
        )

    update_data = data.model_dump(exclude_unset=True)
    if "api_key" in update_data:
        raw_key = update_data.pop("api_key")
        if raw_key:
            update_data["api_key_encrypted"] = encrypt_value(raw_key, settings.SECRET_KEY)
        elif raw_key == "":
            update_data["api_key_encrypted"] = None

    for key, value in update_data.items():
        setattr(model, key, value)

    await db.commit()
    await db.refresh(model)
    return _to_response(model)


async def check_model_usage(db: AsyncSession, model_id: int) -> list[str]:
    """Return a list of resources that reference this model."""
    from app.models.knowledge_base import KnowledgeBase
    from app.models.published_app import PublishedApp
    from sqlalchemy import func

    usages: list[str] = []

    # Check embedding model usage
    kb_embed_count = (await db.execute(
        select(func.count(KnowledgeBase.id)).where(
            KnowledgeBase.embedding_model_id == model_id,
            KnowledgeBase.deleted_at.is_(None),
        )
    )).scalar() or 0
    if kb_embed_count:
        usages.append(f"{kb_embed_count} 个知识库使用此 Embedding 模型")

    # Check LLM model usage in published apps
    app_count = (await db.execute(
        select(func.count(PublishedApp.id)).where(
            PublishedApp.llm_model_id == model_id,
            PublishedApp.is_active == True,
        )
    )).scalar() or 0
    if app_count:
        usages.append(f"{app_count} 个已发布应用使用此 LLM 模型")

    return usages


async def delete_model(db: AsyncSession, user_id: int, model_id: int, force: bool = False):
    """Delete a model. Returns False if not found, raises ValueError if in use (unless force=True)."""
    model = await get_model(db, model_id)
    if not model or model.user_id != user_id:
        return False

    if not force:
        usages = await check_model_usage(db, model_id)
        if usages:
            raise ValueError("模型正在被使用：" + "；".join(usages))

    await db.delete(model)
    await db.commit()
    return True


async def test_connection(model_config_data: dict) -> dict:
    temp_model = ModelConfig(**model_config_data)
    return await test_model_connection(temp_model)
