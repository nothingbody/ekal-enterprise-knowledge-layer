"""SkillInstall model — tracks which skills a user has installed."""

from __future__ import annotations

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Float, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class SkillInstall(Base):
    """Records a user's installation of a skill."""

    __tablename__ = "skill_installs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    skill_id = Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    config_override = Column(Text, nullable=True)  # JSON — per-user config tweaks

    rating = Column(Float, nullable=True)
    use_count = Column(Integer, default=0, nullable=False)
    last_used_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "skill_id", "workspace_id", name="uq_user_skill_ws"),
    )
