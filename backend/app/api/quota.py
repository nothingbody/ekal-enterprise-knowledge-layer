import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.core.security import get_current_user, get_admin_user
from app.services.quota_service import (
    check_quota, add_token_credit, set_plan, reset_trial,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/me")
async def get_my_quota(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await check_quota(db, current_user.id)
    logger.debug("用户 %d 配额: plan=%s", current_user.id, result.get("plan"))
    return result


@router.post("/admin/add-credit")
async def admin_add_credit(
    user_id: int,
    amount: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    quota = await add_token_credit(db, user_id, amount)
    return {
        "message": f"已为用户 {user_id} 添加 {amount} 算力额度",
        "plan": quota.plan,
        "token_credit": quota.token_credit,
    }


@router.post("/admin/set-plan")
async def admin_set_plan(
    user_id: int,
    plan: str,
    token_credit: int = 0,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    quota = await set_plan(db, user_id, plan, token_credit)
    return {
        "message": f"已将用户 {user_id} 设置为 {plan} 方案",
        "plan": quota.plan,
        "token_credit": quota.token_credit,
    }


@router.post("/admin/reset-trial")
async def admin_reset_trial(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    quota = await reset_trial(db, user_id)
    return {
        "message": f"已重置用户 {user_id} 的试用额度",
        "trial_total": quota.trial_total,
        "trial_used": quota.trial_used,
    }
