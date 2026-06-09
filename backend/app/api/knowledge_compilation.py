"""API endpoints for Knowledge Compilation (Karpathy LLM Wiki integration)."""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func, desc

from app.database import get_db
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.compiled_article import CompiledArticle, CompiledArticleStatus, ArticleCrossRef
from app.models.health_report import HealthReport, HealthReportStatus
from app.core.security import get_current_user
from app.core.knowledge_compilation.config import KnowledgeCompilationConfig
from app.services.access_service import require_kb_access
from app.schemas.knowledge_compilation import (
    CompiledArticleResponse,
    ArticleUpdateRequest,
    HealthReportResponse,
    ArticleCrossRefResponse,
    CompilationConfigRequest,
    CompilationConfigResponse,
    CompilationStatusResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_kb_or_404(db: AsyncSession, kb_id: int) -> KnowledgeBase:
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.deleted_at.is_(None),
        )
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(404, "知识库不存在")
    return kb


def _parse_json_list(raw: Optional[str]) -> Optional[list]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _article_to_response(article: CompiledArticle) -> CompiledArticleResponse:
    return CompiledArticleResponse(
        id=article.id,
        kb_id=article.kb_id,
        title=article.title,
        content=article.content,
        summary=article.summary,
        tags=_parse_json_list(article.tags),
        source_doc_ids=_parse_json_list(article.source_doc_ids),
        version=article.version,
        status=article.status,
        token_count=article.token_count,
        created_at=article.created_at,
        updated_at=article.updated_at,
    )


def _health_report_to_response(report: HealthReport) -> HealthReportResponse:
    return HealthReportResponse(
        id=report.id,
        kb_id=report.kb_id,
        status=report.status,
        summary=json.loads(report.summary) if report.summary else None,
        findings=json.loads(report.findings) if report.findings else None,
        created_at=report.created_at,
        completed_at=report.completed_at,
        token_cost=report.token_cost,
    )


# ---------------------------------------------------------------------------
# Compilation Config
# ---------------------------------------------------------------------------

@router.get("/{kb_id}/compilation-config", response_model=CompilationConfigResponse)
async def get_compilation_config(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_kb_access(db, kb_id, current_user.id, "read")
    kb = await _get_kb_or_404(db, kb_id)
    raw = getattr(kb, "knowledge_compilation_config", None)
    if raw:
        try:
            data = json.loads(raw)
            return CompilationConfigResponse(**data)
        except Exception:
            pass
    return CompilationConfigResponse()


@router.put("/{kb_id}/compilation-config", response_model=CompilationConfigResponse)
async def update_compilation_config(
    kb_id: int,
    req: CompilationConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_kb_access(db, kb_id, current_user.id, "write")
    kb = await _get_kb_or_404(db, kb_id)
    config = KnowledgeCompilationConfig(**req.model_dump())
    kb.knowledge_compilation_config = config.to_json()
    await db.commit()
    return CompilationConfigResponse(**req.model_dump())


# ---------------------------------------------------------------------------
# Compiled Articles
# ---------------------------------------------------------------------------

@router.get("/{kb_id}/articles", response_model=List[CompiledArticleResponse])
async def list_articles(
    kb_id: int,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_kb_access(db, kb_id, current_user.id, "read")

    query = (
        select(CompiledArticle)
        .where(
            CompiledArticle.kb_id == kb_id,
            CompiledArticle.deleted_at.is_(None),
        )
        .order_by(desc(CompiledArticle.updated_at))
    )
    if status:
        query = query.where(CompiledArticle.status == status)
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    articles = result.scalars().all()
    return [_article_to_response(a) for a in articles]


@router.get("/articles/{article_id}", response_model=CompiledArticleResponse)
async def get_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CompiledArticle).where(
            CompiledArticle.id == article_id,
            CompiledArticle.deleted_at.is_(None),
        )
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(404, "编译文章不存在")
    await require_kb_access(db, article.kb_id, current_user.id, "read")
    return _article_to_response(article)


@router.put("/articles/{article_id}", response_model=CompiledArticleResponse)
async def update_article(
    article_id: int,
    req: ArticleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CompiledArticle).where(
            CompiledArticle.id == article_id,
            CompiledArticle.deleted_at.is_(None),
        )
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(404, "编译文章不存在")
    await require_kb_access(db, article.kb_id, current_user.id, "write")

    if req.title is not None:
        article.title = req.title
    if req.content is not None:
        article.content = req.content
    if req.summary is not None:
        article.summary = req.summary
    if req.tags is not None:
        article.tags = json.dumps(req.tags, ensure_ascii=False)
    article.version += 1

    await db.commit()
    await db.refresh(article)
    return _article_to_response(article)


@router.delete("/articles/{article_id}")
async def delete_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CompiledArticle).where(CompiledArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(404, "编译文章不存在")
    await require_kb_access(db, article.kb_id, current_user.id, "write")

    from sqlalchemy.sql import func
    article.deleted_at = func.now()
    await db.commit()

    # Remove from vector store
    try:
        from app.core.vector_store import get_vector_store
        from app.services.embedding_service import get_collection_name
        store = get_vector_store()
        store.delete_by_ids(get_collection_name(article.kb_id), [f"article_{article.id}"])
    except Exception:
        pass

    return {"detail": "已删除"}


# ---------------------------------------------------------------------------
# Compilation Triggers
# ---------------------------------------------------------------------------

@router.post("/{kb_id}/compile")
async def trigger_compile_kb(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger full KB compilation (all documents)."""
    await require_kb_access(db, kb_id, current_user.id, "write")
    kb = await _get_kb_or_404(db, kb_id)

    from app.tasks.compilation_tasks import compile_kb_task
    from app.core.task_runner import dispatch as dispatch_task
    dispatch_task(compile_kb_task, kb_id, kb.user_id)
    return {"detail": "全量编译任务已提交", "kb_id": kb_id}


@router.post("/{kb_id}/compile/{doc_id}")
async def trigger_compile_document(
    kb_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger compilation for a single document."""
    await require_kb_access(db, kb_id, current_user.id, "write")
    await _get_kb_or_404(db, kb_id)

    from app.models.document import Document
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.kb_id == kb_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "文档不存在")

    from app.tasks.compilation_tasks import compile_document_task
    from app.core.task_runner import dispatch as dispatch_task
    dispatch_task(compile_document_task, doc_id, kb_id)
    return {"detail": "文档编译任务已提交", "doc_id": doc_id}


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@router.get("/{kb_id}/health-reports", response_model=List[HealthReportResponse])
async def list_health_reports(
    kb_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_kb_access(db, kb_id, current_user.id, "read")
    result = await db.execute(
        select(HealthReport)
        .where(HealthReport.kb_id == kb_id)
        .order_by(desc(HealthReport.created_at))
        .offset(skip)
        .limit(limit)
    )
    reports = result.scalars().all()
    return [_health_report_to_response(r) for r in reports]


@router.get("/health-reports/{report_id}", response_model=HealthReportResponse)
async def get_health_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(HealthReport).where(HealthReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "健康报告不存在")
    await require_kb_access(db, report.kb_id, current_user.id, "read")
    return _health_report_to_response(report)


@router.post("/{kb_id}/health-check")
async def trigger_health_check(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger an on-demand health check."""
    await require_kb_access(db, kb_id, current_user.id, "write")
    kb = await _get_kb_or_404(db, kb_id)

    from app.tasks.compilation_tasks import health_check_task
    from app.core.task_runner import dispatch as dispatch_task
    dispatch_task(health_check_task, kb_id, kb.user_id)
    return {"detail": "健康检查任务已提交", "kb_id": kb_id}


# ---------------------------------------------------------------------------
# Cross References
# ---------------------------------------------------------------------------

@router.get("/{kb_id}/cross-refs", response_model=List[ArticleCrossRefResponse])
async def list_cross_refs(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_kb_access(db, kb_id, current_user.id, "read")

    # Get all articles for this KB, then their cross refs
    article_ids_result = await db.execute(
        select(CompiledArticle.id).where(
            CompiledArticle.kb_id == kb_id,
            CompiledArticle.deleted_at.is_(None),
        )
    )
    article_ids = [row[0] for row in article_ids_result.all()]
    if not article_ids:
        return []

    refs_result = await db.execute(
        select(ArticleCrossRef).where(
            ArticleCrossRef.from_article_id.in_(article_ids)
        )
    )
    refs = refs_result.scalars().all()

    # Resolve titles
    all_ref_ids = set()
    for ref in refs:
        all_ref_ids.add(ref.from_article_id)
        all_ref_ids.add(ref.to_article_id)
    title_result = await db.execute(
        select(CompiledArticle.id, CompiledArticle.title).where(
            CompiledArticle.id.in_(all_ref_ids)
        )
    )
    title_map = {row.id: row.title for row in title_result.all()}

    return [
        ArticleCrossRefResponse(
            id=ref.id,
            from_article_id=ref.from_article_id,
            from_article_title=title_map.get(ref.from_article_id),
            to_article_id=ref.to_article_id,
            to_article_title=title_map.get(ref.to_article_id),
            relationship_type=ref.relationship_type,
            created_at=ref.created_at,
        )
        for ref in refs
    ]


# ---------------------------------------------------------------------------
# Compilation Status
# ---------------------------------------------------------------------------

@router.get("/{kb_id}/compilation-status", response_model=CompilationStatusResponse)
async def get_compilation_status(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_kb_access(db, kb_id, current_user.id, "read")
    kb = await _get_kb_or_404(db, kb_id)

    config = KnowledgeCompilationConfig.from_json(
        getattr(kb, "knowledge_compilation_config", None)
    )

    # Count articles by status
    count_result = await db.execute(
        select(
            CompiledArticle.status,
            sa_func.count(CompiledArticle.id),
        )
        .where(
            CompiledArticle.kb_id == kb_id,
            CompiledArticle.deleted_at.is_(None),
        )
        .group_by(CompiledArticle.status)
    )
    status_counts = {row[0]: row[1] for row in count_result.all()}

    total = sum(status_counts.values())
    compiled = status_counts.get(CompiledArticleStatus.COMPILED.value, 0)
    outdated = status_counts.get(CompiledArticleStatus.OUTDATED.value, 0)
    drafting = status_counts.get(CompiledArticleStatus.DRAFTING.value, 0)

    # Last compiled timestamp
    last_compiled_result = await db.execute(
        select(sa_func.max(CompiledArticle.updated_at)).where(
            CompiledArticle.kb_id == kb_id,
            CompiledArticle.status == CompiledArticleStatus.COMPILED.value,
        )
    )
    last_compiled_at = last_compiled_result.scalar()

    # Last health check
    last_hc_result = await db.execute(
        select(sa_func.max(HealthReport.completed_at)).where(
            HealthReport.kb_id == kb_id,
            HealthReport.status == HealthReportStatus.COMPLETED.value,
        )
    )
    last_health_check_at = last_hc_result.scalar()

    # Latest health score
    health_score = None
    latest_report_result = await db.execute(
        select(HealthReport.summary)
        .where(
            HealthReport.kb_id == kb_id,
            HealthReport.status == HealthReportStatus.COMPLETED.value,
        )
        .order_by(desc(HealthReport.completed_at))
        .limit(1)
    )
    latest_summary = latest_report_result.scalar()
    if latest_summary:
        try:
            health_score = json.loads(latest_summary).get("score")
        except Exception:
            pass

    return CompilationStatusResponse(
        enabled=config.enabled if config else False,
        total_articles=total,
        compiled_articles=compiled,
        outdated_articles=outdated,
        drafting_articles=drafting,
        last_compiled_at=last_compiled_at,
        last_health_check_at=last_health_check_at,
        health_score=health_score,
    )
