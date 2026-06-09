"""ChannelSession — per-(channel, sender) conversation binding.

Inspired by OpenClaw's dmScope: per-channel-peer, this table maps every
(channel_id, sender_id) pair to a single ChatConversation so that
consecutive messages from the same user on the same channel share context.

Lifecycle rules (mirroring OpenClaw session lifecycle):
- A session is "active" while last_active_at is within idle_timeout_minutes.
- On expiry the row is marked is_expired=True; the next message creates a
  fresh conversation and resets the binding.
- Deleting the row is safe — it will be recreated on the next message.
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Boolean, UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class ChannelSession(Base):
    __tablename__ = "channel_sessions"

    id = Column(Integer, primary_key=True, index=True)

    # Which channel this session belongs to
    channel_id = Column(
        Integer,
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Platform-specific sender identifier (e.g. WeChat openid, Telegram user id)
    sender_id = Column(String(256), nullable=False)

    # The active conversation — NULL until the first AI reply creates one
    conversation_id = Column(
        Integer,
        ForeignKey("chat_conversations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamp of the last activity — used for idle-timeout evaluation
    last_active_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Idle timeout in minutes (default 1440 = 24 h).
    # When last_active_at is older than this, the session is considered expired.
    idle_timeout_minutes = Column(Integer, default=1440, nullable=False)

    # Soft-expire flag: set to True when an expired session is detected so the
    # next inbound message knows to start a fresh conversation.
    is_expired = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("channel_id", "sender_id", name="uq_channel_session"),
    )
