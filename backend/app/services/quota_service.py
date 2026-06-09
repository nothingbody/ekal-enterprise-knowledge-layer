"""User quota management — trial (conversation count) and paid (token credit)."""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.user_quota import UserQuota, UsageLog

logger = logging.getLogger(__name__)

TRIAL_CONVERSATIONS = 50


async def get_or_create_quota(db: AsyncSession, user_id: int) -> UserQuota:
    result = await db.execute(
        select(UserQuota).where(UserQuota.user_id == user_id)
    )
    quota = result.scalar_one_or_none()
    if quota:
        return quota

    quota = UserQuota(
        user_id=user_id,
        plan="trial",
        trial_total=TRIAL_CONVERSATIONS,
        trial_used=0,
        token_credit=0,
        token_used=0,
    )
    db.add(quota)
    await db.commit()
    await db.refresh(quota)
    return quota


async def check_quota(db: AsyncSession, user_id: int) -> dict:
    """Check if user has remaining quota. Returns status dict."""
    quota = await get_or_create_quota(db, user_id)

    if quota.plan == "trial":
        remaining = max(0, quota.trial_total - quota.trial_used)
        return {
            "allowed": remaining > 0,
            "plan": "trial",
            "trial_total": quota.trial_total,
            "trial_used": quota.trial_used,
            "trial_remaining": remaining,
            "token_credit": 0,
            "token_used": 0,
            "token_remaining": 0,
        }
    else:
        remaining = max(0, quota.token_credit - quota.token_used)
        return {
            "allowed": remaining > 0,
            "plan": quota.plan,
            "trial_total": quota.trial_total,
            "trial_used": quota.trial_used,
            "trial_remaining": 0,
            "token_credit": quota.token_credit,
            "token_used": quota.token_used,
            "token_remaining": remaining,
        }


async def consume_trial(db: AsyncSession, user_id: int) -> bool:
    """Atomically consume one trial conversation. Returns False if quota exhausted."""
    # Ensure quota record exists
    await get_or_create_quota(db, user_id)

    # Atomic increment with WHERE guard — prevents concurrent over-consumption
    result = await db.execute(
        update(UserQuota)
        .where(
            UserQuota.user_id == user_id,
            UserQuota.plan == "trial",
            UserQuota.trial_used < UserQuota.trial_total,
        )
        .values(trial_used=UserQuota.trial_used + 1)
    )
    await db.commit()
    if result.rowcount == 0:
        # Either not trial plan (allowed) or quota exhausted
        quota = await get_or_create_quota(db, user_id)
        return quota.plan != "trial"
    return True


async def consume_tokens(
    db: AsyncSession, user_id: int,
    input_tokens: int, output_tokens: int,
    conversation_id: int | None = None,
    model_name: str | None = None,
) -> bool:
    """Atomically consume tokens. Returns False if insufficient credit."""
    await get_or_create_quota(db, user_id)
    total = input_tokens + output_tokens

    # Atomic increment with WHERE guard for paid plans
    result = await db.execute(
        update(UserQuota)
        .where(
            UserQuota.user_id == user_id,
            UserQuota.plan != "trial",
            UserQuota.token_used + total <= UserQuota.token_credit,
        )
        .values(token_used=UserQuota.token_used + total)
    )
    # For trial users, rowcount=0 is OK (no token tracking needed)
    if result.rowcount == 0:
        quota = await get_or_create_quota(db, user_id)
        if quota.plan != "trial" and quota.token_used + total > quota.token_credit:
            return False

    log = UsageLog(
        user_id=user_id,
        conversation_id=conversation_id,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total,
    )
    db.add(log)
    await db.commit()
    return True


async def add_token_credit(db: AsyncSession, user_id: int, amount: int) -> UserQuota:
    quota = await get_or_create_quota(db, user_id)
    quota.token_credit += amount
    if quota.plan == "trial" and amount > 0:
        quota.plan = "basic"
    await db.commit()
    await db.refresh(quota)
    return quota


async def set_plan(db: AsyncSession, user_id: int, plan: str, token_credit: int = 0) -> UserQuota:
    quota = await get_or_create_quota(db, user_id)
    quota.plan = plan
    if token_credit > 0:
        quota.token_credit = token_credit
    await db.commit()
    await db.refresh(quota)
    return quota


async def reset_trial(db: AsyncSession, user_id: int) -> UserQuota:
    quota = await get_or_create_quota(db, user_id)
    quota.plan = "trial"
    quota.trial_used = 0
    quota.trial_total = TRIAL_CONVERSATIONS
    await db.commit()
    await db.refresh(quota)
    return quota
