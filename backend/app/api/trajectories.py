"""REST API for RAG decision trajectory analysis."""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.core.security import get_current_user
from app.schemas.trajectory import (
    TrajectoryListItem,
    TrajectoryDetail,
    TrajectoryStepResponse,
    TrajectoryAnalyticsSummary,
    TrajectoryPattern,
)

router = APIRouter()


@router.get("")
async def list_trajectories(
    kb_id: int = Query(None),
    conversation_id: int = Query(None),
    outcome: str = Query(None),
    min_reward: float = Query(None, ge=0, le=1),
    max_reward: float = Query(None, ge=0, le=1),
    user_feedback: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List trajectories with filtering and pagination."""
    from app.services.trajectory_service import list_trajectories as _list

    items, total = await _list(
        db, kb_id=kb_id, conversation_id=conversation_id,
        outcome=outcome, min_reward=min_reward, max_reward=max_reward,
        user_feedback=user_feedback, page=page, page_size=page_size,
    )

    return {
        "items": [TrajectoryListItem.model_validate(t) for t in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/analytics/summary")
async def trajectory_analytics_summary(
    kb_id: int = Query(None),
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate trajectory analytics: outcome distribution, avg steps, duration."""
    from app.services.trajectory_service import compute_summary

    period_days = {"7d": 7, "30d": 30, "90d": 90}[period]
    summary = await compute_summary(db, kb_id=kb_id, period_days=period_days)
    return TrajectoryAnalyticsSummary(**summary)


@router.get("/analytics/patterns")
async def trajectory_pattern_analysis(
    kb_id: int = Query(...),
    min_count: int = Query(5, ge=2),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Identify recurring trajectory patterns and their success rates."""
    from app.services.trajectory_service import extract_patterns

    patterns = await extract_patterns(db, kb_id=kb_id, min_count=min_count)
    return [TrajectoryPattern(**p) for p in patterns]


@router.get("/analytics/decision-tree")
async def trajectory_decision_tree(
    kb_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Build a decision tree from trajectory data showing branching probabilities."""
    from app.services.trajectory_service import build_decision_tree

    tree = await build_decision_tree(db, kb_id=kb_id)
    return tree


@router.get("/{trajectory_id}")
async def get_trajectory(
    trajectory_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full trajectory detail including all steps."""
    from app.services.trajectory_service import get_trajectory_detail

    traj = await get_trajectory_detail(db, trajectory_id)
    if not traj:
        raise HTTPException(404, "轨迹不存在")

    # Parse steps and config
    try:
        steps_data = json.loads(traj.steps_json)
        steps = [TrajectoryStepResponse(**s) for s in steps_data]
    except (json.JSONDecodeError, TypeError):
        steps = []

    try:
        config = json.loads(traj.config_snapshot) if traj.config_snapshot else None
    except (json.JSONDecodeError, TypeError):
        config = None

    detail = TrajectoryDetail.model_validate(traj)
    detail.steps = steps
    detail.config_snapshot = config
    return detail
