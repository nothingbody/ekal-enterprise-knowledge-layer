"""预置模型配置种子数据 — 首次启动时自动为管理员创建默认模型。

仅当用户没有任何模型配置时才会执行，避免重复创建。
API Key 仅从环境变量读取，避免在开源代码中保留任何默认密钥。

桌面模式下还会自动创建默认知识库，实现开箱即用。
"""
import logging
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_config import ModelConfig, ModelType, ModelProvider
from app.models.knowledge_base import KnowledgeBase
from app.core.encryption import encrypt_value
from app.config import settings

logger = logging.getLogger(__name__)

# ── 预置模型配置列表 ──
# 每个项目对应一个要创建的模型配置
# api_key_env: 环境变量名，如果设置了对应环境变量则优先使用
DEFAULT_MODELS = [
    {
        "model_type": ModelType.LLM,
        "provider": ModelProvider.OPENAI,
        "api_base": "https://api.deepseek.com",
        "model_name": "deepseek-chat",
        "display_name": "DeepSeek-V3",
        "is_default": False,
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    {
        "model_type": ModelType.LLM,
        "provider": ModelProvider.ANTHROPIC,
        "api_base": "https://api.anthropic.com/v1",
        "model_name": "claude-sonnet-4",
        "display_name": "Claude Sonnet 4",
        "is_default": True,
        "api_key_env": "CLAUDE_API_KEY",
    },
    {
        "model_type": ModelType.EMBEDDING,
        "provider": ModelProvider.OPENAI,
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "model_name": "embedding-3",
        "display_name": "智谱 embedding-3",
        "is_default": True,
        "api_key_env": "ZHIPU_API_KEY",
    },
    {
        "model_type": ModelType.EMBEDDING,
        "provider": ModelProvider.OPENAI,
        "api_base": "https://api.siliconflow.cn/v1",
        "model_name": "BAAI/bge-m3",
        "display_name": "BGE-M3 (SiliconFlow)",
        "is_default": False,
        "api_key_env": "SILICONFLOW_API_KEY",
    },
]


def _get_api_key(model_def: dict) -> Optional[str]:
    """获取 API Key：仅从环境变量获取。"""
    import os
    env_key = model_def.get("api_key_env")
    if env_key:
        env_val = os.environ.get(env_key, "").strip()
        if env_val:
            return env_val
    return None


async def seed_default_models(db: AsyncSession, user_id: int = 1) -> int:
    """为指定用户创建预置模型配置。

    仅在该用户没有任何模型配置时执行。

    Args:
        db: 数据库会话
        user_id: 目标用户 ID（默认为管理员 user_id=1）

    Returns:
        创建的模型数量
    """
    # 检查用户是否已有模型配置
    existing_count = (await db.execute(
        select(func.count(ModelConfig.id)).where(ModelConfig.user_id == user_id)
    )).scalar() or 0

    if existing_count > 0:
        logger.debug("用户 %d 已有 %d 个模型配置，跳过预置", user_id, existing_count)
        return 0

    created = 0
    for model_def in DEFAULT_MODELS:
        api_key = _get_api_key(model_def)
        encrypted_key = encrypt_value(api_key, settings.SECRET_KEY) if api_key else None

        model = ModelConfig(
            user_id=user_id,
            model_type=model_def["model_type"],
            provider=model_def["provider"],
            api_base=model_def["api_base"],
            model_name=model_def["model_name"],
            display_name=model_def["display_name"],
            api_key_encrypted=encrypted_key,
            is_default=model_def.get("is_default", False),
            params=model_def.get("params"),
        )
        db.add(model)
        created += 1

    if created:
        await db.commit()
        logger.info("已为用户 %d 创建 %d 个预置模型配置", user_id, created)

    return created


async def seed_default_knowledge_base(db: AsyncSession, user_id: int = 1) -> bool:
    """桌面模式下为指定用户创建默认知识库，实现开箱即用。

    仅在该用户没有任何知识库时执行。

    Returns:
        是否创建了知识库
    """
    if not settings.DESKTOP_MODE:
        return False

    existing_count = (await db.execute(
        select(func.count(KnowledgeBase.id)).where(KnowledgeBase.user_id == user_id)
    )).scalar() or 0

    if existing_count > 0:
        logger.debug("用户 %d 已有 %d 个知识库，跳过预置", user_id, existing_count)
        return False

    default_embedding = (await db.execute(
        select(ModelConfig).where(
            ModelConfig.user_id == user_id,
            ModelConfig.model_type == ModelType.EMBEDDING,
            ModelConfig.is_default == True,
        )
    )).scalar_one_or_none()

    if not default_embedding:
        default_embedding = (await db.execute(
            select(ModelConfig).where(
                ModelConfig.user_id == user_id,
                ModelConfig.model_type == ModelType.EMBEDDING,
            )
        )).scalars().first()

    if not default_embedding:
        logger.warning("未找到 Embedding 模型，跳过默认知识库创建")
        return False

    kb = KnowledgeBase(
        user_id=user_id,
        name="默认知识库",
        description="系统自动创建的默认知识库，可直接上传文档使用。",
        embedding_model_id=default_embedding.id,
        chunk_strategy="fixed",
        chunk_size=500,
        chunk_overlap=50,
        search_mode="hybrid",
    )
    db.add(kb)
    await db.commit()
    logger.info("已为用户 %d 创建默认知识库 (embedding_model=%d)", user_id, default_embedding.id)
    return True
