"""Pydantic schemas for trajectory API responses."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TrajectoryStepResponse(BaseModel):
    step_index: int
    stage: str
    action: str
    parameters: Dict[str, Any]
    duration_ms: float
    reward: Optional[float] = None
    reward_source: Optional[str] = None
    state_snapshot: Dict[str, Any] = {}


class TrajectoryListItem(BaseModel):
    trajectory_id: str
    conversation_id: Optional[int] = None
    message_id: Optional[int] = None
    kb_id: int
    original_query: str
    outcome: str
    step_count: int
    total_duration_ms: float
    reward_score: Optional[float] = None
    user_feedback: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TrajectoryDetail(TrajectoryListItem):
    config_snapshot: Optional[Dict[str, Any]] = None
    steps: List[TrajectoryStepResponse] = []


class TrajectoryAnalyticsSummary(BaseModel):
    total_count: int
    outcome_distribution: Dict[str, float]
    avg_steps: float
    avg_duration_ms: float
    avg_reward: Optional[float] = None
    action_frequency: Dict[str, int]
    feedback_rate: float  # fraction of trajectories with user feedback


class TrajectoryPattern(BaseModel):
    fingerprint: str
    action_sequence: List[str]
    count: int
    avg_reward: Optional[float] = None
    avg_duration_ms: float
    success_rate: float


class DecisionTreeNode(BaseModel):
    stage: str
    action: str
    count: int
    avg_reward: Optional[float] = None
    probability: float
    children: List["DecisionTreeNode"] = []
