import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.core.security import get_current_user
from app.schemas.model_config import (
    ModelConfigCreate, ModelConfigUpdate, ModelConfigResponse, ModelTestRequest,
)
from app.services.model_service import (
    create_model, list_models, update_model, delete_model, get_model,
)
from app.core.llm_client import test_model_connection
from app.models.model_config import ModelConfig
from app.models.operation_log import OperationLog, add_log_and_sync

router = APIRouter()
_logger = logging.getLogger(__name__)


@router.post("/", response_model=ModelConfigResponse)
async def add_model(
    data: ModelConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    model = await create_model(db, current_user.id, data)
    add_log_and_sync(db,
        user_id=current_user.id,
        action="create_model",
        resource_type="model_config",
        resource_id=model.id,
        detail=f"创建模型配置「{data.model_name}」({data.model_type})",
    )
    await db.commit()
    return model


@router.get("/", response_model=List[ModelConfigResponse])
async def get_models(
    model_type: Optional[str] = None,
    workspace_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await list_models(db, current_user.id, model_type, workspace_id=workspace_id)


@router.get("/{model_id}", response_model=ModelConfigResponse)
async def get_model(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import select
    from app.models.model_config import ModelConfig
    result = await db.execute(
        select(ModelConfig).where(ModelConfig.id == model_id, ModelConfig.user_id == current_user.id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "模型不存在")
    return model


@router.put("/{model_id}", response_model=ModelConfigResponse)
async def edit_model(
    model_id: int,
    data: ModelConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        model = await update_model(db, current_user.id, model_id, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    add_log_and_sync(db,
        user_id=current_user.id,
        action="update_model",
        resource_type="model_config",
        resource_id=model_id,
        detail=f"更新模型配置「{model.model_name}」",
    )
    await db.commit()
    return model


@router.delete("/{model_id}")
async def remove_model(
    model_id: int,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        success = await delete_model(db, current_user.id, model_id, force=force)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not success:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    add_log_and_sync(db,
        user_id=current_user.id,
        action="delete_model",
        resource_type="model_config",
        resource_id=model_id,
        detail="删除模型配置",
    )
    await db.commit()
    return {"message": "删除成功"}


@router.get("/detect-ollama")
async def detect_ollama(_: User = Depends(get_current_user)):
    """Detect locally running Ollama and list available models."""
    import httpx

    ollama_bases = [
        "http://localhost:11434",
        "http://127.0.0.1:11434",
    ]
    for base_url in ollama_bases:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{base_url}/api/tags")
                if resp.status_code != 200:
                    continue
                data = resp.json()
                raw_models = data.get("models", [])
                models = []
                for m in raw_models:
                    name = m.get("name", "")
                    size_gb = round(m.get("size", 0) / (1024 ** 3), 1)
                    is_embed = any(k in name.lower() for k in ["embed", "bge", "e5", "nomic"])
                    models.append({
                        "name": name,
                        "size_gb": size_gb,
                        "model_type": "embedding" if is_embed else "llm",
                        "api_base": f"{base_url}/v1",
                        "provider": "openai",
                    })
                return {
                    "detected": True,
                    "base_url": base_url,
                    "api_base": f"{base_url}/v1",
                    "models": models,
                }
        except Exception:
            continue

    return {"detected": False, "models": []}


_QUICK_SETUP_PRESETS = {
    "deepseek": {
        "label": "DeepSeek",
        "api_base": "https://api.deepseek.com/v1",
        "provider": "openai",
        "models": [
            {"type": "llm", "name": "deepseek-chat", "display": "DeepSeek V3 (对话)"},
            {"type": "llm", "name": "deepseek-reasoner", "display": "DeepSeek R1 (推理)"},
        ],
        "embedding": {"name": "BAAI/bge-m3", "base": "https://api.siliconflow.cn/v1", "display": "BGE-M3 (SiliconFlow)", "needs_key": "siliconflow"},
    },
    "openai": {
        "label": "OpenAI",
        "api_base": "https://api.openai.com/v1",
        "provider": "openai",
        "models": [
            {"type": "llm", "name": "gpt-4o", "display": "GPT-4o"},
            {"type": "llm", "name": "gpt-4o-mini", "display": "GPT-4o Mini (经济)"},
        ],
        "embedding": {"name": "text-embedding-3-small", "display": "text-embedding-3-small"},
    },
    "zhipu": {
        "label": "智谱 AI",
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "provider": "openai",
        "models": [
            {"type": "llm", "name": "glm-4-flash", "display": "GLM-4 Flash (免费)"},
            {"type": "llm", "name": "glm-4-plus", "display": "GLM-4 Plus"},
        ],
        "embedding": {"name": "embedding-3", "display": "embedding-3 (智谱)"},
    },
    "siliconflow": {
        "label": "SiliconFlow",
        "api_base": "https://api.siliconflow.cn/v1",
        "provider": "openai",
        "models": [
            {"type": "llm", "name": "deepseek-ai/DeepSeek-V3", "display": "DeepSeek V3 (SiliconFlow)"},
            {"type": "llm", "name": "Qwen/Qwen2.5-72B-Instruct", "display": "Qwen 2.5 72B"},
        ],
        "embedding": {"name": "BAAI/bge-m3", "display": "BGE-M3"},
    },
    "qwen": {
        "label": "通义千问",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "provider": "openai",
        "models": [
            {"type": "llm", "name": "qwen-plus", "display": "Qwen Plus"},
            {"type": "llm", "name": "qwen-turbo", "display": "Qwen Turbo (经济)"},
        ],
        "embedding": {"name": "text-embedding-v3", "display": "text-embedding-v3 (通义)"},
    },
}


class QuickSetupRequest(BaseModel):
    preset: str
    api_key: str
    embedding_api_key: Optional[str] = None


@router.get("/quick-setup/presets")
async def get_quick_setup_presets(_: User = Depends(get_current_user)):
    """Return available quick setup presets."""
    return {
        key: {
            "label": p["label"],
            "models": [{"type": m["type"], "name": m["name"], "display": m["display"]} for m in p["models"]],
            "embedding": {"name": p["embedding"]["name"], "display": p["embedding"]["display"]},
            "needs_separate_embedding_key": "needs_key" in p.get("embedding", {}),
        }
        for key, p in _QUICK_SETUP_PRESETS.items()
    }


@router.post("/quick-setup")
async def quick_setup_models(
    data: QuickSetupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """One-click model setup: create LLM + Embedding models from a preset."""
    from sqlalchemy import select

    preset = _QUICK_SETUP_PRESETS.get(data.preset)
    if not preset:
        raise HTTPException(400, f"未知的预设: {data.preset}")

    emb = preset["embedding"]
    if emb.get("needs_key") and not data.embedding_api_key:
        raise HTTPException(
            400,
            f"该套餐的 Embedding 模型({emb['display']})需要单独的 API Key，"
            f"请在「Embedding Key」字段中填写 {emb.get('needs_key', '')} 平台的 API Key",
        )

    existing = (await db.execute(
        select(ModelConfig.model_name).where(ModelConfig.user_id == current_user.id)
    )).scalars().all()
    existing_names = set(existing)

    created = []

    for m in preset["models"]:
        if m["name"] in existing_names:
            continue
        model_data = ModelConfigCreate(
            model_type=m["type"],
            provider=preset["provider"],
            api_base=preset["api_base"],
            api_key=data.api_key,
            model_name=m["name"],
            display_name=m["display"],
            is_default=(m == preset["models"][0]),
        )
        model = await create_model(db, current_user.id, model_data)
        created.append({"id": model.id, "type": m["type"], "name": m["display"]})

    emb = preset["embedding"]
    if emb["name"] not in existing_names:
        emb_base = emb.get("base", preset["api_base"])
        emb_key = data.embedding_api_key or data.api_key
        emb_data = ModelConfigCreate(
            model_type="embedding",
            provider=preset["provider"],
            api_base=emb_base,
            api_key=emb_key,
            model_name=emb["name"],
            display_name=emb["display"],
            is_default=True,
        )
        emb_model = await create_model(db, current_user.id, emb_data)
        created.append({"id": emb_model.id, "type": "embedding", "name": emb["display"]})

    if not created:
        raise HTTPException(400, "所有模型已配置过，无需重复创建")

    add_log_and_sync(db,
        user_id=current_user.id,
        action="quick_setup",
        resource_type="model_config",
        detail=f"一键配置「{preset['label']}」套餐，创建 {len(created)} 个模型",
    )
    await db.commit()

    return {
        "message": f"已成功配置「{preset['label']}」套餐",
        "created_models": created,
    }


@router.post("/test")
async def test_model(data: ModelTestRequest, _: User = Depends(get_current_user)):
    temp_model = ModelConfig(
        model_type=data.model_type,
        provider=data.provider,
        api_base=data.api_base,
        api_key_encrypted=data.api_key,
        model_name=data.model_name,
    )
    result = await test_model_connection(temp_model)
    return result


@router.post("/{model_id}/test")
async def test_saved_model(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import select
    result = await db.execute(
        select(ModelConfig).where(ModelConfig.id == model_id, ModelConfig.user_id == current_user.id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    return await test_model_connection(model)
