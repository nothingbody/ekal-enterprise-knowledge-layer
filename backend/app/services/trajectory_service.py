"""Trajectory analytics service.

Provides querying, aggregation, pattern extraction, and decision tree
construction from persisted RAG decision trajectories.
"""
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trajectory import RAGTrajectory

logger = logging.getLogger(__name__)


async def list_trajectories(
    db: AsyncSession,
    kb_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
    outcome: Optional[str] = None,
    min_reward: Optional[float] = None,
    max_reward: Optional[float] = None,
    user_feedback: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[RAGTrajectory], int]:
    """List trajectories with filtering and pagination."""
    query = select(RAGTrajectory)
    count_query = select(func.count(RAGTrajectory.id))

    conditions = []
    if kb_id is not None:
        conditions.append(RAGTrajectory.kb_id == kb_id)
    if conversation_id is not None:
        conditions.append(RAGTrajectory.conversation_id == conversation_id)
    if outcome:
        conditions.append(RAGTrajectory.outcome == outcome)
    if min_reward is not None:
        conditions.append(RAGTrajectory.reward_score >= min_reward)
    if max_reward is not None:
        conditions.append(RAGTrajectory.reward_score <= max_reward)
    if user_feedback:
        conditions.append(RAGTrajectory.user_feedback == user_feedback)

    for cond in conditions:
        query = query.where(cond)
        count_query = count_query.where(cond)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(RAGTrajectory.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def get_trajectory_detail(
    db: AsyncSession,
    trajectory_id: str,
) -> Optional[RAGTrajectory]:
    """Get a single trajectory by ID."""
    result = await db.execute(
        select(RAGTrajectory).where(RAGTrajectory.trajectory_id == trajectory_id)
    )
    return result.scalar_one_or_none()


async def compute_summary(
    db: AsyncSession,
    kb_id: Optional[int] = None,
    period_days: int = 30,
) -> Dict[str, Any]:
    """Compute aggregate trajectory analytics."""
    since = datetime.now(timezone.utc) - timedelta(days=period_days)

    query = select(RAGTrajectory).where(RAGTrajectory.created_at >= since)
    if kb_id is not None:
        query = query.where(RAGTrajectory.kb_id == kb_id)

    result = await db.execute(query)
    trajectories = list(result.scalars().all())

    if not trajectories:
        return {
            "total_count": 0,
            "outcome_distribution": {},
            "avg_steps": 0,
            "avg_duration_ms": 0,
            "avg_reward": None,
            "action_frequency": {},
            "feedback_rate": 0,
        }

    total = len(trajectories)

    # Outcome distribution
    outcome_counts = Counter(t.outcome for t in trajectories)
    outcome_dist = {k: round(v / total, 4) for k, v in outcome_counts.items()}

    # Averages
    avg_steps = sum(t.step_count for t in trajectories) / total
    avg_duration = sum(t.total_duration_ms for t in trajectories) / total

    # Reward
    rewards = [t.reward_score for t in trajectories if t.reward_score is not None]
    avg_reward = round(sum(rewards) / len(rewards), 4) if rewards else None

    # Action frequency
    action_freq: Counter = Counter()
    for t in trajectories:
        try:
            steps = json.loads(t.steps_json)
            for step in steps:
                action_freq[step.get("action", "unknown")] += 1
        except (json.JSONDecodeError, TypeError):
            pass

    # Feedback rate
    feedback_count = sum(1 for t in trajectories if t.user_feedback)

    return {
        "total_count": total,
        "outcome_distribution": outcome_dist,
        "avg_steps": round(avg_steps, 2),
        "avg_duration_ms": round(avg_duration, 1),
        "avg_reward": avg_reward,
        "action_frequency": dict(action_freq.most_common()),
        "feedback_rate": round(feedback_count / total, 4),
    }


def _action_fingerprint(steps_json: str) -> Tuple[str, List[str]]:
    """Extract action sequence fingerprint from steps JSON."""
    try:
        steps = json.loads(steps_json)
        actions = [s.get("action", "?") for s in steps if s.get("stage") != "init"]
        return "|".join(actions), actions
    except (json.JSONDecodeError, TypeError):
        return "", []


async def extract_patterns(
    db: AsyncSession,
    kb_id: int,
    min_count: int = 5,
) -> List[Dict[str, Any]]:
    """Group trajectories by action sequence fingerprint and compute success rates."""
    result = await db.execute(
        select(RAGTrajectory).where(RAGTrajectory.kb_id == kb_id)
    )
    trajectories = list(result.scalars().all())

    groups: Dict[str, List[RAGTrajectory]] = defaultdict(list)
    fingerprint_actions: Dict[str, List[str]] = {}

    for t in trajectories:
        fp, actions = _action_fingerprint(t.steps_json)
        if fp:
            groups[fp].append(t)
            fingerprint_actions[fp] = actions

    patterns = []
    for fp, group in groups.items():
        if len(group) < min_count:
            continue
        rewards = [t.reward_score for t in group if t.reward_score is not None]
        successes = sum(1 for t in group if t.outcome == "success")
        patterns.append({
            "fingerprint": fp,
            "action_sequence": fingerprint_actions.get(fp, []),
            "count": len(group),
            "avg_reward": round(sum(rewards) / len(rewards), 4) if rewards else None,
            "avg_duration_ms": round(sum(t.total_duration_ms for t in group) / len(group), 1),
            "success_rate": round(successes / len(group), 4),
        })

    patterns.sort(key=lambda p: p["count"], reverse=True)
    return patterns


async def build_decision_tree(
    db: AsyncSession,
    kb_id: int,
) -> Dict[str, Any]:
    """Build a decision tree showing branching probabilities at each stage.

    Returns a nested structure where each node has:
    - stage, action, count, avg_reward, probability, children
    """
    result = await db.execute(
        select(RAGTrajectory).where(RAGTrajectory.kb_id == kb_id)
    )
    trajectories = list(result.scalars().all())

    if not trajectories:
        return {"stage": "root", "action": "start", "count": 0, "probability": 1.0, "children": []}

    # Parse all step sequences
    all_sequences = []
    for t in trajectories:
        try:
            steps = json.loads(t.steps_json)
            seq = [(s.get("stage", "?"), s.get("action", "?")) for s in steps if s.get("stage") != "init"]
            all_sequences.append((seq, t.reward_score))
        except (json.JSONDecodeError, TypeError):
            pass

    return _build_tree_recursive(all_sequences, 0, len(all_sequences))


def _build_tree_recursive(
    sequences: List[Tuple[List[tuple], Optional[float]]],
    depth: int,
    parent_count: int,
) -> Dict[str, Any]:
    """Recursively build tree nodes."""
    if not sequences or depth >= 10:  # safety limit
        return None

    # Group by (stage, action) at current depth
    groups: Dict[tuple, List[Tuple[List[tuple], Optional[float]]]] = defaultdict(list)
    for seq, reward in sequences:
        if depth < len(seq):
            key = seq[depth]
            groups[key].append((seq, reward))

    if not groups:
        return None

    children = []
    for (stage, action), group in sorted(groups.items(), key=lambda x: -len(x[1])):
        rewards = [r for _, r in group if r is not None]
        avg_r = round(sum(rewards) / len(rewards), 4) if rewards else None

        child_node = {
            "stage": stage,
            "action": action,
            "count": len(group),
            "avg_reward": avg_r,
            "probability": round(len(group) / parent_count, 4) if parent_count > 0 else 0,
            "children": [],
        }

        # Recurse for children
        sub_tree = _build_tree_recursive(group, depth + 1, len(group))
        if sub_tree and sub_tree.get("children"):
            child_node["children"] = sub_tree["children"]
        elif sub_tree and sub_tree.get("stage"):
            child_node["children"] = [sub_tree]

        children.append(child_node)

    return {
        "stage": "root" if depth == 0 else children[0]["stage"] if len(children) == 1 else "branch",
        "action": "start" if depth == 0 else "branch",
        "count": parent_count,
        "probability": 1.0,
        "children": children,
    }
