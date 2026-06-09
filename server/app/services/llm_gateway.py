"""
LLM Gateway Service — centralized model proxy with token accounting.

Responsibilities:
- Encrypt / store API keys per org
- Proxy chat-completion requests to upstream providers
- Track token usage and enforce daily quotas
- Provide a unified interface regardless of provider
"""
import json
import logging
from datetime import date, datetime, timezone
from typing import AsyncIterator, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_config import ModelConfig, ModelType

logger = logging.getLogger("llm_gateway")

_http: Optional[httpx.AsyncClient] = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10))
    return _http


async def close_gateway():
    global _http
    if _http and not _http.is_closed:
        await _http.aclose()
        _http = None


async def get_model(db: AsyncSession, model_id: int) -> ModelConfig:
    result = await db.execute(select(ModelConfig).where(ModelConfig.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise ValueError(f"Model config {model_id} not found")
    return model


async def list_available_models(
    db: AsyncSession,
    *,
    org_id: Optional[int] = None,
    model_type: Optional[ModelType] = None,
    user_id: Optional[int] = None,
) -> list[ModelConfig]:
    filters = []
    if model_type:
        filters.append(ModelConfig.model_type == model_type)
    if org_id:
        from sqlalchemy import or_
        filters.append(or_(
            ModelConfig.org_id == org_id,
            ModelConfig.is_shared == True,  # noqa: E712
        ))
    elif user_id:
        from sqlalchemy import or_
        filters.append(or_(
            ModelConfig.created_by == user_id,
            ModelConfig.is_shared == True,  # noqa: E712
        ))

    result = await db.execute(select(ModelConfig).where(*filters))
    return list(result.scalars().all())


async def _maybe_reset_daily(db: AsyncSession, model: ModelConfig) -> None:
    today_str = date.today().isoformat()
    if model.tokens_reset_date != today_str:
        from sqlalchemy import update
        await db.execute(
            update(ModelConfig)
            .where(ModelConfig.id == model.id)
            .values(tokens_used_today=0, tokens_reset_date=today_str)
        )
        await db.commit()
        model.tokens_used_today = 0
        model.tokens_reset_date = today_str


def _check_quota(model: ModelConfig, estimated_tokens: int = 0) -> None:
    if model.max_tokens_per_day and model.tokens_used_today + estimated_tokens > model.max_tokens_per_day:
        raise ValueError(
            f"Model {model.display_name} daily quota exceeded "
            f"({model.tokens_used_today}/{model.max_tokens_per_day})"
        )


async def _update_usage(db: AsyncSession, model: ModelConfig, tokens: int) -> None:
    from sqlalchemy import update
    await db.execute(
        update(ModelConfig)
        .where(ModelConfig.id == model.id)
        .values(tokens_used_today=ModelConfig.tokens_used_today + tokens)
    )
    await db.commit()


def _build_headers(model: ModelConfig) -> dict:
    from app.core.encryption import decrypt_value
    api_key = decrypt_value(model.api_key_encrypted) if model.api_key_encrypted else ""
    headers: dict = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


async def chat_completion(
    db: AsyncSession,
    model_id: int,
    messages: list[dict],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    stream: bool = False,
) -> dict:
    model = await get_model(db, model_id)
    await _maybe_reset_daily(db, model)
    _check_quota(model)

    headers = _build_headers(model)
    body = {
        "model": model.model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    api_url = f"{model.api_base.rstrip('/')}/chat/completions"
    resp = await _client().post(api_url, headers=headers, json=body)
    resp.raise_for_status()
    data = resp.json()

    usage = data.get("usage", {})
    total_tokens = usage.get("total_tokens", 0)
    if total_tokens:
        await _update_usage(db, model, total_tokens)

    return data


async def chat_completion_stream(
    db: AsyncSession,
    model_id: int,
    messages: list[dict],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> AsyncIterator[str]:
    model = await get_model(db, model_id)
    await _maybe_reset_daily(db, model)
    _check_quota(model)

    headers = _build_headers(model)
    body = {
        "model": model.model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    api_url = f"{model.api_base.rstrip('/')}/chat/completions"
    total_tokens = 0

    async with _client().stream("POST", api_url, headers=headers, json=body) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload.strip() == "[DONE]":
                yield "data: [DONE]\n\n"
                break
            try:
                chunk = json.loads(payload)
                usage = chunk.get("usage", {})
                total_tokens += usage.get("total_tokens", 0)
            except json.JSONDecodeError:
                pass
            yield f"data: {payload}\n\n"

    if total_tokens:
        await _update_usage(db, model, total_tokens)
