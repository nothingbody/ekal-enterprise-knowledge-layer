"""System-level API endpoints (admin stats, etc.) for frontend compatibility."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User
from app.models.usage import UsageReport
from app.models.chat import ChatConversation, ChatMessage
from app.core.security import get_admin_user

router = APIRouter()


@router.get("/admin-stats")
async def get_admin_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Admin: global system statistics aggregated from all users."""
    from app.models.synced_user_data import SyncedOperationLog

    total_users = (await db.execute(
        select(func.count(User.id)).where(User.deleted_at.is_(None))
    )).scalar() or 0

    total_conversations = (await db.execute(
        select(func.count(ChatConversation.id))
    )).scalar() or 0

    total_messages = (await db.execute(
        select(func.count(ChatMessage.id))
    )).scalar() or 0

    token_from_usage = (await db.execute(
        select(func.coalesce(func.sum(UsageReport.token_count), 0))
    )).scalar() or 0

    token_from_logs = (await db.execute(
        select(func.coalesce(func.sum(SyncedOperationLog.total_tokens), 0))
    )).scalar() or 0

    return {
        "total_users": total_users,
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "total_tokens": max(token_from_usage, token_from_logs),
    }
