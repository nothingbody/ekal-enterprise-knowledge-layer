from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User
from app.models.usage import UsageReport
from app.schemas import UsageReportCreate, PaginatedResponse, SyncMemoriesRequest, SyncProfileRequest, SyncAgentsRequest, SyncOperationLogsRequest
from app.core.security import get_current_user, get_admin_user

router = APIRouter()


@router.post("/report")
async def submit_usage_report(
    data: UsageReportCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Receive daily usage data from a desktop client."""
    existing = (await db.execute(
        select(UsageReport).where(
            UsageReport.user_id == current_user.id,
            UsageReport.report_date == data.report_date,
            UsageReport.device_id == data.device_id,
        )
    )).scalar_one_or_none()

    if existing:
        existing.token_count = data.token_count
        existing.conversation_count = data.conversation_count
        existing.message_count = data.message_count
        existing.kb_count = data.kb_count
        existing.doc_count = data.doc_count
    else:
        report = UsageReport(
            user_id=current_user.id,
            device_id=data.device_id,
            report_date=data.report_date,
            token_count=data.token_count,
            conversation_count=data.conversation_count,
            message_count=data.message_count,
            kb_count=data.kb_count,
            doc_count=data.doc_count,
        )
        db.add(report)

    await db.commit()
    return {"status": "ok"}


@router.post("/detailed-report")
async def submit_detailed_report(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Receive detailed per-model usage breakdown from a desktop client."""
    data = await request.json()
    device_id = data.get("device_id", "")
    by_model = data.get("by_model", [])

    from app.models.synced_user_data import SyncedUserData
    existing = (await db.execute(
        select(SyncedUserData).where(
            SyncedUserData.user_id == current_user.id,
            SyncedUserData.data_type == "usage_detail",
        )
    )).scalar_one_or_none()

    import json
    payload = json.dumps({"device_id": device_id, "by_model": by_model}, ensure_ascii=False)
    if existing:
        existing.data = payload
    else:
        db.add(SyncedUserData(
            user_id=current_user.id,
            data_type="usage_detail",
            data=payload,
        ))
    await db.commit()
    return {"status": "ok"}


@router.get("/trend")
async def usage_trend(
    days: int = Query(30, ge=0, le=365),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD), used when days=0"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD), used when days=0"),
    user_id: Optional[int] = None,
    org_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Get aggregated usage trend for the admin dashboard."""
    if days == 0 and start_date and end_date:
        try:
            from datetime import datetime as dt
            range_start = dt.strptime(start_date, "%Y-%m-%d").date()
            range_end = dt.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(400, "日期格式无效，请使用 YYYY-MM-DD")
        filters = [UsageReport.report_date >= range_start, UsageReport.report_date <= range_end]
    else:
        if days == 0:
            days = 30
        computed_start = date.today() - timedelta(days=days)
        filters = [UsageReport.report_date >= computed_start]

    if user_id is not None:
        filters.append(UsageReport.user_id == user_id)
    elif org_id is not None:
        filters.append(
            UsageReport.user_id.in_(
                select(User.id).where(User.org_id == org_id)
            )
        )

    result = await db.execute(
        select(
            UsageReport.report_date,
            func.sum(UsageReport.token_count).label("tokens"),
            func.sum(UsageReport.conversation_count).label("conversations"),
            func.sum(UsageReport.message_count).label("messages"),
        )
        .where(*filters)
        .group_by(UsageReport.report_date)
        .order_by(UsageReport.report_date.asc())
    )

    return [
        {
            "date": str(row.report_date),
            "tokens": row.tokens or 0,
            "conversations": row.conversations or 0,
            "messages": row.messages or 0,
        }
        for row in result.all()
    ]


@router.post("/sync-memories")
async def sync_memories(
    data: SyncMemoriesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Receive synced user memories from a desktop client."""
    from app.models.synced_user_data import SyncedMemory

    # Delete old synced memories for this device, then insert fresh
    from sqlalchemy import delete as sa_delete
    await db.execute(
        sa_delete(SyncedMemory).where(
            SyncedMemory.user_id == current_user.id,
            SyncedMemory.device_id == data.device_id,
        )
    )

    for m in data.memories:
        db.add(SyncedMemory(
            user_id=current_user.id,
            device_id=data.device_id,
            content=m.content,
            category=m.category,
            source=m.source,
            importance=m.importance,
            memory_type=m.memory_type,
            remote_created_at=m.created_at,
        ))
    await db.commit()
    return {"status": "ok", "count": len(data.memories)}


@router.post("/sync-profile")
async def sync_profile(
    data: SyncProfileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Receive synced user profile from a desktop client."""
    from app.models.synced_user_data import SyncedProfile

    existing = (await db.execute(
        select(SyncedProfile).where(
            SyncedProfile.user_id == current_user.id,
            SyncedProfile.device_id == data.device_id,
        )
    )).scalar_one_or_none()

    profile = data.profile
    if existing:
        existing.profile_summary = profile.get("profile_summary")
        existing.topics_of_interest = profile.get("topics_of_interest")
        existing.communication_style = profile.get("communication_style")
        existing.expertise_areas = profile.get("expertise_areas")
    else:
        db.add(SyncedProfile(
            user_id=current_user.id,
            device_id=data.device_id,
            profile_summary=profile.get("profile_summary"),
            topics_of_interest=profile.get("topics_of_interest"),
            communication_style=profile.get("communication_style"),
            expertise_areas=profile.get("expertise_areas"),
        ))
    await db.commit()
    return {"status": "ok"}


@router.post("/sync-agents")
async def sync_agents(
    data: SyncAgentsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Receive synced agent configs from a desktop client."""
    from app.models.synced_user_data import SyncedAgentConfig

    from sqlalchemy import delete as sa_delete
    await db.execute(
        sa_delete(SyncedAgentConfig).where(
            SyncedAgentConfig.user_id == current_user.id,
            SyncedAgentConfig.device_id == data.device_id,
        )
    )

    for a in data.agents:
        db.add(SyncedAgentConfig(
            user_id=current_user.id,
            device_id=data.device_id,
            name=a.name,
            description=a.description,
            system_prompt=a.system_prompt,
            kb_ids=a.kb_ids,
            is_active=str(a.is_active) if a.is_active is not None else None,
            remote_created_at=a.created_at,
        ))
    await db.commit()
    return {"status": "ok", "count": len(data.agents)}


@router.post("/sync-operation-logs")
async def sync_operation_logs(
    data: SyncOperationLogsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Receive operation logs synced from a desktop client."""
    from app.models.synced_user_data import SyncedOperationLog
    from datetime import datetime

    existing_local_ids = set()
    if data.logs:
        local_ids = [log.local_id for log in data.logs if log.local_id is not None]
        if local_ids:
            result = await db.execute(
                select(SyncedOperationLog.local_id).where(
                    SyncedOperationLog.user_id == current_user.id,
                    SyncedOperationLog.device_id == data.device_id,
                    SyncedOperationLog.local_id.in_(local_ids),
                )
            )
            existing_local_ids = {r[0] for r in result.all()}

    inserted = 0
    for log in data.logs:
        if log.local_id in existing_local_ids:
            continue
        remote_created = None
        if log.created_at:
            try:
                remote_created = datetime.fromisoformat(log.created_at)
            except ValueError:
                pass
        db.add(SyncedOperationLog(
            user_id=current_user.id,
            device_id=data.device_id,
            local_id=log.local_id,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            detail=log.detail,
            ip_address=log.ip_address,
            prompt_tokens=log.prompt_tokens,
            completion_tokens=log.completion_tokens,
            total_tokens=log.total_tokens,
            latency_ms=log.latency_ms,
            remote_created_at=remote_created,
        ))
        inserted += 1

    await db.commit()
    return {"status": "ok", "inserted": inserted}


@router.get("/summary")
async def usage_summary(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    today = date.today()
    total_tokens = (await db.execute(
        select(func.sum(UsageReport.token_count))
    )).scalar() or 0
    today_tokens = (await db.execute(
        select(func.sum(UsageReport.token_count)).where(UsageReport.report_date == today)
    )).scalar() or 0
    total_conversations = (await db.execute(
        select(func.sum(UsageReport.conversation_count))
    )).scalar() or 0

    return {
        "total_tokens": total_tokens,
        "today_tokens": today_tokens,
        "total_conversations": total_conversations,
    }
