import asyncio
import logging

from app.celery_app import celery

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery.task(bind=True, max_retries=2, default_retry_delay=60)
def sync_database_source_task(self, source_id: int):
    try:
        _run_async(_async_sync_database_source(source_id))
    except Exception as exc:
        logger.warning("数据库源同步失败 (source_id=%s, attempt=%s): %s", source_id, self.request.retries, exc)
        raise self.retry(exc=exc)


async def _async_sync_database_source(source_id: int):
    import app.models  # noqa: F401  — ensure all models are loaded for relationship resolution
    from app.database import async_session
    from app.services.database_source_service import sync_database_source

    async with async_session() as db:
        await sync_database_source(db, source_id)
