"""Trajectory-guided policy engine.

Uses historical trajectory data to provide advisory hints for future
RAG pipeline decisions. The policy is always advisory-only — it
suggests but never forces configuration overrides.

Three-tier approach:
1. Rule-based (default): precomputed statistics from trajectory DB
2. Statistical: pattern matching with success-rate weighting (future)
3. LLM-based: use trajectory context in LLM prompts (future)
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trajectory import RAGTrajectory

logger = logging.getLogger(__name__)

# Cache TTL in seconds
_CACHE_TTL = 300.0  # 5 minutes


@dataclass
class PolicyCache:
    """Precomputed statistics from recent trajectories for a KB."""
    kb_id: int
    computed_at: float                        # monotonic timestamp
    sample_count: int
    skip_success_rate: float                  # success rate when retrieval was skipped
    skip_total: int
    complexity_outcome_map: Dict[str, Dict[str, int]]  # {complexity -> {outcome -> count}}
    action_success_rates: Dict[str, float]    # {action_type -> success rate}
    optimal_top_k_by_complexity: Dict[str, int]  # {complexity -> recommended top_k}
    avg_reward_by_outcome: Dict[str, float]   # {outcome -> avg_reward}


# Module-level cache: {kb_id -> PolicyCache}
_policy_cache: Dict[int, PolicyCache] = {}


class TrajectoryPolicy:
    """Advisory policy engine that suggests pipeline adjustments based on history."""

    MIN_SAMPLES = 20  # minimum trajectories to make suggestions

    async def suggest_pipeline_override(
        self,
        db: AsyncSession,
        query: str,
        kb_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Analyze historical trajectories for this KB and suggest config overrides.

        Returns None if no suggestion (insufficient data or no improvement needed),
        or a dict of advisory hints.
        """
        cache = await self._get_or_refresh_cache(db, kb_id)
        if not cache or cache.sample_count < self.MIN_SAMPLES:
            return None

        hints: Dict[str, Any] = {}

        # Hint 1: If skip_retrieval has poor success rate, warn
        if cache.skip_total >= 5 and cache.skip_success_rate < 0.3:
            hints["adaptive_retrieval_warning"] = (
                f"跳过检索的成功率仅 {cache.skip_success_rate:.0%} "
                f"(共 {cache.skip_total} 次)，建议检查 adaptive_retrieval 配置"
            )

        # Hint 2: If requery action consistently improves, suggest lower threshold
        requery_rate = cache.action_success_rates.get("requery", 0)
        if requery_rate > 0.7:
            hints["lower_relevance_threshold"] = True
            hints["relevance_threshold_reason"] = (
                f"重查询动作成功率 {requery_rate:.0%}，建议降低 relevance_threshold 以更早触发"
            )

        # Hint 3: If filter_irrelevant is very common, retrieval quality may be poor
        filter_rate = cache.action_success_rates.get("filter_irrelevant", 0)
        if filter_rate > 0.5:
            hints["high_filter_rate_warning"] = (
                f"过滤不相关结果的频率高达 {filter_rate:.0%}，"
                "建议检查 embedding 质量或增大 fetch_k_multiplier"
            )

        return hints if hints else None

    async def get_complexity_hint(
        self,
        db: AsyncSession,
        kb_id: int,
        complexity: str,
    ) -> Optional[Dict[str, Any]]:
        """Suggest optimal parameters for a given complexity level."""
        cache = await self._get_or_refresh_cache(db, kb_id)
        if not cache or cache.sample_count < self.MIN_SAMPLES:
            return None

        outcome_counts = cache.complexity_outcome_map.get(complexity, {})
        if not outcome_counts:
            return None

        total = sum(outcome_counts.values())
        if total < 5:
            return None

        success_rate = outcome_counts.get("success", 0) / total
        top_k = cache.optimal_top_k_by_complexity.get(complexity)

        if top_k and success_rate < 0.6:
            return {"suggested_top_k": top_k}

        return None

    async def _get_or_refresh_cache(
        self, db: AsyncSession, kb_id: int
    ) -> Optional[PolicyCache]:
        """Get cached policy data, refreshing if expired."""
        cached = _policy_cache.get(kb_id)
        if cached and (time.monotonic() - cached.computed_at) < _CACHE_TTL:
            return cached

        try:
            cache = await _compute_policy_cache(db, kb_id)
            if cache:
                _policy_cache[kb_id] = cache
            return cache
        except Exception as e:
            logger.warning("Policy cache refresh failed for kb_id=%s: %s", kb_id, e)
            return cached  # return stale cache if available


async def _compute_policy_cache(
    db: AsyncSession,
    kb_id: int,
) -> Optional[PolicyCache]:
    """Compute policy statistics from recent trajectories."""
    result = await db.execute(
        select(RAGTrajectory)
        .where(RAGTrajectory.kb_id == kb_id)
        .order_by(RAGTrajectory.created_at.desc())
        .limit(500)  # last 500 trajectories
    )
    trajectories = list(result.scalars().all())

    if not trajectories:
        return None

    # Parse all trajectories
    skip_success = 0
    skip_total = 0
    complexity_outcomes: Dict[str, Dict[str, int]] = {}
    action_success: Dict[str, List[bool]] = {}
    reward_by_outcome: Dict[str, List[float]] = {}

    for t in trajectories:
        # Track outcome rewards
        if t.reward_score is not None:
            reward_by_outcome.setdefault(t.outcome, []).append(t.reward_score)

        try:
            steps = json.loads(t.steps_json)
        except (json.JSONDecodeError, TypeError):
            continue

        is_success = t.outcome == "success"

        for step in steps:
            action = step.get("action", "")
            stage = step.get("stage", "")

            # Track skip retrieval success
            if action == "skip_retrieval":
                skip_total += 1
                # For skipped retrieval, check if user gave positive feedback
                if t.user_feedback == "like" or (t.reward_score and t.reward_score > 0.5):
                    skip_success += 1

            # Track action success rates
            if stage != "init":
                action_success.setdefault(action, []).append(is_success)

            # Track complexity outcomes
            if action == "classify_complexity":
                params = step.get("parameters", {})
                complexity = params.get("complexity", "unknown")
                complexity_outcomes.setdefault(complexity, {})
                complexity_outcomes[complexity][t.outcome] = (
                    complexity_outcomes[complexity].get(t.outcome, 0) + 1
                )

    # Compute action success rates
    action_rates = {}
    for action, successes in action_success.items():
        if len(successes) >= 3:
            action_rates[action] = sum(successes) / len(successes)

    # Compute avg reward by outcome
    avg_reward_by_outcome = {}
    for outcome, rewards in reward_by_outcome.items():
        avg_reward_by_outcome[outcome] = round(sum(rewards) / len(rewards), 4)

    # Compute optimal top_k by complexity (from successful trajectories' parameters)
    optimal_top_k: Dict[str, int] = {}
    for t in trajectories:
        if t.outcome != "success":
            continue
        try:
            steps = json.loads(t.steps_json)
            for step in steps:
                if step.get("action") == "retrieve":
                    params = step.get("parameters", {})
                    top_k = params.get("top_k")
                    if top_k:
                        # Find complexity for this trajectory
                        for s in steps:
                            if s.get("action") == "classify_complexity":
                                c = s.get("parameters", {}).get("complexity", "moderate")
                                optimal_top_k.setdefault(c, [])
                                optimal_top_k[c].append(top_k)
                                break
        except (json.JSONDecodeError, TypeError):
            pass

    # Average the optimal top_k
    final_top_k = {}
    for c, values in optimal_top_k.items():
        if isinstance(values, list) and values:
            final_top_k[c] = round(sum(values) / len(values))

    return PolicyCache(
        kb_id=kb_id,
        computed_at=time.monotonic(),
        sample_count=len(trajectories),
        skip_success_rate=round(skip_success / skip_total, 4) if skip_total > 0 else 0,
        skip_total=skip_total,
        complexity_outcome_map=complexity_outcomes,
        action_success_rates=action_rates,
        optimal_top_k_by_complexity=final_top_k,
        avg_reward_by_outcome=avg_reward_by_outcome,
    )
