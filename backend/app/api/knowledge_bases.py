import os
import shutil
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database import get_db
from app.config import settings
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document, DocumentChunk
from app.models.chat_history import ChatConversation, ChatMessage
from app.core.security import get_current_user
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate, KnowledgeBaseUpdate, KnowledgeBaseResponse,
)
from app.services.embedding_service import delete_collection
from app.services.document_service import _invalidate_bm25
from app.models.operation_log import OperationLog, add_log_and_sync
from app.services.access_service import (
    list_accessible_kbs,
    require_kb_access,
    serialize_kb,
    compute_processing_counts,
    compute_failed_counts,
    ensure_workspace_write_access,
    set_kb_workspace,
)

router = APIRouter()


@router.post("/", response_model=KnowledgeBaseResponse)
async def create_kb(
    data: KnowledgeBaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.workspace_id is not None:
        await ensure_workspace_write_access(db, data.workspace_id, current_user.id)
    kb = KnowledgeBase(
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        embedding_model_id=data.embedding_model_id,
        chunk_strategy=data.chunk_strategy,
        chunk_size=data.chunk_size,
        chunk_overlap=data.chunk_overlap,
        search_mode=data.search_mode,
        welcome_message=data.welcome_message,
        suggested_questions=data.suggested_questions,
        prompt_template=data.prompt_template,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    if data.workspace_id is not None:
        await set_kb_workspace(db, kb.id, data.workspace_id)

    add_log_and_sync(db,
        user_id=current_user.id,
        action="create_kb",
        resource_type="knowledge_base",
        resource_id=kb.id,
        detail=f"创建知识库「{kb.name}」",
    )
    await db.commit()

    try:
        import asyncio
        from app.services.automation_service import fire_event
        asyncio.ensure_future(fire_event("kb.created", {"kb_id": kb.id, "user_id": current_user.id}))
    except Exception:
        pass

    access = await require_kb_access(db, kb.id, current_user.id, "manage")
    return serialize_kb(access)


@router.get("/")
async def list_kbs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = await list_accessible_kbs(db, current_user.id)
    kb_ids = [item["kb"].id for item in items]
    pc_map = await compute_processing_counts(db, kb_ids)
    fc_map = await compute_failed_counts(db, kb_ids)
    return [
        serialize_kb(
            item,
            processing_count=pc_map.get(item["kb"].id, 0),
            failed_count=fc_map.get(item["kb"].id, 0),
        )
        for item in items
    ]


@router.get("/trash")
async def list_trashed_kbs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(KnowledgeBase)
        .where(KnowledgeBase.user_id == current_user.id, KnowledgeBase.deleted_at.isnot(None))
        .order_by(KnowledgeBase.deleted_at.desc())
    )
    kbs = result.scalars().all()
    return [
        {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "doc_count": kb.doc_count,
            "deleted_at": str(kb.deleted_at),
        }
        for kb in kbs
    ]


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_kb(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    access = await require_kb_access(db, kb_id, current_user.id, "read")
    return serialize_kb(access)


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_kb(
    kb_id: int,
    data: KnowledgeBaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    access = await require_kb_access(db, kb_id, current_user.id, "manage")
    kb = access["kb"]

    update_data = data.model_dump(exclude_unset=True)
    workspace_id = update_data.pop("workspace_id", "__missing__")
    if workspace_id != "__missing__":
        if workspace_id is not None:
            await ensure_workspace_write_access(db, workspace_id, current_user.id)
        await set_kb_workspace(db, kb_id, workspace_id)
    for key, value in update_data.items():
        setattr(kb, key, value)

    await db.commit()
    await db.refresh(kb)
    access = await require_kb_access(db, kb_id, current_user.id, "manage")
    return serialize_kb(access)


@router.delete("/{kb_id}")
async def remove_kb(
    kb_id: int,
    permanent: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    access = await require_kb_access(db, kb_id, current_user.id, "manage")
    kb = access["kb"]

    if not permanent:
        from datetime import datetime, timezone
        kb.deleted_at = datetime.now(timezone.utc)
        add_log_and_sync(db,
            user_id=current_user.id,
            action="delete_kb",
            resource_type="knowledge_base",
            resource_id=kb_id,
            detail=f"将知识库「{kb.name}」移入回收站",
        )
        await db.commit()
        _invalidate_bm25(kb_id)
        return {"message": "知识库已移入回收站"}

    # Clean up resources NOT handled by ORM cascades
    try:
        delete_collection(kb_id)
    except Exception:
        pass

    upload_dir = os.path.join(settings.UPLOAD_DIR, str(kb_id))
    if os.path.exists(upload_dir):
        shutil.rmtree(upload_dir, ignore_errors=True)

    # Delete published apps referencing this KB (FK CASCADE handles it,
    # but explicit delete avoids potential ordering issues)
    from app.models.published_app import PublishedApp
    await db.execute(delete(PublishedApp).where(PublishedApp.kb_id == kb_id))

    # ORM cascades handle: documents, chunks, database_sources,
    # workspace_link, conversations (and their messages via ChatConversation cascade)
    kb_name = kb.name
    await db.delete(kb)
    add_log_and_sync(db,
        user_id=current_user.id,
        action="delete_kb_permanent",
        resource_type="knowledge_base",
        resource_id=kb_id,
        detail=f"永久删除知识库「{kb_name}」",
    )
    await db.commit()
    _invalidate_bm25(kb_id)
    return {"message": "知识库已永久删除"}


@router.post("/{kb_id}/restore")
async def restore_kb(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.deleted_at.isnot(None))
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(404, "知识库不存在或未被删除")
    # Access check: creator, admin, or workspace manager
    has_access = (kb.user_id == current_user.id) or (current_user.role == "admin")
    if not has_access:
        from app.models.workspace import WorkspaceKnowledgeBase, WorkspaceMember
        ws_result = await db.execute(
            select(WorkspaceMember.role)
            .join(WorkspaceKnowledgeBase, WorkspaceKnowledgeBase.workspace_id == WorkspaceMember.workspace_id)
            .where(WorkspaceKnowledgeBase.kb_id == kb_id, WorkspaceMember.user_id == current_user.id)
        )
        ws_role = ws_result.scalar_one_or_none()
        if ws_role not in ("admin", "owner"):
            raise HTTPException(403, "无权操作")
    kb.deleted_at = None
    await db.commit()
    _invalidate_bm25(kb_id)
    return {"message": "知识库已恢复"}


@router.post("/{kb_id}/reindex")
async def reindex_kb(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Drop the existing vector collection and re-embed all chunks (async)."""
    access = await require_kb_access(db, kb_id, current_user.id, "manage")
    kb = access["kb"]
    if not kb.embedding_model_id:
        raise HTTPException(status_code=400, detail="知识库未配置 Embedding 模型")

    # Check there are chunks to reindex
    from sqlalchemy import func
    chunk_count = (await db.execute(
        select(func.count(DocumentChunk.id)).where(DocumentChunk.kb_id == kb_id)
    )).scalar() or 0
    if chunk_count == 0:
        return {"message": "知识库无文档切片，无需重建", "total_chunks": 0}

    # Mark KB as reindexing so frontend can poll and prevent concurrent operations
    kb.reindexing = True
    await db.commit()

    # Dispatch async task
    from app.tasks.document_tasks import reindex_kb_task
    from app.core.task_runner import dispatch as dispatch_task
    dispatch_task(reindex_kb_task, kb_id, kb.embedding_model_id)
    return {
        "message": f"索引重建任务已提交，共 {chunk_count} 个切片将被重新处理",
        "total_chunks": chunk_count,
        "reindexing": True,
    }
