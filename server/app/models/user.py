import enum

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum as SAEnum, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    ORG_ADMIN = "org_admin"
    USER = "user"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(200), nullable=False)
    role = Column(SAEnum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    nickname = Column(String(100), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    last_login_ip = Column(String(45), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    plan = Column(String(30), default="trial", nullable=False, server_default="trial")
    trial_total = Column(Integer, default=50, nullable=False, server_default="50")
    trial_used = Column(Integer, default=0, nullable=False, server_default="0")
    token_credit = Column(BigInteger, default=0, nullable=False, server_default="0")
    token_used = Column(BigInteger, default=0, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    organization = relationship("Organization", back_populates="members_rel", foreign_keys=[org_id])
    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")
    usage_reports = relationship("UsageReport", back_populates="user", cascade="all, delete-orphan")
    published_skills = relationship("MarketSkill", back_populates="author", foreign_keys="MarketSkill.author_id")
