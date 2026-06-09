"""Automation task and execution log models."""

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Float,
    DateTime, ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class AutomationTask(Base):
    __tablename__ = "automation_tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    task_type = Column(String(30), nullable=False)  # "scheduled" | "webhook" | "event"

    # Scheduled tasks
    cron_expression = Column(String(100), nullable=True)
    interval_minutes = Column(Integer, nullable=True)

    # Webhook tasks
    webhook_token = Column(String(64), nullable=True, unique=True)

    # Event tasks
    event_trigger = Column(String(100), nullable=True)

    # JSON config: {"action": "...", "params": {...}}
    config = Column(Text, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String(20), nullable=True)
    last_error = Column(Text, nullable=True)
    run_count = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    logs = relationship("AutomationLog", back_populates="task", cascade="all, delete-orphan", passive_deletes=True)


class AutomationLog(Base):
    __tablename__ = "automation_logs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("automation_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), nullable=False)
    output = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Float, nullable=True)
    triggered_by = Column(String(30), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("AutomationTask", back_populates="logs")
