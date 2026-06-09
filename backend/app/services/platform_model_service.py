"""Platform built-in model — auto-provision for every user.

Sources (checked in order):
1. Environment variables: PLATFORM_LLM_* / PLATFORM_EMBEDDING_*
2. Server-synced shared models cached by cloud/sync.py

Each user automatically gets platform-provided models without needing
their own API key.
"""
import json as _json
import logging
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.model_config import ModelConfig, ModelType, ModelProvider

logger = logging.getLogger(__name__)

_PLATFORM_TAG = "__platform__"


def _get_env_platform_specs() -> list[dict]:
    """Return platform model specs from environment variables."""
    specs: list[dict] = []
    if settings.PLATFORM_LLM_API_BASE and settings.PLATFORM_LLM_API_KEY and settings.PLATFORM_LLM_MODEL_NAME:
        specs.append({
            "model_type": "llm",
            "provider": "custom",
            "api_base": settings.PLATFORM_LLM_API_BASE,
            "api_key": settings.PLATFORM_LLM_API_KEY,
            "model_name": settings.PLATFORM_LLM_MODEL_NAME,
            "display_name": settings.PLATFORM_LLM_DISPLAY_NAME,
        })
    if settings.PLATFORM_EMBEDDING_API_BASE and settings.PLATFORM_EMBEDDING_API_KEY and settings.PLATFORM_EMBEDDING_MODEL_NAME:
        specs.append({
            "model_type": "embedding",
            "provider": "custom",
            "api_base": settings.PLATFORM_EMBEDDING_API_BASE,
            "api_key": settings.PLATFORM_EMBEDDING_API_KEY,
            "model_name": settings.PLATFORM_EMBEDDING_MODEL_NAME,
            "display_name": settings.PLATFORM_EMBEDDING_DISPLAY_NAME,
        })
    return specs


def _get_server_platform_specs() -> list[dict]:
    """Return platform model specs from server-synced cache."""
    try:
        from app.cloud.sync import get_cached_server_platform_models
        cached = get_cached_server_platform_models()
        specs: list[dict] = []
        for m in cached:
            api_key = m.get("api_key", "")
            if not api_key or not m.get("api_base") or not m.get("model_name"):
                continue
            specs.append({
                "model_type": m.get("model_type", "llm"),
                "provider": m.get("provider", "custom"),
                "api_base": m["api_base"],
                "api_key": api_key,
                "model_name": m["model_name"],
                "display_name": m.get("display_name", m["model_name"]),
            })
        return specs
    except Exception as exc:
        logger.debug("Failed to read server platform specs: %s", exc)
        return []


def _get_all_platform_specs() -> list[dict]:
    """Merge env-var specs and server-synced specs (env vars take priority)."""
    specs = _get_env_platform_specs()
    seen = {(s["model_type"], s["model_name"], s["api_base"]) for s in specs}
    for s in _get_server_platform_specs():
        key = (s["model_type"], s["model_name"], s["api_base"])
        if key not in seen:
            seen.add(key)
            specs.append(s)
    return specs


def is_platform_model_configured() -> dict:
    """Check which platform models are configured (env vars or server cache)."""
    specs = _get_all_platform_specs()
    return {
        "llm": any(s["model_type"] == "llm" for s in specs),
        "embedding": any(s["model_type"] == "embedding" for s in specs),
    }


async def ensure_platform_models(db: AsyncSession, user_id: int) -> list[ModelConfig]:
    """Ensure the user has platform-provided models. Creates them if missing.

    Returns the list of platform model configs for this user.
    """
    specs = _get_all_platform_specs()
    if not specs:
        return []

    existing = (await db.execute(
        select(ModelConfig).where(
            ModelConfig.user_id == user_id,
            ModelConfig.params.contains(_PLATFORM_TAG),
        )
    )).scalars().all()

    existing_keys = {
        (
            (m.model_type.value if hasattr(m.model_type, 'value') else m.model_type).lower(),
            m.model_name,
            m.api_base,
        )
        for m in existing
    }
    created = list(existing)

    from app.core.encryption import encrypt_value

    for spec in specs:
        key = (spec["model_type"].lower(), spec["model_name"], spec["api_base"])
        if key in existing_keys:
            continue

        model_type = ModelType(spec["model_type"]) if spec["model_type"] in [e.value for e in ModelType] else ModelType.LLM
        try:
            provider = ModelProvider(spec["provider"])
        except ValueError:
            provider = ModelProvider.CUSTOM

        m = ModelConfig(
            user_id=user_id,
            model_type=model_type,
            provider=provider,
            api_base=spec["api_base"],
            api_key_encrypted=encrypt_value(spec["api_key"], settings.SECRET_KEY),
            model_name=spec["model_name"],
            display_name=spec["display_name"],
            is_default=len(created) == 0,
            params=_json.dumps({"_tag": _PLATFORM_TAG, "is_platform": True}),
        )
        db.add(m)
        created.append(m)

    if len(created) > len(existing):
        await db.commit()
        logger.info("为用户 %d 创建了 %d 个平台内置模型", user_id, len(created) - len(existing))

    return created


def is_platform_model(model: ModelConfig) -> bool:
    """Check if a model config is a platform-provided model."""
    return bool(model.params and _PLATFORM_TAG in model.params)
