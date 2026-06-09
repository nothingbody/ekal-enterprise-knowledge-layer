"""
Scheduled web crawl service — periodic re-crawl dispatch.

Content change detection and re-indexing logic lives in
``app.tasks.document_tasks._async_crawl_url`` which handles both
first-time crawls and scheduled re-crawls.
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.web_source import WebSource, WebSourceStatus

logger = logging.getLogger(__name__)


def compute_content_hash(content: str) -> str:
    normalized = " ".join(content.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def check_and_dispatch_crawls(db: AsyncSession) -> int:
    """Find web sources due for a scheduled crawl and dispatch tasks.

    Returns the number of sources dispatched.
    """
    from app.models.knowledge_base import KnowledgeBase

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(WebSource)
        .join(KnowledgeBase, KnowledgeBase.id == WebSource.kb_id)
        .where(
            KnowledgeBase.deleted_at.is_(None),
            WebSource.crawl_interval_hours.isnot(None),
            WebSource.next_crawl_at.isnot(None),
            WebSource.next_crawl_at <= now,
            WebSource.status != WebSourceStatus.CRAWLING,
        )
    )
    sources = result.scalars().all()
    if not sources:
        return 0

    from app.tasks.document_tasks import crawl_web_source_task
    from app.core.task_runner import dispatch as dispatch_task

    dispatched = 0
    for source in sources:
        sid = source.id
        url = source.url
        interval_h = source.crawl_interval_hours or 24
        try:
            next_time = now + timedelta(hours=interval_h)
            # Set status to PENDING and next_crawl_at atomically BEFORE dispatch
            # to prevent another scheduler from picking up the same source
            result = await db.execute(
                update(WebSource)
                .where(
                    WebSource.id == sid,
                    WebSource.status != WebSourceStatus.PENDING,  # Guard: skip if already dispatched
                )
                .values(
                    status=WebSourceStatus.PENDING,
                    error_message=None,
                    next_crawl_at=next_time,
                )
            )
            await db.commit()
            if result.rowcount == 0:
                continue  # Already dispatched by another scheduler

            dispatch_task(crawl_web_source_task, sid)
            dispatched += 1
            logger.info(
                "已调度定时抓取: source_id=%s url=%s next=%s",
                sid, url, next_time,
            )
        except Exception:
            logger.exception("调度定时抓取失败: source_id=%s", sid)
            await db.rollback()

    return dispatched


async def run_scheduler_loop() -> None:
    """Infinite loop that checks for due crawls every 5 minutes.

    Designed to be launched via asyncio.create_task in the app lifespan.
    """
    import asyncio
    from app.database import async_session

    INTERVAL_SECONDS = 5 * 60

    while True:
        try:
            async with async_session() as db:
                count = await check_and_dispatch_crawls(db)
                if count:
                    logger.info("本轮调度了 %d 个定时抓取任务", count)
        except Exception:
            logger.exception("定时抓取调度循环异常")

        await asyncio.sleep(INTERVAL_SECONDS)
