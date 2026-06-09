"""
运营分析 API。

提供对话统计、知识库分析、问题分析等功能。
"""
from datetime import date, datetime, timedelta
from typing import Optional, Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ChatConversation, ChatMessage, KnowledgeBase, User
from app.api.auth import get_current_user
from app.core.security import get_admin_user

router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_date_range(period: str) -> tuple[date, date]:
    """根据周期获取日期范围。"""
    today = date.today()
    if period == "7d":
        start = today - timedelta(days=7)
    elif period == "30d":
        start = today - timedelta(days=30)
    elif period == "90d":
        start = today - timedelta(days=90)
    else:
        start = today - timedelta(days=7)
    return start, today


@router.get("/overview")
async def get_overview(
    period: str = Query("7d", pattern="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """获取运营概览数据。"""
    start_date, end_date = get_date_range(period)
    prev_start = start_date - (end_date - start_date)
    
    # 当前周期统计
    current_convs = await db.scalar(
        select(func.count(ChatConversation.id)).where(
            and_(
                func.date(ChatConversation.created_at) >= start_date,
                func.date(ChatConversation.created_at) <= end_date,
            )
        )
    ) or 0
    
    current_msgs = await db.scalar(
        select(func.count(ChatMessage.id)).where(
            and_(
                func.date(ChatMessage.created_at) >= start_date,
                func.date(ChatMessage.created_at) <= end_date,
            )
        )
    ) or 0
    
    # 上一周期统计（用于计算变化率）
    prev_convs = await db.scalar(
        select(func.count(ChatConversation.id)).where(
            and_(
                func.date(ChatConversation.created_at) >= prev_start,
                func.date(ChatConversation.created_at) < start_date,
            )
        )
    ) or 0
    
    prev_msgs = await db.scalar(
        select(func.count(ChatMessage.id)).where(
            and_(
                func.date(ChatMessage.created_at) >= prev_start,
                func.date(ChatMessage.created_at) < start_date,
            )
        )
    ) or 0
    
    # 活跃用户数
    active_users = await db.scalar(
        select(func.count(func.distinct(ChatConversation.user_id))).where(
            and_(
                func.date(ChatConversation.created_at) >= start_date,
                func.date(ChatConversation.created_at) <= end_date,
            )
        )
    ) or 0
    
    prev_active_users = await db.scalar(
        select(func.count(func.distinct(ChatConversation.user_id))).where(
            and_(
                func.date(ChatConversation.created_at) >= prev_start,
                func.date(ChatConversation.created_at) < start_date,
            )
        )
    ) or 0
    
    # 反馈统计
    positive_feedback = await db.scalar(
        select(func.count(ChatMessage.id)).where(
            and_(
                func.date(ChatMessage.created_at) >= start_date,
                func.date(ChatMessage.created_at) <= end_date,
                ChatMessage.feedback == "positive",
            )
        )
    ) or 0
    
    negative_feedback = await db.scalar(
        select(func.count(ChatMessage.id)).where(
            and_(
                func.date(ChatMessage.created_at) >= start_date,
                func.date(ChatMessage.created_at) <= end_date,
                ChatMessage.feedback == "negative",
            )
        )
    ) or 0
    
    total_feedback = positive_feedback + negative_feedback
    satisfaction = positive_feedback / total_feedback if total_feedback > 0 else 0.0
    
    def calc_change(current: int, prev: int) -> float:
        if prev == 0:
            return 1.0 if current > 0 else 0.0
        return (current - prev) / prev
    
    return {
        "period": period,
        "conversations": {
            "total": current_convs,
            "change": calc_change(current_convs, prev_convs),
        },
        "messages": {
            "total": current_msgs,
            "change": calc_change(current_msgs, prev_msgs),
        },
        "active_users": {
            "total": active_users,
            "change": calc_change(active_users, prev_active_users),
        },
        "satisfaction": {
            "rate": satisfaction,
            "positive": positive_feedback,
            "negative": negative_feedback,
        },
    }


@router.get("/trends")
async def get_trends(
    metric: Literal["conversations", "messages", "users"] = "conversations",
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """获取趋势数据。"""
    start_date, end_date = get_date_range(period)
    
    if metric == "conversations":
        stmt = (
            select(
                func.date(ChatConversation.created_at).label("date"),
                func.count(ChatConversation.id).label("value"),
            )
            .where(
                and_(
                    func.date(ChatConversation.created_at) >= start_date,
                    func.date(ChatConversation.created_at) <= end_date,
                )
            )
            .group_by(func.date(ChatConversation.created_at))
            .order_by(func.date(ChatConversation.created_at))
        )
    elif metric == "messages":
        stmt = (
            select(
                func.date(ChatMessage.created_at).label("date"),
                func.count(ChatMessage.id).label("value"),
            )
            .where(
                and_(
                    func.date(ChatMessage.created_at) >= start_date,
                    func.date(ChatMessage.created_at) <= end_date,
                )
            )
            .group_by(func.date(ChatMessage.created_at))
            .order_by(func.date(ChatMessage.created_at))
        )
    else:  # users
        stmt = (
            select(
                func.date(ChatConversation.created_at).label("date"),
                func.count(func.distinct(ChatConversation.user_id)).label("value"),
            )
            .where(
                and_(
                    func.date(ChatConversation.created_at) >= start_date,
                    func.date(ChatConversation.created_at) <= end_date,
                )
            )
            .group_by(func.date(ChatConversation.created_at))
            .order_by(func.date(ChatConversation.created_at))
        )
    
    result = await db.execute(stmt)
    data = [
        {"date": str(row.date), "value": row.value}
        for row in result.all()
    ]
    
    return {
        "metric": metric,
        "period": period,
        "data": data,
    }


@router.get("/knowledge-bases")
async def get_knowledge_base_stats(
    sort: Literal["conversations", "satisfaction"] = "conversations",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """获取知识库统计排行。"""
    # 按对话数统计
    stmt = (
        select(
            KnowledgeBase.id,
            KnowledgeBase.name,
            func.count(ChatConversation.id).label("conversation_count"),
        )
        .outerjoin(ChatConversation, ChatConversation.kb_id == KnowledgeBase.id)
        .group_by(KnowledgeBase.id, KnowledgeBase.name)
    )
    
    if sort == "conversations":
        stmt = stmt.order_by(
            desc(func.count(ChatConversation.id)) if order == "desc"
            else func.count(ChatConversation.id)
        )
    
    stmt = stmt.limit(limit)
    
    result = await db.execute(stmt)
    items = [
        {
            "id": row.id,
            "name": row.name,
            "conversation_count": row.conversation_count,
        }
        for row in result.all()
    ]
    
    return {"items": items}


@router.get("/top-questions")
async def get_top_questions(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """获取高频问题。"""
    # 统计用户消息频率
    stmt = (
        select(
            ChatMessage.content,
            func.count(ChatMessage.id).label("count"),
        )
        .where(ChatMessage.role == "user")
        .group_by(ChatMessage.content)
        .order_by(desc(func.count(ChatMessage.id)))
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    items = [
        {"question": row.content[:100], "count": row.count}
        for row in result.all()
    ]
    
    return {"items": items}


@router.get("/low-satisfaction")
async def get_low_satisfaction_messages(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """获取低评分消息。"""
    stmt = (
        select(
            ChatMessage.id,
            ChatMessage.content,
            ChatMessage.feedback,
            ChatMessage.created_at,
            ChatConversation.kb_id,
        )
        .join(ChatConversation, ChatMessage.conversation_id == ChatConversation.id)
        .where(ChatMessage.feedback == "negative")
        .order_by(desc(ChatMessage.created_at))
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    items = [
        {
            "id": row.id,
            "content": row.content[:200],
            "feedback": row.feedback,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "knowledge_base_id": row.kb_id,
        }
        for row in result.all()
    ]

    return {"items": items}


@router.get("/user/usage")
async def get_user_usage(
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """个人用量统计：Token 消耗趋势、KB 使用分布、配额状态。"""
    start_date, _end_date = get_date_range(period)

    from app.models.user_quota import UsageLog
    daily_usage = await db.execute(
        select(
            func.date(UsageLog.created_at).label("dt"),
            func.sum(UsageLog.total_tokens).label("tokens"),
            func.count(UsageLog.id).label("requests"),
        )
        .where(UsageLog.user_id == current_user.id, func.date(UsageLog.created_at) >= start_date)
        .group_by(func.date(UsageLog.created_at))
        .order_by(func.date(UsageLog.created_at))
    )
    trend = [{"date": str(r.dt), "tokens": r.tokens or 0, "requests": r.requests or 0} for r in daily_usage.all()]

    kb_usage = await db.execute(
        select(
            ChatConversation.kb_id,
            KnowledgeBase.name.label("kb_name"),
            func.count(ChatConversation.id).label("conv_count"),
        )
        .join(KnowledgeBase, ChatConversation.kb_id == KnowledgeBase.id)
        .where(ChatConversation.user_id == current_user.id)
        .group_by(ChatConversation.kb_id, KnowledgeBase.name)
        .order_by(desc(func.count(ChatConversation.id)))
        .limit(10)
    )
    kb_breakdown = [{"kb_id": r.kb_id, "kb_name": r.kb_name, "conversations": r.conv_count} for r in kb_usage.all()]

    from app.services.quota_service import get_or_create_quota
    quota = await get_or_create_quota(db, current_user.id)

    return {
        "trend": trend,
        "kb_breakdown": kb_breakdown,
        "quota": {
            "plan": quota.plan,
            "trial_used": quota.trial_used,
            "trial_total": quota.trial_total,
            "token_used": quota.token_used,
            "token_credit": quota.token_credit,
        },
    }
