from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database import get_db
from app.models.user import User
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.core.security import get_current_user
from app.schemas.document import (
    DocumentResponse, ChunkUpdateRequest, ChunkCreateRequest,
    TagUpdateRequest, ExpiryUpdateRequest,
    DuplicateCheckRequest, DuplicateCheckResponse,
    SuggestKBRequest, SuggestKBResponse, KBSuggestion,
)
from app.services.document_service import (
    upload_document, process_document, list_documents, delete_document,
    mark_document_completed, retry_document, get_document_chunks,
    _invalidate_bm25,
)
from app.services.embedding_service import embed_and_store, update_chunk_in_collection, add_chunk_to_collection, delete_chunk_from_collection
from app.services.access_service import require_kb_access
from app.tasks.document_tasks import process_document_task
from app.core.task_runner import dispatch as dispatch_task
from app.core.chunking import split_text
from app.core.parser import parse_document

router = APIRouter()


async def _verify_kb_access(db: AsyncSession, kb_id: int, user_id: int, mode: str = "read"):
    await require_kb_access(db, kb_id, user_id, mode)


async def _get_document_or_404(db: AsyncSession, doc_id: int) -> Document:
    """Get a non-deleted document by ID or raise 404."""
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.deleted_at.is_(None))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "文档不存在")
    return doc


@router.post("/upload/{kb_id}", response_model=DocumentResponse)
async def upload(
    kb_id: int,
    file: UploadFile = File(...),
    force_replace: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_kb_access(db, kb_id, current_user.id, "write")
    doc = await upload_document(db, kb_id, file, force_replace=force_replace)
    dispatch_task(process_document_task, doc.id, kb_id)
    return doc


@router.get("/{kb_id}")
async def get_documents(
    kb_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_kb_access(db, kb_id, current_user.id, "read")
    return await list_documents(db, kb_id, page, page_size)


@router.get("/{doc_id}/chunks")
async def get_chunks(
    doc_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await _get_document_or_404(db, doc_id)
    await _verify_kb_access(db, doc.kb_id, current_user.id, "read")
    return await get_document_chunks(db, doc_id, page, page_size)


@router.post("/{doc_id}/retry", response_model=DocumentResponse)
async def retry(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc_row = await _get_document_or_404(db, doc_id)
    await _verify_kb_access(db, doc_row.kb_id, current_user.id, "write")
    doc = await retry_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在或状态不可重试")
    dispatch_task(process_document_task, doc.id, doc.kb_id)
    return doc


@router.get("/{doc_id}/preview")
async def preview_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the parsed text content of a document (up to 10000 chars)."""
    doc = await _get_document_or_404(db, doc_id)
    await _verify_kb_access(db, doc.kb_id, current_user.id, "read")

    chunks_result = await db.execute(
        select(DocumentChunk.content)
        .where(DocumentChunk.doc_id == doc_id)
        .order_by(DocumentChunk.chunk_index)
    )
    texts = [row[0] for row in chunks_result.all()]
    full_text = "\n\n".join(texts)
    total_chars = len(full_text)
    truncated = full_text[:10000] if total_chars > 10000 else full_text
    return {"content": truncated, "total_chars": total_chars}


@router.delete("/{doc_id}")
async def remove_document(
    doc_id: int,
    permanent: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc_row = await _get_document_or_404(db, doc_id)
    await _verify_kb_access(db, doc_row.kb_id, current_user.id, "write")
    kb_id = await delete_document(db, doc_id, permanent=permanent)
    if kb_id is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"message": "已移至回收站" if not permanent else "已永久删除"}


@router.get("/trash/{kb_id}")
async def get_trash(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List soft-deleted documents in a knowledge base."""
    await _verify_kb_access(db, kb_id, current_user.id, "read")
    from app.services.document_service import list_trash
    items = await list_trash(db, kb_id)
    return {"items": items, "total": len(items)}


@router.post("/{doc_id}/restore")
async def restore_doc(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore a soft-deleted document from trash."""
    # Must query deleted docs directly (not _get_document_or_404 which excludes them)
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.deleted_at.isnot(None))
    )
    doc_row = result.scalar_one_or_none()
    if not doc_row:
        raise HTTPException(404, "文档不在回收站中")
    await _verify_kb_access(db, doc_row.kb_id, current_user.id, "write")
    from app.services.document_service import restore_document
    kb_id = await restore_document(db, doc_id)
    if kb_id is None:
        raise HTTPException(status_code=404, detail="恢复失败")
    return {"message": "已恢复"}


@router.put("/chunks/{chunk_id}")
async def update_chunk(
    chunk_id: int,
    data: ChunkUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(DocumentChunk).where(DocumentChunk.id == chunk_id))
    chunk = result.scalar_one_or_none()
    if not chunk:
        raise HTTPException(404, "切片不存在")
    await _verify_kb_access(db, chunk.kb_id, current_user.id, "write")
    chunk.content = data.content
    await db.commit()
    await update_chunk_in_collection(db, chunk.kb_id, chunk.doc_id, chunk.chunk_index, data.content)
    _invalidate_bm25(chunk.kb_id)
    return {"message": "更新成功", "id": chunk.id}


@router.post("/chunks")
async def create_chunk(
    data: ChunkCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_kb_access(db, data.kb_id, current_user.id, "write")
    doc_result = await db.execute(
        select(Document).where(Document.id == data.doc_id, Document.kb_id == data.kb_id, Document.deleted_at.is_(None))
    )
    if not doc_result.scalar_one_or_none():
        raise HTTPException(404, "文档不存在")

    max_idx_result = await db.execute(
        select(DocumentChunk.chunk_index)
        .where(DocumentChunk.doc_id == data.doc_id)
        .order_by(DocumentChunk.chunk_index.desc())
        .limit(1)
    )
    max_idx = max_idx_result.scalar() or 0

    chunk = DocumentChunk(
        doc_id=data.doc_id,
        kb_id=data.kb_id,
        content=data.content,
        chunk_index=max_idx + 1,
    )
    db.add(chunk)
    await db.commit()
    await db.refresh(chunk)
    await add_chunk_to_collection(db, data.kb_id, data.doc_id, chunk.chunk_index, data.content)
    _invalidate_bm25(data.kb_id)
    return {"message": "创建成功", "id": chunk.id}


@router.delete("/chunks/{chunk_id}")
async def delete_chunk(
    chunk_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(DocumentChunk).where(DocumentChunk.id == chunk_id))
    chunk = result.scalar_one_or_none()
    if not chunk:
        raise HTTPException(404, "切片不存在")
    await _verify_kb_access(db, chunk.kb_id, current_user.id, "write")
    kb_id = chunk.kb_id
    doc_id = chunk.doc_id
    chunk_index = chunk.chunk_index
    await db.delete(chunk)
    await db.commit()
    delete_chunk_from_collection(kb_id, doc_id, chunk_index)
    _invalidate_bm25(kb_id)
    return {"message": "删除成功"}


@router.post("/preview-chunks")
async def preview_chunks(
    file: UploadFile = File(...),
    strategy: str = "fixed",
    chunk_size: int = None,
    chunk_overlap: int = None,
    _: User = Depends(get_current_user),
):
    """Parse a file and return chunk preview without persisting anything."""
    import tempfile, os
    from app.config import settings
    ext = os.path.splitext(file.filename or "")[1].lower()
    if not ext:
        raise HTTPException(400, "无法识别文件类型")

    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(400, f"文件大小超过限制 {settings.MAX_UPLOAD_SIZE_MB}MB")
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        text = parse_document(tmp_path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        os.unlink(tmp_path)

    if not text or not text.strip():
        return {"chunks": [], "total": 0, "text_length": 0}

    chunks = split_text(text, strategy=strategy, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return {
        "chunks": [{"index": i, "content": c, "length": len(c)} for i, c in enumerate(chunks)],
        "total": len(chunks),
        "text_length": len(text),
    }


# ---------------------------------------------------------------------------
# File automation endpoints
# ---------------------------------------------------------------------------


@router.get("/{kb_id}/expiring")
async def get_expiring_documents(
    kb_id: int,
    days: int = Query(7, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出即将过期的文档。"""
    await _verify_kb_access(db, kb_id, current_user.id, "read")
    from app.services.file_automation_service import check_expiring_documents
    all_expiring = await check_expiring_documents(db, days, kb_id=kb_id)
    return all_expiring


@router.post("/{doc_id}/tags")
async def update_document_tags(
    doc_id: int,
    data: TagUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动添加/编辑文档标签。"""
    import json as _json
    doc = await _get_document_or_404(db, doc_id)
    await _verify_kb_access(db, doc.kb_id, current_user.id, "write")

    tags_json = _json.dumps(data.tags, ensure_ascii=False)
    await db.execute(
        update(Document).where(Document.id == doc_id).values(auto_tags=tags_json)
    )
    await db.commit()
    return {"message": "标签更新成功", "tags": data.tags}


@router.post("/check-duplicate", response_model=DuplicateCheckResponse)
async def check_duplicate_endpoint(
    data: DuplicateCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """检查文件是否重复（上传前调用）。"""
    await _verify_kb_access(db, data.kb_id, current_user.id, "read")
    from app.services.file_automation_service import check_duplicate
    dup = await check_duplicate(db, data.kb_id, data.content_hash)
    if dup:
        return DuplicateCheckResponse(
            is_duplicate=True,
            existing_document=DocumentResponse.model_validate(dup),
        )
    return DuplicateCheckResponse(is_duplicate=False)


@router.post("/suggest-kb", response_model=SuggestKBResponse)
async def suggest_kb_endpoint(
    data: SuggestKBRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据文件名和内容预览，推荐合适的知识库。"""
    from app.services.file_automation_service import suggest_knowledge_base
    suggestions = await suggest_knowledge_base(
        db, current_user.id, data.filename, data.content_preview,
    )
    return SuggestKBResponse(
        suggestions=[KBSuggestion(**s) for s in suggestions]
    )


@router.put("/{doc_id}/expiry")
async def set_document_expiry(
    doc_id: int,
    data: ExpiryUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """设置或移除文档过期日期。"""
    doc = await _get_document_or_404(db, doc_id)
    await _verify_kb_access(db, doc.kb_id, current_user.id, "write")

    await db.execute(
        update(Document).where(Document.id == doc_id).values(expires_at=data.expires_at)
    )
    await db.commit()
    action = "已设置" if data.expires_at else "已移除"
    return {"message": f"过期日期{action}", "expires_at": data.expires_at}
