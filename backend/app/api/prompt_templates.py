from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.database import get_db
from app.models.user import User
from app.models.prompt_template import PromptTemplate
from app.core.security import get_current_user
from app.schemas.prompt_template import (
    PromptTemplateCreate,
    PromptTemplateUpdate,
    PromptTemplateResponse,
)

router = APIRouter()

SUPPORTED_VARIABLES = [
    {"name": "context", "label": "检索到的文档上下文", "example": "{context}"},
    {"name": "sql_context", "label": "SQL 查询结果", "example": "{sql_context}"},
    {"name": "question", "label": "用户的提问", "example": "{question}"},
    {"name": "history", "label": "对话历史摘要", "example": "{history}"},
    {"name": "date", "label": "当前日期", "example": "{date}"},
    {"name": "kb_name", "label": "知识库名称", "example": "{kb_name}"},
]


def _serialize(t: PromptTemplate) -> dict:
    return {
        "id": t.id,
        "user_id": t.user_id,
        "name": t.name,
        "description": t.description,
        "content": t.content,
        "category": t.category,
        "is_builtin": bool(t.is_builtin),
        "created_at": str(t.created_at) if t.created_at else None,
        "updated_at": str(t.updated_at) if t.updated_at else None,
    }


@router.get("/")
async def list_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PromptTemplate)
        .where(
            or_(
                PromptTemplate.is_builtin == True,  # noqa: E712
                PromptTemplate.user_id == current_user.id,
            )
        )
        .order_by(PromptTemplate.is_builtin.desc(), PromptTemplate.created_at.desc())
    )
    templates = result.scalars().all()
    return [_serialize(t) for t in templates]


@router.get("/variables")
async def get_supported_variables():
    return SUPPORTED_VARIABLES


@router.get("/{template_id}")
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id)
    )
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(404, "模板不存在")
    if not tpl.is_builtin and tpl.user_id != current_user.id:
        raise HTTPException(403, "无权访问该模板")
    return _serialize(tpl)


@router.post("/")
async def create_template(
    data: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tpl = PromptTemplate(
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        content=data.content,
        category=data.category,
        is_builtin=False,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return _serialize(tpl)


@router.put("/{template_id}")
async def update_template(
    template_id: int,
    data: PromptTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id)
    )
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(404, "模板不存在")
    if tpl.is_builtin:
        raise HTTPException(403, "内置模板不可修改")
    if tpl.user_id != current_user.id:
        raise HTTPException(403, "无权修改该模板")

    for field in ("name", "description", "content", "category"):
        val = getattr(data, field, None)
        if val is not None:
            setattr(tpl, field, val)

    await db.commit()
    await db.refresh(tpl)
    return _serialize(tpl)


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id)
    )
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(404, "模板不存在")
    if tpl.is_builtin:
        raise HTTPException(403, "内置模板不可删除")
    if tpl.user_id != current_user.id:
        raise HTTPException(403, "无权删除该模板")

    await db.delete(tpl)
    await db.commit()
    return {"message": "模板已删除"}
