"""User memory model — stores extracted long-term memories per user."""

from sqlalchemy import Column, Integer, Float, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func

from app.database import Base


class UserMemory(Base):
    __tablename__ = "user_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    category = Column(String(32), default="general")  # general | preference | fact | insight
    source = Column(String(100), nullable=True)  # e.g. "conversation:123" or "manual"
    embedding = Column(JSON, nullable=True)  # stored as list[float]

    importance = Column(Float, default=1.0, nullable=False)
    access_count = Column(Integer, default=0, nullable=False)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    memory_type = Column(String(20), default="persistent")  # persistent | temporary | auto

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
