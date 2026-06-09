import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.database import get_db
from app.models.user import User
from app.models.agent_config import AgentConfig
from app.core.security import get_current_user
from app.services.access_service import list_accessible_kb_ids

router = APIRouter()


class AgentConfigCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    kb_ids: List[int] = Field(default_factory=list)
    llm_model_id: Optional[int] = None
    system_prompt: Optional[str] = None


class AgentConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    kb_ids: Optional[List[int]] = None
    llm_model_id: Optional[int] = None
    system_prompt: Optional[str] = None
    is_active: Optional[bool] = None


def _safe_json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _serialize(agent: AgentConfig) -> dict:
    return {
        "id": agent.id,
        "user_id": agent.user_id,
        "name": agent.name,
        "description": agent.description,
        "kb_ids": _safe_json_list(agent.kb_ids),
        "llm_model_id": agent.llm_model_id,
        "system_prompt": agent.system_prompt,
        "is_active": agent.is_active,
        "created_at": str(agent.created_at) if agent.created_at else None,
        "updated_at": str(agent.updated_at) if agent.updated_at else None,
    }


async def _validate_kb_ids(db: AsyncSession, user_id: int, kb_ids: List[int]) -> List[int]:
    allowed_ids = set(await list_accessible_kb_ids(db, user_id, "read"))
    invalid_ids = [kb_id for kb_id in kb_ids if kb_id not in allowed_ids]
    if invalid_ids:
        raise HTTPException(403, f"无权使用这些知识库: {', '.join(map(str, invalid_ids))}")
    return kb_ids


async def _validate_llm_model_id(
    db: AsyncSession,
    user_id: int,
    llm_model_id: Optional[int],
) -> Optional[int]:
    if llm_model_id is None:
        return None

    from app.models.model_config import ModelConfig, ModelType
    from app.models.workspace import WorkspaceMember, WorkspaceModelConfig

    result = await db.execute(
        select(ModelConfig)
        .outerjoin(
            WorkspaceModelConfig,
            WorkspaceModelConfig.model_config_id == ModelConfig.id,
        )
        .outerjoin(
            WorkspaceMember,
            and_(
                WorkspaceMember.workspace_id == WorkspaceModelConfig.workspace_id,
                WorkspaceMember.user_id == user_id,
            ),
        )
        .where(
            ModelConfig.id == llm_model_id,
            ModelConfig.model_type == ModelType.LLM,
            or_(
                ModelConfig.user_id == user_id,
                WorkspaceMember.user_id == user_id,
            ),
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(403, "无权使用该 LLM 模型，或模型不存在")
    return llm_model_id


@router.get("/")
async def list_agents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AgentConfig)
        .where(AgentConfig.user_id == current_user.id)
        .order_by(AgentConfig.created_at.desc())
    )
    return [_serialize(a) for a in result.scalars().all()]


@router.post("/")
async def create_agent(
    data: AgentConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb_ids = await _validate_kb_ids(db, current_user.id, data.kb_ids)
    llm_model_id = await _validate_llm_model_id(db, current_user.id, data.llm_model_id)

    agent = AgentConfig(
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        kb_ids=json.dumps(kb_ids),
        llm_model_id=llm_model_id,
        system_prompt=data.system_prompt,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return _serialize(agent)


@router.get("/{agent_id}")
async def get_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AgentConfig).where(
            AgentConfig.id == agent_id,
            AgentConfig.user_id == current_user.id,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, "Agent 不存在")
    return _serialize(agent)


@router.put("/{agent_id}")
async def update_agent(
    agent_id: int,
    data: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AgentConfig).where(
            AgentConfig.id == agent_id,
            AgentConfig.user_id == current_user.id,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, "Agent 不存在")
    update_data = data.model_dump(exclude_unset=True)
    if "kb_ids" in update_data:
        update_data["kb_ids"] = json.dumps(
            await _validate_kb_ids(db, current_user.id, update_data["kb_ids"])
        )
    if "llm_model_id" in update_data:
        update_data["llm_model_id"] = await _validate_llm_model_id(
            db, current_user.id, update_data["llm_model_id"]
        )
    for key, value in update_data.items():
        setattr(agent, key, value)
    await db.commit()
    await db.refresh(agent)
    return _serialize(agent)


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AgentConfig).where(
            AgentConfig.id == agent_id,
            AgentConfig.user_id == current_user.id,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, "Agent 不存在")
    await db.delete(agent)
    await db.commit()
    return {"message": "Agent 已删除"}
