from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.models.web_source import WebSource, WebSourceStatus
from app.models.knowledge_base import KnowledgeBase
from app.core.security import get_current_user
from app.schemas.web_source import WebSourceCreate, WebSourceScheduleUpdate
from app.services.access_service import require_kb_access
from app.tasks.document_tasks import crawl_web_source_task
from app.core.task_runner import dispatch as dispatch_task

router = APIRouter()


def _serialize_source(s: WebSource) -> dict:
    return {
        "id": s.id,
        "url": s.url,
        "source_type": getattr(s, "source_type", None) or "html",
        "title": s.title,
        "status": s.status.value if s.status else None,
        "error_message": s.error_message,
        "created_at": str(s.created_at) if s.created_at else None,
        "crawl_interval_hours": s.crawl_interval_hours,
        "last_crawled_at": str(s.last_crawled_at) if s.last_crawled_at else None,
        "content_hash": s.content_hash,
        "auto_reindex": s.auto_reindex if s.auto_reindex is not None else True,
        "next_crawl_at": str(s.next_crawl_at) if s.next_crawl_at else None,
        "crawl_count": s.crawl_count or 0,
        "use_browser": bool(s.use_browser) if s.use_browser is not None else False,
    }


@router.post("/")
async def add_web_source(
    data: WebSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_kb_access(db, data.kb_id, current_user.id, "write")
    from app.core.url_safety import validate_url_safe
    try:
        validate_url_safe(data.url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    existing = await db.execute(
        select(WebSource).where(
            WebSource.kb_id == data.kb_id,
            WebSource.url == data.url,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "该知识库中已存在相同 URL 的网页数据源")

    now = datetime.now(timezone.utc)
    next_crawl = None
    if data.crawl_interval_hours is not None:
        next_crawl = now + timedelta(hours=data.crawl_interval_hours)

    source = WebSource(
        kb_id=data.kb_id,
        url=data.url,
        source_type=data.source_type,
        crawl_interval_hours=data.crawl_interval_hours,
        auto_reindex=data.auto_reindex,
        use_browser=data.use_browser,
        next_crawl_at=next_crawl,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    dispatch_task(crawl_web_source_task, source.id)
    return _serialize_source(source)


@router.get("/{kb_id}")
async def list_web_sources(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_kb_access(db, kb_id, current_user.id, "read")
    result = await db.execute(
        select(WebSource).where(WebSource.kb_id == kb_id).order_by(WebSource.created_at.desc())
    )
    sources = result.scalars().all()
    return [_serialize_source(s) for s in sources]


@router.get("/source/{source_id}")
async def get_web_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WebSource).where(WebSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Web 数据源不存在")
    await require_kb_access(db, source.kb_id, current_user.id, "read")
    return _serialize_source(source)


@router.get("/source/{source_id}/content")
async def get_web_source_content(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the crawled text content of a web source."""
    result = await db.execute(
        select(WebSource).where(WebSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Web 数据源不存在")
    await require_kb_access(db, source.kb_id, current_user.id, "read")
    return {
        "id": source.id,
        "url": source.url,
        "title": source.title,
        "content": source.content or "",
        "content_length": len(source.content or ""),
        "crawl_count": source.crawl_count or 0,
        "last_crawled_at": str(source.last_crawled_at) if source.last_crawled_at else None,
    }


@router.post("/{source_id}/recrawl")
async def recrawl_web_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WebSource).where(WebSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "数据源不存在")
    await require_kb_access(db, source.kb_id, current_user.id, "write")

    if source.status == WebSourceStatus.CRAWLING:
        raise HTTPException(409, "该数据源正在抓取中，请等待完成后再重试")

    from app.models.document import Document, DocumentChunk
    from sqlalchemy import delete as sa_delete
    import logging as _logging
    _logger = _logging.getLogger(__name__)

    file_path_key = source.url[:1000]
    old_docs = (await db.execute(
        select(Document).where(
            Document.kb_id == source.kb_id,
            Document.file_path == file_path_key,
            Document.file_type == "web",
        )
    )).scalars().all()
    old_doc_ids = [d.id for d in old_docs]
    if old_doc_ids:
        try:
            from app.services.embedding_service import delete_doc_chunks_from_collection
            for doc_id in old_doc_ids:
                delete_doc_chunks_from_collection(source.kb_id, doc_id)
        except Exception as vec_err:
            _logger.warning("Web source 重新抓取向量清理失败 (source_id=%s): %s", source_id, vec_err)
        await db.execute(sa_delete(DocumentChunk).where(DocumentChunk.doc_id.in_(old_doc_ids)))
        await db.execute(sa_delete(Document).where(Document.id.in_(old_doc_ids)))

    source.status = WebSourceStatus.PENDING
    source.error_message = None
    source.content = None
    source.content_hash = None
    await db.commit()

    if old_doc_ids:
        from app.services.knowledge_base_service import refresh_kb_counts as _refresh_kb_counts
        from app.services.document_service import _invalidate_bm25
        await _refresh_kb_counts(db, source.kb_id)
        _invalidate_bm25(source.kb_id)

    dispatch_task(crawl_web_source_task, source.id)
    return {**_serialize_source(source), "message": "重新抓取已启动"}


@router.delete("/{source_id}")
async def remove_web_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WebSource).where(WebSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "数据源不存在或无权操作")
    await require_kb_access(db, source.kb_id, current_user.id, "write")

    # Clean up associated documents, chunks and vectors created by this web source
    from app.models.document import Document, DocumentChunk
    from sqlalchemy import delete as sa_delete
    import logging as _logging
    _logger = _logging.getLogger(__name__)

    file_path_key = source.url[:1000]
    old_docs = (await db.execute(
        select(Document).where(
            Document.kb_id == source.kb_id,
            Document.file_path == file_path_key,
            Document.file_type == "web",
        )
    )).scalars().all()
    old_doc_ids = [d.id for d in old_docs]
    if old_doc_ids:
        try:
            from app.services.embedding_service import delete_doc_chunks_from_collection
            for doc_id in old_doc_ids:
                delete_doc_chunks_from_collection(source.kb_id, doc_id)
        except Exception as vec_err:
            _logger.warning("Web source 文档向量清理失败 (source_id=%s): %s", source_id, vec_err)
        await db.execute(sa_delete(DocumentChunk).where(DocumentChunk.doc_id.in_(old_doc_ids)))
        await db.execute(sa_delete(Document).where(Document.id.in_(old_doc_ids)))

    affected_kb_id = source.kb_id
    await db.delete(source)
    await db.commit()

    if old_doc_ids and affected_kb_id:
        from app.services.knowledge_base_service import refresh_kb_counts as _refresh_kb_counts
        from app.services.document_service import _invalidate_bm25
        await _refresh_kb_counts(db, affected_kb_id)
        _invalidate_bm25(affected_kb_id)

    return {"message": "删除成功"}


@router.put("/{source_id}/schedule")
async def update_crawl_schedule(
    source_id: int,
    data: WebSourceScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(WebSource).where(WebSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "数据源不存在")
    await require_kb_access(db, source.kb_id, current_user.id, "write")

    if data.crawl_interval_hours is not None:
        source.crawl_interval_hours = data.crawl_interval_hours
        now = datetime.now(timezone.utc)
        source.next_crawl_at = now + timedelta(hours=data.crawl_interval_hours)
    elif data.crawl_interval_hours is None and "crawl_interval_hours" in (data.model_fields_set or set()):
        source.crawl_interval_hours = None
        source.next_crawl_at = None

    if data.auto_reindex is not None:
        source.auto_reindex = data.auto_reindex

    await db.commit()
    await db.refresh(source)
    return _serialize_source(source)


@router.get("/{kb_id}/crawl-status")
async def get_crawl_status(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_kb_access(db, kb_id, current_user.id, "read")
    result = await db.execute(
        select(WebSource).where(WebSource.kb_id == kb_id).order_by(WebSource.created_at.desc())
    )
    sources = result.scalars().all()

    scheduled = [s for s in sources if s.crawl_interval_hours is not None]
    return {
        "total_sources": len(sources),
        "scheduled_count": len(scheduled),
        "sources": [
            {
                **_serialize_source(s),
                "is_scheduled": s.crawl_interval_hours is not None,
                "is_overdue": (
                    s.next_crawl_at is not None
                    and s.next_crawl_at <= datetime.now(timezone.utc)
                ),
            }
            for s in sources
        ],
    }
