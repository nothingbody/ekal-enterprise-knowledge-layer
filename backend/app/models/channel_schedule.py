"""ChannelSchedule — cron-based proactive push task bound to a channel.

Inspired by OpenClaw's automation/cron: scheduled jobs run in their own
isolated session (cron:<schedule_id>), completely separate from user
conversation history, so they never pollute user context.
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.sql import func

from app.database import Base


class ChannelSchedule(Base):
    __tablename__ = "channel_schedules"

    id = Column(Integer, primary_key=True, index=True)

    # Parent channel (cascades on channel deletion)
    channel_id = Column(
        Integer,
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Cron expression (e.g. "0 9 * * 1-5" = weekdays at 09:00)
    cron_expr = Column(String(64), nullable=False)

    # Prompt to send to the AI (may include {date}, {time} placeholders)
    prompt = Column(Text, nullable=False)

    # Platform-specific recipient identifier.
    # If None the task logs the result but does not send it anywhere.
    target_sender_id = Column(String(256), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)

    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
