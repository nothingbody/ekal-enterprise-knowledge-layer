import enum

from sqlalchemy import Column, Integer, String, DateTime, Text, Enum as SAEnum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class SkillStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    UNLISTED = "unlisted"


class ReviewStatus(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class MarketSkill(Base):
    __tablename__ = "market_skills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True, index=True)
    skill_type = Column(String(50), default="prompt")
    version = Column(String(20), default="1.0.0")
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(SAEnum(SkillStatus), default=SkillStatus.PENDING, nullable=False, index=True)
    config = Column(Text, nullable=True)
    icon_url = Column(String(500), nullable=True)
    download_count = Column(Integer, default=0)
    is_featured = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    author = relationship("User", back_populates="published_skills", foreign_keys=[author_id])
    reviews = relationship("SkillReview", back_populates="skill", cascade="all, delete-orphan")


class SkillReview(Base):
    __tablename__ = "skill_reviews"

    id = Column(Integer, primary_key=True, index=True)
    skill_id = Column(Integer, ForeignKey("market_skills.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(SAEnum(ReviewStatus), nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    skill = relationship("MarketSkill", back_populates="reviews")
    reviewer = relationship("User")
