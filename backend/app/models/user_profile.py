"""User profile model — auto-built summary of user preferences and behavior."""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    profile_summary = Column(Text, nullable=True)
    topics_of_interest = Column(Text, nullable=True)  # JSON array
    communication_style = Column(String(50), nullable=True)  # formal / casual / technical
    expertise_areas = Column(Text, nullable=True)  # JSON array
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
