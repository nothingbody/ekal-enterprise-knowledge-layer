"""Trajectory-aware RAG: Decision trajectory data model and recorder.

Models each RAG query as a decision trajectory τ = (s₀,a₀,r₀, s₁,a₁,r₁, ..., sₙ),
capturing the full sequence of decisions made by the agentic RAG orchestrator.

The TrajectoryRecorder is a lightweight builder that accumulates steps during
orchestrator execution. All operations are in-memory dict/list appends with
no I/O, so overhead is well under 1ms even for complex trajectories.
"""
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class TrajectoryStep:
    """One step (sᵢ, aᵢ, rᵢ) in the decision trajectory."""
    step_index: int
    stage: str          # "init"|"adaptive_check"|"complexity"|"retrieval"|"evaluation"|"corrective"|"refinement"|"policy_hint"|"final"
    action: str         # "skip_retrieval"|"proceed"|"classify_complexity"|"retrieve"|"filter_irrelevant"|"requery"|"web_fallback"|"broaden"|"refine_answer"|"policy_hint"
    parameters: Dict[str, Any]
    duration_ms: float
    reward: Optional[float] = None
    reward_source: Optional[str] = None   # "retrieval_score"|"eval_confidence"|"refinement_score"|"bypass_confidence"
    state_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "step_index": self.step_index,
            "stage": self.stage,
            "action": self.action,
            "parameters": self.parameters,
            "duration_ms": round(self.duration_ms, 1),
            "reward": round(self.reward, 4) if self.reward is not None else None,
            "reward_source": self.reward_source,
            "state_snapshot": self.state_snapshot,
        }


@dataclass
class Trajectory:
    """Complete decision trajectory for one RAG query."""
    trajectory_id: str
    conversation_id: Optional[int]
    message_id: Optional[int]
    kb_id: int
    user_id: Optional[int]
    original_query: str
    steps: List[TrajectoryStep]
    outcome: str            # "success"|"partial"|"failure"|"skipped"
    total_duration_ms: float
    config_snapshot: Dict[str, Any]
    created_at: datetime

    def to_steps_list(self) -> list:
        """Serialize steps to a list of dicts for JSON storage."""
        return [s.to_dict() for s in self.steps]

    def aggregate_reward(self) -> Optional[float]:
        """Compute aggregated reward from all steps.

        Uses weighted average: later steps carry more weight since they
        reflect the final quality of the pipeline output.
        """
        rewards = [(s.reward, s.step_index) for s in self.steps if s.reward is not None]
        if not rewards:
            return None
        total_weight = 0.0
        weighted_sum = 0.0
        for reward, idx in rewards:
            weight = 1.0 + idx * 0.5  # later steps weighted higher
            weighted_sum += reward * weight
            total_weight += weight
        return round(weighted_sum / total_weight, 4) if total_weight > 0 else None

    def action_sequence_fingerprint(self) -> str:
        """Create a hashable fingerprint from the ordered action types."""
        return "|".join(s.action for s in self.steps if s.stage != "init")


class TrajectoryRecorder:
    """Lightweight builder that accumulates trajectory steps during orchestrator execution.

    Usage:
        recorder = TrajectoryRecorder(query, kb_id, user_id, config)
        recorder.add_step("adaptive_check", "proceed", {"confidence": 0.9}, 1.2)
        recorder.add_step("retrieval", "retrieve", {"count": 5, "top_score": 0.85}, 120.0,
                          reward=0.85, reward_source="retrieval_score")
        trajectory = recorder.finalize("success")
    """

    def __init__(
        self,
        query: str,
        kb_id: int,
        user_id: Optional[int],
        config_snapshot: dict,
    ):
        self._trajectory_id = uuid.uuid4().hex
        self._query = query
        self._kb_id = kb_id
        self._user_id = user_id
        self._config_snapshot = config_snapshot
        self._steps: List[TrajectoryStep] = []
        self._start_time = time.monotonic()
        self._created_at = datetime.now(timezone.utc)

    def add_step(
        self,
        stage: str,
        action: str,
        parameters: dict,
        duration_ms: float,
        reward: Optional[float] = None,
        reward_source: Optional[str] = None,
        state_snapshot: Optional[dict] = None,
    ) -> None:
        """Record one decision step."""
        self._steps.append(TrajectoryStep(
            step_index=len(self._steps),
            stage=stage,
            action=action,
            parameters=parameters,
            duration_ms=duration_ms,
            reward=reward,
            reward_source=reward_source,
            state_snapshot=state_snapshot or {},
        ))

    def finalize(self, outcome: str) -> Trajectory:
        """Complete the trajectory and return immutable result."""
        total_ms = (time.monotonic() - self._start_time) * 1000
        return Trajectory(
            trajectory_id=self._trajectory_id,
            conversation_id=None,  # set later when message is saved
            message_id=None,       # set later when message is saved
            kb_id=self._kb_id,
            user_id=self._user_id,
            original_query=self._query,
            steps=list(self._steps),
            outcome=outcome,
            total_duration_ms=round(total_ms, 1),
            config_snapshot=self._config_snapshot,
            created_at=self._created_at,
        )
