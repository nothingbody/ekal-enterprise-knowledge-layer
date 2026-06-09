"""Scheduled maintenance tasks: log cleanup, etc."""
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


@celery.task(bind=True, max_retries=1, default_retry_delay=300)
def cleanup_old_logs_task(self, retention_days: int = 90):
    """Delete operation logs older than retention_days."""
    try:
        deleted = _run_async(_async_cleanup_logs(retention_days))
        logger.info("日志清理完成：删除了 %d 条超过 %d 天的记录", deleted, retention_days)
        return {"deleted": deleted}
    except Exception as exc:
        logger.warning("日志清理失败: %s", exc)
        raise self.retry(exc=exc)


async def _async_cleanup_logs(retention_days: int) -> int:
    from datetime import datetime, timedelta
    from sqlalchemy import delete
    from app.database import async_session
    from app.models.operation_log import OperationLog

    cutoff = datetime.now() - timedelta(days=retention_days)
    async with async_session() as db:
        result = await db.execute(
            delete(OperationLog).where(OperationLog.created_at < cutoff)
        )
        await db.commit()
        return result.rowcount


@celery.task(bind=True, max_retries=1, default_retry_delay=300)
def cleanup_old_conversations_task(self, retention_days: int = 180):
    """Delete chat conversations (and their messages) inactive for over retention_days."""
    try:
        deleted = _run_async(_async_cleanup_conversations(retention_days))
        logger.info("会话清理完成：删除了 %d 条超过 %d 天未活跃的会话", deleted, retention_days)
        return {"deleted": deleted}
    except Exception as exc:
        logger.warning("会话清理失败: %s", exc)
        raise self.retry(exc=exc)


async def _async_cleanup_conversations(retention_days: int) -> int:
    from datetime import datetime, timedelta
    from sqlalchemy import delete, select, func, and_, or_
    from app.database import async_session
    from app.models.chat_history import ChatConversation, ChatMessage

    cutoff = datetime.now() - timedelta(days=retention_days)
    async with async_session() as db:
        # Single query: find conversations created before cutoff whose latest
        # message is also older than cutoff (or have no messages at all).
        latest_msg_subq = (
            select(func.max(ChatMessage.created_at))
            .where(ChatMessage.conversation_id == ChatConversation.id)
            .correlate(ChatConversation)
            .scalar_subquery()
        )
        ids_to_delete = (await db.execute(
            select(ChatConversation.id).where(
                ChatConversation.created_at < cutoff,
                or_(
                    latest_msg_subq.is_(None),
                    latest_msg_subq < cutoff,
                ),
            )
        )).scalars().all()

        if not ids_to_delete:
            return 0

        # Delete messages first, then conversations (batch by 100)
        total = 0
        for i in range(0, len(ids_to_delete), 100):
            batch = ids_to_delete[i:i + 100]
            await db.execute(
                delete(ChatMessage).where(ChatMessage.conversation_id.in_(batch))
            )
            result = await db.execute(
                delete(ChatConversation).where(ChatConversation.id.in_(batch))
            )
            total += result.rowcount
            await db.commit()
        return total
