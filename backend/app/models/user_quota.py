from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, BigInteger, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class UserQuota(Base):
    """User quota tracking — free trial (conversation count) and paid (token credit)."""
    __tablename__ = "user_quotas"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    plan = Column(String(30), default="trial", nullable=False, server_default="trial")

    trial_total = Column(Integer, default=50, nullable=False, server_default="50")
    trial_used = Column(Integer, default=0, nullable=False, server_default="0")

    token_credit = Column(BigInteger, default=0, nullable=False, server_default="0")
    token_used = Column(BigInteger, default=0, nullable=False, server_default="0")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id])


class UsageLog(Base):
    """Per-conversation usage record for billing and analytics."""
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Integer, nullable=True)
    model_name = Column(String(200), nullable=True)

    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
