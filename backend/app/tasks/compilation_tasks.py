"""
Celery tasks for knowledge compilation, synthesis, and health checks.
"""
import asyncio
import logging

from app.celery_app import celery

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine in a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Compile a single document
# ---------------------------------------------------------------------------

@celery.task(bind=True, max_retries=2, default_retry_delay=60)
def compile_document_task(self, doc_id: int, kb_id: int):
    """Compile a single document's chunks into wiki articles."""
    try:
        _run_async(_async_compile_document(doc_id, kb_id))
    except Exception as exc:
        logger.error("Document compilation failed (doc_id=%s): %s", doc_id, exc)
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


async def _async_compile_document(doc_id: int, kb_id: int):
    from app.database import async_session
    from app.models.knowledge_base import KnowledgeBase
    from app.models.document import Document, DocumentChunk
    from app.core.knowledge_compilation.config import KnowledgeCompilationConfig
    from app.core.knowledge_compilation.compiler import compile_chunks_to_articles
    from sqlalchemy import select

    async with async_session() as db:
        kb_result = await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = kb_result.scalar_one_or_none()
        if not kb:
            logger.warning("KB %s not found for compilation", kb_id)
            return

        config = KnowledgeCompilationConfig.from_json(
            getattr(kb, "knowledge_compilation_config", None)
        )
        if not config:
            # Use default config for manual trigger
            config = KnowledgeCompilationConfig(enabled=True)

        chunk_result = await db.execute(
            select(DocumentChunk.content)
            .where(DocumentChunk.doc_id == doc_id)
            .order_by(DocumentChunk.chunk_index)
        )
        chunks = [row[0] for row in chunk_result.all()]
        if not chunks:
            logger.info("No chunks found for doc_id=%s", doc_id)
            return

        articles = await compile_chunks_to_articles(
            db, kb_id, doc_id, chunks, config, kb.user_id
        )
        logger.info("Compiled %d articles from doc_id=%s", len(articles), doc_id)


# ---------------------------------------------------------------------------
# Compile entire KB
# ---------------------------------------------------------------------------

@celery.task(bind=True, max_retries=1, default_retry_delay=120)
def compile_kb_task(self, kb_id: int, user_id: int = 0):
    """Compile all documents in a KB (full rebuild)."""
    try:
        _run_async(_async_compile_kb(kb_id, user_id))
    except Exception as exc:
        logger.error("KB compilation failed (kb_id=%s): %s", kb_id, exc)
        self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))


async def _async_compile_kb(kb_id: int, user_id: int):
    from app.database import async_session
    from app.models.knowledge_base import KnowledgeBase
    from app.core.knowledge_compilation.config import KnowledgeCompilationConfig
    from app.core.knowledge_compilation.compiler import compile_entire_kb
    from sqlalchemy import select

    async with async_session() as db:
        kb_result = await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = kb_result.scalar_one_or_none()
        if not kb:
            return

        config = KnowledgeCompilationConfig.from_json(
            getattr(kb, "knowledge_compilation_config", None)
        )
        if not config:
            config = KnowledgeCompilationConfig(enabled=True)

        articles = await compile_entire_kb(db, kb_id, config, kb.user_id)
        logger.info("Full KB compilation done: %d articles (kb_id=%s)", len(articles), kb_id)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@celery.task(bind=True, max_retries=1, default_retry_delay=300)
def health_check_task(self, kb_id: int, user_id: int = 0):
    """Run a health check on the knowledge base."""
    try:
        _run_async(_async_health_check(kb_id, user_id))
    except Exception as exc:
        logger.error("Health check failed (kb_id=%s): %s", kb_id, exc)
        self.retry(exc=exc, countdown=300 * (2 ** self.request.retries))


async def _async_health_check(kb_id: int, user_id: int):
    from app.database import async_session
    from app.models.knowledge_base import KnowledgeBase
    from app.core.knowledge_compilation.config import KnowledgeCompilationConfig
    from app.core.knowledge_compilation.health_checker import run_health_check
    from sqlalchemy import select

    async with async_session() as db:
        kb_result = await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = kb_result.scalar_one_or_none()
        if not kb:
            return

        config = KnowledgeCompilationConfig.from_json(
            getattr(kb, "knowledge_compilation_config", None)
        )
        if not config:
            config = KnowledgeCompilationConfig(enabled=True, health_check_enabled=True)

        report = await run_health_check(db, kb_id, config, kb.user_id)
        logger.info("Health check done (kb_id=%s): report_id=%s", kb_id, report.id if report else None)


# ---------------------------------------------------------------------------
# Scheduled health checks
# ---------------------------------------------------------------------------

@celery.task
def scheduled_health_checks_task():
    """Scan all KBs and dispatch health checks for those that are due."""
    _run_async(_async_scheduled_health_checks())


async def _async_scheduled_health_checks():
    from app.database import async_session
    from app.models.knowledge_base import KnowledgeBase
    from app.core.knowledge_compilation.config import KnowledgeCompilationConfig
    from app.core.task_runner import dispatch as dispatch_task
    from sqlalchemy import select
    from datetime import datetime, timedelta, timezone

    async with async_session() as db:
        result = await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.deleted_at.is_(None),
                KnowledgeBase.knowledge_compilation_config.isnot(None),
            )
        )
        kbs = result.scalars().all()

        now = datetime.now(timezone.utc)
        for kb in kbs:
            config = KnowledgeCompilationConfig.from_json(kb.knowledge_compilation_config)
            if not config or not config.health_check_enabled:
                continue

            # Check if enough time has passed since last health check
            last_check = config.last_health_check_at
            interval = timedelta(hours=config.health_check_interval_hours)
            if last_check and (now - last_check) < interval:
                continue

            logger.info("Scheduling health check for kb_id=%s", kb.id)
            dispatch_task(health_check_task, kb.id, kb.user_id)
