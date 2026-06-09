import os
import uuid
from pathlib import Path
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from fastapi import UploadFile, HTTPException

from app.config import settings
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.schemas.document import DocumentResponse
from app.core.parser import parse_document
from app.core.chunking import split_text, split_text_fixed

import logging

_logger = logging.getLogger(__name__)

from app.services.knowledge_base_service import refresh_kb_counts as _refresh_kb_counts


def _invalidate_bm25(kb_id: int) -> None:
    try:
        from app.services.retrieval_service import invalidate_bm25_cache
        invalidate_bm25_cache(kb_id)
    except Exception as exc:
        _logger.warning("BM25 缓存失效失败 (kb_id=%s): %s", kb_id, exc)


ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xlsx", ".xls", ".csv",
    ".pptx", ".txt", ".md", ".html", ".htm",
    # Image formats (OCR via LLM vision)
    ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp",
}

MIME_WHITELIST = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel", "text/csv",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain", "text/markdown", "text/html",
    "application/octet-stream",  # fallback for unknown binary
    # Image MIME types
    "image/png", "image/jpeg", "image/tiff", "image/bmp", "image/webp",
}


def _sanitize_filename(filename: str) -> str:
    """Strip path traversal components and dangerous characters from filename."""
    import re
    # Take only the final path component (strip directory traversal)
    name = Path(filename).name
    # Remove null bytes and control characters
    name = re.sub(r'[\x00-\x1f]', '', name)
    # Remove characters that could cause issues in HTML/filesystem
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Collapse multiple underscores/dots
    name = re.sub(r'_{2,}', '_', name)
    # Prevent hidden files (leading dot)
    name = name.lstrip('.')
    # Fallback if name is empty after sanitization
    if not name or not name.strip():
        name = "unnamed_file"
    # Limit filename length
    if len(name) > 255:
        ext = Path(name).suffix
        name = name[:255 - len(ext)] + ext
    return name


def _validate_file(filename: str, content_type: str | None, size: int):
    ext = Path(filename).suffix.lower() if filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 '{ext}'，允许: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    if content_type and content_type not in MIME_WHITELIST:
        raise HTTPException(status_code=400, detail=f"不支持的 MIME 类型: {content_type}")
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if size > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小 {size / 1024 / 1024:.1f}MB 超过限制 {settings.MAX_UPLOAD_SIZE_MB}MB",
        )


async def upload_document(
    db: AsyncSession,
    kb_id: int,
    file: UploadFile,
    force_replace: bool = False,
) -> DocumentResponse:
    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.deleted_at.is_(None))
    )
    kb = kb_result.scalar_one_or_none()
    if not kb:
        raise ValueError("知识库不存在或已删除")

    content = await file.read()
    _validate_file(file.filename, file.content_type, len(content))
    safe_filename = _sanitize_filename(file.filename)

    from app.services.file_automation_service import compute_bytes_hash, check_duplicate
    content_hash = compute_bytes_hash(content)

    dup = await check_duplicate(db, kb_id, content_hash)
    if dup:
        _logger.info(
            "发现重复文档 '%s' (doc_id=%s, kb_id=%s)，同名则替换，否则跳过",
            dup.filename, dup.id, kb_id,
        )
        if dup.filename != safe_filename:
            from fastapi import HTTPException as _HTTPException
            raise _HTTPException(
                status_code=409,
                detail=f"知识库中已存在相同内容的文档「{dup.filename}」(ID: {dup.id})",
            )

    # Incremental update: if a document with the same filename already exists
    # in this KB, require explicit confirmation via force_replace parameter.
    existing = (await db.execute(
        select(Document).where(
            Document.kb_id == kb_id,
            Document.filename == safe_filename,
            Document.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if existing:
        if not force_replace:
            from fastapi import HTTPException as _HTTPException
            raise _HTTPException(
                status_code=409,
                detail={
                    "code": "duplicate_filename",
                    "message": f"知识库中已存在同名文档「{safe_filename}」",
                    "existing_doc_id": existing.id,
                    "existing_chunks": existing.chunk_count,
                    "created_at": str(existing.created_at),
                },
            )
        _logger.info("增量更新：替换同名文档 '%s' (doc_id=%s, kb_id=%s)",
                      safe_filename, existing.id, kb_id)
        from app.services.embedding_service import delete_doc_chunks_from_collection
        try:
            delete_doc_chunks_from_collection(kb_id, existing.id)
        except Exception:
            pass
        await db.execute(delete(DocumentChunk).where(DocumentChunk.doc_id == existing.id))
        old_path = existing.file_path
        await db.delete(existing)
        await db.commit()
        if old_path and os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
        _invalidate_bm25(kb_id)

    kb_dir = os.path.join(settings.UPLOAD_DIR, str(kb_id))
    os.makedirs(kb_dir, exist_ok=True)

    ext = Path(safe_filename).suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(kb_dir, stored_name)

    with open(file_path, "wb") as f:
        f.write(content)

    doc = Document(
        kb_id=kb_id,
        filename=safe_filename,
        file_path=file_path,
        file_size=len(content),
        file_type=ext.lstrip("."),
        content_hash=content_hash,
        status=DocumentStatus.UPLOADING,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    try:
        import asyncio
        from app.services.automation_service import fire_event
        asyncio.ensure_future(fire_event("document.uploaded", {"doc_id": doc.id, "kb_id": kb_id}))
    except Exception:
        pass

    return DocumentResponse.model_validate(doc)


# Image extensions that require LLM vision OCR
_OCR_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
# Document formats that may contain embedded images
_EMBEDDED_IMG_EXTS = {".docx", ".pptx"}


async def _get_ocr_model_for_doc(db: AsyncSession, doc: "Document"):
    """Resolve the OCR model for a document's KB owner. Returns (model, kb) or (None, None)."""
    from app.core.ocr import get_ocr_model

    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == doc.kb_id)
    )
    kb = kb_result.scalar_one_or_none()
    if not kb:
        return None, None
    model = await get_ocr_model(db, kb.user_id)
    return model, kb


async def _try_ocr_fallback(db: AsyncSession, doc: "Document", ext: str) -> Optional[str]:
    """Attempt LLM vision OCR for images or scanned PDFs.

    Returns extracted text, or None if no OCR model is available.
    """
    from app.core.ocr import ocr_image, ocr_pdf_pages

    model, _kb = await _get_ocr_model_for_doc(db, doc)
    if not model:
        return None

    if ext in _OCR_IMAGE_EXTS:
        return await ocr_image(doc.file_path, model)
    elif ext == ".pdf":
        return await ocr_pdf_pages(doc.file_path, model)
    return None


async def _try_ocr_embedded_images(db: AsyncSession, doc: "Document", ext: str) -> Optional[str]:
    """Extract and OCR embedded images from DOCX/PPTX documents.

    Returns OCR text from images, or None if no images or no model.
    """
    from app.core.ocr import (
        extract_docx_images, extract_pptx_images, ocr_embedded_images,
    )

    if ext == ".docx":
        images = extract_docx_images(doc.file_path)
    elif ext == ".pptx":
        images = extract_pptx_images(doc.file_path)
    else:
        return None

    if not images:
        return None

    _logger.info("发现 %d 张嵌入图片，尝试 OCR (doc_id=%s)", len(images), doc.id)
    model, _kb = await _get_ocr_model_for_doc(db, doc)
    if not model:
        _logger.info("未配置 LLM 模型，跳过嵌入图片 OCR (doc_id=%s)", doc.id)
        return None

    return await ocr_embedded_images(images, model, source_label=doc.filename)


async def process_document(db: AsyncSession, doc_id: int):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        return

    try:
        await db.execute(
            update(Document).where(Document.id == doc_id).values(status=DocumentStatus.PARSING)
        )
        await db.commit()

        ext = Path(doc.file_path).suffix.lower()
        text = parse_document(doc.file_path)

        # If text extraction returned empty, try LLM vision OCR
        if not text or not text.strip():
            _logger.info("文本提取为空，尝试 LLM 视觉 OCR (doc_id=%s, ext=%s)", doc_id, ext)
            ocr_text = await _try_ocr_fallback(db, doc, ext)
            if ocr_text and ocr_text.strip():
                text = ocr_text

        # For DOCX/PPTX: also OCR any embedded images and append to text
        if ext in _EMBEDDED_IMG_EXTS:
            img_text = await _try_ocr_embedded_images(db, doc, ext)
            if img_text and img_text.strip():
                separator = "\n\n--- 图片内容 ---\n\n"
                text = (text or "") + separator + img_text

        if not text or not text.strip():
            if ext in _OCR_IMAGE_EXTS or ext == ".pdf":
                error_msg = (
                    "文档内容为空，可能是扫描版 PDF 或纯图片文件。"
                    "请前往「模型管理」添加一个支持视觉能力的 LLM 模型（如 GPT-4o、Claude 3.5），"
                    "系统将自动使用 OCR 识别文档内容。"
                )
            else:
                error_msg = "文档内容为空，请检查文件是否损坏或格式是否正确。"
            await db.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(status=DocumentStatus.FAILED, error_message=error_msg)
            )
            await db.commit()
            return

        kb_result2 = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == doc.kb_id))
        kb = kb_result2.scalar_one_or_none()
        strategy = getattr(kb, 'chunk_strategy', 'fixed') or 'fixed'
        cs = getattr(kb, 'chunk_size', None)
        co = getattr(kb, 'chunk_overlap', None)
        chunks = split_text(text, strategy=strategy, chunk_size=cs, chunk_overlap=co)

        for idx, chunk_text in enumerate(chunks):
            chunk = DocumentChunk(
                doc_id=doc_id,
                kb_id=doc.kb_id,
                content=chunk_text,
                chunk_index=idx,
            )
            db.add(chunk)

        await db.execute(
            update(Document)
            .where(Document.id == doc_id)
            .values(status=DocumentStatus.EMBEDDING, chunk_count=len(chunks))
        )
        await db.commit()

        try:
            from app.services.file_automation_service import auto_tag_document
            llm_for_tags, _kb2 = await _get_ocr_model_for_doc(db, doc)
            await auto_tag_document(db, doc_id, llm_config=llm_for_tags)
        except Exception as exc:
            _logger.warning("自动标签失败 (doc_id=%s): %s", doc_id, exc)

        return doc.kb_id, chunks, doc_id

    except Exception as e:
        error_detail = str(e)
        error_type = type(e).__name__
        if "codec" in error_detail.lower() or "decode" in error_detail.lower():
            friendly_msg = "文件编码不支持。请确认文件未损坏，或尝试将文件转换为 UTF-8 编码后重新上传。"
        elif "password" in error_detail.lower() or "encrypted" in error_detail.lower():
            friendly_msg = "文件已加密或受密码保护，请移除密码保护后重新上传。"
        elif "corrupt" in error_detail.lower() or "invalid" in error_detail.lower():
            friendly_msg = f"文件格式异常，可能已损坏。请检查文件是否完整后重新上传。({error_type})"
        elif "memory" in error_detail.lower() or "too large" in error_detail.lower():
            friendly_msg = "文件过大导致内存不足。请尝试拆分文件后分批上传。"
        else:
            friendly_msg = f"解析失败: {error_detail[:200]}"
        await db.execute(
            update(Document)
            .where(Document.id == doc_id)
            .values(status=DocumentStatus.FAILED, error_message=friendly_msg)
        )
        await db.commit()
        raise


async def mark_document_completed(db: AsyncSession, doc_id: int):
    await db.execute(
        update(Document).where(Document.id == doc_id).values(status=DocumentStatus.COMPLETED)
    )
    await db.commit()
    kb_result = await db.execute(select(Document.kb_id).where(Document.id == doc_id))
    kb_id = kb_result.scalar_one()
    await _refresh_kb_counts(db, kb_id)
    _invalidate_bm25(kb_id)

    try:
        import asyncio
        from app.services.automation_service import fire_event
        asyncio.ensure_future(fire_event("document.processed", {"doc_id": doc_id, "kb_id": kb_id}))
    except Exception:
        pass




async def list_documents(
    db: AsyncSession, kb_id: int, page: int = 1, page_size: int = 20
) -> dict:
    total = (await db.execute(
        select(func.count(Document.id)).where(Document.kb_id == kb_id, Document.deleted_at.is_(None))
    )).scalar() or 0

    result = await db.execute(
        select(Document)
        .where(Document.kb_id == kb_id, Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    _STALLED_THRESHOLD = _td(minutes=30)
    _now = _dt.now(_tz.utc)
    items = []
    for d in result.scalars().all():
        item = DocumentResponse.model_validate(d)
        # Detect stalled documents: still processing after 30 minutes
        if d.status in (DocumentStatus.PARSING, DocumentStatus.EMBEDDING, DocumentStatus.UPLOADING):
            created = d.created_at.replace(tzinfo=_tz.utc) if d.created_at and d.created_at.tzinfo is None else d.created_at
            if created and _now - created > _STALLED_THRESHOLD:
                item.is_stalled = True
        items.append(item)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def delete_document(db: AsyncSession, doc_id: int, permanent: bool = False) -> Optional[int]:
    result = await db.execute(
        select(Document).where(Document.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        return None

    kb_id = doc.kb_id

    if not permanent and not doc.deleted_at:
        from datetime import datetime, timezone
        doc.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        await _refresh_kb_counts(db, kb_id)
        _invalidate_bm25(kb_id)
        return kb_id

    file_path = doc.file_path

    from app.services.embedding_service import delete_doc_chunks_from_collection
    try:
        delete_doc_chunks_from_collection(kb_id, doc_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(
            "向量存储删除失败 (kb_id=%s, doc_id=%s): %s — 继续删除 DB 记录",
            kb_id, doc_id, e,
        )

    await db.execute(delete(DocumentChunk).where(DocumentChunk.doc_id == doc_id))
    await db.delete(doc)

    # Delete file BEFORE commit so DB can rollback if file deletion fails
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError as _del_err:
            import logging
            logging.getLogger(__name__).warning(
                "文件删除失败 (doc_id=%s, path=%s): %s — 继续删除 DB 记录",
                doc_id, file_path, _del_err,
            )

    await db.commit()

    await _refresh_kb_counts(db, kb_id)
    _invalidate_bm25(kb_id)
    return kb_id


async def restore_document(db: AsyncSession, doc_id: int) -> Optional[int]:
    """Restore a soft-deleted document."""
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.deleted_at.isnot(None))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        return None
    doc.deleted_at = None
    await db.commit()
    await _refresh_kb_counts(db, doc.kb_id)
    return doc.kb_id


async def list_trash(db: AsyncSession, kb_id: int, limit: int = 100) -> list:
    """List soft-deleted documents in a knowledge base (capped at `limit`)."""
    result = await db.execute(
        select(Document)
        .where(Document.kb_id == kb_id, Document.deleted_at.isnot(None))
        .order_by(Document.deleted_at.desc())
        .limit(limit)
    )
    return [DocumentResponse.model_validate(d) for d in result.scalars().all()]


async def retry_document(db: AsyncSession, doc_id: int) -> Optional[DocumentResponse]:
    result = await db.execute(
        select(Document).where(Document.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc or doc.status != DocumentStatus.FAILED:
        return None

    from app.services.embedding_service import delete_doc_chunks_from_collection
    try:
        delete_doc_chunks_from_collection(doc.kb_id, doc_id)
    except Exception:
        pass

    await db.execute(delete(DocumentChunk).where(DocumentChunk.doc_id == doc_id))
    await db.execute(
        update(Document).where(Document.id == doc_id)
        .values(status=DocumentStatus.UPLOADING, error_message=None, chunk_count=0)
    )
    await db.commit()
    await db.refresh(doc)
    _invalidate_bm25(doc.kb_id)
    return DocumentResponse.model_validate(doc)


async def get_document_chunks(
    db: AsyncSession, doc_id: int, page: int = 1, page_size: int = 20
) -> dict:
    total = (await db.execute(
        select(func.count(DocumentChunk.id)).where(DocumentChunk.doc_id == doc_id)
    )).scalar() or 0

    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.doc_id == doc_id)
        .order_by(DocumentChunk.chunk_index)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    from app.schemas.document import DocumentChunkResponse
    items = [DocumentChunkResponse.model_validate(c) for c in result.scalars().all()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
