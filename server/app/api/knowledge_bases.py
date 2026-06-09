import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User, UserRole
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.schemas import (
    KBCreate, KBResponse, KBUpdate,
    DocumentResponse, PaginatedResponse,
)
from app.core.security import get_current_user
from app.services.kb_service import get_kb_or_404, list_kbs, create_kb, soft_delete_kb, store_document, soft_delete_document
from app.services.permissions import require_owner_or_admin

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=PaginatedResponse)
async def list_knowledge_bases(
    workspace_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await list_kbs(db, current_user, workspace_id, page, page_size)
    return PaginatedResponse(
        items=[KBResponse.model_validate(kb).model_dump() for kb in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/", response_model=KBResponse)
async def create_knowledge_base(
    data: KBCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb = await create_kb(db, current_user, data.model_dump())
    return KBResponse.model_validate(kb)


@router.get("/{kb_id}", response_model=KBResponse)
async def get_knowledge_base(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb = await get_kb_or_404(db, kb_id)
    require_owner_or_admin(kb.owner_id, current_user, "访问")
    return KBResponse.model_validate(kb)


@router.put("/{kb_id}", response_model=KBResponse)
async def update_knowledge_base(
    kb_id: int,
    data: KBUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb = await get_kb_or_404(db, kb_id)
    require_owner_or_admin(kb.owner_id, current_user, "修改")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(kb, field, value)
    await db.commit()
    await db.refresh(kb)
    return KBResponse.model_validate(kb)


@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await soft_delete_kb(db, current_user, kb_id)
    return {"message": "知识库已删除"}


@router.get("/{kb_id}/documents", response_model=PaginatedResponse)
async def list_documents(
    kb_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb = await get_kb_or_404(db, kb_id)
    require_owner_or_admin(kb.owner_id, current_user, "查看文档")
    filters = [Document.kb_id == kb_id, Document.deleted_at.is_(None)]
    total = (await db.execute(select(func.count(Document.id)).where(*filters))).scalar() or 0
    result = await db.execute(
        select(Document).where(*filters)
        .order_by(Document.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    items = [DocumentResponse.model_validate(doc).model_dump() for doc in result.scalars().all()]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/{kb_id}/documents", response_model=DocumentResponse)
async def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = await file.read()
    doc = await store_document(db, current_user, kb_id, file.filename or "untitled", content)
    return DocumentResponse.model_validate(doc)


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(
    kb_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb = await get_kb_or_404(db, kb_id)
    require_owner_or_admin(kb.owner_id, current_user, "删除文档")
    await soft_delete_document(db, kb_id, doc_id)
    return {"message": "文档已删除"}
