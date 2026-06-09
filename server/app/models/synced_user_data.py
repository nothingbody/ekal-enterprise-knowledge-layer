"""Models for user data synced from desktop clients."""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, JSON
from sqlalchemy.sql import func

from app.models.base import Base


class SyncedMemory(Base):
    __tablename__ = "synced_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(64), nullable=True, index=True)
    content = Column(Text, nullable=False)
    category = Column(String(32), default="general")
    source = Column(String(100), nullable=True)
    importance = Column(Float, default=1.0)
    memory_type = Column(String(20), default="persistent")
    remote_created_at = Column(DateTime(timezone=True), nullable=True)
    synced_at = Column(DateTime(timezone=True), server_default=func.now())


class SyncedProfile(Base):
    __tablename__ = "synced_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(64), nullable=True, index=True)
    profile_summary = Column(Text, nullable=True)
    topics_of_interest = Column(Text, nullable=True)
    communication_style = Column(String(50), nullable=True)
    expertise_areas = Column(Text, nullable=True)
    synced_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SyncedUserData(Base):
    """Generic key-value store for user data synced from desktop clients."""
    __tablename__ = "synced_user_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    data_type = Column(String(50), nullable=False, index=True)
    data = Column(Text, nullable=True)
    synced_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SyncedAgentConfig(Base):
    __tablename__ = "synced_agent_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(64), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=True)
    kb_ids = Column(Text, nullable=True)
    is_active = Column(Text, nullable=True)
    remote_created_at = Column(DateTime(timezone=True), nullable=True)
    synced_at = Column(DateTime(timezone=True), server_default=func.now())


class SyncedOperationLog(Base):
    __tablename__ = "synced_operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(64), nullable=True, index=True)
    local_id = Column(Integer, nullable=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(Integer, nullable=True)
    detail = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    latency_ms = Column(Float, default=0)
    remote_created_at = Column(DateTime(timezone=True), nullable=True)
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
