"""SQLAlchemy model for RAG decision trajectory persistence."""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class RAGTrajectory(Base):
    """Stores one complete decision trajectory for a RAG query.

    Steps are serialized as a JSON array in steps_json rather than a
    separate table because:
    - Trajectories are always read/written atomically
    - Step count is bounded (≤10 per trajectory)
    - Avoids JOIN overhead
    - Matches existing JSON blob patterns (references, agentic_rag_config)
    """
    __tablename__ = "rag_trajectories"

    id = Column(Integer, primary_key=True, index=True)
    trajectory_id = Column(String(64), unique=True, nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    original_query = Column(Text, nullable=False)
    outcome = Column(String(20), nullable=False)          # "success"|"partial"|"failure"|"skipped"
    step_count = Column(Integer, default=0, nullable=False)
    total_duration_ms = Column(Float, nullable=False)
    config_snapshot = Column(Text, nullable=True)          # JSON blob of AgenticRAGConfig
    steps_json = Column(Text, nullable=False)              # JSON array of TrajectoryStep dicts
    reward_score = Column(Float, nullable=True)            # Aggregated reward for quick queries
    user_feedback = Column(String(20), nullable=True)      # Denormalized from ChatMessage.feedback
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_traj_kb_created", "kb_id", "created_at"),
        Index("ix_traj_outcome", "outcome"),
    )
