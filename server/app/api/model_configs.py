import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User, UserRole
from app.models.model_config import ModelConfig, ModelType, ModelProvider
from app.schemas import (
    ModelConfigCreate, ModelConfigResponse, ModelConfigUpdate, PaginatedResponse,
)
from app.core.security import get_current_user, get_admin_user, check_role_level

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=PaginatedResponse)
async def list_model_configs(
    model_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters = []
    if model_type:
        filters.append(ModelConfig.model_type == model_type)
    if not check_role_level(current_user, UserRole.ADMIN):
        from sqlalchemy import or_
        filters.append(or_(
            ModelConfig.created_by == current_user.id,
            ModelConfig.is_shared == True,  # noqa: E712
            ModelConfig.org_id == current_user.org_id,
        ))

    total = (await db.execute(select(func.count(ModelConfig.id)).where(*filters))).scalar() or 0
    result = await db.execute(
        select(ModelConfig).where(*filters)
        .order_by(ModelConfig.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    models = result.scalars().all()
    items = []
    for m in models:
        resp = ModelConfigResponse.model_validate(m)
        resp.api_key_set = bool(m.api_key_encrypted)
        items.append(resp.model_dump())
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/", response_model=ModelConfigResponse)
async def create_model_config(
    data: ModelConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.core.encryption import encrypt_value
    model = ModelConfig(
        org_id=current_user.org_id,
        created_by=current_user.id,
        model_type=data.model_type,
        provider=data.provider,
        api_base=data.api_base,
        api_key_encrypted=encrypt_value(data.api_key) if data.api_key else None,
        model_name=data.model_name,
        display_name=data.display_name,
        params=data.params,
        is_default=data.is_default,
        is_shared=data.is_shared,
        max_tokens_per_day=data.max_tokens_per_day,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    resp = ModelConfigResponse.model_validate(model)
    resp.api_key_set = bool(model.api_key_encrypted)
    return resp


@router.put("/{model_id}", response_model=ModelConfigResponse)
async def update_model_config(
    model_id: int,
    data: ModelConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(ModelConfig).where(ModelConfig.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "模型配置不存在")
    if model.created_by != current_user.id and not check_role_level(current_user, UserRole.ADMIN):
        raise HTTPException(403, "无权修改此模型配置")

    from app.core.encryption import encrypt_value
    for field, value in data.model_dump(exclude_none=True).items():
        if field == "api_key":
            setattr(model, "api_key_encrypted", encrypt_value(value) if value else None)
        else:
            setattr(model, field, value)

    await db.commit()
    await db.refresh(model)
    resp = ModelConfigResponse.model_validate(model)
    resp.api_key_set = bool(model.api_key_encrypted)
    return resp


@router.delete("/{model_id}")
async def delete_model_config(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(ModelConfig).where(ModelConfig.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "模型配置不存在")
    if model.created_by != current_user.id and not check_role_level(current_user, UserRole.ADMIN):
        raise HTTPException(403, "无权删除此模型配置")

    await db.delete(model)
    await db.commit()
    return {"message": "已删除"}


class TestModelRequest(BaseModel):
    api_base: str
    api_key: Optional[str] = None
    model_name: str
    provider: str = "openai"


def _validate_external_url(url: str) -> str:
    """Validate that a URL points to an external host (SSRF protection)."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "仅支持 http/https 协议")
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(400, "无效的 URL")

    # Block obviously internal hostnames
    _blocked = ("localhost", "127.0.0.1", "0.0.0.0", "[::]", "[::1]", "metadata.google.internal")
    if hostname.lower() in _blocked or hostname.lower().endswith(".internal"):
        raise HTTPException(400, "不允许访问内网地址")

    try:
        resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _family, _type, _proto, _canonname, sockaddr in resolved:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise HTTPException(400, "不允许访问内网地址")
    except socket.gaierror:
        pass  # DNS resolution failure is fine — httpx will surface a ConnectError
    return url


@router.post("/test")
async def test_model_connection(
    data: TestModelRequest,
    current_user: User = Depends(get_current_user),
):
    import httpx
    api_url = f"{data.api_base.rstrip('/')}/chat/completions"
    _validate_external_url(api_url)

    headers: dict = {"Content-Type": "application/json"}
    if data.api_key:
        headers["Authorization"] = f"Bearer {data.api_key}"

    body = {
        "model": data.model_name,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 5,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5)) as client:
            resp = await client.post(api_url, headers=headers, json=body)
            resp.raise_for_status()
            return {"status": "ok", "message": "连接成功"}
    except httpx.ConnectError:
        raise HTTPException(400, "无法连接到模型服务，请检查 API 地址")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(400, f"模型服务返回错误: {exc.response.status_code}")
    except Exception as exc:
        raise HTTPException(400, f"测试失败: {exc}")


@router.post("/{model_id}/test")
async def test_saved_model(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.llm_gateway import get_model
    from app.core.encryption import decrypt_value
    model = await get_model(db, model_id)

    import httpx
    api_key = decrypt_value(model.api_key_encrypted) if model.api_key_encrypted else ""
    headers: dict = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": model.model_name,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 5,
    }
    api_url = f"{model.api_base.rstrip('/')}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5)) as client:
            resp = await client.post(api_url, headers=headers, json=body)
            resp.raise_for_status()
            return {"status": "ok", "message": "连接成功", "display_name": model.display_name}
    except httpx.ConnectError:
        raise HTTPException(400, "无法连接到模型服务")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(400, f"模型服务返回错误: {exc.response.status_code}")
    except Exception as exc:
        raise HTTPException(400, f"测试失败: {exc}")


@router.get("/sync")
async def sync_shared_models(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return shared model configs with decrypted API keys for desktop sync."""
    from app.core.encryption import decrypt_value
    from sqlalchemy import or_

    # Build visibility filter — only include org models when user has an org
    visibility = [ModelConfig.is_shared == True]  # noqa: E712
    if current_user.org_id is not None:
        visibility.append(ModelConfig.org_id == current_user.org_id)

    result = await db.execute(
        select(ModelConfig).where(or_(*visibility))
        .order_by(ModelConfig.created_at.desc())
    )
    models = result.scalars().all()
    items = []
    for m in models:
        api_key = ""
        if m.api_key_encrypted:
            try:
                api_key = decrypt_value(m.api_key_encrypted)
            except Exception:
                api_key = ""
        # Mask key for security — show prefix only so desktop can detect changes
        masked_key = (api_key[:8] + "****") if len(api_key) > 8 else ("****" if api_key else "")
        items.append({
            "model_type": m.model_type.value if hasattr(m.model_type, "value") else str(m.model_type),
            "provider": m.provider.value if hasattr(m.provider, "value") else str(m.provider),
            "api_base": m.api_base,
            "api_key": masked_key,
            "model_name": m.model_name,
            "display_name": m.display_name,
            "is_default": m.is_default,
            "params": m.params,
        })
    return {"items": items, "total": len(items)}


class ChatRequest(BaseModel):
    model_id: int
    messages: list[dict]
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False


@router.post("/chat")
async def proxy_chat(
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.llm_gateway import chat_completion, chat_completion_stream

    try:
        if data.stream:
            return StreamingResponse(
                chat_completion_stream(
                    db, data.model_id, data.messages,
                    temperature=data.temperature, max_tokens=data.max_tokens,
                ),
                media_type="text/event-stream",
            )
        result = await chat_completion(
            db, data.model_id, data.messages,
            temperature=data.temperature, max_tokens=data.max_tokens,
        )
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("LLM proxy error: %s", exc)
        raise HTTPException(502, f"LLM 请求失败: {exc}")
